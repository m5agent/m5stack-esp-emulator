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


def build_flash_with_littlefs() -> bytes:
    work_py = ROOT / ".work/py"
    if not work_py.is_dir():
        raise unittest.SkipTest("littlefs-python test runtime is unavailable")
    if str(work_py) not in sys.path:
        sys.path.insert(0, str(work_py))
    try:
        from littlefs import LittleFS, UserContext
    except (ImportError, OSError) as error:
        raise unittest.SkipTest(
            f"littlefs-python is unavailable: {error}"
        ) from error

    context = UserContext(buffsize=0x8000)
    filesystem = LittleFS(
        context=context,
        block_size=4096,
        block_count=8,
    )
    filesystem.makedirs("/res", exist_ok=True)
    filesystem.makedirs("/certs", exist_ok=True)
    with filesystem.open("/main.py", "wb") as handle:
        handle.write(b"print('hello')\n")
    with filesystem.open("/res/LICENSE", "wb") as handle:
        handle.write(b"SPDX-License-Identifier: MIT\n")
    with filesystem.open("/certs/device.key", "wb") as handle:
        handle.write(b"not-a-real-private-key\n")
    filesystem.unmount()

    image = bytearray(b"\xff" * 0x28000)
    boot = build_image(descriptor=False)
    image[: len(boot)] = boot
    app = build_image()
    image[0x10000 : 0x10000 + len(app)] = app
    image[0x20000 : 0x20000 + len(context.buffer)] = bytes(
        context.buffer
    )
    entries = []
    for subtype, offset, size, label in (
        (0, 0x10000, 0x2000, b"factory"),
        (0x83, 0x20000, 0x8000, b"storage"),
    ):
        entry = bytearray(32)
        struct.pack_into("<H", entry, 0, 0x50AA)
        entry[2] = 0 if subtype == 0 else 1
        entry[3] = subtype
        struct.pack_into("<II", entry, 4, offset, size)
        entry[12 : 12 + len(label)] = label
        entries.append(entry)
    payload = b"".join(entries)
    md5_entry = bytearray(32)
    struct.pack_into("<H", md5_entry, 0, 0xEBEB)
    md5_entry[16:32] = hashlib.md5(payload).digest()
    image[0x8000 : 0x8000 + len(payload)] = payload
    image[0x8000 + len(payload) : 0x8020 + len(payload)] = md5_entry
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

    def test_classic_esp32_bootloader_and_sparse_flash_are_supported(self):
        image = bytearray(b"\xff" * 0x12000)
        boot = build_image(chip_id=0x0000, descriptor=False)
        image[0x1000 : 0x1000 + len(boot)] = boot
        app = build_image(chip_id=0x0000)
        image[0x10000 : 0x10000 + len(app)] = app
        entry = bytearray(32)
        struct.pack_into("<H", entry, 0, 0x50AA)
        struct.pack_into("<II", entry, 4, 0x10000, 0x2000)
        entry[12:19] = b"factory"
        md5_entry = bytearray(32)
        struct.pack_into("<H", md5_entry, 0, 0xEBEB)
        md5_entry[16:32] = hashlib.md5(entry).digest()
        image[0x8000:0x8020] = entry
        image[0x8020:0x8040] = md5_entry
        # Declare a 16 MiB classic ESP32 layout while omitting the unused tail.
        entry[4:12] = struct.pack("<II", 0x10000, 0xFE0000)
        md5_entry[16:32] = hashlib.md5(entry).digest()
        image[0x8000:0x8020] = entry
        image[0x8020:0x8040] = md5_entry

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "classic-sparse.bin"
            path.write_bytes(image)
            result = analyze_firmware(path, expected_chip_id_value=0x0000)

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["bootloader"]["offset"], 0x1000)
        self.assertEqual(result["declared_flash_size"], 16 << 20)
        self.assertTrue(result["sparse_source"])

    def test_esp32p4_bootloader_at_0x2000_is_supported(self):
        image = bytearray(b"\xff" * 0x12000)
        boot = build_image(chip_id=0x0012, descriptor=False)
        image[0x2000 : 0x2000 + len(boot)] = boot
        app = build_image(chip_id=0x0012)
        image[0x10000 : 0x10000 + len(app)] = app
        entry = bytearray(32)
        struct.pack_into("<H", entry, 0, 0x50AA)
        struct.pack_into("<II", entry, 4, 0x10000, 0x2000)
        entry[12:19] = b"factory"
        md5_entry = bytearray(32)
        struct.pack_into("<H", md5_entry, 0, 0xEBEB)
        md5_entry[16:32] = hashlib.md5(entry).digest()
        image[0x8000:0x8020] = entry
        image[0x8020:0x8040] = md5_entry

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "esp32p4.bin"
            path.write_bytes(image)
            result = analyze_firmware(path, expected_chip_id_value=0x0012)

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["bootloader"]["offset"], 0x2000)
        self.assertIn(
            "ESP32-P4 bootloader found at 0x2000",
            result["warnings"],
        )

    def test_blank_ota_slot_does_not_invalidate_other_app(self):
        image = bytearray(b"\xff" * 0x22000)
        boot = build_image(chip_id=0x0009, descriptor=False)
        image[: len(boot)] = boot
        app = build_image(chip_id=0x0009)
        image[0x11000 : 0x11000 + len(app)] = app
        entries = []
        for subtype, offset, label in (
            (0x10, 0x10000, b"ota_0"),
            (0x11, 0x11000, b"ota_1"),
        ):
            entry = bytearray(32)
            struct.pack_into("<H", entry, 0, 0x50AA)
            entry[2] = 0
            entry[3] = subtype
            struct.pack_into("<II", entry, 4, offset, 0x8000)
            entry[12 : 12 + len(label)] = label
            entries.append(entry)
        payload = b"".join(entries)
        md5_entry = bytearray(32)
        struct.pack_into("<H", md5_entry, 0, 0xEBEB)
        md5_entry[16:32] = hashlib.md5(payload).digest()
        image[0x8000 : 0x8000 + len(payload)] = payload
        image[0x8000 + len(payload) : 0x8020 + len(payload)] = md5_entry

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank-ota.bin"
            path.write_bytes(image)
            result = analyze_firmware(path, expected_chip_id_value=0x0009)

        self.assertTrue(result["valid"], result["errors"])
        self.assertFalse(result["app_images"][0]["present"])
        self.assertTrue(result["app_images"][1]["valid"])

    def test_littlefs_inventory_hashes_files_and_redacts_sensitive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "littlefs.bin"
            path.write_bytes(build_flash_with_littlefs())
            result = analyze_firmware(path, expected_chip_id_value=0x0009)

        self.assertTrue(result["valid"], result["errors"])
        filesystem = result["filesystems"][0]
        self.assertEqual(filesystem["type"], "littlefs")
        self.assertEqual(filesystem["status"], "PASS")
        self.assertEqual(filesystem["block_size"], 4096)
        self.assertEqual(filesystem["declared_licenses"], ["MIT"])
        self.assertEqual(len(filesystem["sensitive_files"]), 1)
        self.assertEqual(
            filesystem["sensitive_files"][0]["path"],
            "<redacted-sensitive-path>",
        )
        file_paths = {row["path"] for row in filesystem["files"]}
        self.assertIn("/main.py", file_paths)
        self.assertIn("/res/LICENSE", file_paths)
        self.assertIn("<redacted-sensitive-path>", file_paths)


if __name__ == "__main__":
    unittest.main(verbosity=2)
