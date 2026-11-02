#!/usr/bin/env python3
"""Reconstruct the m5_lcd_cam deterministic DVP frames and verify an M12 log.

The synthetic LCD_CAM scene is sensor independent: 4 color bands by row
(phase = frame_seed) with white grid lines where x % 40 < 2 or
(y + frame_seed) % 40 < 2, emitted as 8-bit DVP RGB565 wire bytes (high byte
then low byte per pixel).  This oracle rebuilds the expected stream for the
AtomS3R-M12 probe geometries and checks the guest sha256 digests; it does not
send frame data to the guest.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

GEOMETRY = {
    "QQVGA": (160, 120),
    "QVGA": (320, 240),
    "VGA": (640, 480),
    "HD": (1280, 720),
}


def frame_bytes(width: int, height: int, seed: int = 0) -> bytes:
    data = bytearray(width * height * 2)
    area = width * height
    for index in range(len(data)):
        pixel = (index // 2) % area
        x = pixel % width
        y = pixel // width
        band = (y * 4 // height + seed) & 3
        if band == 0:
            red, green, blue = 235, 48, 48
        elif band == 1:
            red, green, blue = 235, 190, 35
        elif band == 2:
            red, green, blue = 40, 190, 80
        else:
            red, green, blue = 35, 105, 235
        if (x % 40) < 2 or ((y + seed) % 40) < 2:
            red = green = blue = 245
        value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
        data[index] = value & 0xFF if index & 1 else value >> 8
    return bytes(data)


def digest(width: int, height: int, seed: int = 0) -> str:
    return hashlib.sha256(frame_bytes(width, height, seed)).hexdigest()


GEOM_RE = re.compile(r"^M12_GEOM (\S+) (\d+) (\d+) (\d+) (\d+) ([0-9a-f]{64})$")
BASE_RE = re.compile(r"^M12_FRAME_SHA256 ([0-9a-f]{64})$")
STREAM_RE = re.compile(r"^M12_STREAM_FRAME \d+ (\d+) ([0-9a-f]{64})$")


def verify_geometry(lines: list[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for line in lines:
        match = GEOM_RE.match(line)
        if not match:
            continue
        name, _index, width, height, size, observed = match.groups()
        width, height, size = int(width), int(height), int(size)
        if GEOMETRY.get(name) != (width, height):
            errors.append(f"{name}: probe geometry {width}x{height} unexpected")
            continue
        if size != width * height * 2:
            errors.append(f"{name}: {size} bytes != {width * height * 2}")
            continue
        expected = digest(width, height)
        if observed != expected:
            errors.append(f"{name}: digest {observed} != reconstructed {expected}")
            continue
        seen.add(name)
    # Module default QVGA is reported as the single-frame baseline.
    for line in lines:
        match = BASE_RE.match(line)
        if match:
            expected = digest(320, 240)
            if match.group(1) != expected:
                errors.append(f"QVGA: digest {match.group(1)} != {expected}")
            else:
                seen.add("QVGA")
    missing = sorted(set(GEOMETRY) - seen)
    if missing:
        errors.append(f"missing geometry cases: {missing}")
    return errors


def verify_stream(lines: list[str], count: int = 5) -> list[str]:
    errors: list[str] = []
    frames = [
        (int(match.group(1)), match.group(2))
        for line in lines
        for match in [STREAM_RE.match(line)]
        if match
    ]
    if len(frames) != count:
        errors.append(f"stream frames {len(frames)} != {count}")
    valid = {digest(320, 240, seed): seed for seed in range(0, 128)}
    seeds: list[int] = []
    for index, (size, observed) in enumerate(frames):
        if size != 320 * 240 * 2:
            errors.append(f"stream frame {index}: {size} bytes")
        seed = valid.get(observed)
        if seed is None:
            errors.append(
                f"stream frame {index}: digest {observed} is not a "
                "reconstructed QVGA scene frame (torn/partial frame)"
            )
        else:
            seeds.append(seed)
    if len(set(seeds)) != len(seeds):
        errors.append(f"stream repeated a scene frame: seeds {seeds}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("serial_log", type=Path)
    args = parser.parse_args()
    lines = [line.strip() for line in
             args.serial_log.read_text(errors="replace").splitlines()]
    errors = verify_geometry(lines) + verify_stream(lines)
    if errors:
        for error in errors:
            print("M12_FRAME_ORACLE_FAIL", error)
        raise SystemExit(1)
    print("M12_FRAME_ORACLE_OK geometry=4 stream=5")


if __name__ == "__main__":
    main()
