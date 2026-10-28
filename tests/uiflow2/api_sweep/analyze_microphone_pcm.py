#!/usr/bin/env python3
"""Compare retained guest Mic.record samples with a same-session tone fixture.

This signal oracle permits the documented M5Unified gain, DC removal and
clipping. It establishes frequency/sample routing through I2S, not byte-exact
audio fidelity or physical microphone measurements.
"""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import wave
import zipfile


def signal_metrics(raw, sample_rate, channels=1):
    values = list(struct.unpack("<" + "h" * (len(raw) // 2), raw))[::channels]
    if len(values) < 100:
        raise ValueError("at least 100 signed PCM samples are required")
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    energy = sum(value * value for value in centered)
    crossings = []
    for index in range(1, len(centered)):
        left, right = centered[index - 1:index + 1]
        if left <= 0 < right:
            crossings.append(index - 1 + (-left / (right - left)))
    crossing_frequency = None
    if len(crossings) >= 5:
        crossing_frequency = (len(crossings) - 1) * sample_rate / (crossings[-1] - crossings[0])

    def spectral_energy(frequency):
        increment = complex(math.cos(2 * math.pi * frequency / sample_rate),
                            -math.sin(2 * math.pi * frequency / sample_rate))
        phase, total = 1.0, 0.0
        for value in centered:
            total += value * phase
            phase *= increment
        return 2 * abs(total) ** 2 / (len(values) * energy) if energy else 0.0

    # Search independently of the expected fixture tone, then refine to 1 Hz.
    ratio, frequency = max((spectral_energy(frequency), frequency)
                           for frequency in range(50, min(2000, sample_rate // 2), 5))
    ratio, frequency = max((spectral_energy(candidate), candidate)
                           for candidate in range(max(1, frequency - 5), frequency + 6))
    return {"sample_count": len(values), "mean": mean,
            "rms": math.sqrt(energy / len(values)), "minimum": min(values),
            "maximum": max(values), "positive_crossings": len(crossings),
            "frequency_hz": frequency, "zero_crossing_frequency_hz": crossing_frequency,
            "fundamental_energy_fraction": ratio}


def analyze(folder):
    report = json.loads(folder.joinpath("report.json").read_text())
    rows = []
    for line in folder.joinpath("serial.txt").read_text().splitlines():
        if "HARDWARE_API " in line:
            try:
                rows.append(json.loads(line.split("HARDWARE_API ", 1)[1]))
            except ValueError:
                pass
    captured = [row for row in rows if row["api"] == "M5.Mic.record.pcm_bytes"]
    if len(captured) != 1:
        raise ValueError("one complete guest capture is required")
    output = bytes.fromhex(captured[0]["value"])
    with zipfile.ZipFile(folder / "evidence.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        fixture = manifest["audio_fixture"]
        source = archive.read("audio/microphone-source.pcm")
    if fixture.get("source_kind") != "generated-deterministic-tone":
        raise ValueError("this oracle requires the owned generated-tone fixture")
    sample_rate = fixture["sample_rate_hz"]
    expected = fixture["frequency_hz"]
    # Bound the host input analysis to the same duration as the guest capture.
    input_bytes = len(output) * fixture["channels"]
    source_metrics = signal_metrics(source[:input_bytes], sample_rate, fixture["channels"])
    output_metrics = signal_metrics(output, sample_rate)
    stopped_recording = any(row["api"] == "M5.Mic.isRecording"
                            and row["status"] == "API_ASSERTION_PASS"
                            and not row.get("value") for row in rows)
    checks = {"guest_completed": report["status"] == "EXECUTED",
              "requested_byte_count": len(output) == 3200,
              "recording_finished": stopped_recording,
              "input_matches_declared_tone": source_metrics["frequency_hz"] is not None
                  and abs(source_metrics["frequency_hz"] - expected) <= 2,
              "output_frequency_matches_input": output_metrics["frequency_hz"] is not None
                  and abs(output_metrics["frequency_hz"] - expected) <= 3,
              "nonzero_output": output_metrics["rms"] >= 100,
              "tone_dominates_output": output_metrics["fundamental_energy_fraction"] >= .65,
              "runtime_stopped": report.get("cleanup", {}).get("runtime_pid_gone") is True}
    result = {"schema_version": 1, "device": report["device_id"],
              "status": "DATA_PLANE_PASS" if all(checks.values()) else "FAIL",
              "oracle": "1600 signed mono samples complete; independent zero-crossing frequency and sinusoidal-energy checks match the same-session owned tone through the actual I2S/M5.Mic path. Gain/DC/clipping are permitted; byte-exact fidelity and physical hardware are outside this result.",
              "checks": checks, "input": source_metrics, "output": output_metrics,
              "fixture": fixture, "input_sha256": hashlib.sha256(source).hexdigest(),
              "output_sha256": hashlib.sha256(output).hexdigest(),
              "evidence": {"report": str(folder / "report.json"),
                           "serial": str(folder / "serial.txt"),
                           "session_id": report["session_id"],
                           "firmware_sha256": report["firmware_sha256"],
                           "runtime_binary_sha256": report.get("runtime_binary_sha256"),
                           "evidence_sha256": report["evidence_sha256"]}}
    folder.joinpath("pcm-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    folder.joinpath("microphone-output.pcm").write_bytes(output)
    wav_rows = [row for row in rows if row["api"] == "M5.Mic.recordWavFile.wav_bytes"]
    wav_chunks = [row for row in rows if row["api"] == "M5.Mic.recordWavFile.wav_chunk"]
    if wav_rows or wav_chunks:
        if wav_rows and (len(wav_rows) != 1 or wav_chunks):
            raise ValueError("one complete WAV capture is required")
        if wav_rows:
            wav_bytes = bytes.fromhex(wav_rows[0]["value"])
        else:
            payload = bytearray()
            for chunk in wav_chunks:
                if chunk["value"]["offset"] != len(payload):
                    raise ValueError("WAV chunk byte cursor is inconsistent")
                payload.extend(bytes.fromhex(chunk["value"]["hex"]))
            wav_bytes = bytes(payload)
        file_rows = [row for row in rows if row["api"] == "M5.Mic.recordWavFile.file" and row["status"] == "OBSERVED"]
        if not file_rows or file_rows[-1]["value"] != {"bytes": len(wav_bytes), "sha256": hashlib.sha256(wav_bytes).hexdigest()}:
            raise ValueError("retained WAV chunks do not match the guest file size/hash")
        with wave.open(io.BytesIO(wav_bytes)) as handle:
            wav_format = {"channels": handle.getnchannels(), "sample_width": handle.getsampwidth(),
                          "sample_rate_hz": handle.getframerate(), "frame_count": handle.getnframes()}
            wav_pcm = handle.readframes(handle.getnframes())
        metrics = signal_metrics(wav_pcm, wav_format["sample_rate_hz"], wav_format["channels"])
        wav_checks = {"guest_completed": checks["guest_completed"],
                      "declared_pcm_format": wav_format == {"channels": 1, "sample_width": 2, "sample_rate_hz": 16000, "frame_count": 16000},
                      "all_declared_bytes_present": len(wav_pcm) == 32000,
                      "frequency_matches_owned_input": abs(metrics["frequency_hz"] - expected) <= 3,
                      "tone_dominates_output": metrics["fundamental_energy_fraction"] >= .65,
                      "nonzero_output": metrics["rms"] >= 100,
                      "runtime_stopped": checks["runtime_stopped"]}
        wav_result = {"schema_version": 1, "device": report["device_id"],
                      "status": "DATA_PLANE_PASS" if all(wav_checks.values()) else "FAIL",
                      "oracle": "Host WAV parser validates RIFF/PCM header, one-second 16 kHz mono payload and independent spectral frequency/energy against the owned same-session tone; byte-exact fidelity and physical hardware are outside this result.",
                      "checks": wav_checks, "format": wav_format, "output": metrics,
                      "wav_sha256": hashlib.sha256(wav_bytes).hexdigest(),
                      "evidence": result["evidence"]}
        folder.joinpath("wav-oracle.json").write_text(json.dumps(wav_result, indent=2) + "\n")
        folder.joinpath("microphone-output.wav").write_bytes(wav_bytes)
        result["wav"] = wav_result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="+")
    args = parser.parse_args()
    passed = True
    for folder in args.run:
        row = analyze(folder)
        print(json.dumps({key: row[key] for key in ("device", "status", "checks", "output")}))
        passed = passed and row["status"] == "DATA_PLANE_PASS"
        if "wav" in row:
            print(json.dumps({key: row["wav"][key] for key in ("device", "status", "checks", "format", "output")}))
            passed = passed and row["wav"]["status"] == "DATA_PLANE_PASS"
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
