"""Bounded postmortem observations from retained guest and runtime output."""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
import base64
import hashlib
import json
from pathlib import Path
import re
import struct

from device_service_errors import ServiceError
from esp32_uart_coredump import decode_task_contexts
from firmware_analysis import (
    PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE, analyze_esp_image, find_app_descriptor, parse_partition_table,
)
from xtensa_elf_symbols import EM_RISCV, EM_XTENSA, ElfSymbolError, parse_elf32_symbols

CRASH_OUTPUT_LIMIT = 512 * 1024
FLASH_DUMP_LIMIT = 512 * 1024
SYMBOL_FILE_LIMIT = 64 * 1024 * 1024
ANSI_COLOR = re.compile(r"\x1b\[[0-9;]*m")
GURU = re.compile(r"^Guru Meditation Error: Core\s+([01]) panic'ed \(([^)]+)\)")
ABORT = re.compile(r"^abort\(\) was called at PC (0x[0-9a-fA-F]{8}) on core ([01])\b")
ASSERT = re.compile(r"^assert failed:\s*(.+)")
DUMP_CORE = re.compile(r"^Core\s+([01]) register dump\s*:")
DUMP_PC = re.compile(r"^(MEPC|PC)\s*:\s*(0x[0-9a-fA-F]{8})\b")
BACKTRACE = re.compile(r"(0x[0-9a-fA-F]{8}):(0x[0-9a-fA-F]{8})")
ELF_HASH = re.compile(r"^ELF file SHA256:\s+([0-9a-fA-F]{8,64})(?![0-9a-fA-F])")
ROM_BOOT = re.compile(r"^(?:ESP-ROM:|ets [A-Z][a-z]{2} +\d+ \d{4})")
IDF_BOOT = re.compile(r"^[ID] \(\s*\d+\) boot: ESP-IDF .+ bootloader")
RESET = re.compile(r"^rst:(0x[0-9a-fA-F]+)\s*\(([^)]+)\)")
APP_LOAD = re.compile(
    r"^[ID] \(\s*([0-9]{1,20})\) boot: Loaded app from partition at offset (0x[0-9a-fA-F]{1,8})$"
)
APP_LOAD_LIMIT = 16
DUMP_START = re.compile(r"=+ CORE DUMP START =+")
DUMP_END = re.compile(r"=+ CORE DUMP END =+")
FLASH_DUMP_SAVED = re.compile(r"I \(\s*\d+\) esp_core_dump_flash: Core dump has been saved to flash\.")
BACKEND_ILLEGAL = re.compile(
    r"Illegal instruction (0x[0-9a-fA-F]{8}) at PC=(0x[0-9a-fA-F]{8}) hart=([01])\b"
)
S3_IWDT_STAGE0_PREFIX = "M5_S3_IWDT_STAGE0 "
S3_IWDT_JSON_LIMIT = 2048
_S3_IWDT_UINT32 = (0, (1 << 32) - 1)
_S3_IWDT_UINT64 = (0, (1 << 64) - 1)
_S3_IWDT_TIME = (0, (1 << 63) - 1)
_S3_IWDT_DEADLINE = (-1, (1 << 63) - 1)
_S3_IWDT_SCALARS = {
    "schema_version": (1, 1), "now_ns": _S3_IWDT_TIME,
    "feed_attempts": _S3_IWDT_UINT64, "feeds": _S3_IWDT_UINT64, "feed_cpu": (-1, 1),
    "last_feed_ns": _S3_IWDT_TIME, "last_feed_deadline_ns": _S3_IWDT_DEADLINE,
    "stage0_ticks": _S3_IWDT_UINT32, "stage1_ticks": _S3_IWDT_UINT32,
    "wdt_config0": _S3_IWDT_UINT32, "wdt_prescaler": _S3_IWDT_UINT32,
    "wdt_hz": _S3_IWDT_UINT64, "wdt_irq_enabled": (0, 1),
}
_S3_IWDT_VECTORS = {
    "alarms": (2, _S3_IWDT_UINT64), "coalesced": (2, _S3_IWDT_UINT64),
    "last_alarm_ns": (2, _S3_IWDT_TIME), "last_expire_ns": (2, _S3_IWDT_DEADLINE),
    "irq_sources": (3, (0, 63)), "irq_rises": (3, _S3_IWDT_UINT64),
    "irq_falls": (3, _S3_IWDT_UINT64), "irq_level": (3, (0, 1)),
    "cpu_ps": (2, _S3_IWDT_UINT32), "cpu_intenable": (2, _S3_IWDT_UINT32),
    "cpu_intset": (2, _S3_IWDT_UINT32),
}
_S3_IWDT_MATRICES = {
    "acks": (2, _S3_IWDT_UINT64), "last_ack_ns": (2, _S3_IWDT_DEADLINE),
    "routes": (3, (0, 31)),
}


