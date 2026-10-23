#!/usr/bin/env python3
"""Install the unified StackChan probe into a merged UIFlow2 image."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))

from run_profile_ui_test import runtime_files  # noqa: E402

FLASH_SIZE = 16 << 20
APP_OFFSET = 0x10000
SYSTEM_FS_OFFSET = 0x9A0000
SYSTEM_FS_SIZE = 0x100000
VFS_OFFSET = 0xAA0000
VFS_SIZE = 0x4C0000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--files-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--prog-size", type=int, default=32)
    args = parser.parse_args()

    try:
        import littlefs
    except ImportError:
        raise SystemExit(
            "install littlefs-python: python3 -m pip install littlefs-python"
        )

    image = bytearray(args.base.read_bytes())
    if len(image) > FLASH_SIZE:
        raise SystemExit("base image is larger than 16 MiB")
    image.extend(b"\xff" * (FLASH_SIZE - len(image)))

    segments = (
        (0, args.build_dir / "bootloader/bootloader.bin"),
        (0x8000, args.build_dir / "partition_table/partition-table.bin"),
        (APP_OFFSET, args.build_dir / "micropython.bin"),
        (SYSTEM_FS_OFFSET, args.build_dir / "fs-system.bin"),
    )
    for offset, source in segments:
        payload = source.read_bytes()
        if source.name == "fs-system.bin" and len(payload) > SYSTEM_FS_SIZE:
            raise SystemExit("fs-system.bin does not fit its partition")
        image[offset:offset + len(payload)] = payload

    vfs = bytearray([0xFF]) * VFS_SIZE
    fs = littlefs.LittleFS(
        context=littlefs.UserContext(buffer=vfs),
        block_size=4096,
        block_count=VFS_SIZE // 4096,
        read_size=128,
        prog_size=args.prog_size,
        lookahead_size=128,
        block_cycles=100,
        mount=False,
    )
    fs.format()
    fs.mount()
    for relative, source in runtime_files(args.files_dir.resolve()).items():
        destination = "/" + relative.as_posix()
        with fs.open(destination, "w") as target:
            target.write(source.read_text())
    fs.unmount()

    image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE] = vfs
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    print(f"image: {args.out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
