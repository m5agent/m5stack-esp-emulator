#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import random
import struct
import sys
import tempfile
import unittest
import zlib
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from firmware_analysis import (
    analyze_esp_image,
    analyze_firmware,
    parse_partition_table,
)
from firmware_filesystems import SPIFFS_CONFIGS, inventory_data_partition

RSA3072_TEST_VECTOR = json.loads(
    (
        ROOT
        / "platform/tests/fixtures/"
        "secure_boot_rsa3072_test_vector.json"
    ).read_text()
)
ECDSA_TEST_VECTORS = json.loads(
    (
        ROOT
        / "platform/tests/fixtures/"
        "secure_boot_ecdsa_test_vectors.json"
    ).read_text()
)


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


def build_secure_boot_v2_sector(
    image_content: bytes,
    *,
    scheme: str = "rsa",
    curve_id: int = 2,
) -> bytes:
    block = bytearray(1216)
    block[0] = 0xE7
    if scheme == "rsa":
        block[1] = 0x02
        digest = hashlib.sha256(image_content).digest()
        signature = bytes.fromhex(
            RSA3072_TEST_VECTOR["signatures"][digest.hex()]
        )
        block[4:36] = digest
        block[36:420] = bytes.fromhex(
            RSA3072_TEST_VECTOR["public_key"]["n_little_endian"]
        )
        block[420:424] = bytes.fromhex(
            RSA3072_TEST_VECTOR["public_key"]["e_little_endian"]
        )
        block[812:1196] = signature[::-1]
    elif scheme == "ecdsa":
        block[1] = 0x03
        if curve_id == 3:
            block[2] = 1
            block[4:52] = hashlib.sha384(image_content).digest()
            block[52] = curve_id
            digest = bytes(block[4:52]).hex()
            vector = ECDSA_TEST_VECTORS["p384"]
            signature = vector["signatures"][digest]
            block[53:101] = bytes.fromhex(vector["x_little"])
            block[101:149] = bytes.fromhex(vector["y_little"])
            block[149:197] = bytes.fromhex(signature["r_little"])
            block[197:245] = bytes.fromhex(signature["s_little"])
        else:
            block[4:36] = hashlib.sha256(image_content).digest()
            block[36] = curve_id
            if curve_id == 2:
                digest = bytes(block[4:36]).hex()
                vector = ECDSA_TEST_VECTORS["p256"]
                signature = vector["signatures"][digest]
                block[37:69] = bytes.fromhex(vector["x_little"])
                block[69:101] = bytes.fromhex(vector["y_little"])
                block[101:133] = bytes.fromhex(signature["r_little"])
                block[133:165] = bytes.fromhex(signature["s_little"])
            elif curve_id == 1:
                digest = bytes(block[4:36]).hex()
                vector = ECDSA_TEST_VECTORS["p192"]
                signature = vector["signatures"][digest]
                block[37:61] = bytes.fromhex(vector["x_little"])
                block[61:85] = bytes.fromhex(vector["y_little"])
                block[101:125] = bytes.fromhex(
                    signature["r_little"]
                )
                block[125:149] = bytes.fromhex(
                    signature["s_little"]
                )
    else:
        raise ValueError(scheme)
    struct.pack_into("<I", block, 1196, zlib.crc32(block[:1196]))
    sector = bytearray(b"\xff" * 4096)
    sector[: len(block)] = block
    return bytes(sector)


def build_flash_with_secure_boot_v2(
    *,
    scheme: str = "rsa",
    curve_id: int = 2,
) -> bytes:
    image = bytearray(build_flash())
    boot_sector = 0x1000
    app_sector = 0x11000
    image[boot_sector : boot_sector + 4096] = build_secure_boot_v2_sector(
        bytes(image[:boot_sector]),
        scheme=scheme,
        curve_id=curve_id,
    )
    image[app_sector : app_sector + 4096] = build_secure_boot_v2_sector(
        bytes(image[0x10000:app_sector]),
        scheme=scheme,
        curve_id=curve_id,
    )
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


def _fat_short_name_checksum(name: bytes) -> int:
    value = 0
    for byte in name:
        value = (((value & 1) << 7) + (value >> 1) + byte) & 0xFF
    return value


