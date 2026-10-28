"""Plain CoreS3/Cardputer audio completion, owned fixtures and ZIP contracts."""

import hashlib
import io
import json
from pathlib import Path
import struct
import uuid
import unittest
import zipfile

from device_service import DeviceSession
import test_device_service as service_tests


class PlainQemuAudioTests(unittest.TestCase):
    setUp = service_tests.DeviceServiceUnitTests.setUp
    tearDown = service_tests.DeviceServiceUnitTests.tearDown

    def session(self, device, *, runtime="qemu", runtime_env=None):
        spec = self.service.specs[device]
        instance = DeviceSession(
            self.service, session_id=uuid.uuid4().hex, spec=spec,
            firmware_id="a" * 64, firmware_path=spec.reference_path,
            firmware_sha="a" * 64, firmware_source="reference",
            source_artifacts=[], ttl_seconds=60, ready_marker=None,
            ready_timeout=30, ready_conditions=None, runtime=runtime,
            runtime_env=runtime_env or {}, network_config={},
        )
        instance.state = "stopped"
        return instance

    def test_default_audio_completion_and_paths_are_owned_per_session(self):
        first = self.session("cores3")
        second = self.session("cardputer-adv")
        paths = []
        for session in (first, second):
            environment = {
                "M5SW_I2S_DMA_IRQ": "0",
                "M5SW_I2S_PCM_FILE": "/unrelated-session/speaker.pcm",
                "M5SW_I2S_RX_PCM_FILE": "/unrelated-session/microphone.pcm",
            }
            session._plain_qemu_audio_environment(environment)
            self.assertEqual(environment["M5SW_I2S_DMA_IRQ"], "1")
            self.assertEqual(Path(environment["M5SW_I2S_PCM_FILE"]).parent, session.dir)
            self.assertEqual(Path(environment["M5SW_I2S_RX_PCM_FILE"]).parent, session.dir)
            paths.append(environment["M5SW_I2S_PCM_FILE"])
        self.assertNotEqual(*paths)

    def test_unvalidated_devices_and_other_runtimes_do_not_inherit_support(self):
        for device, runtime in (("atoms3r", "qemu"), ("core2", "qemu"), ("cores3", "qemu-unified")):
            with self.subTest(device=device, runtime=runtime):
                environment = {}
                self.session(device, runtime=runtime)._plain_qemu_audio_environment(environment)
                self.assertEqual(environment, {})

    def test_explicit_diagnostic_overrides_remain_explicit_and_are_not_archived_as_fixture(self):
        session = self.session("cores3", runtime_env={"M5SW_I2S_DMA_IRQ": "0", "M5SW_I2S_RX_PCM_FILE": "/explicit-diagnostic/input.pcm"})
        environment = {}
        session._plain_qemu_audio_environment(environment)
        self.assertEqual(environment["M5SW_I2S_DMA_IRQ"], "0")
        self.assertEqual(environment["M5SW_I2S_RX_PCM_FILE"], "/explicit-diagnostic/input.pcm")
        session.microphone_source_pcm.write_bytes(b"not the selected input")
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"manifest"}))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["audio_fixture"]["source_kind"], "explicit-diagnostic-override")
            self.assertEqual(set(manifest["audio_fixture"]), {"source_kind", "input_override"})
            self.assertNotIn("audio/microphone-source.pcm", archive.namelist())

    def test_real_fixture_generation_and_zip_preserve_pcm_bytes_and_provenance(self):
        session = self.session("cardputer-adv")
        session._prepare_microphone_tone(session.spec.id, "plain_qemu_audio_inputs_prepared")
        source = session.microphone_source_pcm.read_bytes()
        samples = struct.unpack("<16000h", source)
        self.assertEqual(len(source), 32000)
        self.assertEqual(samples[0], 0)
        self.assertGreater(max(samples), 11000)
        self.assertLess(min(samples), -11000)
        speaker = b"\x00\x00\xff\x7f" * 64
        session.speaker_pcm.write_bytes(speaker)
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"manifest"}))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("audio/microphone-source.pcm"), source)
            self.assertEqual(archive.read("audio/speaker.pcm"), speaker)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["audio"]["sha256"], hashlib.sha256(speaker).hexdigest())
            self.assertEqual(manifest["device_data"]["audio/microphone-source.pcm"]["sha256"], hashlib.sha256(source).hexdigest())
            self.assertEqual(manifest["audio_fixture"]["source_kind"], "generated-deterministic-tone")
            self.assertEqual(manifest["audio_fixture"]["sample_rate_hz"], 16000)
            self.assertTrue(any(event["event"] == "plain_qemu_audio_inputs_prepared" for event in session.events))

    def test_cores3_fixture_has_two_identical_interleaved_input_channels(self):
        session = self.session("cores3")
        session._prepare_microphone_tone("CoreS3", "plain_qemu_audio_inputs_prepared", channels=2)
        samples = struct.unpack("<32000h", session.microphone_source_pcm.read_bytes())
        self.assertEqual(samples[::2], samples[1::2])
        self.assertGreater(max(samples), 11000)
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"manifest"}))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["audio_fixture"]["channels"], 2)


if __name__ == "__main__":
    unittest.main()
