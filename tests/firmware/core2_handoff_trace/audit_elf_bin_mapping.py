#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Iterable


ESP_IMAGE_MAGIC = 0xE9
ESP32_EXTENDED_HEADER_SIZE = 16
ESP_IMAGE_HEADER_SIZE = 8 + ESP32_EXTENDED_HEADER_SIZE
ELF32_HEADER_SIZE = 52
ELF32_SECTION_HEADER_SIZE = 40


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_app_segments(image: bytes, app_offset: int) -> list[dict[str, int]]:
    if app_offset < 0 or app_offset >= len(image):
        raise ValueError("application offset is outside the image")
    if image[app_offset] != ESP_IMAGE_MAGIC:
        raise ValueError(
            f"application offset 0x{app_offset:x} does not start with "
            f"ESP image magic 0x{ESP_IMAGE_MAGIC:02x}"
        )

    segment_count = image[app_offset + 1]
    cursor = app_offset + ESP_IMAGE_HEADER_SIZE
    segments: list[dict[str, int]] = []
    for index in range(segment_count):
        if cursor + 8 > len(image):
            raise ValueError(f"segment {index} header exceeds the image")
        load_addr, length = struct.unpack_from("<II", image, cursor)
        data_offset = cursor + 8
        data_end = data_offset + length
        if data_end > len(image):
            raise ValueError(f"segment {index} data exceeds the image")
        segments.append(
            {
                "index": index,
                "load_addr": load_addr,
                "length": length,
                "file_offset": data_offset,
                "index_file_offset": cursor,
            }
        )
        cursor = data_end
    return segments


def read_app_bytes(
    image: bytes,
    segments: Iterable[dict[str, int]],
    address: int,
    size: int,
) -> tuple[dict[str, int], bytes]:
    for segment in segments:
        start = segment["load_addr"]
        end = start + segment["length"]
        if start <= address and address + size <= end:
            offset = segment["file_offset"] + address - start
            return segment, image[offset : offset + size]
    raise ValueError(f"address 0x{address:08x} is not covered by the app image")


def read_elf_bytes(elf: bytes, address: int, size: int) -> tuple[dict[str, int], bytes]:
    if len(elf) < ELF32_HEADER_SIZE:
        raise ValueError("ELF file is shorter than an ELF32 header")
    if elf[:4] != b"\x7fELF":
        raise ValueError("input is not an ELF file")
    if elf[4] != 1 or elf[5] != 1:
        raise ValueError("only little-endian ELF32 files are supported")

    section_offset = struct.unpack_from("<I", elf, 32)[0]
    section_entry_size = struct.unpack_from("<H", elf, 46)[0]
    section_count = struct.unpack_from("<H", elf, 48)[0]
    if section_entry_size < ELF32_SECTION_HEADER_SIZE:
        raise ValueError("ELF section header is too small")

    for index in range(section_count):
        header_offset = section_offset + index * section_entry_size
        if header_offset + ELF32_SECTION_HEADER_SIZE > len(elf):
            raise ValueError("ELF section table exceeds the file")
        section_addr = struct.unpack_from("<I", elf, header_offset + 12)[0]
        file_offset = struct.unpack_from("<I", elf, header_offset + 16)[0]
        section_size = struct.unpack_from("<I", elf, header_offset + 20)[0]
        if (
            section_addr != 0
            and section_addr <= address
            and address + size <= section_addr + section_size
        ):
            offset = file_offset + address - section_addr
            return (
                {
                    "index": index,
                    "addr": section_addr,
                    "size": section_size,
                    "file_offset": file_offset,
                },
                elf[offset : offset + size],
            )
    raise ValueError(f"address 0x{address:08x} is not covered by an ELF section")


def audit(
    image: bytes,
    elf: bytes,
    app_offset: int,
    addresses: Iterable[int],
    window: int,
) -> dict[str, object]:
    segments = parse_app_segments(image, app_offset)
    rows = []
    for address in addresses:
        segment, bin_bytes = read_app_bytes(image, segments, address, window)
        section, elf_bytes = read_elf_bytes(elf, address, window)
        rows.append(
            {
                "address": address,
                "window": window,
                "app_segment": segment,
                "elf_section": section,
                "bin_bytes_hex": bin_bytes.hex(),
                "bin_bytes_sha256": hashlib.sha256(bin_bytes).hexdigest(),
                "elf_bytes_hex": elf_bytes.hex(),
                "elf_bytes_sha256": hashlib.sha256(elf_bytes).hexdigest(),
                "matches": bin_bytes == elf_bytes,
            }
        )
    all_match = all(row["matches"] for row in rows)
    return {
        "schema_version": 1,
        "kind": "esp32-app-elf-mapping-audit",
        "validation": "static artifact mapping audit",
        "app_offset": app_offset,
        "segments": segments,
        "addresses": rows,
        "all_match": all_match,
        "classification": (
            "BIN_ELF_BYTES_MATCH"
            if all_match
            else "BIN_ELF_BYTES_MISMATCH"
        ),
    }


def parse_int(value: str) -> int:
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--image-label", required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--elf-label", required=True)
    parser.add_argument("--app-offset", type=parse_int, default=0x10000)
    parser.add_argument("--address", action="append", type=parse_int, required=True)
    parser.add_argument("--window", type=parse_int, default=16)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.window <= 0:
        raise SystemExit("--window must be positive")

    image = args.image.read_bytes()
    elf = args.elf.read_bytes()
    result = audit(
        image=image,
        elf=elf,
        app_offset=args.app_offset,
        addresses=args.address,
        window=args.window,
    )
    result["image"] = {
        "label": args.image_label,
        "bytes": len(image),
        "sha256": sha256(args.image),
    }
    result["elf"] = {
        "label": args.elf_label,
        "bytes": len(elf),
        "sha256": sha256(args.elf),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
