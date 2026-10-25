#!/usr/bin/env python3
"""Static analysis for ESP merged/segmented flash images."""
from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

ESP_IMAGE_MAGIC = 0xE9
ESP_APP_DESC_MAGIC = 0xABCD5432
PARTITION_MAGIC = 0x50AA
PARTITION_MD5_MAGIC = 0xEBEB
PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0x1000
SECURE_BOOT_V2_SIGNATURE_MAGIC = 0xE7
SECURE_BOOT_V2_SIGNATURE_SECTOR_SIZE = 0x1000
SECURE_BOOT_V2_SIGNATURE_BLOCK_SIZE = 1216

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


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _secure_boot_v2_block(data: bytes, index: int) -> dict | None:
    start = index * SECURE_BOOT_V2_SIGNATURE_BLOCK_SIZE
    block = data[
        start : start + SECURE_BOOT_V2_SIGNATURE_BLOCK_SIZE
    ]
    if len(block) != SECURE_BOOT_V2_SIGNATURE_BLOCK_SIZE:
        return None
    if block[0] != SECURE_BOOT_V2_SIGNATURE_MAGIC:
        return None
    version = block[1]
    if version not in {0x02, 0x03}:
        return None
    expected_crc = _u32(block, 1196)
    actual_crc = zlib.crc32(block[:1196]) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        return None
    sha_version = block[2] if version == 0x03 else 0
    digest_length = 48 if version == 0x03 and sha_version == 1 else 32
    image_digest = block[4 : 4 + digest_length]
    if version == 0x02:
        scheme = "rsa-pss-sha256"
        public_key_digest = hashlib.sha256(block[36:812]).hexdigest()
        curve_id = None
    elif sha_version == 1:
        curve_id = block[52]
        scheme = (
            "ecdsa-p384-sha384"
            if curve_id == 3
            else f"ecdsa-unknown-curve-{curve_id}-sha384"
        )
        public_key_digest = hashlib.sha256(block[52:149]).hexdigest()
    else:
        curve_id = block[36]
        curve_name = {
            1: "p192",
            2: "p256",
            3: "p384",
        }.get(curve_id, f"unknown-{curve_id}")
        scheme = f"ecdsa-{curve_name}-sha256"
        public_key_digest = hashlib.sha256(block[36:101]).hexdigest()
    return {
        "index": index,
        "version": version,
        "sha_version": sha_version,
        "curve_id": curve_id,
        "scheme": scheme,
        "image_digest_sha256": (
            hashlib.sha256(image_digest).hexdigest()
            if len(image_digest) == 32
            else None
        ),
        "image_digest_sha384": (
            hashlib.sha384(image_digest).hexdigest()
            if len(image_digest) == 48
            else None
        ),
        "public_key_digest_sha256": public_key_digest,
        "block_crc32": expected_crc,
        "_image_digest": image_digest,
    }


def detect_secure_boot_v2_signature(
    data: bytes,
    image: dict,
    *,
    region_end: int,
) -> dict:
    image_start = int(image.get("offset", 0))
    image_end = int(image.get("image_end", image_start))
    first_sector = _align_up(
        image_end,
        SECURE_BOOT_V2_SIGNATURE_SECTOR_SIZE,
    )
    last_sector = min(region_end, len(data))
    candidate_count = 0
    for sector_offset in range(
        first_sector,
        last_sector - SECURE_BOOT_V2_SIGNATURE_SECTOR_SIZE + 1,
        SECURE_BOOT_V2_SIGNATURE_SECTOR_SIZE,
    ):
        sector = data[
            sector_offset : sector_offset
            + SECURE_BOOT_V2_SIGNATURE_SECTOR_SIZE
        ]
        if not sector or sector[0] != SECURE_BOOT_V2_SIGNATURE_MAGIC:
            continue
        candidate_count += 1
        blocks = []
        for index in range(3):
            block = _secure_boot_v2_block(sector, index)
            if block is None:
                break
            blocks.append(block)
        if not blocks:
            continue
        image_content = data[image_start:sector_offset]
        digest_matches = []
        for block in blocks:
            digest = block.pop("_image_digest")
            actual = (
                hashlib.sha384(image_content).digest()
                if len(digest) == 48
                else hashlib.sha256(image_content).digest()
            )
            digest_matches.append(actual == digest)
        return {
            "status": (
                "image-digest-match"
                if all(digest_matches)
                else "image-digest-mismatch"
            ),
            "sector_offset": sector_offset,
            "image_bytes": sector_offset - image_start,
            "candidate_count": candidate_count,
            "block_count": len(blocks),
            "blocks": blocks,
            "image_digest_match": all(digest_matches),
            "signature_authenticity": "not-verified",
            "trust_root": "not-verified",
        }
    return {
        "status": "not-found",
        "sector_offset": None,
        "image_bytes": None,
        "candidate_count": candidate_count,
        "block_count": 0,
        "blocks": [],
        "image_digest_match": False,
        "signature_authenticity": "not-verified",
        "trust_root": "not-verified",
    }


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
    from firmware_filesystems import inventory_flash_filesystems

    result["filesystems"] = inventory_flash_filesystems(
        data,
        result["partition_table"],
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
        image["secure_boot_v2_signature"] = detect_secure_boot_v2_signature(
            data,
            image,
            region_end=min(
                partition["offset"] + partition["size"],
                len(data),
            ),
        )
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
    bootloader["secure_boot_v2_signature"] = detect_secure_boot_v2_signature(
        data,
        bootloader,
        region_end=min(PARTITION_TABLE_OFFSET, len(data)),
    )
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
    signature_images = []
    for image in images:
        evidence = image.get("secure_boot_v2_signature")
        if not isinstance(evidence, dict):
            continue
        signature_images.append(
            {
                "label": (
                    "bootloader"
                    if image is bootloader
                    else str(image.get("label") or "app")
                ),
                **evidence,
            }
        )
    if any(
        row.get("status") == "image-digest-mismatch"
        for row in signature_images
    ):
        signature_status = "invalid"
    elif any(
        row.get("status") == "image-digest-match"
        for row in signature_images
    ):
        signature_status = "signed-image-observed"
    else:
        signature_status = "not-found"
    result["secure_boot_v2"] = {
        "status": signature_status,
        "signature_authenticity": "not-verified",
        "trust_root": "not-verified",
        "images": signature_images,
    }
    result["valid"] = (
        bootloader.get("valid", False)
        and partition_table["valid"]
        and any(image.get("valid") for image in result["app_images"])
        and not result["errors"]
    )
    return result
