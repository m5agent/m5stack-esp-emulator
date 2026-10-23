#!/usr/bin/env python3
"""Build a NanoC6 UIFlow2 image for the C6 WiFi probe."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

VFS_OFFSET = 0x371000
VFS_SIZE = 0x8D000
FLASH_SIZE = 4 << 20


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--app-only", action="store_true")
    args = parser.parse_args()

    try:
        import littlefs
    except ImportError:
        raise SystemExit("install littlefs-python")

    image = bytearray(args.base.read_bytes())
    image.extend(b"\xff" * (FLASH_SIZE - len(image)))
    if args.build_dir:
        segments = (
            (0x10000, args.build_dir / "micropython.bin"),
        ) if args.app_only else (
            (0, args.build_dir / "bootloader/bootloader.bin"),
            (0x8000, args.build_dir / "partition_table/partition-table.bin"),
            (0x10000, args.build_dir / "micropython.bin"),
        )
        for offset, source in segments:
            payload = source.read_bytes()
            image[offset:offset + len(payload)] = payload
    vfs = bytearray([0xFF]) * VFS_SIZE
    fs = littlefs.LittleFS(
        context=littlefs.UserContext(buffer=vfs),
        block_size=4096,
        block_count=VFS_SIZE // 4096,
        read_size=128,
        prog_size=32,
        lookahead_size=128,
        block_cycles=100,
        mount=False,
    )
    fs.format()
    fs.mount()
    here = Path(__file__).parent
    for name in ("boot.py", "main.py"):
        with fs.open("/" + name, "w") as target:
            target.write((here / name).read_text())
    fs.unmount()
    image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE] = vfs
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    print(f"image: {args.out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
