"""Probe cleanup distinguishes shared HTTP resources from owned processes."""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "api_sweep_run_guest_cleanup_test", ROOT / "tests/uiflow2/api_sweep/run_guest.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

from device_service import DeviceSession, STICKS3_WIFI_PROFILE, UnifiedHttpFixture


class ApiSweepCompanionCleanupTests(unittest.TestCase):
    def shared_snapshots(self, port=18081):
        worker = {"worker_id": "test-worker", "instance_id": "test-instance",
                  "generation": 1, "pid": os.getpid()}
        metadata = {"required": True, "state": "running", "pid": os.getpid(),
                    "port": port, "generation": 1, "ownership_verified": True,
                    "adopted": False, "recovery_action": "keep-running"}
        before = {"state": "running", "worker": worker,
                  "companions": {"http_fixture": metadata}}
        stopped = copy.deepcopy(before)
        stopped["state"] = "stopped"
        stopped["companions"]["http_fixture"].update(
            state="terminated", ownership_verified=False,
        )
        return before, stopped

    def test_real_shared_http_fixture_closes_its_listener_and_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = UnifiedHttpFixture(Path(temporary) / "requests.json", port=0)
            session = object.__new__(DeviceSession)
            session.runtime = "qemu-wifi"
            session.network_config = {"profile": STICKS3_WIFI_PROFILE}
            session._http_fixture = fixture
            before, stopped = self.shared_snapshots(fixture.server.server_port)
            session._companions = {"http": {
                key: value for key, value in before["companions"]["http_fixture"].items()
                if key != "required"
            }}
            session._companions["http"]["kind"] = "in-process-http-fixture"
            before["companions"] = session._companion_snapshot()
            try:
                self.assertTrue(fixture.thread.is_alive())
                session._close_http_fixture()
                stopped["companions"] = session._companion_snapshot()
                self.assertFalse(fixture.thread.is_alive())
                self.assertEqual(fixture.server.socket.fileno(), -1)
                inspect = mock.Mock(return_value={"exists": True})
                result = RUNNER.companion_cleanup(
                    before, stopped, runtime_pid_gone=True, worker_identity=before["worker"],
                    inspect_process=inspect,
                )
                self.assertTrue(result["companions_cleanup_complete"])
                self.assertEqual(result["companions_pid_gone"], {})
                self.assertEqual(result["companions_lifecycle"]["http_fixture"]["mode"],
                                 "shared-service-fixture")
                inspect.assert_not_called()
            finally:
                if session._http_fixture is not None:
                    session._close_http_fixture()

    def test_owned_child_must_exit_even_when_metadata_says_terminated(self):
        child = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE,
        )
        before = {"state": "running", "companions": {
            "ble_probe": {"required": True, "pid": child.pid, "state": "running"},
        }}
        stopped = copy.deepcopy(before)
        stopped["state"] = "stopped"
        stopped["companions"]["ble_probe"]["state"] = "terminated"
        try:
            result = RUNNER.companion_cleanup(before, stopped, runtime_pid_gone=True)
            self.assertFalse(result["companions_cleanup_complete"])
            self.assertEqual(result["companions_pid_gone"], {"ble_probe": False})
        finally:
            child.terminate()
            child.wait(timeout=5)
            child.stdin.close()
        result = RUNNER.companion_cleanup(before, stopped, runtime_pid_gone=True)
        self.assertTrue(result["companions_cleanup_complete"])
        self.assertEqual(result["companions_pid_gone"], {"ble_probe": True})

    def test_shared_http_fixture_without_termination_fails(self):
        before, stopped = self.shared_snapshots()
        stopped["companions"]["http_fixture"]["state"] = "running"
        result = RUNNER.companion_cleanup(
            before, stopped, runtime_pid_gone=True, worker_identity=before["worker"],
        )
        self.assertFalse(result["companions_cleanup_complete"])
        self.assertFalse(result["companions_lifecycle"]["http_fixture"]["route_terminated"])

    def test_an_arbitrary_live_pid_cannot_be_exempted_as_shared_http(self):
        for mismatch in ("pid", "instance_id", "generation", "port"):
            with self.subTest(mismatch=mismatch):
                before, stopped = self.shared_snapshots()
                if mismatch == "pid":
                    before["worker"]["pid"] += 1
                    stopped["worker"]["pid"] += 1
                elif mismatch == "generation":
                    stopped["worker"]["generation"] = 2
                elif mismatch == "instance_id":
                    before["worker"]["instance_id"] = None
                else:
                    stopped["companions"]["http_fixture"]["port"] += 1
                inspect = mock.Mock(return_value={"exists": True})
                result = RUNNER.companion_cleanup(
                    before, stopped, runtime_pid_gone=True, worker_identity=before["worker"],
                    inspect_process=inspect,
                )
                self.assertFalse(result["companions_cleanup_complete"])

    def test_qemu_embedded_route_needs_termination_and_runtime_exit(self):
        before, stopped = self.shared_snapshots(18089)
        for snapshot in (before, stopped):
            snapshot["companions"]["http_fixture"].update(
                pid=None, recovery_action="qemu-process-owned",
            )
        for terminated, runtime_gone in ((False, True), (True, False), (True, True)):
            with self.subTest(terminated=terminated, runtime_gone=runtime_gone):
                stopped["companions"]["http_fixture"]["state"] = "terminated" if terminated else "running"
                result = RUNNER.companion_cleanup(before, stopped, runtime_pid_gone=runtime_gone)
                self.assertEqual(result["companions_cleanup_complete"], terminated and runtime_gone)


if __name__ == "__main__":
    unittest.main()
