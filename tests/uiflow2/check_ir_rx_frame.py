#!/usr/bin/env python3
"""Check the UIFlow2 StickS3 IR RX success marker in a screendump."""
from __future__ import annotations

import argparse
from pathlib import Path


def ppm_rgb(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    tokens: list[bytes] = []
    offset = 0
    while len(tokens) < 4:
        while offset < len(data) and data[offset:offset + 1].isspace():
            offset += 1
        if data[offset:offset + 1] == b"#":
            offset = data.index(b"\n", offset) + 1
            continue
        end = offset
        while end < len(data) and not data[end:end + 1].isspace():
            end += 1
        tokens.append(data[offset:end])
        offset = end
    if tokens[0] != b"P6":
        raise ValueError("expected binary PPM")
    width, height = int(tokens[1]), int(tokens[2])
    while offset < len(data) and data[offset:offset + 1].isspace():
        offset += 1
        break
    pixels = data[offset:]
    packed_stride = width * 3
    padded_stride = (packed_stride + 3) & ~3
    if len(pixels) == height * padded_stride:
        canonical = bytearray(width * height * 3)
        for y in range(height):
            src = pixels[y * padded_stride:y * padded_stride + packed_stride]
            dst = y * packed_stride
            canonical[dst:dst + packed_stride] = src
        pixels = bytes(canonical)
    elif len(pixels) != height * packed_stride:
        raise ValueError("unexpected PPM payload size")
    return width, height, pixels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame", type=Path)
    parser.add_argument("--x", type=int, default=4)
    parser.add_argument("--y", type=int, default=4)
    args = parser.parse_args()

    width, height, pixels = ppm_rgb(args.frame)
    if not (0 <= args.x < width and 0 <= args.y < height):
        raise SystemExit("sample coordinate outside frame")
    offset = (args.y * width + args.x) * 3
    red, green, blue = pixels[offset:offset + 3]
    if green <= red * 2 or green <= blue * 2:
        raise SystemExit(
            f"IR RX success marker missing: rgb=({red},{green},{blue})"
        )
    print(f"PASS IR RX marker rgb=({red},{green},{blue})")


if __name__ == "__main__":
    main()
