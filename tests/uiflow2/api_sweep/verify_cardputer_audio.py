#!/usr/bin/env python3
"""Verify Cardputer audio using an independent guest UART and native DMA capture."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import zipfile

from verify_mic_recording import dominant_frequency


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def unpack_pcm(raw):
    require(raw and len(raw) % 2 == 0, "missing or misaligned s16le audio")
    return struct.unpack(f"<{len(raw) // 2}h", raw)


def metrics(raw, samples):
    return {
        "bytes": len(raw),
        "samples": len(samples),
        "nonzero_samples": sum(bool(sample) for sample in samples),
        "rms_s16": round(math.sqrt(sum(sample * sample for sample in samples) / len(samples)), 3),
        "pcm_sha256": sha256(raw).hexdigest(),
    }


def verify(run_dir, mode):
    report = json.loads((run_dir / "report.json").read_text())
    stopped = json.loads((run_dir / "stopped.json").read_text())
    lines = (run_dir / "serial.txt").read_text().splitlines()
    for marker in (
        f"NATIVE_AUDIO_MODE {mode}",
        "NATIVE_AUDIO_SPEAKER_CONFIG 48000 False 1",
        "NATIVE_AUDIO_SPEAKER_STARTED 12800",
        "NATIVE_AUDIO_SPEAKER_FINISHED",
        "NATIVE_AUDIO_FINISHED",
    ):
        require(lines.count(marker) == 1, f"missing or repeated marker {marker}")
    require(not any(line.startswith(("NATIVE_AUDIO_MIC_ERROR", "NATIVE_AUDIO_SPEAKER_ERROR"))
                    for line in lines), "guest audio API failure")
    mic_pcm = bytearray()
    for line in lines:
        if line.startswith("NATIVE_AUDIO_MIC "):
            _, offset, hex_pcm = line.split()
            require(int(offset) == len(mic_pcm), "missing or out-of-order guest PCM")
            mic_pcm.extend(bytes.fromhex(hex_pcm))
    mic_samples = unpack_pcm(mic_pcm)
    require(len(mic_samples) == 3200, "incomplete guest microphone capture")

    with zipfile.ZipFile(run_dir / "evidence.zip") as bundle:
        require(bundle.testzip() is None, "corrupt evidence ZIP")
        manifest = json.loads(bundle.read("manifest.json"))
        fixture = manifest["audio_fixture"]
        speaker_pcm = bundle.read("audio/speaker.pcm")
        require(len(speaker_pcm) == manifest["audio"]["bytes"]
                and sha256(speaker_pcm).hexdigest() == manifest["audio"]["sha256"],
                "speaker PCM manifest mismatch")
        source_member = "audio/microphone-source.pcm"
        if mode == "tone":
            source = bundle.read(source_member)
            require(fixture == {
                "source_kind": "generated-deterministic-tone", "input_override": False,
                "sample_rate_hz": 16000, "channels": 1, "sample_format": "s16le",
                "frequency_hz": 440, "duration_seconds": 1,
            }, "unexpected generated fixture metadata")
            require(len(source) == 32000 and manifest["device_data"][source_member] == {
                "bytes": len(source), "sha256": sha256(source).hexdigest(),
            }, "generated fixture manifest mismatch")
            fixture["pcm_sha256"] = sha256(source).hexdigest()
        else:
            require(fixture == {"source_kind": "explicit-diagnostic-override", "input_override": True}
                    and source_member not in bundle.namelist(),
                    "explicit local input leaked into evidence")

    speaker_samples = unpack_pcm(speaker_pcm)
    mic = metrics(mic_pcm, mic_samples)
    speaker = metrics(speaker_pcm, speaker_samples)
    mic["sample_rate_hz"] = 16000
    speaker["sample_rate_hz"] = 48000
    speaker["trailing_zero_samples"] = next(
        (index for index, value in enumerate(reversed(speaker_samples)) if value),
        len(speaker_samples),
    )
    speaker["dominant_hz"] = round(dominant_frequency(speaker_samples[:4096], 48000, 660), 3)
    require(speaker["rms_s16"] > 100 and abs(speaker["dominant_hz"] - 660) < 5,
            "native speaker capture lacks the expected tone")
    if mode == "tone":
        mic["dominant_hz"] = round(dominant_frequency(mic_samples, 16000, 440), 3)
        require(mic["rms_s16"] > 100 and abs(mic["dominant_hz"] - 440) < 5,
                "guest microphone capture lacks the expected tone")
        require(38000 <= speaker["nonzero_samples"] <= 38500,
                "native PCM does not contain the complete 0.8 s tone")
    else:
        require(mic["nonzero_samples"] == 0 and mic["rms_s16"] == 0,
                "silent injection produced nonzero guest samples")
        require(4700 <= speaker["nonzero_samples"] <= 4900
                and speaker["trailing_zero_samples"] >= 33000,
                "native speaker pilot or silent tail is incomplete")

    cleanup = report["cleanup"]
    require(report["status"] == "EXECUTED" and cleanup["terminal_state"] == "stopped"
            and cleanup["history_preserved"] and cleanup["runtime_pid_gone"]
            and stopped["flash_retained"] is False, "guest cleanup evidence is incomplete")
    keys = (
        "device_id", "base_sha256", "firmware_sha256", "runtime_binary_sha256",
        "source_sha256", "fixture_sha256", "evidence_sha256",
    )
    return {
        "status": "PASS",
        **{key: report[key] for key in keys},
        "mode": mode,
        "microphone_fixture": fixture,
        "guest_microphone": mic,
        "native_speaker": speaker,
        "cleanup": {
            "terminal_state": "stopped", "history_preserved": True,
            "runtime_pid_gone": True, "flash_retained": False,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("mode", choices=("tone", "silence"))
    args = parser.parse_args()
    print(json.dumps(verify(args.run_dir, args.mode), indent=2))
