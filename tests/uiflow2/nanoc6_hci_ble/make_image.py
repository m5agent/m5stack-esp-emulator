#!/usr/bin/env python3
"""Build a NanoC6 HCI-UART board + BLE QEMU image."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))

from run_profile_ui_test import runtime_files  # noqa: E402

FLASH_SIZE = 4 << 20
VFS_OFFSET = 0x371000
VFS_SIZE = 0x8D000
BOOTLOADER_OFFSET = 0
PARTITION_OFFSET = 0x8000
APP_OFFSET = 0x10000


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
        raise SystemExit("install littlefs-python")

    image = bytearray(args.base.read_bytes())
    if len(image) > FLASH_SIZE:
        raise SystemExit("base image is larger than 4 MiB")
    image.extend(b"\xff" * (FLASH_SIZE - len(image)))
    for offset, source in (
        (BOOTLOADER_OFFSET, args.build_dir / "bootloader/bootloader.bin"),
        (PARTITION_OFFSET, args.build_dir / "partition_table/partition-table.bin"),
        (APP_OFFSET, args.build_dir / "micropython.bin"),
    ):
        payload = source.read_bytes()
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
        with fs.open("/" + relative.as_posix(), "w") as target:
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
