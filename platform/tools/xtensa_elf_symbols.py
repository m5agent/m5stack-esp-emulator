#!/usr/bin/env python3
"""Read named function/object addresses from a 32-bit little-endian ELF."""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
ELFCLASS32 = 1
ELFDATA2LSB = 1
ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SYMBOL_ENTRY = struct.Struct("<IIIBBH")
SHT_SYMTAB = 2
SHN_XINDEX = 0xFFFF
STB_LOCAL = 0
STB_GLOBAL = 1
STB_WEAK = 2
STT_OBJECT = 1
STT_FUNC = 2
CORE2_NATIVE_VHCI_SYMBOLS = {
    "M5_NATIVE_VHCI_SEND_PC": "API_vhci_host_send_packet",
    "M5_NATIVE_VHCI_ENV_PTR": "vhci_env_p",
    "M5_NATIVE_VHCI_IDLE_PC": "esp_cpu_wait_for_intr",
}


class ElfSymbolError(ValueError):
    """Raised when an ELF symbol table cannot be used safely."""


@dataclass(frozen=True)
class ElfSymbol:
    name: str
    value: int
    size: int
    type: str
    binding: str
    section_index: int


def _read_at(
    source,
    offset: int,
    size: int,
    label: str,
    file_size: int,
) -> bytes:
    if offset > file_size or size > file_size - offset:
        raise ElfSymbolError(
            f"{label} exceeds file size at offset 0x{offset:x}"
        )
    source.seek(offset)
    data = source.read(size)
    if len(data) != size:
        raise ElfSymbolError(f"{label} is truncated at offset 0x{offset:x}")
    return data


def _cstring(table: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(table):
        raise ElfSymbolError(f"string offset 0x{offset:x} is out of range")
    end = table.find(b"\x00", offset)
    if end < 0:
        raise ElfSymbolError(f"string offset 0x{offset:x} is not terminated")
    return table[offset:end].decode("utf-8", errors="replace")


def parse_elf32_symbols(path: Path) -> dict[str, list[ElfSymbol]]:
    with path.open("rb") as source:
        source.seek(0, 2)
        file_size = source.tell()
        header = _read_at(
            source,
            0,
            ELF_HEADER.size,
            "ELF header",
            file_size,
        )
        (
            ident,
            _elf_type,
            machine,
            _version,
            _entry,
            _program_offset,
            section_offset,
            _flags,
            header_size,
            _program_entry_size,
            _program_count,
            section_entry_size,
            section_count,
            section_names_index,
        ) = ELF_HEADER.unpack(header)
        if ident[:4] != ELF_MAGIC:
            raise ElfSymbolError("input is not an ELF file")
        if ident[4] != ELFCLASS32:
            raise ElfSymbolError("only ELF32 inputs are supported")
        if ident[5] != ELFDATA2LSB:
            raise ElfSymbolError("only little-endian ELF inputs are supported")
        if machine != 94:
            raise ElfSymbolError(f"ELF machine {machine} is not Xtensa")
        if header_size != ELF_HEADER.size:
            raise ElfSymbolError(
                f"unsupported ELF header size {header_size}"
            )
        if (
            section_offset == 0
            or section_entry_size < SECTION_HEADER.size
        ):
            raise ElfSymbolError("ELF has no usable section table")

        first_raw = _read_at(
            source,
            section_offset,
            section_entry_size,
            "section zero",
            file_size,
        )
        first = SECTION_HEADER.unpack_from(first_raw)
        if section_count == 0:
            section_count = first[5]
        if section_names_index == SHN_XINDEX:
            section_names_index = first[6]
        if section_count <= 0 or section_count > 65535:
            raise ElfSymbolError(f"invalid section count {section_count}")

        sections = []
        for index in range(section_count):
            raw = _read_at(
                source,
                section_offset + index * section_entry_size,
                section_entry_size,
                f"section header {index}",
                file_size,
            )
            sections.append(SECTION_HEADER.unpack_from(raw))
        if section_names_index >= len(sections):
            raise ElfSymbolError("section-name table index is out of range")
        names_section = sections[section_names_index]
        section_names = _read_at(
            source,
            names_section[4],
            names_section[5],
            "section-name string table",
            file_size,
        )

        symbols: dict[str, list[ElfSymbol]] = {}
        found_symtab = False
        for section in sections:
            if section[1] != SHT_SYMTAB:
                continue
            found_symtab = True
            if section[6] >= len(sections):
                raise ElfSymbolError("symbol string-table index is out of range")
            strings_section = sections[section[6]]
            strings = _read_at(
                source,
                strings_section[4],
                strings_section[5],
                "symbol string table",
                file_size,
            )
            entry_size = section[9] or SYMBOL_ENTRY.size
            if entry_size < SYMBOL_ENTRY.size or section[5] % entry_size:
                raise ElfSymbolError("symbol table entry size is invalid")
            table = _read_at(
                source,
                section[4],
                section[5],
                "symbol table",
                file_size,
            )
            for offset in range(0, len(table), entry_size):
                (
                    name_offset,
                    value,
                    size,
                    info,
                    _other,
                    section_index,
                ) = SYMBOL_ENTRY.unpack_from(table, offset)
                name = _cstring(strings, name_offset)
                symbol_type = info & 0x0F
                binding = info >> 4
                if (
                    not name
                    or symbol_type not in {STT_FUNC, STT_OBJECT}
                    or binding not in {STB_LOCAL, STB_GLOBAL, STB_WEAK}
                    or value == 0
                    or section_index == 0
                ):
                    continue
                symbol = ElfSymbol(
                    name=name,
                    value=value,
                    size=size,
                    type="function" if symbol_type == STT_FUNC else "object",
                    binding=(
                        "local"
                        if binding == STB_LOCAL
                        else "global"
                        if binding == STB_GLOBAL
                        else "weak"
                    ),
                    section_index=section_index,
                )
                symbols.setdefault(name, []).append(symbol)
        if not found_symtab:
            raise ElfSymbolError("ELF has no symbol table")
        return symbols


def resolve_symbols(
    path: Path,
    names: list[str],
) -> dict[str, ElfSymbol]:
    symbols = parse_elf32_symbols(path)
    resolved = {}
    for name in names:
        matches = symbols.get(name, [])
        if not matches:
            raise ElfSymbolError(f"required symbol {name!r} is missing")
        globals_ = [row for row in matches if row.binding == "global"]
        candidates = globals_ or matches
        unique = {
            (row.value, row.size, row.type, row.section_index)
            for row in candidates
        }
        if len(unique) != 1:
            raise ElfSymbolError(
                f"required symbol {name!r} is ambiguous: "
                + ", ".join(
                    f"0x{row.value:08x}/{row.type}" for row in candidates
                )
            )
        resolved[name] = candidates[0]
    return resolved


def core2_native_vhci_addresses(path: Path) -> dict[str, int]:
    symbols = resolve_symbols(
        path,
        list(CORE2_NATIVE_VHCI_SYMBOLS.values()),
    )
    addresses = {
        environment: symbols[name].value
        for environment, name in CORE2_NATIVE_VHCI_SYMBOLS.items()
    }
    return addresses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("elf", type=Path)
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="symbol name that must resolve",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.elf.is_file():
        parser.error(f"ELF does not exist: {args.elf}")
    symbols = resolve_symbols(args.elf, args.require)
    payload = {
        name: asdict(symbol)
        for name, symbol in sorted(symbols.items())
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for name, symbol in payload.items():
            print(
                f"{name:40s} 0x{symbol['value']:08x} "
                f"{symbol['type']} {symbol['binding']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
