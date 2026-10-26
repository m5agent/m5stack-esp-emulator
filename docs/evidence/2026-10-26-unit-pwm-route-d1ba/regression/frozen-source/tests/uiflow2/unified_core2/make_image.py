#!/usr/bin/env python3
"""Build a merged Core2 UIFlow2 image with the unified probe."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))

from run_profile_ui_test import runtime_files  # noqa: E402

FLASH_SIZE = 16 << 20
BOOTLOADER_OFFSET = 0x1000
PARTITION_OFFSET = 0x8000
APP_OFFSET = 0x10000
VFS_OFFSET = 0x820000
VFS_SIZE = 0x7DF000


def append_segment(image: bytearray, offset: int, path: Path) -> None:
    payload = path.read_bytes()
    end = offset + len(payload)
    if end > len(image):
        raise SystemExit(f"{path} does not fit at {offset:#x}")
    image[offset:end] = payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--littlefs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--files-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    image = bytearray(args.base.read_bytes())
    if len(image) > FLASH_SIZE:
        raise SystemExit("base image is larger than 16 MiB")
    image.extend(b"\xff" * (FLASH_SIZE - len(image)))

    append_segment(image, BOOTLOADER_OFFSET,
                   args.build_dir / "bootloader/bootloader.bin")
    append_segment(image, PARTITION_OFFSET,
                   args.build_dir / "partition_table/partition-table.bin")
    append_segment(image, APP_OFFSET, args.build_dir / "micropython.bin")

    with tempfile.TemporaryDirectory(prefix="core2-unified-files-") as temp:
        files_dir = Path(temp) / "files"
        files_dir.mkdir()
        for relative, source in runtime_files(args.files_dir.resolve()).items():
            destination = files_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        vfs_path = Path(temp) / "vfs.bin"
        subprocess.run(
            [
                str(args.littlefs),
                "-c",
                "-b",
                "core2",
                "-i",
                str(files_dir),
                "-o",
                str(vfs_path),
                "-s",
                hex(VFS_SIZE),
            ],
            check=True,
            timeout=60,
        )
        vfs = vfs_path.read_bytes()
    if len(vfs) != VFS_SIZE:
        raise SystemExit(
            f"LittleFS produced {len(vfs):#x}, expected {VFS_SIZE:#x}"
        )
    image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE] = vfs

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    print(f"image: {args.out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
