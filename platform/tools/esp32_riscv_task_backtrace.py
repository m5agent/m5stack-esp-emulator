"""Bounded RV32 ILP32 saved-thread backtraces from ESP-IDF UART dumps."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
import struct

from esp32_uart_coredump import ESP32C6_CHIP_ID, PRSTATUS, TASK_LAYOUTS, core_loads, core_notes
from xtensa_elf_symbols import EF_RISCV_RVC, EM_RISCV

MAX_ELF_BYTES = 8 * 1024 * 1024
MAX_DEBUG_FRAME_BYTES = 256 * 1024
MAX_CFI_ENTRIES = 4096
MAX_STACK_BYTES = 64 * 1024
MAX_FRAMES = 16
RA, SP = 1, 2
ADDRESS_LIMIT = 1 << 32
SOURCE = "matched_rv32_debug_frame"


def _receipt(status: str, reason: str, frames: list[dict[str, str]]) -> dict:
    return {"status": status, "source": SOURCE, "stop_reason": reason, "frames": frames}


def _debug_frame_ranges(path: Path, elf_reader) -> list[tuple[int, int, object]]:
    from elftools.dwarf.callframe import CallFrameInfo, FDE
    from elftools.dwarf.structs import DWARFStructs

    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        if not 0 < size <= MAX_ELF_BYTES:
            raise ValueError("application ELF exceeds its bound")
        stream.seek(0)
        elf = elf_reader(stream)
        if (elf.elfclass != 32 or not elf.little_endian or elf["e_type"] != "ET_EXEC"
                or elf["e_machine"] != "EM_RISCV" or elf["e_flags"] & ~EF_RISCV_RVC
                or elf.num_sections() > 256 or elf.num_segments() > 128):
            raise ValueError("unsupported RV32 application ELF")
        sections = [section for section in elf.iter_sections() if section.name == ".debug_frame"]
        if len(sections) != 1:
            raise ValueError("expected one .debug_frame section")
        section = sections[0]
        offset, length = section["sh_offset"], section["sh_size"]
        if (section["sh_type"] != "SHT_PROGBITS" or section["sh_flags"] & 0x800
                or not 0 < length <= MAX_DEBUG_FRAME_BYTES or not 0 < offset <= size - length
                or section["sh_addr"] != 0):
            raise ValueError("invalid or unsupported .debug_frame section")
        code = [(p["p_vaddr"], p["p_vaddr"] + p["p_filesz"]) for p in elf.iter_segments()
                if p["p_type"] == "PT_LOAD" and p["p_flags"] & 1
                and p["p_vaddr"] + p["p_filesz"] <= ADDRESS_LIMIT]
        contents = section.data()
        if len(contents) != length:
            raise ValueError("truncated .debug_frame section")

    structs = DWARFStructs(little_endian=True, dwarf_format=32, address_size=4)
    entries = CallFrameInfo(BytesIO(contents), length, 0, structs).get_entries()
    if len(entries) > MAX_CFI_ENTRIES:
        raise ValueError("too many CFI entries")
    ranges = []
    for entry in entries:
        if not isinstance(entry, FDE):
            continue
        start = entry["initial_location"]
        end = start + entry["address_range"]
        if any(low <= start < end <= high for low, high in code):
            ranges.append((start, end, entry))
    return ranges


def _rule_at(ranges: list[tuple[int, int, object]], pc: int) -> dict | None:
    matches = [(start, end, entry) for start, end, entry in ranges if start <= pc < end]
    if len(matches) != 1:
        return None
    start, end, entry = matches[0]
    if (entry.cie["version"] != 3 or entry.cie["augmentation"] or
            entry.cie["return_address_register"] != RA or len(entry.instructions) > 256
            or len(entry.cie.instructions) > 64):
        return None
    rows = entry.get_decoded().table
    addresses = [row["pc"] for row in rows]
    if not addresses or addresses != sorted(set(addresses)) or addresses[0] < start or addresses[-1] > end:
        return None
    return next((row for row in reversed(rows) if row["pc"] <= pc), None)


def _saved_backtrace(
    pc: int, sp: int, saved_ra: int, stack_address: int, stack: memoryview,
    lookup: Callable[[int], dict | None],
) -> dict:
    """Follow only saved RA and SP-relative CFI within a task's own stack segment."""
    frames = []
    stack_end = stack_address + len(stack)
    for depth in range(MAX_FRAMES):
        frames.append({"pc": f"0x{pc:08x}", "sp": f"0x{sp:08x}"})
        row = lookup(pc if depth == 0 else pc - 1)
        if row is None:
            return _receipt("partial", "missing_or_ambiguous_cfi", frames)
        cfa_rule = row.get("cfa")
        if (cfa_rule is None or cfa_rule.reg != SP or cfa_rule.expr is not None
                or type(cfa_rule.offset) is not int or not 0 <= cfa_rule.offset <= MAX_STACK_BYTES
                or cfa_rule.offset % 4):
            return _receipt("partial", "unsupported_cfi", frames)
        cfa = sp + cfa_rule.offset
        if not stack_address <= sp <= cfa <= stack_end:
            return _receipt("partial", "stack_not_captured", frames)
        rule = row.get(RA)
        if rule is not None and rule.type == "UNDEFINED":
            return _receipt("complete", "return_address_undefined", frames)
        if depth == 0 and cfa == sp and (rule is None or rule.type == "SAME_VALUE"):
            caller = saved_ra
        elif rule is not None and rule.type == "OFFSET" and type(rule.arg) is int:
            pointer = cfa + rule.arg
            if not sp <= pointer <= cfa - 4 or pointer % 4:
                return _receipt("partial", "stack_not_captured", frames)
            caller, = struct.unpack_from("<I", stack, pointer - stack_address)
        else:
            return _receipt("partial", "unsupported_cfi", frames)
        if not caller or caller % 2 or (caller == pc and cfa == sp):
            return _receipt("partial", "invalid_return_address", frames)
        if lookup(caller - 1) is None:
            return _receipt("partial", "missing_or_ambiguous_cfi", frames)
        pc, sp = caller, cfa
    return _receipt("partial", "frame_limit", frames)


