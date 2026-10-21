#!/usr/bin/env python3
"""Validate a captured square-wave PCM stream by sign transitions."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcm", type=Path)
    parser.add_argument("--sample-rate", type=int, required=True)
    parser.add_argument("--frequency", type=float, required=True)
    parser.add_argument("--duration-ms", type=float, required=True)
    parser.add_argument("--tolerance", type=float, default=0.05)
    args = parser.parse_args()

    data = args.pcm.read_bytes()
    if not data or len(data) % 2:
        raise SystemExit(f"invalid signed-16 PCM file: {args.pcm}")
    samples = struct.unpack(f"<{len(data) // 2}h", data)
    active = [index for index, sample in enumerate(samples) if sample]
    if not active:
        raise SystemExit("PCM contains no active samples")

    first = active[0]
    last = active[-1]
    stream = samples[first:last + 1]
    transitions = sum(
        1
        for first, second in zip(stream, stream[1:])
        if (first >= 0) != (second >= 0)
    )
    expected = args.frequency * args.duration_ms / 1000.0 * 2.0
    tolerance = expected * args.tolerance
    print(
        f"square PCM active={len(stream)} transitions={transitions} "
        f"expected={expected:.1f} tolerance={tolerance:.1f}"
    )
    if abs(transitions - expected) > tolerance:
        raise SystemExit(
            f"transition count {transitions} differs from "
            f"{expected:.1f} +/- {tolerance:.1f}"
        )


if __name__ == "__main__":
    main()