CPU_PC_DUMP_LIMIT = 64 * 1024
CPU_HEADER = re.compile(r"CPU#([0-9]{1,2})")
XTENSA_PC = re.compile(r"PC=([0-9a-fA-F]{8})")
RISCV32_PC = re.compile(r"[ \t]*pc[ \t]+([0-9a-fA-F]{8})[ \t]*")
NATIVE_C6_CPU_PATH = re.compile(r"/machine/[a-zA-Z0-9_./\[\]-]{1,128}")


def qmp_cpu_pc_sample(qmp_call, *, native_c6: bool = False) -> dict:
    """Sample only current PC values through fixed local monitor commands."""
    before = _sample_run_state(qmp_call)
    topology = qmp_call("query-cpus-fast").get("return")
    max_cpus = 1 if native_c6 else 2
    if not isinstance(topology, list) or not 1 <= len(topology) <= max_cpus:
        raise ServiceError("cpu_pc_unavailable", "unexpected native CPU topology", 409)
    target = "riscv32" if native_c6 else "xtensa"
    indices = set()
    for cpu in topology:
        if not isinstance(cpu, dict) or type(cpu.get("cpu-index")) is not int:
            raise ServiceError("cpu_pc_unavailable", "invalid native CPU identity", 409)
        reported_target = cpu.get("target") if native_c6 else cpu.get("target", cpu.get("arch"))
        if reported_target != target:
            raise ServiceError("cpu_pc_not_supported", "vCPU target does not match the native sampling path", 409)
        indices.add(cpu["cpu-index"])
    if indices != set(range(len(topology))):
        raise ServiceError("cpu_pc_unavailable", "unexpected native CPU indices", 409)
    identity = _native_c6_qmp_identity(qmp_call, topology[0]) if native_c6 else {}
    registers = qmp_call("human-monitor-command", **{"command-line": "info registers -a"}).get("return")
    after = _sample_run_state(qmp_call)
    if before != after:
        raise ServiceError("cpu_pc_state_changed", "QEMU run state changed during PC sampling", 409)
    pcs = _monitor_pcs(registers, indices, RISCV32_PC if native_c6 else XTENSA_PC)
    return {
        "source": "qmp_hmp_info_registers", "target": target, **identity,
        "run_state_before": before, "run_state_after": after,
        "cpus": [{"cpu_index": index, "pc": pcs[index]} for index in sorted(pcs)],
    }


def _native_c6_qmp_identity(qmp_call, cpu: dict) -> dict:
    cpu_path = cpu.get("qom-path")
    if not isinstance(cpu_path, str) or not NATIVE_C6_CPU_PATH.fullmatch(cpu_path):
        raise ServiceError("cpu_pc_unavailable", "native C6 CPU path is unavailable", 409)
    machine_type = qmp_call("qom-get", path="/machine", property="type").get("return")
    if machine_type != "esp32c6-machine":
        raise ServiceError("cpu_pc_not_supported", "native C6 machine type was not confirmed", 409)
    cpu_model = qmp_call("qom-get", path=cpu_path, property="type").get("return")
    if cpu_model != "espressif-riscv-cpu":
        raise ServiceError("cpu_pc_not_supported", "native C6 CPU model was not confirmed", 409)
    return {"machine_type": machine_type, "cpu_model": cpu_model}


