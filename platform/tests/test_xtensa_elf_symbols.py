#!/usr/bin/env python3
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from xtensa_elf_symbols import (  # noqa: E402
    CORE2_NATIVE_HCI_SYMBOLS,
    ELF_HEADER,
    SECTION_HEADER,
    SYMBOL_ENTRY,
    ElfSymbolError,
    core2_native_hci_device_args,
    parse_elf32_symbols,
    resolve_symbols,
)


def build_elf(symbols: list[tuple[str, int, int, int, int]]) -> bytes:
    strings = bytearray(b"\0")
    offsets = {}
    for name, *_rest in symbols:
        offsets[name] = len(strings)
        strings.extend(name.encode() + b"\0")
    section_names = bytearray(b"\0")
    section_offsets = {}
    for name in (".symtab", ".strtab", ".shstrtab"):
        section_offsets[name] = len(section_names)
        section_names.extend(name.encode() + b"\0")

    symtab = bytearray(SYMBOL_ENTRY.size)
    for name, value, size, info, section_index in symbols:
        symtab.extend(
            SYMBOL_ENTRY.pack(
                offsets[name],
                value,
                size,
                info,
                0,
                section_index,
            )
        )
    symtab_offset = 0x100
    strings_offset = symtab_offset + len(symtab)
    names_offset = strings_offset + len(strings)
    section_offset = names_offset + len(section_names)
    image = bytearray(section_offset + 4 * SECTION_HEADER.size)
    image[symtab_offset:symtab_offset + len(symtab)] = symtab
    image[strings_offset:strings_offset + len(strings)] = strings
    image[names_offset:names_offset + len(section_names)] = section_names

    header = ELF_HEADER.pack(
        b"\x7fELF" + bytes([1, 1, 1]) + bytes(9),
        2,
        94,
        1,
        0x40000000,
        0,
        section_offset,
        0,
        ELF_HEADER.size,
        0,
        0,
        SECTION_HEADER.size,
        4,
        3,
    )
    image[:len(header)] = header
    rows = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (
            section_offsets[".symtab"],
            2,
            0,
            0,
            symtab_offset,
            len(symtab),
            2,
            1,
            4,
            SYMBOL_ENTRY.size,
        ),
        (
            section_offsets[".strtab"],
            3,
            0,
            0,
            strings_offset,
            len(strings),
            0,
            0,
            1,
            0,
        ),
        (
            section_offsets[".shstrtab"],
            3,
            0,
            0,
            names_offset,
            len(section_names),
            0,
            0,
            1,
            0,
        ),
    ]
    for index, row in enumerate(rows):
        start = section_offset + index * SECTION_HEADER.size
        image[start:start + SECTION_HEADER.size] = SECTION_HEADER.pack(*row)
    return bytes(image)


def corrupt_section_field(
    image: bytes,
    section_index: int,
    field_index: int,
    value: int,
) -> bytes:
    header = ELF_HEADER.unpack_from(image)
    section_offset = header[6]
    section_size = header[11]
    target = (
        section_offset
        + section_index * section_size
        + field_index * 4
    )
    result = bytearray(image)
    struct.pack_into("<I", result, target, value)
    return bytes(result)


class XtensaElfSymbolTests(unittest.TestCase):
    def test_resolves_global_function_and_object_addresses(self):
        symbol_rows = [
            ("API_vhci_host_send_packet", 0x403064D8, 0x40, 0x12, 1),
            ("vhci_env_p", 0x3FFCC0A4, 4, 0x11, 1),
        ]
        symbol_rows.extend(
            (
                name,
                0x40010000 + index * 0x20,
                0x100,
                0x12,
                1,
            )
            for index, name in enumerate(CORE2_NATIVE_HCI_SYMBOLS)
            if name not in {"vhci_env_p"}
        )
        image = build_elf(symbol_rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware.elf"
            path.write_bytes(image)
            symbols = resolve_symbols(
                path,
                ["API_vhci_host_send_packet", "vhci_env_p"],
            )
            device_args = core2_native_hci_device_args(path)
        self.assertEqual(symbols["API_vhci_host_send_packet"].value, 0x403064D8)
        self.assertEqual(symbols["API_vhci_host_send_packet"].type, "function")
        self.assertEqual(symbols["vhci_env_p"].value, 0x3FFCC0A4)
        self.assertEqual(symbols["vhci_env_p"].type, "object")
        self.assertTrue(device_args.startswith("esp32-native-hci,"))
        self.assertIn("hli-c2h=on", device_args)
        self.assertIn("trace-l2cap-rx-pc=", device_args)

    def test_rejects_missing_and_ambiguous_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ambiguous.elf"
            path.write_bytes(
                build_elf(
                    [
                        ("duplicate", 0x40000000, 4, 0x12, 1),
                        ("duplicate", 0x40000010, 4, 0x12, 1),
                    ]
                )
            )
            with self.assertRaisesRegex(ElfSymbolError, "ambiguous"):
                resolve_symbols(path, ["duplicate"])
            with self.assertRaisesRegex(ElfSymbolError, "missing"):
                resolve_symbols(path, ["absent"])
            parsed = parse_elf32_symbols(path)
        self.assertEqual(len(parsed["duplicate"]), 2)

    def test_rejects_section_span_beyond_file_size(self):
        image = build_elf(
            [("bounded", 0x40000000, 4, 0x12, 1)]
        )
        malformed = corrupt_section_field(
            image,
            section_index=1,
            field_index=5,
            value=(
                (len(image) // SYMBOL_ENTRY.size) + 2
            ) * SYMBOL_ENTRY.size,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oversized.elf"
            path.write_bytes(malformed)
            with self.assertRaisesRegex(
                ElfSymbolError,
                "exceeds file size",
            ):
                parse_elf32_symbols(path)

    def test_hci_ack_diagnostics_require_packet_trace_opt_in(self):
        symbol_rows = [
            (
                name,
                0x40010000 + index * 0x20,
                0x100,
                0x12,
                1,
            )
            for index, name in enumerate(CORE2_NATIVE_HCI_SYMBOLS)
        ]
        image = build_elf(symbol_rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware.elf"
            path.write_bytes(image)
            with patch.dict(os.environ, {}, clear=True):
                default_args = core2_native_hci_device_args(path)
            with patch.dict(
                os.environ,
                {"M5_CORE2_HCI_PACKET_TRACE": "1"},
                clear=True,
            ):
                traced_args = core2_native_hci_device_args(path)

        self.assertNotIn("trace-hci-rx-evt-pc=", default_args)
        self.assertNotIn("ble-hs-hci-ctx-address=", default_args)
        self.assertIn("trace-hci-rx-evt-pc=0x", traced_args)
        self.assertIn("trace-hci-rx-ack-check-pc=0x", traced_args)
        self.assertIn("ble-hs-hci-ctx-address=0x", traced_args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