def _fat_short_name_11(name: str) -> bytes:
    if name == ".":
        return b".       " + b"   "
    if name == "..":
        return b"..      " + b"   "
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    encoded = stem.upper().encode("ascii")[:8].ljust(8, b" ")
    return encoded + suffix.upper().encode("ascii")[:3].ljust(3, b" ")


def _fat_lfn_entries(name: str, short_name: bytes) -> bytes:
    if name.upper() == short_name.decode("ascii").strip():
        return b""
    encoded = name.encode("utf-16le")
    characters = [
        int.from_bytes(encoded[offset : offset + 2], "little")
        for offset in range(0, len(encoded), 2)
    ]
    chunks = [
        characters[offset : offset + 13]
        for offset in range(0, len(characters), 13)
    ]
    checksum = _fat_short_name_checksum(short_name)
    rows = bytearray()
    for sequence in range(len(chunks), 0, -1):
        chunk = chunks[sequence - 1]
        padded = chunk + [0] * (13 - len(chunk))
        if len(chunk) < 13:
            padded[len(chunk)] = 0
            for index in range(len(chunk) + 1, 13):
                padded[index] = 0xFFFF
        entry = bytearray(32)
        entry[0] = sequence | (0x40 if sequence == len(chunks) else 0)
        entry[11] = 0x0F
        entry[13] = checksum
        for index, value in enumerate(padded):
            offsets = (
                1,
                3,
                5,
                7,
                9,
                14,
                16,
                18,
                20,
                22,
                24,
                28,
                30,
            )
            entry[offsets[index] : offsets[index] + 2] = value.to_bytes(
                2, "little"
            )
        rows.extend(entry)
    return bytes(rows)


def _fat_directory_entry(
    name: str,
    *,
    short_name: str | None = None,
    attributes: int = 0x20,
    cluster: int = 0,
    size: int = 0,
) -> bytes:
    short = _fat_short_name_11(short_name or name)
    entry = bytearray(32)
    entry[:11] = short
    entry[11] = attributes
    struct.pack_into("<H", entry, 20, (cluster >> 16) & 0xFFFF)
    struct.pack_into("<H", entry, 26, cluster & 0xFFFF)
    struct.pack_into("<I", entry, 28, size)
    return _fat_lfn_entries(name, short) + bytes(entry)