def _sample_run_state(qmp_call) -> str:
    status = qmp_call("query-status").get("return")
    if isinstance(status, dict):
        if status.get("status") == "running" and status.get("running") is True:
            return "running"
        if status.get("status") == "paused" and status.get("running") is False:
            return "paused"
    raise ServiceError("cpu_pc_unavailable", "QEMU is not running or paused", 409)


def _monitor_pcs(registers: object, indices: set[int], pattern: re.Pattern[str]) -> dict[int, str]:
    if not isinstance(registers, str) or len(registers) > CPU_PC_DUMP_LIMIT or not registers.isascii():
        raise ServiceError("cpu_pc_unavailable", "unsupported monitor register output", 409)
    pcs = {}
    seen = set()
    index = None
    for row in registers.splitlines():
        header = CPU_HEADER.fullmatch(row)
        if header:
            index = int(header[1])
            if index in seen or index not in indices:
                raise ServiceError("cpu_pc_unavailable", "monitor CPU header differs from topology", 409)
            seen.add(index)
        pc = pattern.fullmatch(row)
        if pc:
            if index not in indices or index in pcs:
                raise ServiceError("cpu_pc_unavailable", "monitor PC has an ambiguous CPU index", 409)
            pcs[index] = "0x" + pc[1].lower()
    if pcs.keys() != indices:
        raise ServiceError("cpu_pc_unavailable", "not all native CPUs reported a current PC", 409)
    return pcs


def output_tail(path: Path, captured: bytes | None = None) -> tuple[dict, str]:
    """Describe and decode the bounded byte range used by the parser."""
    if captured is None:
        try:
            with path.open("rb") as stream:
                size = stream.seek(0, 2)
                offset = max(0, size - CRASH_OUTPUT_LIMIT)
                stream.seek(offset)
                data = stream.read(size - offset)
        except OSError:
            return {"status": "unavailable", "bytes": 0}, ""
    else:
        offset = max(0, len(captured) - CRASH_OUTPUT_LIMIT)
        data = captured[offset:]
    return _output_sample(data, offset, truncated=offset > 0)


def _output_sample(data: bytes, offset: int, *, truncated: bool) -> tuple[dict, str]:
    # Ignore a potentially partial first line and unfinished current line.
    # Hash the full captured byte range for reproducibility.
    body = data.split(b"\n", 1)[-1] if offset and b"\n" in data else data
    body = body[:body.rfind(b"\n") + 1]
    return {
        "status": "available" if data else "empty",
        "offset": offset,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "truncated": truncated,
    }, ANSI_COLOR.sub("", body.decode("utf-8", errors="replace"))


def _s3_iwdt_stage0_observation(stderr: str) -> dict | None:
    """Accept one bounded, versioned native trace line, independently of the guest console."""
    lines = [line for line in stderr.splitlines() if line.startswith(S3_IWDT_STAGE0_PREFIX)]
    if len(lines) != 1 or len(lines[0]) > S3_IWDT_JSON_LIMIT or not lines[0].isascii():
        return None
    try:
        timing = json.loads(lines[0][len(S3_IWDT_STAGE0_PREFIX):])
    except (ValueError, RecursionError):
        return None
    if not isinstance(timing, dict) or set(timing) != (
        _S3_IWDT_SCALARS.keys() | _S3_IWDT_VECTORS.keys() | _S3_IWDT_MATRICES.keys()
        | {"cpu_irq_snapshot_available"}
    ):
        return None

    def integer(value, bounds):
        return type(value) is int and bounds[0] <= value <= bounds[1]

    def vector(value, size, bounds):
        return isinstance(value, list) and len(value) == size and all(integer(item, bounds) for item in value)

    if not all(integer(timing[key], bounds) for key, bounds in _S3_IWDT_SCALARS.items()):
        return None
    if not all(vector(timing[key], size, bounds) for key, (size, bounds) in _S3_IWDT_VECTORS.items()):
        return None
    for key, (rows, bounds) in _S3_IWDT_MATRICES.items():
        matrix = timing[key]
        if not isinstance(matrix, list) or len(matrix) != rows or not all(vector(row, 2, bounds) for row in matrix):
            return None
    if (timing["irq_sources"] != [55, 57, 58] or timing["feeds"] > timing["feed_attempts"]
            or type(timing["cpu_irq_snapshot_available"]) is not bool):
        return None
    return {"kind": "esp32s3_iwdt_stage0", "source": "runtime_stderr", "timing": timing}


