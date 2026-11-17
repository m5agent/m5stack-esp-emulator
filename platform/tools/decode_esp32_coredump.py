#!/usr/bin/env python3
"""Decode a retained Core2 ESP-IDF UART core dump with trusted local tooling."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import selectors
import shlex
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from device_service_crash import (
    CRASH_OUTPUT_LIMIT,
    SYMBOL_FILE_LIMIT,
    identify_crash_elf,
    output_tail,
    serial_crash_observations,
    uart_dump_after_panic,
)
from esp32_uart_coredump import app_note_digest, core_notes, verify_container

FLASH_SIZE = 16 * 1024 * 1024
ARCHIVE_LIMIT = 32 * 1024 * 1024
OUTPUT_LIMIT = 256 * 1024
DECODE_TIMEOUT = 45
DECODER_VERSION = "espcoredump.py v1.17.2"
TASK_NAME = r"[A-Za-z0-9_.-]{1,16}"
TASK_ROW = re.compile(
    rf"\s*(0x[0-9a-f]{{1,8}})\s+({TASK_NAME})\s+(\d{{1,3}})/(\d{{1,3}})"
    r"\s+(\d{1,8})/(\d{1,8})\s*"
)
CRASHED_TASK = re.compile(
    rf"^Crashed task handle: (0x[0-9a-f]{{1,8}}), name: '({TASK_NAME})', GDB name: '[^\r\n]+'$",
    re.MULTILINE,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds the supported size")
    return data


def evidence_entry(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    matches = [entry for entry in archive.infolist() if entry.filename == name]
    if len(matches) != 1 or matches[0].file_size > limit:
        raise ValueError(f"evidence lacks a unique bounded {name}")
    return archive.read(matches[0])


def read_evidence(evidence: bytes) -> tuple[dict, str]:
    with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
        manifest = json.loads(evidence_entry(archive, "manifest.json", OUTPUT_LIMIT))
        entries = {}
        for name, limit in (("diagnostics/crash.json", OUTPUT_LIMIT), ("serial.log", 16 * CRASH_OUTPUT_LIMIT)):
            data = evidence_entry(archive, name, limit)
            if manifest["files"][name] != {"size": len(data), "sha256": sha256(data)}:
                raise ValueError(f"manifest digest or size differs for {name}")
            entries[name] = data
    receipt = json.loads(entries["diagnostics/crash.json"])
    session, device = manifest["session"], manifest["device"]
    if (manifest["schema_version"] != 1 or receipt["schema_version"] != 1
            or receipt["status"] != "observed" or device["device_id"] != "core2"
            or device["flash_size"] != FLASH_SIZE or device["backend"] != "qemu-esp32lx6"
            or (receipt["runtime"], receipt["device_id"]) != ("qemu", "core2")
            or any(receipt[key] != session[key] for key in (
                "session_id", "device_id", "runtime", "firmware_sha256",
            ))):
        raise ValueError("session evidence does not identify the supported native Core2 path")
    source, console = output_tail(Path("serial.log"), entries["serial.log"])
    if source != receipt["sources"]["console"]:
        raise ValueError("serial range differs from the crash receipt")
    return receipt, console


def uart_dump(console: str, receipt: dict) -> tuple[bytes, str]:
    observed = serial_crash_observations(console, "")
    panic = observed["panic"]
    if (observed["core_dump"]["status"] != "uart_reported_complete"
            or observed["core_dump"]["status"] != receipt["core_dump"]["status"]
            or panic is None or panic != receipt["panic"]):
        raise ValueError("serial does not confirm the recorded panic and completed UART dump")
    return uart_dump_after_panic(console, panic)


def validate_dump(dump: bytes, elf_sha: str) -> int:
    checksum, elf = verify_container(dump)
    if not elf_sha.startswith(app_note_digest(list(core_notes(elf)))):
        raise ValueError("dump ELF note digest differs from the application ELF")
    return checksum


def run_bounded(command: list[str], workdir: Path) -> str:
    # The trusted vendor program and GDB run without network and with a private writable directory.
    policy = ("(version 1) (allow default) (deny network*) (deny file-write*) "
              f"(allow file-write* (subpath {json.dumps(str(workdir))}))")
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(workdir), "LC_ALL": "C"}
    with subprocess.Popen(
        ["/usr/bin/sandbox-exec", "-p", policy, *command], cwd=workdir, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True,
    ) as process, selectors.DefaultSelector() as ready:
        ready.register(process.stdout, selectors.EVENT_READ)
        output = bytearray()
        deadline = time.monotonic() + DECODE_TIMEOUT
        try:
            while ready.select(max(0, deadline - time.monotonic())):
                read = os.read(process.stdout.fileno(), 8192)
                if not read:
                    break
                output.extend(read)
                if len(output) > OUTPUT_LIMIT:
                    raise ValueError("decoder output exceeded its bound")
                if time.monotonic() >= deadline:
                    raise ValueError("decoder timed out")
            else:
                raise ValueError("decoder timed out")
            if process.wait(timeout=max(0, deadline - time.monotonic())):
                raise ValueError("sandboxed decoder failed")
        finally:
            # Reap any decoder descendants left behind after errors or deadline expiry.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return output.decode("utf-8", errors="replace")


def task_summary(report: str) -> dict:
    crashed = CRASHED_TASK.findall(report)
    header = "       TCB             NAME PRIO C/B  STACK USED/FREE"
    lines = report.splitlines()
    if len(crashed) != 1 or lines.count(header) != 1:
        raise ValueError("decoder did not report a unique crashed task and FreeRTOS task table")
    cursor = lines.index(header) + 2
    tasks = []
    seen = set()
    for line in lines[cursor:]:
        if not line.strip():
            break
        row = TASK_ROW.fullmatch(line)
        if not row or len(tasks) >= 64:
            raise ValueError("decoder returned an unsupported or oversized FreeRTOS task table")
        address, name, current, base, used, free = row.groups()
        if address in seen:
            raise ValueError("decoder returned a duplicate FreeRTOS task")
        seen.add(address)
        tasks.append({
            "name": name, "crashed": (address, name) == crashed[0],
            "priority": int(current), "base_priority": int(base),
            "stack_used_bytes": int(used), "stack_free_bytes": int(free),
        })
    if not any(task["crashed"] for task in tasks) or not any(
        re.fullmatch(r"=+ ESP32 CORE DUMP END =+", line) for line in lines
    ):
        raise ValueError("decoder did not complete the crashed task report")
    return {"tasks": tasks, "crashed_task": crashed[0][1]}


def decode(evidence_path: Path, firmware_path: Path, elf_path: Path, decoder: Path, gdb: Path) -> dict:
    evidence = read_bounded(evidence_path, ARCHIVE_LIMIT)
    receipt, console = read_evidence(evidence)
    dump, prefix = uart_dump(console, receipt)
    firmware = read_bounded(firmware_path, FLASH_SIZE)
    if len(firmware) != FLASH_SIZE or sha256(firmware) != receipt["firmware_sha256"]:
        raise ValueError("merged firmware does not match the session SHA-256")
    elf = read_bounded(elf_path, SYMBOL_FILE_LIMIT)
    elf_sha = sha256(elf)
    checksum = validate_dump(dump, elf_sha)
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ValueError("a Darwin network-denied decoder sandbox is required")
    with tempfile.TemporaryDirectory(prefix="esp32-coredump-") as directory:
        workdir = Path(directory).resolve()
        copied_elf, copied_dump, gdb_wrapper = (workdir / name for name in ("app.elf", "dump.raw", "gdb"))
        copied_elf.write_bytes(elf)
        copied_dump.write_bytes(dump)
        identified = identify_crash_elf(prefix, firmware, FLASH_SIZE, 0, copied_elf, elf_sha)
        if not identified["symbolization_eligible"] or identified != receipt["elf"]:
            raise ValueError("application ELF does not match the crash receipt and firmware descriptor")
        gdb_command = shlex.join([str(gdb.resolve(strict=True)), "-nx", "-nh", "-iex",
                                  "set auto-load off", "-iex", "set debuginfod enabled off"])
        gdb_wrapper.write_text(f'#!/bin/sh\nexec {gdb_command} "$@"\n', encoding="utf-8")
        gdb_wrapper.chmod(0o700)
        decoder = str(decoder.resolve(strict=True))
        if run_bounded([decoder, "--version"], workdir).strip() != DECODER_VERSION:
            raise ValueError("unsupported Espressif core dump tool version")
        report = run_bounded([
            decoder, "info_corefile", "--gdb", str(gdb_wrapper), "--core-format", "raw",
            "--core", str(copied_dump), str(copied_elf),
        ], workdir)
    return {
        "schema_version": 1, "status": "decoded", "device_id": "core2", "runtime": "qemu",
        "evidence_sha256": sha256(evidence), "firmware_sha256": receipt["firmware_sha256"],
        "console_sha256": receipt["sources"]["console"]["sha256"], "application_elf_sha256": elf_sha,
        "dump_sha256": sha256(dump), "dump_bytes": len(dump), "dump_crc32": f"{checksum:08x}",
        "decoder_version": DECODER_VERSION,
        **task_summary(report),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("evidence", "firmware", "elf", "decoder", "gdb"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = decode(args.evidence, args.firmware, args.elf, args.decoder, args.gdb)
    except subprocess.TimeoutExpired:
        parser.exit(1, "offline core dump decode failed: decoder timed out\n")
    except (ValueError, struct.error) as error:
        parser.exit(1, f"offline core dump decode failed: {error}\n")
    except (KeyError, TypeError, OSError, zipfile.BadZipFile, RuntimeError):
        parser.exit(1, "offline core dump decode failed: unreadable or incompatible evidence or tools\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
