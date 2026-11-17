"""Bounded postmortem observations from retained guest and runtime output."""
from __future__ import annotations

from bisect import bisect_left
import hashlib
from pathlib import Path
import re

from device_service_errors import ServiceError
from firmware_analysis import analyze_esp_image, find_app_descriptor, parse_partition_table
from xtensa_elf_symbols import ElfSymbolError, parse_elf32_symbols

CRASH_OUTPUT_LIMIT = 512 * 1024
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
BACKEND_ILLEGAL = re.compile(
    r"Illegal instruction (0x[0-9a-fA-F]{8}) at PC=(0x[0-9a-fA-F]{8}) hart=([01])\b"
)


CPU_PC_DUMP_LIMIT = 64 * 1024
CPU_HEADER = re.compile(r"CPU#([0-9]{1,2})")
XTENSA_PC = re.compile(r"PC=([0-9a-fA-F]{8})")


def qmp_cpu_pc_sample(qmp_call) -> dict:
    """Sample only current PC values through fixed local monitor commands."""
    before = _sample_run_state(qmp_call)
    topology = qmp_call("query-cpus-fast").get("return")
    if not isinstance(topology, list) or not 1 <= len(topology) <= 2:
        raise ServiceError("cpu_pc_unavailable", "unexpected native CPU topology", 409)
    indices = set()
    for cpu in topology:
        if not isinstance(cpu, dict) or type(cpu.get("cpu-index")) is not int:
            raise ServiceError("cpu_pc_unavailable", "invalid native CPU identity", 409)
        if cpu.get("target", cpu.get("arch")) != "xtensa":
            raise ServiceError("cpu_pc_not_supported", "live PC sampling supports Xtensa native QEMU", 409)
        indices.add(cpu["cpu-index"])
    if indices != set(range(len(topology))):
        raise ServiceError("cpu_pc_unavailable", "unexpected native CPU indices", 409)
    registers = qmp_call("human-monitor-command", **{"command-line": "info registers -a"}).get("return")
    after = _sample_run_state(qmp_call)
    if before != after:
        raise ServiceError("cpu_pc_state_changed", "QEMU run state changed during PC sampling", 409)
    pcs = _xtensa_monitor_pcs(registers, indices)
    return {
        "source": "qmp_hmp_info_registers", "target": "xtensa",
        "run_state_before": before, "run_state_after": after,
        "cpus": [{"cpu_index": index, "pc": pcs[index]} for index in sorted(pcs)],
    }


def _sample_run_state(qmp_call) -> str:
    status = qmp_call("query-status").get("return")
    if isinstance(status, dict):
        if status.get("status") == "running" and status.get("running") is True:
            return "running"
        if status.get("status") == "paused" and status.get("running") is False:
            return "paused"
    raise ServiceError("cpu_pc_unavailable", "QEMU is not running or paused", 409)


def _xtensa_monitor_pcs(registers: str, indices: set[int]) -> dict[int, str]:
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
        pc = XTENSA_PC.fullmatch(row)
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
    # Ignore a potentially partial first line and unfinished current line.
    # Hash the full captured byte range for reproducibility.
    body = data.split(b"\n", 1)[-1] if offset and b"\n" in data else data
    body = body[:body.rfind(b"\n") + 1]
    return {
        "status": "available" if data else "empty",
        "offset": offset,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "truncated": offset > 0,
    }, ANSI_COLOR.sub("", body.decode("utf-8", errors="replace"))


def serial_crash_observations(console: str, stderr: str) -> dict:
    panic = None
    active = False
    core = None
    cpus = {}
    dump_status = "not_observed"
    dump_open = False
    reset_reports = []
    rom_boots = idf_boots = reboot_requests = panic_count = 0
    task_watchdog_reports = 0
    for raw in console.splitlines():
        line = raw.strip()
        reset = RESET.match(line)
        rom_boot = ROM_BOOT.match(line)
        idf_boot = IDF_BOOT.match(line)
        if rom_boot or idf_boot or reset or line == "Rebooting...":
            rom_boots += bool(rom_boot)
            idf_boots += bool(idf_boot)
            reboot_requests += line == "Rebooting..."
            if reset:
                reset_reports.append({"code": reset[1].lower(), "reason": reset[2][:100]})
                reset_reports = reset_reports[-16:]
            active = False
            dump_open = False
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
        if re.fullmatch(r"=+ CORE DUMP START =+", line):
            dump_open = True
            dump_status = "uart_incomplete"
        elif dump_open and re.fullmatch(r"=+ CORE DUMP END =+", line):
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
    return {
        "panic": panic,
        "panic_count": panic_count,
        "cpus": sorted(cpus.values(), key=lambda item: item["core"]),
        "boot": {"rom_banners": rom_boots, "idf_banners": idf_boots,
                 "reboot_requests": reboot_requests, "reset_reports": reset_reports},
        "task_watchdog_reports": task_watchdog_reports,
        "core_dump": {"status": dump_status},
        "backend_observations": sorted(backend_observations.values(), key=lambda item: item["hart"]),
    }


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


def crash_function_symbols(observed: dict, artifact: Path | None) -> dict:
    """Annotate only guest-reported Xtensa addresses, after exact ELF admission."""
    if artifact is None:
        return {"status": "not_decoded", "addresses": []}
    panic = observed["panic"]
    pcs = {row["pc"] for row in observed["cpus"] if row.get("pc")}
    pcs.update(row["pc"] for row in panic["core_unassigned_backtrace"])
    pcs.update(frame["pc"] for row in observed["cpus"] for frame in row.get("backtrace", []))
    if panic.get("abort_call_site_pc"):
        pcs.add(panic["abort_call_site_pc"])
    if not pcs:
        return {"status": "no_addresses", "addresses": []}
    try:
        if artifact.stat().st_size > SYMBOL_FILE_LIMIT:
            return {"status": "unavailable", "reason": "elf_symbol_file_too_large", "addresses": []}
        symbols = parse_elf32_symbols(artifact)
    except (OSError, ElfSymbolError):
        return {"status": "unavailable", "reason": "unsupported_or_unreadable_xtensa_symbols", "addresses": []}

    lookup = sorted(int(pc, 16) for pc in pcs)
    matches: dict[int, set[tuple[str, int]]] = {pc: set() for pc in lookup}
    for named_symbols in symbols.values():
        for symbol in named_symbols:
            if symbol.type != "function":
                continue
            start = bisect_left(lookup, symbol.value)
            end = bisect_left(lookup, symbol.value + max(1, symbol.size))
            for pc in lookup[start:end]:
                matches[pc].add((symbol.name[:240], pc - symbol.value))

    resolved = []
    for pc, candidates in matches.items():
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
    return {
        "status": status,
        "source": "matched_xtensa_elf_function_ranges",
        "addresses": resolved,
    }
