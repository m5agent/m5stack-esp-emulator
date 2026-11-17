"""Read FreeRTOS task fields from captured TCBs and a matching ESP-IDF ELF."""

from __future__ import annotations

import re
import struct
from itertools import islice
from pathlib import Path

from esp32_uart_coredump import core_loads
from xtensa_elf_symbols import EM_XTENSA

MAX_DEBUG_ELF_BYTES = 8 * 1024 * 1024
MAX_CAPTURED_STACK_BYTES = 1024 * 1024
RAW_FIELDS = (b"pxTopOfStack", b"uxPriority", b"uxBasePriority",
              b"pxStack", b"pxEndOfStack", b"pcTaskName")
CONSTANT_FORMS = {"DW_FORM_data1", "DW_FORM_data2", "DW_FORM_data4", "DW_FORM_udata"}
KERNEL_TCB = b"tskTaskControlBlock"
KERNEL_SOURCE = b"/freertos/FreeRTOS-Kernel/tasks.c"


def _constant(die, name: str, *, default: int | None = None) -> int:
    value = die.attributes.get(name)
    if value is None and default is not None:
        return default
    if value is None or value.form not in CONSTANT_FORMS or type(value.value) is not int:
        raise ValueError("dynamic or missing DWARF attribute")
    return value.value


def _type_of(die):
    ref = die.attributes.get("DW_AT_type")
    if ref is None or ref.form != "DW_FORM_ref4" or not 0 < ref.value < die.cu.size:
        raise ValueError("expected a type in the same compilation unit")
    resolved = die.get_DIE_from_attribute("DW_AT_type")
    for _ in range(8):
        if resolved.tag not in {"DW_TAG_typedef", "DW_TAG_volatile_type", "DW_TAG_const_type"}:
            return resolved
        ref = resolved.attributes.get("DW_AT_type")
        if ref is None or ref.form != "DW_FORM_ref4" or not 0 < ref.value < die.cu.size:
            break
        resolved = resolved.get_DIE_from_attribute("DW_AT_type")
    raise ValueError("unsupported or cyclic FreeRTOS type alias")


def _name_width(die) -> int:
    if die.tag != "DW_TAG_array_type":
        raise ValueError("task name is not a fixed character array")
    char_type = _type_of(die)
    bounds = list(islice(die.iter_children(), 2))
    if (char_type.tag != "DW_TAG_base_type" or _constant(char_type, "DW_AT_byte_size") != 1
            or _constant(char_type, "DW_AT_encoding") not in {6, 8}
            or len(bounds) != 1 or bounds[0].tag != "DW_TAG_subrange_type"
            or _constant(bounds[0], "DW_AT_lower_bound", default=0) != 0):
        raise ValueError("unsupported task name array elements or bounds")
    width = _constant(bounds[0], "DW_AT_upper_bound") + 1
    if not 2 <= width <= 64:
        raise ValueError("unsupported task name array size")
    return width


