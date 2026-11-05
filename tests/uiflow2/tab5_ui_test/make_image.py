#!/usr/bin/env python3
"""Overlay a Tab5 probe in its actual VFS without changing the application."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
from firmware_analysis import analyze_esp_image, find_app_descriptor, parse_partition_table
from uiflow_source import FS_CONFIG, build_uiflow_source_image, uiflow_vfs_layout

FLASH_SIZE = 16 << 20


def application_identity(data: bytes) -> dict:
    table = parse_partition_table(data, image_size=FLASH_SIZE)
    if not table["valid"] or table["warnings"]:
        raise ValueError("Tab5 requires a complete valid partition table")
    factory = [p for p in table["partitions"] if p["type"] == 0 and p["subtype"] == 0]
    if len(factory) != 1:
        raise ValueError("Tab5 regression requires exactly one factory application")
    part = factory[0]
    start, end = part["offset"], part["offset"] + part["size"]
    info = analyze_esp_image(data, start)
    if (not info["valid"] or info.get("chip_id") != 0x12
            or info["image_end"] > end or end > len(data)):
        raise ValueError("Tab5 factory application is truncated, corrupt or not ESP32-P4")
    descriptor = find_app_descriptor(data, start, info["image_end"])
    return {
        "offset": start, "size": part["size"], "segments_end": info["image_end"],
        "partition_sha256": hashlib.sha256(data[start:end]).hexdigest(),
        "segments_sha256": hashlib.sha256(data[start:info["image_end"]]).hexdigest(),
        "elf_sha256": descriptor["elf_sha256"] if descriptor else None,
        "version": descriptor["version"] if descriptor else None,
    }


def compose_image(base: bytes, files: dict[str, str], *,
                  vfs_offset: int | None = None, vfs_size: int | None = None,
                  layout_policy: str = "actual") -> tuple[bytes, dict]:
    layout = uiflow_vfs_layout(base, FLASH_SIZE)
    declared = {"offset": vfs_offset, "size": vfs_size}
    drift = any(value is not None and value != layout[key]
                for key, value in declared.items())
    if drift:
        message = (f"VFS layout drift: declared {declared}; actual "
                   f"offset={layout['offset']:#x} size={layout['size']:#x}")
        if layout_policy == "strict":
            raise ValueError(message)
        print(message + "; using the actual partition table", file=sys.stderr)
    padded = base + b"\xff" * (FLASH_SIZE - len(base))
    application = application_identity(padded)
    start, size = layout["offset"], layout["size"]
    empty_vfs = padded[start:start + size] == b"\xff" * size
    composition_base = base
    if empty_vfs:
        # The checked-in emulator build recipe leaves its VFS erased. Only
        # that exact empty state may be initialized; an unmountable populated
        # official filesystem must fail without erasing anything.
        import littlefs
        buffer = bytearray(b"\xff" * size)
        fs = littlefs.LittleFS(context=littlefs.UserContext(buffer=buffer),
                               block_count=size // 4096, mount=False, **FS_CONFIG)
        fs.format()
        prepared = bytearray(padded)
        prepared[start:start + size] = buffer
        composition_base = bytes(prepared)
    image, metadata = build_uiflow_source_image(composition_base, FLASH_SIZE, files)
    if application_identity(image) != application:
        raise ValueError("VFS composition changed the original Tab5 application")
    metadata.update(application=application, application_bytes_unchanged=True,
                    declared_vfs=declared, layout_drift=drift,
                    input_base_sha256=hashlib.sha256(base).hexdigest(),
                    empty_vfs_initialized=empty_vfs)
    return image, metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--files-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--prog-size", type=int, choices=(32,), default=32)
    parser.add_argument("--vfs-offset", type=lambda x: int(x, 0))
    parser.add_argument("--vfs-size", type=lambda x: int(x, 0))
    parser.add_argument("--layout-policy", choices=("actual", "strict"), default="actual")
    args = parser.parse_args()
    files = {name: (args.files_dir / name).read_text() for name in ("boot.py", "main.py")}
    image, metadata = compose_image(args.base.read_bytes(), files,
                                   vfs_offset=args.vfs_offset, vfs_size=args.vfs_size,
                                   layout_policy=args.layout_policy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    (args.out.parent / "composition.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"image: {args.out}")
    print(f"sha256: {metadata['firmware_sha256']}")


if __name__ == "__main__":
    main()
