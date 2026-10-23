#!/usr/bin/env python3
"""Static analysis for ESP merged/segmented flash images."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ESP_IMAGE_MAGIC = 0xE9
ESP_APP_DESC_MAGIC = 0xABCD5432
PARTITION_MAGIC = 0x50AA
PARTITION_MD5_MAGIC = 0xEBEB
PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0x1000

CHIP_IDS = {
    0x0000: "esp32",
    0x0002: "esp32s2",
    0x0005: "esp32c3",
    0x0009: "esp32s3",
    0x000C: "esp32c2",
    0x000D: "esp32c6",
    0x0010: "esp32h2",
    0x0012: "esp32p4",
    0x0014: "esp32c61",
    0x0017: "esp32c5",
    0x0019: "esp32h21",
    0x001C: "esp32h4",
}


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def analyze_esp_image(data: bytes, offset: int = 0) -> dict:
    result = {
        "offset": offset,
        "valid": False,
        "errors": [],
        "warnings": [],
        "segments": [],
    }
    if offset < 0 or offset + 24 > len(data):
        result["errors"].append("image header is truncated")
        return result
    header = data[offset:offset + 24]
    if header[0] != ESP_IMAGE_MAGIC:
        result["errors"].append(
            f"invalid image magic 0x{header[0]:02x}, expected 0xe9"
        )
        return result
    segment_count = header[1]
    if segment_count > 16:
        result["errors"].append(f"segment count {segment_count} exceeds 16")
        return result
    chip_id = _u16(header, 12)
    result.update(
        {
            "valid": True,
            "segment_count": segment_count,
            "entry_addr": _u32(header, 4),
            "chip_id": chip_id,
            "chip": CHIP_IDS.get(chip_id, f"unknown(0x{chip_id:04x})"),
            "min_chip_rev_full": _u16(header, 15),
            "max_chip_rev_full": _u16(header, 17),
            "hash_appended": bool(header[23]),
        }
    )
    cursor = offset + 24
    for index in range(segment_count):
        if cursor + 8 > len(data):
            result["valid"] = False
            result["errors"].append(f"segment {index} header is truncated")
            break
        load_addr = _u32(data, cursor)
        length = _u32(data, cursor + 4)
        segment_start = cursor + 8
        segment_end = segment_start + length
        if segment_end > len(data):
            result["valid"] = False
            result["errors"].append(
                f"segment {index} data exceeds image: 0x{segment_start:x}-0x{segment_end:x}"
            )
            break
        result["segments"].append(
            {
                "index": index,
                "load_addr": load_addr,
                "length": length,
            }
        )
        cursor = segment_end
    result["image_end"] = cursor
    return result


def parse_partition_table(
    data: bytes,
    offset: int = PARTITION_TABLE_OFFSET,
    *,
    image_size: int | None = None,
    enforce_size: bool = True,
) -> dict:
    declared_size = len(data) if image_size is None else image_size
    result = {
        "offset": offset,
        "image_size": declared_size,
        "valid": False,
        "errors": [],
        "warnings": [],
        "partitions": [],
        "md5": None,
    }
    table = data[offset:offset + PARTITION_TABLE_SIZE]
    if len(table) < 32:
        result["errors"].append("partition table is truncated")
        return result
    table_end = None
    for index in range(0, len(table), 32):
        entry = table[index:index + 32]
        if len(entry) < 32:
            break
        magic = _u16(entry, 0)
        if magic == PARTITION_MAGIC:
            part_offset = _u32(entry, 4)
            size = _u32(entry, 8)
            label = entry[12:28].split(b"\x00", 1)[0].decode(
                "utf-8", errors="replace"
            )
            partition = {
                "type": entry[2],
                "subtype": entry[3],
                "offset": part_offset,
                "size": size,
                "label": label,
                "flags": _u32(entry, 28),
            }
            result["partitions"].append(partition)
            if enforce_size and part_offset + size > declared_size:
                result["errors"].append(
                    f"partition {label or index // 32} exceeds flash size"
                )
            continue
        if magic == PARTITION_MD5_MAGIC:
            result["md5"] = entry[16:32].hex()
            table_end = index
            break
        if magic == 0xFFFF:
            table_end = index
            break
        result["errors"].append(
            f"invalid partition entry magic 0x{magic:04x} at 0x{offset + index:x}"
        )
        break
    if not result["partitions"]:
        result["errors"].append("no partition entries found")
        return result
    if table_end is None:
        result["warnings"].append("partition table has no end or MD5 entry")
        table_end = len(result["partitions"]) * 32
    if result["md5"]:
        expected = hashlib.md5(table[:table_end]).hexdigest()
        if expected != result["md5"]:
            result["errors"].append("partition table MD5 does not match")
    result["valid"] = not result["errors"]
    return result


def find_app_descriptor(data: bytes, start: int, end: int) -> dict | None:
    magic = struct.pack("<I", ESP_APP_DESC_MAGIC)
    index = data.find(magic, start, end)
    if index < 0 or index + 256 > len(data):
        return None
    block = data[index:index + 256]

    def text(offset: int, length: int) -> str:
        return block[offset:offset + length].split(b"\x00", 1)[0].decode(
            "utf-8", errors="replace"
        )

    return {
        "offset": index,
        "secure_version": _u32(block, 4),
        "version": text(16, 32),
        "project_name": text(48, 32),
        "compile_time": text(80, 16),
        "compile_date": text(96, 16),
        "idf_version": text(112, 32),
        "elf_sha256": block[144:176].hex(),
        "min_efuse_blk_rev_full": _u16(block, 176),
        "max_efuse_blk_rev_full": _u16(block, 178),
    }


def expected_chip_id(soc: str) -> int | None:
    value = soc.upper()
    if "ESP32-P4" in value:
        return 0x0012
    if "ESP32-S3" in value:
        return 0x0009
    if "ESP32-C6" in value:
        return 0x000D
    if "ESP32-C3" in value:
        return 0x0005
    if "ESP32" in value:
        return 0x0000
    return None


def _next_power_of_two(value: int) -> int:
    result = 1
    while result < value:
        result <<= 1
    return result


def analyze_firmware(
    path: Path,
    *,
    expected_chip_id_value: int | None = None,
) -> dict:
    data = path.read_bytes()
    result = {
        "image_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "valid": False,
        "errors": [],
        "warnings": [],
        "bootloader": analyze_esp_image(data, 0),
        "partition_table": {},
        "app_images": [],
        "app_descriptor": None,
    }
    if not result["bootloader"]["valid"]:
        for offset, warning in (
            (0x1000, "classic ESP32 bootloader found at 0x1000"),
            (0x2000, "ESP32-P4 bootloader found at 0x2000"),
        ):
            candidate = analyze_esp_image(data, offset)
            if candidate["valid"]:
                result["bootloader"] = candidate
                result["warnings"].append(warning)
                break

    structural_table = parse_partition_table(
        data,
        enforce_size=False,
    )
    partition_end = max(
        (
            partition["offset"] + partition["size"]
            for partition in structural_table.get("partitions", [])
        ),
        default=len(data),
    )
    declared_size = _next_power_of_two(
        max(len(data), partition_end)
    )
    result["declared_flash_size"] = declared_size
    result["sparse_source"] = len(data) < declared_size
    result["partition_table"] = parse_partition_table(
        data,
        image_size=declared_size,
    )
    partition_table = result["partition_table"]
    if not partition_table["valid"]:
        result["warnings"].append(
            "no valid partition table; image may be app-only or non-standard"
        )
    for partition in partition_table.get("partitions", []):
        if partition["type"] != 0:
            continue
        image = analyze_esp_image(data, partition["offset"])
        image["present"] = any(
            byte != 0xFF
            for byte in data[
                partition["offset"] : min(
                    partition["offset"] + 32,
                    len(data),
                )
            ]
        )
        image["label"] = partition["label"]
        image["size"] = partition["size"]
        result["app_images"].append(image)
        if image["valid"]:
            descriptor = find_app_descriptor(
                data,
                partition["offset"],
                min(partition["offset"] + partition["size"], len(data)),
            )
            if descriptor:
                result["app_descriptor"] = descriptor
    bootloader = result["bootloader"]
    images = [
        bootloader,
        *[
            image
            for image in result["app_images"]
            if image.get("present")
        ],
    ]
    for image in images:
        result["errors"].extend(image.get("errors", []))
    if expected_chip_id_value is not None:
        for image in images:
            if image.get("valid") and image.get("chip_id") != expected_chip_id_value:
                result["errors"].append(
                    f"image chip {image.get('chip')} does not match expected "
                    f"chip id 0x{expected_chip_id_value:04x}"
                )
    if not result["app_images"]:
        result["warnings"].append("no app partition image found")
    if result["app_descriptor"] is None:
        result["warnings"].append("ESP app descriptor not found")
    result["valid"] = (
        bootloader.get("valid", False)
        and partition_table["valid"]
        and any(image.get("valid") for image in result["app_images"])
        and not result["errors"]
    )
    return result
