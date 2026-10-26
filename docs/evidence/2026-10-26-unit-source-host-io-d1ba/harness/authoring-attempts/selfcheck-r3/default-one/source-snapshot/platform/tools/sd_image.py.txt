#!/usr/bin/env python3
"""Create small deterministic FAT16 SD-card images for emulator fixtures."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


BYTES_PER_SECTOR = 512
SECTORS_PER_CLUSTER = 4
FAT32_SECTORS_PER_CLUSTER = 1
RESERVED_SECTORS = 1
FAT_COUNT = 2
ROOT_ENTRIES = 512
ROOT_DIR_SECTORS = ROOT_ENTRIES * 32 // BYTES_PER_SECTOR
MEDIA_DESCRIPTOR = 0xF8
MBR_PARTITION_START = 2048
FAT32_RESERVED_SECTORS = 32


def _fat_size_sectors(total_sectors: int) -> int:
    size = 1
    while True:
        data_sectors = (
            total_sectors
            - RESERVED_SECTORS
            - ROOT_DIR_SECTORS
            - FAT_COUNT * size
        )
        clusters = data_sectors // SECTORS_PER_CLUSTER
        required = ((clusters + 2) * 2 + BYTES_PER_SECTOR - 1) // BYTES_PER_SECTOR
        if required == size:
            if not 4085 <= clusters <= 65524:
                raise ValueError("image size does not produce a valid FAT16 cluster count")
            return size
        size = required


def _fat32_size_sectors(partition_sectors: int) -> int:
    size = 1
    while True:
        data_sectors = (
            partition_sectors
            - FAT32_RESERVED_SECTORS
            - FAT_COUNT * size
        )
        clusters = data_sectors // FAT32_SECTORS_PER_CLUSTER
        required = ((clusters + 2) * 4 + BYTES_PER_SECTOR - 1) // BYTES_PER_SECTOR
        if required == size:
            if clusters < 65525:
                raise ValueError("image size does not produce a valid FAT32 cluster count")
            return size
        size = required


def _volume_id(label: str) -> int:
    return int.from_bytes(hashlib.sha256(label.encode("ascii")).digest()[:4], "little")


def fat16_boot_sector(*, total_sectors: int, fat_sectors: int, label: str) -> bytes:
    boot = bytearray(BYTES_PER_SECTOR)
    boot[0:3] = b"\xeb\x3c\x90"
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", boot, 11, BYTES_PER_SECTOR)
    boot[13] = SECTORS_PER_CLUSTER
    struct.pack_into("<H", boot, 14, RESERVED_SECTORS)
    boot[16] = FAT_COUNT
    struct.pack_into("<H", boot, 17, ROOT_ENTRIES)
    struct.pack_into("<H", boot, 19, total_sectors if total_sectors < 65536 else 0)
    boot[21] = MEDIA_DESCRIPTOR
    struct.pack_into("<H", boot, 22, fat_sectors)
    struct.pack_into("<H", boot, 24, 32)
    struct.pack_into("<H", boot, 26, 64)
    struct.pack_into("<I", boot, 28, 0)
    struct.pack_into("<I", boot, 32, total_sectors if total_sectors >= 65536 else 0)
    boot[36] = 0x80
    boot[38] = 0x29
    struct.pack_into("<I", boot, 39, _volume_id(label))
    boot[43:54] = label.encode("ascii").ljust(11, b" ")[:11]
    boot[54:62] = b"FAT16   "
    boot[510:512] = b"\x55\xaa"
    return bytes(boot)


def fat32_boot_sector(
    *,
    partition_sectors: int,
    fat_sectors: int,
    hidden_sectors: int,
    label: str,
) -> bytes:
    boot = bytearray(BYTES_PER_SECTOR)
    boot[0:3] = b"\xeb\x58\x90"
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", boot, 11, BYTES_PER_SECTOR)
    boot[13] = FAT32_SECTORS_PER_CLUSTER
    struct.pack_into("<H", boot, 14, FAT32_RESERVED_SECTORS)
    boot[16] = FAT_COUNT
    struct.pack_into("<H", boot, 17, 0)
    struct.pack_into("<H", boot, 19, 0)
    boot[21] = MEDIA_DESCRIPTOR
    struct.pack_into("<H", boot, 22, 0)
    struct.pack_into("<H", boot, 24, 32)
    struct.pack_into("<H", boot, 26, 64)
    struct.pack_into("<I", boot, 28, hidden_sectors)
    struct.pack_into("<I", boot, 32, partition_sectors)
    struct.pack_into("<I", boot, 36, fat_sectors)
    struct.pack_into("<H", boot, 40, 0)
    struct.pack_into("<H", boot, 42, 0)
    struct.pack_into("<I", boot, 44, 2)
    struct.pack_into("<H", boot, 48, 1)
    struct.pack_into("<H", boot, 50, 6)
    boot[64] = 0x80
    boot[66] = 0x29
    struct.pack_into("<I", boot, 67, _volume_id(label))
    boot[71:82] = label.encode("ascii").ljust(11, b" ")[:11]
    boot[82:90] = b"FAT32   "
    boot[510:512] = b"\x55\xaa"
    return bytes(boot)


def mbr_sector(*, partition_sectors: int) -> bytes:
    mbr = bytearray(BYTES_PER_SECTOR)
    mbr[0:3] = b"\xfa\x31\xc0"
    start = MBR_PARTITION_START
    entry = 446
    mbr[entry] = 0
    mbr[entry + 1:entry + 4] = b"\xfe\xff\xff"
    mbr[entry + 4] = 0x0C
    mbr[entry + 5:entry + 8] = b"\xfe\xff\xff"
    struct.pack_into("<II", mbr, entry + 8, start, partition_sectors)
    mbr[510:512] = b"\x55\xaa"
    return bytes(mbr)


def fs_info_sector(*, free_clusters: int) -> bytes:
    info = bytearray(BYTES_PER_SECTOR)
    struct.pack_into("<I", info, 0, 0x41615252)
    struct.pack_into("<I", info, 484, 0x61417272)
    struct.pack_into("<I", info, 488, free_clusters)
    struct.pack_into("<I", info, 492, 3)
    struct.pack_into("<I", info, 508, 0xAA550000)
    return bytes(info)


def create_fat16_image(
    path: Path,
    *,
    size_mib: int = 32,
    label: str = "M5FIXTURE",
) -> dict:
    if size_mib < 16 or size_mib > 64:
        raise ValueError("size_mib must be between 16 and 64")
    normalized_label = label.upper()
    if (
        not normalized_label
        or len(normalized_label) > 11
        or any(not (char.isalnum() or char in "_-") for char in normalized_label)
    ):
        raise ValueError("label must be 1-11 ASCII letters, digits, '_' or '-'")

    total_sectors = size_mib * 1024 * 1024 // BYTES_PER_SECTOR
    fat_sectors = _fat_size_sectors(total_sectors)
    boot = fat16_boot_sector(
        total_sectors=total_sectors,
        fat_sectors=fat_sectors,
        label=normalized_label,
    )
    fat_start = RESERVED_SECTORS * BYTES_PER_SECTOR
    second_fat_start = fat_start + fat_sectors * BYTES_PER_SECTOR
    root_start = second_fat_start + fat_sectors * BYTES_PER_SECTOR
    fat_prefix = struct.pack("<HH", 0xFFF8, 0xFFFF)
    volume_entry = bytearray(32)
    volume_entry[0:11] = normalized_label.encode("ascii").ljust(11, b" ")[:11]
    volume_entry[11] = 0x08

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as image:
        image.truncate(total_sectors * BYTES_PER_SECTOR)
        image.seek(0)
        image.write(boot)
        for offset in (fat_start, second_fat_start):
            image.seek(offset)
            image.write(fat_prefix)
        image.seek(root_start)
        image.write(volume_entry)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "filesystem": "FAT16",
        "sector_bytes": BYTES_PER_SECTOR,
        "sectors_per_cluster": SECTORS_PER_CLUSTER,
        "fat_sectors": fat_sectors,
        "label": normalized_label,
    }


def create_fat32_mbr_image(
    path: Path,
    *,
    size_mib: int = 64,
    label: str = "M5FIXTURE",
) -> dict:
    if size_mib < 64 or size_mib > 96:
        raise ValueError("FAT32 size_mib must be between 64 and 96")
    normalized_label = label.upper()
    if (
        not normalized_label
        or len(normalized_label) > 11
        or any(not (char.isalnum() or char in "_-") for char in normalized_label)
    ):
        raise ValueError("label must be 1-11 ASCII letters, digits, '_' or '-'")

    total_sectors = size_mib * 1024 * 1024 // BYTES_PER_SECTOR
    partition_sectors = total_sectors - MBR_PARTITION_START
    fat_sectors = _fat32_size_sectors(partition_sectors)
    boot = fat32_boot_sector(
        partition_sectors=partition_sectors,
        fat_sectors=fat_sectors,
        hidden_sectors=MBR_PARTITION_START,
        label=normalized_label,
    )
    partition_start_bytes = MBR_PARTITION_START * BYTES_PER_SECTOR
    first_fat = partition_start_bytes + FAT32_RESERVED_SECTORS * BYTES_PER_SECTOR
    second_fat = first_fat + fat_sectors * BYTES_PER_SECTOR
    root_start = second_fat + fat_sectors * BYTES_PER_SECTOR
    clusters = (
        partition_sectors
        - FAT32_RESERVED_SECTORS
        - FAT_COUNT * fat_sectors
    ) // FAT32_SECTORS_PER_CLUSTER
    fat_prefix = struct.pack(
        "<III",
        0x0FFFFFF8,
        0x0FFFFFFF,
        0x0FFFFFFF,
    )
    fsinfo = fs_info_sector(free_clusters=max(0, clusters - 1))
    volume_entry = bytearray(32)
    volume_entry[0:11] = normalized_label.encode("ascii").ljust(11, b" ")[:11]
    volume_entry[11] = 0x08

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as image:
        image.truncate(total_sectors * BYTES_PER_SECTOR)
        image.seek(0)
        image.write(
            mbr_sector(
                partition_sectors=partition_sectors,
            )
        )
        image.seek(partition_start_bytes)
        image.write(boot)
        image.seek(partition_start_bytes + BYTES_PER_SECTOR)
        image.write(fsinfo)
        image.seek(partition_start_bytes + 6 * BYTES_PER_SECTOR)
        image.write(boot)
        image.seek(partition_start_bytes + 7 * BYTES_PER_SECTOR)
        image.write(fsinfo)
        for offset in (first_fat, second_fat):
            image.seek(offset)
            image.write(fat_prefix)
        image.seek(root_start)
        image.write(volume_entry)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "filesystem": "FAT32",
        "partition_layout": "MBR",
        "partition_start_sector": MBR_PARTITION_START,
        "partition_sectors": partition_sectors,
        "sector_bytes": BYTES_PER_SECTOR,
        "sectors_per_cluster": FAT32_SECTORS_PER_CLUSTER,
        "fat_sectors": fat_sectors,
        "clusters": clusters,
        "label": normalized_label,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--format",
        choices=("fat32-mbr", "fat16-superfloppy"),
        default="fat32-mbr",
    )
    parser.add_argument("--size-mib", type=int)
    parser.add_argument("--label", default="M5FIXTURE")
    args = parser.parse_args()
    if args.format == "fat32-mbr":
        result = create_fat32_mbr_image(
            args.out,
            size_mib=args.size_mib or 64,
            label=args.label,
        )
    else:
        result = create_fat16_image(
            args.out,
            size_mib=args.size_mib or 32,
            label=args.label,
        )
    print(
        f"created {result['filesystem']} "
        f"{result.get('partition_layout', 'superfloppy')} image "
        f"{result['bytes']} bytes "
        f"sha256={result['sha256']}"
    )


if __name__ == "__main__":
    main()
