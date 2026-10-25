#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / (
    "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-pc-mapping-audit.json"
)
SCRIPT = ROOT / "tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "core2_pc_mapping_audit",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load mapping audit module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Core2PcMappingAuditTests(unittest.TestCase):
    def test_public_bin_rejects_unbound_elf_symbolization(self) -> None:
        evidence = json.loads(AUDIT.read_text())
        self.assertEqual(evidence["classification"], "BIN_ELF_BYTES_MISMATCH")
        self.assertFalse(evidence["all_match"])
        self.assertEqual(
            evidence["image"]["sha256"],
            "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc",
        )
        self.assertEqual(
            evidence["elf"]["sha256"],
            "5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49",
        )
        rows = {
            row["address"]: row for row in evidence["addresses"]
        }
        self.assertEqual(set(rows), {0x400843AC, 0x400843AF, 0x400843B1})
        for address, row in rows.items():
            self.assertEqual(row["app_segment"]["index"], 3, address)
            self.assertFalse(row["matches"], address)
            self.assertNotEqual(
                row["bin_bytes_sha256"],
                row["elf_bytes_sha256"],
                address,
            )

    def test_app_and_elf_extractors_preserve_link_address(self) -> None:
        module = load_module()
        image = bytearray(0x80)
        image[0x20] = module.ESP_IMAGE_MAGIC
        image[0x21] = 1
        image[0x38:0x40] = struct.pack("<II", 0x40080000, 8)
        image[0x40:0x48] = b"ABCDEFGH"
        segments = module.parse_app_segments(image, 0x20)
        segment, payload = module.read_app_bytes(
            bytes(image),
            segments,
            0x40080002,
            4,
        )
        self.assertEqual(segment["index"], 0)
        self.assertEqual(payload, b"CDEF")

        section_offset = module.ELF32_HEADER_SIZE
        data_offset = section_offset + 2 * module.ELF32_SECTION_HEADER_SIZE
        elf = bytearray(data_offset + 8)
        elf[:4] = b"\x7fELF"
        elf[4] = 1
        elf[5] = 1
        struct.pack_into("<I", elf, 32, section_offset)
        struct.pack_into("<H", elf, 46, module.ELF32_SECTION_HEADER_SIZE)
        struct.pack_into("<H", elf, 48, 2)
        section_header = section_offset + module.ELF32_SECTION_HEADER_SIZE
        struct.pack_into("<I", elf, section_header + 12, 0x40080000)
        struct.pack_into("<I", elf, section_header + 16, data_offset)
        struct.pack_into("<I", elf, section_header + 20, 8)
        elf[data_offset : data_offset + 8] = b"ABCDEFGH"
        section, payload = module.read_elf_bytes(
            bytes(elf),
            0x40080002,
            4,
        )
        self.assertEqual(section["index"], 1)
        self.assertEqual(payload, b"CDEF")

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "audit.json"
            result = module.audit(
                image=bytes(image),
                elf=bytes(elf),
                app_offset=0x20,
                addresses=[0x40080002],
                window=4,
            )
            output.write_text(json.dumps(result))
        self.assertTrue(result["all_match"])
        self.assertEqual(result["classification"], "BIN_ELF_BYTES_MATCH")


if __name__ == "__main__":
    unittest.main()
