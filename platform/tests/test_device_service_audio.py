"""Verify media validation and Cardputer session ownership without a runtime cache."""

import hashlib
import io
import json
import math
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
import wave

from device_service import DeviceSession
from device_service_audio import WAV_MAX_BYTES, decode_cardputer_wave, pcm_metrics
from device_service_errors import ServiceError
from runtime_acl import RuntimeACL


def make_wave(data, rate=16000, channels=1):
    contents = io.BytesIO()
    with wave.open(contents, "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(data)
    return contents.getvalue()


class MediaValidationTests(unittest.TestCase):
    def test_wav_preserves_signed_little_endian_pcm_and_checks_full_frames(self):
        raw = struct.pack("<hhh", -32768, 0, 32767)
        valid = make_wave(raw)
        self.assertEqual(decode_cardputer_wave(valid), raw)
        for bad in (valid[:-2], make_wave(raw, rate=22050), make_wave(raw * 2, channels=2)):
            with self.subTest(size=len(bad)), self.assertRaisesRegex(ServiceError, "16 kHz"):
                decode_cardputer_wave(bad)
        with self.assertRaises(ServiceError) as large:
            decode_cardputer_wave(b"x" * (WAV_MAX_BYTES + 1))
        self.assertEqual(large.exception.status, 413)

    def test_pcm_tracks_tone_and_constant_signal(self):
        tone = b"".join(
            struct.pack("<h", int(10000 * math.sin(math.tau * 660 * i / 48000)))
            for i in range(8192)
        )
        measured = pcm_metrics(tone, 48000)
        self.assertAlmostEqual(measured["dominant_frequency_hz"], 660, delta=2)
        self.assertAlmostEqual(measured["rms"], 7071, delta=20)
        self.assertEqual(measured["spectrum_frames"], 8192)
        self.assertIsNone(pcm_metrics(bytes(1024), 48000)["dominant_frequency_hz"])
        self.assertEqual(pcm_metrics(struct.pack("<h", -32768), 16000)["peak"], 32768)


class NativeAudioSessionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.session = DeviceSession.__new__(DeviceSession)
        self.session.id = "owned"
        self.session.firmware_sha = "a" * 64
        self.session.spec = SimpleNamespace(id="cardputer")
        self.session.state = "running"
        self.session.runtime = "qemu"
        self.session.runtime_env = {}
        self.session._lifecycle_lock = threading.RLock()
        self.session._lock = threading.RLock()
        self.session._stop_event = threading.Event()
        self.session._process_identity_matches = lambda: True
        self.session._record_event = lambda *args, **kwargs: None
        self.session.speaker_pcm = root / "speaker.pcm"
        self.session.microphone_source_pcm = root / "microphone-source.pcm"
        self.session.audio_fixture_path = root / "audio-fixture.json"
        self.artifact = root / "test.wav"
        self.session.service = SimpleNamespace(artifacts=SimpleNamespace(path=lambda _: self.artifact))

    def test_replace_keeps_previous_fixture_after_invalid_or_stopped_request(self):
        raw = b"\x20\x00\x10\x00" * 80
        wav = make_wave(raw)
        self.artifact.write_bytes(wav)
        artifact_id = hashlib.sha256(wav).hexdigest()
        receipt = self.session.audio_inject({"artifact_id": artifact_id})
        self.assertEqual(receipt["status"], "staged")
        self.assertEqual(receipt["applies_on"], "next_i2s_rx_start")
        self.assertEqual(self.session.microphone_source_pcm.read_bytes(), raw)
        self.assertEqual(json.loads(self.session.audio_fixture_path.read_bytes()), receipt)
        with self.assertRaises(ServiceError) as malformed:
            self.session.audio_inject({"artifact_id": 5})
        self.assertEqual(malformed.exception.code, "invalid_audio_fixture")
        self.session.state = "stopped"
        with self.assertRaises(ServiceError) as stopped:
            self.session.audio_inject({"artifact_id": artifact_id})
        self.assertEqual(stopped.exception.code, "audio_session_not_running")
        self.assertEqual(self.session.microphone_source_pcm.read_bytes(), raw)

    def test_capture_window_is_hashed_and_runtime_permissions_are_independent(self):
        self.session.speaker_pcm.write_bytes(b"12345678")
        data, receipt = self.session.audio_capture("pcm", 2, 4, None)
        self.assertEqual(data, b"3456")
        self.assertEqual(receipt["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual((receipt["next_offset"], receipt["observed_bytes"]), (6, 8))
        with self.assertRaises(ServiceError) as invalid:
            self.session.audio_capture("metrics", 1, 4, 48000)
        self.assertEqual(invalid.exception.code, "invalid_audio_layout")
        self.session.service.runtime_acl = RuntimeACL.from_document({
            "schema_version": 1, "devices": {"cardputer": {"allow": ["audio.read"]}},
        })
        self.assertEqual(self.session.audio_capture("pcm", 2, 4, None)[0], data)
        with self.assertRaises(ServiceError) as forbidden:
            self.session.audio_inject({"artifact_id": "a" * 64})
        self.assertEqual(forbidden.exception.status, 403)
        self.assertEqual(forbidden.exception.extra["operation"], "audio.inject")

    def test_unit_media_has_its_own_stage_and_fixed_clock_capture(self):
        session = self.session
        session.spec.id = "dial"
        session.dir = session.speaker_pcm.parent
        session.unit_audio_pcm = session.dir / "unit-audio.pcm"
        session.unit_audio_fixture = session.dir / "unit-audio-fixture.json"
        raw = b"\x02\x00\xfe\xff" * 2048
        wav = make_wave(raw)
        self.artifact.write_bytes(wav)
        artifact_id = hashlib.sha256(wav).hexdigest()
        session.units = [{"id": "player", "media_wav_artifact_ids": [artifact_id]}]
        env = {"M5SW_UNIT_AUDIO_PCM_DIR": "/old", "M5SW_UNIT_AUDIO_PCM_OUT": "/old"}
        session._unit_audio_environment(env)
        self.assertEqual(Path(env["M5SW_UNIT_AUDIO_PCM_DIR"], "1.pcm").read_bytes(), raw)
        self.assertEqual(Path(env["M5SW_UNIT_AUDIO_PCM_OUT"]), session.unit_audio_pcm)
        session.unit_audio_pcm.write_bytes(raw + b"\x10")
        data, metrics = session.audio_capture("metrics", 0, len(raw), None, source="unit")
        self.assertIsNone(data)
        self.assertEqual(metrics["observed_bytes"], len(raw))
        self.assertEqual(metrics["sample_rate_hz"], 16000)
        self.assertEqual(metrics["source"], "native_n9301_unit")
        self.assertEqual(metrics["unit_id"], "player")
        self.assertEqual(metrics["rms"], 2)
        for raw_source, rate, code in (
            ("speaker", None, "audio_unsupported"),
            ("unit", 48000, "invalid_audio_layout"),
        ):
            with self.assertRaises(ServiceError) as error:
                session.audio_capture("metrics", 0, len(raw), rate, source=raw_source)
            self.assertEqual(error.exception.code, code)
        session.service.runtime_acl = RuntimeACL.from_document({
            "schema_version": 1, "devices": {"dial": {"allow": ["serial.read"]}},
        })
        with self.assertRaises(ServiceError) as forbidden:
            session.audio_capture("pcm", 0, len(raw), None, source="unit")
        self.assertEqual(forbidden.exception.status, 403)
        session.units = []
        session._unit_audio_environment(env)
        self.assertFalse(env)
