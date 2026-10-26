#!/usr/bin/env python3
"""Build an AtomS3R UIFlow2 test image from a merged 8 MiB image."""
import argparse
import hashlib
from pathlib import Path

VFS_OFFSET = 0x641000
VFS_SIZE = 0x1BE000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prog-size", type=int, default=32)
    parser.add_argument("--efuse-out", type=Path)
    args = parser.parse_args()

    try:
        import littlefs
    except ImportError:
        raise SystemExit("install littlefs-python: python3 -m pip install littlefs-python")

    image = bytearray(args.base.read_bytes())
    if len(image) != 8 << 20:
        raise SystemExit("base image must be exactly 8 MiB")

    vfs = bytearray([0xff]) * VFS_SIZE
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
    here = Path(__file__).parent
    for name in ("boot.py", "main.py"):
        with fs.open("/" + name, "w") as f:
            f.write((here / name).read_text())
    fs.unmount()

    image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE] = vfs
    args.out.write_bytes(image)
    print(f"image: {args.out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")

    if args.efuse_out:
        efuse = bytearray(4096)
        # ESP32-S3 PKG_VERSION=1 (PICO/LGA56): BLOCK1 bit 117.
        efuse[36:40] = (0x00200000).to_bytes(4, "little")
        args.efuse_out.write_bytes(efuse)
        print(f"efuse: {args.efuse_out}")


if __name__ == "__main__":
    main()
