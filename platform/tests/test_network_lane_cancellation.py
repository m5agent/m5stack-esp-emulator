"""Network runner ownership and cancellation; no service or real processes."""
from __future__ import annotations

import hashlib
import io
import json
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import network_lane as lane


class _Output:
    def __init__(self, exited, *, ready=False):
        self.exited = exited
        self.lines = queue.Queue()
        self.closed = False
        if ready:
            self.lines.put("BLE_PROBE_READY\n")

    def __iter__(self):
        while True:
            try:
                yield self.lines.get(timeout=0.01)
            except queue.Empty:
                if self.exited.is_set():
                    return

    def close(self):
        self.closed = True


class _Process:
    def __init__(self, pid, *, ready=False, resistant=False, exited=False):
        self.pid = pid
        self.returncode = 0 if exited else None
        self.exited = threading.Event()
        if exited:
            self.exited.set()
        self.stdout = _Output(self.exited, ready=ready)
        self.resistant = resistant

    def poll(self):
        return self.returncode

    def send_signal(self, signum):
        if not self.resistant:
            self.returncode = -int(signum)
            self.exited.set()

    def terminate(self):
        self.send_signal(signal.SIGTERM)

    def kill(self):
        self.send_signal(signal.SIGKILL)

    def wait(self, timeout=None):
        # Failed cleanup is immediate in these tests, not a real 5-second wait.
        if self.resistant:
            raise subprocess.TimeoutExpired("inert-network-child", timeout)
        if not self.exited.wait(timeout=timeout):
            raise subprocess.TimeoutExpired("inert-network-child", timeout)
        return self.returncode


class NetworkLaneCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.out = self.root / "out"
        self.firmware = self.root / "firmware.bin"
        self.emulator = self.root / "emulator"
        self.firmware.write_bytes(b"inert-firmware")
        self.emulator.write_bytes(b"not-an-executable")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.processes = []
        self.handlers = {signal.SIGTERM: signal.SIG_DFL}
        self.ready = True
        self.cancel_role = None
        self.fail_role = None
        self.natural_emulator_exit = True
        self.popen_receipts = []
        self.stack.enter_context(mock.patch.object(
            lane, "process_identity", side_effect=self._identity,
        ))
        self.popen = self.stack.enter_context(mock.patch.object(
            lane.subprocess, "Popen", side_effect=self._popen,
        ))
        self.stack.enter_context(mock.patch.object(
            lane.signal, "getsignal", side_effect=lambda sig: self.handlers[sig],
        ))
        self.stack.enter_context(mock.patch.object(
            lane.signal, "signal", side_effect=self._set_handler,
        ))
        self.stack.enter_context(mock.patch.object(
            lane.os, "killpg", side_effect=self._signal_child,
        ))
        self.stack.enter_context(mock.patch.object(
            lane.os, "kill", side_effect=AssertionError("real OS signal forbidden"),
        ))
        self.stack.enter_context(mock.patch.object(lane, "free_port", return_value=19001))
        self.addCleanup(self._cleanup_fake_processes)

    def _identity(self, pid):
        return {
            "pid": pid, "start_token": f"test-start-{pid}",
            "command_sha256": hashlib.sha256(f"test-command-{pid}".encode()).hexdigest(),
            "identity_verified": True,
        }

    def _set_handler(self, sig, handler):
        previous = self.handlers[sig]
        self.handlers[sig] = handler
        return previous

    def _cancel(self):
        self.handlers[signal.SIGTERM](signal.SIGTERM, None)

    def _signal_child(self, pid, signum):
        for proc in self.processes:
            if proc.pid == pid:
                proc.send_signal(signum)
                return
        raise AssertionError("signal targets an unowned fake process")

    def _popen(self, command, **kwargs):
        self.assertTrue((self.out / "lifecycle.json").is_file())
        self.popen_receipts.append(self.receipt())
        role = "ble" if kwargs.get("stdout") is subprocess.PIPE else "emulator"
        if role == self.fail_role:
            raise OSError("inert launch failure")
        proc = _Process(
            910000 + len(self.processes), ready=self.ready,
            exited=role == "emulator" and self.natural_emulator_exit,
        )
        self.processes.append(proc)
        if role == self.cancel_role:
            self._cancel()
        return proc

    def _cleanup_fake_processes(self):
        for proc in self.processes:
            proc.resistant = False
            proc.kill()

    def config(self, **changes):
        values = dict(
            profile="generic-observe", chip="esp32s3", firmware=self.firmware,
            elf=None, emulator=self.emulator, out_dir=self.out, timeout=1,
            ssid="test-ssid", password="never-save-this-password",
            firmware_ap_password=None, wifi_auth="wpa2", psram_size="0",
            net_mode="user", hostfwd=[], console_mode="uart0", wifi=False,
            ble=True, ble_port=19002, ble_name="test-ble", tcp=False,
            expected_markers=[], i2c_devices=[],
        )
        values.update(changes)
        return lane.LaneConfig(**values)

    def receipt(self):
        return json.loads((self.out / "lifecycle.json").read_text())

    def lifecycle(self):
        self.out.mkdir(exist_ok=True)
        return lane.LaneLifecycle(self.out, threading.Event())

    def assert_complete(self, *, roles):
        receipt = self.receipt()
        self.assertEqual(receipt["state"], "cleanup-complete")
        self.assertTrue(receipt["cleanup_complete"])
        self.assertEqual(receipt["runner"]["pid"], lane.os.getpid())
        for role in ("emulator", "ble"):
            child = receipt["children"][role]
            if role in roles:
                self.assertEqual(child["state"], "exited")
                self.assertIsInstance(child["returncode"], int)
            else:
                self.assertIsNone(child)
        self.assertTrue(all(proc.poll() is not None for proc in self.processes))
        self.assertNotIn("never-save-this-password", json.dumps(receipt))
        self.assertEqual(list(self.out.glob(".lifecycle.json.*.tmp")), [])

    def test_starting_receipt_precedes_every_child_and_contains_no_command_text(self):
        lane.execute(self.config())
        self.assertEqual(len(self.popen_receipts), 2)
        first, second = self.popen_receipts
        self.assertEqual(first["state"], "starting")
        self.assertEqual(first["children"], {"emulator": None, "ble": None})
        self.assertEqual(second["state"], "children-known")
        self.assertIsNotNone(second["children"]["ble"])
        self.assertIsNone(second["children"]["emulator"])
        self.assert_complete(roles={"ble", "emulator"})
        self.assertNotIn('"command":', (self.out / "lifecycle.json").read_text())
        self.assertEqual(self.handlers[signal.SIGTERM], signal.SIG_DFL)

    def test_initial_receipt_write_failure_never_launches_a_child(self):
        with mock.patch.object(lane.os, "replace", side_effect=OSError("inert receipt failure")):
            with self.assertRaises(OSError):
                lane.execute(self.config())
        self.popen.assert_not_called()
        self.assertFalse((self.out / "lifecycle.json").exists())
        self.assertEqual(list(self.out.glob(".lifecycle.json.*.tmp")), [])
        self.assertEqual(self.handlers[signal.SIGTERM], signal.SIG_DFL)

    def test_signal_handler_precedes_receipt_construction_and_cancellation_cleans_empty_receipt(self):
        lifecycle_class = lane.LaneLifecycle

        def cancel_during_construction(out_dir, stop_requested):
            self.assertTrue(callable(self.handlers[signal.SIGTERM]))
            self._cancel()
            self.assertTrue(stop_requested.is_set())
            return lifecycle_class(out_dir, stop_requested)

        with mock.patch.object(lane, "LaneLifecycle", side_effect=cancel_during_construction):
            with self.assertRaises(lane.LaneCancelled):
                lane.execute(self.config())
        self.popen.assert_not_called()
        self.assert_complete(roles=set())
        self.assertEqual(self.handlers[signal.SIGTERM], signal.SIG_DFL)

    def test_cancel_before_first_spawn_never_creates_child(self):
        lifecycle = self.lifecycle()
        lifecycle.stop_requested.set()
        with self.assertRaises(lane.LaneCancelled):
            lifecycle.spawn("ble", ["inert"])
        lifecycle.cleanup()
        self.popen.assert_not_called()
        self.assert_complete(roles=set())

    def test_cancel_during_ble_popen_reaps_late_handle_and_never_starts_emulator(self):
        self.cancel_role = "ble"
        with self.assertRaises(lane.LaneCancelled):
            lane.execute(self.config())
        self.assertEqual(self.popen.call_count, 1)
        self.assert_complete(roles={"ble"})
        self.assertEqual(self.handlers[signal.SIGTERM], signal.SIG_DFL)

    def test_ble_readiness_is_cancelled_without_waiting_ten_seconds(self):
        self.ready = False
        entered = threading.Event()
        original = lane.wait_for_ble_ready

        def observed(*args, **kwargs):
            entered.set()
            return original(*args, **kwargs)

        def cancel_when_waiting():
            self.assertTrue(entered.wait(1))
            self._cancel()

        notifier = threading.Thread(target=cancel_when_waiting)
        notifier.start()
        started = time.monotonic()
        try:
            with mock.patch.object(lane, "wait_for_ble_ready", side_effect=observed):
                with self.assertRaises(lane.LaneCancelled):
                    lane.execute(self.config())
        finally:
            notifier.join(2)
        self.assertLess(time.monotonic() - started, 1)
        self.assertFalse(notifier.is_alive())
        self.assertEqual(self.popen.call_count, 1)
        self.assert_complete(roles={"ble"})

    def test_ready_event_cannot_override_a_cancel_request(self):
        lifecycle = self.lifecycle()
        ready = threading.Event()
        ready.set()
        lifecycle.stop_requested.set()
        with self.assertRaises(lane.LaneCancelled):
            lane.wait_for_ble_ready(ready, _Process(919999), lifecycle)
        lifecycle.cleanup()

    def test_cancel_during_emulator_popen_cleans_both_children(self):
        self.cancel_role = "emulator"
        self.natural_emulator_exit = False
        with self.assertRaises(lane.LaneCancelled):
            lane.execute(self.config())
        self.assertEqual(self.popen.call_count, 2)
        self.assert_complete(roles={"ble", "emulator"})

    def test_emulator_launch_failure_still_cleans_existing_ble_child(self):
        self.fail_role = "emulator"
        with self.assertRaises(OSError):
            lane.execute(self.config())
        self.assert_complete(roles={"ble"})

    def test_post_spawn_receipt_failure_does_not_forget_process(self):
        persist = lane.LaneLifecycle._persist
        failed = []

        def fail_once(instance):
            if instance.processes and not instance.cleanup_started and not failed:
                failed.append(True)
                raise OSError("inert child receipt failure")
            return persist(instance)

        with mock.patch.object(lane.LaneLifecycle, "_persist", fail_once):
            with self.assertRaises(OSError):
                lane.execute(self.config())
        self.assert_complete(roles={"ble"})

    def test_collector_start_failure_still_reaps_ble(self):
        with mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("inert thread failure")):
            with self.assertRaises(RuntimeError):
                lane.execute(self.config())
        self.assert_complete(roles={"ble"})

    def test_rapidly_reaped_child_can_complete_without_ps_identity(self):
        def identity(pid):
            if pid == lane.os.getpid():
                return self._identity(pid)
            return {"pid": pid, "start_token": None, "command_sha256": None,
                    "identity_verified": False}

        with mock.patch.object(lane, "process_identity", side_effect=identity):
            lane.execute(self.config(ble=False))
        self.assert_complete(roles={"emulator"})
        child = self.receipt()["children"]["emulator"]
        self.assertFalse(child["identity_verified"])
        self.assertIsNone(child["start_token"])

    def test_first_child_cleanup_failure_does_not_skip_second_child_or_fixture(self):
        lifecycle = self.lifecycle()
        self.natural_emulator_exit = False
        ble = lifecycle.spawn("ble", ["inert"], stdout=subprocess.PIPE)
        emulator = lifecycle.spawn("emulator", ["inert"], stdout=io.BytesIO())
        ble.resistant = True
        fixture = SimpleNamespace(close=mock.Mock())
        lifecycle.fixtures.append(fixture)
        with self.assertRaises(lane.LaneError):
            lifecycle.cleanup()
        self.assertIsNone(ble.poll())
        self.assertIsNotNone(emulator.poll())
        fixture.close.assert_called_once()
        receipt = self.receipt()
        self.assertFalse(receipt["cleanup_complete"])
        self.assertEqual(receipt["state"], "children-known")
        self.assertEqual(receipt["children"]["ble"]["state"], "cleanup-pending")

    def test_fixture_failure_cannot_publish_cleanup_complete(self):
        lifecycle = self.lifecycle()
        lifecycle.fixtures.append(SimpleNamespace(close=mock.Mock(side_effect=OSError("inert fixture failure"))))
        with self.assertRaises(lane.LaneError):
            lifecycle.cleanup()
        self.assertFalse(self.receipt()["cleanup_complete"])

    def test_failure_before_runtime_try_still_closes_fixture(self):
        fixture = SimpleNamespace(close=mock.Mock(), requests=[], port=19001)
        with mock.patch.object(lane, "start_lab_server", return_value=fixture), mock.patch.object(
            lane, "build_emulator_command", side_effect=ValueError("inert setup failure"),
        ):
            with self.assertRaises(ValueError):
                lane.execute(self.config(tcp=True))
        fixture.close.assert_called_once()
        self.popen.assert_not_called()
        self.assert_complete(roles=set())

    def test_interrupted_complete_publication_leaves_incomplete_atomic_receipt(self):
        lifecycle = self.lifecycle()
        proc = lifecycle.spawn("ble", ["inert"], stdout=subprocess.PIPE)
        previous = self.receipt()
        with mock.patch.object(lane.os, "replace", side_effect=OSError("inert interrupted write")):
            with self.assertRaises(OSError):
                lifecycle.cleanup()
        self.assertIsNotNone(proc.poll())
        self.assertEqual(self.receipt(), previous)
        self.assertFalse(self.receipt()["cleanup_complete"])
        self.assertEqual(list(self.out.glob(".lifecycle.json.*.tmp")), [])

    def test_identity_hash_uses_ps_command_without_storing_it(self):
        command = "python network_lane.py --password do-not-persist"
        replies = [SimpleNamespace(returncode=0, stdout="Mon Oct 26 10:00:00 2026\n"),
                   SimpleNamespace(returncode=0, stdout=command + "\n")]
        with mock.patch.object(lane.subprocess, "run", side_effect=replies):
            result = _REAL_PROCESS_IDENTITY(919999)
        self.assertTrue(result["identity_verified"])
        self.assertEqual(result["command_sha256"], hashlib.sha256(command.encode()).hexdigest())
        self.assertNotIn(command, json.dumps(result))


_REAL_PROCESS_IDENTITY = lane.process_identity


if __name__ == "__main__":
    unittest.main(verbosity=2)
