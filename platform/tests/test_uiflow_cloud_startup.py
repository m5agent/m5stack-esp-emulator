"""Cloud startup orchestration contracts; guest/cloud acceptance is separate."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import device_service as service_module
import test_device_service as fixtures
import uiflow_cloud_startup as cloud
from nvs_image import FIRST_ENTRY_OFFSET, NvsImageError, NvsU8, build_nvs_image, build_string_nvs_image


class CloudNvsTests(unittest.TestCase):
    def test_full_stock_settings_match_idf_generator_030(self):
        # esp-idf-nvs-partition-gen 0.3.0, official partition_nvs.csv field
        # order, ssid0=myssid, pswd0 empty, boot_option=data,u8,1, size 0x6000.
        image = cloud.cloud_nvs_image(0x6000)
        self.assertEqual(hashlib.sha256(image).hexdigest(), "370bb0fd9a8c0c226865982cb78fc87c850f32a5847707de6884879b277441ee")
        self.assertEqual(len(image), 0x6000)
        boot = next(image[offset:offset + 32] for offset in range(FIRST_ENTRY_OFFSET, 4096, 32)
                    if image[offset + 8:offset + 24].split(b"\0")[0] == b"boot_option")
        self.assertEqual((boot[0], boot[1], boot[2], boot[24]), (1, 1, 1, 1))

    def test_unsigned_byte_is_explicit_and_bounded(self):
        for value in (-1, 256, True, "1"):
            with self.subTest(value=value), self.assertRaises(NvsImageError):
                build_nvs_image(4096, {"uiflow": {"boot_option": NvsU8(value)}})
        with self.assertRaises(NvsImageError):
            build_nvs_image(4096, {"uiflow": {"boot_option": 1}})
        with self.assertRaises(NvsImageError):
            build_string_nvs_image(4096, {"uiflow": {"boot_option": NvsU8(1)}})


class CloudStartupTests(unittest.TestCase):
    def setUp(self):
        fixtures.DeviceServiceUnitTests.setUp(self)
        self.image = fixtures.build_flash_with_nvs_partition()
        self.reference = Path(self.tmp.name) / "stock-reference.bin"
        self.reference.write_bytes(self.image)
        self.sha = hashlib.sha256(self.image).hexdigest()
        self.service.specs["cores3"] = replace(self.service.specs["cores3"], reference_path=self.reference)
        self.service.max_per_device = 2
        self.admission = mock.patch.dict(cloud.CLOUD_REFERENCE_SHA256, {"cores3": self.sha})
        self.admission.start()
        self.addCleanup(self.admission.stop)

    def tearDown(self):
        fixtures.DeviceServiceUnitTests.tearDown(self)

    def request(self, **extra):
        return {"device_id": "cores3", "uiflow_startup": {"mode": "cloud", "reference_sha256": self.sha}, **extra}

    def create(self, **extra):
        with mock.patch.object(service_module.DeviceSession, "start"):
            return self.service.create_session(self.request(**extra))

    def assert_rejected(self, body, code):
        before = sorted(self.service.artifacts.root.iterdir())
        with self.assertRaises(service_module.ServiceError) as caught:
            self.service.create_session(body)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(before, sorted(self.service.artifacts.root.iterdir()))
        self.assertEqual(len(self.service._sessions), 0)

    def test_capability_is_hash_bound_and_not_a_generic_device_claim(self):
        row = self.service.get_device("cores3")
        self.assertEqual(row["uiflow_startup"], {"modes": ["cloud"], "reference_sha256": self.sha, "runtime": "qemu-wifi"})
        self.assertEqual(self.service.get_device("atoms3")["uiflow_startup"], {"modes": []})
        self.reference.write_bytes(self.image + b"changed")
        self.assertEqual(self.service.get_device("cores3")["uiflow_startup"], {"modes": []})

    def test_core2_cloud_capability_requires_the_radio_runtime(self):
        spec = replace(self.service.specs["core2"], reference_path=self.reference)
        unavailable = service_module.ServiceError("qemu_wifi_backend_unavailable", "test missing radio", 503)
        with mock.patch.dict(cloud.CLOUD_REFERENCE_SHA256, {"core2": self.sha}), mock.patch.object(cloud, "core2_radio_qemu_path", side_effect=unavailable):
            self.assertEqual(cloud.cloud_startup_capability(spec), {"modes": []})
            with self.assertRaises(service_module.ServiceError) as caught:
                cloud.verified_cloud_reference(spec, self.sha)
            self.assertEqual(caught.exception.code, "qemu_wifi_backend_unavailable")

    def test_pin_and_mode_conflicts_fail_before_side_effects(self):
        for value in (None, {}, {"mode": "cloud", "reference_sha256": "bad"},
                      {"mode": "cloud", "reference_sha256": self.sha, "unknown": True}):
            with self.subTest(value=value):
                self.assert_rejected(self.request(uiflow_startup=value), "invalid_uiflow_startup")
        self.assert_rejected(self.request(uiflow_startup={"mode": "cloud", "reference_sha256": "0" * 64}), "uiflow_startup_reference_mismatch")
        for field in ("program_mode", "program_transport", "firmware_id", "source", "nvs", "base_firmware_id", "expected_base_sha256", "uiflow_source_sha256"):
            with self.subTest(field=field):
                self.assert_rejected(self.request(**{field: None}), "uiflow_startup_conflict")
        self.assert_rejected(self.request(runtime="qemu"), "uiflow_startup_conflict")
        self.assert_rejected(self.request(network={"wifi_ssid": "another-ap"}), "uiflow_startup_conflict")
        self.assert_rejected(self.request(network={"http_fixture": True}), "uiflow_startup_conflict")
        for key in ("M5SW_WIFI_SSID", "M5SW_S3_WIFI_TRACE", "M5SW_CLASSIC_WIFI_AP"):
            with self.subTest(runtime_env=key):
                self.assert_rejected(self.request(runtime_env={key: "override"}), "uiflow_startup_conflict")

    def test_existing_network_policy_is_enforced_without_fallback(self):
        self.assert_rejected(self.request(network={"policy": {"isolation": "trusted-host", "egress": "allowlist"}}), "invalid_network_policy")
        deny = {"isolation": "namespace", "egress": "deny-all", "dns": "deny"}
        with mock.patch.object(service_module, "namespace_capability", return_value={"status": "UNAVAILABLE", "errors": ["test unavailable"], "checks": {}}):
            self.assert_rejected(self.request(network={"policy": deny}), "network_isolation_unavailable")

    def test_legal_restricted_policies_are_not_relaxed_for_cloud(self):
        policies = [
            {"isolation": "namespace", "egress": "deny-all", "dns": "deny"},
            {"isolation": "namespace", "egress": "allowlist", "dns": "deny",
             "allowed_endpoints": [{"protocol": "tcp", "address": "8.8.8.8", "port": 1883}]},
        ]
        for policy in policies:
            with self.subTest(policy=policy), mock.patch.object(service_module, "namespace_capability", return_value={"status": "PASS", "checks": {}, "errors": []}), mock.patch.object(service_module, "egress_capability", return_value={"status": "PASS", "checks": {}, "errors": []}):
                result = self.create(network={"policy": policy})
                session = self.service.get_session(result["session_id"])
                for key, value in policy.items():
                    self.assertEqual(session.network_config["policy"][key], value)
                self.assertFalse(session.network_config["http_fixture"])

    def test_idempotency_keeps_original_pin_and_reuses_generated_fixture(self):
        body = self.request(idempotency_key="original-cloud-body")
        with mock.patch.object(service_module.DeviceSession, "start"):
            first = self.service.create_session(body)
            second = self.service.create_session(self.request())
            self.assertEqual(first["source_artifacts"], second["source_artifacts"])
            self.reference.unlink()
            replay = self.service.create_session(body)
            self.assertEqual(replay["session_id"], first["session_id"])
            with self.assertRaises(service_module.ServiceError) as caught:
                self.service.create_session({**body, "uiflow_startup": {"mode": "cloud", "reference_sha256": "0" * 64}})
            self.assertEqual(caught.exception.code, "session_idempotency_conflict")

    def test_stock_pin_and_normalization_survive_history_reload(self):
        body = self.request(idempotency_key="cloud-history")
        with mock.patch.object(service_module.DeviceSession, "start"):
            original = self.service.create_session(body)
        session = self.service.get_session(original["session_id"])
        session.state = "stopped"
        session._persist_session()
        self.service.close_all()
        with mock.patch.object(service_module, "load_device_specs", return_value=self.service.specs):
            restored_service = service_module.DeviceService(state_dir=self.service.state_dir, max_sessions=2, max_per_device=2)
        try:
            restored = restored_service.get_session(session.id).snapshot()
            self.assertTrue(restored["restored"])
            self.assertEqual(restored["uiflow_startup"], original["uiflow_startup"])
            self.assertEqual(restored["firmware_provenance"], original["firmware_provenance"])
            with mock.patch.object(service_module.DeviceSession, "start") as start:
                replay = restored_service.create_session(body)
            start.assert_not_called()
            self.assertEqual(replay["session_id"], session.id)
            self.assertTrue(replay["idempotent_replay"])
        finally:
            restored_service.close_all()

    def test_cloud_reference_preserves_existing_manifest_and_firmware_bytes(self):
        # Importing this exact stock image through the public firmware API may
        # have already established a manifest used by a live-program base.
        data = self.image.ljust(self.service.specs["cores3"].flash_size, b"\xff")
        artifact = self.service.upload_artifact(data)
        manifest = {
            "schema_version": 1,
            "kind": "m5stack-firmware-manifest",
            "device_id": "cores3",
            "artifact": {
                "kind": "merged-flash", "file": "firmware.bin",
                "artifact_id": artifact["artifact_id"], "size": len(data),
                "sha256": artifact["sha256"],
            },
            "target": {
                "soc": "esp32s3", "chip_id": 9, "flash_size": len(data),
                "psram_size": 8 << 20, "partition_table": {}, "application": None,
            },
            "security": {
                "secure_boot": "unknown", "flash_encryption": "unknown",
                "efuse": "not-included", "secure_version": 0,
            },
            "provenance": {"importer": "test", "source_format": "merged-bin"},
            "resources": {},
            "capabilities": {"required": ["wifi"], "optional": []},
            "validation": {"status": "PASS", "errors": [], "warnings": []},
        }
        fixtures.seal_manifest(manifest)
        existing = self.service.create_firmware({
            "device_id": "cores3", "kind": "manifest", "manifest": manifest,
        })
        metadata_path = self.service.firmware._meta(existing["firmware_id"])
        firmware_path = self.service.firmware.path(existing["firmware_id"])
        metadata_before = metadata_path.read_bytes()
        firmware_before = firmware_path.read_bytes()
        result = self.create()
        self.assertEqual(result["firmware_sha256"], existing["firmware_id"])
        self.assertEqual(self.service.firmware.get(existing["firmware_id"]), existing)
        self.assertEqual(metadata_path.read_bytes(), metadata_before)
        self.assertEqual(firmware_path.read_bytes(), firmware_before)

    def test_cloud_startup_changes_only_session_nvs_and_retains_identity(self):
        body = self.request(idempotency_key="cloud-request-original")
        body_before = json.loads(json.dumps(body))
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            result = self.service.create_session(body)
            replay = self.service.create_session(body)
        start.assert_called_once()
        self.assertEqual(body, body_before)
        self.assertEqual(replay["session_id"], result["session_id"])
        self.assertTrue(replay["idempotent_replay"])
        session = self.service.get_session(result["session_id"])
        self.assertEqual(result["uiflow_startup"], body["uiflow_startup"])
        normalized = self.image.ljust(session.spec.flash_size, b"\xff")
        normalized_sha = hashlib.sha256(normalized).hexdigest()
        self.assertEqual(result["firmware_sha256"], normalized_sha)
        self.assertNotEqual(normalized_sha, self.sha)
        self.assertEqual(session.firmware_path.read_bytes(), normalized)
        self.assertEqual(result["firmware_provenance"]["metadata"], {
            "reference_sha256": self.sha, "reference_size": len(self.image),
            "normalized_sha256": normalized_sha, "normalized_size": session.spec.flash_size,
            "normalization": "trailing-ff-padding",
        })
        self.assertEqual(result["firmware_source"], "reference")
        self.assertEqual(result["runtime"], "qemu-wifi")
        self.assertIsNone(session.program_transport)
        self.assertFalse(session.program_bootstrap)
        self.assertFalse(session.network_config["http_fixture"])
        self.assertTrue(session.network_config["capture_pcap"])
        self.assertEqual(session.network_config["wifi_ssid"], "myssid")
        self.assertEqual(session.network_config["wifi_password"], "")
        self.assertEqual(session.network_config["policy"]["isolation"], "trusted-host")
        self.assertEqual(session._session_record()["uiflow_startup"], body["uiflow_startup"])
        self.assertEqual(len(session.source_artifacts), 3)
        self.assertEqual(session.source_artifacts[0], self.sha)
        self.assertEqual(session.source_artifacts[1], normalized_sha)
        fixture = self.service.artifacts.path(session.source_artifacts[2]).read_bytes()
        self.assertEqual(fixture, cloud.cloud_nvs_image(0x6000))
        session.virtual_flash = session.dir / "virtual-flash.bin"
        padded = self.image.ljust(session.spec.flash_size, b"\xff")
        session.virtual_flash.write_bytes(padded)
        session.flash_info = {"transport": "test-host-image"}
        session._apply_nvs_fixture()
        actual = session.virtual_flash.read_bytes()
        self.assertEqual(actual[:0x9000], padded[:0x9000])
        self.assertEqual(actual[0x9000:0xf000], fixture)
        self.assertEqual(actual[0xf000:], padded[0xf000:])
        self.assertEqual(self.reference.read_bytes(), self.image)
        self.assertFalse(session.nvs_info["source_artifact_modified"])

    def test_explicit_capture_opt_out_and_policy_survive(self):
        result = self.create(network={"capture_pcap": False, "policy": {"isolation": "trusted-host", "egress": "native", "dns": "slirp"}})
        session = self.service.get_session(result["session_id"])
        self.assertFalse(session.network_config["capture_pcap"])
        self.assertEqual(session.network_config["policy"]["egress"], "native")


if __name__ == "__main__":
    unittest.main()
