#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from firmware_analysis import analyze_firmware, analyze_esp_image, parse_partition_table


def build_image(chip_id: int = 0x0009, descriptor: bool = True) -> bytes:
    segment = bytearray()
    if descriptor:
        desc = bytearray(256)
        struct.pack_into("<I", desc, 0, 0xABCD5432)
        desc[16:24] = b"1.2.3\x00\x00\x00"
        desc[48:56] = b"probe\x00\x00\x00"
        desc[112:120] = b"v5.5.4\x00\x00"
        segment.extend(desc)
    segment.extend(b"\x00" * 16)
    header = bytearray(24)
    header[0] = 0xE9
    header[1] = 1
    struct.pack_into("<I", header, 4, 0x40380000)
    struct.pack_into("<H", header, 12, chip_id)
    return bytes(header) + struct.pack("<II", 0x3FC00000, len(segment)) + bytes(segment)


def build_flash() -> bytes:
    image = bytearray(b"\xff" * 0x12000)
    boot = build_image(descriptor=False)
    image[:len(boot)] = boot
    app = build_image()
    image[0x10000:0x10000 + len(app)] = app
    entry = bytearray(32)
    struct.pack_into("<H", entry, 0, 0x50AA)
    entry[2] = 0
    entry[3] = 0
    struct.pack_into("<II", entry, 4, 0x10000, 0x2000)
    entry[12:19] = b"factory"
    md5_entry = bytearray(32)
    struct.pack_into("<H", md5_entry, 0, 0xEBEB)
    md5_entry[16:32] = hashlib.md5(entry).digest()
    image[0x8000:0x8020] = entry
    image[0x8020:0x8040] = md5_entry
    return bytes(image)


class FirmwareAnalysisTests(unittest.TestCase):
    def test_parses_partition_table_and_app_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware.bin"
            path.write_bytes(build_flash())
            result = analyze_firmware(path, expected_chip_id_value=0x0009)
        self.assertTrue(result["valid"], result["errors"])
        self.assertTrue(result["partition_table"]["valid"])
        self.assertEqual(result["partition_table"]["partitions"][0]["label"], "factory")
        self.assertEqual(result["app_descriptor"]["version"], "1.2.3")
        self.assertEqual(result["app_descriptor"]["project_name"], "probe")

    def test_detects_chip_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware.bin"
            path.write_bytes(build_flash())
            result = analyze_firmware(path, expected_chip_id_value=0x000D)
        self.assertFalse(result["valid"])
        self.assertTrue(any("does not match expected" in item for item in result["errors"]))

    def test_truncated_segment_is_rejected(self):
        image = build_image()
        result = analyze_esp_image(image[:-4])
        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_missing_partition_table_is_reported(self):
        result = parse_partition_table(build_image() + b"\xff" * 0x9000)
        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
