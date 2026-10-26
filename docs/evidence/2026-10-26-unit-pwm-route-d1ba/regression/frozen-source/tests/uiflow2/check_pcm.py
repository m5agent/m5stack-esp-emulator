#!/usr/bin/env python3
"""Validate that a captured signed 16-bit PCM stream contains real audio."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pcm", type=Path)
    parser.add_argument("--min-nonzero", type=int, default=1000)
    parser.add_argument("--min-peak-to-peak", type=int, default=1000)
    args = parser.parse_args()

    data = args.pcm.read_bytes()
    if not data:
        raise SystemExit(f"PCM capture is empty: {args.pcm}")
    if len(data) % 2:
        raise SystemExit(f"PCM capture has an odd byte count: {len(data)}")

    samples = struct.unpack(f"<{len(data) // 2}h", data)
    nonzero = sum(1 for sample in samples if sample)
    peak_to_peak = max(samples) - min(samples)
    print(
        f"PCM bytes={len(data)} samples={len(samples)} "
        f"nonzero={nonzero} peak_to_peak={peak_to_peak}"
    )
    if nonzero < args.min_nonzero:
        raise SystemExit(
            f"PCM has only {nonzero} nonzero samples; "
            f"expected at least {args.min_nonzero}"
        )
    if peak_to_peak < args.min_peak_to_peak:
        raise SystemExit(
            f"PCM peak-to-peak is {peak_to_peak}; "
            f"expected at least {args.min_peak_to_peak}"
        )


if __name__ == "__main__":
    main()
