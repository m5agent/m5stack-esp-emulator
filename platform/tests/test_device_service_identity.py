"""Identity admission/storage/lifecycle tests; live cloud acceptance is separate."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import device_service as service_module
from device_service_errors import ServiceError
from device_service_identity import DeviceIdentityStore, parse_device_identity, restore_device_identity
import test_device_service as fixtures
import test_uiflow_cloud_startup as cloud_fixtures


class IdentityStoreTests(unittest.TestCase):
    def test_strict_request_and_normalization(self):
        self.assertIsNone(parse_device_identity({}, device_id="cores3", cloud=False))
        self.assertEqual(parse_device_identity({}, device_id="cores3", cloud=True), {"key": "uiflow-cloud-cores3"})
        self.assertEqual(parse_device_identity({"device_identity": {"mac": "02123456789A"}}, device_id="cores3", cloud=False), {"mac": "02:12:34:56:78:9a"})
        for value in (None, [], {}, {"key": "x", "mac": "02:12:34:56:78:9a"}, {"other": "x"}, {"key": "../x"}, {"key": "x" * 65}, {"key": "云"}, {"mac": "01:12:34:56:78:9a"}, {"mac": "00:00:00:00:00:00"}, {"mac": "ff:ff:ff:ff:ff:ff"}, {"mac": "02-12-34-56-78-9a"}):
            with self.subTest(value=value), self.assertRaises(ServiceError) as caught:
                parse_device_identity({"device_identity": value}, device_id="cores3", cloud=False)
            self.assertEqual(caught.exception.code, "invalid_device_identity")

    def test_private_durable_store_and_failed_atomic_update(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "identities.json"
            store = DeviceIdentityStore(path)
            first = store.resolve({"key": "board"}, "cores3")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(int(first["mac"][:2], 16) & 3, 2)
            before = path.read_bytes()
            with mock.patch("device_service_identity.os.replace", side_effect=OSError("write failed")), self.assertRaises(ServiceError):
                store.resolve({"key": "another"}, "cores3")
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn("another", store.entries)
            self.assertEqual(list(Path(root).glob("*.tmp")), [])
            self.assertEqual(DeviceIdentityStore(path).resolve({"key": "board"}, "cores3"), first)
            with self.assertRaises(ServiceError) as caught:
                store.resolve({"key": "board"}, "core2")
            self.assertEqual(caught.exception.code, "device_identity_device_mismatch")
            store.resolve({"mac": "02:12:34:56:78:9a"}, "cores3")
            self.assertEqual(path.read_bytes(), before)

    def test_corruption_does_not_silently_rotate_identity(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "identities.json"
            for record in ("{", '{"schema_version":2,"entries":{}}', '{"schema_version":1,"entries":{"x":{"device_id":"cores3","mac":"ff:ff:ff:ff:ff:ff"}}}'):
                path.write_text(record)
                with self.assertRaises(ServiceError) as caught:
                    DeviceIdentityStore(path)
                self.assertEqual(caught.exception.code, "device_identity_store_invalid")
                self.assertEqual(path.read_text(), record)
        for record in ({"source": "unknown", "mac": "02:12:34:56:78:9a"}, {"source": "persistent-fixture", "key": "bad/key", "mac": "02:12:34:56:78:9a"}):
            with self.assertRaises(ServiceError):
                restore_device_identity(record)


class IdentitySessionTests(unittest.TestCase):
    def setUp(self):
        fixtures.DeviceServiceUnitTests.setUp(self)
        self.service.max_sessions = 8
        self.service.max_per_device = 8

    tearDown = fixtures.DeviceServiceUnitTests.tearDown
    _stopped_session = fixtures.DeviceServiceUnitTests._stopped_session

    def test_identity_capability_is_explicit_and_device_scoped(self):
        for device_id in ("cores3", "core2", "nanoc6"):
            row = self.service.get_device(device_id)
            self.assertEqual(row["device_identity"], {
                "schema_version": 1, "selectors": ["key", "mac"],
                "runtimes": ["qemu", "qemu-wifi", "qemu-ble", "qemu-unified"],
                "cloud_default": "persistent-key",
            })
        for device_id in ("tab5", "cardputer-zero", "nesso-n1"):
            capability = self.service.get_device(device_id)["device_identity"]
            self.assertEqual(capability["selectors"], [])
            self.assertEqual(capability["runtimes"], [])
            self.assertIsNone(capability["cloud_default"])

    def create(self, identity=None, **extra):
        payload = {"device_id": "cores3", **extra}
        if identity is not None:
            payload["device_identity"] = identity
        with mock.patch.object(service_module.DeviceSession, "start"):
            return self.service.create_session(payload)

    def test_stable_identity_and_legacy_concurrency(self):
        first = self.create({"key": "board"})
        self.service.get_session(first["session_id"]).stop()
        second = self.create({"key": "board"})
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertEqual(first["device_identity"], second["device_identity"])
        a, b = self.create(), self.create()
        self.assertNotIn("device_identity", a)
        self.assertNotIn("device_identity", b)
        self.assertNotEqual(service_module.qemu_station_mac(a["session_id"]), service_module.qemu_station_mac(b["session_id"]))

    def test_concurrent_claim_only_admits_one_and_replay_precedes_conflict(self):
        barrier = threading.Barrier(2)
        def attempt():
            barrier.wait()
            try:
                return self.service.create_session({"device_id": "cores3", "device_identity": {"key": "board"}})
            except ServiceError as error:
                return error.code
        with mock.patch.object(service_module.DeviceSession, "start"), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertIn("device_identity_in_use", results)
        first = self.create({"key": "another"}, idempotency_key="same-request")
        replay = self.create({"key": "another"}, idempotency_key="same-request")
        self.assertEqual(first["session_id"], replay["session_id"])
        self.assertTrue(replay["idempotent_replay"])
        with self.assertRaises(ServiceError) as caught:
            self.create({"key": "changed"}, idempotency_key="same-request")
        self.assertEqual(caught.exception.code, "session_idempotency_conflict")

    def test_mac_aliases_stopping_and_failed_cleanup_are_fenced(self):
        result = self.create({"key": "board"})
        session = self.service.get_session(result["session_id"])
        mac = result["device_identity"]["mac"]
        for state in ("provisioning", "stopping", "failed"):
            session.state = state
            with self.subTest(state=state), self.assertRaises(ServiceError) as caught:
                self.create({"mac": mac})
            self.assertEqual(caught.exception.code, "device_identity_in_use")
            self.assertNotIn(mac, caught.exception.message)
        session.stop()
        self.assertEqual(self.create({"mac": mac})["device_identity"], {"source": "explicit-mac", "mac": mac})

    def test_constructor_idempotency_and_start_failures_release_claim(self):
        for failure in ("constructor", "idempotency", "start"):
            target = (mock.patch.object(service_module.DeviceSession, "__init__", side_effect=RuntimeError("construction failed")) if failure == "constructor" else
                      mock.patch.object(self.service, "_remember_session_idempotency_locked", side_effect=OSError("storage failed")) if failure == "idempotency" else
                      mock.patch.object(service_module.DeviceSession, "start", side_effect=RuntimeError("thread failed")))
            with self.subTest(failure=failure), target, self.assertRaises((RuntimeError, OSError)):
                self.service.create_session({"device_id": "cores3", "device_identity": {"key": failure}})
            result = self.create({"key": failure})
            self.service.get_session(result["session_id"]).stop()

    def test_failed_stop_does_not_release_live_identity(self):
        result = self.create({"key": "board"})
        session = self.service.get_session(result["session_id"])
        with mock.patch.object(session, "_terminate_runtime", side_effect=RuntimeError("termination pending")), self.assertRaises(RuntimeError):
            session.stop()
        self.assertEqual(session.state, "stopping")
        with self.assertRaises(ServiceError) as caught:
            self.create({"key": "board"})
        self.assertEqual(caught.exception.code, "device_identity_in_use")
        session.stop()
        self.create({"key": "board"})

    def test_invalid_request_does_not_create_persistent_identity(self):
        with self.assertRaises(ServiceError):
            self.create({"key": "invalid"}, ttl_seconds=1)
        self.assertNotIn("invalid", self.service.device_identities.entries)
        self.assertFalse(self.service.device_identities.path.exists())

    def test_restart_retains_exact_identity_and_history(self):
        result = self.create({"key": "board"})
        session = self.service.get_session(result["session_id"])
        session.stop()
        self.service.close_all()
        with mock.patch.object(service_module, "load_device_specs", return_value=self.service.specs):
            restarted = service_module.DeviceService(state_dir=self.service.state_dir)
        try:
            restored = restarted.get_session(session.id)
            self.assertEqual(restored.device_identity, result["device_identity"])
            with mock.patch.object(service_module.DeviceSession, "start"):
                new = restarted.create_session({"device_id": "cores3", "device_identity": {"key": "board"}})
            self.assertEqual(new["device_identity"], result["device_identity"])
        finally:
            restarted.close_all()

    def test_unsupported_driver_and_network_lane_fail_closed(self):
        for driver in ("none", "unknown.efuse"):
            self.service.specs["cores3"] = replace(self.service.specs["cores3"], efuse_driver=driver)
            with self.assertRaises(ServiceError) as caught:
                self.create({"key": "board"})
            self.assertEqual(caught.exception.code, "unsupported_device_identity")
        spec = self.service.specs["cores3"]
        from device_service_identity import validate_identity_runtime
        for runtime, monitor in (("network", False), ("qemu-wifi", True)):
            with self.assertRaises(ServiceError):
                validate_identity_runtime(spec, runtime, monitor)

    def test_launch_uses_same_mac_for_nic_and_efuse(self):
        session = self._stopped_session()
        session.spec = self.service.specs["core2"]
        session.runtime = "qemu-wifi"
        session.network_config = {"profile": "core2-openmac", "nic": "misc.esp32_wifi"}
        session.state = "booting"
        session.device_identity = {"source": "explicit-mac", "mac": "02:12:34:56:78:9a"}
        class Captured(Exception):
            pass
        with mock.patch.object(session, "_prepare_microphone_tone"), mock.patch.object(service_module, "core2_radio_qemu_path", return_value=session.spec.qemu), mock.patch.object(service_module.subprocess, "Popen", side_effect=Captured) as launch:
            with self.assertRaises(Captured):
                session._launch()
        command = launch.call_args.args[0]
        self.assertIn("mac=02:12:34:56:78:9a", command[command.index("-nic") + 1])
        self.assertEqual((session.dir / "efuse.bin").read_bytes()[4:11], bytes.fromhex("9a7856341202d2"))
        self.assertEqual(session.efuse_identity["mac"], session.device_identity["mac"])


class CloudIdentityTests(unittest.TestCase):
    setUp = cloud_fixtures.CloudStartupTests.setUp
    tearDown = cloud_fixtures.CloudStartupTests.tearDown
    request = cloud_fixtures.CloudStartupTests.request
    create = cloud_fixtures.CloudStartupTests.create

    def test_cloud_default_is_stable_and_explicit_identity_is_honored(self):
        first = self.create()
        self.assertEqual(first["device_identity"]["key"], "uiflow-cloud-cores3")
        with self.assertRaises(ServiceError) as caught:
            self.create()
        self.assertEqual(caught.exception.code, "device_identity_in_use")
        self.service.get_session(first["session_id"]).stop()
        second = self.create()
        self.assertEqual(second["device_identity"], first["device_identity"])
        explicit = self.create(device_identity={"mac": "02:12:34:56:78:9a"})
        self.assertEqual(explicit["device_identity"]["source"], "explicit-mac")


if __name__ == "__main__":
    unittest.main()
