#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

import device_service as device_service_module
from device_service import (
    DEFAULT_MAX_PER_DEVICE,
    DEFAULT_MAX_SESSIONS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_CHUNK_BYTES,
    QMP,
    DeviceService,
    DeviceSession,
    ServiceError,
    StoragePolicy,
    default_session_ready_timeout,
    effective_session_ready_timeout,
)
from nvs_image import PAGE_SIZE, build_string_nvs_image
from serve import Handler, _wait_for_session
from test_firmware_analysis import build_flash
from worker_auth import sign_worker_request


def hermetic_flash_preparer(
    spec: device_service_module.DeviceSpec,
    image: Path,
    firmware_sha: str,
    work_dir: Path,
) -> dict:
    data = image.read_bytes()
    if len(data) > spec.flash_size:
        raise ValueError("firmware exceeds device flash size")
    target = work_dir / "virtual-flash.bin"
    target.write_bytes(data.ljust(spec.flash_size, b"\xff"))
    return {
        "transport": "test-host-image",
        "verified": True,
        "flash_size": spec.flash_size,
        "firmware_sha256": firmware_sha,
        "virtual_flash": str(target),
    }


def build_flash_with_nvs_partition(*, nvs_size: int = 0x6000) -> bytes:
    base = build_flash()
    image = bytearray(b"\xff" * len(base))
    image[:0x8000] = base[:0x8000]
    image[0x10000:] = base[0x10000:]
    if nvs_size > 0x6000:
        raise ValueError("test NVS partition exceeds space before app")
    entries = []
    for subtype, offset, size, label in (
        (2, 0x9000, nvs_size, b"nvs"),
        (0, 0x10000, 0x2000, b"factory"),
    ):
        entry = bytearray(32)
        struct.pack_into("<H", entry, 0, 0x50AA)
        entry[2] = 1 if subtype == 2 else 0
        entry[3] = subtype
        struct.pack_into("<II", entry, 4, offset, size)
        entry[12 : 12 + len(label)] = label
        entries.append(entry)
    table = b"".join(entries)
    md5_entry = bytearray(32)
    struct.pack_into("<H", md5_entry, 0, 0xEBEB)
    md5_entry[16:32] = hashlib.md5(table).digest()
    image[0x8000 : 0x8000 + len(table)] = table
    image[0x8000 + len(table) : 0x8000 + len(table) + 32] = md5_entry
    return bytes(image)


def webburner_package(image: bytes) -> bytes:
    parts = {
        "bootloader.bin": image[:0x8000],
        "partition-table.bin": image[0x8000:0x10000],
        "application.bin": image[0x10000:],
    }
    offsets = {
        "bootloader.bin": 0,
        "partition-table.bin": 0x8000,
        "application.bin": 0x10000,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "name": "Web Probe",
                    "version": "2.0.0",
                    "builds": [
                        {
                            "chipFamily": "ESP32-S3",
                            "parts": [
                                {
                                    "path": name,
                                    "offset": offsets[name],
                                }
                                for name in parts
                            ],
                        }
                    ],
                }
            ),
        )
        for name, data in parts.items():
            archive.writestr(name, data)
    return output.getvalue()


class DeviceServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        runtime = Path(self.tmp.name) / "runtime"
        runtime.mkdir()
        qemu = runtime / "qemu-system-xtensa"
        qemu.write_text("#!/bin/sh\nexit 0\n")
        qemu.chmod(0o755)
        rom_dir = runtime / "pc-bios"
        rom_dir.mkdir()
        esp_emu = runtime / "esp-emu"
        esp_emu.write_text("#!/bin/sh\nexit 0\n")
        esp_emu.chmod(0o755)
        emulator_rom = runtime / "esp32p4_rev0_rom.elf"
        emulator_rom.write_bytes(b"test rom")
        efuse = runtime / "efuse.bin"
        efuse.write_bytes(b"\0" * 4096)
        c6_firmware = runtime / "c6.bin"
        c6_firmware.write_bytes(b"test c6 firmware")
        qemu_reference = runtime / "qemu-reference.bin"
        qemu_reference.write_bytes(b"\xff" * (4 << 20))
        tab5_reference = runtime / "tab5-reference.bin"
        tab5_reference.write_bytes(b"\xff" * (16 << 20))
        specs = {}
        for device_id, spec in device_service_module.load_device_specs().items():
            if spec.service_kind == "tab5":
                spec = replace(
                    spec,
                    emulator=esp_emu,
                    rom=emulator_rom,
                    efuse=efuse,
                    c6_firmware=c6_firmware,
                    reference_path=tab5_reference,
                )
            else:
                spec = replace(
                    spec,
                    qemu=qemu,
                    rom_dir=rom_dir,
                    flash_emulator=(
                        esp_emu if spec.flash_emulator is not None else None
                    ),
                    reference_path=qemu_reference,
                )
            specs[device_id] = spec
        self.service = DeviceService(
            state_dir=Path(self.tmp.name),
            max_sessions=2,
            max_per_device=1,
            flash_preparer=hermetic_flash_preparer,
        )
        self.service.specs = specs

    def tearDown(self):
        self.service.close_all()
        self.tmp.cleanup()

    def test_http_companion_persists_requests_and_recovers_by_generation(
        self,
    ):
        log_path = Path(self.tmp.name) / "http-fixture.json"
        port = device_service_module.free_tcp_port()
        first = device_service_module.UnifiedHttpFixture(
            log_path,
            body=b"FIRST\n",
            port=port,
            generation=1,
        )
        try:
            request = Request(
                f"http://127.0.0.1:{port}/unified",
                headers={"Host": "qemu.test"},
            )
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.read(), b"FIRST\n")
            persisted = json.loads(log_path.read_text())
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["fixture_generation"], 1)
        finally:
            first.close()

        seed = json.loads(log_path.read_text())
        second = device_service_module.UnifiedHttpFixture(
            log_path,
            body=b"SECOND\n",
            port=port,
            seed_requests=seed,
            generation=2,
        )
        try:
            request = Request(
                f"http://127.0.0.1:{port}/unified",
                headers={"Host": "qemu.test"},
            )
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.read(), b"SECOND\n")
        finally:
            second.close()

        recovered = json.loads(log_path.read_text())
        self.assertEqual(
            [item["fixture_generation"] for item in recovered],
            [1, 2],
        )
        self.assertEqual(
            [(item["path"], item["host"]) for item in recovered],
            [("/unified", "qemu.test"), ("/unified", "qemu.test")],
        )

    def test_catalog_enables_tab5_and_excludes_cardputer_zero(self):
        payload = self.service.list_devices()
        rows = {row["device_id"]: row for row in payload["devices"]}
        self.assertEqual(len(rows), 14)
        self.assertEqual(sum(row["creatable"] for row in rows.values()), 13)
        self.assertTrue(rows["tab5"]["supported"])
        self.assertTrue(rows["tab5"]["creatable"])
        self.assertEqual(rows["tab5"]["peripheral_status"], "partial")
        self.assertTrue(rows["tab5"]["warnings"])
        self.assertFalse(rows["tab5"]["features"]["qom"])
        self.assertTrue(rows["sticks3"]["features"]["device_state"])
        self.assertTrue(rows["sticks3"]["features"]["network"])
        self.assertEqual(rows["sticks3"]["network_status"], "validated")
        self.assertIn(
            "uiflow2-sticks3",
            rows["sticks3"]["network_profiles"],
        )
        self.assertIn(
            "uiflow2-sticks3-unified",
            rows["sticks3"]["network_profiles"],
        )
        self.assertIn(
            "uiflow2-sticks3-wifi",
            rows["sticks3"]["network_profiles"],
        )
        self.assertEqual(rows["nanoc6"]["network_status"], "validated")
        self.assertIn(
            "nanoc6-hci-ble",
            rows["nanoc6"]["network_profiles"],
        )
        self.assertEqual(rows["nesso-n1"]["network_status"], "validated")
        self.assertIn(
            "nesso-unified",
            rows["nesso-n1"]["network_profiles"],
        )
        self.assertEqual(rows["cores3"]["network_status"], "validated")
        self.assertTrue(rows["cores3"]["features"]["network"])
        self.assertTrue(rows["cores3"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-cores3-unified",
            rows["cores3"]["network_profiles"],
        )
        self.assertEqual(rows["stopwatch"]["network_status"], "validated")
        self.assertTrue(rows["stopwatch"]["features"]["network"])
        self.assertTrue(rows["stopwatch"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-stopwatch-unified",
            rows["stopwatch"]["network_profiles"],
        )
        self.assertEqual(rows["cardputer-adv"]["network_status"], "validated")
        self.assertTrue(rows["cardputer-adv"]["features"]["network"])
        self.assertTrue(rows["cardputer-adv"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-cardputer-adv-unified",
            rows["cardputer-adv"]["network_profiles"],
        )
        self.assertEqual(rows["atoms3r"]["network_status"], "validated")
        self.assertTrue(rows["atoms3r"]["features"]["network"])
        self.assertTrue(rows["atoms3r"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-atoms3r-unified",
            rows["atoms3r"]["network_profiles"],
        )
        self.assertEqual(rows["papercolor"]["network_status"], "validated")
        self.assertTrue(rows["papercolor"]["features"]["network"])
        self.assertTrue(rows["papercolor"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-papercolor-unified",
            rows["papercolor"]["network_profiles"],
        )
        self.assertEqual(rows["papermono"]["network_status"], "validated")
        self.assertTrue(rows["papermono"]["features"]["network"])
        self.assertTrue(rows["papermono"]["features"]["device_state"])
        self.assertTrue(rows["papermono"]["features"]["storage"])
        self.assertFalse(rows["atoms3r"]["features"]["storage"])
        self.assertIn(
            "uiflow2-papermono-unified",
            rows["papermono"]["network_profiles"],
        )
        self.assertTrue(rows["stackchan"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-stackchan-unified",
            rows["stackchan"]["network_profiles"],
        )
        self.assertTrue(rows["stamplc"]["features"]["device_state"])
        self.assertIn(
            "uiflow2-stamplc-unified",
            rows["stamplc"]["network_profiles"],
        )
        for validated_s3 in (
            "papercolor",
            "papermono",
            "stackchan",
            "stamplc",
        ):
            self.assertEqual(rows[validated_s3]["network_status"], "validated")
            self.assertTrue(rows[validated_s3]["features"]["network"])
        for unsupported in ("core2", "tab5"):
            self.assertEqual(
                rows[unsupported]["network_status"],
                "not-supported",
            )
            self.assertEqual(rows[unsupported]["network_profiles"], [])
        self.assertFalse(rows["core2"]["features"]["network"])
        self.assertFalse(rows["cardputer-zero"]["supported"])
        self.assertFalse(rows["tab5"]["features"]["network"])
        self.assertTrue(payload["network_enabled"])

    def test_session_create_idempotency_replays_and_persists(self):
        request = {
            "device_id": "sticks3",
            "ttl_seconds": 60,
            "idempotency_key": "review-session-create-001",
        }
        with mock.patch.object(
            device_service_module.DeviceSession,
            "start",
            autospec=True,
        ):
            first = self.service.create_session(request)
            replay = self.service.create_session(request)
            with self.assertRaises(ServiceError) as conflict:
                self.service.create_session(
                    {**request, "ttl_seconds": 61}
                )

        self.assertEqual(first["session_id"], replay["session_id"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(conflict.exception.code, "session_idempotency_conflict")
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(
            len(self.service.list_sessions(include_stopped=False)["sessions"]),
            1,
        )
        with self.assertRaises(ServiceError) as invalid_key:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "idempotency_key": "bad\x00key",
                }
            )
        self.assertEqual(
            invalid_key.exception.code,
            "invalid_idempotency_key",
        )
        mapping_path = self.service.state_dir / "session-idempotency.json"
        mapping_text = mapping_path.read_text()
        self.assertNotIn(request["idempotency_key"], mapping_text)
        self.assertNotIn(request["idempotency_key"], mapping_path.name)
        self.assertEqual(mapping_path.stat().st_mode & 0o777, 0o600)

        session_id = first["session_id"]
        self.service.close_all()
        reopened = DeviceService(
            state_dir=self.service.state_dir,
            max_sessions=2,
            max_per_device=1,
            flash_preparer=hermetic_flash_preparer,
        )
        reopened.specs = self.service.specs
        try:
            with mock.patch.object(
                device_service_module.DeviceSession,
                "start",
                autospec=True,
            ):
                restored_replay = reopened.create_session(request)
            self.assertEqual(
                restored_replay["session_id"],
                session_id,
            )
            self.assertTrue(restored_replay["idempotent_replay"])
        finally:
            reopened.close_all()

    def test_missing_runtime_files_are_reported(self):
        spec = self.service.specs["sticks3"]
        self.service.specs["sticks3"] = replace(
            spec,
            qemu=ROOT / "__missing_qemu__",
            rom_dir=ROOT / "__missing_rom_dir__",
            flash_emulator=ROOT / "__missing_esp_emu__",
        )

        rows = {
            row["device_id"]: row
            for row in self.service.list_devices()["devices"]
        }
        row = rows["sticks3"]
        expected = [
            "__missing_qemu__",
            "__missing_rom_dir__",
            "__missing_esp_emu__",
        ]
        self.assertFalse(row["backend_ready"])
        self.assertFalse(row["creatable"])
        self.assertEqual(row["missing_runtime_files"], expected)

        with self.assertRaises(ServiceError) as caught:
            self.service.create_session(
                {"device_id": "sticks3", "ttl_seconds": 60}
            )
        error = caught.exception
        self.assertEqual(error.code, "backend_not_ready")
        self.assertEqual(error.status, 503)
        self.assertEqual(error.extra["missing"], expected)
        self.assertEqual(
            error.extra["documentation"],
            "docs/deployment.md",
        )

    def test_backend_qemu_can_use_architecture_runtime_overrides(self):
        xtensa_override = Path("/opt/m5-qemu/qemu-system-xtensa")
        riscv_override = Path("/opt/m5-qemu/qemu-system-riscv32")
        with mock.patch.dict(
            os.environ,
            {
                "M5_QEMU_XTENSA": str(xtensa_override),
                "M5_QEMU_RISCV32": str(riscv_override),
            },
        ):
            specs = device_service_module.load_device_specs()

        self.assertEqual(specs["sticks3"].qemu, xtensa_override)
        self.assertEqual(specs["core2"].qemu, xtensa_override)
        self.assertEqual(specs["nanoc6"].qemu, riscv_override)

    def test_merged_firmware_is_padded_to_device_flash(self):
        artifact = self.service.upload_artifact(b"\xe9" + b"X" * 1023)
        firmware = self.service.create_firmware(
            {
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            }
        )
        self.assertEqual(firmware["size"], 8 << 20)
        self.assertEqual(
            self.service.firmware.path(firmware["firmware_id"]).stat().st_size,
            8 << 20,
        )

    def test_manifest_firmware_is_validated_and_recorded(self):
        data = b"\xe9" + b"M" * 1023
        artifact = self.service.upload_artifact(data)
        manifest = {
            "schema_version": 1,
            "kind": "m5stack-firmware-manifest",
            "device_id": "sticks3",
            "artifact": {
                "kind": "merged-flash",
                "file": "firmware.bin",
                "artifact_id": artifact["artifact_id"],
                "size": len(data),
                "sha256": artifact["sha256"],
            },
            "target": {
                "soc": "esp32s3",
                "chip_id": 9,
                "flash_size": 8 << 20,
                "psram_size": 8 << 20,
                "partition_table": {},
                "application": None,
            },
            "security": {
                "secure_boot": "unknown",
                "flash_encryption": "unknown",
                "efuse": "not-included",
                "secure_version": 0,
            },
            "provenance": {
                "importer": "test",
                "source_format": "merged-bin",
            },
            "resources": {},
            "capabilities": {
                "required": ["wifi"],
                "optional": [],
            },
            "validation": {
                "status": "PASS",
                "errors": [],
                "warnings": [],
            },
        }
        manifest["manifest_id"] = device_service_module.canonical_json_sha256(
            manifest
        )
        firmware = self.service.create_firmware(
            {
                "device_id": "sticks3",
                "kind": "manifest",
                "manifest": manifest,
            }
        )
        self.assertEqual(firmware["kind"], "manifest")
        self.assertEqual(
            firmware["manifest_id"],
            manifest["manifest_id"],
        )
        self.assertEqual(
            firmware["source"]["artifact_id"],
            artifact["artifact_id"],
        )
        self.assertEqual(firmware["size"], 8 << 20)

        rejected = json.loads(json.dumps(manifest))
        rejected["capabilities"]["required"] = ["camera"]
        rejected["manifest_id"] = device_service_module.canonical_json_sha256(
            {
                key: value
                for key, value in rejected.items()
                if key != "manifest_id"
            }
        )
        with self.assertRaises(ServiceError) as caught:
            self.service.create_firmware(
                {
                    "device_id": "sticks3",
                    "kind": "manifest",
                    "manifest": rejected,
                }
            )
        self.assertEqual(
            caught.exception.code,
            "unsupported_firmware_capability",
        )
        self.assertEqual(
            caught.exception.extra["issues"][0]["code"],
            "unsupported_capability",
        )

    def test_qemu_runtime_rejects_psram_capability_mismatch(self):
        data = b"\xe9" + b"C" * 1023
        artifact = self.service.upload_artifact(data)
        manifest = {
            "schema_version": 1,
            "kind": "m5stack-firmware-manifest",
            "device_id": "core2",
            "artifact": {
                "kind": "merged-flash",
                "file": "firmware.bin",
                "artifact_id": artifact["artifact_id"],
                "size": len(data),
                "sha256": artifact["sha256"],
            },
            "target": {
                "soc": "esp32",
                "chip_id": 0,
                "flash_size": 16 << 20,
                "psram_size": 8 << 20,
                "partition_table": {},
                "application": None,
            },
            "security": {
                "secure_boot": "unknown",
                "flash_encryption": "unknown",
                "efuse": "not-included",
                "secure_version": 0,
            },
            "provenance": {
                "importer": "test",
                "source_format": "merged-bin",
            },
            "resources": {},
            "capabilities": {
                "required": ["wifi"],
                "optional": [],
            },
            "validation": {
                "status": "PASS",
                "errors": [],
                "warnings": [],
            },
        }
        manifest["manifest_id"] = device_service_module.canonical_json_sha256(
            manifest
        )
        firmware = self.service.create_firmware(
            {
                "device_id": "core2",
                "kind": "manifest",
                "manifest": manifest,
            }
        )
        elf = self.service.upload_artifact(b"\x7fELF-test")
        with mock.patch.dict(
            os.environ,
            {"M5_CORE2_RADIO_QEMU": str(self.service.specs["core2"].qemu)},
        ):
            with self.assertRaises(ServiceError) as caught:
                self.service.create_session(
                    {
                        "device_id": "core2",
                        "firmware_id": firmware["firmware_id"],
                        "runtime": "qemu-unified",
                        "network": {
                            "profile": "core2-native-hci",
                            "elf_artifact_id": elf["artifact_id"],
                        },
                    }
                )
        self.assertEqual(
            caught.exception.code,
            "unsupported_firmware_capability",
        )
        issue = caught.exception.extra["issues"][0]
        self.assertEqual(issue["code"], "runtime_psram_mismatch")
        self.assertEqual(issue["available"], 4 << 20)

    def test_qemu_wifi_network_result_refreshes_before_stop(self):
        spec = self.service.specs["sticks3"]
        firmware = Path(self.tmp.name) / "sticks3-wifi.bin"
        firmware.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="c" * 32,
            spec=spec,
            firmware_id="d" * 64,
            firmware_path=firmware,
            firmware_sha="d" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker=None,
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-wifi",
            network_config={
                "profile": "uiflow2-sticks3-wifi",
                "nic": "misc.esp32s3.wifi",
                "net_mode": "user",
                "expected_markers": ["APP DNS_OK", "APP HTTP 200"],
                "attempts": 1,
            },
            network_result={
                "status": "PARTIAL",
                "checks": {"marker:1": False, "marker:2": False},
            },
        )
        session.state = "running"
        session.serial0.write_text("APP DNS_OK api.example\nAPP HTTP 200 128\n")

        live = session.snapshot()
        self.assertEqual(live["network"]["status"], "PASS")
        self.assertTrue(all(live["network"]["checks"].values()))

        stopped = session.stop(purge=True)
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(stopped["network"]["status"], "PASS")
        self.assertTrue(all(stopped["network"]["checks"].values()))

    def test_core2_and_tab5_use_exact_host_image(self):
        for device_id in ("core2", "tab5"):
            with self.subTest(device_id=device_id):
                spec = self.service.specs[device_id]
                image = b"\xff" * spec.flash_size
                firmware = Path(self.tmp.name) / f"{device_id}.bin"
                firmware.write_bytes(image)
                firmware_sha = device_service_module.hashlib.sha256(
                    image
                ).hexdigest()

                def unexpected_flash_preparer(*args, **kwargs):
                    raise AssertionError(
                        f"{device_id} must not invoke the esptool path"
                    )

                self.service.flash_preparer = unexpected_flash_preparer
                prepared = self.service.prepare_flash(spec, firmware, firmware_sha)

                self.assertEqual(prepared["info"]["transport"], "host-image")
                self.assertTrue(prepared["info"]["verified"])
                self.assertEqual(prepared["path"].stat().st_size, spec.flash_size)

    def test_core2_service_exposes_board_psram(self):
        self.assertEqual(self.service.specs["core2"].memory, "4")
        regular = device_service_module.qemu_runtime_memory(
            "4",
            "core2-unified",
            "core2",
        )
        native = device_service_module.qemu_runtime_memory(
            "4",
            "core2-native-hci",
            "core2",
        )
        self.assertEqual(regular["effective_psram_mib"], 4)
        self.assertEqual(regular["policy"], "qemu-emulated-psram")
        self.assertEqual(native["cli_requested_psram_mib"], 0)
        self.assertEqual(native["effective_psram_mib"], 4)
        self.assertEqual(
            native["effective_source"],
            "validated-m5core2-qom",
        )
        self.assertEqual(
            native["policy"],
            "native-controller-machine-default-psram",
        )
        self.assertEqual(
            native["physical_cache_psram_timing"],
            "NOT RUN",
        )
        issue = device_service_module.runtime_psram_mismatch(
            "4",
            "core2-native-hci",
            8 << 20,
            "core2",
        )
        self.assertEqual(issue["code"], "runtime_psram_mismatch")
        self.assertEqual(issue["available"], 4 << 20)
        self.assertEqual(
            issue["memory_policy"],
            "native-controller-machine-default-psram",
        )
        self.assertIsNone(
            device_service_module.runtime_psram_mismatch(
                "4",
                "core2-unified",
                4 << 20,
                "core2",
            )
        )

    def test_tab5_service_models_board_i2c_devices(self):
        devices = device_service_module.TAB5_I2C_DEVICES
        by_address = {
            value.split("0x", 1)[1].split(",", 1)[0]: value
            for value in devices
        }

        self.assertEqual(
            set(by_address),
            {"32", "41", "43", "44", "68"},
        )
        self.assertIn("reg=0x01=0xA2", by_address["43"])
        self.assertIn("reg=0x01=0xA2", by_address["44"])
        self.assertIn("reg=0x0F=0x00", by_address["44"])
        self.assertIn("reg=0x00=0x24", by_address["68"])

    def test_segmented_firmware_rejects_overlap(self):
        artifact = self.service.upload_artifact(b"APP")
        with self.assertRaises(Exception) as context:
            self.service.create_firmware(
                {
                    "device_id": "sticks3",
                    "kind": "segmented",
                    "segments": [
                        {"offset": "0x10000", "artifact_id": artifact["artifact_id"]},
                        {"offset": "0x10001", "artifact_id": artifact["artifact_id"]},
                    ],
                }
            )
        self.assertEqual(getattr(context.exception, "code", None), "overlapping_segments")

    def test_capacity_reports_isolated_leases(self):
        capacity = self.service.capacity()
        self.assertEqual(capacity["max_sessions"], 2)
        self.assertEqual(capacity["max_per_device"], 1)
        self.assertEqual(
            capacity["modes"]["network"],
            "enabled-separate-lane",
        )
        self.assertEqual(capacity["modes"]["qemu-wifi"], "enabled-s3")
        self.assertEqual(
            capacity["modes"]["qemu-ble"],
            "enabled-nanoc6-hci-nesso-hci",
        )
        self.assertEqual(
            capacity["modes"]["qemu-unified"],
            "enabled-sticks3-cores3-cardputer-adv-stopwatch-atoms3r-papercolor-papermono-stackchan-stamplc-c6-wifi-ble",
        )
        self.assertEqual(capacity["modes"]["tab5"], "enabled-partial")

    def test_worker_drain_blocks_admission_until_resume(self):
        worker = self.service.worker_status()
        self.assertEqual(worker["state"], "ready")
        self.assertTrue(worker["accepting_leases"])

        draining = self.service.drain_worker()
        self.assertEqual(draining["worker"]["state"], "drained")
        self.assertEqual(
            self.service.capacity()["worker"]["state"],
            "drained",
        )
        self.assertEqual(
            self.service.capacity()["available_sessions"],
            0,
        )
        with self.assertRaises(ServiceError) as caught:
            self.service.create_session(
                {"device_id": "sticks3", "ttl_seconds": 60}
            )
        self.assertEqual(caught.exception.code, "worker_not_accepting")
        self.assertEqual(caught.exception.status, 503)

        resumed = self.service.resume_worker()
        self.assertEqual(resumed["worker"]["state"], "ready")
        self.assertTrue(
            self.service.capacity()["worker"]["accepting_leases"]
        )

    def test_default_capacity_matches_measured_workstation_profile(self):
        self.assertEqual(DEFAULT_MAX_SESSIONS, 12)
        self.assertEqual(DEFAULT_MAX_PER_DEVICE, 8)
        self.assertEqual(MAX_ARTIFACT_BYTES, 96 * 1024 * 1024)
        self.assertEqual(MAX_ARTIFACT_CHUNK_BYTES, 8 * 1024 * 1024)

    def test_core2_tcg_cache_is_bounded(self):
        self.assertEqual(
            device_service_module.core2_accel_args(),
            [
                "-accel",
                "tcg,thread=single,tb-size=128",
                "-icount",
                "shift=auto,align=off,sleep=off",
            ],
        )

    def test_ble_profiles_use_longer_default_ready_timeout(self):
        for profile in (
            "core2-native-vhci",
            "core2-native-hci",
            "core2-hci-gatt",
            "nanoc6-hci-ble",
            "nesso-unified",
            "uiflow2-sticks3-unified",
        ):
            with self.subTest(profile=profile):
                self.assertEqual(
                    default_session_ready_timeout(
                        {"profile": profile}
                    ),
                    90.0,
                )
        self.assertEqual(
            default_session_ready_timeout(
                {"profile": "uiflow2-sticks3-wifi"}
            ),
            30.0,
        )

    def test_reconnect_workload_extends_ready_timeout_budget(self):
        requested = 180.0
        effective = effective_session_ready_timeout(
            {
                "profile": "core2-native-hci",
                "ble_reconnect_cycles": 121,
                "ble_reconnect_delay_seconds": 2,
            },
            requested,
        )

        self.assertGreater(effective, 900)
        self.assertEqual(
            effective_session_ready_timeout(
                {
                    "profile": "uiflow2-sticks3-wifi",
                    "ble_reconnect_cycles": 121,
                    "ble_reconnect_delay_seconds": 2,
                },
                requested,
            ),
            requested,
        )

    def test_catalog_exposes_sku_and_coverage(self):
        row = self.service.get_device("cores3")
        self.assertEqual(row["sku"], "K128")
        self.assertIn("generic-flash", row["firmware_families"])
        self.assertIn("peripheral_status", row["coverage"])

    def test_artifact_list_and_delete(self):
        artifact = self.service.upload_artifact(b"probe")
        self.assertEqual(
            self.service.artifacts.list()[0]["artifact_id"],
            artifact["artifact_id"],
        )
        self.service.artifacts.delete(artifact["artifact_id"])
        self.assertEqual(self.service.artifacts.list(), [])

    def test_streamed_artifact_upload_is_content_checked_and_resumable(self):
        payload = b"streamed-firmware" * 4096
        first = payload[:20000]
        second = payload[20000:]
        upload = self.service.begin_artifact_upload(
            expected_size=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            name="streamed.bin",
            content_type="application/octet-stream",
        )
        progress = self.service.append_artifact_upload(
            upload["upload_id"],
            offset=0,
            data=first,
            sha256=hashlib.sha256(first).hexdigest(),
        )
        self.assertEqual(progress["next_offset"], len(first))
        resumed = self.service.artifacts.get_upload(upload["upload_id"])
        self.assertEqual(resumed["received_bytes"], len(first))
        with self.assertRaises(ServiceError) as caught:
            self.service.append_artifact_upload(
                upload["upload_id"],
                offset=0,
                data=second,
                sha256=hashlib.sha256(second).hexdigest(),
            )
        self.assertEqual(caught.exception.code, "invalid_chunk_offset")
        self.service.append_artifact_upload(
            upload["upload_id"],
            offset=len(first),
            data=second,
            sha256=hashlib.sha256(second).hexdigest(),
        )
        artifact = self.service.complete_artifact_upload(upload["upload_id"])
        self.assertEqual(
            artifact["artifact_id"], hashlib.sha256(payload).hexdigest()
        )
        self.assertEqual(
            self.service.artifacts.read(artifact["artifact_id"]), payload
        )
        completed = self.service.artifacts.get_upload(upload["upload_id"])
        self.assertEqual(completed["status"], "completed")

        aborted = self.service.begin_artifact_upload(
            expected_size=4,
            expected_sha256=hashlib.sha256(b"stop").hexdigest(),
        )
        self.assertTrue(
            self.service.artifacts.abort_upload(aborted["upload_id"])["aborted"]
        )

    def test_streamed_artifact_upload_rejects_bad_hash_and_incomplete_state(self):
        payload = b"verified-prefix"
        upload = self.service.begin_artifact_upload(
            expected_size=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )
        with self.assertRaises(ServiceError) as caught:
            self.service.append_artifact_upload(
                upload["upload_id"],
                offset=0,
                data=payload,
                sha256="0" * 64,
            )
        self.assertEqual(caught.exception.code, "chunk_hash_mismatch")
        self.assertEqual(
            self.service.get_artifact_upload(upload["upload_id"])[
                "received_bytes"
            ],
            0,
        )

        first = payload[:4]
        self.service.append_artifact_upload(
            upload["upload_id"],
            offset=0,
            data=first,
            sha256=hashlib.sha256(first).hexdigest(),
        )
        with self.assertRaises(ServiceError) as caught:
            self.service.complete_artifact_upload(upload["upload_id"])
        self.assertEqual(caught.exception.code, "incomplete_upload")

        bad_final = self.service.begin_artifact_upload(
            expected_size=len(payload),
            expected_sha256="1" * 64,
        )
        self.service.append_artifact_upload(
            bad_final["upload_id"],
            offset=0,
            data=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        with self.assertRaises(ServiceError) as caught:
            self.service.complete_artifact_upload(bad_final["upload_id"])
        self.assertEqual(caught.exception.code, "artifact_hash_mismatch")
        self.service.abort_artifact_upload(bad_final["upload_id"])

    def test_streamed_artifact_upload_rejects_oversized_chunk(self):
        upload = self.service.begin_artifact_upload(
            expected_size=8,
            expected_sha256=hashlib.sha256(b"12345678").hexdigest(),
        )
        with mock.patch.object(
            device_service_module,
            "MAX_ARTIFACT_CHUNK_BYTES",
            4,
        ):
            with self.assertRaises(ServiceError) as caught:
                self.service.append_artifact_upload(
                    upload["upload_id"],
                    offset=0,
                    data=b"12345",
                    sha256=hashlib.sha256(b"12345").hexdigest(),
                )
        self.assertEqual(caught.exception.code, "chunk_too_large")
        self.assertEqual(caught.exception.status, 413)

    def test_streamed_artifact_upload_rolls_back_failed_append(self):
        upload = self.service.begin_artifact_upload(
            expected_size=5,
            expected_sha256=hashlib.sha256(b"chunk").hexdigest(),
        )
        part = self.service.artifacts._upload_part(upload["upload_id"])
        fsync_calls = 0

        def fail_once_then_succeed(_fd):
            nonlocal fsync_calls
            fsync_calls += 1
            if fsync_calls == 1:
                raise OSError("simulated disk failure")

        with mock.patch.object(
            device_service_module.os,
            "fsync",
            side_effect=fail_once_then_succeed,
        ):
            with self.assertRaises(ServiceError) as caught:
                self.service.append_artifact_upload(
                    upload["upload_id"],
                    offset=0,
                    data=b"chunk",
                    sha256=hashlib.sha256(b"chunk").hexdigest(),
                )
        self.assertEqual(caught.exception.code, "upload_write_failed")
        self.assertEqual(part.read_bytes(), b"")
        self.assertEqual(
            self.service.get_artifact_upload(upload["upload_id"])[
                "received_bytes"
            ],
            0,
        )
        self.service.abort_artifact_upload(upload["upload_id"])

    def test_storage_gc_removes_abandoned_upload_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DeviceService(
                state_dir=Path(tmp),
                storage_policy=StoragePolicy(
                    history_ttl_seconds=0,
                    max_history_sessions=100,
                    max_history_bytes=0,
                    max_cache_bytes=0,
                    cache_grace_seconds=60,
                    min_free_bytes=0,
                    prune_interval_seconds=3600,
                ),
            )
            try:
                payload = b"abandoned staging"
                upload = service.begin_artifact_upload(
                    expected_size=len(payload),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )
                service.append_artifact_upload(
                    upload["upload_id"],
                    offset=0,
                    data=payload,
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
                upload_dir = service.artifacts._upload_dir()
                old = time.time() - 120
                for path in upload_dir.glob(f"{upload['upload_id']}.*"):
                    os.utime(path, (old, old))

                result = service.prune_storage(
                    include_cache=True,
                    now=time.time(),
                )

                self.assertEqual(result["cache"]["uploads_removed"], 2)
                self.assertFalse(
                    service.artifacts._upload_part(upload["upload_id"]).exists()
                )
                self.assertFalse(
                    service.artifacts._upload_meta(upload["upload_id"]).exists()
                )
                with self.assertRaises(ServiceError) as caught:
                    service.get_artifact_upload(upload["upload_id"])
                self.assertEqual(caught.exception.code, "unknown_upload")
            finally:
                service.close_all()

    def test_imports_webburner_package_as_normalized_firmware(self):
        package = webburner_package(build_flash())
        artifact = self.service.upload_artifact(
            package,
            name="web-probe.zip",
            content_type="application/zip",
        )

        firmware = self.service.import_firmware_package(
            {
                "device_id": "sticks3",
                "artifact_id": artifact["artifact_id"],
            }
        )

        self.assertEqual(firmware["device_id"], "sticks3")
        self.assertEqual(firmware["kind"], "manifest")
        self.assertEqual(firmware["size"], 8 << 20)
        manifest = firmware["manifest"]
        self.assertEqual(
            manifest["provenance"]["source_format"],
            "web-manifest",
        )
        self.assertEqual(
            manifest["artifact"]["kind"],
            "merged-flash",
        )
        self.assertEqual(
            manifest["artifact"]["normalized_from"],
            "segmented-flash",
        )
        self.assertEqual(len(manifest["artifact"]["source_segments"]), 3)
        self.assertEqual(
            firmware["source"]["compatibility"]["status"],
            "PASS",
        )
        self.assertTrue(self.service.firmware.path(firmware["firmware_id"]).is_file())
        self.assertFalse((self.service.state_dir / "firmware-imports").exists())

    def test_firmware_package_import_rejects_unknown_extension(self):
        artifact = self.service.upload_artifact(
            b"not a firmware package",
            name="firmware.txt",
        )
        with self.assertRaises(ServiceError) as caught:
            self.service.import_firmware_package(
                {
                    "device_id": "sticks3",
                    "artifact_id": artifact["artifact_id"],
                }
            )
        self.assertEqual(
            caught.exception.code,
            "unsupported_firmware_package",
        )

    def test_runtime_env_is_narrowly_allowlisted(self):
        with self.assertRaises(ServiceError) as caught:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "runtime_env": {"PATH": "/tmp"},
                }
            )
        self.assertEqual(caught.exception.code, "invalid_runtime_env")
        with self.assertRaises(ServiceError) as wrong_device:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "runtime_env": {"M5SW_CORE2_PMIC": "axp192"},
                }
            )
        self.assertEqual(
            wrong_device.exception.code,
            "invalid_runtime_env",
        )
        with self.assertRaises(ServiceError) as bad_variant:
            self.service.create_session(
                {
                    "device_id": "core2",
                    "runtime_env": {"M5SW_CORE2_PMIC": "axp999"},
                }
            )
        self.assertEqual(
            bad_variant.exception.code,
            "invalid_runtime_env",
        )

    def test_storage_fixture_is_bound_to_a_modeled_sd_card(self):
        artifact = self.service.upload_artifact(b"\x00" * 512)
        with self.assertRaises(ServiceError) as wrong_device:
            self.service.create_session(
                {
                    "device_id": "atoms3r",
                    "storage": {
                        "sd_image_artifact_id": artifact["artifact_id"],
                    },
                }
            )
        self.assertEqual(wrong_device.exception.code, "storage_not_supported")

        invalid_size = self.service.upload_artifact(b"\x00" * 513)
        with self.assertRaises(ServiceError) as bad_image:
            self.service.create_session(
                {
                    "device_id": "papermono",
                    "storage": {
                        "sd_image_artifact_id": invalid_size["artifact_id"],
                    },
                }
            )
        self.assertEqual(bad_image.exception.code, "invalid_storage_image")

        with self.assertRaises(ServiceError) as unknown_field:
            self.service.create_session(
                {
                    "device_id": "papermono",
                    "storage": {
                        "sd_image_artifact_id": artifact["artifact_id"],
                        "path": "/tmp/untrusted",
                    },
                }
            )
        self.assertEqual(unknown_field.exception.code, "invalid_storage")

    def test_nvs_fixture_is_partition_bound_and_session_isolated(self):
        image = build_flash_with_nvs_partition()
        firmware_artifact = self.service.upload_artifact(image)
        firmware = self.service.create_firmware(
            {
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": firmware_artifact["artifact_id"],
            }
        )
        nvs_data = build_string_nvs_image(
            0x6000,
            {
                "config": {
                    "wifi_ssid": "myssid",
                    "wifi_password": "",
                    "openaikey": "test-openai-key-not-secret",
                }
            },
        )
        nvs_artifact = self.service.upload_artifact(nvs_data)

        with mock.patch.object(
            device_service_module.DeviceSession,
            "start",
            autospec=True,
        ):
            created = self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "nvs": {
                        "partition_label": "nvs",
                        "image_artifact_id": nvs_artifact["artifact_id"],
                    },
                }
            )
        session = self.service.get_session(created["session_id"])
        self.assertEqual(session.nvs_config["offset"], 0x9000)
        self.assertEqual(session.nvs_config["size"], 0x6000)
        self.assertIn(
            nvs_artifact["artifact_id"],
            session.source_artifacts,
        )

        session.virtual_flash = session.dir / "virtual-flash.bin"
        session.virtual_flash.write_bytes(
            image.ljust(session.spec.flash_size, b"\xff")
        )
        session.flash_info = {"transport": "test-host-image"}
        session._apply_nvs_fixture()

        effective = session.virtual_flash.read_bytes()
        self.assertEqual(effective[0x9000:0xF000], nvs_data)
        self.assertEqual(
            self.service.firmware.path(firmware["firmware_id"]).read_bytes()[
                0x9000:0xF000
            ],
            b"\xff" * 0x6000,
        )
        self.assertEqual(
            self.service.artifacts.path(
                nvs_artifact["artifact_id"]
            ).read_bytes(),
            nvs_data,
        )
        self.assertTrue(session.nvs_summary_path.is_file())
        self.assertEqual(
            session.nvs_info["source_artifact_modified"],
            False,
        )
        self.assertEqual(
            session.nvs_info["effective_flash_sha256"],
            hashlib.sha256(effective).hexdigest(),
        )
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle(
            include={"manifest", "serial"}
        ))) as archive:
            self.assertIn("nvs/summary.json", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(
                manifest["nvs"]["partition_label"],
                "nvs",
            )

    def test_nvs_fixture_rejects_wrong_size_and_partition(self):
        image = build_flash_with_nvs_partition()
        firmware_artifact = self.service.upload_artifact(image)
        firmware = self.service.create_firmware(
            {
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": firmware_artifact["artifact_id"],
            }
        )
        small = self.service.upload_artifact(b"\xff" * PAGE_SIZE)
        with self.assertRaises(ServiceError) as wrong_size:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "nvs": {
                        "image_artifact_id": small["artifact_id"],
                    },
                }
            )
        self.assertEqual(wrong_size.exception.code, "invalid_nvs_image")

        exact = self.service.upload_artifact(b"\xff" * 0x6000)
        with self.assertRaises(ServiceError) as missing_partition:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "nvs": {
                        "partition_label": "settings",
                        "image_artifact_id": exact["artifact_id"],
                    },
                }
            )
        self.assertEqual(
            missing_partition.exception.code,
            "nvs_partition_not_found",
        )
        with self.assertRaises(ServiceError) as unknown_field:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "nvs": {
                        "image_artifact_id": exact["artifact_id"],
                        "path": "/tmp/untrusted",
                    },
                }
            )
        self.assertEqual(unknown_field.exception.code, "invalid_nvs")

        with self.assertRaises(ServiceError) as network_runtime:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "runtime": "network",
                    "network": {"profile": "esp-idf-http"},
                    "nvs": {
                        "image_artifact_id": exact["artifact_id"],
                    },
                }
            )
        self.assertEqual(
            network_runtime.exception.code,
            "nvs_not_supported",
        )
        self.assertIn(
            "sticks3/network",
            network_runtime.exception.message,
        )

    def test_qemu_unified_runtime_selects_single_guest_profiles(self):
        unified = device_service_module.parse_qemu_ble_execution(
            self.service.specs["sticks3"],
            {"profile": "uiflow2-sticks3-unified"},
            runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
        )
        self.assertEqual(unified["profile"], "uiflow2-sticks3-unified")
        self.assertEqual(unified["ble_linger_seconds"], 20)
        self.assertEqual(unified["ble_reconnect_cycles"], 1)
        long_link = device_service_module.parse_qemu_ble_execution(
            self.service.specs["sticks3"],
            {
                "profile": "uiflow2-sticks3-unified",
                "ble_linger_seconds": 7260,
                "ble_reconnect_cycles": 3,
                "ble_reconnect_delay_seconds": 1.5,
            },
            runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
        )
        self.assertEqual(long_link["ble_linger_seconds"], 7260)
        self.assertEqual(long_link["ble_reconnect_cycles"], 3)
        self.assertEqual(long_link["ble_reconnect_delay_seconds"], 1.5)
        with self.assertRaises(ServiceError) as invalid_linger:
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "uiflow2-sticks3-unified",
                    "ble_linger_seconds": 7261,
                },
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(invalid_linger.exception.code, "invalid_network")
        twenty_cycles = device_service_module.parse_qemu_ble_execution(
            self.service.specs["sticks3"],
            {
                "profile": "uiflow2-sticks3-unified",
                "ble_reconnect_cycles": 20,
            },
            runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
        )
        self.assertEqual(twenty_cycles["ble_reconnect_cycles"], 20)
        one_hundred_twenty_one_cycles = (
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "uiflow2-sticks3-unified",
                    "ble_reconnect_cycles": 121,
                },
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        )
        self.assertEqual(
            one_hundred_twenty_one_cycles["ble_reconnect_cycles"],
            121,
        )
        with self.assertRaises(ServiceError) as invalid_cycles:
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "uiflow2-sticks3-unified",
                    "ble_reconnect_cycles": 122,
                },
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(invalid_cycles.exception.code, "invalid_network")
        legacy = device_service_module.parse_qemu_ble_execution(
            self.service.specs["sticks3"],
            {"profile": "uiflow2-sticks3-unified"},
            runtime=device_service_module.QEMU_BLE_RUNTIME,
        )
        self.assertEqual(legacy["profile"], "uiflow2-sticks3-unified")
        nesso = device_service_module.parse_qemu_ble_execution(
            self.service.specs["nesso-n1"],
            {"profile": "nesso-unified"},
            runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
        )
        self.assertEqual(nesso["profile"], "nesso-unified")
        with self.assertRaises(ServiceError) as radio_only:
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                {"profile": "uiflow2-sticks3-wifi"},
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(
            radio_only.exception.code,
            "qemu_unified_profile_required",
        )
        with self.assertRaises(ServiceError) as unsupported_device:
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["tab5"],
                {"profile": "uiflow2-sticks3-unified"},
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(
            unsupported_device.exception.code,
            "qemu_unified_not_supported",
        )

    def test_qemu_wifi_supports_generic_s3_observe_profile(self):
        parsed = device_service_module.parse_qemu_wifi_execution(
            self.service.specs["atoms3r"],
            {
                "profile": "generic-observe",
                "expected_markers": ["got ip:"],
                "capture_pcap": True,
            },
        )
        self.assertEqual(parsed["profile"], "generic-observe")
        self.assertEqual(parsed["nic"], "misc.esp32s3.wifi")
        self.assertEqual(parsed["wifi_auth"], "open")
        self.assertTrue(parsed["capture_pcap"])
        self.assertEqual(parsed["expected_markers"], ["got ip:"])

        secured = device_service_module.parse_qemu_wifi_execution(
            self.service.specs["atoms3r"],
            {
                "profile": "generic-observe",
                "wifi_ssid": "myssid",
                "wifi_password": "mypassword",
                "wifi_auth": "wpa2-psk",
            },
        )
        self.assertEqual(secured["wifi_auth"], "wpa2-psk")
        self.assertEqual(secured["wifi_password"], "mypassword")

        with self.assertRaises(ServiceError) as unsupported:
            device_service_module.parse_qemu_wifi_execution(
                self.service.specs["atoms3r"],
                {"profile": "uiflow2-sticks3-wifi"},
            )
        self.assertEqual(
            unsupported.exception.code,
            "unsupported_network_profile",
        )
        with self.assertRaises(ServiceError) as wpa3:
            device_service_module.parse_qemu_wifi_execution(
                self.service.specs["atoms3r"],
                {
                    "profile": "generic-observe",
                    "wifi_password": "mypassword",
                    "wifi_auth": "wpa3-sae",
                },
            )
        self.assertEqual(
            wpa3.exception.code,
            "unsupported_wifi_security",
        )

    def test_qemu_wifi_binds_s3_efuse_mac_to_station_address(self):
        session_id = "a" * 32
        mac = device_service_module.qemu_station_mac(session_id)
        self.assertEqual(mac, device_service_module.qemu_station_mac(session_id))
        self.assertTrue(mac.startswith("02:"))
        self.assertEqual(len(mac.split(":")), 6)

        efuse = bytearray(64)
        device_service_module.set_s3_efuse_mac(efuse, mac)
        self.assertEqual(
            bytes(efuse[24:30]),
            bytes.fromhex(mac.replace(":", ""))[::-1],
        )
        with self.assertRaises(ValueError):
            device_service_module.set_s3_efuse_mac(bytearray(29), mac)

    def test_qemu_radio_capture_defaults_on_and_can_be_disabled(self):
        captured = device_service_module.parse_qemu_ble_execution(
            self.service.specs["sticks3"],
            {"profile": "uiflow2-sticks3-unified"},
            runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
        )
        self.assertTrue(captured["capture_pcap"])
        disabled = device_service_module.parse_qemu_ble_execution(
            self.service.specs["sticks3"],
            {
                "profile": "uiflow2-sticks3-unified",
                "capture_pcap": False,
            },
            runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
        )
        self.assertFalse(disabled["capture_pcap"])
        with self.assertRaises(ServiceError) as invalid:
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                {"capture_pcap": "yes"},
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(invalid.exception.code, "invalid_network")

        options = device_service_module.qemu_pcap_options(
            Path("/tmp/session/network.pcap")
        )
        self.assertEqual(options[0], "-object")
        self.assertIn("filter-dump", options[1])
        self.assertIn("netdev=wifi0", options[1])
        self.assertIn("file=/tmp/session/network.pcap", options[1])

    def test_network_namespace_policy_requires_linux_and_is_recorded(self):
        request = {
            "profile": "uiflow2-sticks3-unified",
            "policy": {
                "isolation": "namespace",
                "egress": "lab-only",
                "dns": "deny",
            },
        }
        with (
            mock.patch.object(
                device_service_module,
                "namespace_capability",
                return_value={
                    "status": "UNAVAILABLE",
                    "checks": {},
                    "errors": ["requires Linux"],
                },
            ),
            self.assertRaises(ServiceError) as unavailable,
        ):
            device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                request,
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(
            unavailable.exception.code,
            "network_isolation_unavailable",
        )
        with mock.patch.object(
            device_service_module,
            "namespace_capability",
            return_value={"status": "PASS", "checks": {}, "errors": []},
        ), mock.patch.object(
            device_service_module,
            "egress_capability",
            return_value={"status": "PASS", "checks": {}, "errors": []},
        ):
            parsed = device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                request,
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(parsed["policy"]["isolation"], "namespace")
        self.assertEqual(parsed["policy"]["egress"], "lab-only")
        self.assertEqual(parsed["policy"]["dns"], "deny")
        self.assertTrue(parsed["capture_pcap"])
        allowlist = dict(request)
        allowlist["policy"] = {
            "isolation": "namespace",
            "egress": "allowlist",
            "dns": "controlled",
            "allowed_hosts": ["qemu.test"],
            "allowed_domains": ["fixture.test"],
        }
        with mock.patch.object(
            device_service_module,
            "namespace_capability",
            return_value={"status": "PASS", "checks": {}, "errors": []},
        ), mock.patch.object(
            device_service_module,
            "egress_capability",
            return_value={
                "status": "UNAVAILABLE",
                "checks": {},
                "errors": ["nft unavailable"],
            },
        ):
            with self.assertRaises(ServiceError) as egress_unavailable:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["sticks3"],
                    allowlist,
                    runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
                )
        self.assertEqual(
            egress_unavailable.exception.code,
            "egress_policy_unavailable",
        )
        with mock.patch.object(
            device_service_module,
            "namespace_capability",
            return_value={"status": "PASS", "checks": {}, "errors": []},
        ), mock.patch.object(
            device_service_module,
            "egress_capability",
            return_value={"status": "PASS", "checks": {}, "errors": []},
        ):
            parsed = device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                allowlist,
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        self.assertEqual(
            parsed["policy"]["allowed_hosts"],
            ["qemu.test"],
        )
        self.assertEqual(
            parsed["policy"]["allowed_domains"],
            ["fixture.test"],
        )
        self.assertEqual(
            parsed["policy"]["allowed_endpoints"],
            [
                {
                    "protocol": "tcp",
                    "address": "10.0.2.2",
                    "port": device_service_module.UNIFIED_HTTP_PORTS[
                        device_service_module.STICKS3_UNIFIED_PROFILE
                    ],
                }
            ],
        )
        self.assertTrue(parsed["policy"]["controlled_resolver"])

    def test_controlled_domain_policy_requires_a_bound_slirp_endpoint(self):
        external = device_service_module.NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "controlled",
                "allowed_domains": ["fixture.test"],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "1.1.1.1",
                        "port": 443,
                    }
                ],
            }
        )
        with self.assertRaises(ServiceError) as missing:
            device_service_module.require_allowlist_http_fixture(
                "core2-ble-advertise",
                external,
            )
        self.assertEqual(missing.exception.code, "allowlist_not_supported")
        bound = device_service_module.NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "controlled",
                "allowed_domains": ["fixture.test"],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "10.0.2.2",
                        "port": 18443,
                    }
                ],
            }
        )
        device_service_module.require_allowlist_http_fixture(
            "core2-ble-advertise",
            bound,
        )

    def test_network_namespace_ipv6_endpoint_requires_ipv6_capability(self):
        request = {
            "profile": "uiflow2-sticks3-unified",
            "policy": {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "deny",
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "2001:db8:6d35::443",
                        "port": 443,
                    }
                ],
            },
        }
        capability = mock.Mock(
            return_value={"status": "PASS", "checks": {}, "errors": []}
        )
        with (
            mock.patch.object(
                device_service_module,
                "namespace_capability",
                return_value={"status": "PASS", "checks": {}, "errors": []},
            ),
            mock.patch.object(
                device_service_module,
                "egress_capability",
                capability,
            ),
        ):
            parsed = device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                request,
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
        capability.assert_called_once_with(
            require_gateway=True,
            require_ipv6=True,
        )
        self.assertIn(
            {
                "protocol": "tcp",
                "address": "2001:db8:6d35::443",
                "port": 443,
            },
            parsed["policy"]["allowed_endpoints"],
        )

    def test_capture_summary_is_written_after_qemu_stops(self):
        spec = self.service.specs["sticks3"]
        firmware = Path(self.tmp.name) / "capture-firmware.bin"
        firmware.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="7" * 32,
            spec=spec,
            firmware_id="8" * 64,
            firmware_path=firmware,
            firmware_sha="8" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker=None,
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-wifi",
            network_config={
                "profile": "uiflow2-sticks3-wifi",
                "nic": "misc.esp32s3.wifi",
                "net_mode": "user",
                "capture_pcap": True,
                "expected_markers": [],
                "attempts": 1,
            },
        )
        session.network_pcap.write_bytes(
            b"\xd4\xc3\xb2\xa1"
            + struct.pack("<HHiIII", 2, 4, 0, 0, 262144, 1)
        )
        summary = session._finalize_network_capture()
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["packets"], 0)
        self.assertTrue(session.network_pcap_summary.is_file())
        self.assertEqual(
            session._network_capture_evidence()["format"],
            "pcap",
        )

    def test_qemu_network_fault_uses_set_link_action(self):
        spec = self.service.specs["sticks3"]
        firmware = Path(self.tmp.name) / "fault-firmware.bin"
        firmware.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="9" * 32,
            spec=spec,
            firmware_id="a" * 64,
            firmware_path=firmware,
            firmware_sha="a" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker=None,
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-wifi",
            network_config={
                "profile": "uiflow2-sticks3-wifi",
                "nic": "misc.esp32s3.wifi",
                "net_mode": "user",
            },
        )
        with mock.patch.object(
            session,
            "_qmp_execute",
            return_value={"return": {}},
        ) as execute:
            down = session.network_fault({"action": "down"})
            up = session.network_fault({"action": "up"})
        self.assertFalse(down["network_fault"]["up"])
        self.assertTrue(up["network_fault"]["up"])
        self.assertEqual(
            execute.call_args_list,
            [
                mock.call(
                    "set_link",
                    {"name": "wifi0", "up": False},
                ),
                mock.call(
                    "set_link",
                    {"name": "wifi0", "up": True},
                ),
            ],
        )
        with self.assertRaises(ServiceError) as invalid:
            session.network_fault({"action": "cycle"})
        self.assertEqual(
            invalid.exception.code,
            "invalid_network_fault",
        )

    def test_qemu_network_fault_can_remove_and_restore_radio(self):
        spec = self.service.specs["sticks3"]
        firmware = Path(self.tmp.name) / "radio-fault-firmware.bin"
        firmware.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="a" * 32,
            spec=spec,
            firmware_id="b" * 64,
            firmware_path=firmware,
            firmware_sha="b" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker=None,
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-wifi",
            network_config={
                "profile": "uiflow2-sticks3-wifi",
                "nic": "misc.esp32s3.wifi",
                "net_mode": "user",
            },
        )
        listing = {
            "return": [
                {
                    "name": "device[0]",
                    "type": "child<misc.esp32s3.wifi>",
                },
                {
                    "name": "device[1]",
                    "type": "child<gd25q64>",
                },
            ]
        }
        properties = {
            "return": [
                {"name": "radio-enabled", "type": "bool"},
                {"name": "netdev", "type": "str"},
            ]
        }
        with (
            mock.patch.object(
                session,
                "_qmp_call",
                side_effect=[listing, properties, listing, properties],
            ) as qom_list,
            mock.patch.object(
                session,
                "_qmp_execute",
                return_value={"return": {}},
            ) as execute,
        ):
            down = session.network_fault(
                {"action": "down", "target": "radio"}
            )
            up = session.network_fault(
                {"action": "up", "target": "radio"}
            )
        self.assertEqual(
            down["network_fault"]["qom_path"],
            "/machine/unattached/device[0]",
        )
        self.assertEqual(up["network_fault"]["target"], "radio")
        self.assertEqual(qom_list.call_count, 4)
        self.assertEqual(
            execute.call_args_list,
            [
                mock.call(
                    "qom-set",
                    {
                        "path": "/machine/unattached/device[0]",
                        "property": "radio-enabled",
                        "value": False,
                    },
                ),
                mock.call(
                    "qom-set",
                    {
                        "path": "/machine/unattached/device[0]",
                        "property": "radio-enabled",
                        "value": True,
                    },
                ),
            ],
        )

    def test_network_profile_requires_supported_chip_and_elf(self):
        with self.assertRaises(ServiceError) as core2:
            device_service_module.parse_network_execution(
                self.service.specs["core2"],
                {"profile": "esp-idf-http"},
            )
        self.assertEqual(core2.exception.code, "network_not_supported")
        with self.assertRaises(ServiceError) as elf_required:
            device_service_module.parse_network_execution(
                self.service.specs["sticks3"],
                {"profile": "uiflow2-sticks3"},
            )
        self.assertEqual(elf_required.exception.code, "elf_required")
        coex = device_service_module.parse_network_execution(
            self.service.specs["nanoc6"],
            {
                "profile": "esp-idf-coex",
                "elf_artifact_id": "a" * 64,
            },
        )
        self.assertTrue(coex["ble"])
        c6 = device_service_module.parse_network_execution(
            self.service.specs["nanoc6"],
            {"profile": "esp-idf-http"},
        )
        self.assertEqual(c6["psram_size"], "0")
        wrong_password = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {"profile": "esp-idf-wrong-password"},
        )
        self.assertTrue(wrong_password["wifi"])
        self.assertFalse(wrong_password["ble"])
        self.assertFalse(wrong_password["tcp"])
        generic = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {
                "profile": "generic-observe",
                "expected_markers": ["APP_READY"],
            },
        )
        with self.assertRaises(ServiceError) as pcap_unsupported:
            device_service_module.parse_network_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "generic-observe",
                    "capture_pcap": True,
                },
            )
        self.assertEqual(
            pcap_unsupported.exception.code,
            "pcap_not_supported",
        )
        self.assertEqual(generic["expected_markers"], ["APP_READY"])
        self.assertEqual(generic["net_mode"], "user,restrict=yes")
        self.assertEqual(generic["console_mode"], "auto")
        provisioning = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {
                "profile": "generic-observe",
                "firmware_ap_password": "captive123",
                "hostfwd": [
                    {
                        "protocol": "tcp",
                        "host_port": 18080,
                        "guest_port": 80,
                    }
                ],
            },
        )
        self.assertEqual(
            provisioning["hostfwd"],
            ["tcp:127.0.0.1:18080-:80"],
        )
        self.assertEqual(
            provisioning["firmware_ap_password"],
            "captive123",
        )
        open_ap = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {
                "profile": "generic-observe",
                "firmware_ap_password": "",
            },
        )
        self.assertEqual(open_ap["firmware_ap_password"], "")
        for invalid in (
            {
                "firmware_ap_password": "short",
            },
            {
                "hostfwd": [
                    {
                        "protocol": "tcp",
                        "host_port": 80,
                        "guest_port": 80,
                    }
                ],
            },
            {
                "hostfwd": [
                    {
                        "protocol": "tcp",
                        "host_port": 18080,
                        "guest_port": 80,
                    },
                    {
                        "protocol": "tcp",
                        "host_port": 18080,
                        "guest_port": 81,
                    },
                ],
            },
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ServiceError) as bad_provisioning:
                    device_service_module.parse_network_execution(
                        self.service.specs["sticks3"],
                        {
                            "profile": "generic-observe",
                            **invalid,
                        },
                    )
                self.assertEqual(
                    bad_provisioning.exception.code,
                    "invalid_network",
                )
        bootstrapped = device_service_module.parse_network_execution(
            self.service.specs["cardputer-adv"],
            {
                "profile": "generic-observe",
                "i2c_devices": ["0:0x34,fill=0,reg=0x03=0x4a"],
            },
        )
        self.assertEqual(
            bootstrapped["i2c_devices"],
            ["0:0x34,fill=0x00,reg=0x03=0x4A"],
        )
        with self.assertRaises(ServiceError) as invalid_i2c:
            device_service_module.parse_network_execution(
                self.service.specs["cardputer-adv"],
                {
                    "profile": "generic-observe",
                    "i2c_devices": ["0:0x34,width=9"],
                },
            )
        self.assertEqual(invalid_i2c.exception.code, "invalid_network")
        with self.assertRaises(ServiceError) as generic_ble_elf:
            device_service_module.parse_network_execution(
                self.service.specs["nanoc6"],
                {
                    "profile": "generic-observe",
                    "wifi": True,
                    "ble": True,
                },
            )
        self.assertEqual(generic_ble_elf.exception.code, "elf_required")
        generic_c6 = device_service_module.parse_network_execution(
            self.service.specs["nanoc6"],
            {
                "profile": "generic-observe",
                "expected_markers": ["APP_READY"],
            },
        )
        self.assertEqual(generic_c6["console_mode"], "usb-jtag")
        dns_udp = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {"profile": "idf-dns-udp"},
        )
        self.assertFalse(dns_udp["tcp"])
        self.assertEqual(dns_udp["net_mode"], "user")
        self.assertEqual(dns_udp["console_mode"], "uart0")
        generic_open = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {
                "profile": "generic-observe",
                "net_mode": "user",
            },
        )
        self.assertEqual(generic_open["net_mode"], "user")
        with self.assertRaises(ServiceError) as invalid_mode:
            device_service_module.parse_network_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "generic-observe",
                    "net_mode": "tap,ifname=bridge0",
                },
            )
        self.assertEqual(invalid_mode.exception.code, "invalid_network")
        with self.assertRaises(ServiceError) as invalid_console:
            device_service_module.parse_network_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "generic-observe",
                    "console_mode": "vga",
                },
            )
        self.assertEqual(invalid_console.exception.code, "invalid_network")

    def test_experimental_qemu_wifi_core2_gate_and_sticks3_lane(self):
        with self.assertRaises(ServiceError) as unavailable:
            device_service_module.parse_qemu_wifi_execution(
                self.service.specs["core2"],
                {},
            )
        self.assertEqual(
            unavailable.exception.code,
            "qemu_wifi_backend_unavailable",
        )
        fake_qemu = Path(self.tmp.name) / "qemu-core2-wifi"
        fake_qemu.write_bytes(b"fake")
        fake_qemu.chmod(0o755)
        old = os.environ.get("M5_CORE2_WIFI_QEMU")
        os.environ["M5_CORE2_WIFI_QEMU"] = str(fake_qemu)
        try:
            parsed = device_service_module.parse_qemu_wifi_execution(
                self.service.specs["core2"],
                {
                    "profile": "core2-openmac",
                    "expected_markers": ["CORE2_WIFI_RESULT: PASSED"],
                },
            )
            self.assertEqual(parsed["net_mode"], "user")
            self.assertEqual(parsed["nic"], "misc.esp32_wifi")
            sticks3 = device_service_module.parse_qemu_wifi_execution(
                self.service.specs["sticks3"],
                {
                    "profile": "uiflow2-sticks3-wifi",
                    "expected_markers": ["WEATHER_READY"],
                },
            )
            self.assertEqual(sticks3["nic"], "misc.esp32s3.wifi")
            self.assertEqual(sticks3["expected_markers"], ["WEATHER_READY"])
            atoms3r = device_service_module.parse_qemu_wifi_execution(
                self.service.specs["atoms3r"],
                {"expected_markers": ["got ip:"]},
            )
            self.assertEqual(atoms3r["profile"], "generic-observe")
            self.assertEqual(atoms3r["nic"], "misc.esp32s3.wifi")
            with self.assertRaises(ServiceError) as wrong_device:
                device_service_module.parse_qemu_wifi_execution(
                    self.service.specs["nanoc6"],
                    {},
                )
            self.assertEqual(
                wrong_device.exception.code,
                "qemu_wifi_not_supported",
            )
            with self.assertRaises(ServiceError) as restricted:
                device_service_module.parse_qemu_wifi_execution(
                    self.service.specs["core2"],
                    {"net_mode": "user,restrict=on"},
                )
            self.assertEqual(restricted.exception.code, "invalid_network")
            with self.assertRaises(ServiceError) as no_http_allowlist:
                device_service_module.parse_qemu_wifi_execution(
                    self.service.specs["core2"],
                    {
                        "policy": {
                            "isolation": "namespace",
                            "egress": "allowlist",
                            "dns": "deny",
                            "allowed_hosts": ["allowed.lab.test"],
                        }
                    },
                )
            self.assertEqual(
                no_http_allowlist.exception.code,
                "allowlist_not_supported",
            )
            gated = DeviceService(
                state_dir=Path(self.tmp.name) / "qemu-wifi-service",
                max_sessions=1,
                max_per_device=1,
            )
            try:
                row = gated.get_device("core2")
                self.assertEqual(
                    row["network_profiles"],
                    [
                        "core2-native-hci",
                        "core2-native-vhci",
                        "core2-unified",
                        "core2-openmac",
                        "core2-ble-advertise",
                        "core2-hci-gatt",
                    ],
                )
                self.assertEqual(row["network_status"], "validated")
                self.assertTrue(row["features"]["network"])
                self.assertEqual(
                    gated.capacity()["modes"]["qemu-unified"],
                    "enabled-sticks3-cores3-cardputer-adv-stopwatch-atoms3r-papercolor-papermono-stackchan-stamplc-core2-c6-wifi-ble",
                )
                self.assertEqual(
                    gated.capacity()["modes"]["qemu-wifi"],
                    "enabled-s3-and-core2",
                )
                self.assertEqual(
                    gated.capacity()["modes"]["qemu-ble"],
                    "enabled-core2-experimental-nanoc6-hci-nesso-hci",
                )
            finally:
                gated.close_all()
        finally:
            if old is None:
                os.environ.pop("M5_CORE2_WIFI_QEMU", None)
            else:
                os.environ["M5_CORE2_WIFI_QEMU"] = old

    def test_qemu_ble_profiles_and_core2_environment_gate(self):
        fake_qemu = Path(self.tmp.name) / "qemu-core2-radio"
        fake_qemu.write_bytes(b"fake")
        fake_qemu.chmod(0o755)
        fake_gdb = Path(self.tmp.name) / "xtensa-gdb"
        fake_gdb.write_bytes(b"fake")
        fake_gdb.chmod(0o755)
        old_radio = os.environ.get("M5_CORE2_RADIO_QEMU")
        old_wifi = os.environ.get("M5_CORE2_WIFI_QEMU")
        old_gdb = os.environ.get("M5_XTENSA_GDB")
        os.environ.pop("M5_CORE2_WIFI_QEMU", None)
        os.environ["M5_CORE2_RADIO_QEMU"] = str(fake_qemu)
        os.environ["M5_XTENSA_GDB"] = str(fake_gdb)
        try:
            parsed = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {
                    "profile": "core2-ble-advertise",
                    "expected_markers": ["CORE2_BLE_RESULT: PASSED"],
                },
            )
            self.assertEqual(parsed["profile"], "core2-ble-advertise")
            with self.assertRaises(ServiceError) as no_http_allowlist:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["core2"],
                    {
                        "profile": "core2-ble-advertise",
                        "policy": {
                            "isolation": "namespace",
                            "egress": "allowlist",
                            "dns": "deny",
                            "allowed_hosts": ["allowed.lab.test"],
                        },
                    },
                )
            self.assertEqual(
                no_http_allowlist.exception.code,
                "allowlist_not_supported",
            )
            hci_gatt = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {"profile": "core2-hci-gatt"},
            )
            self.assertEqual(hci_gatt["profile"], "core2-hci-gatt")
            self.assertEqual(
                hci_gatt["expected_markers"],
                list(device_service_module.CORE2_HCI_GATT_MARKERS),
            )
            core2_unified = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {"profile": "core2-unified"},
            )
            self.assertEqual(core2_unified["profile"], "core2-unified")
            self.assertEqual(
                core2_unified["expected_markers"],
                list(device_service_module.CORE2_UNIFIED_MARKERS),
            )
            elf_artifact_id = "a" * 64
            native_vhci = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {
                    "profile": "core2-native-vhci",
                    "elf_artifact_id": elf_artifact_id,
                },
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
            self.assertEqual(
                native_vhci["profile"],
                "core2-native-vhci",
            )
            self.assertEqual(
                native_vhci["expected_markers"],
                list(device_service_module.CORE2_UNIFIED_MARKERS),
            )
            self.assertEqual(
                native_vhci["elf_artifact_id"],
                elf_artifact_id,
            )
            native_hci = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {
                    "profile": "core2-native-hci",
                    "elf_artifact_id": elf_artifact_id,
                },
                runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
            )
            self.assertEqual(
                native_hci["profile"],
                "core2-native-hci",
            )
            self.assertEqual(
                native_hci["expected_markers"],
                list(device_service_module.CORE2_UNIFIED_MARKERS),
            )
            self.assertEqual(
                native_hci["elf_artifact_id"],
                elf_artifact_id,
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.CORE2_UNIFIED_PROFILE
                ],
                18089,
            )
            nanoc6 = device_service_module.parse_qemu_ble_execution(
                self.service.specs["nanoc6"],
                {},
            )
            self.assertEqual(nanoc6["profile"], "nanoc6-hci-ble")
            self.assertEqual(nanoc6["nic"], "misc.esp32c6.wifi")
            self.assertEqual(
                nanoc6["expected_markers"],
                list(device_service_module.NANOC6_HCI_BLE_MARKERS),
            )
            self.assertEqual(
                nanoc6["ble_name"],
                "M5-NANOC6-HCI",
            )
            nesso = device_service_module.parse_qemu_ble_execution(
                self.service.specs["nesso-n1"],
                {},
            )
            self.assertEqual(nesso["profile"], "nesso-unified")
            self.assertEqual(nesso["nic"], "misc.esp32c6.wifi")
            self.assertEqual(
                nesso["expected_markers"],
                list(device_service_module.NESSO_UNIFIED_MARKERS),
            )
            self.assertEqual(
                nesso["ble_name"],
                "M5-NESSO-UNIFIED",
            )
            unified = device_service_module.parse_qemu_ble_execution(
                self.service.specs["sticks3"],
                {},
            )
            self.assertEqual(
                unified["profile"],
                "uiflow2-sticks3-unified",
            )
            self.assertEqual(unified["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                unified["expected_markers"],
                list(device_service_module.STICKS3_UNIFIED_MARKERS),
            )
            cores3 = device_service_module.parse_qemu_ble_execution(
                self.service.specs["cores3"],
                {},
            )
            self.assertEqual(
                cores3["profile"],
                "uiflow2-cores3-unified",
            )
            self.assertEqual(cores3["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                cores3["expected_markers"],
                list(device_service_module.CORES3_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.CORES3_UNIFIED_PROFILE
                ],
                18081,
            )
            cardputer = device_service_module.parse_qemu_ble_execution(
                self.service.specs["cardputer-adv"],
                {},
            )
            self.assertEqual(
                cardputer["profile"],
                "uiflow2-cardputer-adv-unified",
            )
            self.assertEqual(cardputer["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                cardputer["expected_markers"],
                list(device_service_module.CARDPUTER_ADV_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.CARDPUTER_ADV_UNIFIED_PROFILE
                ],
                18082,
            )
            stopwatch = device_service_module.parse_qemu_ble_execution(
                self.service.specs["stopwatch"],
                {},
            )
            self.assertEqual(
                stopwatch["profile"],
                "uiflow2-stopwatch-unified",
            )
            self.assertEqual(stopwatch["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                stopwatch["expected_markers"],
                list(device_service_module.STOPWATCH_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.STOPWATCH_UNIFIED_PROFILE
                ],
                18083,
            )
            atoms3r = device_service_module.parse_qemu_ble_execution(
                self.service.specs["atoms3r"],
                {},
            )
            self.assertEqual(
                atoms3r["profile"],
                "uiflow2-atoms3r-unified",
            )
            self.assertEqual(atoms3r["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                atoms3r["expected_markers"],
                list(device_service_module.ATOMS3R_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.ATOMS3R_UNIFIED_PROFILE
                ],
                18084,
            )
            papercolor = device_service_module.parse_qemu_ble_execution(
                self.service.specs["papercolor"],
                {},
            )
            self.assertEqual(
                papercolor["profile"],
                "uiflow2-papercolor-unified",
            )
            self.assertEqual(papercolor["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                papercolor["expected_markers"],
                list(device_service_module.PAPERCOLOR_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.PAPERCOLOR_UNIFIED_PROFILE
                ],
                18085,
            )
            papermono = device_service_module.parse_qemu_ble_execution(
                self.service.specs["papermono"],
                {},
            )
            self.assertEqual(
                papermono["profile"],
                "uiflow2-papermono-unified",
            )
            self.assertEqual(papermono["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                papermono["expected_markers"],
                list(device_service_module.PAPERMONO_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.PAPERMONO_UNIFIED_PROFILE
                ],
                18086,
            )
            stackchan = device_service_module.parse_qemu_ble_execution(
                self.service.specs["stackchan"],
                {},
            )
            self.assertEqual(
                stackchan["profile"],
                "uiflow2-stackchan-unified",
            )
            self.assertEqual(stackchan["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                stackchan["expected_markers"],
                list(device_service_module.STACKCHAN_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.STACKCHAN_UNIFIED_PROFILE
                ],
                18087,
            )
            stamplc = device_service_module.parse_qemu_ble_execution(
                self.service.specs["stamplc"],
                {},
            )
            self.assertEqual(
                stamplc["profile"],
                "uiflow2-stamplc-unified",
            )
            self.assertEqual(stamplc["nic"], "misc.esp32s3.wifi")
            self.assertEqual(
                stamplc["expected_markers"],
                list(device_service_module.STAMPLC_UNIFIED_MARKERS),
            )
            self.assertEqual(
                device_service_module.UNIFIED_HTTP_PORTS[
                    device_service_module.STAMPLC_UNIFIED_PROFILE
                ],
                18088,
            )
            with self.assertRaises(ServiceError) as wrong_device:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["tab5"],
                    {},
                )
            self.assertEqual(
                wrong_device.exception.code,
                "qemu_ble_not_supported",
            )
            with self.assertRaises(ServiceError) as wrong_profile:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["core2"],
                    {"profile": "core2-openmac"},
                )
            self.assertEqual(
                wrong_profile.exception.code,
                "unsupported_network_profile",
            )
            with self.assertRaises(ServiceError) as missing_elf:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["core2"],
                    {"profile": "core2-native-vhci"},
                    runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
                )
            self.assertEqual(missing_elf.exception.code, "elf_required")
            with self.assertRaises(ServiceError) as native_hci_missing_elf:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["core2"],
                    {"profile": "core2-native-hci"},
                    runtime=device_service_module.QEMU_UNIFIED_RUNTIME,
                )
            self.assertEqual(
                native_hci_missing_elf.exception.code,
                "elf_required",
            )
        finally:
            if old_radio is None:
                os.environ.pop("M5_CORE2_RADIO_QEMU", None)
            else:
                os.environ["M5_CORE2_RADIO_QEMU"] = old_radio
            if old_wifi is None:
                os.environ.pop("M5_CORE2_WIFI_QEMU", None)
            else:
                os.environ["M5_CORE2_WIFI_QEMU"] = old_wifi
            if old_gdb is None:
                os.environ.pop("M5_XTENSA_GDB", None)
            else:
                os.environ["M5_XTENSA_GDB"] = old_gdb

    def test_network_session_runs_isolated_lane_and_retains_evidence(self):
        fake_lane = Path(self.tmp.name) / "fake-network-lane.py"
        fake_lane.write_text(
            "#!/usr/bin/env python3\n"
            "import argparse,json,pathlib,sys\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('--out-dir',type=pathlib.Path,required=True)\n"
            "a,_=p.parse_known_args()\n"
            "a.out_dir.mkdir(parents=True,exist_ok=True)\n"
            "(a.out_dir/'argv.json').write_text(json.dumps(sys.argv[1:]))\n"
            "(a.out_dir/'serial.log').write_text('LANE_DONE\\n')\n"
            "e={'status':'PASS','checks':{'wifi_dhcp':True}}\n"
            "(a.out_dir/'evidence.json').write_text(json.dumps(e))\n"
            "print(json.dumps(e))\n"
        )
        fake_lane.chmod(0o755)
        fake_emulator = Path(self.tmp.name) / "esp-emu"
        fake_emulator.write_bytes(b"fake")
        old_lane = device_service_module.NETWORK_LANE
        device_service_module.NETWORK_LANE = fake_lane
        old_emulator = os.environ.get("M5_NETWORK_EMULATOR")
        os.environ["M5_NETWORK_EMULATOR"] = str(fake_emulator)
        try:
            artifact = self.service.upload_artifact(b"\xe9" + b"X" * 1023)
            firmware = self.service.create_firmware(
                {
                    "device_id": "sticks3",
                    "kind": "merged",
                    "artifact_id": artifact["artifact_id"],
                }
            )
            created = self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "runtime": "network",
                    "network": {
                        "profile": "esp-idf-http",
                        "timeout_seconds": 10,
                    },
                }
            )
            session = self.service.get_session(created["session_id"])
            sid = session.id
            deadline = time.time() + 5
            while time.time() < deadline and session.state in {
                "provisioning",
                "flashing",
                "booting",
                "running",
            }:
                time.sleep(0.02)
            snapshot = session.snapshot()
            self.assertEqual(snapshot["runtime"], "network")
            self.assertEqual(snapshot["state"], "stopped")
            self.assertEqual(snapshot["network"]["status"], "PASS")
            self.assertEqual(
                session.network_evidence()["checks"]["wifi_dhcp"],
                True,
            )
            argv = json.loads((session.network_dir / "argv.json").read_text())
            net_mode_index = argv.index("--net-mode")
            self.assertEqual(argv[net_mode_index + 1], "user")
            console_mode_index = argv.index("--console-mode")
            self.assertEqual(argv[console_mode_index + 1], "uart0")
            bundle = session.evidence_bundle(
                {"manifest", "network", "serial", "logs"}
            )
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                self.assertIn("network/evidence.json", archive.namelist())
                self.assertIn("network-runner.stdout", archive.namelist())
            self.service.close_all()
            restored_service = DeviceService(
                state_dir=Path(self.tmp.name),
                max_sessions=1,
                max_per_device=1,
            )
            try:
                restored = restored_service.get_session(sid).snapshot()
                self.assertEqual(restored["runtime"], "network")
                self.assertEqual(restored["network"]["status"], "PASS")
            finally:
                restored_service.close_all()
        finally:
            device_service_module.NETWORK_LANE = old_lane
            if old_emulator is None:
                os.environ.pop("M5_NETWORK_EMULATOR", None)
            else:
                os.environ["M5_NETWORK_EMULATOR"] = old_emulator

    def test_generic_network_session_passes_restricted_backend(self):
        fake_lane = Path(self.tmp.name) / "fake-network-lane.py"
        fake_lane.write_text(
            "#!/usr/bin/env python3\n"
            "import argparse,json,pathlib,sys\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('--out-dir',type=pathlib.Path,required=True)\n"
            "a,_=p.parse_known_args()\n"
            "a.out_dir.mkdir(parents=True,exist_ok=True)\n"
            "(a.out_dir/'argv.json').write_text(json.dumps(sys.argv[1:]))\n"
            "e={'status':'PARTIAL','checks':{}}\n"
            "(a.out_dir/'evidence.json').write_text(json.dumps(e))\n"
            "print(json.dumps(e))\n"
        )
        fake_lane.chmod(0o755)
        fake_emulator = Path(self.tmp.name) / "esp-emu"
        fake_emulator.write_bytes(b"fake")
        old_lane = device_service_module.NETWORK_LANE
        device_service_module.NETWORK_LANE = fake_lane
        old_emulator = os.environ.get("M5_NETWORK_EMULATOR")
        os.environ["M5_NETWORK_EMULATOR"] = str(fake_emulator)
        try:
            artifact = self.service.upload_artifact(b"\xe9" + b"X" * 1023)
            firmware = self.service.create_firmware(
                {
                    "device_id": "sticks3",
                    "kind": "merged",
                    "artifact_id": artifact["artifact_id"],
                }
            )
            created = self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "runtime": "network",
                    "network": {
                        "profile": "generic-observe",
                        "timeout_seconds": 10,
                        "expected_markers": ["APP_READY"],
                        "firmware_ap_password": "captive123",
                        "hostfwd": [
                            {
                                "protocol": "tcp",
                                "host_port": 18080,
                                "guest_port": 80,
                            }
                        ],
                        "i2c_devices": [
                            "0:0x34,fill=0,reg=0x03=0x4a"
                        ],
                    },
                }
            )
            session = self.service.get_session(created["session_id"])
            deadline = time.time() + 5
            while (
                time.time() < deadline
                and session.state in {
                    "provisioning",
                    "flashing",
                    "booting",
                    "running",
                }
            ):
                time.sleep(0.02)
            self.assertEqual(session.snapshot()["state"], "stopped")
            argv = json.loads((session.network_dir / "argv.json").read_text())
            net_mode_index = argv.index("--net-mode")
            self.assertEqual(
                argv[net_mode_index + 1],
                "user,restrict=yes",
            )
            console_mode_index = argv.index("--console-mode")
            self.assertEqual(argv[console_mode_index + 1], "auto")
            i2c_index = argv.index("--i2c-dev")
            self.assertEqual(
                argv[i2c_index + 1],
                "0:0x34,fill=0x00,reg=0x03=0x4A",
            )
            firmware_ap_index = argv.index("--firmware-ap-password")
            self.assertEqual(
                argv[firmware_ap_index + 1],
                "captive123",
            )
            hostfwd_index = argv.index("--hostfwd")
            self.assertEqual(
                argv[hostfwd_index + 1],
                "tcp:127.0.0.1:18080-:80",
            )
            persisted = json.loads(
                (session.dir / "session.json").read_text()
            )
            self.assertEqual(
                persisted["network"]["wifi_password"],
                "<redacted>",
            )
            self.assertEqual(
                persisted["network"]["firmware_ap_password"],
                "<redacted>",
            )
            self.assertNotIn(
                "mypassword",
                (session.dir / "session.json").read_text(),
            )
            self.assertNotIn(
                "captive123",
                (session.dir / "session.json").read_text(),
            )
        finally:
            device_service_module.NETWORK_LANE = old_lane
            if old_emulator is None:
                os.environ.pop("M5_NETWORK_EMULATOR", None)
            else:
                os.environ["M5_NETWORK_EMULATOR"] = old_emulator

    def test_network_session_stop_collects_runner_evidence(self):
        fake_lane = Path(self.tmp.name) / "graceful-network-lane.py"
        fake_lane.write_text(
            "#!/usr/bin/env python3\n"
            "import argparse,json,pathlib,signal,sys,time\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('--out-dir',type=pathlib.Path,required=True)\n"
            "a,_=p.parse_known_args()\n"
            "a.out_dir.mkdir(parents=True,exist_ok=True)\n"
            "def stop(_signum,_frame):\n"
            "    e={'status':'PARTIAL','checks':{},'stop_requested':True}\n"
            "    (a.out_dir/'evidence.json').write_text(json.dumps(e))\n"
            "    sys.exit(0)\n"
            "signal.signal(signal.SIGTERM,stop)\n"
            "while True: time.sleep(0.1)\n"
        )
        fake_lane.chmod(0o755)
        fake_emulator = Path(self.tmp.name) / "esp-emu"
        fake_emulator.write_bytes(b"fake")
        old_lane = device_service_module.NETWORK_LANE
        device_service_module.NETWORK_LANE = fake_lane
        old_emulator = os.environ.get("M5_NETWORK_EMULATOR")
        os.environ["M5_NETWORK_EMULATOR"] = str(fake_emulator)
        try:
            artifact = self.service.upload_artifact(b"\xe9" + b"X" * 1023)
            firmware = self.service.create_firmware(
                {
                    "device_id": "sticks3",
                    "kind": "merged",
                    "artifact_id": artifact["artifact_id"],
                }
            )
            created = self.service.create_session(
                {
                    "device_id": "sticks3",
                    "firmware_id": firmware["firmware_id"],
                    "runtime": "network",
                    "network": {
                        "profile": "generic-observe",
                        "timeout_seconds": 60,
                    },
                }
            )
            session = self.service.get_session(created["session_id"])
            deadline = time.time() + 5
            while time.time() < deadline:
                if session.state == "running":
                    break
                time.sleep(0.02)
            self.assertEqual(session.state, "running")
            time.sleep(0.1)
            stopped = session.stop(purge=False)
            self.assertEqual(stopped["state"], "stopped")
            self.assertEqual(stopped["network"]["status"], "PARTIAL")
            evidence = json.loads(
                (session.network_dir / "evidence.json").read_text()
            )
            self.assertTrue(evidence["stop_requested"])
        finally:
            device_service_module.NETWORK_LANE = old_lane
            if old_emulator is None:
                os.environ.pop("M5_NETWORK_EMULATOR", None)
            else:
                os.environ["M5_NETWORK_EMULATOR"] = old_emulator

    def test_network_wait_does_not_return_on_running_state(self):
        class FakeSession:
            def __init__(self):
                self.calls = 0

            def snapshot(self):
                self.calls += 1
                if self.calls < 3:
                    return {"state": "running", "network": {"status": "RUNNING"}}
                return {"state": "stopped", "network": {"status": "PASS"}}

        session = FakeSession()
        result = _wait_for_session(
            session,
            {"wait_for_completion": True, "timeout_seconds": 1},
        )
        self.assertEqual(result["state"], "stopped")
        self.assertGreaterEqual(session.calls, 3)

    def test_qemu_wifi_network_evidence_and_bundle(self):
        spec = self.service.specs["core2"]
        firmware_path = Path(self.tmp.name) / "core2-firmware.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="b" * 32,
            spec=spec,
            firmware_id="c" * 64,
            firmware_path=firmware_path,
            firmware_sha="c" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="CORE2_WIFI_RESULT: PASSED",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-wifi",
            network_config={
                "profile": "core2-openmac",
                "net_mode": "user",
                "nic": "misc.esp32_wifi",
                "expected_markers": [
                    "CORE2_WIFI_SCAN_OK 3",
                    "CORE2_WIFI_RESULT: PASSED",
                ],
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "CORE2_WIFI_SCAN_OK 3\n"
            "CORE2_WIFI_RESULT: PASSED\n"
        )
        evidence = session.network_evidence()
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertTrue(session.snapshot()["display_available"])
        bundle = session.evidence_bundle({"manifest", "serial", "network"})
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn("network/evidence.json", archive.namelist())
            self.assertIn("serial.log", archive.namelist())
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_qemu_ble_network_evidence_scope(self):
        spec = self.service.specs["core2"]
        firmware_path = Path(self.tmp.name) / "core2-ble.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="d" * 32,
            spec=spec,
            firmware_id="e" * 64,
            firmware_path=firmware_path,
            firmware_sha="e" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="CORE2_BLE_RESULT: PASSED",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "core2-ble-advertise",
                "expected_markers": [
                    "CORE2_BLE_ACTIVE True",
                    "CORE2_BLE_RESULT: PASSED",
                ],
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "CORE2_BLE_ACTIVE True\n"
            "CORE2_BLE_RESULT: PASSED\n"
        )
        evidence = session.network_evidence()
        self.assertEqual(evidence["kind"], "m5stack-qemu-ble-proof")
        self.assertEqual(evidence["status"], "PASS")
        self.assertIn("WiFi", evidence["not_claimed"])
        self.assertIn("external BLE peer/GATT", evidence["not_claimed"])
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_qemu_ble_hci_gatt_evidence_and_bundle(self):
        spec = self.service.specs["core2"]
        firmware_path = Path(self.tmp.name) / "core2-hci-gatt.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="1" * 32,
            spec=spec,
            firmware_id="2" * 64,
            firmware_path=firmware_path,
            firmware_sha="2" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="CORE2_HCI_BLE_ACK_SENT",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "core2-hci-gatt",
                "expected_markers": list(
                    device_service_module.CORE2_HCI_GATT_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "CORE2_HCI_BLE_READY\n"
            "CORE2_HCI_BLE_RX b'M5_CORE2_HCI'\n"
            "CORE2_HCI_BLE_ACK_SENT\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_CORE2_HCI\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_CORE2_HCI\n"
            "BLE_BUMBLE_PASS\n"
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-qemu-ble-hci-gatt-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertIn(
            "native ESP32 Bluetooth radio/controller model",
            evidence["not_claimed"],
        )
        bundle = session.evidence_bundle({"manifest", "serial", "logs", "network"})
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn("network/evidence.json", archive.namelist())
            self.assertIn("ble-probe.log", archive.namelist())
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_hci_probe_wait_allows_multi_cycle_completion_after_30_seconds(
        self,
    ):
        spec = self.service.specs["core2"]
        firmware_path = Path(self.tmp.name) / "core2-reconnect-timeout.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="9" * 32,
            spec=spec,
            firmware_id="8" * 64,
            firmware_path=firmware_path,
            firmware_sha="8" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_CORE2_READY",
            ready_timeout=120,
            ready_conditions=None,
            runtime="qemu-unified",
            network_config={
                "profile": "core2-native-hci",
                "expected_markers": [],
                "attempts": 1,
                "ble_reconnect_cycles": 10,
            },
        )
        session.hci_probe_log.write_text("BLE_PROBE_READY\n")
        session._hci_probe = mock.Mock()
        session._hci_probe.poll.return_value = None
        clock = {"now": 0.0}

        def sleep_and_complete(_: float) -> None:
            clock["now"] += 5.0
            if clock["now"] >= 45.0:
                session.hci_probe_log.write_text(
                    "BLE_PROBE_READY\n"
                    "BLE_BUMBLE_CYCLE_PASS 10\n"
                    "BLE_BUMBLE_PASS cycles=10\n"
                )

        with (
            mock.patch.object(
                device_service_module.time,
                "time",
                side_effect=lambda: clock["now"],
            ),
            mock.patch.object(
                device_service_module.time,
                "sleep",
                side_effect=sleep_and_complete,
            ),
        ):
            session._wait_hci_probe_result(120)

        self.assertGreaterEqual(clock["now"], 45.0)
        session._hci_probe = None
        session.state = "stopped"

    def test_hci_probe_post_pass_continuity_trigger_is_explicit(self):
        spec = self.service.specs["sticks3"]
        firmware_path = Path(self.tmp.name) / "sticks3-continuity.bin"
        firmware_path.write_bytes(b"\xff" * spec.flash_size)
        session = DeviceSession(
            self.service,
            session_id="c" * 32,
            spec=spec,
            firmware_id="d" * 64,
            firmware_path=firmware_path,
            firmware_sha="d" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_STICKS3_READY",
            ready_timeout=123,
            ready_conditions=None,
            runtime="qemu-unified",
            network_config={
                "profile": device_service_module.STICKS3_UNIFIED_PROFILE,
                "attempts": 1,
                "ble_post_pass_continuity": True,
            },
            persist=False,
        )
        command, _ = session._hci_probe_command()
        self.assertIn("--post-pass-trigger", command)
        trigger_index = command.index("--post-pass-trigger") + 1
        self.assertEqual(
            command[trigger_index],
            str(session.dir / "ble-continuity.trigger"),
        )
        timeout_index = command.index("--post-pass-trigger-timeout") + 1
        self.assertEqual(command[timeout_index], "123")

    def test_sticks3_unified_qemu_evidence_and_bundle(self):
        spec = self.service.specs["sticks3"]
        firmware_path = Path(self.tmp.name) / "sticks3-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="3" * 32,
            spec=spec,
            firmware_id="4" * 64,
            firmware_path=firmware_path,
            firmware_sha="4" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_STICKS3_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-unified",
            network_config={
                "profile": "uiflow2-sticks3-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.STICKS3_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_STICKS3_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_STICKS3_HTTP_PASS\n"
            "UNIFIED_STICKS3_BLE_RX b'M5_STICKS3_UNIFIED'\n"
            "UNIFIED_STICKS3_BLE_ACK_SENT\n"
            "UNIFIED_STICKS3_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-STICKS3-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_STICKS3_UNIFIED\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_STICKS3_UNIFIED\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-sticks3-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(
            evidence["runtime"]["guest_process_count"],
            1,
        )
        bundle = session.evidence_bundle(
            {"manifest", "serial", "logs", "network"}
        )
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn("network/evidence.json", archive.namelist())
            self.assertIn("ble-probe.log", archive.namelist())
            self.assertIn("http-fixture.json", archive.namelist())
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_cores3_unified_qemu_evidence(self):
        spec = self.service.specs["cores3"]
        firmware_path = Path(self.tmp.name) / "cores3-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="5" * 32,
            spec=spec,
            firmware_id="6" * 64,
            firmware_path=firmware_path,
            firmware_sha="6" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_CORES3_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-cores3-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.CORES3_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_CORES3_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_CORES3_HTTP_PASS\n"
            "UNIFIED_CORES3_BLE_RX b'M5_CORES3_UNIFIED'\n"
            "UNIFIED_CORES3_BLE_ACK_SENT\n"
            "UNIFIED_CORES3_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-CORES3-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_CORES3_UNIFIED\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_CORES3_UNIFIED\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-cores3-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(
            evidence["gatt"]["payload"],
            "M5_CORES3_UNIFIED",
        )
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_stop_failed_session_releases_unified_fixture(self):
        spec = self.service.specs["cores3"]
        firmware_path = Path(self.tmp.name) / "failed-cores3.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="7" * 32,
            spec=spec,
            firmware_id="8" * 64,
            firmware_path=firmware_path,
            firmware_sha="8" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_CORES3_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={"profile": "uiflow2-cores3-unified"},
        )

        class FakeFixture:
            closed = False

            def close(self):
                self.closed = True

        fixture = FakeFixture()
        session.state = "failed"
        session._http_fixture = fixture
        result = session.stop(purge=False)
        self.assertEqual(result["state"], "failed")
        self.assertTrue(fixture.closed)
        self.assertIsNone(session._http_fixture)

    def test_cardputer_unified_qemu_evidence(self):
        spec = self.service.specs["cardputer-adv"]
        firmware_path = Path(self.tmp.name) / "cardputer-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="9" * 32,
            spec=spec,
            firmware_id="a" * 64,
            firmware_path=firmware_path,
            firmware_sha="a" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_CARDPUTER_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-cardputer-adv-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.CARDPUTER_ADV_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_CARDPUTER_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_CARDPUTER_HTTP_PASS\n"
            "UNIFIED_CARDPUTER_BLE_RX b'M5_CPTR_ADV'\n"
            "UNIFIED_CARDPUTER_BLE_ACK_SENT\n"
            "UNIFIED_CARDPUTER_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-CPTR-ADV-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_CPTR_ADV\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_CPTR_ADV\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-cardputer-adv-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["gatt"]["name"], "M5-CPTR-ADV-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_CPTR_ADV")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_stopwatch_unified_qemu_evidence(self):
        spec = self.service.specs["stopwatch"]
        firmware_path = Path(self.tmp.name) / "stopwatch-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="b" * 32,
            spec=spec,
            firmware_id="c" * 64,
            firmware_path=firmware_path,
            firmware_sha="c" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_STOPWATCH_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-stopwatch-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.STOPWATCH_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_STOPWATCH_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_STOPWATCH_HTTP_PASS\n"
            "UNIFIED_STOPWATCH_BLE_RX b'M5_STOPWATCH_U'\n"
            "UNIFIED_STOPWATCH_BLE_ACK_SENT\n"
            "UNIFIED_STOPWATCH_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-STOPWATCH-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_STOPWATCH_U\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_STOPWATCH_U\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-stopwatch-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["gatt"]["name"], "M5-STOPWATCH-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_STOPWATCH_U")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_atoms3r_unified_qemu_evidence(self):
        spec = self.service.specs["atoms3r"]
        firmware_path = Path(self.tmp.name) / "atoms3r-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="d" * 32,
            spec=spec,
            firmware_id="e" * 64,
            firmware_path=firmware_path,
            firmware_sha="e" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_ATOMS3R_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-atoms3r-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.ATOMS3R_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_ATOMS3R_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_ATOMS3R_HTTP_PASS\n"
            "UNIFIED_ATOMS3R_BLE_RX b'M5_ATOMS3R_U'\n"
            "UNIFIED_ATOMS3R_BLE_ACK_SENT\n"
            "UNIFIED_ATOMS3R_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-ATOMS3R-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_ATOMS3R_U\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_ATOMS3R_U\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-atoms3r-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["gatt"]["name"], "M5-ATOMS3R-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_ATOMS3R_U")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_papercolor_unified_qemu_evidence(self):
        spec = self.service.specs["papercolor"]
        firmware_path = Path(self.tmp.name) / "papercolor-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="f" * 32,
            spec=spec,
            firmware_id="1" * 64,
            firmware_path=firmware_path,
            firmware_sha="1" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_PAPERCOLOR_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-papercolor-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.PAPERCOLOR_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_PAPERCOLOR_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_PAPERCOLOR_HTTP_PASS\n"
            "UNIFIED_PAPERCOLOR_BLE_RX b'M5_PAPERCOLOR_U'\n"
            "UNIFIED_PAPERCOLOR_BLE_ACK_SENT\n"
            "UNIFIED_PAPERCOLOR_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-PAPERCOLOR-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_PAPERCOLOR_U\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_PAPERCOLOR_U\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-papercolor-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["gatt"]["name"], "M5-PAPERCOLOR-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_PAPERCOLOR_U")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_papermono_unified_qemu_evidence(self):
        spec = self.service.specs["papermono"]
        firmware_path = Path(self.tmp.name) / "papermono-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="e" * 32,
            spec=spec,
            firmware_id="2" * 64,
            firmware_path=firmware_path,
            firmware_sha="2" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_PAPERMONO_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-papermono-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.PAPERMONO_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_PAPERMONO_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_PAPERMONO_HTTP_PASS\n"
            "UNIFIED_PAPERMONO_BLE_RX b'M5_PAPERMONO_U'\n"
            "UNIFIED_PAPERMONO_BLE_ACK_SENT\n"
            "UNIFIED_PAPERMONO_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-PAPERMONO-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_PAPERMONO_U\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_PAPERMONO_U\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-papermono-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["gatt"]["name"], "M5-PAPERMONO-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_PAPERMONO_U")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_stackchan_unified_qemu_evidence(self):
        spec = self.service.specs["stackchan"]
        firmware_path = Path(self.tmp.name) / "stackchan-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="d" * 32,
            spec=spec,
            firmware_id="3" * 64,
            firmware_path=firmware_path,
            firmware_sha="3" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_STACKCHAN_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-stackchan-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.STACKCHAN_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_STACKCHAN_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_STACKCHAN_HTTP_PASS\n"
            "UNIFIED_STACKCHAN_BLE_RX b'M5_STACKCHAN_U'\n"
            "UNIFIED_STACKCHAN_BLE_ACK_SENT\n"
            "UNIFIED_STACKCHAN_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-STACKCHAN-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_STACKCHAN_U\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_STACKCHAN_U\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-stackchan-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["runtime"]["hci_transport"], "UART2 H4")
        self.assertEqual(evidence["gatt"]["name"], "M5-STACKCHAN-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_STACKCHAN_U")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_stamplc_unified_qemu_evidence(self):
        spec = self.service.specs["stamplc"]
        firmware_path = Path(self.tmp.name) / "stamplc-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="c" * 32,
            spec=spec,
            firmware_id="4" * 64,
            firmware_path=firmware_path,
            firmware_sha="4" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_STAMPLC_READY",
            ready_timeout=10,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "uiflow2-stamplc-unified",
                "nic": "misc.esp32s3.wifi",
                "expected_markers": list(
                    device_service_module.STAMPLC_UNIFIED_MARKERS
                ),
                "attempts": 5,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_STAMPLC_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_STAMPLC_HTTP_PASS\n"
            "UNIFIED_STAMPLC_BLE_RX b'M5_STAMPLC_U'\n"
            "UNIFIED_STAMPLC_BLE_ACK_SENT\n"
            "UNIFIED_STAMPLC_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-STAMPLC-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_STAMPLC_U\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_STAMPLC_U\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-stamplc-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["runtime"]["hci_transport"], "UART1 H4")
        self.assertEqual(evidence["gatt"]["name"], "M5-STAMPLC-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_STAMPLC_U")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_core2_unified_qemu_evidence(self):
        spec = self.service.specs["core2"]
        firmware_path = Path(self.tmp.name) / "core2-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="b" * 32,
            spec=spec,
            firmware_id="5" * 64,
            firmware_path=firmware_path,
            firmware_sha="5" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_CORE2_READY",
            ready_timeout=20,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "core2-unified",
                "nic": "misc.esp32_wifi",
                "expected_markers": list(
                    device_service_module.CORE2_UNIFIED_MARKERS
                ),
                "attempts": 3,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "UNIFIED_CORE2_WIFI_CONNECTED 10.0.2.15\n"
            "UNIFIED_CORE2_HTTP_PASS\n"
            "UNIFIED_CORE2_PUBLIC_DNS 198.18.0.86\n"
            "UNIFIED_CORE2_PUBLIC_HTTP_PASS\n"
            "UNIFIED_CORE2_BLE_RX b'M5_CORE2_UNIFIED'\n"
            "UNIFIED_CORE2_BLE_ACK_SENT\n"
            "UNIFIED_CORE2_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-CORE2-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_CORE2_UNIFIED\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_CORE2_UNIFIED\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}])
        )
        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-core2-unified-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["runtime"]["hci_transport"], "UART1 H4")
        self.assertEqual(evidence["runtime"]["wifi_nic"], "misc.esp32_wifi")
        self.assertEqual(
            evidence["runtime"]["memory"]["effective_psram_mib"],
            4,
        )
        self.assertEqual(evidence["gatt"]["name"], "M5-CORE2-UNIFIED")
        self.assertEqual(evidence["gatt"]["payload"], "M5_CORE2_UNIFIED")
        self.assertEqual(
            session.snapshot()["runtime_memory"]["effective_psram_mib"],
            4,
        )
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_nanoc6_hci_ble_qemu_evidence(self):
        spec = self.service.specs["nanoc6"]
        firmware_path = Path(self.tmp.name) / "nanoc6-hci-ble.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="6" * 32,
            spec=spec,
            firmware_id="7" * 64,
            firmware_path=firmware_path,
            firmware_sha="7" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="NANOC6_HCI_BLE_ACK_SENT",
            ready_timeout=20,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "nanoc6-hci-ble",
                "nic": "misc.esp32c6.wifi",
                "expected_markers": list(
                    device_service_module.NANOC6_HCI_BLE_MARKERS
                ),
                "attempts": 3,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "NANOC6_HCI_BOARD 140\n"
            "NANOC6_HCI_RGB 1 00FF00\n"
            "NANOC6_HCI_BLUE 1\n"
            "NANOC6_HCI_IR 0x56 0xA3\n"
            "NANOC6_HCI_WIFI_SCAN []\n"
            "NANOC6_HCI_WIFI_CONNECTED 10.0.2.15\n"
            "NANOC6_HCI_HTTP_PASS\n"
            "NANOC6_HCI_BUTTON_PRESS\n"
            "NANOC6_HCI_BUTTON_RELEASE\n"
            "NANOC6_HCI_BLE_RX b'M5_NANOC6_HCI'\n"
            "NANOC6_HCI_BLE_ACK_SENT\n"
            "NANOC6_HCI_READY\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-NANOC6-HCI'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_NANOC6_HCI\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_NANOC6_HCI\n"
            "BLE_BUMBLE_PASS\n"
        )
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}]) + "\n"
        )

        green = 0x00FF00
        ws2812_words = [
            0x2000 if green & (1 << (23 - index)) else 0x1000
            for index in range(24)
        ]
        payload = 0x56 | ((0x56 ^ 0xFF) << 8)
        payload |= 0xA3 << 16
        payload |= (0xA3 ^ 0xFF) << 24
        nec_words = [9000 | (4500 << 16)]
        for index in range(32):
            nec_words.append(
                560 | ((1690 if payload & (1 << index) else 560) << 16)
            )
        nec_words.append(560)
        session.rmt_capture.write_bytes(
            b"".join(word.to_bytes(4, "little") for word in ws2812_words + nec_words)
        )

        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-nanoc6-board-hci-ble-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["runtime"]["hci_transport"], "UART1 H4")
        self.assertEqual(
            evidence["runtime"]["wifi"],
            "PASS via QEMU ESP32-C6 MAC/DMA and SLiRP",
        )
        self.assertEqual(evidence["http_requests"], [
            {"path": "/unified", "host": "qemu.test"}
        ])
        self.assertEqual(evidence["rmt"]["ws2812"]["status"], "PASS")
        self.assertEqual(evidence["rmt"]["nec"]["status"], "PASS")
        self.assertEqual(evidence["gatt"]["name"], "M5-NANOC6-HCI")
        self.assertEqual(evidence["gatt"]["payload"], "M5_NANOC6_HCI")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_nesso_unified_qemu_evidence(self):
        spec = self.service.specs["nesso-n1"]
        firmware_path = Path(self.tmp.name) / "nesso-unified.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="8" * 32,
            spec=spec,
            firmware_id="9" * 64,
            firmware_path=firmware_path,
            firmware_sha="9" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker="UNIFIED_NESSO_BLE_ACK_SENT",
            ready_timeout=30,
            ready_conditions=None,
            runtime="qemu-ble",
            network_config={
                "profile": "nesso-unified",
                "nic": "misc.esp32c6.wifi",
                "expected_markers": list(
                    device_service_module.NESSO_UNIFIED_MARKERS
                ),
                "attempts": 3,
            },
        )
        session.state = "running"
        session.serial0.write_text(
            "\n".join(device_service_module.NESSO_UNIFIED_MARKERS) + "\n"
        )
        session.hci_probe_log.write_text(
            "BLE_PROBE_READY\n"
            "BLE_BUMBLE_FOUND name='M5-NESSO-UNIFIED'\n"
            "BLE_BUMBLE_CONNECTED\n"
            "BLE_BUMBLE_GATT_DISCOVERED\n"
            "BLE_BUMBLE_SUBSCRIBED\n"
            "BLE_BUMBLE_WRITE M5_NESSO_UNIFIED\n"
            "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_NESSO_UNIFIED\n"
            "BLE_BUMBLE_PASS\n"
        )
        payload = 0x56 | ((0x56 ^ 0xFF) << 8)
        payload |= 0xA3 << 16
        payload |= (0xA3 ^ 0xFF) << 24
        nec_words = [9000 | (4500 << 16)]
        for index in range(32):
            nec_words.append(
                560 | ((1690 if payload & (1 << index) else 560) << 16)
            )
        nec_words.append(560)
        session.rmt_capture.write_bytes(
            b"".join(word.to_bytes(4, "little") for word in nec_words)
        )
        session.speaker_pcm.write_bytes(b"\x00\x00\xff\x7f" * 2048)
        session.http_fixture_log.write_text(
            json.dumps([{"path": "/unified", "host": "qemu.test"}]) + "\n"
        )
        session.unified_frame_changed = True
        session.frame_metrics = lambda **_kwargs: {  # type: ignore[method-assign]
            "png": b"png",
            "png_bytes": 3,
            "width": 135,
            "height": 240,
            "nonblack_pixels": 7000,
            "unique_colors": 17,
        }

        evidence = session.network_evidence()
        self.assertEqual(
            evidence["kind"],
            "m5stack-nesso-board-hci-ble-qemu-proof",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["runtime"]["hci_transport"], "UART1 H4")
        self.assertEqual(
            evidence["runtime"]["wifi"],
            "PASS via QEMU ESP32-C6 MAC/DMA and SLiRP",
        )
        self.assertEqual(evidence["http_requests"], [
            {"path": "/unified", "host": "qemu.test"}
        ])
        self.assertEqual(evidence["rmt"]["nec"]["status"], "PASS")
        self.assertEqual(evidence["pcm"]["check"]["status"], "PASS")
        self.assertEqual(evidence["gatt"]["name"], "M5-NESSO-UNIFIED")
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_qemu_wifi_requires_and_directly_uses_complete_flash_image(self):
        spec = self.service.specs["core2"]
        image = bytearray(b"\xff" * spec.flash_size)

        def write_test_esp_image(offset: int) -> None:
            image[offset] = 0xE9
            image[offset + 1] = 0
            struct.pack_into("<I", image, offset + 4, 0x40000000)
            struct.pack_into("<H", image, offset + 12, 0)

        write_test_esp_image(0x1000)
        write_test_esp_image(0x10000)
        struct.pack_into(
            "<HBBII16sI",
            image,
            0x8000,
            0x50AA,
            0,
            0x10,
            0x10000,
            0x1000,
            b"factory",
            0,
        )
        firmware = Path(self.tmp.name) / "core2-complete.bin"
        firmware.write_bytes(image)
        firmware_sha = device_service_module.hashlib.sha256(image).hexdigest()

        def unexpected_flash_preparer(*args, **kwargs):
            raise AssertionError("qemu-wifi must not invoke esptool")

        self.service.flash_preparer = unexpected_flash_preparer
        prepared = self.service.prepare_flash(
            spec,
            firmware,
            firmware_sha,
            runtime="qemu-wifi",
        )
        self.assertEqual(prepared["path"], firmware)
        self.assertEqual(
            prepared["info"]["transport"],
            "direct-complete-flash-image",
        )
        self.assertEqual(prepared["info"]["bootloader_offset"], 0x1000)
        self.assertEqual(prepared["info"]["app_partitions"][0]["label"], "factory")

        partial = Path(self.tmp.name) / "core2-partial.bin"
        partial.write_bytes(image[:0x11000])
        with self.assertRaises(ServiceError) as incomplete:
            self.service.prepare_flash(
                spec,
                partial,
                device_service_module.hashlib.sha256(
                    partial.read_bytes()
                ).hexdigest(),
                runtime="qemu-wifi",
            )
        self.assertEqual(
            incomplete.exception.code,
            "complete_flash_image_required",
        )

    def test_qemu_wifi_allows_erased_inactive_ota_slot(self):
        spec = self.service.specs["sticks3"]
        image = bytearray(b"\xff" * spec.flash_size)

        def write_test_esp_image(offset: int) -> None:
            image[offset] = 0xE9
            image[offset + 1] = 0
            struct.pack_into("<I", image, offset + 4, 0x40000000)
            struct.pack_into("<H", image, offset + 12, 9)

        write_test_esp_image(0)
        write_test_esp_image(0x10000)
        for index, (subtype, offset, label) in enumerate(
            (
                (0x10, 0x10000, b"app0"),
                (0x11, 0x200000, b"app1"),
            )
        ):
            struct.pack_into(
                "<HBBII16sI",
                image,
                0x8000 + index * 32,
                0x50AA,
                0,
                subtype,
                offset,
                0x1000,
                label,
                0,
            )

        firmware = Path(self.tmp.name) / "sticks3-sparse-ota.bin"
        firmware.write_bytes(image)
        firmware_sha = device_service_module.hashlib.sha256(image).hexdigest()
        prepared = self.service.prepare_flash(
            spec,
            firmware,
            firmware_sha,
            runtime="qemu-wifi",
        )
        self.assertEqual(
            [row["label"] for row in prepared["info"]["app_partitions"]],
            ["app0"],
        )
        self.assertEqual(
            [
                row["label"]
                for row in prepared["info"]["erased_app_partitions"]
            ],
            ["app1"],
        )

        image[0x200000] = 0
        corrupted = Path(self.tmp.name) / "sticks3-corrupt-ota.bin"
        corrupted.write_bytes(image)
        with self.assertRaises(ServiceError) as invalid:
            self.service.prepare_flash(
                spec,
                corrupted,
                device_service_module.hashlib.sha256(image).hexdigest(),
                runtime="qemu-wifi",
            )
        self.assertEqual(
            invalid.exception.code,
            "direct_flash_layout_invalid",
        )

    def _stopped_session(
        self,
        firmware: bytes = b"\xff" * 1024,
        *,
        service: DeviceService | None = None,
        session_id: str = "a" * 32,
        created_at: str | None = None,
        completed_at: str | None = None,
    ):
        service = service or self.service
        spec = service.specs["sticks3"]
        firmware_path = service.state_dir / f"firmware-{session_id}.bin"
        firmware_path.write_bytes(firmware)
        session = DeviceSession(
            service,
            session_id=session_id,
            spec=spec,
            firmware_id="f" * 64,
            firmware_path=firmware_path,
            firmware_sha="f" * 64,
            firmware_source="uploaded",
            source_artifacts=["e" * 64],
            ttl_seconds=60,
            ready_marker=None,
            ready_timeout=10,
            ready_conditions=None,
            created_at=created_at,
            completed_at=completed_at,
        )
        session.serial0.write_text("ready\n")
        session.virtual_flash = session.dir / "virtual-flash.bin"
        session.virtual_flash.write_bytes(firmware)
        session.state = "stopped"
        session._persist_session()
        service._sessions[session.id] = session
        return session

    def test_session_history_filter_and_clear(self):
        session = self._stopped_session()
        self.assertEqual(self.service.list_sessions(include_stopped=False)["sessions"], [])
        cleared = self.service.clear_stopped(purge=True)
        self.assertEqual(cleared["cleared"], 1)
        self.assertNotIn(session.id, self.service._sessions)

    def test_stop_releases_virtual_flash_by_default(self):
        session = self._stopped_session(session_id="b" * 32)
        flash_path = session.dir / "virtual-flash.bin"
        self.assertTrue(flash_path.is_file())

        result = session.stop(purge=False)

        self.assertFalse(flash_path.exists())
        self.assertFalse(result["flash_retained"])
        self.assertTrue((session.dir / "serial.log").is_file())
        self.assertTrue(session.session_record_path.is_file())

    def test_stop_can_retain_virtual_flash(self):
        session = self._stopped_session(session_id="c" * 32)
        flash_path = session.dir / "virtual-flash.bin"

        result = session.stop(purge=False, retain_flash=True)

        self.assertTrue(flash_path.is_file())
        self.assertTrue(result["flash_retained"])

    def test_service_close_does_not_rewrite_stopped_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DeviceService(
                state_dir=Path(tmp),
                storage_policy=StoragePolicy(
                    min_free_bytes=0,
                    prune_interval_seconds=3600,
                ),
            )
            session = self._stopped_session(
                service=service,
                session_id="e" * 32,
            )
            flash_path = session.dir / "virtual-flash.bin"
            self.assertTrue(flash_path.is_file())

            service.close_all()

            self.assertTrue(flash_path.is_file())

    def test_history_retention_prunes_oldest_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DeviceService(
                state_dir=Path(tmp),
                storage_policy=StoragePolicy(
                    history_ttl_seconds=0,
                    max_history_sessions=2,
                    max_history_bytes=0,
                    cache_grace_seconds=3600,
                    min_free_bytes=0,
                    prune_interval_seconds=3600,
                ),
            )
            try:
                sessions = [
                    self._stopped_session(
                        service=service,
                        session_id=f"{index:032x}",
                        created_at=f"2026-10-23T00:0{index}:00+00:00",
                        completed_at=f"2026-10-23T00:0{index}:30+00:00",
                    )
                    for index in range(1, 4)
                ]

                result = service.prune_storage(include_cache=False)

                self.assertEqual(result["pruned_sessions"], 1)
                self.assertNotIn(sessions[0].id, service._sessions)
                self.assertIn(sessions[1].id, service._sessions)
                self.assertIn(sessions[2].id, service._sessions)
            finally:
                service.close_all()

    def test_cache_gc_keeps_firmware_referenced_by_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DeviceService(
                state_dir=Path(tmp),
                storage_policy=StoragePolicy(
                    history_ttl_seconds=0,
                    max_history_sessions=100,
                    max_history_bytes=0,
                    max_cache_bytes=0,
                    cache_grace_seconds=0,
                    min_free_bytes=0,
                    prune_interval_seconds=3600,
                ),
            )
            try:
                artifact_a = service.upload_artifact(b"A" * 1024)
                firmware_a = service.create_firmware(
                    {
                        "device_id": "sticks3",
                        "kind": "merged",
                        "artifact_id": artifact_a["artifact_id"],
                    }
                )
                artifact_b = service.upload_artifact(b"B" * 2048)
                firmware_b = service.create_firmware(
                    {
                        "device_id": "sticks3",
                        "kind": "merged",
                        "artifact_id": artifact_b["artifact_id"],
                    }
                )
                session = self._stopped_session(
                    service=service,
                    session_id="d" * 32,
                )
                session.firmware_id = firmware_b["firmware_id"]
                session.firmware_sha = firmware_b["sha256"]
                session.source_artifacts = [artifact_b["artifact_id"]]
                session._persist_session()

                cache_root = service.state_dir / "flash-cache" / "sticks3"
                cache_root.mkdir(parents=True)
                cache_a = cache_root / f"{firmware_a['firmware_id']}.bin"
                cache_b = cache_root / f"{firmware_b['firmware_id']}.bin"
                cache_a.write_bytes(b"A")
                cache_b.write_bytes(b"B")

                result = service.prune_storage(include_cache=True)

                self.assertEqual(result["cache"]["firmware_removed"], 1)
                self.assertEqual(result["cache"]["artifacts_removed"], 1)
                self.assertFalse(service.firmware._meta(firmware_a["firmware_id"]).exists())
                self.assertFalse(service.artifacts._meta(artifact_a["artifact_id"]).exists())
                self.assertFalse(cache_a.exists())
                self.assertTrue(service.firmware._meta(firmware_b["firmware_id"]).is_file())
                self.assertTrue(service.artifacts._meta(artifact_b["artifact_id"]).is_file())
                self.assertTrue(cache_b.is_file())
            finally:
                service.close_all()

    def test_cache_gc_enforces_total_cache_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = DeviceService(
                state_dir=Path(tmp),
                storage_policy=StoragePolicy(
                    history_ttl_seconds=0,
                    max_history_sessions=100,
                    max_history_bytes=0,
                    max_cache_bytes=9 * 1024 * 1024,
                    cache_grace_seconds=3600,
                    min_free_bytes=0,
                    prune_interval_seconds=3600,
                ),
            )
            try:
                firmware = []
                for index in range(2):
                    artifact = service.upload_artifact(bytes([index]) * 1024)
                    record = service.create_firmware(
                        {
                            "device_id": "sticks3",
                            "kind": "merged",
                            "artifact_id": artifact["artifact_id"],
                        }
                    )
                    firmware.append(record)
                    meta_path = service.firmware._meta(record["firmware_id"])
                    meta = json.loads(meta_path.read_text())
                    meta["created_at"] = (
                        datetime.now(timezone.utc)
                        - timedelta(seconds=120 - index)
                    ).isoformat()
                    meta_path.write_text(json.dumps(meta))

                result = service.prune_storage(include_cache=True)

                self.assertGreaterEqual(result["cache"]["firmware_removed"], 1)
                self.assertLessEqual(
                    service.storage_stats()["firmware"]["bytes"],
                    9 * 1024 * 1024,
                )
            finally:
                service.close_all()

    def test_storage_reserve_rejects_low_disk(self):
        service = DeviceService(
            state_dir=Path(self.tmp.name) / "storage-reserve",
            storage_policy=StoragePolicy(min_free_bytes=50),
        )
        try:
            usage = mock.Mock(total=100, used=99, free=1)
            with mock.patch.object(
                device_service_module.shutil,
                "disk_usage",
                return_value=usage,
            ):
                with self.assertRaises(ServiceError) as caught:
                    service._ensure_storage_capacity(10)
            self.assertEqual(caught.exception.code, "storage_exhausted")
            self.assertEqual(caught.exception.status, 507)
            self.assertEqual(caught.exception.extra["required_bytes"], 60)
        finally:
            service.close_all()

    def test_list_sessions_does_not_block_capacity_during_snapshot(self):
        session = self._stopped_session()
        snapshot_started = threading.Event()
        release_snapshot = threading.Event()
        capacity_done = threading.Event()
        original_snapshot = session.snapshot

        def slow_snapshot():
            snapshot_started.set()
            release_snapshot.wait(timeout=2)
            return original_snapshot()

        session.snapshot = slow_snapshot
        list_thread = threading.Thread(target=self.service.list_sessions)
        list_thread.start()
        self.assertTrue(snapshot_started.wait(timeout=1))

        def query_capacity():
            self.service.capacity()
            capacity_done.set()

        capacity_thread = threading.Thread(target=query_capacity)
        capacity_thread.start()
        try:
            self.assertTrue(capacity_done.wait(timeout=0.5))
        finally:
            release_snapshot.set()
            list_thread.join(timeout=2)
            capacity_thread.join(timeout=2)
        self.assertFalse(list_thread.is_alive())
        self.assertFalse(capacity_thread.is_alive())

    def test_qmp_timeout_is_bounded_and_closes_connection(self):
        session = self._stopped_session()
        session.state = "running"

        class FakeProcess:
            def poll(self):
                return None

        class FakeSocket:
            def settimeout(self, timeout):
                self.timeout = timeout

        class TimedOutQMP:
            def __init__(self):
                self.sock = FakeSocket()
                self.closed = False

            def cmd(self, name, **arguments):
                raise TimeoutError("timed out")

            def close(self):
                self.closed = True

        qmp = TimedOutQMP()
        session._proc = FakeProcess()
        session._qmp = qmp
        with self.assertRaises(ServiceError) as context:
            session._qmp_call("query-status")
        self.assertEqual(context.exception.code, "qmp_timeout")
        self.assertEqual(context.exception.status, 504)
        self.assertTrue(qmp.closed)
        self.assertIsNone(session._qmp)
        session.state = "stopped"
        session._proc = None

    def test_physical_key_down_and_up_are_distinct_qmp_events(self):
        session = self._stopped_session()
        session.state = "running"

        class FakeProcess:
            def poll(self):
                return None

        class RecordingQMP:
            def __init__(self):
                self.calls = []

            def cmd(self, name, **arguments):
                self.calls.append((name, arguments))
                return {"return": {}}

        qmp = RecordingQMP()
        session._proc = FakeProcess()
        session._qmp = qmp
        session.inject({"kind": "key", "key": "a", "action": "down"})
        session.inject({"kind": "key", "key": "a", "action": "up"})

        key_events = [
            call[1]["events"][0]["data"]["down"]
            for call in qmp.calls
            if call[0] == "input-send-event"
        ]
        self.assertEqual(key_events, [True, False])
        input_events = [
            event["spec"] for event in session.events if event["event"] == "input"
        ]
        self.assertEqual(input_events, ["keydown:a", "keyup:a"])
        session.state = "stopped"
        session._proc = None
        session._qmp = None

    def test_qmp_command_read_honors_socket_timeout(self):
        socket_path = Path(self.tmp.name) / "qmp-timeout.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen(1)

        def serve():
            connection, _ = server.accept()
            try:
                connection.sendall(b'{"QMP":{"version":{}}}\n')
                connection.recv(4096)
                connection.sendall(b'{"return":{}}\n')
                connection.recv(4096)
                threading.Event().wait(0.5)
            finally:
                connection.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        qmp = QMP(socket_path, timeout=0.1)
        try:
            with self.assertRaises(TimeoutError):
                qmp.cmd("screendump", filename="never-created.ppm")
        finally:
            qmp.close()
            server.close()
            thread.join(timeout=1)

    def test_sticks3_device_state_probe_and_persisted_fallback(self):
        session = self._stopped_session()
        session.state = "running"

        class FakeProcess:
            def poll(self):
                return None

        class FakeSocket:
            def settimeout(self, timeout):
                self.timeout = timeout

        class StateQMP:
            def __init__(self):
                self.sock = FakeSocket()
                self.values = {
                    ("/machine/m5pm1", "vbat-mv"): 4000,
                    ("/machine/m5pm1", "vin-mv"): 5000,
                    ("/machine/m5pm1", "vinout-mv"): 5000,
                    ("/machine/m5pm1", "charging"): False,
                    ("/machine/m5pm1", "temperature-c"): 25,
                    ("/machine/m5pm1", "pa-enabled"): True,
                    ("/machine/m5pm1", "gpio-input-bits"): 31,
                    ("/machine/bmi270", "accel-x"): 0,
                    ("/machine/bmi270", "accel-y"): 0,
                    ("/machine/bmi270", "accel-z"): 1,
                    ("/machine/bmi270", "gyro-x"): 0,
                    ("/machine/bmi270", "gyro-y"): 0,
                    ("/machine/bmi270", "gyro-z"): 0,
                }

            def cmd(self, name, **arguments):
                self.assert_name = name
                return {
                    "return": self.values[
                        (arguments["path"], arguments["property"])
                    ]
                }

            def close(self):
                pass

        session._proc = FakeProcess()
        session._qmp = StateQMP()
        live = session.device_state()
        self.assertTrue(live["available"])
        self.assertEqual(live["source"], "live")
        self.assertEqual(
            live["components"]["power"]["properties"]["vbat-mv"], 4000
        )
        self.assertEqual(
            live["components"]["imu"]["properties"]["accel-z"], 1
        )
        self.assertTrue(session.snapshot()["last_device_state_available"])

        session.state = "stopped"
        session._qmp = None
        session._proc = None
        persisted = session.device_state()
        self.assertTrue(persisted["available"])
        self.assertEqual(persisted["source"], "persisted")
        self.assertEqual(
            persisted["components"]["power"]["properties"]["pa-enabled"], True
        )

    def test_serial_readiness_and_evidence_bundle(self):
        session = self._stopped_session()
        session.state = "running"
        result = session.wait_ready(
            {
                "timeout_seconds": 1,
                "ready": {
                    "serial_markers": ["ready"],
                    "require_all": True,
                },
            }
        )
        self.assertTrue(result["ready"])
        bundle = session.evidence_bundle({"manifest", "serial", "flash"})
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn("manifest.json", archive.namelist())
            self.assertIn("serial.log", archive.namelist())
            self.assertIn("flash/virtual-flash.bin", archive.namelist())

    def test_qom_diff_uses_stored_snapshots(self):
        session = self._stopped_session()
        before = "1" * 32
        after = "2" * 32
        (session.dir / f"qom-{before}.json").write_text(
            json.dumps({"nodes": {"a": {"value": 1}}})
        )
        (session.dir / f"qom-{after}.json").write_text(
            json.dumps({"nodes": {"a": {"value": 2}, "b": {"value": 3}}})
        )
        diff = session.qom_diff(before, after)
        self.assertIn("b/value", diff["added"])
        self.assertIn("a/value", diff["changed"])

    def test_stopped_session_returns_persisted_last_frame(self):
        session = self._stopped_session()
        session.last_frame_path.write_bytes(b"\x89PNG\r\n\x1a\nlast-frame")
        session.last_frame_meta_path.write_text(
            json.dumps(
                {
                    "width": 135,
                    "height": 240,
                    "nonblack_pixels": 10,
                    "unique_colors": 2,
                    "captured_at": "2026-10-22T00:00:00+00:00",
                }
            )
        )
        metrics = session.frame_metrics()
        self.assertEqual(metrics["source"], "persisted")
        self.assertEqual(metrics["width"], 135)
        self.assertEqual(metrics["png_bytes"], len(b"\x89PNG\r\n\x1a\nlast-frame"))

    def test_stopped_history_and_last_frame_survive_service_restart(self):
        session = self._stopped_session()
        session.completed_at = "2026-10-22T08:00:00+00:00"
        session.last_frame_path.write_bytes(b"\x89PNG\r\n\x1a\nlast-frame")
        session.last_frame_meta_path.write_text(
            json.dumps(
                {
                    "width": 135,
                    "height": 240,
                    "nonblack_pixels": 10,
                    "unique_colors": 2,
                    "captured_at": "2026-10-22T07:59:59+00:00",
                }
            )
        )
        session._record_event("stopped")
        session._persist_session()

        self.service.close_all()
        restarted = DeviceService(
            state_dir=self.service.state_dir,
            max_sessions=2,
            max_per_device=1,
        )
        try:
            rows = restarted.list_sessions()["sessions"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["session_id"], session.id)
            self.assertEqual(rows[0]["state"], "stopped")
            self.assertTrue(rows[0]["restored"])
            self.assertFalse(rows[0]["interrupted"])
            self.assertTrue(rows[0]["last_frame_available"])
            self.assertEqual(
                rows[0]["last_frame_captured_at"],
                "2026-10-22T07:59:59+00:00",
            )
            self.assertEqual(restarted.capacity()["active_sessions"], 0)
            restored = restarted.get_session(session.id)
            self.assertEqual(restored.frame_metrics()["width"], 135)
            events = restarted.session_events(session.id)["events"]
            self.assertEqual(events[-1]["event"], "stopped")
        finally:
            restarted.close_all()

    def test_running_orphan_is_rejected_and_verified_process_is_reattached(
        self,
    ):
        orphan = self._stopped_session(session_id="a" * 32)
        orphan.state = "running"
        orphan.completed_at = None
        orphan.pid = 12345
        orphan._persist_session()
        self.service.worker.reserve_lease(orphan.id)

        reattached = self._stopped_session(session_id="d" * 32)
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                str(reattached.qmp_path),
            ]
        )
        identity = device_service_module.inspect_process(process.pid)
        self.assertTrue(identity["exists"])
        reattached.state = "running"
        reattached.completed_at = None
        reattached.pid = process.pid
        reattached.process_start_token = identity["start_token"]
        reattached._worker_lease_active = True
        reattached._persist_session()
        self.service.worker.reserve_lease(reattached.id)

        stale = self._stopped_session(session_id="e" * 32)
        stale.state = "running"
        stale.completed_at = None
        stale.pid = process.pid
        stale.process_start_token = "stale-start-token"
        stale._persist_session()
        self.service.worker.reserve_lease(stale.id)

        self.service._stop.set()
        self.service.worker.close()
        fake_qmp = mock.MagicMock()
        fake_qmp.cmd.side_effect = lambda command, **arguments: (
            {"return": {"status": "running"}}
            if command == "query-status"
            else {"return": {}}
        )
        try:
            with mock.patch.object(
                device_service_module,
                "wait_qmp",
                return_value=fake_qmp,
            ):
                restarted = DeviceService(
                    state_dir=self.service.state_dir,
                    max_sessions=3,
                    max_per_device=3,
                )
            try:
                orphan_row = restarted.get_session(orphan.id).snapshot()
                self.assertEqual(orphan_row["state"], "failed")
                self.assertTrue(orphan_row["restored"])
                self.assertTrue(orphan_row["interrupted"])
                self.assertFalse(orphan_row["reattached_process"])
                self.assertIn("service restarted", orphan_row["error"])

                stale_row = restarted.get_session(stale.id).snapshot()
                self.assertEqual(stale_row["state"], "failed")
                self.assertTrue(stale_row["interrupted"])
                self.assertFalse(stale_row["reattached_process"])
                self.assertIn("safe re-attach rejected", stale_row["error"])

                live_row = restarted.get_session(reattached.id).snapshot()
                self.assertEqual(live_row["state"], "running")
                self.assertTrue(live_row["restored"])
                self.assertFalse(live_row["interrupted"])
                self.assertTrue(live_row["reattached_process"])
                self.assertEqual(
                    live_row["recovery_scope"],
                    "qemu-control-plane",
                )
                self.assertEqual(restarted.capacity()["active_sessions"], 1)
                worker = restarted.worker_status()
                self.assertEqual(worker["generation"], 2)
                self.assertEqual(worker["active_lease_count"], 1)
                self.assertEqual(
                    worker["active_lease_ids"],
                    [reattached.id],
                )
                abandoned_ids = {
                    lease["lease_id"]
                    for lease in worker["abandoned_leases"]
                }
                self.assertIn(orphan.id, abandoned_ids)
                self.assertIn(stale.id, abandoned_ids)
                self.assertIn(reattached.id, abandoned_ids)

                orphan_events = restarted.session_events(orphan.id)["events"]
                self.assertEqual(orphan_events[-1]["event"], "interrupted")
                self.assertEqual(
                    orphan_events[-1]["previous_state"],
                    "running",
                )
                live_events = restarted.session_events(
                    reattached.id
                )["events"]
                self.assertEqual(live_events[-1]["event"], "reattached")
                self.assertEqual(
                    live_events[-1]["recovery_scope"],
                    "qemu-control-plane",
                )
            finally:
                restarted.close_all()
            process.wait(timeout=5)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_unified_reattach_recovers_http_and_adopts_live_ble_peer(self):
        spec = self.service.specs["sticks3"]
        profile = device_service_module.STICKS3_UNIFIED_PROFILE
        session_id = "f" * 32
        firmware_path = Path(self.tmp.name) / "sticks3-unified.bin"
        firmware_path.write_bytes(b"\xff" * spec.flash_size)
        qemu = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                str(Path("/tmp") / f"m5-service-{session_id}.sock"),
            ]
        )
        qemu_identity = device_service_module.inspect_process(qemu.pid)
        ble_port = device_service_module.free_tcp_port()
        ble = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(60)",
                str(device_service_module.BLE_PROBE),
                "--port",
                str(ble_port),
                "--name-prefix",
                "M5-STICKS3-UNIFIED",
            ]
        )
        ble_identity = device_service_module.inspect_process(ble.pid)
        self.assertTrue(qemu_identity["exists"])
        self.assertTrue(ble_identity["exists"])
        command_sha256 = hashlib.sha256(
            str(ble_identity["command"]).encode()
        ).hexdigest()
        http_port = device_service_module.free_tcp_port()
        session = DeviceSession(
            self.service,
            session_id=session_id,
            spec=spec,
            firmware_id="a" * 64,
            firmware_path=firmware_path,
            firmware_sha="a" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=120,
            ready_marker="UNIFIED_STICKS3_READY",
            ready_timeout=120,
            ready_conditions=None,
            runtime="qemu-unified",
            network_config={
                "profile": profile,
                "nic": "misc.esp32s3.wifi",
                "attempts": 1,
                "policy": {
                    "isolation": "trusted-host",
                    "egress": "native",
                    "dns": "slirp",
                },
                "ble_reconnect_cycles": 2,
            },
            initial_state="running",
            process_start_token=qemu_identity["start_token"],
            companions={
                "ble": {
                    "state": "running",
                    "pid": ble.pid,
                    "start_token": ble_identity["start_token"],
                    "command_sha256": command_sha256,
                    "port": ble_port,
                },
                "http": {
                    "state": "running",
                    "port": http_port,
                    "generation": 1,
                },
            },
        )
        session.pid = qemu.pid
        session.http_fixture_log.write_text(
            json.dumps(
                [
                    {
                        "path": "/unified",
                        "host": "qemu.test",
                        "fixture_generation": 1,
                    }
                ]
            )
        )
        fake_qmp = mock.MagicMock()
        fake_qmp.cmd.return_value = {"return": {"status": "running"}}
        try:
            with (
                mock.patch.object(
                    device_service_module,
                    "wait_qmp",
                    return_value=fake_qmp,
                ),
                mock.patch.dict(
                    device_service_module.UNIFIED_HTTP_PORTS,
                    {profile: http_port},
                ),
            ):
                recovered = session.reattach()
                request = Request(
                    f"http://127.0.0.1:{http_port}/unified",
                    headers={"Host": "qemu.test"},
                )
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(
                        response.read(),
                        device_service_module.UNIFIED_HTTP_BODIES[profile],
                    )
            self.assertEqual(
                recovered["recovery_scope"],
                "qemu-control-plane+companions",
            )
            self.assertEqual(
                recovered["companion_recovery"]["ble_probe"]["state"],
                "adopted",
            )
            self.assertEqual(
                recovered["companion_recovery"]["http_fixture"][
                    "generation"
                ],
                2,
            )
            requests = json.loads(session.http_fixture_log.read_text())
            self.assertEqual(
                [item["fixture_generation"] for item in requests],
                [1, 2],
            )
            snapshot = session.snapshot()
            self.assertEqual(
                snapshot["recovery_scope"],
                "qemu-control-plane+companions",
            )
            self.assertTrue(
                snapshot["companions"]["ble_probe"]["adopted"]
            )
            self.assertNotIn("start_token", snapshot["companions"]["ble_probe"])
        finally:
            session._terminate_process()
            for process in (qemu, ble):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    def test_companion_recovery_fails_closed_without_ownership(self):
        spec = self.service.specs["sticks3"]
        firmware_path = Path(self.tmp.name) / "sticks3-unified.bin"
        firmware_path.write_bytes(b"\xff" * spec.flash_size)
        for isolation, expected_code in (
            ("trusted-host", "companion_recovery_failed"),
            ("namespace", "companion_recovery_unsupported"),
        ):
            with self.subTest(isolation=isolation):
                session = DeviceSession(
                    self.service,
                    session_id=uuid.uuid4().hex,
                    spec=spec,
                    firmware_id="b" * 64,
                    firmware_path=firmware_path,
                    firmware_sha="b" * 64,
                    firmware_source="uploaded",
                    source_artifacts=[],
                    ttl_seconds=120,
                    ready_marker="UNIFIED_STICKS3_READY",
                    ready_timeout=120,
                    ready_conditions=None,
                    runtime="qemu-unified",
                    network_config={
                        "profile": device_service_module.STICKS3_UNIFIED_PROFILE,
                        "policy": {
                            "isolation": isolation,
                            "egress": (
                                "native"
                                if isolation == "trusted-host"
                                else "deny-all"
                            ),
                            "dns": (
                                "slirp"
                                if isolation == "trusted-host"
                                else "deny"
                            ),
                        },
                    },
                    initial_state="running",
                    companions={
                        "http": {
                            "state": "running",
                            "port": device_service_module.UNIFIED_HTTP_PORTS[
                                device_service_module.STICKS3_UNIFIED_PROFILE
                            ],
                            "generation": 1,
                        }
                    },
                    persist=False,
                )
                with self.assertRaises(ServiceError) as error:
                    session._recover_companions()
                self.assertEqual(error.exception.code, expected_code)


class DeviceServiceHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = DeviceService(
            state_dir=Path(cls.tmp.name),
            api_token="test-auth-value",
        )
        Handler.service = cls.service
        Handler.api_token = None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.service.close_all()
        Handler.service = None
        cls.tmp.cleanup()

    def request(self, path, *, method="GET", data=None, headers=None):
        request = Request(self.base + path, method=method, data=data, headers=headers or {})
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)

    def test_v1_catalog_and_capacity(self):
        status, payload = self.request("/api/v1/devices")
        self.assertEqual(status, 200)
        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(len(payload["devices"]), 14)
        status, capacity = self.request("/api/v1/capacity")
        self.assertEqual(status, 200)
        self.assertEqual(
            capacity["modes"]["network"],
            "enabled-separate-lane",
        )
        self.assertEqual(capacity["worker"]["state"], "ready")
        self.assertFalse(capacity["worker"]["stale"])

        status, draining = self.request(
            "/api/v1/worker/drain",
            method="POST",
            data=b"",
        )
        self.assertEqual(status, 200)
        self.assertEqual(draining["worker"]["state"], "drained")
        status, resumed = self.request(
            "/api/v1/worker/resume",
            method="POST",
            data=b"",
        )
        self.assertEqual(status, 200)
        self.assertEqual(resumed["worker"]["state"], "ready")

    def test_openapi_is_served(self):
        with urlopen(self.base + "/api/v1/openapi.yaml", timeout=5) as response:
            self.assertEqual(response.status, 200)
            document = response.read()
            self.assertIn(b"openapi: 3.1.0", document)
            self.assertIn(b"qemu-unified", document)
            self.assertIn(b"ManifestFirmwareRequest", document)
            self.assertIn(b"network-fault", document)

    def test_remote_worker_directory_http_contract(self):
        worker_id = f"remote-{uuid.uuid4().hex[:12]}"
        identity = {
            "worker_id": worker_id,
            "instance_id": "instance-a",
            "generation": 1,
            "stale_after_seconds": 30,
            "endpoint": "http://worker.example:8787",
            "capabilities": {"qemu": True, "network_namespace": True},
            "active_lease_ids": ["lease-1"],
        }
        status, registered = self.request(
            "/api/v1/workers",
            method="POST",
            data=json.dumps(identity).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(registered["worker"]["state"], "ready")
        self.assertEqual(
            registered["worker"]["active_lease_ids"],
            ["lease-1"],
        )

        status, listing = self.request("/api/v1/workers")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(listing["worker_count"], 1)
        self.assertIn(
            worker_id,
            {worker["worker_id"] for worker in listing["workers"]},
        )

        job_request = {
            "label": "queue-contract",
            "request": {
                "device_id": "sticks3",
                "profile": "uiflow2-sticks3-unified",
            },
            "required_capabilities": {"qemu": True},
            "max_attempts": 2,
            "idempotency_key": f"job-{uuid.uuid4().hex[:12]}",
        }
        status, submitted = self.request(
            "/api/v1/jobs",
            method="POST",
            data=json.dumps(job_request).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        job_id = submitted["job"]["job_id"]
        self.assertEqual(submitted["job"]["status"], "queued")
        status, replay = self.request(
            "/api/v1/jobs",
            method="POST",
            data=json.dumps(job_request).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(replay["job"]["job_id"], job_id)
        self.assertTrue(replay["job"]["idempotent_replay"])

        identity_payload = {
            "worker_id": worker_id,
            "instance_id": "instance-a",
            "generation": 1,
        }
        status, claimed = self.request(
            "/api/v1/jobs/claim",
            method="POST",
            data=json.dumps(identity_payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(claimed["job"]["job_id"], job_id)
        self.assertEqual(claimed["job"]["status"], "leased")
        lease_id = claimed["job"]["lease"]["lease_id"]

        status, job_heartbeat = self.request(
            f"/api/v1/jobs/{job_id}/heartbeat",
            method="POST",
            data=json.dumps(
                {**identity_payload, "lease_id": lease_id}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            job_heartbeat["job"]["lease"]["lease_id"],
            lease_id,
        )
        status, completed = self.request(
            f"/api/v1/jobs/{job_id}/result",
            method="POST",
            data=json.dumps(
                {
                    **identity_payload,
                    "lease_id": lease_id,
                    "state": "PASS",
                    "evidence_sha256": "b" * 64,
                    "summary": {"checks": 4},
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(completed["job"]["status"], "completed")
        status, jobs = self.request(
            "/api/v1/jobs?status=completed&limit=10"
        )
        self.assertEqual(status, 200)
        self.assertEqual(jobs["counts"]["completed"], 1)
        self.assertEqual(jobs["jobs"][0]["job_id"], job_id)
        status, cancel_submit = self.request(
            "/api/v1/jobs",
            method="POST",
            data=json.dumps(
                {
                    "label": "cancel-contract",
                    "request": {"device_id": "sticks3"},
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        cancel_job_id = cancel_submit["job"]["job_id"]
        status, cancelled = self.request(
            f"/api/v1/jobs/{cancel_job_id}/cancel",
            method="POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["job"]["status"], "cancelled")

        heartbeat_payload = {
            "instance_id": "instance-a",
            "generation": 1,
            "active_lease_ids": [],
            "capabilities": {"qemu": True},
        }
        status, heartbeat = self.request(
            f"/api/v1/workers/{worker_id}/heartbeat",
            method="POST",
            data=json.dumps(heartbeat_payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(heartbeat["worker"]["active_lease_count"], 0)
        status, result = self.request(
            f"/api/v1/workers/{worker_id}/results",
            method="POST",
            data=json.dumps(
                {
                    "instance_id": "instance-a",
                    "generation": 1,
                    "lease_id": "lease-1",
                    "state": "PASS",
                    "evidence_sha256": "a" * 64,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["result"]["lease_id"], "lease-1")
        status, drained = self.request(
            f"/api/v1/workers/{worker_id}/drain",
            method="POST",
            data=json.dumps(
                {"instance_id": "instance-a", "generation": 1}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(drained["worker"]["state"], "drained")
        status, stopped = self.request(
            f"/api/v1/workers/{worker_id}/stop",
            method="POST",
            data=json.dumps(
                {"instance_id": "instance-a", "generation": 1}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(stopped["worker"]["state"], "stopped")

        request = Request(
            self.base + f"/api/v1/workers/{worker_id}/heartbeat",
            method="POST",
            data=json.dumps(
                {"instance_id": "instance-b", "generation": 1}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 409)
        error = json.loads(caught.exception.read())
        self.assertEqual(
            error["error"]["code"],
            "worker_identity_mismatch",
        )

    def test_storage_stats_and_manual_prune(self):
        status, storage = self.request("/api/v1/storage")
        self.assertEqual(status, 200)
        self.assertIn("sessions", storage)
        self.assertIn("policy", storage)
        self.assertIn("free_bytes", storage["disk"])

        status, pruned = self.request(
            "/api/v1/storage/prune?include_cache=0",
            method="POST",
            data=b"",
        )
        self.assertEqual(status, 200)
        self.assertIn("pruned_sessions", pruned)
        self.assertFalse(pruned["cache"]["freed_bytes"])

    def test_artifact_and_firmware_round_trip(self):
        status, artifact = self.request(
            "/api/v1/artifacts",
            method="POST",
            data=b"\xe9" + b"A" * 31,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": "probe.bin",
            },
        )
        self.assertEqual(status, 201)
        body = json.dumps(
            {
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            }
        ).encode()
        status, firmware = self.request(
            "/api/v1/firmware",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(firmware["device_id"], "sticks3")
        status, fetched = self.request(f"/api/v1/firmware/{firmware['firmware_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["sha256"], firmware["sha256"])

    def test_streamed_artifact_http_upload(self):
        payload = b"web-burner-stream" * 32768
        first = payload[:200000]
        second = payload[200000:]
        status, upload = self.request(
            "/api/v1/artifact-uploads",
            method="POST",
            data=json.dumps(
                {
                    "expected_size": len(payload),
                    "expected_sha256": hashlib.sha256(payload).hexdigest(),
                    "name": "web-burner.bin",
                    "content_type": "application/octet-stream",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 202)
        upload_id = upload["upload_id"]
        status, progress = self.request(
            f"/api/v1/artifact-uploads/{upload_id}/chunks",
            method="POST",
            data=first,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Chunk-Offset": "0",
                "X-Chunk-SHA256": hashlib.sha256(first).hexdigest(),
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(progress["next_offset"], len(first))
        status, resumed = self.request(
            f"/api/v1/artifact-uploads/{upload_id}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(resumed["received_bytes"], len(first))
        status, progress = self.request(
            f"/api/v1/artifact-uploads/{upload_id}/chunks",
            method="POST",
            data=second,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Chunk-Offset": str(len(first)),
                "X-Chunk-SHA256": hashlib.sha256(second).hexdigest(),
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(progress["next_offset"], len(payload))
        status, artifact = self.request(
            f"/api/v1/artifact-uploads/{upload_id}/complete",
            method="POST",
            data=b"",
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            artifact["artifact_id"], hashlib.sha256(payload).hexdigest()
        )
        status, stored = self.request(
            f"/api/v1/artifacts/{artifact['artifact_id']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(stored["size"], len(payload))

        status, aborted = self.request(
            "/api/v1/artifact-uploads",
            method="POST",
            data=json.dumps(
                {
                    "expected_size": 1,
                    "expected_sha256": hashlib.sha256(b"x").hexdigest(),
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 202)
        status, deleted = self.request(
            f"/api/v1/artifact-uploads/{aborted['upload_id']}",
            method="DELETE",
        )
        self.assertEqual(status, 200)
        self.assertTrue(deleted["aborted"])

    def test_webburner_http_import(self):
        package = webburner_package(build_flash())
        status, artifact = self.request(
            "/api/v1/artifacts",
            method="POST",
            data=package,
            headers={
                "Content-Type": "application/zip",
                "X-Artifact-Name": "web-probe.zip",
            },
        )
        self.assertEqual(status, 201)
        status, firmware = self.request(
            "/api/v1/firmware/import",
            method="POST",
            data=json.dumps(
                {
                    "device_id": "sticks3",
                    "artifact_id": artifact["artifact_id"],
                    "required_capabilities": ["wifi", "screen"],
                    "optional_capabilities": ["IR"],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(firmware["kind"], "manifest")
        self.assertEqual(
            firmware["manifest"]["provenance"]["source_format"],
            "web-manifest",
        )
        self.assertEqual(firmware["manifest"]["artifact"]["kind"], "merged-flash")
        self.assertEqual(
            firmware["manifest"]["capabilities"],
            {
                "required": ["display", "wifi"],
                "optional": ["ir"],
                "detected": [],
            },
        )
        mismatch_request = Request(
            self.base + "/api/v1/firmware/import",
            method="POST",
            data=json.dumps(
                {
                    "device_id": "sticks3",
                    "artifact_id": artifact["artifact_id"],
                    "required_capabilities": ["camera"],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as mismatch_error:
            urlopen(mismatch_request, timeout=5)
        self.assertEqual(mismatch_error.exception.code, 409)
        mismatch = json.loads(mismatch_error.exception.read())
        self.assertEqual(
            mismatch["error"]["code"],
            "unsupported_firmware_capability",
        )
        self.assertTrue(
            any(
                issue.get("requirement") == "camera"
                for issue in mismatch["error"]["issues"]
            )
        )
        status, optional_firmware = self.request(
            "/api/v1/firmware/import",
            method="POST",
            data=json.dumps(
                {
                    "device_id": "sticks3",
                    "artifact_id": artifact["artifact_id"],
                    "required_capabilities": ["wifi"],
                    "optional_capabilities": ["camera"],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            optional_firmware["manifest"]["validation"]["status"],
            "PASS",
        )
        self.assertIn(
            "unsupported_optional_capability",
            {
                warning["code"]
                for warning in optional_firmware["manifest"]["validation"][
                    "warnings"
                ]
            },
        )
        invalid_request = Request(
            self.base + "/api/v1/firmware/import",
            method="POST",
            data=json.dumps(
                {
                    "device_id": "sticks3",
                    "artifact_id": artifact["artifact_id"],
                    "required_capabilities": "wifi",
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as invalid_error:
            urlopen(invalid_request, timeout=5)
        self.assertEqual(invalid_error.exception.code, 400)
        invalid = json.loads(invalid_error.exception.read())
        self.assertEqual(
            invalid["error"]["code"],
            "invalid_capability_requirements",
        )

    def test_device_state_endpoint(self):
        spec = self.service.specs["sticks3"]
        firmware_path = Path(self.tmp.name) / "state-firmware.bin"
        firmware_path.write_bytes(b"\xff" * 1024)
        session = DeviceSession(
            self.service,
            session_id="b" * 32,
            spec=spec,
            firmware_id="f" * 64,
            firmware_path=firmware_path,
            firmware_sha="f" * 64,
            firmware_source="uploaded",
            source_artifacts=[],
            ttl_seconds=60,
            ready_marker=None,
            ready_timeout=10,
            ready_conditions=None,
        )
        session.state = "stopped"
        session.device_state_path.write_text(
            json.dumps(
                {
                    "session_id": session.id,
                    "device_id": "sticks3",
                    "state": "running",
                    "supported": True,
                    "available": True,
                    "source": "live",
                    "captured_at": "2026-10-22T00:00:00+00:00",
                    "components": {"power": {"properties": {"vbat-mv": 4000}}},
                    "errors": {},
                }
            )
        )
        self.service._sessions[session.id] = session
        status, payload = self.request(
            f"/api/v1/sessions/{session.id}/device-state"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "persisted")
        self.assertEqual(
            payload["components"]["power"]["properties"]["vbat-mv"], 4000
        )
        self.service._sessions.pop(session.id, None)


class LegacyApiAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = DeviceService(
            state_dir=Path(cls.tmp.name),
            api_token="test-auth-value",
        )

        class AuthHandler(Handler):
            api_token = "test-auth-value"
            service = cls.service

        cls.handler = AuthHandler
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), AuthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.service.close_all()
        cls.tmp.cleanup()

    def test_legacy_api_requires_token(self):
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/api/devices", timeout=5)
        self.assertEqual(context.exception.code, 401)
        request = Request(
            self.base + "/api/devices",
            headers={"Authorization": "Bearer test-auth-value"},
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_remote_worker_api_requires_token(self):
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/api/v1/workers", timeout=5)
        self.assertEqual(context.exception.code, 401)

        request = Request(
            self.base + "/api/v1/workers",
            method="POST",
            data=json.dumps(
                {
                    "worker_id": "auth-worker",
                    "instance_id": "auth-instance",
                    "generation": 1,
                    "capabilities": {"qemu": True},
                }
            ).encode(),
            headers={
                "Authorization": "Bearer test-auth-value",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 201)
            payload = json.load(response)
        self.assertEqual(payload["worker"]["worker_id"], "auth-worker")

        with self.assertRaises(HTTPError) as unsigned:
            request = Request(
                self.base + "/api/v1/workers/auth-worker/heartbeat",
                method="POST",
                data=json.dumps(
                    {
                        "worker_id": "auth-worker",
                        "instance_id": "auth-instance",
                        "generation": 1,
                    }
                ).encode(),
                headers={
                    "Authorization": "Bearer test-auth-value",
                    "Content-Type": "application/json",
                },
            )
            urlopen(request, timeout=5)
        self.assertEqual(unsigned.exception.code, 401)

        heartbeat_payload = json.dumps(
            {
                "worker_id": "auth-worker",
                "instance_id": "auth-instance",
                "generation": 1,
                "state": "ready",
                "active_lease_ids": [],
            }
        ).encode()
        signed_headers = sign_worker_request(
            "test-auth-value",
            {
                "worker_id": "auth-worker",
                "instance_id": "auth-instance",
                "generation": 1,
            },
            "POST",
            "/api/v1/workers/auth-worker/heartbeat",
            heartbeat_payload,
        )
        request = Request(
            self.base + "/api/v1/workers/auth-worker/heartbeat",
            method="POST",
            data=heartbeat_payload,
            headers={
                "Authorization": "Bearer test-auth-value",
                "Content-Type": "application/json",
                **signed_headers,
            },
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