def _captured_stack(
    loads: list[tuple[int, int, memoryview]], tcb: int, tcb_size: int, sp: int,
) -> tuple[int, memoryview] | None:
    # ESP-IDF writes each task's TCB and stack consecutively as PT_LOAD segments.
    tcb_indices = [index for index, (addr, _, _) in enumerate(loads) if addr == tcb]
    if len(tcb_indices) != 1 or tcb_indices[0] + 1 >= len(loads):
        return None
    _, tcb_span, tcb_data = loads[tcb_indices[0]]
    if tcb_span != tcb_size or len(tcb_data) != tcb_size:
        return None
    stack_index = tcb_indices[0] + 1
    address, span, stack = loads[stack_index]
    end = address + len(stack)
    if not 0 < len(stack) == span <= MAX_STACK_BYTES or not address <= sp < end:
        return None
    if any(
        index != stack_index and other < end and sp < other + size
        for index, (other, size, _) in enumerate(loads)
    ):
        return None
    return address, stack


def annotate_riscv_backtraces(
    decoded: dict, checked_core: bytes, artifact: Path, elf_reader, *, tcb_size: int,
) -> None:
    """Annotate selected saved contexts using a validated, matched RV32 artifact."""
    tasks = [task for task in decoded["tasks"] if task["context_status"] == "captured"]
    try:
        ranges = _debug_frame_ranges(artifact, elf_reader)
        loads = list(core_loads(checked_core, machine=EM_RISCV))
        registers = {
            struct.unpack_from("<I", payload, 24)[0]: struct.unpack_from("<3I", payload, 72)
            for kind, payload in core_notes(checked_core, machine=EM_RISCV)
            if kind == PRSTATUS and len(payload) == TASK_LAYOUTS[ESP32C6_CHIP_ID].prstatus_bytes
        }
    except Exception:
        for task in tasks:
            task["saved_backtrace"] = _receipt("unavailable", "invalid_debug_frame", [])
        return
    for task in tasks:
        pc_from_context = int(task["pc"], 16)
        sp_from_context = int(task["sp"], 16)
        tcb = int(task["tcb"], 16)
        regs = registers.get(tcb)
        if (regs is None or regs[::2] != (pc_from_context, sp_from_context)
                or not pc_from_context or pc_from_context % 2 or sp_from_context % 4):
            task["saved_backtrace"] = _receipt("unavailable", "invalid_saved_registers", [])
            continue
        captured = _captured_stack(loads, tcb, tcb_size, sp_from_context)
        if captured is None:
            task["saved_backtrace"] = _receipt("partial", "stack_not_captured", [
                {"pc": task["pc"], "sp": task["sp"]},
            ])
            continue
        pc, ra, sp = regs
        address, stack = captured
        try:
            task["saved_backtrace"] = _saved_backtrace(
                pc, sp, ra, address, stack, lambda caller: _rule_at(ranges, caller),
            )
        except Exception:
            task["saved_backtrace"] = _receipt("partial", "unsupported_cfi", [
                {"pc": task["pc"], "sp": task["sp"]},
            ])