def build_fat_volume(fat_type: str) -> bytes:
    if fat_type not in {"fat12", "fat16", "fat32"}:
        raise ValueError(fat_type)
    sector_size = 512
    sectors_per_cluster = 1
    cluster_size = sector_size * sectors_per_cluster
    reserved_sectors = 1
    fat_count = 2
    root_entry_count = 0 if fat_type == "fat32" else 32
    if fat_type == "fat12":
        total_sectors = 128
        fat_sectors = 1
    elif fat_type == "fat16":
        total_sectors = 5000
        fat_sectors = 20
    else:
        total_sectors = 256
        fat_sectors = 3
    root_dir_sectors = (
        root_entry_count * 32 + sector_size - 1
    ) // sector_size
    first_data_sector = (
        reserved_sectors + fat_count * fat_sectors + root_dir_sectors
    )
    cluster_count = (
        total_sectors - first_data_sector
    ) // sectors_per_cluster

    cluster_payloads: list[bytearray] = []
    chains: list[list[int]] = []

    def allocate(payload: bytes = b"") -> list[int]:
        chunks = [
            payload[offset : offset + cluster_size]
            for offset in range(0, len(payload), cluster_size)
        ] or [b""]
        chain: list[int] = []
        for chunk in chunks:
            cluster = len(cluster_payloads) + 2
            cluster_payloads.append(
                bytearray(chunk.ljust(cluster_size, b"\x00"))
            )
            chain.append(cluster)
        if len(cluster_payloads) > cluster_count:
            raise AssertionError("test FAT volume is too small")
        chains.append(chain)
        return chain

    root_chain = allocate() if fat_type == "fat32" else []
    main_payload = b"print('fat fixture')\n" + b"x" * 684
    main_chain = allocate(main_payload)
    res_chain = allocate()
    certs_chain = allocate()
    configs_chain = allocate()
    license_payload = b"SPDX-License-Identifier: Apache-2.0\n"
    license_chain = allocate(license_payload)
    key_payload = b"not-a-real-private-key\n"
    key_chain = allocate(key_payload)
    long_name = "long_configuration.json"
    config_payload = b'{"enabled":true}\n'
    config_chain = allocate(config_payload)

    def directory(parent: int) -> bytes:
        return (
            _fat_directory_entry(
                ".",
                short_name=".",
                attributes=0x10,
                cluster=parent,
            )
            + _fat_directory_entry(
                "..",
                short_name="..",
                attributes=0x10,
                cluster=0,
            )
        )

    root_entries = (
        _fat_directory_entry(
            "main.py",
            cluster=main_chain[0],
            size=len(main_payload),
        )
        + _fat_directory_entry(
            "RES",
            attributes=0x10,
            cluster=res_chain[0],
        )
        + _fat_directory_entry(
            "CERTS",
            attributes=0x10,
            cluster=certs_chain[0],
        )
        + _fat_directory_entry(
            "CONFIGS",
            attributes=0x10,
            cluster=configs_chain[0],
        )
    )
    res_entries = directory(res_chain[0]) + _fat_directory_entry(
        "LICENSE",
        cluster=license_chain[0],
        size=len(license_payload),
    )
    certs_entries = directory(certs_chain[0]) + _fat_directory_entry(
        "device.key",
        cluster=key_chain[0],
        size=len(key_payload),
    )
    configs_entries = directory(configs_chain[0]) + _fat_directory_entry(
        long_name,
        short_name="LONGC~1.JSON",
        cluster=config_chain[0],
        size=len(config_payload),
    )

    def write_cluster(chain: list[int], payload: bytes) -> None:
        for index, cluster in enumerate(chain):
            chunk = payload[
                index * cluster_size : (index + 1) * cluster_size
            ]
            cluster_payloads[cluster - 2] = bytearray(
                chunk.ljust(cluster_size, b"\x00")
            )

    if root_chain:
        write_cluster(root_chain, root_entries)
    write_cluster(res_chain, res_entries)
    write_cluster(certs_chain, certs_entries)
    write_cluster(configs_chain, configs_entries)

    volume = bytearray(total_sectors * sector_size)
    volume[0:3] = b"\xeb\x3c\x90"
    volume[3:11] = b"M5TEST  "
    struct.pack_into("<H", volume, 11, sector_size)
    volume[13] = sectors_per_cluster
    struct.pack_into("<H", volume, 14, reserved_sectors)
    volume[16] = fat_count
    struct.pack_into("<H", volume, 17, root_entry_count)
    if total_sectors < 0x10000:
        struct.pack_into("<H", volume, 19, total_sectors)
    else:
        struct.pack_into("<I", volume, 32, total_sectors)
    volume[21] = 0xF8
    struct.pack_into("<H", volume, 24, 32)
    struct.pack_into("<H", volume, 26, 64)
    if fat_type == "fat32":
        struct.pack_into("<I", volume, 36, fat_sectors)
        struct.pack_into("<I", volume, 44, root_chain[0])
        volume[82:90] = b"FAT32   "
    else:
        struct.pack_into("<H", volume, 22, fat_sectors)
        label = b"FAT12   " if fat_type == "fat12" else b"FAT16   "
        volume[54:62] = label
    volume[510:512] = b"\x55\xaa"

    fat = bytearray(fat_sectors * sector_size)

    def set_fat_entry(cluster: int, value: int) -> None:
        if fat_type == "fat12":
            offset = cluster + cluster // 2
            raw = fat[offset] | fat[offset + 1] << 8
            if cluster & 1:
                raw = (raw & 0x000F) | ((value & 0x0FFF) << 4)
            else:
                raw = (raw & 0xF000) | (value & 0x0FFF)
            fat[offset] = raw & 0xFF
            fat[offset + 1] = (raw >> 8) & 0xFF
        elif fat_type == "fat16":
            struct.pack_into("<H", fat, cluster * 2, value & 0xFFFF)
        else:
            struct.pack_into("<I", fat, cluster * 4, value & 0x0FFFFFFF)

    eoc = {
        "fat12": 0x0FFF,
        "fat16": 0xFFFF,
        "fat32": 0x0FFFFFFF,
    }[fat_type]
    set_fat_entry(0, eoc)
    set_fat_entry(1, eoc)
    for chain in chains:
        for current, following in pairwise(chain):
            set_fat_entry(current, following)
        set_fat_entry(chain[-1], eoc)

    fat_offset = reserved_sectors * sector_size
    for copy_index in range(fat_count):
        start = fat_offset + copy_index * len(fat)
        volume[start : start + len(fat)] = fat

    if fat_type != "fat32":
        root_offset = (
            reserved_sectors + fat_count * fat_sectors
        ) * sector_size
        volume[root_offset : root_offset + len(root_entries)] = root_entries

    for index, payload in enumerate(cluster_payloads):
        start = (first_data_sector + index * sectors_per_cluster) * sector_size
        volume[start : start + len(payload)] = payload
    return bytes(volume)


