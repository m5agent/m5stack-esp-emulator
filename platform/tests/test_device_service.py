#!/usr/bin/env python3
from __future__ import annotations

import json
import io
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import device_service as device_service_module
from device_service import (
    DEFAULT_MAX_PER_DEVICE,
    DEFAULT_MAX_SESSIONS,
    DeviceService,
    DeviceSession,
    MAX_ARTIFACT_BYTES,
    QMP,
    ServiceError,
)
from serve import Handler, _wait_for_session


class DeviceServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = DeviceService(
            state_dir=Path(self.tmp.name),
            max_sessions=2,
            max_per_device=1,
        )

    def tearDown(self):
        self.service.close_all()
        self.tmp.cleanup()

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
        self.assertEqual(rows["nesso-n1"]["network_status"], "validated")
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
        self.assertEqual(capacity["modes"]["qemu-wifi"], "enabled-sticks3")
        self.assertEqual(capacity["modes"]["qemu-ble"], "disabled")
        self.assertEqual(
            capacity["modes"]["qemu-unified"],
            "enabled-sticks3-cores3-cardputer-adv-stopwatch-atoms3r-papercolor-wifi-ble",
        )
        self.assertEqual(capacity["modes"]["tab5"], "enabled-partial")

    def test_default_capacity_matches_measured_workstation_profile(self):
        self.assertEqual(DEFAULT_MAX_SESSIONS, 12)
        self.assertEqual(DEFAULT_MAX_PER_DEVICE, 8)
        self.assertEqual(MAX_ARTIFACT_BYTES, 96 * 1024 * 1024)

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

    def test_runtime_env_is_narrowly_allowlisted(self):
        with self.assertRaises(ServiceError) as caught:
            self.service.create_session(
                {
                    "device_id": "sticks3",
                    "runtime_env": {"PATH": "/tmp"},
                }
            )
        self.assertEqual(caught.exception.code, "invalid_runtime_env")

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
        generic = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {
                "profile": "generic-observe",
                "expected_markers": ["APP_READY"],
            },
        )
        self.assertEqual(generic["expected_markers"], ["APP_READY"])
        self.assertEqual(generic["net_mode"], "user,restrict=yes")
        self.assertEqual(generic["console_mode"], "auto")
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
            with self.assertRaises(ServiceError) as wrong_device:
                device_service_module.parse_qemu_wifi_execution(
                    self.service.specs["atoms3r"],
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
                        "core2-openmac",
                        "core2-ble-advertise",
                        "core2-hci-gatt",
                    ],
                )
                self.assertEqual(row["network_status"], "unverified")
                self.assertFalse(row["features"]["network"])
                self.assertEqual(
                    gated.capacity()["modes"]["qemu-wifi"],
                    "enabled-sticks3-and-core2",
                )
                self.assertEqual(
                    gated.capacity()["modes"]["qemu-ble"],
                    "enabled-core2-experimental",
                )
            finally:
                gated.close_all()
        finally:
            if old is None:
                os.environ.pop("M5_CORE2_WIFI_QEMU", None)
            else:
                os.environ["M5_CORE2_WIFI_QEMU"] = old

    def test_experimental_qemu_ble_is_core2_only_and_env_gated(self):
        fake_qemu = Path(self.tmp.name) / "qemu-core2-radio"
        fake_qemu.write_bytes(b"fake")
        fake_qemu.chmod(0o755)
        old_radio = os.environ.get("M5_CORE2_RADIO_QEMU")
        old_wifi = os.environ.get("M5_CORE2_WIFI_QEMU")
        os.environ.pop("M5_CORE2_WIFI_QEMU", None)
        os.environ["M5_CORE2_RADIO_QEMU"] = str(fake_qemu)
        try:
            parsed = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {
                    "profile": "core2-ble-advertise",
                    "expected_markers": ["CORE2_BLE_RESULT: PASSED"],
                },
            )
            self.assertEqual(parsed["profile"], "core2-ble-advertise")
            hci_gatt = device_service_module.parse_qemu_ble_execution(
                self.service.specs["core2"],
                {"profile": "core2-hci-gatt"},
            )
            self.assertEqual(hci_gatt["profile"], "core2-hci-gatt")
            self.assertEqual(
                hci_gatt["expected_markers"],
                list(device_service_module.CORE2_HCI_GATT_MARKERS),
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
            with self.assertRaises(ServiceError) as wrong_device:
                device_service_module.parse_qemu_ble_execution(
                    self.service.specs["papermono"],
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
        finally:
            if old_radio is None:
                os.environ.pop("M5_CORE2_RADIO_QEMU", None)
            else:
                os.environ["M5_CORE2_RADIO_QEMU"] = old_radio
            if old_wifi is None:
                os.environ.pop("M5_CORE2_WIFI_QEMU", None)
            else:
                os.environ["M5_CORE2_WIFI_QEMU"] = old_wifi

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
            runtime="qemu-ble",
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

    def _stopped_session(self, firmware: bytes = b"\xff" * 1024):
        spec = self.service.specs["sticks3"]
        firmware_path = Path(self.tmp.name) / "firmware.bin"
        firmware_path.write_bytes(firmware)
        session = DeviceSession(
            self.service,
            session_id="a" * 32,
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
        )
        session.serial0.write_text("ready\n")
        session.virtual_flash = session.dir / "virtual-flash.bin"
        session.virtual_flash.write_bytes(firmware)
        session.state = "stopped"
        self.service._sessions[session.id] = session
        return session

    def test_session_history_filter_and_clear(self):
        session = self._stopped_session()
        self.assertEqual(self.service.list_sessions(include_stopped=False)["sessions"], [])
        cleared = self.service.clear_stopped(purge=True)
        self.assertEqual(cleared["cleared"], 1)
        self.assertNotIn(session.id, self.service._sessions)

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

    def test_running_orphan_is_restored_as_interrupted_history(self):
        session = self._stopped_session()
        session.state = "running"
        session.completed_at = None
        session.pid = 12345
        session._persist_session()

        restarted = DeviceService(
            state_dir=self.service.state_dir,
            max_sessions=2,
            max_per_device=1,
        )
        try:
            rows = restarted.list_sessions()["sessions"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["state"], "failed")
            self.assertTrue(rows[0]["restored"])
            self.assertTrue(rows[0]["interrupted"])
            self.assertIn("service restarted", rows[0]["error"])
            self.assertEqual(restarted.capacity()["active_sessions"], 0)
            events = restarted.session_events(session.id)["events"]
            self.assertEqual(events[-1]["event"], "interrupted")
            self.assertEqual(events[-1]["previous_state"], "running")
        finally:
            restarted.close_all()


class DeviceServiceHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = DeviceService(state_dir=Path(cls.tmp.name))
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

    def test_openapi_is_served(self):
        with urlopen(self.base + "/api/v1/openapi.yaml", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"openapi: 3.1.0", response.read())

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
        cls.service = DeviceService(state_dir=Path(cls.tmp.name))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
