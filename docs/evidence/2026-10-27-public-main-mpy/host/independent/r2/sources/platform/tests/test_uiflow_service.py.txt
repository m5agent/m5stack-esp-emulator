"""UIFlow source API integration; real LittleFS, no guest/QEMU execution."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock
from urllib.error import HTTPError
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

import device_service as service_module
import test_device_service as service_fixtures
import test_uiflow_source as source_fixtures
from serve import Handler
from uiflow_source import DEFAULT_BOOT, UIFlowSourceError, build_uiflow_source_image

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


def explicit_base_image(*, chip_id=9, family=True, flags=0):
    """Static admission fixture, never executed or claimed as firmware PASS."""
    image = bytearray(source_reference())
    from test_firmware_analysis import build_image
    app = bytearray(build_image(chip_id=chip_id))
    app[32 + 16:32 + 48] = b"V2.5.3\0".ljust(32, b"\0")
    app[32 + 48:32 + 80] = b"micropython\0".ljust(32, b"\0")
    if family:
        app.extend(b"_uiflow_run_main\0UIFLOW2\0")
        struct.pack_into("<I", app, 28, len(app) - 32)
    image[0x10000:0x20000] = b"\xff" * 0x10000
    image[0x10000:0x10000 + len(app)] = app
    image[source_fixtures.VFS_OFFSET + source_fixtures.VFS_SIZE:] = b"\xff" * (len(image) - source_fixtures.VFS_OFFSET - source_fixtures.VFS_SIZE)
    if flags:
        struct.pack_into("<I", image, 0x8000 + 28, flags)
        table = image[0x8000:0x8040]
        image[0x8040 + 16:0x8040 + 32] = hashlib.md5(table).digest()
    return bytes(image)


def store_explicit_base(service, *, data=None, psram_size=None, required=None, security=None):
    data = explicit_base_image() if data is None else data
    # Upload is deliberately sparse. The required composer pin must cover
    # the flash-sized normalized FirmwareStore result rather than this SHA.
    data = data[:source_fixtures.VFS_OFFSET + source_fixtures.VFS_SIZE]
    artifact = service.artifacts.create(data)
    normalized = data.ljust(source_fixtures.FLASH_SIZE, b"\xff")
    manifest = {
        "schema_version": 1, "kind": "m5stack-firmware-manifest", "device_id": "cores3",
        "artifact": {"kind": "merged-flash", "file": "fixture.bin", "artifact_id": artifact["artifact_id"],
                     "size": len(data), "sha256": artifact["sha256"], "source_sha256": artifact["sha256"]},
        "target": {"soc": "esp32s3", "chip_id": 9, "flash_size": source_fixtures.FLASH_SIZE,
                   "psram_size": psram_size, "partition_table": service_module.parse_partition_table(normalized, image_size=len(normalized)),
                   "application": service_module.find_app_descriptor(normalized, 0x10000, 0x20000)},
        "security": security or {"secure_boot": "unknown", "flash_encryption": "unknown", "efuse": "not-included", "secure_version": 0},
        "provenance": {"importer": "static-unit-fixture", "source_format": "merged-bin"},
        "resources": {}, "capabilities": {"required": required or ["wifi"], "optional": []},
        "validation": {"status": "PASS", "errors": [], "warnings": []},
    }
    service_fixtures.seal_manifest(manifest)
    return service.create_firmware({"device_id": "cores3", "kind": "manifest", "manifest": manifest})


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

    def test_explicit_base_requires_pin_and_an_actual_stored_manifest(self):
        base = store_explicit_base(self.service)
        payload = {"device_id": "cores3", "files": CALLER_FILES, "base_firmware_id": base["firmware_id"]}
        self.assert_error_without_publish("uiflow_base_binding_required", payload, status=400)
        for invalid in (None, [], True, "A" * 64):
            self.assert_error_without_publish("invalid_uiflow_request", {**payload, "base_firmware_id": invalid}, status=400)
        self.assert_error_without_publish("unknown_firmware", {**payload, "base_firmware_id": "0" * 64, "expected_base_sha256": "0" * 64}, status=404)
        self.assert_error_without_publish("uiflow_base_hash_mismatch", {**payload, "expected_base_sha256": base["manifest"]["artifact"]["sha256"]}, status=409)
        meta = self.service.firmware._meta(base["firmware_id"])
        record = json.loads(meta.read_text());record["kind"] = "merged";meta.write_text(json.dumps(record))
        self.assert_error_without_publish("uiflow_base_not_admitted", {**payload, "expected_base_sha256": base["sha256"]}, status=409)

    def test_explicit_base_rejects_store_corruption_symlinks_and_special_files(self):
        base = store_explicit_base(self.service)
        payload = {"device_id": "cores3", "files": CALLER_FILES, "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"]}
        path = self.service.firmware._data(base["firmware_id"])
        original = path.read_bytes();path.write_bytes(b"\0" + original[1:])
        self.assert_error_without_publish("uiflow_base_hash_mismatch", payload, status=409)
        path.write_bytes(original)
        target = path.with_name("separate-base-image.bin");target.write_bytes(original);path.unlink();path.symlink_to(target)
        self.assert_error_without_publish("uiflow_base_unreadable", payload, status=409)
        path.unlink();os.mkfifo(path)
        self.assert_error_without_publish("uiflow_base_integrity_error", payload, status=409)
        path.unlink();path.write_bytes(original)
        meta = self.service.firmware._meta(base["firmware_id"]);record = json.loads(meta.read_text());record["sha256"] = "0" * 64;meta.write_text(json.dumps(record))
        self.assert_error_without_publish("uiflow_base_integrity_error", payload, status=409)
        original_meta = json.dumps(base).encode();meta.write_bytes(original_meta)
        target_meta = meta.with_name("separate-base-metadata.json");target_meta.write_bytes(original_meta);meta.unlink();meta.symlink_to(target_meta)
        self.assert_error_without_publish("uiflow_base_unreadable", payload, status=409)
        meta.unlink();meta.write_bytes(original_meta)

    def test_actual_secure_boot_sector_cannot_be_hidden_by_unknown_manifest_security(self):
        for valid_crc in (True, False):
            data = bytearray(explicit_base_image())
            block = bytearray(1216);block[0:2] = b"\xe7\x02";block[4:36] = hashlib.sha256(data[:0x1000]).digest()
            # Deliberately invalid RSA math; CRC-valid and malformed candidate
            # sectors must both be rejected independently of caller metadata.
            struct.pack_into("<I", block, 1196, zlib.crc32(block[:1196]) if valid_crc else 0)
            sector = bytearray(b"\xff" * 4096);sector[:len(block)] = block;data[0x1000:0x2000] = sector
            base = store_explicit_base(self.service, data=bytes(data))
            with self.subTest(valid_crc=valid_crc):
                self.assert_error_without_publish("uiflow_base_not_admitted", {
                    "device_id": "cores3", "files": CALLER_FILES, "base_firmware_id": base["firmware_id"],
                    "expected_base_sha256": base["sha256"],
                }, status=409)

    def test_explicit_base_rejects_actual_wrong_chip_family_and_flagged_partitions(self):
        for data in (explicit_base_image(chip_id=5), explicit_base_image(family=False), explicit_base_image(flags=1)):
            base = store_explicit_base(self.service, data=data)
            self.assert_error_without_publish("uiflow_base_not_admitted", {
                "device_id": "cores3", "files": CALLER_FILES, "base_firmware_id": base["firmware_id"],
                "expected_base_sha256": base["sha256"],
            }, status=409)

    def test_explicit_base_revalidates_manifest_identity_profile_and_security(self):
        base = store_explicit_base(self.service)
        path = self.service.firmware._meta(base["firmware_id"]);original = path.read_bytes()
        cases = (("identity", "firmware_manifest_id_mismatch"), ("capabilities", "unsupported_firmware_capability"),
                 ("security", "unsupported_firmware_capability"), ("device", "firmware_device_mismatch"),
                 ("artifact", "uiflow_base_integrity_error"), ("partitions", "uiflow_base_integrity_error"),
                 ("psram-type", "invalid_firmware_manifest"), ("security-type", "invalid_firmware_manifest"))
        for case, code in cases:
            record = json.loads(original)
            if case == "identity":record["manifest"]["manifest_id"] = "0" * 64
            elif case == "capabilities":record["manifest"]["capabilities"]["required"] = ["vendor-private-sensor"]
            elif case == "security":record["manifest"]["security"]["secure_boot_config"] = "v2"
            elif case == "device":record["device_id"] = "sticks3"
            elif case == "artifact":record["manifest"]["artifact"]["sha256"] = "0" * 64
            elif case == "partitions":record["manifest"]["target"]["partition_table"]["partitions"][0]["size"] += 4096
            elif case == "psram-type":record["manifest"]["target"]["psram_size"] = "8388608"
            elif case == "security-type":record["manifest"]["security"]["secure_boot"] = []
            if case != "identity":
                service_fixtures.seal_manifest(record["manifest"]);record["manifest_id"] = record["manifest"]["manifest_id"];record["source"]["manifest_id"] = record["manifest_id"]
            path.write_text(json.dumps(record))
            with self.subTest(case=case):
                self.assert_error_without_publish(code, {"device_id": "cores3", "files": CALLER_FILES,
                    "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"]}, status=409)
        path.write_bytes(original)


@unittest.skipUnless(source_fixtures.littlefs is not None, "compatible littlefs-python is unavailable")
class UIFlowServiceCompositionTests(ServiceFixture, unittest.TestCase):
    def test_explicit_manifest_base_is_composed_without_mutating_base_or_reference(self):
        base = store_explicit_base(self.service)
        base_path = self.service.firmware.path(base["firmware_id"])
        before_base, before_metadata, before_reference = base_path.read_bytes(), self.service.firmware._meta(base["firmware_id"]).read_bytes(), self.reference.read_bytes()
        expected_image, expected_metadata = build_uiflow_source_image(before_base, source_fixtures.FLASH_SIZE, CALLER_FILES,
                                                                     expected_base_sha256=base["sha256"])
        record = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        self.assertEqual(record["firmware_id"], sha(expected_image))
        self.assertEqual(record["base_manifest"], base["manifest"])
        meta = record["source"]["metadata"]
        self.assertEqual({key: meta[key] for key in expected_metadata}, expected_metadata)
        self.assertEqual(meta["base_firmware_id"], base["firmware_id"])
        self.assertEqual(meta["base_provenance"]["stored_sha256"], base["sha256"])
        self.assertNotEqual(base["sha256"], base["manifest"]["artifact"]["sha256"])
        self.assertEqual(meta["base_provenance"]["artifact_sha256"], base["manifest"]["artifact"]["sha256"])
        self.assertEqual(meta["base_provenance"]["pin_scope"], "normalized-stored-flash-image")
        self.assertEqual(base_path.read_bytes(), before_base)
        self.assertEqual(self.service.firmware._meta(base["firmware_id"]).read_bytes(), before_metadata)
        self.assertEqual(self.reference.read_bytes(), before_reference)
        session, created = self.session_for(record)
        self.assertEqual(created["firmware_provenance"], record["source"])
        session.stop(purge=False)

    def test_explicit_base_composition_does_not_require_a_cached_reference(self):
        base = store_explicit_base(self.service)
        self.service.specs["cores3"] = replace(self.service.specs["cores3"], reference_path=None)
        self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])

    def test_byte_identical_explicit_composition_preserves_original_manifest_without_publish(self):
        base = store_explicit_base(self.service)
        original = self.service.firmware.path(base["firmware_id"]).read_bytes()
        files = {"main.py": "old main\n", "boot.py": "old boot\n"}
        _, metadata = build_uiflow_source_image(original, source_fixtures.FLASH_SIZE, files)
        metadata["firmware_sha256"] = base["sha256"]
        # Exercise a valid byte-identical builder result (e.g. a future
        # filesystem no-op optimization) without rewriting firmware IDs.
        with mock.patch.object(service_module, "build_uiflow_source_image", return_value=(original, metadata)):
            for _ in range(2):
                self.assert_error_without_publish("uiflow_source_context_conflict", {"device_id": "cores3", "files": files,
                    "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"]}, status=409)
        self.assertEqual(self.service.firmware.get(base["firmware_id"]), base)
        session, _ = self.session_for(base)
        session.stop(purge=False)

    def test_explicit_base_same_context_retry_succeeds_but_cannot_become_another_base(self):
        base = store_explicit_base(self.service, psram_size=8 << 20)
        first = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        second = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        for key in ("firmware_id", "device_id", "kind", "source", "base_manifest"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(self.service.firmware.get(base["firmware_id"]), base)
        self.assert_error_without_publish("uiflow_base_not_admitted", {"device_id": "cores3", "files": CALLER_FILES,
            "base_firmware_id": first["firmware_id"], "expected_base_sha256": first["sha256"]}, status=409)

    def test_real_default_and_explicit_aliases_cannot_replace_each_others_context(self):
        self.reference.write_bytes(explicit_base_image())
        base = store_explicit_base(self.service, psram_size=8 << 20)
        for explicit_first in (True, False):
            with self.subTest(explicit_first=explicit_first):
                files = {**CALLER_FILES, "main.py": f"print({explicit_first})\n"}
                default_files = {**files, "boot.py": DEFAULT_BOOT}
                explicit_request = {"device_id": "cores3", "files": files,
                    "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"]}
                default_request = {"device_id": "cores3", "files": default_files}
                # The real LittleFS composer produces identical flash bytes
                # despite different caller JSON and source-file origins.
                explicit_image, _ = build_uiflow_source_image(self.reference.read_bytes(), source_fixtures.FLASH_SIZE, files)
                default_image, _ = build_uiflow_source_image(self.reference.read_bytes(), source_fixtures.FLASH_SIZE, default_files)
                self.assertEqual(explicit_image, default_image)
                first, rejected = (explicit_request, default_request) if explicit_first else (default_request, explicit_request)
                record = self.service.create_uiflow_firmware(first)
                rejected_artifact = sha(canonical(rejected["files"]))
                self.assertFalse(self.service.artifacts._meta(rejected_artifact).exists())
                self.assert_error_without_publish("uiflow_source_context_conflict", rejected, status=409)
                self.assertFalse(self.service.artifacts._meta(rejected_artifact).exists())
                self.assertEqual(self.service.firmware.get(record["firmware_id"]), record)

    def test_explicit_context_cannot_be_replaced_by_merged_or_manifest_intake(self):
        base = store_explicit_base(self.service, psram_size=8 << 20)
        record = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        data = self.service.firmware.path(record["firmware_id"]).read_bytes()
        artifact = self.service.artifacts.create(data)
        self.assert_error_without_publish("uiflow_source_context_conflict", {"device_id": "cores3", "kind": "merged",
            "artifact_id": artifact["artifact_id"]}, status=409, alias=False)
        manifest = json.loads(json.dumps(base["manifest"]))
        manifest["artifact"].update({"artifact_id": artifact["artifact_id"], "sha256": artifact["sha256"],
                                     "size": artifact["size"], "source_sha256": artifact["sha256"]})
        service_fixtures.seal_manifest(manifest)
        self.assert_error_without_publish("uiflow_source_context_conflict", {"device_id": "cores3", "kind": "manifest",
            "manifest": manifest}, status=409, alias=False)
        self.assertEqual(self.service.firmware.get(record["firmware_id"]), record)

    def test_explicit_context_rejects_other_source_origin_or_base_constraints(self):
        base = store_explicit_base(self.service, psram_size=8 << 20)
        record = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        self.assert_error_without_publish("uiflow_source_context_conflict", {"device_id": "cores3",
            "files": {**CALLER_FILES, "boot.py": DEFAULT_BOOT}, "base_firmware_id": base["firmware_id"],
            "expected_base_sha256": base["sha256"]}, status=409)
        # The legacy manifest intake can attach another manifest to identical
        # base bytes; it must not replace an already derived image's context.
        weaker_base = store_explicit_base(self.service, psram_size=None)
        self.assertEqual(weaker_base["firmware_id"], base["firmware_id"])
        self.assertNotEqual(weaker_base["manifest_id"], base["manifest_id"])
        self.assert_error_without_publish("uiflow_source_context_conflict", {"device_id": "cores3",
            "files": CALLER_FILES, "base_firmware_id": weaker_base["firmware_id"],
            "expected_base_sha256": weaker_base["sha256"]}, status=409)
        self.assertEqual(self.service.firmware.get(record["firmware_id"]), record)

    def test_unreadable_existing_context_fails_closed_before_source_publish(self):
        self.reference.write_bytes(explicit_base_image())
        base = store_explicit_base(self.service)
        record = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        path = self.service.firmware._meta(record["firmware_id"])
        original = path.read_bytes()
        alias = {"device_id": "cores3", "files": {**CALLER_FILES, "boot.py": DEFAULT_BOOT}}
        for content in (b"{broken", b"[]"):
            path.write_bytes(content)
            self.assert_error_without_publish("uiflow_source_context_conflict", alias, status=409)
        target = path.with_name("separate-context.json")
        target.write_bytes(original)
        path.unlink();path.symlink_to(target)
        self.assert_error_without_publish("uiflow_source_context_conflict", alias, status=409)
        path.unlink();os.mkfifo(path)
        self.assert_error_without_publish("uiflow_source_context_conflict", alias, status=409)
        path.unlink();path.write_bytes(original)

    def test_timestamp_exception_keeps_all_other_manifest_and_source_fields_exact(self):
        base = store_explicit_base(self.service, psram_size=8 << 20)
        request = {"device_id": "cores3", "files": CALLER_FILES,
                   "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"]}
        record = self.service.create_uiflow_firmware(request)
        path = self.service.firmware._meta(record["firmware_id"])
        original = path.read_bytes()
        for field in ("psram", "security", "required-capabilities", "validation", "nested-created-at", "artifact-file", "source-created-at"):
            changed = json.loads(original)
            manifest = changed["base_manifest"]
            if field == "psram":manifest["target"]["psram_size"] = 4 << 20
            elif field == "security":manifest["security"]["secure_version"] = 1
            elif field == "required-capabilities":manifest["capabilities"]["required"] = ["wifi", "display"]
            elif field == "validation":manifest["validation"]["warnings"] = [{"code": "fixture-semantic-warning"}]
            elif field == "nested-created-at":manifest["target"]["created_at"] = "2026-10-27T00:00:00Z"
            elif field == "artifact-file":manifest["artifact"]["file"] = "another-name.bin"
            elif field == "source-created-at":changed["source"]["metadata"]["created_at"] = "2026-10-27T00:00:00Z"
            path.write_text(json.dumps(changed))
            with self.subTest(field=field):
                self.assert_error_without_publish("uiflow_source_context_conflict", request, status=409)
        path.write_bytes(original)

    def test_default_only_alias_retains_existing_metadata_update_behavior(self):
        first = self.create_source()
        second = self.create_source(files={**CALLER_FILES, "boot.py": DEFAULT_BOOT})
        self.assertEqual(first["firmware_id"], second["firmware_id"])
        self.assertNotEqual(first["source"], second["source"])
        self.assertNotIn("base_manifest", second)
        self.assertEqual(self.service.firmware.get(first["firmware_id"]), second)

    def test_explicit_base_psram_requirement_survives_source_composition(self):
        self.reference.write_bytes(explicit_base_image())
        base = store_explicit_base(self.service, psram_size=8 << 20)
        record = self.create_source(base_firmware_id=base["firmware_id"], expected_base_sha256=base["sha256"])
        self.service.specs["cores3"] = replace(self.service.specs["cores3"], memory="4")
        before = set(self.service._sessions)
        for attempt in range(2):
            with mock.patch.object(service_module.DeviceSession, "start") as start:
                with self.assertRaises(service_module.ServiceError) as caught:
                    self.service.create_session({"device_id": "cores3", "firmware_id": record["firmware_id"], "runtime": "qemu",
                        "uiflow_source_sha256": record["source"]["metadata"]["source_sha256"]})
            self.assertEqual(caught.exception.code, "unsupported_firmware_capability")
            self.assertEqual(caught.exception.extra["issues"][0]["code"], "runtime_psram_mismatch")
            start.assert_not_called();self.assertEqual(set(self.service._sessions), before)
            if attempt == 0:
                self.assert_error_without_publish("uiflow_source_context_conflict", {"device_id": "cores3",
                    "files": {**CALLER_FILES, "boot.py": DEFAULT_BOOT}}, status=409)

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

    @unittest.skipUnless(source_fixtures.littlefs is not None, "compatible littlefs-python is unavailable")
    def test_public_explicit_base_endpoint_requires_normalized_pin(self):
        base = store_explicit_base(self.service)
        payload = {"device_id": "cores3", "files": {"main.py": "print('explicit base HTTP')\n"}, "base_firmware_id": base["firmware_id"]}
        with self.assertRaises(HTTPError) as caught:self.post("/api/v1/firmware/uiflow", payload)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)["error"]["code"], "uiflow_base_binding_required")
        with self.assertRaises(HTTPError) as caught:self.post("/api/v1/firmware/uiflow", {**payload, "expected_base_sha256": base["manifest"]["artifact"]["sha256"]})
        self.assertEqual(caught.exception.code, 409)
        status, record = self.post("/api/v1/firmware/uiflow", {**payload, "expected_base_sha256": base["sha256"]})
        self.assertEqual(status, 201)
        self.assertEqual(record["kind"], "uiflow")
        self.assertEqual(record["source"]["metadata"]["base_firmware_id"], base["firmware_id"])

    @unittest.skipUnless(source_fixtures.littlefs is not None, "compatible littlefs-python is unavailable")
    def test_public_reimport_timestamp_change_allows_identical_explicit_source_retry(self):
        upload = explicit_base_image()
        source = {"device_id": "cores3", "files": {"main.py": "print('public import timestamp retry')\n"}}
        imports, compositions = [], []
        for _ in range(2):
            status, artifact = self.request("/api/v1/artifacts", method="POST", data=upload,
                headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": "timestamp-retry.bin"})
            self.assertEqual(status, 201)
            status, base = self.post("/api/v1/firmware/import", {"device_id": "cores3", "artifact_id": artifact["artifact_id"]})
            self.assertEqual(status, 201)
            imports.append(base)
            status, derived = self.post("/api/v1/firmware/uiflow", {**source,
                "base_firmware_id": base["firmware_id"], "expected_base_sha256": base["sha256"]})
            self.assertEqual(status, 201)
            compositions.append(derived)
        self.assertEqual(imports[0]["firmware_id"], imports[1]["firmware_id"])
        self.assertEqual(imports[0]["manifest_id"], imports[1]["manifest_id"])
        self.assertNotEqual(imports[0]["manifest"]["created_at"], imports[1]["manifest"]["created_at"])
        old_manifest, new_manifest = dict(imports[0]["manifest"]), dict(imports[1]["manifest"])
        old_manifest.pop("created_at");new_manifest.pop("created_at")
        self.assertEqual(old_manifest, new_manifest)
        self.assertEqual(compositions[0]["firmware_id"], compositions[1]["firmware_id"])
        self.assertEqual(compositions[0]["source"], compositions[1]["source"])
        self.assertEqual(compositions[1]["base_manifest"], imports[1]["manifest"])
        self.assertEqual(sha(self.service.firmware.path(compositions[1]["firmware_id"]).read_bytes()), compositions[0]["firmware_id"])

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
