#!/usr/bin/env python3
"""Create an RMT symbol stream containing one NEC frame."""
from __future__ import annotations

import argparse
from pathlib import Path


def symbol(duration0: int, duration1: int, level0: int, level1: int) -> int:
    return (
        (duration0 & 0x7FFF)
        | ((level0 & 1) << 15)
        | ((duration1 & 0x7FFF) << 16)
        | ((level1 & 1) << 31)
    )


def nec_symbols(address: int, command: int) -> list[int]:
    words = [symbol(9000, 4500, 1, 0)]
    payload = ((command & 0xFF) << 16) | (address & 0xFF)
    for index in range(32):
        space = 1690 if payload & (1 << index) else 560
        words.append(symbol(560, space, 1, 0))
    words.append(symbol(560, 0, 1, 0))
    return words


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--address", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--command", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    words = nec_symbols(args.address, args.command)
    args.output.write_bytes(
        b"".join(word.to_bytes(4, "little") for word in words)
    )
    print(f"wrote {len(words)} RMT symbols to {args.output}")


if __name__ == "__main__":
    main()
