#!/usr/bin/env python3
"""Verify a retained M5.Mic record/recordWavFile signal against the owned tone."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import zipfile


def records(serial):
    for line in serial.splitlines():
        if line.startswith("HARDWARE_API "):
            yield json.loads(line.split(" ", 1)[1])


def wav_pcm(rows):
    chunks = sorted(
        (row for row in rows if row["api"] == "M5.Mic.recordWavFile.wav_chunk"),
        key=lambda row: row["value"]["offset"],
    )
    if not chunks:
        return None
    data = b"".join(bytes.fromhex(row["value"]["hex"]) for row in chunks)
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE" or data[12:16] != b"fmt ":
        raise ValueError("recorded WAV header is invalid")
    audio_format, channels, rate, byte_rate, block_align, bits = struct.unpack_from(
        "<HHIIHH", data, 20
    )
    if data[36:40] != b"data":
        raise ValueError("recorded WAV data chunk was not at the expected offset")
    size = struct.unpack_from("<I", data, 40)[0]
    pcm = data[44:44 + size]
    return pcm, {
        "audio_format": audio_format,
        "channels": channels,
        "sample_rate_hz": rate,
        "byte_rate": byte_rate,
        "block_align": block_align,
        "bits": bits,
        "wav_size": len(data),
        "wav_sha256": hashlib.sha256(data).hexdigest(),
    }


def dominant_frequency(samples, rate, expected):
    """Recover the fixture fundamental without trusting clipped spectral peaks.

    Core2's PDM capture is strongly clipped, so a rectangular-window DFT can
    put the apparent peak near 395 Hz even though the recovered waveform still
    repeats at the expected rate. Normalized autocorrelation remains stable
    under clipping; the expected fixture frequency bounds the lag search to
    avoid selecting a harmonic multiple.
    """
    if len(samples) < 32:
        raise ValueError("Mic capture is too short for frequency verification")
    mean = sum(samples) / len(samples)
    centered = [sample - mean for sample in samples]
    minimum_lag = max(2, int(rate / (expected * 1.25)))
    maximum_lag = min(
        len(centered) // 2,
        int(math.ceil(rate / (expected * 0.8))),
    )
    if maximum_lag <= minimum_lag:
        raise ValueError("Mic capture has too few samples for lag search")

    scores = {}
    for lag in range(minimum_lag - 1, maximum_lag + 2):
        if lag <= 0 or lag >= len(centered):
            continue
        left = centered[:-lag]
        right = centered[lag:]
        numerator = sum(a * b for a, b in zip(left, right))
        left_power = sum(value * value for value in left)
        right_power = sum(value * value for value in right)
        denominator = math.sqrt(left_power * right_power)
        scores[lag] = numerator / denominator if denominator else -1.0

    best_lag = max(
        (lag for lag in scores if minimum_lag <= lag <= maximum_lag),
        key=scores.get,
    )
    offset = 0.0
    if best_lag - 1 in scores and best_lag + 1 in scores:
        before = scores[best_lag - 1]
        current = scores[best_lag]
        after = scores[best_lag + 1]
        denominator = before - 2.0 * current + after
        if denominator:
            offset = 0.5 * (before - after) / denominator
            offset = max(-0.5, min(0.5, offset))
    return rate / (best_lag + offset)


def fixture_metadata(run_dir):
    with zipfile.ZipFile(run_dir / "evidence.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        source = manifest.get("device_data", {}).get("audio/microphone-source.pcm")
        return {
            "audio_fixture": manifest.get("audio_fixture"),
            "input_source_sha256": source.get("sha256") if source else None,
            "input_source_bytes": source.get("bytes") if source else None,
        }


def verify(run_dir, expected, tolerance):
    report = json.loads((run_dir / "report.json").read_text())
    rows = list(records((run_dir / "serial.txt").read_text(errors="replace")))
    summary_row = next((row for row in rows if row["api"] == "M5.Mic.record.pcm"), None)
    raw_row = next((row for row in rows if row["api"] == "M5.Mic.record.pcm_bytes"), None)
    wav = wav_pcm(rows)
    outputs = {}
    if raw_row is not None:
        raw_pcm = bytes.fromhex(raw_row["value"])
        raw_samples = struct.unpack("<%dh" % (len(raw_pcm) // 2), raw_pcm)
        raw_frequency = dominant_frequency(raw_samples, 16000, expected)
        raw_error = abs(raw_frequency - expected) / expected
        outputs["record"] = {
            "status": "PASS" if raw_error <= tolerance else "FAIL",
            "dominant_frequency_hz": raw_frequency,
            "relative_error": round(raw_error, 6),
            "samples": len(raw_samples),
            "nonzero_samples": sum(sample != 0 for sample in raw_samples),
            "min_sample": min(raw_samples),
            "max_sample": max(raw_samples),
            "pcm_sha256": hashlib.sha256(raw_pcm).hexdigest(),
        }
    if wav is not None:
        pcm, wav_format = wav
        rate = wav_format["sample_rate_hz"]
        wav_samples = struct.unpack("<%dh" % (len(pcm) // 2), pcm)
        wav_frequency = dominant_frequency(wav_samples, rate, expected)
        wav_error = abs(wav_frequency - expected) / expected
        outputs["recordWavFile"] = {
            "status": "PASS"
            if rate == 16000 and wav_error <= tolerance
            else "FAIL",
            "dominant_frequency_hz": wav_frequency,
            "relative_error": round(wav_error, 6),
            "sample_rate_hz": rate,
            "samples": len(wav_samples),
            "nonzero_samples": sum(sample != 0 for sample in wav_samples),
            "min_sample": min(wav_samples),
            "max_sample": max(wav_samples),
            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "format": wav_format,
        }
    if not outputs:
        raise ValueError("no retained Mic PCM bytes or WAV chunks")
    selected = outputs.get("recordWavFile", outputs.get("record"))
    pcm = (
        wav[0]
        if wav is not None
        else bytes.fromhex(raw_row["value"])
    )
    rate = (
        wav[1]["sample_rate_hz"]
        if wav is not None
        else 16000
    )
    if wav is None:
        wav_format = None
    samples = struct.unpack("<%dh" % (len(pcm) // 2), pcm)
    if not samples:
        raise ValueError("Mic output contains no samples")
    recording_states = [
        row["value"]
        for row in rows
        if row["api"] == "M5.Mic.isRecording" and "value" in row
    ]
    guest_state_ok = (
        summary_row is not None
        and summary_row["value"].get("recording") == 0
        and 1 in recording_states
        and recording_states[-1] == 0
    )
    passed = all(output["status"] == "PASS" for output in outputs.values())
    if not guest_state_ok:
        passed = False
    result = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "device_id": report["device_id"],
        "firmware_sha256": report["firmware_sha256"],
        "runtime_binary_sha256": report["runtime_binary_sha256"],
        "status": "PASS" if passed else "FAIL",
        "expected_frequency_hz": expected,
        "dominant_frequency_hz": selected["dominant_frequency_hz"],
        "relative_error": selected["relative_error"],
        "tolerance": tolerance,
        "sample_rate_hz": rate,
        "samples": len(samples),
        "nonzero_samples": sum(sample != 0 for sample in samples),
        "min_sample": min(samples),
        "max_sample": max(samples),
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "record_pcm_sha256": (
            outputs["record"]["pcm_sha256"] if "record" in outputs else None
        ),
        "record_wav_pcm_sha256": (
            outputs["recordWavFile"]["pcm_sha256"]
            if "recordWavFile" in outputs
            else None
        ),
        "guest_state_ok": guest_state_ok,
        "recording_states": recording_states,
        "guest_summary": summary_row["value"] if summary_row else None,
        "outputs": outputs,
        "wav": wav_format,
        **fixture_metadata(run_dir),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expected-frequency", type=float, default=440.0)
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run_dir, args.expected_frequency, args.tolerance)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
