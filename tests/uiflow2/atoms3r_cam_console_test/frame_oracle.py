#!/usr/bin/env python3
"""Reconstruct the m5_lcd_cam deterministic DVP frames and verify a serial log.

The model generates an RGB565 byte stream from camera_pattern_pixel():
4 color bands by row (phase = frame_seed), with white grid lines where
y % 40 < 2 (phase advanced by frame_seed) or x % 40 < 2.  The 8-bit DVP wire
bytes are high byte then low byte for every pixel.  This script rebuilds that
stream for a geometry/frame_seed and checks the sha256 digests printed by the
guest probe.  No frame data is sent to the guest: it only cross-checks the
bytes the guest received from the modelled LCD_CAM+GDMA path.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


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


GEOMETRY = {
    "QQVGA": (160, 120),
    "240X240": (240, 240),
    "QVGA": (320, 240),
    "CIF": (400, 296),
    "VGA": (640, 480),
}
GEOM_RE = re.compile(r"^CAM_GEOM (\S+) (\d+) (\d+) (\d+) (\d+) ([0-9a-f]{64})$")
BASE_RE = re.compile(r"^CAM_FRAME_SHA256 ([0-9a-f]{64})$")
STREAM_RE = re.compile(r"^CAM_STREAM_FRAME \d+ (\d+) ([0-9a-f]{64})$")


def verify_geometry(lines: list[str]) -> list[str]:
    errors = []
    seen = set()
    for line in lines:
        match = GEOM_RE.match(line)
        if not match:
            continue
        name, _index, width, height, size, observed = match.groups()
        width, height, size = int(width), int(height), int(size)
        expected_wh = GEOMETRY.get(name)
        if expected_wh != (width, height):
            errors.append(f"{name}: probe geometry {width}x{height} unexpected")
            continue
        if size != width * height * 2:
            errors.append(f"{name}: {size} bytes != {width * height * 2}")
            continue
        expected = digest(width, height)
        if observed != expected:
            errors.append(
                f"{name}: digest {observed} != reconstructed {expected}"
            )
            continue
        seen.add(name)
    # The module default (QVGA) is the backward-compatible single-frame case:
    # it is reported as CAM_CAPTURE_BYTES + CAM_FRAME_SHA256 instead of a
    # CAM_GEOM line.
    for line in lines:
        match = BASE_RE.match(line)
        if match:
            expected = digest(320, 240)
            if match.group(1) != expected:
                errors.append(
                    f"QVGA: digest {match.group(1)} != reconstructed {expected}"
                )
            else:
                seen.add("QVGA")
    missing = sorted(set(GEOMETRY) - seen)
    if missing:
        errors.append(f"missing geometry cases: {missing}")
    return errors


def verify_stream(lines: list[str], count: int = 5) -> list[str]:
    errors = []
    frames = []
    for line in lines:
        match = STREAM_RE.match(line)
        if match:
            size, observed = match.groups()
            frames.append((int(size), observed))
    if len(frames) != count:
        errors.append(f"stream frames {len(frames)} != {count}")
    valid = {digest(320, 240, seed): seed for seed in range(0, 128)}
    seen_seeds = []
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
            seen_seeds.append(seed)
    if len(set(seen_seeds)) != len(seen_seeds):
        errors.append(f"stream repeated a scene frame: seeds {seen_seeds}")
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
            print("FRAME_ORACLE_FAIL", error)
        raise SystemExit(1)
    print("FRAME_ORACLE_OK geometry=5 stream=5")


if __name__ == "__main__":
    main()