def crash_console_observations(
    path: Path, stderr: str, captured: bytes | None = None, *, native_s3: bool = False,
    core_dump_chip_id: int | None = None, capture_task_core: Callable[[bytes], None] | None = None,
    decode_flash_dump: Callable[[str], dict] | None = None,
) -> tuple[dict, dict]:
    """Use one bounded tail and, if useful, the fixed console prefix."""
    if captured is not None:
        return _crash_console_snapshot(
            len(captured), lambda offset, size: captured[offset:offset + size], stderr,
            native_s3=native_s3, core_dump_chip_id=core_dump_chip_id, capture_task_core=capture_task_core,
            decode_flash_dump=decode_flash_dump,
        )
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, 2)

            def read(offset: int, length: int) -> bytes:
                stream.seek(offset)
                return stream.read(length)

            return _crash_console_snapshot(
                size, read, stderr, native_s3=native_s3, core_dump_chip_id=core_dump_chip_id,
                capture_task_core=capture_task_core, decode_flash_dump=decode_flash_dump,
            )
    except OSError:
        return {"status": "unavailable", "bytes": 0}, serial_crash_observations("", stderr, native_s3=native_s3)


def _crash_console_snapshot(
    size: int, read: Callable[[int, int], bytes], stderr: str, *, native_s3: bool,
    core_dump_chip_id: int | None, capture_task_core: Callable[[bytes], None] | None,
    decode_flash_dump: Callable[[str], dict] | None,
) -> tuple[dict, dict]:
    offset = max(0, size - CRASH_OUTPUT_LIMIT)
    tail = read(offset, size - offset)
    source, console = _output_sample(tail, offset, truncated=offset > 0)
    observed = serial_crash_observations(console, stderr, native_s3=native_s3)
    if core_dump_chip_id is not None and observed["core_dump"]["status"] == "uart_reported_complete":
        observed["core_dump"]["decoding"] = _decode_uart_task_contexts(
            console, observed["panic"], core_dump_chip_id, capture_task_core=capture_task_core,
        )
    elif decode_flash_dump is not None and observed["core_dump"]["status"] == "flash_reported_saved":
        observed["core_dump"]["decoding"] = _decode_flash_after_panic(
            console, observed["panic"], decode_flash_dump,
        )
    if not offset or observed["panic"] is not None or len(tail) != size - offset:
        return source, observed
    try:
        prefix = read(0, CRASH_OUTPUT_LIMIT)
    except OSError:
        return source, observed
    if len(prefix) == CRASH_OUTPUT_LIMIT:
        earlier_source, earlier_text = _output_sample(prefix, 0, truncated=True)
        earlier = serial_crash_observations(earlier_text, "")
        if earlier["panic"] is not None:
            observed["earlier_console"] = {
                "scope": "console_prefix",
                "source": earlier_source,
                "panic": earlier["panic"],
                "cpus": earlier["cpus"],
            }
    return source, observed