def build_flash_with_fat(fat_type: str = "fat16") -> bytes:
    volume = build_fat_volume(fat_type)
    data_offset = 0x30000
    image = bytearray(b"\xff" * (data_offset + len(volume)))
    boot = build_image(descriptor=False)
    image[: len(boot)] = boot
    app = build_image()
    image[0x10000 : 0x10000 + len(app)] = app
    image[data_offset : data_offset + len(volume)] = volume
    entries = []
    for subtype, offset, size, label in (
        (0, 0x10000, 0x20000, b"factory"),
        (0x81, data_offset, len(volume), b"storage"),
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


def build_spiffs_volume(
    *,
    page_size: int = 256,
    block_size: int = 4096,
    obj_name_len: int = 32,
    metadata_len: int = 4,
    multi_index: bool = False,
) -> bytes:
    pages_per_block = block_size // page_size
    lookup_pages = max(1, pages_per_block * 2 // page_size)
    content_len = page_size - 5
    index_header_len = 8 + 4 + 1 + obj_name_len + metadata_len
    head_entries = (page_size - index_header_len) // 2
    continuation_entries = (page_size - 8) // 2
    if head_entries <= 0 or continuation_entries <= 0:
        raise ValueError("SPIFFS fixture geometry has no index entries")
    files = (
        ("/main.py", b"print('spiffs fixture')\n" + b"m" * 620),
        (
            "/res/LICENSE",
            b"SPDX-License-Identifier: BSD-3-Clause\n",
        ),
        ("/certs/device.key", b"not-a-real-spiffs-key\n"),
        (
            "/configs/settings.json",
            b'{"enabled":true,"mode":"safe"}\n',
        ),
    )
    if multi_index:
        main_size = content_len * (head_entries + 2)
        files = (
            (
                "/main.py",
                (
                    b"print('spiffs multi-index fixture')\n"
                    + (b"0123456789abcdef" * ((main_size // 16) + 1))
                )[:main_size],
            ),
            *files[1:],
        )

    data_counts = [
        (len(contents) + content_len - 1) // content_len
        for _, contents in files
    ]
    index_counts = [
        1
        if data_count <= head_entries
        else 1
        + (
            data_count
            - head_entries
            + continuation_entries
            - 1
        )
        // continuation_entries
        for data_count in data_counts
    ]
    usable_pages = pages_per_block - lookup_pages
    required_pages = sum(data_counts) + sum(index_counts)
    block_count = max(
        1,
        (required_pages + usable_pages - 1) // usable_pages,
    )
    volume = bytearray(b"\xff" * (block_size * block_count))
    next_page = 0

    def alloc_page() -> int:
        nonlocal next_page
        while next_page < len(volume) // page_size:
            block_page = next_page % pages_per_block
            if block_page < lookup_pages:
                next_page += 1
                continue
            result = next_page
            next_page += 1
            return result
        raise ValueError("SPIFFS fixture volume is too small")

    def set_lut(page_ix: int, obj_id: int) -> None:
        block = page_ix // pages_per_block
        block_page = page_ix % pages_per_block
        struct.pack_into(
            "<H",
            volume,
            block * block_size + (block_page - lookup_pages) * 2,
            obj_id,
        )

    for obj_id, (name, contents) in enumerate(files, start=1):
        chunks = [
            contents[offset : offset + content_len]
            for offset in range(0, len(contents), content_len)
        ]
        if not chunks:
            chunks = [b""]
        page_groups: list[list[bytes]] = []
        remaining_chunks = list(chunks)
        page_groups.append(remaining_chunks[:head_entries])
        del remaining_chunks[:head_entries]
        while remaining_chunks:
            page_groups.append(
                remaining_chunks[:continuation_entries]
            )
            del remaining_chunks[:continuation_entries]

        index_pages = [alloc_page() for _ in page_groups]
        data_pages: list[int] = []
        for chunk in chunks:
            page_ix = alloc_page()
            data_pages.append(page_ix)
            set_lut(page_ix, obj_id)
            span_ix = len(data_pages) - 1
            page = bytearray(b"\xff" * page_size)
            struct.pack_into("<HHB", page, 0, obj_id, span_ix, 0xFC)
            page[5 : 5 + len(chunk)] = chunk
            start = page_ix * page_size
            volume[start : start + page_size] = page

        encoded = name.encode("utf-8")
        if len(encoded) >= obj_name_len:
            raise ValueError("SPIFFS fixture path exceeds object-name length")
        data_offset = 0
        for span_ix, (index_page, page_group) in enumerate(
            zip(index_pages, page_groups, strict=True)
        ):
            set_lut(index_page, obj_id | 0x8000)
            index = bytearray(b"\xff" * page_size)
            struct.pack_into(
                "<HHB",
                index,
                0,
                obj_id | 0x8000,
                span_ix,
                0xF8,
            )
            entry_offset = 8
            if span_ix == 0:
                struct.pack_into("<I", index, 8, len(contents))
                index[12] = 1
                index[
                    13 : 13 + obj_name_len + metadata_len
                ] = b"\x00" * (obj_name_len + metadata_len)
                index[13 : 13 + len(encoded)] = encoded
                entry_offset = index_header_len
            for _ in page_group:
                struct.pack_into(
                    "<H",
                    index,
                    entry_offset,
                    data_pages[data_offset],
                )
                entry_offset += 2
                data_offset += 1
            start = index_page * page_size
            volume[start : start + page_size] = index
    return bytes(volume)


def build_flash_with_spiffs(**kwargs) -> bytes:
    volume = build_spiffs_volume(**kwargs)
    data_offset = 0x30000
    image = bytearray(b"\xff" * (data_offset + len(volume)))
    boot = build_image(descriptor=False)
    image[: len(boot)] = boot
    app = build_image()
    image[0x10000 : 0x10000 + len(app)] = app
    image[data_offset : data_offset + len(volume)] = volume
    entries = []
    for subtype, offset, size, label in (
        (0, 0x10000, 0x20000, b"factory"),
        (0x82, data_offset, len(volume), b"storage"),
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

    def test_detects_secure_boot_v2_signature_structure_and_digest(self):
        for scheme, curve_id, expected in (
            ("rsa", 2, "rsa-pss-sha256"),
            ("ecdsa", 1, "ecdsa-p192-sha256"),
            ("ecdsa", 2, "ecdsa-p256-sha256"),
            ("ecdsa", 3, "ecdsa-p384-sha384"),
        ):
            with self.subTest(scheme=scheme, curve_id=curve_id):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "signed.bin"
                    path.write_bytes(
                        build_flash_with_secure_boot_v2(
                            scheme=scheme,
                            curve_id=curve_id,
                        )
                    )
                    result = analyze_firmware(
                        path,
                        expected_chip_id_value=0x0009,
                    )

                self.assertTrue(result["valid"], result["errors"])
                evidence = result["secure_boot_v2"]
                self.assertEqual(
                    evidence["status"],
                    "signed-image-observed",
                )
                self.assertEqual(
                    evidence["signature_authenticity"],
                    "not-verified",
                )
                self.assertEqual(
                    evidence["trust_root"],
                    "not-verified",
                )
                by_label = {
                    row["label"]: row for row in evidence["images"]
                }
                self.assertEqual(
                    by_label["bootloader"]["sector_offset"],
                    0x1000,
                )
                self.assertEqual(
                    by_label["factory"]["sector_offset"],
                    0x11000,
                )
                for row in by_label.values():
                    self.assertEqual(row["block_count"], 1)
                    self.assertEqual(
                        row["blocks"][0]["scheme"],
                        expected,
                    )
                    self.assertEqual(
                        row["blocks"][0]["signature_math"],
                        "valid",
                    )
                    self.assertTrue(row["image_digest_match"])
                    self.assertEqual(
                        row["signature_math_verified"],
                        True,
                    )
                    self.assertEqual(
                        row["signature_authenticity"],
                        "not-verified",
                    )

    def test_secure_boot_v2_digest_mismatch_is_invalid(self):
        image = bytearray(build_flash_with_secure_boot_v2())
        image[0x10500] ^= 0xFF
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tampered.bin"
            path.write_bytes(image)
            result = analyze_firmware(path, expected_chip_id_value=0x0009)

        evidence = result["secure_boot_v2"]
        self.assertEqual(evidence["status"], "invalid")
        factory = next(
            row for row in evidence["images"] if row["label"] == "factory"
        )
        self.assertEqual(factory["status"], "image-digest-mismatch")
        self.assertFalse(factory["image_digest_match"])

    def test_secure_boot_v2_rsa_signature_math_mismatch_is_invalid(self):
        image = bytearray(build_flash_with_secure_boot_v2())
        sector_offset = 0x11000
        image[sector_offset + 900] ^= 0x01
        struct.pack_into(
            "<I",
            image,
            sector_offset + 1196,
            zlib.crc32(image[sector_offset : sector_offset + 1196]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-signature.bin"
            path.write_bytes(image)
            result = analyze_firmware(path, expected_chip_id_value=0x0009)

        evidence = result["secure_boot_v2"]
        self.assertEqual(evidence["status"], "invalid")
        factory = next(
            row for row in evidence["images"] if row["label"] == "factory"
        )
        self.assertEqual(factory["status"], "signature-math-mismatch")
        self.assertTrue(factory["image_digest_match"])
        self.assertFalse(factory["signature_math_verified"])
        self.assertEqual(
            factory["blocks"][0]["signature_math"],
            "invalid",
        )

    def test_secure_boot_v2_ecdsa_signature_math_mismatch_is_invalid(self):
        image = bytearray(
            build_flash_with_secure_boot_v2(
                scheme="ecdsa",
                curve_id=2,
            )
        )
        sector_offset = 0x11000
        image[sector_offset + 115] ^= 0x01
        struct.pack_into(
            "<I",
            image,
            sector_offset + 1196,
            zlib.crc32(image[sector_offset : sector_offset + 1196]),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-ecdsa-signature.bin"
            path.write_bytes(image)
            result = analyze_firmware(path, expected_chip_id_value=0x0009)

        evidence = result["secure_boot_v2"]
        self.assertEqual(evidence["status"], "invalid")
        factory = next(
            row for row in evidence["images"] if row["label"] == "factory"
        )
        self.assertEqual(factory["status"], "signature-math-mismatch")
        self.assertTrue(factory["image_digest_match"])
        self.assertFalse(factory["signature_math_verified"])
        self.assertEqual(
            factory["blocks"][0]["signature_math"],
            "invalid",
        )

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
        self.assertEqual(filesystem["permission_model"]["kind"], "none")
        self.assertEqual(
            filesystem["permission_summary"]["files_with_policy"],
            filesystem["file_count"],
        )
        self.assertEqual(
            filesystem["permission_summary"]["unix_mode_recorded"],
            0,
        )
        self.assertEqual(
            filesystem["permission_summary"]["runtime_enforcement"],
            "NOT RUN",
        )
        for row in filesystem["files"]:
            self.assertEqual(
                row["permission_policy"]["source"],
                "filesystem-metadata",
            )
            self.assertEqual(
                row["permission_policy"]["unix_mode"],
                "not-recorded",
            )

    def test_fat_inventory_supports_fat12_fat16_and_fat32(self):
        for fat_type in ("fat12", "fat16", "fat32"):
            with self.subTest(fat_type=fat_type):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / f"{fat_type}.bin"
                    path.write_bytes(build_flash_with_fat(fat_type))
                    result = analyze_firmware(
                        path,
                        expected_chip_id_value=0x0009,
                    )

                self.assertTrue(result["valid"], result["errors"])
                filesystem = result["filesystems"][0]
                self.assertEqual(filesystem["type"], "fat")
                self.assertEqual(filesystem["fat_type"], fat_type)
                self.assertEqual(filesystem["status"], "PASS")
                self.assertEqual(
                    filesystem["declared_licenses"],
                    ["Apache-2.0"],
                )
                self.assertEqual(filesystem["file_count"], 4)
                self.assertEqual(filesystem["directory_count"], 3)
                paths = {row["path"] for row in filesystem["files"]}
                self.assertIn("/main.py", paths)
                self.assertIn("/RES/LICENSE", paths)
                self.assertIn(
                    "/CONFIGS/long_configuration.json",
                    paths,
                )
                self.assertIn("<redacted-sensitive-path>", paths)
                self.assertNotIn(
                    "device.key",
                    json.dumps(result),
                )
                main = next(
                    row for row in filesystem["files"]
                    if row["path"] == "/main.py"
                )
                expected = (
                    b"print('fat fixture')\n" + b"x" * 684
                )
                self.assertEqual(len(expected), main["size"])
                self.assertEqual(
                    main["sha256"],
                    hashlib.sha256(expected).hexdigest(),
                )
                self.assertEqual(
                    filesystem["permission_model"]["kind"],
                    "fat-attributes",
                )
                self.assertEqual(
                    filesystem["permission_summary"]["files_with_policy"],
                    filesystem["file_count"],
                )
                self.assertEqual(
                    main["permission_policy"],
                    {
                        "source": "fat-directory-entry",
                        "model": "fat-attributes",
                        "unix_mode": "not-applicable",
                        "read_only_attribute": False,
                        "hidden": False,
                        "system": False,
                        "archive": True,
                        "runtime_enforcement": "not-proven",
                    },
                )
                self.assertTrue(filesystem["directory_permissions"])
                self.assertEqual(len(filesystem["sensitive_files"]), 1)

    def test_fat_read_only_attribute_is_recorded_without_overclaiming(self):
        volume = bytearray(build_fat_volume("fat12"))
        short_name = b"MAIN    PY"
        entry_offset = volume.find(short_name)
        self.assertGreaterEqual(entry_offset, 0)
        volume[entry_offset + 11] |= 0x01
        result = inventory_data_partition(
            bytes(volume),
            {
                "label": "storage",
                "subtype": 0x81,
                "offset": 0,
                "size": len(volume),
            },
        )

        self.assertIsNotNone(result)
        main = next(
            row for row in result["files"] if row["path"] == "/main.py"
        )
        self.assertTrue(
            main["permission_policy"]["read_only_attribute"]
        )
        self.assertEqual(
            main["permission_policy"]["runtime_enforcement"],
            "not-proven",
        )
        self.assertEqual(
            result["permission_summary"]["fat_read_only_attribute_count"],
            1,
        )
        self.assertEqual(
            result["permission_summary"]["runtime_enforcement"],
            "NOT RUN",
        )

    def test_fat_cycle_is_partial_not_a_pass(self):
        volume = bytearray(build_fat_volume("fat12"))
        fat_offset = 512
        cluster = 2
        offset = fat_offset + cluster + cluster // 2
        raw = volume[offset] | volume[offset + 1] << 8
        raw = (raw & 0xF000) | cluster
        volume[offset] = raw & 0xFF
        volume[offset + 1] = (raw >> 8) & 0xFF

        result = inventory_data_partition(
            bytes(volume),
            {
                "label": "storage",
                "subtype": 0x81,
                "offset": 0,
                "size": len(volume),
            },
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertTrue(
            any("loop" in error for error in result["errors"]),
            result["errors"],
        )

    def test_erased_fat_partition_is_unformatted(self):
        result = inventory_data_partition(
            b"\xff" * 4096,
            {
                "label": "storage",
                "subtype": 0x81,
                "offset": 0,
                "size": 4096,
            },
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "UNFORMATTED")

    def test_malformed_fat_inputs_are_rejected_without_exception(self):
        random_source = random.Random(0xFA7)
        for size in (512, 1024, 4096, 16384):
            with self.subTest(size=size):
                data = bytearray(random_source.randbytes(size))
                data[510:512] = b"\x55\xaa"
                result = inventory_data_partition(
                    bytes(data),
                    {
                        "label": "storage",
                        "subtype": 0x81,
                        "offset": 0,
                        "size": size,
                    },
                )
                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "INVALID")

    def test_spiffs_inventory_hashes_files_and_redacts_sensitive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spiffs.bin"
            path.write_bytes(build_flash_with_spiffs())
            result = analyze_firmware(path, expected_chip_id_value=0x0009)

        self.assertTrue(result["valid"], result["errors"])
        filesystem = result["filesystems"][0]
        self.assertEqual(filesystem["type"], "spiffs")
        self.assertEqual(filesystem["status"], "PASS")
        self.assertEqual(filesystem["page_size"], 256)
        self.assertEqual(filesystem["block_size"], 4096)
        self.assertEqual(
            filesystem["declared_licenses"],
            ["BSD-3-Clause"],
        )
        self.assertEqual(filesystem["file_count"], 4)
        self.assertEqual(filesystem["directory_count"], 3)
        paths = {row["path"] for row in filesystem["files"]}
        self.assertIn("/main.py", paths)
        self.assertIn("/res/LICENSE", paths)
        self.assertIn("/configs/settings.json", paths)
        self.assertIn("<redacted-sensitive-path>", paths)
        self.assertNotIn("device.key", json.dumps(result))
        main = next(
            row
            for row in filesystem["files"]
            if row["path"] == "/main.py"
        )
        expected = b"print('spiffs fixture')\n" + b"m" * 620
        self.assertEqual(main["size"], len(expected))
        self.assertEqual(
            main["sha256"],
            hashlib.sha256(expected).hexdigest(),
        )
        self.assertEqual(len(filesystem["sensitive_files"]), 1)
        self.assertTrue(filesystem["lut_validated"])
        self.assertEqual(filesystem["permission_model"]["kind"], "none")
        self.assertEqual(
            filesystem["permission_summary"]["files_with_policy"],
            filesystem["file_count"],
        )
        self.assertEqual(
            filesystem["permission_summary"]["runtime_enforcement"],
            "NOT RUN",
        )
        for row in filesystem["files"]:
            self.assertEqual(
                row["permission_policy"]["unix_mode"],
                "not-recorded",
            )
            self.assertEqual(
                row["permission_policy"]["runtime_enforcement"],
                "not-proven",
            )

        for config in SPIFFS_CONFIGS:
            page_size, block_size, obj_name_len, metadata_len = config
            with self.subTest(
                page_size=page_size,
                block_size=block_size,
                obj_name_len=obj_name_len,
                metadata_len=metadata_len,
            ):
                volume = build_spiffs_volume(
                    page_size=page_size,
                    block_size=block_size,
                    obj_name_len=obj_name_len,
                    metadata_len=metadata_len,
                    multi_index=True,
                )
                inventory = inventory_data_partition(
                    volume,
                    {
                        "label": "storage",
                        "subtype": 0x82,
                        "offset": 0,
                        "size": len(volume),
                    },
                )
                self.assertIsNotNone(inventory)
                self.assertEqual(inventory["status"], "PASS")
                self.assertTrue(inventory["lut_validated"])
                self.assertEqual(
                    inventory["selected_config"],
                    {
                        "page_size": page_size,
                        "block_size": block_size,
                        "object_name_len": obj_name_len,
                        "metadata_len": metadata_len,
                    },
                )
                main = next(
                    row
                    for row in inventory["files"]
                    if row["path"] == "/main.py"
                )
                self.assertGreater(main["index_page_count"], 1)
                self.assertGreater(main["data_page_count"], 1)

    def test_unformatted_and_malformed_spiffs_inputs(self):
        result = inventory_data_partition(
            b"\xff" * 4096,
            {
                "label": "storage",
                "subtype": 0x82,
                "offset": 0,
                "size": 4096,
            },
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "UNFORMATTED")

        random_source = random.Random(0x5F1F5)
        for size in (4096, 16384):
            with self.subTest(kind="random", size=size):
                result = inventory_data_partition(
                    random_source.randbytes(size),
                    {
                        "label": "storage",
                        "subtype": 0x82,
                        "offset": 0,
                        "size": size,
                    },
                )
                self.assertIsNotNone(result)
                self.assertEqual(result["status"], "INVALID")
                self.assertNotIn("files", result)

        corrupted = bytearray(build_spiffs_volume())
        page_size = 256
        block_size = 4096
        pages_per_block = 4096 // page_size
        lookup_pages = 1
        corrupted_index_count = 0
        for block in range(len(corrupted) // block_size):
            for block_page in range(lookup_pages, pages_per_block):
                lut_offset = (
                    block * block_size
                    + (block_page - lookup_pages) * 2
                )
                lut_obj_id = int.from_bytes(
                    corrupted[lut_offset : lut_offset + 2],
                    "little",
                )
                if lut_obj_id & 0x8000:
                    corrupted[lut_offset : lut_offset + 2] = b"\xff\xff"
                    corrupted_index_count += 1
        self.assertGreater(corrupted_index_count, 0)
        result = inventory_data_partition(
            bytes(corrupted),
            {
                "label": "storage",
                "subtype": 0x82,
                "offset": 0,
                "size": len(corrupted),
            },
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "INVALID")
        self.assertNotIn("files", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
