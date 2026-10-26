#!/usr/bin/env python3
"""Build a Tab5 peripheral-test image from the official 16 MiB image."""
import argparse
import hashlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prog-size", type=int, default=32)
    parser.add_argument("--vfs-offset", type=lambda x: int(x, 0), default=0x610000)
    parser.add_argument("--vfs-size", type=lambda x: int(x, 0), default=0x1E0000)
    args = parser.parse_args()

    try:
        import littlefs
    except ImportError:
        raise SystemExit(
            "install littlefs-python: python3 -m pip install littlefs-python"
        )

    image = bytearray(args.base.read_bytes())
    if len(image) != 16 << 20:
        raise SystemExit("base image must be exactly 16 MiB")

    vfs = bytearray([0xFF]) * args.vfs_size
    fs = littlefs.LittleFS(
        context=littlefs.UserContext(buffer=vfs),
        block_size=4096,
        block_count=args.vfs_size // 4096,
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
        with fs.open("/" + name, "w") as output:
            output.write((here / name).read_text())
    fs.unmount()

    image[args.vfs_offset:args.vfs_offset + args.vfs_size] = vfs
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    print(f"image: {args.out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")


if __name__ == "__main__":
    main()
