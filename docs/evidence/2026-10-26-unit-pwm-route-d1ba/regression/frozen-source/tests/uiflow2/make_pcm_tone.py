#!/usr/bin/env python3
"""Generate a deterministic signed 16-bit PCM tone for emulator injection."""
from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--frequency", type=float, default=440.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--amplitude", type=int, default=12000)
    args = parser.parse_args()

    samples = int(args.sample_rate * args.seconds)
    data = bytearray()
    for index in range(samples):
        value = int(
            args.amplitude
            * math.sin(2.0 * math.pi * args.frequency * index / args.sample_rate)
        )
        data.extend(struct.pack("<h", value))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(
        f"wrote {args.output}: {len(data)} bytes, "
        f"{args.frequency:g} Hz @ {args.sample_rate} Hz"
    )


if __name__ == "__main__":
    main()
