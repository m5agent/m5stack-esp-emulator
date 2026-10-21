#!/usr/bin/env python3
"""Decode WS2812/GRB LED bytes from captured ESP32-S3 RMT symbols."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

SYMBOLS_PER_LED = 24


def parse_rgb(value: str) -> tuple[int, int, int]:
    parts = tuple(int(part, 0) for part in value.split(","))
    if len(parts) != 3 or any(part < 0 or part > 255 for part in parts):
        raise argparse.ArgumentTypeError("RGB must be three values in 0..255")
    return parts


def decode_chunk(symbols: list[int]) -> bytes | None:
    highs = [symbol & 0x7FFF for symbol in symbols]
    if not highs:
        return None
    low = min(highs)
    high = max(highs)
    if high <= low:
        return None
    threshold = (low + high) / 2
    bits = "".join("1" if value > threshold else "0" for value in highs)
    if len(bits) % 8:
        return None
    return bytes(int(bits[index:index + 8], 2)
                 for index in range(0, len(bits), 8))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rmt")
    parser.add_argument("--led", action="append", type=parse_rgb, required=True)
    args = parser.parse_args()

    raw = Path(args.rmt).read_bytes()
    if len(raw) < 4 or len(raw) % 4:
        raise SystemExit(f"invalid RMT capture size: {len(raw)}")
    symbols = list(struct.unpack(f"<{len(raw) // 4}I", raw))
    chunk_size = len(args.led) * SYMBOLS_PER_LED
    expected = bytes(channel for led in args.led for channel in led)
    observed = []
    for offset in range(0, len(symbols) - chunk_size + 1, chunk_size):
        decoded = decode_chunk(symbols[offset:offset + chunk_size])
        if decoded is None:
            continue
        observed.append(decoded)
        if decoded == expected:
            print(f"WS2812 PASS expected={expected.hex()} "
                  f"chunk={offset // chunk_size}")
            return
    raise SystemExit(f"WS2812 mismatch expected={expected.hex()} "
                     f"observed={[value.hex() for value in observed]}")


if __name__ == "__main__":
    main()
