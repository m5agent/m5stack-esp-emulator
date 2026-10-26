#!/usr/bin/env python3
"""Deliver a real HCI event through the firmware BTDM HLI queue."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from qemu_accel import core2_accel_args  # noqa: E402

DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_ELF = ROOT / ".work/uiflow2-core2-symbols/micropython.elf"
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEVICE_PATH = "/machine/peripheral-anon/device[0]"
RESET_COMPLETE = bytes.fromhex("040e0401030c00")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class QMP:
    def __init__(self, path: Path, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if path.exists():
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    sock.connect(str(path))
                    self.sock = sock
                    break
                except OSError:
                    sock.close()
            if time.monotonic() >= deadline:
                raise RuntimeError("QMP socket did not become ready")
            time.sleep(0.02)
        self.stream = self.sock.makefile("rwb", buffering=0)
        if "QMP" not in json.loads(self.stream.readline()):
            raise RuntimeError("invalid QMP greeting")
        self.command("qmp_capabilities")

    def command(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {"execute": name}
        if arguments is not None:
            payload["arguments"] = arguments
        self.stream.write(json.dumps(payload).encode() + b"\n")
        while True:
            response = json.loads(self.stream.readline())
            if "event" in response:
                continue
            if "error" in response:
                raise RuntimeError(
                    f"QMP {name} failed: {response['error']}"
                )
            return response.get("return")

    def get(self, property_name: str) -> Any:
        return self.command(
            "qom-get",
            {"path": DEVICE_PATH, "property": property_name},
        )

    def close(self) -> None:
        self.stream.close()
        self.sock.close()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_h4_command(peer: socket.socket, timeout: float) -> bytes:
    peer.settimeout(0.2)
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = peer.recv(4096)
        except TimeoutError:
            chunk = b""
        if chunk:
            data.extend(chunk)
            if len(data) >= 4:
                expected = 4 + data[3]
                if len(data) >= expected:
                    return bytes(data[:expected])
        time.sleep(0.02)
    raise RuntimeError(
        f"timeout waiting for H4 command: {bytes(data).hex()}"
    )


def wait_qmp_value(
    qmp: QMP,
    property_name: str,
    predicate,
    timeout: float,
) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = qmp.get(property_name)
        if predicate(value):
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"timeout waiting for {property_name}: {value!r}"
            )
        time.sleep(0.02)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()

    for label, path in (
        ("image", args.image),
        ("QEMU", args.qemu),
        ("ELF", args.elf),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")

    sys.path.insert(0, str(ROOT / "platform/tools"))
    from xtensa_elf_symbols import resolve_symbols

    symbols = resolve_symbols(
        args.elf,
        [
            "vhci_env_p",
            "malloc",
            "g_rw_schd_queue",
            "s_meta_queue_ptr",
            "ble_transport_alloc_evt",
            "ble_transport_to_hs_evt_impl",
        ],
    )
    out_dir = args.out_dir or Path(
        tempfile.mkdtemp(prefix="m5-core2-hli-event-")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    serial = out_dir / "serial.log"
    qmp_path = out_dir / "qmp.sock"
    port = free_port()
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(1)
    listener.settimeout(args.timeout)
    hci_device = (
        "esp32-native-hci,chardev=hci,"
        f"env-pointer-address=0x{symbols['vhci_env_p'].value:08x},"
        f"c2h-allocator-address=0x{symbols['malloc'].value:08x},"
        "c2h-scratch-size=2048,"
        "scheduler-queue-address="
        f"0x{symbols['g_rw_schd_queue'].value:08x},"
        "meta-queue-pointer-address="
        f"0x{symbols['s_meta_queue_ptr'].value:08x},"
        "hli-test-event=13,"
        "hli-test-callback="
        f"0x{symbols['ble_transport_to_hs_evt_impl'].value:08x},"
        "hli-event-allocator-address="
        f"0x{symbols['ble_transport_alloc_evt'].value:08x},"
        "hli-event-buffer-size=70,"
        "hli-event-data=0e0401030c00"
    )
    command = [
        str(args.qemu),
        "-snapshot",
        *core2_accel_args(),
        "-m",
        "0",
        "-M",
        "m5core2",
        "-drive",
        f"file={args.image},if=mtd,format=raw",
        "-L",
        str(args.rom_dir),
        "-display",
        "none",
        "-d",
        "guest_errors",
        "-serial",
        f"file:{serial}",
        "-no-reboot",
        "-chardev",
        (
            "socket,id=hci,host=127.0.0.1,"
            f"port={port},server=off,nodelay=on"
        ),
        "-device",
        hci_device,
        "-qmp",
        f"unix:{qmp_path},server=on,wait=off",
    ]
    process = subprocess.Popen(
        command,
        stdout=(out_dir / "qemu.stdout").open("wb"),
        stderr=(out_dir / "qemu.stderr").open("wb"),
    )
    peer: socket.socket | None = None
    qmp: QMP | None = None
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "m5stack-core2-native-hci-hli-event",
        "scope": "virtual-device firmware HLI event delivery",
        "status": "FAIL",
        "firmware": {
            "file": args.image.name,
            "sha256": sha256(args.image),
            "bytes": args.image.stat().st_size,
        },
        "qemu_sha256": sha256(args.qemu),
        "elf_sha256": sha256(args.elf),
        "symbols": {
            name: f"0x{symbol.value:08x}"
            for name, symbol in sorted(symbols.items())
        },
        "checks": {},
    }
    try:
        peer, _ = listener.accept()
        qmp = QMP(qmp_path, args.timeout)
        reset = read_h4_command(peer, args.timeout)
        posts = wait_qmp_value(
            qmp,
            "hli-posts",
            lambda value: value >= 1,
            args.timeout,
        )
        next_command = read_h4_command(peer, args.timeout)
        consumed = wait_qmp_value(
            qmp,
            "hli-consumed",
            lambda value: value >= 1,
            args.timeout,
        )
        counters = {
            name: qmp.get(name)
            for name in (
                "hli-posts",
                "hli-consumed",
                "hli-event-buffers",
                "hli-errors",
                "hli-last-event",
                "hli-queue-depth",
                "meta-queue-depth",
                "h2c-packets",
                "h2c-incomplete-writes",
                "malformed-packets",
                "dropped-packets",
                "last-error",
            )
        }
        serial_text = (
            serial.read_text(errors="replace")
            if serial.is_file()
            else ""
        )
        result.update(
            {
                "reset_command": reset.hex(),
                "next_command": next_command.hex(),
                "hli_posts": posts,
                "hli_consumed": consumed,
                "counters": counters,
            }
        )
        result["checks"] = {
            "stock_reset_captured": reset == bytes.fromhex("01030c00"),
            "reset_complete_queued": counters["hli-posts"] == 1,
            "guest_hli_queue_consumed": counters["hli-consumed"] == 1,
            "pool_event_buffer_allocated": counters["hli-event-buffers"] == 1,
            "hli_event_13": counters["hli-last-event"] == 13,
            "hli_no_errors": counters["hli-errors"] == 0,
            "hli_queue_empty": counters["hli-queue-depth"] == 0,
            "meta_queue_empty": counters["meta-queue-depth"] == 0,
            "guest_sent_next_command": next_command.startswith(b"\x01"),
            "guest_progressed_past_reset": next_command != reset,
            "qom_saw_second_h2c": counters["h2c-packets"] >= 2,
            "partial_h2c_length_writes_observed": (
                counters["h2c-incomplete-writes"] >= 1
            ),
            "no_malformed_packets": counters["malformed-packets"] == 0,
            "no_dropped_packets": counters["dropped-packets"] == 0,
            "no_guest_exception_marker": not any(
                marker in serial_text
                for marker in (
                    "Guru Meditation",
                    "LoadProhibited",
                    "InstrFetchProhibited",
                    "Cache disabled",
                    "assert failed",
                )
            ),
        }
        if not all(result["checks"].values()):
            raise RuntimeError(f"HLI event checks failed: {result['checks']}")
        result["status"] = "PASS"
        result["not_claimed"] = [
            "complete HCI command sequence",
            "BLE connection or GATT",
            "bit-exact controller/baseband",
            "physical hardware",
        ]
    except Exception as error:
        result["error"] = str(error)
        if qmp is not None:
            result["diagnostics"] = {}
            for property_name in (
                "hli-valid",
                "hli-posts",
                "hli-consumed",
                "hli-event-buffers",
                "hli-event-buffer-address",
                "hli-event-length",
                "hli-errors",
                "hli-last-event",
                "hli-queue-begin",
                "hli-queue-end",
                "hli-queue-depth",
                "meta-queue-begin",
                "meta-queue-end",
                "meta-queue-depth",
                "h2c-packets",
                "h2c-incomplete-writes",
                "malformed-packets",
                "dropped-packets",
                "last-error",
            ):
                try:
                    result["diagnostics"][property_name] = qmp.get(
                        property_name
                    )
                except (OSError, RuntimeError) as diagnostic_error:
                    result["diagnostics"][property_name] = (
                        f"unavailable: {diagnostic_error}"
                    )
    finally:
        if peer is not None:
            peer.close()
        listener.close()
        if qmp is not None:
            try:
                qmp.command("quit")
            except (OSError, RuntimeError):
                pass
            qmp.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        result["qemu_exit_code"] = process.returncode
        if process.returncode != 0:
            result["status"] = "FAIL"
            result["checks"]["qemu_clean_exit"] = False
        else:
            result["checks"]["qemu_clean_exit"] = True
        evidence = out_dir / "evidence.json"
        evidence.write_text(
            json.dumps(result, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2))
        print(f"evidence={evidence}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