def serial_crash_observations(console: str, stderr: str, *, native_s3: bool = False) -> dict:
    panic = None
    active = False
    core = None
    cpus = {}
    dump_status = "not_observed"
    dump_open = False
    reset_reports = []
    application_loads = []
    application_load_count = 0
    boot_ordinal = None
    boot_stage = 3  # Unknown until a complete ROM banner is captured.
    rom_boots = idf_boots = reboot_requests = panic_count = 0
    task_watchdog_reports = 0
    for console_line, raw in enumerate(console.splitlines(), 1):
        line = raw.strip()
        reset = RESET.match(line)
        rom_boot = ROM_BOOT.match(line)
        idf_boot = IDF_BOOT.match(line)
        if rom_boot or idf_boot or reset or line == "Rebooting...":
            if rom_boot:
                boot_ordinal, boot_stage = rom_boots + 1, 0
            elif reset:
                if boot_stage != 0:
                    boot_ordinal = None
                boot_stage = 1
            elif idf_boot:
                if boot_stage >= 2:
                    boot_ordinal = None
                boot_stage = 2
            else:
                boot_ordinal, boot_stage = None, 3
            rom_boots += bool(rom_boot)
            idf_boots += bool(idf_boot)
            reboot_requests += line == "Rebooting..."
            if reset:
                reset_reports.append({"code": reset[1].lower(), "reason": reset[2][:100]})
                reset_reports = reset_reports[-16:]
            active = False
            dump_open = False
        app_load = APP_LOAD.fullmatch(line)
        if app_load and int(app_load[1]) <= (1 << 64) - 1:
            application_load_count += 1
            application_loads.append({
                "console_line": console_line,
                "boot_ordinal": boot_ordinal,
                "idf_log_ms": int(app_load[1]),
                "offset": int(app_load[2], 16),
            })
            application_loads = application_loads[-APP_LOAD_LIMIT:]
            boot_stage = 3
        if "task_wdt: Task watchdog got triggered" in line:
            task_watchdog_reports += 1
        opening = GURU.match(line) or ABORT.match(line) or ASSERT.match(line)
        if opening:
            if opening.re is GURU:
                core, reason = int(opening[1]), opening[2]
            elif opening.re is ABORT:
                core, reason = int(opening[2]), "abort"
            else:
                core, reason = None, opening[1]
            panic = {
                "kind": "watchdog" if "wdt" in reason.lower() or "watchdog" in reason.lower() else "panic",
                "core": core,
                "reason": reason[:240],
                "line": line[:400],
                "core_unassigned_backtrace": [],
                "elf_sha256_prefix": None,
            }
            if opening.re is ABORT:
                panic["abort_call_site_pc"] = opening[1].lower()
            panic_count += 1
            cpus = {}
            active = True
            dump_open = False
        elif active:
            register_dump = DUMP_CORE.match(line)
            pc = DUMP_PC.match(line)
            elf = ELF_HASH.match(line)
            if register_dump:
                core = int(register_dump[1])
                cpus.setdefault(core, {"core": core})
            elif pc and core in cpus:
                cpus[core].update(pc=pc[2].lower(), register=pc[1], pc_source="guest_register_dump")
            elif line.startswith("Backtrace:"):
                frames = [
                    {"pc": addr.lower(), "sp": sp.lower()} for addr, sp in BACKTRACE.findall(line)[:64]
                ]
                if core is None:
                    panic["core_unassigned_backtrace"] = frames
                elif frames:
                    cpus.setdefault(core, {"core": core})["backtrace"] = frames
            elif elf:
                panic["elf_sha256_prefix"] = elf[1].lower()
        if DUMP_START.fullmatch(line):
            dump_open = True
            dump_status = "uart_incomplete"
        elif dump_open and DUMP_END.fullmatch(line):
            dump_open = False
            dump_status = "uart_reported_complete"
        elif "Core dump has been saved to flash" in line:
            dump_status = "flash_reported_saved"
        elif "Core dump data check failed" in line:
            dump_status = "flash_check_failed"
        elif "Failed to write core dump" in line or "Core dump write failed" in line:
            dump_status = "write_failed"

    backend_observations = {}
    for line in stderr.splitlines():
        match = BACKEND_ILLEGAL.search(line)
        if match:
            core = int(match[3])
            backend_observations[core] = {
                "kind": "illegal_instruction_reported", "hart": core,
                "pc": match[2].lower(), "instruction": match[1].lower(),
                "source": "runtime_stderr",
            }
    backend = sorted(backend_observations.values(), key=lambda item: item["hart"])
    if native_s3:
        timing = _s3_iwdt_stage0_observation(stderr)
        if timing is not None:
            backend.append(timing)
    return {
        "panic": panic,
        "panic_count": panic_count,
        "cpus": sorted(cpus.values(), key=lambda item: item["core"]),
        "boot": {"rom_banners": rom_boots, "idf_banners": idf_boots,
                 "reboot_requests": reboot_requests, "reset_reports": reset_reports,
                 "application_load_count": application_load_count,
                 "application_loads": application_loads},
        "task_watchdog_reports": task_watchdog_reports,
        "core_dump": {"status": dump_status},
        "backend_observations": backend,
    }


