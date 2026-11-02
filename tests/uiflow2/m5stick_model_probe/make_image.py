"""Build the m5stick model-fixture image from the generic classic-ESP32 image.

The fixture replaces the LittleFS vfs partition (0x375000/0x89000) of the
official Atom Lite UIFlow2 build; it is only a generic MicroPython transport
for the m5stick device-model probe, not the M5Stick factory firmware.
"""
import argparse
import hashlib
from pathlib import Path

VFS_OFFSET = 0x375000
VFS_SIZE = 0x89000
FLASH_SIZE = 4 << 20


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prog-size", type=int, default=32)
    args = parser.parse_args()

    try:
        import littlefs
    except ImportError:
        raise SystemExit("install littlefs-python: python3 -m pip install littlefs-python")

    image = bytearray(args.base.read_bytes())
    image.extend(b"\xff" * (FLASH_SIZE - len(image)))
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


if __name__ == "__main__":
    main()
