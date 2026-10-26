"""UIFlow source API integration; real LittleFS, no guest/QEMU execution."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
from urllib.error import HTTPError
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

import device_service as service_module
import test_device_service as service_fixtures
import test_uiflow_source as source_fixtures
from serve import Handler
from uiflow_source import UIFlowSourceError, build_uiflow_source_image

SUPPORTED = ("cores3", "atoms3r", "sticks3", "stopwatch")
SENTINEL = "UIFLOW_SOURCE_CONTENT_MUST_NOT_APPEAR_IN_LIST_METADATA_20261026"
CALLER_FILES = {
    "main.py": f"print('{SENTINEL}')\n",
    "pkg/__init__.py": "",
    "pkg/sensor.py": "value = '温度'\n",
}


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(files):
    return json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def source_reference():
    image = bytearray(source_fixtures.real_base() if source_fixtures.littlefs else source_fixtures.base_image())
    esp = service_fixtures.build_flash()
    image[:0x8000] = esp[:0x8000]
    image[0x10000:0x12000] = esp[0x10000:0x12000]
    return bytes(image)


def install_reference(service, directory):
    path = Path(directory) / "admitted-uiflow2-reference.bin"
    path.write_bytes(source_reference())
    specs = dict(service.specs)
    for device_id in SUPPORTED:
        specs[device_id] = replace(specs[device_id], flash_size=source_fixtures.FLASH_SIZE, reference_path=path)
    service.specs = specs
    service.firmware.specs = specs
    return path


class ServiceFixture:
    def setUp(self):
        # Reuse existing service lifecycle, hermetic runtime paths and worker setup.
        service_fixtures.DeviceServiceUnitTests.setUp(self)
        self.reference = install_reference(self.service, self.tmp.name)

    def tearDown(self):
        service_fixtures.DeviceServiceUnitTests.tearDown(self)

    def stores(self):
        return {
            group: {p.name: sha(p.read_bytes()) for p in root.iterdir() if p.is_file()}
            for group, root in (("artifacts", self.service.artifacts.root), ("firmware", self.service.firmware.root))
        }

    def assert_error_without_publish(self, code, payload, *, status=None, alias=True):
        before = self.stores()
        with self.assertRaises(service_module.ServiceError) as caught:
            if alias:
                self.service.create_uiflow_firmware(payload)
            else:
                self.service.create_firmware(payload)
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        self.assertEqual(self.stores(), before, "a rejected request must not publish source or firmware objects")
        return caught.exception

    def create_source(self, **fields):
        return self.service.create_uiflow_firmware({"device_id": "cores3", "files": dict(CALLER_FILES), **fields})

    def session_for(self, firmware):
        payload = {"device_id": firmware["device_id"], "firmware_id": firmware["firmware_id"],
                   "runtime": "qemu", "ttl_seconds": 120}
        if firmware.get("kind") == "uiflow":
            payload["uiflow_source_sha256"] = firmware["source"]["metadata"]["source_sha256"]
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            result = self.service.create_session(payload)
        start.assert_called_once()
        return self.service.get_session(result["session_id"]), result


class UIFlowServiceAdmissionTests(ServiceFixture, unittest.TestCase):
    def test_alias_rejects_every_explicit_kind_before_publishing(self):
        for kind in ("uiflow", "merged", None):
            with self.subTest(kind=kind):
                self.assert_error_without_publish("invalid_uiflow_request", {
                    "device_id": "cores3", "files": CALLER_FILES, "kind": kind,
                }, status=400)

    def test_unknown_fields_and_bad_files_do_not_publish(self):
        cases = [
            ("invalid_uiflow_request", {"device_id": "cores3", "files": CALLER_FILES, "base": "user-supplied"}),
            ("invalid_uiflow_source", {"device_id": "cores3", "files": {"other.py": "pass"}}),
            ("invalid_uiflow_source_path", {"device_id": "cores3", "files": {"main.py": "pass", "../escape.py": "pass"}}),
            ("invalid_uiflow_source", {"device_id": "cores3", "files": {"main.py": 42}}),
        ]
        for code, payload in cases:
            with self.subTest(code=code):
                self.assert_error_without_publish(code, payload)

    def test_supported_device_gate_is_distinct_from_unknown_device(self):
        for device_id in ("core2", "tab5", "cardputer-adv"):
            with self.subTest(device=device_id):
                self.assert_error_without_publish("unsupported_uiflow_device", {
                    "device_id": device_id, "files": CALLER_FILES,
                }, status=409)
        self.assert_error_without_publish("unknown_device", {"device_id": "no-such-device", "files": CALLER_FILES}, status=400)

    def test_missing_reference_is_structured_without_cas_side_effects(self):
        original = self.service.specs["cores3"]
        for path in (None, Path(self.tmp.name) / "does-not-exist.bin"):
            self.service.specs["cores3"] = replace(original, reference_path=path)
            self.assert_error_without_publish("reference_firmware_missing", {"device_id": "cores3", "files": CALLER_FILES}, status=409)

    def test_expected_base_hash_drift_rejects_before_publishing(self):
        self.assert_error_without_publish("uiflow_base_hash_mismatch", {
            "device_id": "cores3", "files": CALLER_FILES, "expected_base_sha256": "0" * 64,
        }, status=409)

    def test_reference_read_failure_is_503_without_publishing(self):
        read_bytes = Path.read_bytes
        def unreadable(path):
            if path == self.reference:
                raise PermissionError("injected reference read failure")
            return read_bytes(path)
        with mock.patch.object(Path, "read_bytes", side_effect=unreadable, autospec=True):
            self.assert_error_without_publish("reference_firmware_unreadable", {
                "device_id": "cores3", "files": CALLER_FILES,
            }, status=503)

    def test_helper_dependency_error_preserves_code_status_and_zero_artifacts(self):
        with mock.patch.object(service_module, "build_uiflow_source_image", side_effect=UIFlowSourceError(
                "uiflow_source_dependency_unavailable", "compatible littlefs-python is required", 503)):
            self.assert_error_without_publish("uiflow_source_dependency_unavailable", {
                "device_id": "cores3", "files": CALLER_FILES,
            }, status=503)


@unittest.skipUnless(source_fixtures.littlefs is not None, "compatible littlefs-python is unavailable")
class UIFlowServiceCompositionTests(ServiceFixture, unittest.TestCase):
    def test_real_source_to_cas_firmware_and_exact_helper_metadata(self):
        base = self.reference.read_bytes()
        expected_image, expected_metadata = build_uiflow_source_image(base, source_fixtures.FLASH_SIZE, CALLER_FILES, expected_base_sha256=sha(base))
        record = self.create_source(expected_base_sha256=sha(base))
        self.assertEqual(record["kind"], "uiflow")
        self.assertEqual(record["firmware_id"], sha(expected_image))
        self.assertEqual(record["sha256"], expected_metadata["firmware_sha256"])
        self.assertEqual(record["source"]["metadata"], expected_metadata)
        artifact_id = record["source"]["artifact_id"]
        self.assertEqual(artifact_id, sha(canonical(CALLER_FILES)))
        self.assertEqual(artifact_id, expected_metadata["source_sha256"])
        self.assertEqual(self.service.artifacts.read(artifact_id), canonical(CALLER_FILES))
        self.assertEqual(self.service.artifacts.get(artifact_id)["content_type"], "application/json")
        self.assertEqual(self.service.firmware.path(record["firmware_id"]).read_bytes(), expected_image)
        self.assertEqual(self.service.firmware.get(record["firmware_id"]), record)
        self.assertEqual(self.reference.read_bytes(), base)
        self.assertEqual(source_fixtures.read_file(expected_image, "/res/font.bin"), bytes(range(256)) * 4)
        self.assertEqual(source_fixtures.read_file(expected_image, "/pkg/sensor.py"), CALLER_FILES["pkg/sensor.py"].encode())
        self.assertNotIn(SENTINEL, json.dumps(record))
        self.assertNotIn(SENTINEL, json.dumps(self.service.firmware.list()))

    def test_all_four_supported_ids_use_their_reference_without_mutating_it(self):
        original = sha(self.reference.read_bytes())
        for device_id in SUPPORTED:
            with self.subTest(device=device_id):
                result = self.service.create_uiflow_firmware({"device_id": device_id, "files": {"main.py": f"device = '{device_id}'\n"}})
                self.assertEqual(result["device_id"], device_id)
                self.assertEqual(result["source"]["metadata"]["base_sha256"], original)
        self.assertEqual(sha(self.reference.read_bytes()), original)

    def test_explicit_boot_origin_and_generic_kind_are_supported(self):
        files = {"main.py": "pass\n", "boot.py": "# caller boot\n_uiflow_run_main = True\n"}
        result = self.service.create_firmware({"kind": "uiflow", "device_id": "cores3", "files": files})
        meta = result["source"]["metadata"]
        self.assertEqual(meta["generated_files"], [])
        self.assertEqual({row["origin"] for row in meta["files"]}, {"caller"})
        image = self.service.firmware.path(result["firmware_id"]).read_bytes()
        self.assertEqual(source_fixtures.read_file(image, "/boot.py"), files["boot.py"].encode())

    def test_bad_existing_filesystem_cannot_publish_a_source_bundle(self):
        base = bytearray(self.reference.read_bytes())
        base[source_fixtures.VFS_OFFSET:source_fixtures.VFS_OFFSET + source_fixtures.VFS_SIZE] = b"\xff" * source_fixtures.VFS_SIZE
        self.reference.write_bytes(base)
        self.assert_error_without_publish("uiflow_vfs_unmountable", {"device_id": "cores3", "files": CALLER_FILES}, status=409)

    def test_helper_source_binding_mismatch_is_checked_before_artifact_creation(self):
        image, metadata = build_uiflow_source_image(self.reference.read_bytes(), source_fixtures.FLASH_SIZE, CALLER_FILES)
        metadata["source_sha256"] = "0" * 64
        with mock.patch.object(service_module, "build_uiflow_source_image", return_value=(image, metadata)):
            self.assert_error_without_publish("uiflow_source_integrity_error", {"device_id": "cores3", "files": CALLER_FILES}, status=500)

    def test_session_provenance_persist_restore_zip_and_list_are_source_bound(self):
        firmware = self.create_source()
        expected = json.loads(json.dumps(firmware["source"]))
        session, created = self.session_for(firmware)
        self.assertEqual(created["firmware_provenance"], expected)
        self.assertEqual(created["source_artifacts"], [expected["artifact_id"]])
        self.assertEqual(session.snapshot()["firmware_provenance"], expected)
        session.serial0.write_text("offline fixture; no guest execution\n")
        stopped = session.stop(purge=False)
        self.assertEqual(stopped["firmware_provenance"], expected)
        persisted = json.loads(session.session_record_path.read_text())
        self.assertEqual(persisted["firmware_provenance"], expected)
        session_id = session.id
        self.service._sessions.pop(session_id)
        self.service._restore_history()
        restored = self.service.get_session(session_id)
        self.assertIsNot(restored, session)
        self.assertEqual(restored.firmware_provenance, expected)
        self.assertEqual(restored.snapshot()["firmware_provenance"], expected)
        bundle = restored.evidence_bundle({"manifest", "serial"})
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            data = archive.read("firmware/uiflow-source.json")
            provenance = json.loads(data)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(provenance, expected)
            self.assertEqual(manifest["session"]["firmware_provenance"], expected)
            self.assertEqual(manifest["files"]["firmware/uiflow-source.json"], {"size": len(data), "sha256": sha(data)})
            self.assertNotIn(SENTINEL, data.decode())
        self.assertNotIn(SENTINEL, json.dumps(self.service.list_sessions()))
        self.assertNotIn(SENTINEL, session.session_record_path.read_text())
        self.assertEqual(self.service.artifacts.read(expected["artifact_id"]), canonical(CALLER_FILES))

    def assert_session_binding_rejected(self, firmware, code, status, **fields):
        before_sessions = set(self.service._sessions)
        before_history = set((self.service.state_dir / "sessions").glob("*/session.json"))
        with mock.patch.object(service_module.DeviceSession, "start") as start:
            with self.assertRaises(service_module.ServiceError) as caught:
                self.service.create_session({"device_id": firmware["device_id"],
                    "firmware_id": firmware["firmware_id"], "runtime": "qemu", **fields})
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.status, status)
        start.assert_not_called()
        self.assertEqual(set(self.service._sessions), before_sessions)
        self.assertEqual(set((self.service.state_dir / "sessions").glob("*/session.json")), before_history)

    def test_uiflow_session_requires_a_matching_source_pin_before_start(self):
        firmware = self.create_source()
        self.assert_session_binding_rejected(firmware, "uiflow_source_binding_required", 400)
        self.assert_session_binding_rejected(firmware, "uiflow_source_binding_mismatch", 409,
                                             uiflow_source_sha256="0" * 64)
        for malformed in (False, 42, "short", "A" * 64):
            with self.subTest(pin=malformed):
                self.assert_session_binding_rejected(firmware, "invalid_uiflow_source_binding", 400,
                                                     uiflow_source_sha256=malformed)

    def test_same_image_different_source_declarations_cannot_silently_rebind_session(self):
        files = {"main.py": "print('same image different declaration')\n"}
        first = self.create_source(files=files)
        first_pin = first["source"]["metadata"]["source_sha256"]
        second = self.create_source(files={**files, "boot.py": source_fixtures.source.DEFAULT_BOOT})
        second_pin = second["source"]["metadata"]["source_sha256"]
        self.assertEqual(first["firmware_id"], second["firmware_id"])
        self.assertNotEqual(first_pin, second_pin)
        self.assertEqual(self.service.firmware.get(first["firmware_id"])["source"], second["source"])
        self.assert_session_binding_rejected(first, "uiflow_source_binding_mismatch", 409,
                                             uiflow_source_sha256=first_pin)
        session, created = self.session_for(second)
        self.assertEqual(created["firmware_provenance"], second["source"])
        self.assertEqual(created["source_artifacts"], [second_pin])
        session.stop(purge=False)
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"manifest"}))) as archive:
            provenance = json.loads(archive.read("firmware/uiflow-source.json"))
            self.assertEqual(provenance, second["source"])
            self.assertEqual(provenance["metadata"]["source_sha256"], second_pin)
        self.assertEqual(self.service.artifacts.read(first_pin), canonical(files))
        self.assertEqual(self.service.artifacts.read(second_pin), canonical({**files, "boot.py": source_fixtures.source.DEFAULT_BOOT}))

    def test_source_pin_on_non_uiflow_firmware_is_rejected_before_start(self):
        artifact = self.service.artifacts.create(self.reference.read_bytes())
        firmware = self.service.create_firmware({"device_id": "cores3", "kind": "merged",
                                               "artifact_id": artifact["artifact_id"]})
        self.assert_session_binding_rejected(firmware, "uiflow_source_binding_mismatch", 409,
                                             uiflow_source_sha256=sha(canonical(CALLER_FILES)))

    def test_generic_firmware_sessions_do_not_get_source_provenance(self):
        artifact = self.service.artifacts.create(self.reference.read_bytes())
        firmware = self.service.create_firmware({"device_id": "cores3", "kind": "merged", "artifact_id": artifact["artifact_id"]})
        session, snapshot = self.session_for(firmware)
        self.assertNotIn("firmware_provenance", snapshot)
        session.stop(purge=False)
        self.assertNotIn("firmware_provenance", json.loads(session.session_record_path.read_text()))
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"manifest"}))) as archive:
            self.assertNotIn("firmware/uiflow-source.json", archive.namelist())


class UIFlowServiceHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Existing HTTP fixture owns local ephemeral server and Handler cleanup.
        service_fixtures.DeviceServiceHttpTests.setUpClass.__func__(cls)
        cls.reference = install_reference(cls.service, cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        service_fixtures.DeviceServiceHttpTests.tearDownClass.__func__(cls)

    request = service_fixtures.DeviceServiceHttpTests.request

    def post(self, path, payload):
        return self.request(path, method="POST", data=canonical(payload), headers={"Content-Type": "application/json"})

    @unittest.skipUnless(source_fixtures.littlefs is not None, "compatible littlefs-python is unavailable")
    def test_public_alias_and_generic_source_route_return_identical_firmware(self):
        payload = {"device_id": "cores3", "files": {"main.py": "print('http source')\n"}}
        status, alias = self.post("/api/v1/firmware/uiflow", payload)
        self.assertEqual(status, 201)
        status, generic = self.post("/api/v1/firmware", {**payload, "kind": "uiflow"})
        self.assertEqual(status, 201)
        self.assertEqual(alias["firmware_id"], generic["firmware_id"])
        self.assertEqual(alias["source"], generic["source"])
        status, fetched = self.request(f"/api/v1/firmware/{alias['firmware_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["source"], alias["source"])
        self.assertEqual(self.service.artifacts.read(alias["source"]["artifact_id"]), canonical(payload["files"]))

    def test_alias_rejection_is_a_structured_http_400_without_artifacts(self):
        before = {p.name for p in self.service.artifacts.root.iterdir()}
        with self.assertRaises(HTTPError) as caught:
            self.post("/api/v1/firmware/uiflow", {"device_id": "cores3", "kind": "merged", "files": CALLER_FILES})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)["error"]["code"], "invalid_uiflow_request")
        self.assertEqual(before, {p.name for p in self.service.artifacts.root.iterdir()})

    def test_http_body_limit_precedes_decoded_source_limit_without_publishing(self):
        files = {name: "\\" * source_fixtures.source.MAX_FILE_BYTES
                 for name in ("main.py", "one.py", "two.py", "three.py")}
        self.assertEqual(sum(len(text.encode("utf-8")) for text in files.values()),
                         source_fixtures.source.MAX_SOURCE_BYTES)
        payload = {"device_id": "cores3", "files": files}
        self.assertGreater(len(canonical(payload)), 1024 * 1024)
        before = {group: set(root.iterdir()) for group, root in (
            ("artifacts", self.service.artifacts.root), ("firmware", self.service.firmware.root))}
        with mock.patch.object(service_module, "build_uiflow_source_image") as build:
            # Reject from headers before accepting source bytes. Sending the whole
            # body after early rejection can race a closed socket in urllib.
            connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            try:
                connection.request("POST", "/api/v1/firmware/uiflow", headers={
                    "Content-Type": "application/json", "Content-Length": str(len(canonical(payload)))})
                response = connection.getresponse()
                self.assertEqual(response.status, 413)
                self.assertEqual(json.load(response)["error"]["code"], "body_too_large")
            finally:
                connection.close()
        build.assert_not_called()
        self.assertEqual(before, {group: set(root.iterdir()) for group, root in (
            ("artifacts", self.service.artifacts.root), ("firmware", self.service.firmware.root))})

    def test_source_route_obeys_existing_bearer_auth_before_store_changes(self):
        previous = Handler.api_token
        before = {p.name for p in self.service.artifacts.root.iterdir()}
        Handler.api_token = "uiflow-unit-http-test-token"
        try:
            with self.assertRaises(HTTPError) as caught:
                self.post("/api/v1/firmware/uiflow", {"device_id": "cores3", "files": CALLER_FILES})
            self.assertEqual(caught.exception.code, 401)
            self.assertEqual(json.load(caught.exception)["error"]["code"], "unauthorized")
        finally:
            Handler.api_token = previous
        self.assertEqual(before, {p.name for p in self.service.artifacts.root.iterdir()})


if __name__ == "__main__":
    unittest.main()