def _lines_after_panic(console: str, panic: dict) -> list[str]:
    lines = [line.strip() for line in console.splitlines()]
    panic_index = len(lines) - 1 - lines[::-1].index(panic["line"])
    after_panic = []
    for line in lines[panic_index + 1:]:
        if line == "Rebooting..." or RESET.match(line) or ROM_BOOT.match(line) or IDF_BOOT.match(line):
            break
        after_panic.append(line)
    return after_panic


def _panic_digest(lines: list[str], panic: dict) -> str:
    prefix = panic["elf_sha256_prefix"]
    if not re.fullmatch(r"[0-9a-f]{8,64}", prefix or ""):
        raise ValueError("panic lacks an application ELF SHA-256 prefix")
    reported = [match[1].lower() for line in lines if (match := ELF_HASH.match(line))]
    if reported != [prefix]:
        raise ValueError("dump is not associated with the panic ELF digest")
    return prefix


def uart_dump_after_panic(console: str, panic: dict) -> tuple[bytes, str]:
    """Select one completed transfer associated with the latest recognized panic."""
    after_panic = _lines_after_panic(console, panic)
    starts = [i for i, line in enumerate(after_panic) if DUMP_START.fullmatch(line)]
    ends = [i for i, line in enumerate(after_panic) if DUMP_END.fullmatch(line)]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("serial does not contain one completed dump after the recorded panic")
    prefix = _panic_digest(after_panic[:starts[0]], panic)
    payload = after_panic[starts[0] + 1:ends[0]]
    if not payload or any(not line or len(line) > 128 for line in payload):
        raise ValueError("invalid UART Base64 dump lines")
    return b"".join(base64.b64decode(line, validate=True) for line in payload), prefix


def _decode_flash_after_panic(console: str, panic: dict | None, decode: Callable[[str], dict]) -> dict:
    if panic is None:
        return {"status": "unavailable", "reason": "panic_unavailable"}
    try:
        lines = _lines_after_panic(console, panic)
        markers = [index for index, line in enumerate(lines) if FLASH_DUMP_SAVED.fullmatch(line)]
        if len(markers) != 1:
            raise ValueError("no unique Flash write completion after the panic")
        prefix = _panic_digest(lines[:markers[0]], panic)
    except ValueError:
        return {"status": "unavailable", "reason": "invalid_or_unbound_flash_write"}
    return decode(prefix)


def decode_flash_task_contexts(
    flash_path: Path | None, firmware_path: Path, flash_size: int, panic_prefix: str, *,
    chip_id: int, capture_task_core: Callable[[bytes], None] | None,
) -> dict:
    """Decode a new plaintext ESP-IDF dump within the admitted Flash layout."""
    if flash_path is None:
        return {"status": "unavailable", "reason": "flash_unavailable"}
    try:
        with firmware_path.open("rb") as firmware, flash_path.open("rb") as flash:
            if flash.seek(0, 2) != flash_size:
                return {"status": "unavailable", "reason": "invalid_or_unsupported_flash_layout"}
            firmware.seek(PARTITION_TABLE_OFFSET)
            flash.seek(PARTITION_TABLE_OFFSET)
            table = firmware.read(PARTITION_TABLE_SIZE)
            area = _flash_dump_partition(table, flash_size) if flash.read(PARTITION_TABLE_SIZE) == table else None
            if area is None:
                return {"status": "unavailable", "reason": "invalid_or_unsupported_flash_layout"}
            offset, size = area
            flash.seek(offset)
            header = flash.read(4)
            if len(header) != 4:
                return {"status": "unavailable", "reason": "unsupported_or_invalid_dump"}
            length, = struct.unpack("<I", header)
            if not 80 <= length <= min(size, FLASH_DUMP_LIMIT):
                return {"status": "unavailable", "reason": "unsupported_or_invalid_dump"}
            dump = header + flash.read(length - 4)
            firmware.seek(offset)
            baseline = firmware.read(length)
            if dump == baseline.ljust(length, b"\xff"):
                return {"status": "unavailable", "reason": "unchanged_flash_dump"}
    except OSError:
        return {"status": "unavailable", "reason": "flash_unavailable"}
    try:
        decoded = decode_task_contexts(dump, panic_prefix, chip_id=chip_id, capture_core=capture_task_core)
    except ValueError:
        return {"status": "unavailable", "reason": "unsupported_or_invalid_dump"}
    return {**decoded, "source": "virtual_flash", "flash_offset": offset}


