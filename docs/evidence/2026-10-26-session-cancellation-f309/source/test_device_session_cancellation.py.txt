"""Deterministic host lifecycle races; no service, guest, or real process.

The actual Session constructor, start/provision, launch, stop, persistence and
lease cleanup run against temporary files. Event barriers replace only slow
external boundaries, so cancellation must fence real resource publication.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import device_service as service_module
from device_service import (
    DeviceService,
    DeviceSession,
    NetworkDeviceSession,
    ServiceError,
    Tab5DeviceSession,
)


class _Barrier:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def wait(self):
        self.entered.set()
        if not self.release.wait(5):
            raise AssertionError("test did not release the lifecycle barrier")


class _Process:
    """A handle whose wait genuinely blocks until test-owned termination."""

    def __init__(self, pid):
        self.pid = pid
        self.returncode = None
        self.exited = threading.Event()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if not self.exited.wait(timeout):
            raise subprocess.TimeoutExpired("inert-test-runtime", timeout)
        return self.returncode

    def send_signal(self, signum):
        self.returncode = -int(signum)
        self.exited.set()

    def terminate(self):
        self.send_signal(signal.SIGTERM)

    def kill(self):
        self.send_signal(signal.SIGKILL)


class DeviceSessionCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.sessions = []
        self.barriers = []
        self.completions = []
        self.thread_errors = []
        self.processes = []
        self.shutdown_threads = []
        self.resource_publications = []
        self.popen_barrier = None
        self.popen_barrier_call = 1
        self.popen_calls = 0
        self.prepared = self.root / "prepared-image"
        self.prepared.write_bytes(b"inert isolated flash fixture")
        self.emulator = self.root / "inert-emulator"
        self.emulator.write_text("not an executable runtime\n")
        self.specs = service_module.load_device_specs()
        self.stack.enter_context(mock.patch.object(
            service_module, "SESSION_STOP_WAIT_SECONDS", 0.04, create=True,
        ))
        self.popen = self.stack.enter_context(mock.patch.object(
            service_module.subprocess, "Popen", side_effect=self._popen,
        ))
        self.stack.enter_context(mock.patch.object(
            service_module, "inspect_process",
            return_value={"exists": False, "start_token": None, "command": ""},
        ))
        self.stack.enter_context(mock.patch.object(
            service_module.os, "killpg", side_effect=self._signal_process,
        ))
        self.stack.enter_context(mock.patch.object(
            service_module.os, "kill", side_effect=AssertionError("real OS signal"),
        ))
        self.stack.enter_context(mock.patch.object(
            service_module, "free_tcp_port", return_value=41001,
        ))
        self.stack.enter_context(mock.patch.object(
            service_module, "wait_for_fs_path", return_value=None,
        ))
        self.stack.enter_context(mock.patch.object(
            service_module, "wait_for_tcp_port", return_value=None,
        ))
        self.qmp = mock.Mock()
        self.qmp.cmd.return_value = {}
        self.wait_qmp = self.stack.enter_context(mock.patch.object(
            service_module, "wait_qmp", return_value=self.qmp,
        ))
        self.stack.enter_context(mock.patch.dict(
            service_module.os.environ,
            {"M5_NETWORK_EMULATOR": str(self.emulator)},
        ))
        self.addCleanup(self._finish_workers)

    def _barrier(self):
        barrier = _Barrier()
        self.barriers.append(barrier)
        return barrier

    def _signal_process(self, pid, signum):
        for process in self.processes:
            if process.pid == pid:
                process.send_signal(signum)
                return
        raise AssertionError("signal targets an unowned test process")

    def _popen(self, *args, **kwargs):
        self.popen_calls += 1
        if self.popen_barrier and self.popen_calls == self.popen_barrier_call:
            self.popen_barrier.wait()
        process = _Process(900000 + len(self.processes))
        self.processes.append(process)
        self.resource_publications.append(("process", self.sessions[-1].state))
        return process

    def _session(self, cls=DeviceSession, *, runtime="qemu", **overrides):
        tab5 = cls is Tab5DeviceSession
        device_id = "tab5" if tab5 else "atoms3r"
        spec = replace(
            self.specs[device_id], display=None, state_probes={},
            qemu=self.emulator, rom_dir=self.root, flash_size=self.prepared.stat().st_size,
            emulator=self.emulator, elf=self.prepared, rom=self.prepared,
            efuse=self.prepared, c6_firmware=self.prepared,
        )
        worker = SimpleNamespace(
            worker_id="cancellation-test-worker", generation=1,
            release_lease=mock.Mock(),
        )
        service = SimpleNamespace(
            state_dir=self.root, worker=worker,
            storage_policy=SimpleNamespace(retain_session_flash=False),
            prepare_flash=mock.Mock(return_value={
                "path": self.prepared, "info": {"transport": "inert-test"},
            }),
            raw_device=lambda _: {}, artifacts=SimpleNamespace(),
        )
        kwargs = dict(
            session_id=uuid.uuid4().hex, spec=spec, firmware_id="a" * 64,
            firmware_path=self.prepared,
            firmware_sha=hashlib.sha256(self.prepared.read_bytes()).hexdigest(),
            firmware_source="uploaded", source_artifacts=[], ttl_seconds=60,
            ready_marker=None, ready_timeout=1, ready_conditions=None,
            runtime=runtime, worker_lease_active=True,
        )
        if cls is NetworkDeviceSession:
            kwargs["network_config"] = {"chip": "esp32s3", "profile": "test-only"}
        kwargs.update(overrides)
        session = cls(service, **kwargs)
        session.qmp_path = session.dir / "qmp.sock"
        if tab5:
            session._hosted_socket = session.dir / "hosted.sock"
        self.sessions.append(session)
        return session

    def _start(self, session):
        completed = threading.Event()
        self.completions.append(completed)
        provision = session._provision

        def observed_provision():
            try:
                provision()
            except BaseException as error:
                self.thread_errors.append(error)
            finally:
                completed.set()

        self.stack.enter_context(mock.patch.object(
            session, "_provision", side_effect=observed_provision,
        ))
        session.start()
        return completed

    def _finish_workers(self):
        for barrier in self.barriers:
            barrier.release.set()
        for completed in self.completions:
            completed.wait(2)
        for process in self.processes:
            process.terminate()
        for session in self.sessions:
            session.stop()
        for thread in self.shutdown_threads:
            thread.join(2)

    def _cancel_at(
        self, session, barrier, *, stop_options=None, retain_flash=False,
        purge=False, pending_check=None,
    ):
        completed = self._start(session)
        self.assertTrue(barrier.entered.wait(2), "provision never reached barrier")
        stop_done = threading.Event()
        responses = []

        def request_stop():
            try:
                responses.append(session.stop(**(stop_options or {})))
            except BaseException as error:
                self.thread_errors.append(error)
            finally:
                stop_done.set()

        stopper = threading.Thread(target=request_stop, daemon=True)
        stopper.start()
        try:
            self.assertTrue(session._stop_event.wait(1), "stop must publish cancellation before waiting")
            self.assertTrue(stop_done.wait(1), "stop must return within the bounded wait")
            self.assertEqual(len(responses), 1, self.thread_errors)
            pending = responses[0]
            self.assertEqual(pending["state"], "stopping")
            self.assertTrue(pending["stop_pending"])
            self.assertEqual(pending["session_id"], session.id)
            self.assertEqual(pending["device_id"], session.spec.id)
            self.assertFalse(completed.is_set())
            self.assertTrue(session.dir.is_dir(), "pending stop must not purge live transaction files")
            self.assertTrue(session._worker_lease_active)
            session.service.worker.release_lease.assert_not_called()
            self.assertIsNone(session.completed_at)
            if pending_check:
                pending_check()
        finally:
            barrier.release.set()
            self.assertTrue(completed.wait(2), "provision failed to leave cancelled stage")
            stopper.join(2)
        automatic = session.snapshot()
        self.assertEqual(automatic["state"], "stopped", "cancelled transaction must finalize without caller retry")
        result = automatic if retain_flash or purge else session.stop()
        self.assertEqual(result["state"], "stopped", self.thread_errors)
        self.assertFalse(result.get("stop_pending", False))
        self.assertTrue(session._stop_event.is_set())
        if retain_flash:
            self.assertTrue(result["flash_retained"])
            self.assertEqual(session.virtual_flash.read_bytes(), self.prepared.read_bytes())
        else:
            self.assertFalse((session.dir / "virtual-flash.bin").exists())
            if not purge:
                self.assertFalse(result["flash_retained"])
        self.assertFalse(session._worker_lease_active)
        self.assertIsNotNone(session.completed_at)
        if purge:
            self.assertFalse(session.dir.exists())
            self.assertEqual(session.stop(purge=True)["state"], "stopped")
            self.assertFalse(session.dir.exists(), "repeated stop must not recreate purged history")
        else:
            persisted = json.loads(session.session_record_path.read_text())
            self.assertEqual(persisted["state"], "stopped")
        session.service.worker.release_lease.assert_called_once()
        self.assertFalse(self.thread_errors, self.thread_errors)
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        self.assertFalse(any(state in {"stopped", "failed"} for _, state in self.resource_publications))
        self.assertFalse(any(event.get("to") == "running" for event in session.events))
        return result

    def test_cancel_during_prepare_is_bounded_and_never_launches(self):
        session = self._session()
        barrier = self._barrier()

        def prepare(*args, **kwargs):
            barrier.wait()
            return {"path": self.prepared, "info": {"transport": "inert-test"}}

        session.service.prepare_flash.side_effect = prepare
        self._cancel_at(session, barrier)
        self.popen.assert_not_called()
        self.assertFalse(any(event["event"] == "failed" for event in session.events))

    def test_stop_before_provision_remains_terminal(self):
        session = self._session()
        self.assertEqual(session.stop()["state"], "stopped")
        session._provision()
        self.assertEqual(session.snapshot()["state"], "stopped")
        self.assertTrue(session._stop_event.is_set())
        session.service.prepare_flash.assert_not_called()
        self.popen.assert_not_called()
        session.service.worker.release_lease.assert_called_once()

    def test_cancel_during_flash_copy_does_not_publish_after_terminal(self):
        session = self._session()
        barrier = self._barrier()
        copyfile = service_module.shutil.copyfile

        def delayed_copy(source, destination, *args, **kwargs):
            if Path(destination).name == "virtual-flash.bin":
                barrier.wait()
                self.resource_publications.append(("flash", session.state))
            return copyfile(source, destination, *args, **kwargs)

        self.stack.enter_context(mock.patch.object(
            service_module.shutil, "copyfile", side_effect=delayed_copy,
        ))
        self._cancel_at(session, barrier)
        self.popen.assert_not_called()

    def test_cancel_during_sd_copy_cannot_launch_or_release_lease_early(self):
        session = self._session()
        sd = self.root / "source-sd"
        sd.write_bytes(b"test SD fixture")
        session.storage_config = {"sd_image_artifact_id": hashlib.sha256(sd.read_bytes()).hexdigest()}
        session.service.artifacts.path = mock.Mock(return_value=sd)
        barrier = self._barrier()
        copyfile = service_module.shutil.copyfile

        def delayed_copy(source, destination, *args, **kwargs):
            if Path(destination) == session.sd_card_image:
                barrier.wait()
                self.resource_publications.append(("sd", session.state))
            return copyfile(source, destination, *args, **kwargs)

        self.stack.enter_context(mock.patch.object(
            service_module.shutil, "copyfile", side_effect=delayed_copy,
        ))
        self._cancel_at(session, barrier)
        self.popen.assert_not_called()

    def test_cancel_while_popen_returns_reaps_the_late_handle(self):
        session = self._session()
        self.popen_barrier = self._barrier()
        self._cancel_at(session, self.popen_barrier)
        self.assertEqual(self.popen.call_count, 1)

    def test_cancel_during_qmp_handshake_is_bounded_and_reaps_runtime(self):
        session = self._session()
        barrier = self._barrier()

        def delayed_qmp(*args, **kwargs):
            barrier.wait()
            return self.qmp

        self.wait_qmp.side_effect = delayed_qmp
        self._cancel_at(session, barrier)
        self.assertEqual(self.popen.call_count, 1)

    def test_cancel_during_readiness_never_publishes_running(self):
        session = self._session(ready_marker="APPLICATION_READY")
        barrier = self._barrier()
        self.stack.enter_context(mock.patch.object(
            session, "wait_for_marker", side_effect=lambda *args: barrier.wait(),
        ))
        self._cancel_at(session, barrier)
        self.assertEqual(self.popen.call_count, 1)

    def test_purge_pending_waits_for_transaction_and_does_not_recreate_history(self):
        session = self._session()
        barrier = self._barrier()

        def prepare(*args, **kwargs):
            barrier.wait()
            return {"path": self.prepared, "info": {"transport": "inert-test"}}

        session.service.prepare_flash.side_effect = prepare
        self._cancel_at(session, barrier, stop_options={"purge": True}, purge=True)
        self.popen.assert_not_called()

    def test_pending_stop_preserves_explicit_retain_flash_during_auto_finalize(self):
        session = self._session()
        barrier = self._barrier()

        def delayed_qmp(*args, **kwargs):
            barrier.wait()
            return self.qmp

        self.wait_qmp.side_effect = delayed_qmp
        self._cancel_at(
            session, barrier, stop_options={"retain_flash": True}, retain_flash=True,
        )

    def test_normal_retain_flash_and_explicit_release(self):
        session = self._session()
        session._provision()
        retained = session.stop(retain_flash=True)
        self.assertEqual(retained["state"], "stopped")
        self.assertTrue(retained["flash_retained"])
        self.assertEqual(session.virtual_flash.read_bytes(), self.prepared.read_bytes())
        released = session.stop(retain_flash=False)
        self.assertFalse(released["flash_retained"])
        session.service.worker.release_lease.assert_called_once()

    def _stop_with_later_intent(self, later_options):
        session = self._session()
        session._provision()
        barrier = self._barrier()
        terminate = session._terminate_runtime

        def blocked_terminate():
            barrier.wait()
            terminate()

        self.stack.enter_context(mock.patch.object(
            session, "_terminate_runtime", side_effect=blocked_terminate,
        ))
        first_done = threading.Event()
        self.completions.append(first_done)
        first_results = []

        def first_stop():
            try:
                first_results.append(session.stop(retain_flash=True))
            except BaseException as error:
                self.thread_errors.append(error)
            finally:
                first_done.set()

        first = threading.Thread(target=first_stop, daemon=True)
        first.start()
        try:
            self.assertTrue(barrier.entered.wait(2))
            pending = session.stop(**later_options)
            self.assertEqual(pending["state"], "stopping")
            self.assertTrue(pending["stop_pending"])
            self.assertTrue(session.dir.is_dir())
            self.assertTrue(session.virtual_flash.is_file())
            session.service.worker.release_lease.assert_not_called()
        finally:
            barrier.release.set()
            self.assertTrue(first_done.wait(2))
            first.join(1)
        self.assertFalse(self.thread_errors, self.thread_errors)
        self.assertEqual(len(first_results), 1)
        self.assertEqual(first_results[0]["state"], "stopped")
        self.assertFalse(session._worker_lease_active)
        session.service.worker.release_lease.assert_called_once()
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        return session, first_results[0]

    def test_inflight_stop_consumes_later_purge_without_caller_retry(self):
        session, _ = self._stop_with_later_intent({"purge": True})
        self.assertFalse(session.dir.exists(), "first stop ignored later pending purge")

    def test_inflight_stop_consumes_later_flash_release_without_caller_retry(self):
        session, result = self._stop_with_later_intent({"retain_flash": False})
        self.assertTrue(session.dir.is_dir())
        self.assertFalse(result["flash_retained"])
        self.assertFalse((session.dir / "virtual-flash.bin").exists())

    def test_lease_release_failure_keeps_stop_pending_until_retry(self):
        session = self._session()
        session._provision()
        release = session.service.worker.release_lease
        release.side_effect = RuntimeError("test lease backend unavailable")
        try:
            with self.assertRaises(ServiceError) as caught:
                session.stop()
            self.assertEqual(caught.exception.code, "worker_lease_release_pending")
            pending = session.snapshot()
            self.assertEqual(pending["state"], "stopping")
            self.assertTrue(pending["stop_pending"])
            self.assertIsNone(session.completed_at)
            self.assertTrue(session._worker_lease_active)
            self.assertTrue(session.virtual_flash.is_file())
            self.assertTrue(all(process.poll() is not None for process in self.processes))
        finally:
            release.side_effect = None
        recovered = session.stop()
        self.assertEqual(recovered["state"], "stopped")
        self.assertFalse(recovered["flash_retained"])
        self.assertFalse(session._worker_lease_active)
        self.assertEqual(release.call_count, 2)
        self.assertEqual(self.popen.call_count, 1)

    def test_pending_snapshot_does_not_wait_for_qmp_session_lock(self):
        session = self._session()
        barrier = self._barrier()

        def delayed_qmp(*args, **kwargs):
            barrier.wait()
            return self.qmp

        self.wait_qmp.side_effect = delayed_qmp

        def pending_snapshot():
            done = threading.Event()
            results = []

            def read_snapshot():
                results.append(session.snapshot())
                done.set()

            reader = threading.Thread(target=read_snapshot, daemon=True)
            reader.start()
            self.assertTrue(done.wait(0.5), "pending snapshot waited on blocked QMP lock")
            reader.join(1)
            self.assertEqual(results[0]["session_id"], session.id)
            self.assertEqual(results[0]["state"], "stopping")
            self.assertTrue(results[0]["stop_pending"])

        self._cancel_at(session, barrier, pending_check=pending_snapshot)

    def test_cancelled_radio_failure_never_retries_launch(self):
        session = self._session(
            runtime="qemu-wifi", ready_marker="RADIO_READY",
            network_config={"profile": "test-only", "attempts": 3},
        )
        barrier = self._barrier()

        def failed_ready(*args):
            barrier.wait()
            raise ServiceError("ready_timeout", "test readiness timeout", 408)

        self.stack.enter_context(mock.patch.object(session, "wait_for_marker", side_effect=failed_ready))
        self.stack.enter_context(mock.patch.object(session, "network_evidence", return_value={"status": "RUNNING"}))
        self.stack.enter_context(mock.patch.object(session, "_finalize_network_capture", return_value={}))
        self._cancel_at(session, barrier)
        self.assertEqual(self.popen.call_count, 1)

    def test_network_cancel_during_copy_uses_shared_lifecycle(self):
        session = self._session(NetworkDeviceSession, runtime="network")
        barrier = self._barrier()
        copyfile = service_module.shutil.copyfile

        def delayed_copy(source, destination, *args, **kwargs):
            if Path(destination).name == "virtual-flash.bin":
                barrier.wait()
                self.resource_publications.append(("network-flash", session.state))
            return copyfile(source, destination, *args, **kwargs)

        self.stack.enter_context(mock.patch.object(service_module.shutil, "copyfile", side_effect=delayed_copy))
        self._cancel_at(session, barrier)
        self.popen.assert_not_called()

    def test_network_cancel_during_popen_reaps_runner(self):
        session = self._session(NetworkDeviceSession, runtime="network")
        self.popen_barrier = self._barrier()
        self._cancel_at(session, self.popen_barrier)
        self.assertEqual(self.popen.call_count, 1)

    @staticmethod
    def _network_lifecycle_receipt(session):
        return {
            "schema_version": 1,
            "kind": "m5stack-network-lane-lifecycle",
            "state": "cleanup-complete", "cleanup_complete": True,
            "runner": {
                "pid": session._proc.pid,
                "start_token": session.process_start_token,
                "command_sha256": session._network_runner_command_sha256,
            },
            "children": {"ble": None, "emulator": None},
        }

    def _complete_network_naturally(
        self, session, *, mutate_receipt=None, runner_start_token=None,
    ):
        handled = threading.Event()
        handle_exit = session._handle_process_exit

        def observed_exit(returncode):
            try:
                handle_exit(returncode)
            except BaseException as error:
                self.thread_errors.append(error)
            finally:
                handled.set()

        self.stack.enter_context(mock.patch.object(
            session, "_handle_process_exit", side_effect=observed_exit,
        ))
        session._provision()
        self.assertEqual(session.state, "running")
        if runner_start_token is not None:
            session.process_start_token = runner_start_token
        receipt = self._network_lifecycle_receipt(session)
        if mutate_receipt:
            mutate_receipt(receipt)
        (session.network_dir / "lifecycle.json").write_text(json.dumps(receipt))
        session._network_evidence_path().write_text(json.dumps({"status": "PASS"}))
        self.processes[-1].send_signal(0)
        self.assertTrue(handled.wait(2), "network monitor did not handle natural completion")
        self.assertFalse(self.thread_errors, self.thread_errors)

    def test_network_natural_completion_releases_worker_lease(self):
        session = self._session(NetworkDeviceSession, runtime="network")
        self._complete_network_naturally(session)
        self.assertEqual(session.snapshot()["state"], "stopped")
        self.assertFalse(session._worker_lease_active)
        self.assertFalse((session.dir / "virtual-flash.bin").exists())
        session.service.worker.release_lease.assert_called_once()

    def test_network_natural_completion_lease_failure_stays_pending(self):
        session = self._session(NetworkDeviceSession, runtime="network")
        release = session.service.worker.release_lease
        release.side_effect = RuntimeError("test lease backend unavailable")
        try:
            self._complete_network_naturally(session)
            self.assertEqual(session.snapshot()["state"], "stopping")
            self.assertIsNone(session.completed_at)
            self.assertTrue(session._worker_lease_active)
        finally:
            release.side_effect = None
        self.assertEqual(session.stop()["state"], "stopped")
        self.assertFalse(session._worker_lease_active)
        self.assertEqual(release.call_count, 2)

    def _reject_network_receipt(self, mutate, *, runner_start_token=None):
        session = self._session(NetworkDeviceSession, runtime="network")
        try:
            self._complete_network_naturally(
                session, mutate_receipt=mutate, runner_start_token=runner_start_token,
            )
            self.assertEqual(session.snapshot()["state"], "stopping")
            self.assertTrue(session._worker_lease_active)
            self.assertIsNone(session.completed_at)
            self.assertTrue(session.virtual_flash.is_file())
            session.service.worker.release_lease.assert_not_called()
            with self.assertRaises(ServiceError) as caught:
                session.stop()
            self.assertEqual(caught.exception.code, "session_cleanup_pending")
            self.assertTrue(session._worker_lease_active)
            session.service.worker.release_lease.assert_not_called()
        finally:
            # A valid replacement is required even for test teardown. Never
            # bypass the real external-cleanup gate to release the lease.
            if session._proc is not None:
                (session.network_dir / "lifecycle.json").write_text(
                    json.dumps(self._network_lifecycle_receipt(session))
                )
        recovered = session.stop()
        self.assertIn(recovered["state"], {"stopped", "failed"})
        self.assertFalse(session._worker_lease_active)
        session.service.worker.release_lease.assert_called_once()

    def test_network_incomplete_cleanup_receipt_keeps_lease_pending(self):
        def incomplete(receipt):
            receipt["state"] = "cleanup-pending"
            receipt["cleanup_complete"] = False

        self._reject_network_receipt(incomplete)

    def test_network_wrong_runner_pid_keeps_lease_pending(self):
        self._reject_network_receipt(
            lambda receipt: receipt["runner"].__setitem__("pid", receipt["runner"]["pid"] + 1),
        )

    def test_network_wrong_runner_token_keeps_lease_pending(self):
        self._reject_network_receipt(
            lambda receipt: receipt["runner"].__setitem__("start_token", "different-runner-start"),
            runner_start_token="expected-runner-start",
        )

    def test_tab5_cancel_during_prepare_never_launches_either_chip(self):
        session = self._session(Tab5DeviceSession)
        barrier = self._barrier()

        def prepare(*args, **kwargs):
            barrier.wait()
            return {"path": self.prepared, "info": {"transport": "inert-test"}}

        session.service.prepare_flash.side_effect = prepare
        self._cancel_at(session, barrier)
        self.popen.assert_not_called()

    def test_tab5_cancel_during_c6_popen_reaps_companion(self):
        session = self._session(Tab5DeviceSession)
        self.popen_barrier = self._barrier()
        self._cancel_at(session, self.popen_barrier)
        self.assertEqual(self.popen.call_count, 1)

    def test_tab5_cancel_during_p4_popen_reaps_both_chips(self):
        session = self._session(Tab5DeviceSession)
        self.popen_barrier = self._barrier()
        self.popen_barrier_call = 2
        self._cancel_at(session, self.popen_barrier)
        self.assertEqual(self.popen.call_count, 2)

    def test_tab5_reset_cancel_automatically_finalizes_without_stop_retry(self):
        session = self._session(Tab5DeviceSession)
        session._provision()
        self.assertEqual(session.state, "running")
        self.assertEqual(self.popen.call_count, 2)
        barrier = self._barrier()
        self.popen_barrier = barrier
        self.popen_barrier_call = 3
        reset_done = threading.Event()
        self.completions.append(reset_done)
        reset_errors = []

        def reset_session():
            try:
                session.reset()
            except ServiceError as error:
                reset_errors.append(error)
            finally:
                reset_done.set()

        resetter = threading.Thread(target=reset_session, daemon=True)
        resetter.start()
        try:
            self.assertTrue(barrier.entered.wait(2))
            pending = session.stop()
            self.assertEqual(pending["state"], "stopping")
            self.assertTrue(pending["stop_pending"])
            session.service.worker.release_lease.assert_not_called()
        finally:
            barrier.release.set()
            self.assertTrue(reset_done.wait(2))
            resetter.join(1)
        self.assertEqual(session.snapshot()["state"], "stopped")
        self.assertTrue(reset_errors)
        self.assertTrue(all(error.code == "session_stopping" for error in reset_errors))
        self.assertFalse(session._worker_lease_active)
        session.service.worker.release_lease.assert_called_once()
        self.assertFalse((session.dir / "virtual-flash.bin").exists())
        self.assertEqual(self.popen.call_count, 3)
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        self.assertEqual(sum(event.get("to") == "running" for event in session.events), 1)

    def test_tab5_reset_launch_failure_reaps_both_chips_and_preserves_failure(self):
        session = self._session(Tab5DeviceSession)
        session._provision()
        self.assertEqual(self.popen.call_count, 2)

        def fail_restart_p4(*args, **kwargs):
            if self.popen_calls == 3:
                raise RuntimeError("test Tab5 P4 restart failed")
            return self._popen(*args, **kwargs)

        self.popen.side_effect = fail_restart_p4
        with self.assertRaisesRegex(RuntimeError, "test Tab5 P4 restart failed"):
            session.reset()
        failed = session.snapshot()
        self.assertEqual(failed["state"], "failed")
        self.assertIn("test Tab5 P4 restart failed", failed["error"])
        self.assertEqual(self.popen.call_count, 4)
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        self.assertFalse(session._worker_lease_active)
        session.service.worker.release_lease.assert_called_once()
        self.assertFalse((session.dir / "virtual-flash.bin").exists())
        self.assertEqual(session.stop()["state"], "failed")

    def test_set_state_cannot_resurrect_terminal_sessions(self):
        for terminal in ("stopped", "failed"):
            with self.subTest(terminal=terminal):
                session = self._session(initial_state=terminal)
                for transition in ("flashing", "booting", "running"):
                    with self.assertRaises(ServiceError):
                        session._set_state(transition)
                    self.assertEqual(session.state, terminal)
        self.popen.assert_not_called()

    def test_set_state_cannot_publish_running_after_cancel_request(self):
        session = self._session(initial_state="booting")
        session._stop_event.set()
        with self.assertRaises(ServiceError):
            session._set_state("running")
        self.assertFalse(any(event.get("to") == "running" for event in session.events))

    def _admission_service(self, stopping_session, *, max_sessions=1):
        # Avoid DeviceService.__init__: no worker heartbeat or janitor thread.
        service = DeviceService.__new__(DeviceService)
        service._lock = threading.RLock()
        service._stop = threading.Event()
        service._sessions = {stopping_session.id: stopping_session}
        service.specs = dict(self.specs)
        service.specs[stopping_session.spec.id] = replace(
            stopping_session.spec, flash_emulator=None,
        )
        service.max_sessions = max_sessions
        service.max_per_device = 1
        service.default_ttl = 60
        service.worker = stopping_session.service.worker
        service._session_idempotency = {}
        service._worker_summary = mock.Mock(return_value={"accepting_leases": True})
        service.worker_status = mock.Mock(return_value={"accepting_leases": True})
        service._ensure_storage_capacity = mock.Mock()
        service.reference_info = mock.Mock(return_value={
            "firmware_id": stopping_session.firmware_id,
            "path": self.prepared,
            "sha256": stopping_session.firmware_sha,
        })
        return service

    def test_stopping_session_keeps_capacity_until_cleanup_finishes(self):
        session = self._session(initial_state="stopping")
        service = self._admission_service(session)
        occupied = service.capacity()
        self.assertEqual(occupied["active_sessions"], 1)
        self.assertEqual(occupied["available_sessions"], 0)
        self.assertEqual(occupied["by_device"], {session.spec.id: 1})
        listed = service.list_sessions(include_stopped=False)["sessions"]
        self.assertEqual([item["session_id"] for item in listed], [session.id])
        session.stop()
        available = service.capacity()
        self.assertEqual(available["active_sessions"], 0)
        self.assertEqual(available["available_sessions"], 1)

    def test_global_admission_rejects_capacity_occupied_by_stopping(self):
        session = self._session(initial_state="stopping")
        service = self._admission_service(session)
        with self.assertRaises(ServiceError) as caught:
            service.create_session({"device_id": session.spec.id})
        self.assertEqual(caught.exception.code, "capacity_exhausted")
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(list(service._sessions), [session.id])
        self.popen.assert_not_called()

    def test_device_admission_rejects_slot_occupied_by_stopping(self):
        session = self._session(initial_state="stopping")
        service = self._admission_service(session, max_sessions=2)
        with self.assertRaises(ServiceError) as caught:
            service.create_session({"device_id": session.spec.id})
        self.assertEqual(caught.exception.code, "device_capacity_exhausted")
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(list(service._sessions), [session.id])
        self.popen.assert_not_called()

    def test_close_all_drains_until_provision_and_lease_are_finished(self):
        session = self._session()
        service = self._admission_service(session)
        service._shutdown_lock = threading.Lock()
        service._shutdown_thread = None
        service._worker_closed = False
        service._janitor = threading.Thread(target=lambda: None, daemon=True)
        service._janitor.start()
        service._janitor.join()
        service.worker.started = True
        service.worker.snapshot = mock.Mock(side_effect=lambda: {
            "active_lease_count": int(session._worker_lease_active),
        })
        service.worker.drain = mock.Mock()
        closed = threading.Event()
        close_observations = []
        barrier = self._barrier()

        def worker_close():
            close_observations.append({
                "state": session.state,
                "lease_active": session._worker_lease_active,
                "prepare_released": barrier.release.is_set(),
                "flash_exists": (session.dir / "virtual-flash.bin").exists(),
            })
            closed.set()

        service.worker.close = mock.Mock(side_effect=worker_close)

        def prepare(*args, **kwargs):
            barrier.wait()
            return {"path": self.prepared, "info": {"transport": "inert-test"}}

        session.service.prepare_flash.side_effect = prepare
        completed = self._start(session)
        try:
            self.assertTrue(barrier.entered.wait(2))
            draining = service.close_all()
            self.assertEqual(draining["state"], "draining")
            self.assertEqual(draining["pending_sessions"], [session.id])
            shutdown = service._shutdown_thread
            self.assertIsNotNone(shutdown)
            self.shutdown_threads.append(shutdown)
            self.assertFalse(shutdown.daemon)
            repeated = service.close_all()
            self.assertEqual(repeated["state"], "draining")
            self.assertIs(service._shutdown_thread, shutdown)
            service.worker.close.assert_not_called()
            service.worker.release_lease.assert_not_called()
            self.assertTrue(session._worker_lease_active)
            self.assertTrue(service._stop.is_set())
            with self.assertRaises(ServiceError) as rejected:
                service.create_session({"device_id": session.spec.id})
            self.assertEqual(rejected.exception.code, "service_stopping")
            self.assertEqual(rejected.exception.status, 503)
        finally:
            barrier.release.set()
            self.assertTrue(completed.wait(2))
        self.assertTrue(closed.wait(2), "shutdown did not close worker after cleanup")
        service._shutdown_thread.join(2)
        self.assertFalse(service._shutdown_thread.is_alive())
        self.assertEqual(close_observations, [{
            "state": "stopped", "lease_active": False,
            "prepare_released": True, "flash_exists": False,
        }])
        service.worker.close.assert_called_once()
        service.worker.drain.assert_called_once()
        session.service.worker.release_lease.assert_called_once()
        self.assertEqual(service.close_all()["state"], "stopped")
        service.worker.close.assert_called_once()
        self.popen.assert_not_called()

    def test_close_all_waits_for_inflight_janitor_prune_before_worker_close(self):
        service = DeviceService.__new__(DeviceService)
        service._lock = threading.RLock()
        service._stop = threading.Event()
        service._sessions = {}
        service._shutdown_lock = threading.Lock()
        service._shutdown_thread = None
        service._worker_closed = False
        service.worker = SimpleNamespace(
            started=True, drain=mock.Mock(), close=mock.Mock(),
            snapshot=mock.Mock(return_value={"active_lease_count": 0}),
        )
        service.worker_queue = mock.Mock()
        service.worker_directory = mock.Mock()
        service.worker_directory.list_workers.return_value = {"workers": []}
        service.storage_policy = SimpleNamespace(prune_interval_seconds=0)
        barrier = self._barrier()
        service.prune_storage = mock.Mock(side_effect=barrier.wait)
        real_wait = service._stop.wait
        first_tick = True

        def immediate_first_tick(timeout):
            nonlocal first_tick
            if first_tick:
                first_tick = False
                return False
            return real_wait(timeout)

        self.stack.enter_context(mock.patch.object(
            service._stop, "wait", side_effect=immediate_first_tick,
        ))
        closed = threading.Event()
        close_observations = []

        def worker_close():
            close_observations.append({
                "janitor_alive": service._janitor.is_alive(),
                "prune_released": barrier.release.is_set(),
            })
            closed.set()

        service.worker.close.side_effect = worker_close
        service._janitor = threading.Thread(target=service._janitor_loop, daemon=True)
        self.shutdown_threads.append(service._janitor)
        service._janitor.start()
        try:
            self.assertTrue(barrier.entered.wait(2))
            draining = service.close_all()
            self.assertEqual(draining["state"], "draining")
            self.assertEqual(draining["pending_sessions"], [])
            shutdown = service._shutdown_thread
            self.assertIsNotNone(shutdown)
            self.shutdown_threads.append(shutdown)
            self.assertFalse(shutdown.daemon)
            self.assertTrue(service._janitor.is_alive())
            service.worker.close.assert_not_called()
            self.assertEqual(service.close_all()["state"], "draining")
            self.assertIs(service._shutdown_thread, shutdown)
            service.worker.close.assert_not_called()
        finally:
            barrier.release.set()
            service._janitor.join(2)
        self.assertFalse(service._janitor.is_alive())
        self.assertTrue(closed.wait(2))
        service._shutdown_thread.join(2)
        self.assertFalse(service._shutdown_thread.is_alive())
        self.assertEqual(close_observations, [{"janitor_alive": False, "prune_released": True}])
        service.worker.close.assert_called_once()
        service.worker.drain.assert_called_once()

    def test_create_started_before_shutdown_is_rejected_at_admission(self):
        session = self._session(initial_state="stopped")
        service = self._admission_service(session)
        reference = service.reference_info.return_value
        barrier = self._barrier()

        def lookup_reference(spec):
            barrier.wait()
            return reference

        service.reference_info.side_effect = lookup_reference
        done = threading.Event()
        self.completions.append(done)
        errors = []

        def create():
            try:
                service.create_session({"device_id": session.spec.id})
            except BaseException as error:
                errors.append(error)
            finally:
                done.set()

        creator = threading.Thread(target=create, daemon=True)
        creator.start()
        try:
            self.assertTrue(barrier.entered.wait(2))
            service._stop.set()
        finally:
            barrier.release.set()
            self.assertTrue(done.wait(2))
            creator.join(1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ServiceError)
        self.assertEqual(errors[0].code, "service_stopping")
        self.assertEqual(errors[0].status, 503)
        self.assertEqual(list(service._sessions), [session.id])
        self.popen.assert_not_called()

    def _owned_identity(self, session, pid, command):
        ownership = {"exists": True}
        start_token = "test-owned-process-start"

        def inspect(candidate):
            return {
                "exists": ownership["exists"] and candidate == pid,
                "start_token": start_token, "command": command,
            }

        clock = itertools.count()
        self.stack.enter_context(mock.patch.object(service_module, "inspect_process", side_effect=inspect))
        self.stack.enter_context(mock.patch.object(service_module.time, "time", side_effect=lambda: next(clock)))
        self.stack.enter_context(mock.patch.object(service_module.time, "sleep", return_value=None))
        self.stack.enter_context(mock.patch.object(session._stop_event, "wait", return_value=True))
        kill = self.stack.enter_context(mock.patch.object(service_module.os, "kill", return_value=None))
        killpg = self.stack.enter_context(mock.patch.object(service_module.os, "killpg", return_value=None))
        self.stack.enter_context(mock.patch.object(service_module.os, "getpgid", return_value=pid))
        return ownership, start_token, kill, killpg

    def test_reattached_qemu_still_owned_after_kill_keeps_identity_and_pending(self):
        session = self._session(initial_state="running")
        pid = 910001
        ownership, token, kill, _ = self._owned_identity(
            session, pid, "inert-qemu -qmp " + str(session.qmp_path),
        )
        session.pid = pid
        session.process_start_token = token
        session._reattached_process = True
        session.virtual_flash = session.dir / "virtual-flash.bin"
        session.virtual_flash.write_bytes(self.prepared.read_bytes())
        session.qmp_path.write_text("inert QMP ownership fixture")
        try:
            with self.assertRaises(ServiceError) as pending:
                session.stop()
            self.assertEqual(pending.exception.code, "session_cleanup_pending")
            self.assertEqual(session.snapshot()["state"], "stopping")
            self.assertEqual(session.pid, pid)
            self.assertEqual(session.process_start_token, token)
            self.assertTrue(session._reattached_process)
            self.assertTrue(session.qmp_path.exists())
            self.assertTrue(session.virtual_flash.is_file())
            self.assertTrue(session._worker_lease_active)
            self.assertIsNone(session.completed_at)
            session.service.worker.release_lease.assert_not_called()
            self.assertEqual([call.args[1] for call in kill.call_args_list], [signal.SIGTERM, signal.SIGKILL])
        finally:
            ownership["exists"] = False
        self.assertEqual(session.stop()["state"], "stopped")
        self.assertIsNone(session.pid)
        self.assertFalse(session._reattached_process)
        self.assertFalse(session.qmp_path.exists())
        session.service.worker.release_lease.assert_called_once()
        self.popen.assert_not_called()

    def test_reattached_ble_still_owned_after_kill_keeps_identity_and_pending(self):
        session = self._session(initial_state="running")
        pid = 910002
        command = "inert-ble-peer --session " + session.id
        ownership, token, _, killpg = self._owned_identity(session, pid, command)
        command_sha = hashlib.sha256(command.encode()).hexdigest()
        session._external_hci_probe_pid = pid
        session._external_hci_probe_start_token = token
        session._external_hci_probe_command_sha256 = command_sha
        session._companions["ble"] = {"state": "adopted", "adopted": True}
        try:
            with self.assertRaises(ServiceError) as pending:
                session.stop()
            self.assertEqual(pending.exception.code, "session_cleanup_pending")
            self.assertEqual(session.snapshot()["state"], "stopping")
            self.assertEqual(session._external_hci_probe_pid, pid)
            self.assertEqual(session._external_hci_probe_start_token, token)
            self.assertEqual(session._external_hci_probe_command_sha256, command_sha)
            self.assertEqual(session._companions["ble"]["state"], "adopted")
            self.assertTrue(session._worker_lease_active)
            self.assertIsNone(session.completed_at)
            session.service.worker.release_lease.assert_not_called()
            self.assertEqual([call.args[1] for call in killpg.call_args_list], [signal.SIGTERM, signal.SIGKILL])
        finally:
            ownership["exists"] = False
        self.assertEqual(session.stop()["state"], "stopped")
        self.assertIsNone(session._external_hci_probe_pid)
        self.assertIsNone(session._external_hci_probe_start_token)
        self.assertIsNone(session._external_hci_probe_command_sha256)
        self.assertEqual(session._companions["ble"]["state"], "terminated")
        session.service.worker.release_lease.assert_called_once()
        self.popen.assert_not_called()

    def test_normal_provision_and_repeated_stop_preserve_success(self):
        session = self._session()
        session._provision()
        self.assertEqual(session.snapshot()["state"], "running")
        self.assertEqual(self.popen.call_count, 1)
        self.assertFalse(session._stop_event.is_set())
        first = session.stop()
        second = session.stop()
        self.assertEqual(first["state"], "stopped")
        self.assertEqual(second["state"], "stopped")
        self.assertEqual(first["completed_at"], second["completed_at"])
        self.assertFalse(first["flash_retained"])
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        session.service.worker.release_lease.assert_called_once()

    def test_normal_prepare_failure_stays_failed_after_stop(self):
        session = self._session()
        session.service.prepare_flash.side_effect = RuntimeError("test preparation failed")
        session._provision()
        failed = session.snapshot()
        self.assertEqual(failed["state"], "failed")
        self.assertIn("test preparation failed", failed["error"])
        completed_at = failed["completed_at"]
        self.assertEqual(session.stop()["state"], "failed")
        self.assertEqual(session.completed_at, completed_at)
        session.service.worker.release_lease.assert_called_once()
        self.popen.assert_not_called()

    def test_normal_qmp_failure_reaps_process_and_preserves_failed_state(self):
        session = self._session()
        self.wait_qmp.side_effect = RuntimeError("test QMP unavailable")
        session._provision()
        failed = session.snapshot()
        self.assertEqual(failed["state"], "failed")
        self.assertIn("test QMP unavailable", failed["error"])
        self.assertEqual(session.stop()["state"], "failed")
        self.assertTrue(all(process.poll() is not None for process in self.processes))
        session.service.worker.release_lease.assert_called_once()


if __name__ == "__main__":
    unittest.main()
