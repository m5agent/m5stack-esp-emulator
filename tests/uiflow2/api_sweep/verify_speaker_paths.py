#!/usr/bin/env python3
"""Verify retained M5.Speaker PCM against each board's native output format."""
from __future__ import annotations

import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path
import struct
import zipfile


OUTPUT_FORMATS = {
    "stopwatch": {"sample_rate_hz": 44100, "channels": 2},
    "sticks3": {"sample_rate_hz": 22050, "channels": 2},
    "core2": {"sample_rate_hz": 48000, "channels": 1},
}


def fft(values):
    count = len(values)
    target = 0
    for source in range(1, count):
        bit = count >> 1
        while target & bit:
            target ^= bit
            bit >>= 1
        target ^= bit
        if source < target:
            values[source], values[target] = values[target], values[source]
    length = 2
    while length <= count:
        angle = -2.0 * math.pi / length
        root = complex(math.cos(angle), math.sin(angle))
        half = length // 2
        for offset in range(0, count, length):
            weight = 1 + 0j
            for index in range(offset, offset + half):
                even = values[index]
                odd = values[index + half] * weight
                values[index] = even + odd
                values[index + half] = even - odd
                weight *= root
        length <<= 1
    return values


def dominant_frequency(samples, sample_rate):
    size = 1
    while size * 2 <= min(8192, len(samples)):
        size *= 2
    if size < 1024:
        raise ValueError("speaker capture is too short for frequency verification")
    selected = samples[:size]
    mean = sum(selected) / size
    spectrum = fft([complex(value - mean, 0) for value in selected])
    low = max(1, int(80 * size / sample_rate))
    high = min(size // 2, int(2000 * size / sample_rate))
    power, index = max(
        ((abs(spectrum[item]) ** 2, item) for item in range(low, high + 1)),
        key=lambda item: item[0],
    )
    if power <= 0:
        raise ValueError("speaker capture has no spectral energy")
    return index * sample_rate / size


def analyze(raw, expected, tolerance, output_format):
    if len(raw) < 4096:
        raise ValueError("speaker capture is too short")
    channels = output_format["channels"]
    frame_size = channels * 2
    complete = len(raw) - len(raw) % frame_size
    if complete < 4096:
        raise ValueError("speaker capture has too few complete s16 frames")
    values = struct.unpack("<%dh" % (complete // 2), raw[:complete])
    first = next((index for index, value in enumerate(values) if value), None)
    if first is None:
        raise ValueError("speaker capture is silent")
    first -= first % channels
    values = values[first:]
    if channels == 2:
        left = values[::2]
        right = values[1::2]
        left, right = left[:len(right)], right[:len(left)]
        identical = (
            sum(a == b for a, b in zip(left, right)) / max(1, len(left))
        )
        samples = left
    else:
        identical = None
        samples = values
    measured = dominant_frequency(samples, output_format["sample_rate_hz"])
    relative_error = abs(measured - expected) / expected
    passed = relative_error <= tolerance and (
        identical is None or identical >= 0.98
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "expected_frequency_hz": expected,
        "dominant_frequency_hz": round(measured, 3),
        "relative_error": round(relative_error, 6),
        "tolerance": tolerance,
        "sample_rate_hz": output_format["sample_rate_hz"],
        "channels": channels,
        "stereo_channels_identical_fraction": (
            round(identical, 6) if identical is not None else None
        ),
        "capture_bytes": len(raw),
        "complete_pcm_bytes": complete,
        "trimmed_start_bytes": first * 2,
        "samples_analyzed": min(8192, len(samples)),
        "min_sample": min(samples),
        "max_sample": max(samples),
        "pcm_sha256": hashlib.sha256(raw).hexdigest(),
    }


def verify(run_dir, expected, tolerance):
    report = json.loads((run_dir / "report.json").read_text())
    serial = (run_dir / "serial.txt").read_text(errors="replace")
    case = next(
        (
            item
            for item in ("wav-file", "wav", "file", "raw")
            if "SPEAKER_PATH_DONE " + item in serial
        ),
        None,
    )
    if case is None:
        raise ValueError("speaker path did not reach its completion marker")
    with zipfile.ZipFile(run_dir / "evidence.zip") as archive:
        raw = archive.read("audio/speaker.pcm")
        manifest = json.loads(archive.read("manifest.json"))
    observed = manifest.get("audio", {})
    if observed.get("bytes") != len(raw) or observed.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("speaker PCM differs from the evidence manifest")
    result = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "device_id": report["device_id"],
        "firmware_sha256": report["firmware_sha256"],
        "runtime_binary_sha256": report["runtime_binary_sha256"],
        "case": case,
        **analyze(
            raw,
            expected,
            tolerance,
            OUTPUT_FORMATS[report["device_id"]],
        ),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-frequency", type=float, default=660.0)
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run_dir, args.expected_frequency, args.tolerance)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