def _flash_dump_partition(table: bytes, flash_size: int) -> tuple[int, int] | None:
    if len(table) != PARTITION_TABLE_SIZE:
        return None
    layout = parse_partition_table(table, offset=0, image_size=flash_size)
    if not layout["valid"] or layout["warnings"]:
        return None
    parts = layout["partitions"]
    matches = [part for part in parts if (part["type"], part["subtype"]) == (1, 3)]
    if len(matches) != 1:
        return None
    partition = matches[0]
    offset, size = partition["offset"], partition["size"]
    if (
        partition["flags"] or offset < PARTITION_TABLE_OFFSET + PARTITION_TABLE_SIZE
        or offset % 4096 or size < 4096 or size % 4096
        or any(
            part is not partition and part["offset"] < offset + size
            and offset < part["offset"] + part["size"] for part in parts
        )
    ):
        return None
    return offset, size


def _decode_uart_task_contexts(
    console: str, panic: dict | None, chip_id: int, *,
    capture_task_core: Callable[[bytes], None] | None,
) -> dict:
    if panic is None:
        return {"status": "unavailable", "reason": "panic_unavailable"}
    try:
        dump, prefix = uart_dump_after_panic(console, panic)
    except ValueError:
        return {"status": "unavailable", "reason": "invalid_or_unbound_uart_transfer"}
    try:
        return decode_task_contexts(dump, prefix, chip_id=chip_id, capture_core=capture_task_core)
    except ValueError:
        return {"status": "unavailable", "reason": "unsupported_or_invalid_dump"}


def firmware_elf_candidates(data: bytes, flash_size: int, chip_id: int | None, prefix: str) -> set[str]:
    """Use validated application headers and the canonical first segment descriptor."""
    table = parse_partition_table(data, image_size=flash_size)
    candidates = set()
    if not table["valid"]:
        return candidates
    for partition in table["partitions"]:
        if partition["type"] != 0:
            continue
        offset = partition["offset"]
        image = analyze_esp_image(data, offset)
        if not image["valid"] or image.get("chip_id") != chip_id:
            continue
        if image["image_end"] > offset + partition["size"]:
            continue
        desc_start = offset + 32
        desc_end = desc_start + 256
        if not image.get("segments") or image["segments"][0]["length"] < 256:
            continue
        descriptor = find_app_descriptor(data, desc_start, desc_end)
        if not descriptor or descriptor["offset"] != desc_start:
            continue
        expected = descriptor["elf_sha256"]
        if expected not in {"0" * 64, "f" * 64} and expected.startswith(prefix):
            candidates.add(expected)
    return candidates


def identify_crash_elf(
    reported: str | None, data: bytes | None, flash_size: int,
    chip_id: int | None, artifact: Path | None, artifact_sha: str | None,
) -> dict:
    result = {
        "status": "not_uploaded", "reported_sha256_prefix": reported,
        "artifact_sha256": artifact_sha, "expected_sha256": None,
        "symbolization_eligible": False,
    }
    if artifact is None:
        return result
    with artifact.open("rb") as handle:
        if handle.read(4) != b"\x7fELF":
            return {**result, "status": "invalid_elf"}
        handle.seek(0)
        if hashlib.file_digest(handle, "sha256").hexdigest() != artifact_sha:
            return {**result, "status": "artifact_hash_mismatch"}
    if data is None or not reported:
        return {**result, "status": "identity_unavailable"}
    candidates = firmware_elf_candidates(data, flash_size, chip_id, reported)
    if not candidates:
        return {**result, "status": "identity_unavailable"}
    if len(candidates) != 1:
        return {**result, "status": "identity_ambiguous"}
    expected = next(iter(candidates))
    if expected != artifact_sha:
        return {**result, "status": "mismatch", "expected_sha256": expected}
    return {**result, "status": "matched", "expected_sha256": expected, "symbolization_eligible": True}


