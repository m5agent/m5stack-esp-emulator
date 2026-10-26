#!/usr/bin/env python3
"""Verify a deterministic byte pattern in a raw disk image sector."""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--sector", type=int, required=True)
    parser.add_argument("--length", type=int, default=512)
    parser.add_argument("--offset", type=lambda value: int(value, 0),
                        default=0x31)
    parser.add_argument("--multiplier", type=int, default=7)
    args = parser.parse_args()

    start = args.sector * 512
    data = args.image.read_bytes()[start:start + args.length]
    expected = bytes(
        (index * args.multiplier + args.offset) & 0xFF
        for index in range(args.length)
    )
    print(
        f"disk image={args.image} sector={args.sector} "
        f"length={len(data)} match={data == expected}"
    )
    if data != expected:
        raise SystemExit("raw disk sector does not match expected pattern")


if __name__ == "__main__":
    main()
