#!/usr/bin/env python3
"""Create deterministic NVS images containing string configuration values."""

from __future__ import annotations

import argparse
import hashlib
import struct
import zlib
from collections.abc import Mapping
from pathlib import Path

PAGE_SIZE = 4096
HEADER_SIZE = 32
BITMAP_OFFSET = 32
BITMAP_SIZE = 32
FIRST_ENTRY_OFFSET = 64
ENTRY_SIZE = 32
MAX_ENTRIES = 126
ACTIVE_STATE = 0xFFFFFFFE
VERSION2 = 0xFE
TYPE_U8 = 0x01
TYPE_STRING = 0x21
CHUNK_ANY = 0xFF


class NvsImageError(ValueError):
    """Raised when requested NVS contents cannot fit a valid image."""


def _crc32(data: bytes) -> int:
    return zlib.crc32(data, 0xFFFFFFFF) & 0xFFFFFFFF


def _entry_crc(entry: bytearray) -> None:
    crc_data = bytes(entry[0:4]) + bytes(entry[8:32])
    struct.pack_into("<I", entry, 4, _crc32(crc_data))


def _key_bytes(value: str, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise NvsImageError(f"{field} must be a non-empty string")
    encoded = value.encode("utf-8")
    if len(encoded) > 15:
        raise NvsImageError(f"{field} must be at most 15 UTF-8 bytes")
    if b"\x00" in encoded:
        raise NvsImageError(f"{field} must not contain NUL")
    return encoded


def _namespace_entry(namespace_index: int, namespace: str) -> bytes:
    entry = bytearray(b"\xff" * ENTRY_SIZE)
    entry[0] = 0
    entry[1] = TYPE_U8
    entry[2] = 1
    entry[3] = CHUNK_ANY
    key_data = _key_bytes(namespace, "namespace")
    entry[8:24] = b"\x00" * 16
    entry[8 : 8 + len(key_data)] = key_data
    entry[24] = namespace_index
    _entry_crc(entry)
    return bytes(entry)


def _string_entries(namespace_index: int, key: str, value: str) -> list[bytes]:
    key_data = _key_bytes(key, "key")
    if not isinstance(value, str):
        raise NvsImageError(f"value for {key!r} must be a string")
    data = value.encode("utf-8") + b"\x00"
    data_slots = max(1, (len(data) + ENTRY_SIZE - 1) // ENTRY_SIZE)
    header = bytearray(b"\xff" * ENTRY_SIZE)
    header[0] = namespace_index
    header[1] = TYPE_STRING
    header[2] = data_slots + 1
    header[3] = CHUNK_ANY
    header[8:24] = b"\x00" * 16
    header[8 : 8 + len(key_data)] = key_data
    struct.pack_into("<H", header, 24, len(data))
    struct.pack_into("<I", header, 28, _crc32(data))
    _entry_crc(header)
    padded = data.ljust(data_slots * ENTRY_SIZE, b"\xff")
    return [
        bytes(header),
        *(
            padded[index : index + ENTRY_SIZE]
            for index in range(0, len(padded), ENTRY_SIZE)
        ),
    ]


def build_string_nvs_image(
    partition_size: int,
    namespaces: Mapping[str, Mapping[str, str]],
) -> bytes:
    """Build one active NVSv2 page followed by erased pages.

    The supported subset is a namespace entry plus string key/value pairs.
    This is sufficient for first-boot configuration fixtures while keeping
    the generator deterministic and dependency-free.
    """

    if (
        isinstance(partition_size, bool)
        or not isinstance(partition_size, int)
        or partition_size < PAGE_SIZE
        or partition_size % PAGE_SIZE
    ):
        raise NvsImageError("partition size must be a positive multiple of 4096")
    if not isinstance(namespaces, Mapping) or not namespaces:
        raise NvsImageError("at least one namespace is required")

    entries: list[bytes] = []
    for namespace_index, (namespace, values) in enumerate(
        namespaces.items(),
        start=1,
    ):
        entries.append(_namespace_entry(namespace_index, namespace))
        if not isinstance(values, Mapping) or not values:
            raise NvsImageError(f"namespace {namespace!r} must contain values")
        for key, value in values.items():
            if not isinstance(key, str):
                raise NvsImageError("keys must be strings")
            entries.extend(_string_entries(namespace_index, key, value))
    if len(entries) > MAX_ENTRIES:
        raise NvsImageError(
            f"NVS fixture needs {len(entries)} entries; maximum is {MAX_ENTRIES}"
        )

    page = bytearray(b"\xff" * PAGE_SIZE)
    header = bytearray(b"\xff" * HEADER_SIZE)
    struct.pack_into("<I", header, 0, ACTIVE_STATE)
    struct.pack_into("<I", header, 4, 0)
    header[8] = VERSION2
    struct.pack_into("<I", header, 28, _crc32(bytes(header[4:28])))
    page[:HEADER_SIZE] = header

    bitmap = bytearray(b"\xff" * BITMAP_SIZE)
    for index, entry in enumerate(entries):
        offset = FIRST_ENTRY_OFFSET + index * ENTRY_SIZE
        page[offset : offset + ENTRY_SIZE] = entry
        bitmap[(index * 2) // 8] &= ~(1 << ((index * 2) & 7))
    page[BITMAP_OFFSET : BITMAP_OFFSET + BITMAP_SIZE] = bitmap

    image = bytearray(b"\xff" * partition_size)
    image[:PAGE_SIZE] = page
    return bytes(image)


def create_string_nvs_image(
    path: Path,
    *,
    partition_size: int,
    namespaces: Mapping[str, Mapping[str, str]],
) -> dict:
    data = build_string_nvs_image(partition_size, namespaces)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_size": PAGE_SIZE,
        "version": 2,
        "namespaces": list(namespaces),
        "entry_count": sum(len(values) for values in namespaces.values()),
    }


def _parse_set(value: str) -> tuple[str, str, str]:
    try:
        namespace, assignment = value.split(":", 1)
        key, entry_value = assignment.split("=", 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "--set must use namespace:key=value"
        ) from error
    return namespace, key, entry_value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--partition-size", type=lambda value: int(value, 0))
    parser.add_argument(
        "--set",
        action="append",
        type=_parse_set,
        default=[],
        metavar="NAMESPACE:KEY=VALUE",
    )
    args = parser.parse_args()
    namespaces: dict[str, dict[str, str]] = {}
    for namespace, key, value in args.set:
        namespaces.setdefault(namespace, {})[key] = value
    if args.partition_size is None:
        args.partition_size = PAGE_SIZE * max(1, len(args.set))
    result = create_string_nvs_image(
        args.out,
        partition_size=args.partition_size,
        namespaces=namespaces,
    )
    print(result)


if __name__ == "__main__":
    main()