def crash_function_symbols(
    observed: dict, artifact: Path | None, *, expected_machine: int = EM_XTENSA,
    artifact_sha256: str | None = None,
) -> dict:
    """Annotate guest-reported addresses after exact ELF admission."""
    if artifact is None:
        return {"status": "not_decoded", "addresses": []}
    panic = observed["panic"]
    pcs = {row["pc"] for row in observed["cpus"] if row.get("pc")}
    pcs.update(row["pc"] for row in panic["core_unassigned_backtrace"])
    pcs.update(frame["pc"] for row in observed["cpus"] for frame in row.get("backtrace", []))
    if panic.get("abort_call_site_pc"):
        pcs.add(panic["abort_call_site_pc"])
    decoded = observed["core_dump"].get("decoding")
    task_pcs = set()
    if decoded and decoded["status"] == "decoded" and artifact_sha256 and artifact_sha256.startswith(
        decoded["dump_elf_sha256_prefix"]
    ):
        task_pcs = {row["pc"] for row in decoded["tasks"] if row["pc"]}
    if not (pcs or task_pcs):
        return {"status": "no_addresses", "addresses": []}
    target = "riscv" if expected_machine == EM_RISCV else "xtensa"
    source = f"matched_{target}_elf_function_ranges"
    try:
        if artifact.stat().st_size > SYMBOL_FILE_LIMIT:
            return _unavailable_symbols("elf_symbol_file_too_large", decoded if task_pcs else None)
        symbols = parse_elf32_symbols(artifact, expected_machine=expected_machine)
    except (OSError, ElfSymbolError):
        return _unavailable_symbols(f"unsupported_or_unreadable_{target}_symbols", decoded if task_pcs else None)

    observed_pcs = {int(pc, 16) for pc in pcs}
    observed_task_pcs = {int(pc, 16) for pc in task_pcs}
    lookup = sorted(observed_pcs | observed_task_pcs)
    matches: dict[int, set[tuple[str, int]]] = {pc: set() for pc in lookup}
    for named_symbols in symbols.values():
        for symbol in named_symbols:
            if symbol.type != "function":
                continue
            start = bisect_left(lookup, symbol.value)
            end = bisect_left(lookup, symbol.value + max(1, symbol.size))
            for pc in lookup[start:end]:
                matches[pc].add((symbol.name[:240], pc - symbol.value))

    if task_pcs:
        decoded["symbols"] = _symbol_receipt(observed_task_pcs, matches, source)
    return _symbol_receipt(observed_pcs, matches, source)


def _unavailable_symbols(reason: str, task_dump: dict | None) -> dict:
    result = {"status": "unavailable", "reason": reason, "addresses": []}
    if task_dump is not None:
        task_dump["symbols"] = result
    return result


def _symbol_receipt(pcs: set[int], matches: dict[int, set[tuple[str, int]]], source: str) -> dict:
    if not pcs:
        return {"status": "no_addresses", "addresses": []}
    resolved = []
    for pc in sorted(pcs):
        candidates = matches[pc]
        row = {"pc": f"0x{pc:08x}", "status": "unresolved"}
        if len(candidates) == 1:
            name, offset = next(iter(candidates))
            row.update(status="resolved", function=name, offset=offset)
        elif candidates:
            row["status"] = "ambiguous"
        resolved.append(row)
    count = sum(row["status"] == "resolved" for row in resolved)
    if count == len(resolved):
        status = "decoded"
    elif count:
        status = "partial"
    else:
        status = "unresolved"
    return {"status": status, "source": source, "addresses": resolved}