def _read_layout(path: Path, elf_reader) -> tuple[int, dict[bytes, tuple[int, int]]]:
    with path.open("rb") as stream:
        file_size = stream.seek(0, 2)
        if not 0 < file_size <= MAX_DEBUG_ELF_BYTES:
            raise ValueError("application debug ELF exceeds its size limit")
        stream.seek(0)
        elf = elf_reader(stream)
        if (elf.elfclass != 32 or not elf.little_endian or elf["e_machine"] != "EM_XTENSA"
                or elf["e_type"] != "ET_EXEC" or elf.num_sections() > 256):
            raise ValueError("expected an executable ESP32 Xtensa ELF32")
        seen = set()
        extents = []
        for section in elf.iter_sections():
            name = section.name
            if name.startswith((".debug_", ".zdebug_", ".eh_frame")):
                start = section["sh_offset"]
                end = start + section["sh_size"]
                if (name in seen or name.startswith(".zdebug_") or section["sh_flags"] & 0x800
                        or section["sh_type"] != "SHT_PROGBITS" or not 0 <= start <= end <= file_size):
                    raise ValueError("ambiguous, compressed or truncated debug section")
                if end > start:
                    extents.append((start, end))
                seen.add(name)
        extents.sort()
        if any(left[1] > right[0] for left, right in zip(extents, extents[1:])):
            raise ValueError("overlapping ELF debug sections")
        if not {".debug_info", ".debug_abbrev"} <= seen:
            raise ValueError("application ELF lacks DWARF debug information")
        dwarf = elf.get_dwarf_info(relocate_dwarf_sections=False, follow_links=False)
        kernel_units = []
        for index, unit in enumerate(dwarf.iter_CUs()):
            if index >= 1024:
                raise ValueError("too many DWARF compilation units")
            unit_name = unit.get_top_DIE().attributes.get("DW_AT_name")
            if unit_name and unit_name.value.replace(b"\\", b"/").endswith(KERNEL_SOURCE):
                kernel_units.append(unit)
        if len(kernel_units) != 1:
            raise ValueError("FreeRTOS kernel compilation unit is missing or ambiguous")
        unit = kernel_units[0]
        if unit["version"] != 4 or unit["address_size"] != 4 or unit.size > 256 * 1024:
            raise ValueError("unsupported FreeRTOS DWARF compilation unit")
        types = []
        for index, die in enumerate(unit.iter_DIEs()):
            if index >= 10000:
                raise ValueError("too many FreeRTOS debug entries")
            name = die.attributes.get("DW_AT_name")
            if (die.tag == "DW_TAG_structure_type" and name and name.value == KERNEL_TCB
                    and "DW_AT_byte_size" in die.attributes):
                types.append(die)
        if len(types) != 1:
            raise ValueError("FreeRTOS task structure is missing or ambiguous")
        structure = types[0]
        size = _constant(structure, "DW_AT_byte_size")
        members = list(islice(structure.iter_children(), 129))
        if not 0 < size <= 1024 or len(members) > 128:
            raise ValueError("invalid FreeRTOS task structure size")
        fields = {}
        used = set()
        for member in members:
            name = member.attributes.get("DW_AT_name")
            if member.tag != "DW_TAG_member" or not name or name.value not in RAW_FIELDS:
                continue
            field = name.value
            offset = _constant(member, "DW_AT_data_member_location")
            datatype = _type_of(member)
            if field == b"pcTaskName":
                width = _name_width(datatype)
            else:
                width = _constant(datatype, "DW_AT_byte_size")
                type_ok = (datatype.tag == "DW_TAG_pointer_type" if field.startswith(b"px") else
                           datatype.tag == "DW_TAG_base_type" and _constant(datatype, "DW_AT_encoding") == 7)
                if width != 4 or offset % 4 or not type_ok:
                    raise ValueError("invalid FreeRTOS pointer or priority type")
            extent = set(range(offset, offset + width))
            if field in fields or used & extent or not 0 <= offset < offset + width <= size:
                raise ValueError("invalid or overlapping FreeRTOS task fields")
            used.update(extent)
            fields[field] = (offset, width)
        if fields.keys() != set(RAW_FIELDS):
            raise ValueError("FreeRTOS task fields are incomplete")
        return size, fields


def _task_fields(data: memoryview, fields: dict, *, captured_context: bool) -> dict:
    offset, width = fields[b"pcTaskName"]
    name, end, _ = bytes(data[offset:offset + width]).partition(b"\0")
    if not end or not re.fullmatch(rb"[ -~]{1,63}", name):
        raise ValueError("invalid TCB task name")

    def uint(field: bytes) -> int:
        return struct.unpack_from("<I", data, fields[field][0])[0]

    priority = uint(b"uxPriority")
    base_priority = uint(b"uxBasePriority")
    if not 0 <= base_priority <= priority <= 255:
        raise ValueError("invalid TCB priorities")
    result = {"name": name.decode("ascii"), "priority": priority, "base_priority": base_priority}
    low, saved, high = (uint(key) for key in (b"pxStack", b"pxTopOfStack", b"pxEndOfStack"))
    if captured_context and 0 < low <= saved <= high and 0 < high - low <= MAX_CAPTURED_STACK_BYTES:
        result["stack"] = {
            "source": "tcb_saved_stack_bounds", "used_bytes": high - saved, "free_bytes": saved - low,
        }
    return result


def annotate_xtensa_tasks(decoded: dict, checked_core: bytes, artifact: Path) -> None:
    """Add metadata only from unique task memory and the checked application ELF."""
    try:
        from elftools.elf.elffile import ELFFile
    except ImportError:
        decoded["task_metadata"] = {"status": "unavailable", "reason": "pyelftools_unavailable"}
        return
    try:
        size, fields = _read_layout(artifact, ELFFile)
        loads = list(core_loads(checked_core, machine=EM_XTENSA))
    except Exception:
        # Malformed optional debug data must not erase the observed PC/SP receipt.
        decoded["task_metadata"] = {"status": "unavailable", "reason": "unsupported_or_invalid_task_layout"}
        return

    complete, recovered = 0, 0
    for task in decoded["tasks"]:
        address = int(task["tcb"], 16)
        overlapping = [(base, length, data) for base, length, data in loads
                       if base < address + size and address < base + length]
        if len(overlapping) != 1:
            continue
        base, length, data = overlapping[0]
        if (base, length, len(data)) != (address, size, size):
            continue
        try:
            details = _task_fields(data, fields, captured_context=task["context_status"] == "captured")
        except ValueError:
            continue
        task["metadata"] = details
        recovered += 1
        complete += "stack" in details
    if not recovered:
        decoded["task_metadata"] = {"status": "unavailable", "reason": "task_memory_unavailable"}
        return
    decoded["task_metadata"] = {
        "status": "decoded" if complete == len(decoded["tasks"]) else "partial",
        "source": "matched_elf_dwarf_and_core_dump_tcb",
        "complete_tasks": complete,
    }
