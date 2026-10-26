#!/usr/bin/env python3
"""Decode RMT symbols captured from the UIFlow2 StickS3 IR example."""
from __future__ import annotations

import argparse
from pathlib import Path


def word_parts(word: int) -> tuple[int, int, int, int]:
    return (
        word & 0x7FFF,
        (word >> 16) & 0x7FFF,
        (word >> 15) & 1,
        (word >> 31) & 1,
    )


def decode_nec_at(words: list[int], offset: int) -> tuple[int, int, int]:
    frame = words[offset:offset + 34]
    if len(frame) != 34:
        raise ValueError(f"incomplete NEC frame at offset {offset}")

    duration0, duration1, _, _ = word_parts(frame[0])
    if not (8800 <= duration0 <= 9200 and 4300 <= duration1 <= 4700):
        raise ValueError(
            f"invalid NEC leader at offset {offset}: "
            f"duration0={duration0}, duration1={duration1}"
        )

    payload = 0
    for index, word in enumerate(frame[1:33]):
        _, space, _, _ = word_parts(word)
        if 1500 <= space <= 1800:
            payload |= 1 << index
        elif not 450 <= space <= 700:
            raise ValueError(
                f"invalid NEC bit space at index {index}, offset {offset}: "
                f"{space} us"
            )
    tail0, tail1, _, _ = word_parts(frame[33])
    if not (450 <= tail0 <= 700 and tail1 == 0):
        raise ValueError(
            f"invalid NEC tail at offset {offset}: "
            f"duration0={tail0}, duration1={tail1}"
        )
    return payload & 0xFF, (payload >> 16) & 0xFF, offset


def decode_nec(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    if len(data) % 4:
        raise ValueError(f"RMT capture is not word-aligned: {len(data)} bytes")
    words = [
        int.from_bytes(data[offset:offset + 4], "little")
        for offset in range(0, len(data), 4)
    ]
    errors = []
    for offset in range(len(words) - 33):
        try:
            address, command, found_offset = decode_nec_at(words, offset)
        except ValueError as error:
            errors.append(str(error))
            continue
        return address, command, found_offset
    detail = errors[0] if errors else "capture is too short"
    raise ValueError(f"no NEC frame found in {len(words)} symbols: {detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--address", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--command", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    address, command, offset = decode_nec(args.capture)
    if address != (args.address & 0xFF):
        raise SystemExit(f"address mismatch: {address:#04x} != {args.address:#04x}")
    if command != (args.command & 0xFF):
        raise SystemExit(f"command mismatch: {command:#04x} != {args.command:#04x}")
    print(
        f"PASS NEC offset={offset} address={address:#04x} "
        f"command={command:#04x}"
    )


if __name__ == "__main__":
    main()
