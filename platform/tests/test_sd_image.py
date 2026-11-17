#!/usr/bin/env python3

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from firmware_filesystems import inventory_sd_filesystems
from sd_image import (
    BYTES_PER_SECTOR,
    FAT_COUNT,
    MBR_PARTITION_START,
    ROOT_DIR_SECTORS,
    create_fat16_image,
    create_fat32_mbr_image,
)


class SdImageTests(unittest.TestCase):
    def test_fat16_image_has_boot_signature_and_duplicate_fats(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fixture.img"
            result = create_fat16_image(
                output,
                size_mib=16,
                label="M5TEST",
            )

            data = output.read_bytes()
            self.assertEqual(result["bytes"], 16 << 20)
            self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(data[0:3], b"\xeb\x3c\x90")
            self.assertEqual(struct.unpack_from("<H", data, 11)[0], BYTES_PER_SECTOR)
            self.assertEqual(data[13], 4)
            self.assertEqual(data[16], FAT_COUNT)
            self.assertEqual(struct.unpack_from("<H", data, 17)[0], 512)
            self.assertEqual(data[21], 0xF8)
            self.assertEqual(data[38], 0x29)
            self.assertEqual(data[43:54], b"M5TEST     ")
            self.assertEqual(data[54:62], b"FAT16   ")
            self.assertEqual(data[510:512], b"\x55\xaa")

            fat_sectors = struct.unpack_from("<H", data, 22)[0]
            first_fat = BYTES_PER_SECTOR
            second_fat = first_fat + fat_sectors * BYTES_PER_SECTOR
            self.assertEqual(
                data[first_fat:first_fat + 4],
                struct.pack("<HH", 0xFFF8, 0xFFFF),
            )
            self.assertEqual(
                data[first_fat:first_fat + fat_sectors * BYTES_PER_SECTOR],
                data[second_fat:second_fat + fat_sectors * BYTES_PER_SECTOR],
            )

            root_start = (
                first_fat
                + FAT_COUNT * fat_sectors * BYTES_PER_SECTOR
            )
            self.assertEqual(
                data[root_start + ROOT_DIR_SECTORS * BYTES_PER_SECTOR - 32:
                     root_start + ROOT_DIR_SECTORS * BYTES_PER_SECTOR],
                b"\x00" * 32,
            )
            self.assertEqual(data[root_start:root_start + 11], b"M5TEST     ")
            self.assertEqual(data[root_start + 11], 0x08)
            inventory = inventory_sd_filesystems(data)
            self.assertEqual(inventory["layout"], "superfloppy")
            self.assertEqual(inventory["filesystems"][0]["fat_type"], "fat16")
            dated = bytearray(32)
            dated[:11] = b"DATED   TXT"
            dated[11] = 0x20  # archive
            struct.pack_into("<H", dated, 18, (46 << 9) | (11 << 5) | 17)
            with output.open("r+b") as disk:
                disk.seek(root_start + 32)
                disk.write(dated)
            files = inventory_sd_filesystems(output.read_bytes())["filesystems"][0]["files"]
            self.assertEqual([row["path"] for row in files], ["/DATED.TXT"])

    def test_fat16_image_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fixture.img"
            with self.assertRaisesRegex(ValueError, "size_mib"):
                create_fat16_image(output, size_mib=8)
            with self.assertRaisesRegex(ValueError, "label"):
                create_fat16_image(output, label="BAD LABEL")

    def test_fat32_mbr_image_has_partition_boot_and_duplicate_fats(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fixture.img"
            result = create_fat32_mbr_image(
                output,
                size_mib=64,
                label="M5FAT32",
            )

            data = output.read_bytes()
            self.assertEqual(data[510:512], b"\x55\xaa")
            self.assertEqual(data[446 + 4], 0x0C)
            self.assertEqual(
                struct.unpack_from("<II", data, 446 + 8),
                (MBR_PARTITION_START, result["partition_sectors"]),
            )

            partition_offset = MBR_PARTITION_START * BYTES_PER_SECTOR
            boot = data[partition_offset:partition_offset + BYTES_PER_SECTOR]
            self.assertEqual(boot[0:3], b"\xeb\x58\x90")
            self.assertEqual(struct.unpack_from("<H", boot, 11)[0], BYTES_PER_SECTOR)
            self.assertEqual(struct.unpack_from("<H", boot, 14)[0], 32)
            self.assertEqual(struct.unpack_from("<I", boot, 28)[0], MBR_PARTITION_START)
            self.assertEqual(boot[82:90], b"FAT32   ")
            self.assertEqual(boot[510:512], b"\x55\xaa")
            self.assertEqual(
                data[
                    partition_offset + 6 * BYTES_PER_SECTOR:
                    partition_offset + 7 * BYTES_PER_SECTOR
                ],
                boot,
            )

            info_offset = partition_offset + BYTES_PER_SECTOR
            self.assertEqual(
                struct.unpack_from("<I", data, info_offset)[0],
                0x41615252,
            )
            self.assertEqual(
                struct.unpack_from("<I", data, info_offset + 484)[0],
                0x61417272,
            )

            fat_sectors = struct.unpack_from("<I", boot, 36)[0]
            first_fat = partition_offset + 32 * BYTES_PER_SECTOR
            second_fat = first_fat + fat_sectors * BYTES_PER_SECTOR
            self.assertEqual(
                data[first_fat:first_fat + 12],
                struct.pack("<III", 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF),
            )
            self.assertEqual(
                data[first_fat:first_fat + fat_sectors * BYTES_PER_SECTOR],
                data[second_fat:second_fat + fat_sectors * BYTES_PER_SECTOR],
            )

            inventory = inventory_sd_filesystems(data)
            self.assertEqual(inventory["layout"], "mbr")
            volume, = inventory["filesystems"]
            self.assertEqual((volume["fat_type"], volume["offset"]), ("fat32", partition_offset))
            corrupt_mbr = bytearray(data[:512])
            struct.pack_into("<I", corrupt_mbr, 446 + 8, 0xFFFFFFFF)
            rejected = inventory_sd_filesystems(bytes(corrupt_mbr))
            self.assertEqual(rejected["filesystems"], [])
            self.assertTrue(rejected["errors"])

    def test_fat32_mbr_image_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fixture.img"
            with self.assertRaisesRegex(ValueError, "size_mib"):
                create_fat32_mbr_image(output, size_mib=32)
            with self.assertRaisesRegex(ValueError, "valid FAT32 cluster count"):
                create_fat32_mbr_image(output, size_mib=64, sectors_per_cluster=2)
            self.assertFalse(output.exists())

    def test_fat32_geometry_accounts_for_fat_sectors_at_cluster_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fixture.img"
            for size_mib, cluster_width in ((65, 1), (96, 2)):
                with self.subTest(size_mib=size_mib, cluster_width=cluster_width):
                    result = create_fat32_mbr_image(
                        output, size_mib=size_mib, sectors_per_cluster=cluster_width,
                    )
                    data = output.read_bytes()
                    offset = MBR_PARTITION_START * BYTES_PER_SECTOR
                    boot = data[offset:offset + BYTES_PER_SECTOR]
                    volume, = inventory_sd_filesystems(data)["filesystems"]
                    self.assertEqual(volume["fat_type"], "fat32")
                    self.assertEqual(boot[13], cluster_width)
                    fat_sectors = result["fat_sectors"]
                    self.assertGreaterEqual(fat_sectors * BYTES_PER_SECTOR, (result["clusters"] + 2) * 4)
                    self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
