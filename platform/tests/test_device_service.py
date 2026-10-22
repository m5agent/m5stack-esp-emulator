#!/usr/bin/env python3
from __future__ import annotations

import json
import io
import os
import socket
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
        self.assertIn(
            "uiflow2-sticks3",
            rows["sticks3"]["network_profiles"],
        )
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
        self.assertEqual(capacity["modes"]["tab5"], "enabled-partial")

    def test_default_capacity_matches_measured_workstation_profile(self):
        self.assertEqual(DEFAULT_MAX_SESSIONS, 12)
        self.assertEqual(DEFAULT_MAX_PER_DEVICE, 8)

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
        dns_udp = device_service_module.parse_network_execution(
            self.service.specs["sticks3"],
            {"profile": "idf-dns-udp"},
        )
        self.assertFalse(dns_udp["tcp"])
        self.assertEqual(dns_udp["net_mode"], "user")
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
