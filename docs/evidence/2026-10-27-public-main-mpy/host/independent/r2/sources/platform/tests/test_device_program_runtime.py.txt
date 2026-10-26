"""Host integration contracts for same-guest source execution.

Actual Session persistence, admission, launch assembly, stop and HTTP handlers
run against temporary files. QEMU/process and raw-REPL execution are mocked;
these tests do not execute firmware or contact the Device Service on 8787.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import device_service as service_module
from device_service import DeviceService, DeviceSession, ServiceError
from guest_console import GuestConsoleError
from program_revisions import ProgramRevisionStore, RevisionError
from program_packages import ProgramPackageStore
from serve import Handler
from uiflow_runtime import UIFlowRuntimeError, execution_markers


class _Console:
    def __init__(self, log, order=None):
        self.log = log
        self.log.touch(exist_ok=True)
        self.order = order if order is not None else []
        self.close_calls = 0

    def connect(self, **kwargs):
        self.order.append("console-connect")
        return self

    def offset(self):
        return self.log.stat().st_size

    def check_alive(self):
        if self.close_calls:
            raise GuestConsoleError("console_closed", "console is closed")

    def read_from(self, offset, limit):
        with self.log.open("rb") as stream:
            stream.seek(offset)
            return stream.read(limit)

    def append(self, value):
        with self.log.open("ab") as stream:
            stream.write(value)

    def close(self):
        self.close_calls += 1
        self.order.append("console-close")


class _Process:
    pid = 987654321

    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class _ProgramFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="m5-program-", dir="/tmp")
        self.root = Path(self.temporary.name)
        self.stack = ExitStack()
        self.sessions, self.threads = [], []
        self.addCleanup(self.cleanup)
        self.prepared = self.root / "inert-flash.bin"
        self.prepared.write_bytes(b"inert flash fixture")
        self.emulator = self.root / "not-an-executable"
        self.emulator.write_text("not a runnable emulator\n")
        self.spec = replace(
            service_module.load_device_specs()["atoms3r"], display=None,
            state_probes={}, qemu=self.emulator, rom_dir=self.root,
            flash_size=self.prepared.stat().st_size,
        )
        self.service = SimpleNamespace(
            state_dir=self.root,
            worker=SimpleNamespace(worker_id="program-fixture", generation=1, release_lease=mock.Mock()),
            storage_policy=SimpleNamespace(retain_session_flash=False),
            raw_device=lambda _: {},
            program_revisions=ProgramRevisionStore(self.root / "revisions"),
        )
        self.stack.enter_context(mock.patch.object(
            service_module, "inspect_process", return_value={"exists": False, "start_token": None, "command": None},
        ))
        self.stack.enter_context(mock.patch.object(
            service_module.os, "kill", side_effect=AssertionError("real OS signal forbidden"),
        ))
        self.stack.enter_context(mock.patch.object(
            service_module.os, "killpg", side_effect=AssertionError("real OS process-group signal forbidden"),
        ))
        self.popen = self.stack.enter_context(mock.patch.object(
            service_module.subprocess, "Popen", side_effect=AssertionError("unmocked process launch forbidden"),
        ))

    def cleanup(self):
        for session in self.sessions:
            session.stop()
        for thread in self.threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive(), "program fixture thread leaked")
        self.stack.close()
        self.temporary.cleanup()

    def session(self, *, transport="uart-repl", state="running", sid=None, restored=False, management_binding=None):
        session = DeviceSession(
            self.service, session_id=sid or uuid.uuid4().hex, spec=self.spec,
            firmware_id="a" * 64, firmware_path=self.prepared,
            firmware_sha=hashlib.sha256(self.prepared.read_bytes()).hexdigest(),
            firmware_source="reference", source_artifacts=[], ttl_seconds=60,
            ready_marker=None, ready_timeout=1, ready_conditions=None,
            initial_state=state, program_transport=transport, restored=restored,
            management_binding=management_binding,
        )
        session.qmp_path = session.dir / "qmp.sock"
        session.console_path = session.dir / "console.sock"
        self.sessions.append(session)
        return session

    def console(self, session, order=None):
        console = _Console(session.serial0, order)
        session._console = console
        return console

    def background(self, function):
        result = {}

        def run():
            try:
                result["value"] = function()
            except BaseException as error:
                result["error"] = error

        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        return thread, result

    def assert_service_error(self, function, *, code=None, status=None):
        with self.assertRaises(ServiceError) as caught:
            function()
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        return caught.exception

    def run_stub(self, state="running"):
        return self.stack.enter_context(mock.patch.object(
            service_module, "run_source", return_value={
                "state": state, "acknowledged": True, "serial_offset": 0,
                "next_offset": 0, "transfer_mode": "test-protocol-boundary",
                "cleanup_mode": "interrupt-only",
            },
        ))

    def record(self, session, execution_id=None):
        path = session.program_path if execution_id is None else session.dir / "programs" / f"{execution_id}.json"
        return json.loads(path.read_text())


class DeviceProgramRuntimeTests(_ProgramFixture):
    def test_invalid_transport_types_fail_before_any_backend_work(self):
        service = object.__new__(DeviceService)
        service._stop = threading.Event()
        for value in ([], {}, True, 123, "invalid"):
            with self.subTest(value=value):
                self.assert_service_error(lambda: service.create_session({"device_id": "atoms3r", "program_transport": value}),
                                          code="unsupported_program_transport", status=400)

    def launch(self, session, *, connection_error=None):
        session.virtual_flash = self.prepared
        order = []
        console = _Console(session.serial0, order)
        qmp = mock.Mock()
        qmp.cmd.side_effect = lambda name, **kwargs: order.append(f"qmp:{name}") or {}
        self.popen.side_effect = lambda *args, **kwargs: order.append("process") or _Process()
        self.stack.enter_context(mock.patch.object(service_module, "wait_qmp", return_value=qmp))
        self.stack.enter_context(mock.patch.object(session, "_verify_units_runtime", side_effect=lambda: order.append("verify-units")))
        factory = self.stack.enter_context(mock.patch("guest_console.GuestConsole", return_value=console))
        if connection_error:
            console.connect = mock.Mock(side_effect=connection_error)
        return order, console, qmp, factory

    def test_default_launch_keeps_file_serial_without_console_or_pause(self):
        session = self.session(transport=None)
        order, _, qmp, factory = self.launch(session)
        session._launch()
        command = self.popen.call_args.args[0]
        self.assertNotIn("-S", command)
        self.assertIn(f"file:{session.serial0}", command)
        self.assertIn(f"file:{session.serial1}", command)
        factory.assert_not_called()
        self.assertNotIn("qmp:cont", order)
        self.assertNotIn("program_transport", session._session_record())
        self.assertIs(session._qmp, qmp)

    def test_optin_launch_connects_unique_reader_before_owned_qmp_cont(self):
        session = self.session()
        order, console, qmp, factory = self.launch(session)
        session._launch()
        command = self.popen.call_args.args[0]
        self.assertEqual(command.count("-S"), 1)
        self.assertIn("chardev:program-console", command)
        backend = command[command.index("-chardev") + 1]
        self.assertIn(f"path={session.console_path}", backend)
        self.assertNotIn("logfile=", backend, "the unique reader owns serial.log")
        factory.assert_called_once_with(session.console_path, session.serial0)
        self.assertLess(order.index("console-connect"), order.index("qmp:cont"))
        self.assertLess(order.index("qmp:cont"), order.index("verify-units"))
        self.assertIs(session._qmp, qmp)
        self.assertIs(session._console, console)
        self.assertEqual(session._session_record()["program_transport"], "uart-repl")

    def test_console_connection_failure_does_not_resume_and_is_cleaned_once(self):
        session = self.session()
        order, console, qmp, _ = self.launch(session, connection_error=GuestConsoleError("console_connect_timeout", "fixture refused"))
        with self.assertRaises(GuestConsoleError):
            session._launch()
        self.assertNotIn("qmp:cont", order)
        session._terminate_process()
        session._terminate_process()
        self.assertEqual(console.close_calls, 1)
        qmp.close.assert_called_once()
        self.assertIsNone(session._console)

    def test_verified_reattach_reconnects_console_without_resuming_or_launching(self):
        session = self.session()
        session.pid = _Process.pid
        session.process_start_token = "fixture-owned-token"
        console = _Console(session.serial0)
        qmp = mock.Mock()
        qmp.cmd.return_value = {"return": {"status": "running"}}
        with mock.patch.object(session, "_process_identity_matches", return_value=True), \
             mock.patch.object(session, "_recover_companions", return_value={}), \
             mock.patch.object(service_module, "wait_qmp", return_value=qmp) as connect_qmp, \
             mock.patch("guest_console.GuestConsole", return_value=console) as connect_console:
            result = session._reattach_runtime()
        self.assertEqual(result["qmp_status"], "running")
        connect_qmp.assert_called_once_with(session.qmp_path, timeout=5)
        connect_console.assert_called_once_with(session.console_path, session.serial0)
        self.assertEqual(console.order, ["console-connect"])
        self.assertEqual(qmp.cmd.call_args_list, [mock.call("query-status")])
        self.assertIs(session._console, console)
        self.assertIs(session._qmp, qmp)
        self.assertTrue(any(event["event"] == "program_console_reattached" and event["output_gap_possible"] for event in session.events))
        self.popen.assert_not_called()
        session.stop()
        self.assertEqual(console.close_calls, 1)
        qmp.close.assert_called_once()

    def test_success_persists_revision_and_execution_without_exposing_source(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub("completed")
        source = "print('中文 checkpoint')\n"
        result = session.run_program({"source": source, "expected_execution_id": None})
        record = self.record(session)
        self.assertEqual(result["program"], record)
        self.assertEqual(record["state"], "completed")
        self.assertEqual(record["execution_mode"], "same-guest-uart-repl")
        self.assertEqual(record["firmware_sha256"], session.firmware_sha)
        self.assertEqual(record["source_bytes"], len(source.encode()))
        self.assertNotIn("source", record)
        self.assertEqual(self.record(session, record["execution_id"]), record)
        revision = self.service.program_revisions.get(record["revision_id"])
        self.assertEqual(revision["source_sha256"], record["source_sha256"])
        self.assertEqual(execute.call_args.args[1], source)
        self.popen.assert_not_called()

    def test_expected_execution_id_fences_replacement(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub()
        first = session.run_program({"source": "print(1)", "expected_execution_id": None})["program"]
        self.assert_service_error(lambda: session.run_program({"source": "print(2)", "expected_execution_id": None}), code="program_generation_conflict", status=409)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.record(session)["execution_id"], first["execution_id"])
        second = session.run_program({"source": "print(2)", "expected_execution_id": first["execution_id"]})["program"]
        self.assertNotEqual(first["execution_id"], second["execution_id"])
        self.assertEqual(execute.call_count, 2)

    def test_one_transfer_owns_the_console_and_busy_rejects_second(self):
        session = self.session()
        self.console(session)
        entered, release = threading.Event(), threading.Event()

        def run(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("fixture transfer not released")
            return {"state": "completed", "acknowledged": True}

        execute = self.stack.enter_context(mock.patch.object(service_module, "run_source", side_effect=run))
        thread, result = self.background(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}))
        try:
            self.assertTrue(entered.wait(1))
            self.assert_service_error(lambda: session.run_program({"source": "print(2)", "expected_execution_id": session._program["execution_id"]}), code="program_busy", status=409)
        finally:
            release.set()
        thread.join(timeout=1)
        self.assertNotIn("error", result)
        self.assertEqual(execute.call_count, 1)
        self.assertFalse(session._program_lock.locked())

    def test_source_and_timeout_validation_happens_before_guest_io(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub()
        bad = [None, [], {}, {"source": "x"}, {"source": 2, "expected_execution_id": None},
               {"source": "\ud800", "expected_execution_id": None},
               {"source": "x", "expected_execution_id": None, "extra": True}]
        bad.extend({"source": "x", "expected_execution_id": None, "timeout_seconds": timeout} for timeout in (True, 0, 31, float("nan"), float("inf")))
        for payload in bad:
            with self.subTest(payload=repr(payload)):
                self.assert_service_error(lambda: session.run_program(payload), code="invalid_program", status=400)
        self.assert_service_error(lambda: session.run_program({"source": "中" * 21846, "expected_execution_id": None}), code="program_too_large", status=413)
        execute.assert_not_called()
        self.assertFalse(session.program_path.exists())

    def test_transport_must_be_opted_in_available_and_running(self):
        for transport, state, connected in ((None, "running", True), ("uart-repl", "booting", True), ("uart-repl", "running", False), ("uart-repl", "stopped", False)):
            with self.subTest(transport=transport, state=state, connected=connected):
                session = self.session(transport=transport, state=state)
                if connected:
                    self.console(session)
                self.assert_service_error(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}), status=409)

    def test_timeout_retains_unknown_until_matching_actual_marker(self):
        session = self.session()
        console = self.console(session)
        self.stack.enter_context(mock.patch.object(service_module, "run_source", side_effect=UIFlowRuntimeError("program_timeout", "fixture no acknowledgement")))
        error = self.assert_service_error(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}), code="program_timeout", status=504)
        program = session.program_status()["program"]
        self.assertEqual(program["state"], "unknown")
        self.assertEqual(error.extra["execution_id"], program["execution_id"])
        console.append(execution_markers("0" * 32)["DONE"])
        self.assertEqual(session.program_status()["program"]["state"], "unknown")
        markers = execution_markers(program["execution_id"])
        console.append(markers["START"])
        self.assertEqual(session.program_status()["program"]["state"], "running")
        console.append(markers["DONE"])
        self.assertEqual(session.program_status()["program"]["state"], "completed")
        self.assertEqual(self.record(session, program["execution_id"])["state"], "completed")

    def test_failed_replacement_does_not_claim_old_guest_was_interrupted(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub()
        first = session.run_program({"source": "while True: pass", "expected_execution_id": None})["program"]
        execute.side_effect = UIFlowRuntimeError("program_timeout", "no raw prompt; interrupt unconfirmed")
        self.assert_service_error(lambda: session.run_program({"source": "print(2)", "expected_execution_id": first["execution_id"]}), status=504)
        self.assertNotEqual(self.record(session, first["execution_id"])["state"], "interrupted", "no actual interrupt acknowledgement exists")

    def test_interruption_record_waits_for_raw_repl_synchronization(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub()
        first = session.run_program({"source": "while True: pass", "expected_execution_id": None})["program"]

        def synchronized_run(*args, on_synchronized, **kwargs):
            before = self.record(session, first["execution_id"])
            self.assertNotEqual(before["state"], "interrupted")
            self.assertFalse(before.get("interruption_confirmed", False))
            on_synchronized()
            confirmed = self.record(session, first["execution_id"])
            self.assertEqual(confirmed["state"], "interrupted")
            self.assertTrue(confirmed["interruption_confirmed"])
            return {"state": "completed", "acknowledged": True}

        execute.side_effect = synchronized_run
        session.run_program({"source": "print(2)", "expected_execution_id": first["execution_id"]})
        self.assertEqual(self.record(session, first["execution_id"])["state"], "interrupted")

    def test_stop_during_revision_creation_fences_late_submission(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub()
        entered, release = threading.Event(), threading.Event()
        create = self.service.program_revisions.create

        def delayed(payload):
            entered.set()
            if not release.wait(2):
                raise AssertionError("revision fixture not released")
            return create(payload)

        self.stack.enter_context(mock.patch.object(self.service.program_revisions, "create", side_effect=delayed))
        thread, result = self.background(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}))
        try:
            self.assertTrue(entered.wait(1))
            session.stop()
        finally:
            release.set()
        thread.join(timeout=1)
        self.assertIsInstance(result.get("error"), ServiceError)
        self.assertEqual(result["error"].status, 409)
        execute.assert_not_called()
        self.assertFalse(any(event["event"] == "program_submitted" for event in session.events))
        self.assertFalse(session.program_path.exists(), "stopped submission must not publish a program")
        self.assertEqual(list((session.dir / "programs").glob("*.json")), [])
        self.assertFalse(session._program_lock.locked())

    def test_stop_cancels_inflight_program_and_retains_record(self):
        session = self.session()
        console = self.console(session)
        entered = threading.Event()

        def run(*args, cancelled, **kwargs):
            entered.set()
            if not session._stop_event.wait(2):
                raise AssertionError("stop did not cancel execution")
            self.assertTrue(cancelled())
            raise UIFlowRuntimeError("program_cancelled", "fixture stopped")

        self.stack.enter_context(mock.patch.object(service_module, "run_source", side_effect=run))
        thread, result = self.background(lambda: session.run_program({"source": "while True: pass", "expected_execution_id": None}))
        self.assertTrue(entered.wait(1))
        execution_id = session._program["execution_id"]
        session.stop()
        thread.join(timeout=1)
        self.assertIsInstance(result.get("error"), ServiceError)
        self.assertEqual(result["error"].status, 409)
        self.assertIn(self.record(session, execution_id)["state"], {"cancelled", "interrupted"})
        self.assertEqual(console.close_calls, 1)
        self.assertIsNone(session._console)
        self.assertTrue(session.program_path.exists())

    def test_stop_cannot_be_overwritten_by_late_success(self):
        session = self.session()
        self.console(session)
        entered, release = threading.Event(), threading.Event()

        def run(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("late result fixture not released")
            return {"state": "running", "acknowledged": True}

        self.stack.enter_context(mock.patch.object(service_module, "run_source", side_effect=run))
        thread, result = self.background(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}))
        try:
            self.assertTrue(entered.wait(1))
            session.stop()
        finally:
            release.set()
        thread.join(timeout=1)
        if "value" in result:
            self.assertIn(result["value"]["program"]["state"], {"cancelled", "interrupted"})
        else:
            self.assertIsInstance(result["error"], ServiceError)
            self.assertEqual(result["error"].status, 409)
        self.assertNotEqual(self.record(session)["state"], "running")

    def test_purge_fences_late_program_success_and_error(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                session = self.session()
                self.console(session)
                entered, release = threading.Event(), threading.Event()

                def execute(*args, **kwargs):
                    entered.set()
                    if not release.wait(2):
                        raise AssertionError("purge fixture not released")
                    if failure:
                        raise UIFlowRuntimeError("program_cancelled", "purged")
                    return {"state": "running", "acknowledged": True}

                with mock.patch.object(service_module, "run_source", side_effect=execute):
                    thread, result = self.background(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}))
                    try:
                        self.assertTrue(entered.wait(1))
                        session.stop(purge=True)
                        self.assertFalse(session.dir.exists())
                    finally:
                        release.set()
                    thread.join(timeout=1)
                self.assertIsInstance(result.get("error"), ServiceError)
                self.assertEqual(result["error"].status, 409)
                self.assertFalse(session.dir.exists(), "late execution resurrected purged history")

    def test_console_failure_persists_unknown_instead_of_running(self):
        session = self.session()
        console = self.console(session)
        self.run_stub()
        session.run_program({"source": "while True: pass", "expected_execution_id": None})
        with mock.patch.object(console, "check_alive", side_effect=GuestConsoleError("console_eof", "fixture EOF")):
            status = session.program_status()["program"]
        self.assertEqual(status["state"], "unknown")
        self.assertEqual(status["error"]["code"], "console_eof")
        self.assertEqual(self.record(session)["state"], "unknown")

    def test_revision_error_is_mapped_and_no_program_is_submitted(self):
        session = self.session()
        self.console(session)
        execute = self.run_stub()
        self.stack.enter_context(mock.patch.object(self.service.program_revisions, "create", side_effect=RevisionError("program_revision_storage_error", "fixture quota", 503)))
        self.assert_service_error(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}), code="program_revision_storage_error", status=503)
        execute.assert_not_called()
        self.assertFalse(session.program_path.exists())
        self.assertFalse(session._program_lock.locked())

    def test_restored_inactive_session_cannot_report_unobserved_running(self):
        session = self.session()
        self.console(session)
        self.run_stub()
        session.run_program({"source": "while True: pass", "expected_execution_id": None})
        restored = self.session(sid=session.id, state="failed", restored=True)
        self.assertIsNone(restored._console)
        observed = restored.program_status()["program"]
        self.assertEqual(observed["state"], "unknown")
        self.assertEqual(self.record(restored)["state"], observed["state"])
        self.assertEqual(self.record(restored, observed["execution_id"])["state"], observed["state"])

    def test_corrupt_program_record_does_not_abort_history_restore(self):
        good = self.session(transport=None, state="stopped")
        bad = self.session(state="stopped")
        bad.program_path.write_text("{broken program record")
        restored = object.__new__(DeviceService)
        restored.__dict__.update(self.service.__dict__)
        restored.specs = {self.spec.id: self.spec}
        restored._sessions = {}
        restored._restore_history()
        self.assertIn(good.id, restored._sessions)
        self.sessions.extend(restored._sessions.values())
        if bad.id in restored._sessions:
            program = restored._sessions[bad.id].program_status()["program"]
            self.assertTrue(program is None or program.get("state") != "running")

    def test_restored_console_gap_does_not_replay_start_as_live_running(self):
        session = self.session()
        self.console(session)
        self.run_stub()
        program = session.run_program({"source": "while True: pass", "expected_execution_id": None})["program"]
        restored = self.session(sid=session.id, state="running", restored=True)
        console = self.console(restored)
        console.append(execution_markers(program["execution_id"])["START"])
        status = restored.program_status()["program"]
        self.assertEqual(status["state"], "unknown")
        self.assertTrue(status["output_gap_possible"])
        console.append(execution_markers(program["execution_id"])["DONE"])
        self.assertEqual(restored.program_status()["program"]["state"], "completed")

    def test_invalid_restored_offset_and_state_fail_closed(self):
        for field, value in (("serial_offset", "bad"), ("serial_offset", -1), ("serial_offset", True), ("state", [])):
            session = self.session()
            session.program_path.write_text(json.dumps({"execution_id": "a" * 32, "revision_id": "b" * 64,
                                                        "serial_offset": 0, "state": "running", field: value}))
            restored = self.session(sid=session.id, state="running", restored=True)
            self.assertIsNone(restored._program)
            self.assertIsNotNone(restored._program_restore_error)


class DeviceRunRevisionTests(_ProgramFixture):
    def setUp(self):
        super().setUp()
        self.service.program_packages = ProgramPackageStore(self.root / "packages")
        self.revision = self.service.program_packages.create({"files": {"main.py": {"encoding": "utf8", "data": "print('reserved run')\n"}}})
        self.deploy = self.stack.enter_context(mock.patch.object(service_module, "deploy_package", side_effect=self.deployed))
        self.execute = self.run_stub("running")

    @staticmethod
    def deployed(*args, on_synchronized, on_progress, **kwargs):
        on_synchronized()
        on_progress({"phase": "activated"})

    def target(self, **kwargs):
        session = self.session(**kwargs)
        self.console(session)
        return session

    def run_reserved(self, session, *, execution_id=None, expected=None, **kwargs):
        return session.run_revision(self.revision["revision_id"], execution_id=execution_id or uuid.uuid4().hex,
                                    expected_execution_id=expected, **kwargs)

    def test_reserved_identity_reads_existing_package_without_creating_revision(self):
        session = self.target()
        execution_id = uuid.uuid4().hex
        synchronized = mock.Mock(side_effect=lambda: self.assertFalse(session._lock._is_owned(), "coordinator callback must run outside session lock"))
        def execute(*args, on_synchronized, **kwargs):
            on_synchronized()
            return {"state": "running", "acknowledged": True}
        self.execute.side_effect = execute
        with mock.patch.object(self.service.program_packages, "create", side_effect=AssertionError("new package")), \
             mock.patch.object(self.service.program_revisions, "create", side_effect=AssertionError("new Python revision")):
            result = self.run_reserved(session, execution_id=execution_id, on_synchronized=synchronized)["program"]
        self.assertEqual(result["execution_id"], execution_id)
        self.assertEqual(result["revision_id"], self.revision["revision_id"])
        self.assertEqual(self.execute.call_args.args[2], execution_id)
        self.assertEqual(self.execute.call_args.kwargs["source_path"], "main.py")
        synchronized.assert_called_once_with()
        self.assertEqual(self.record(session, execution_id), result)
        self.assert_service_error(lambda: self.run_reserved(session, execution_id=execution_id, expected=execution_id),
                                  code="program_execution_conflict", status=409)
        self.assertEqual(self.execute.call_count, 1)
        self.popen.assert_not_called()

    def test_reserved_identity_stale_generation_and_quota_still_fail_before_transport(self):
        session = self.target()
        for value in (None, True, "bad", "A" * 32, "a" * 31):
            self.assert_service_error(lambda: session.run_revision(self.revision["revision_id"], execution_id=value,
                                      expected_execution_id=None), code="invalid_program", status=400)
        self.assert_service_error(lambda: self.run_reserved(session, expected="f" * 32), code="program_generation_conflict", status=409)
        directory = session.dir / "programs"
        directory.mkdir()
        for index in range(256):
            (directory / f"{index:032x}.json").write_text("{}")
        self.assert_service_error(lambda: self.run_reserved(session), code="program_quota_exceeded", status=429)
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_cancel_during_package_read_never_publishes_or_writes_console(self):
        session = self.target()
        entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
        read = self.service.program_packages.read_files
        def delayed(*args):
            entered.set()
            self.assertTrue(release.wait(2))
            return read(*args)
        with mock.patch.object(self.service.program_packages, "read_files", side_effect=delayed):
            thread, result = self.background(lambda: self.run_reserved(session, cancelled=cancel.is_set))
            try:
                self.assertTrue(entered.wait(1))
                cancel.set()
            finally:
                release.set()
            thread.join(timeout=1)
        self.assertEqual(result["error"].code, "program_cancelled")
        self.assertFalse(session._stop_event.is_set())
        self.assertFalse(session.program_path.exists())
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_cancel_at_deployment_writing_and_publish_keeps_unconfirmed_execution(self):
        for phase in ("writing", "published"):
            with self.subTest(phase=phase):
                session = self.target()
                entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
                def deploy(*args, on_synchronized, on_progress, cancelled, **kwargs):
                    on_synchronized()
                    on_progress({"phase": phase})
                    entered.set()
                    self.assertTrue(release.wait(2))
                    self.assertTrue(cancelled())
                    raise UIFlowRuntimeError("program_cancelled", "fixture token cancelled")
                self.deploy.side_effect = deploy
                thread, result = self.background(lambda: self.run_reserved(session, cancelled=cancel.is_set))
                try:
                    self.assertTrue(entered.wait(1))
                    self.assertTrue(session._program_lock.locked())
                    cancel.set()
                finally:
                    release.set()
                thread.join(timeout=1)
                self.assertEqual(result["error"].code, "program_cancelled")
                record = self.record(session)
                self.assertEqual(record["state"], "interrupt-requested")
                self.assertFalse(record["interruption_confirmed"])
                self.assertEqual(record["deployment"]["phase"], phase)
                self.assertFalse(session._stop_event.is_set())
                self.assertFalse(session._program_lock.locked())
        self.execute.assert_not_called()

    def test_cancel_before_and_after_start_fences_late_success_and_error(self):
        for marker in (False, True):
            for late_error in (False, True):
                with self.subTest(marker=marker, late_error=late_error):
                    session = self.target()
                    entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
                    def execute(console, source, execution_id, *, on_synchronized, **kwargs):
                        on_synchronized()
                        if marker:
                            console.append(execution_markers(execution_id)["START"])
                        entered.set()
                        self.assertTrue(release.wait(2))
                        if late_error:
                            raise UIFlowRuntimeError("program_timeout", "late fixture error")
                        return {"state": "completed", "acknowledged": True}
                    self.execute.side_effect = execute
                    thread, result = self.background(lambda: self.run_reserved(session, cancelled=cancel.is_set))
                    try:
                        self.assertTrue(entered.wait(1))
                        cancel.set()
                    finally:
                        release.set()
                    thread.join(timeout=1)
                    self.assertEqual(result["error"].code, "program_cancelled")
                    record = self.record(session)
                    session._console.append(execution_markers(record["execution_id"])["DONE"])
                    self.assertEqual(session.program_status()["program"]["state"], "interrupt-requested")
                    self.assertFalse(record["interruption_confirmed"])
                    self.assertTrue(record["cancel_requested"])
                    self.assertFalse(session._stop_event.is_set())

    def test_independent_interrupt_reacquires_lock_and_requires_prompt_before_confirmation(self):
        session = self.target()
        cancel = threading.Event()
        def cancelled_success(*args, **kwargs):
            cancel.set()
            return {"state": "running", "acknowledged": True}
        self.execute.side_effect = cancelled_success
        self.assert_service_error(lambda: self.run_reserved(session, cancelled=cancel.is_set), code="program_cancelled", status=409)
        execution_id = session._program["execution_id"]
        self.assertFalse(session._program_lock.locked(), "lock release is not interruption confirmation")
        self.assertFalse(self.record(session)["interruption_confirmed"])
        entered, release = threading.Event(), threading.Event()
        def no_prompt(console, *, cancelled, **kwargs):
            self.assertFalse(cancelled(), "recovery must ignore the cancelled Run token")
            entered.set()
            self.assertTrue(release.wait(2))
            raise GuestConsoleError("console_timeout", "fixture no prompt")
        with mock.patch.object(service_module, "synchronize_raw_repl", side_effect=no_prompt):
            thread, result = self.background(lambda: session.interrupt_program(expected_execution_id=execution_id))
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.record(session)["state"], "interrupt-requested")
                self.assertFalse(self.record(session)["interruption_confirmed"])
                self.assert_service_error(lambda: self.run_reserved(session, expected=execution_id), code="program_busy", status=409)
            finally:
                release.set()
            thread.join(timeout=1)
        self.assertEqual(result["error"].status, 504)
        self.assertEqual(self.record(session)["state"], "unknown")
        session._console.append(execution_markers(execution_id)["START"])
        self.assertEqual(session.program_status()["program"]["state"], "unknown")
        ack = {"serial_offset": 1, "prompt_end": 30, "interruption_confirmed": True, "cleanup_mode": "interrupt-only"}
        with mock.patch.object(service_module, "synchronize_raw_repl", return_value=ack) as sync:
            confirmed = session.interrupt_program(expected_execution_id=execution_id)["program"]
            self.assertTrue(sync.call_args.kwargs["cancelled"].__self__ is session._stop_event)
            repeated = session.interrupt_program(expected_execution_id=execution_id)["program"]
            self.assertEqual(sync.call_count, 2, "each recovery call requires a fresh actual prompt")
        self.assertEqual(confirmed["interrupt_ack"], repeated["interrupt_ack"])
        self.assertEqual(confirmed["state"], "interrupted")
        self.assertTrue(confirmed["interruption_confirmed"])
        self.execute.side_effect = None
        self.execute.return_value = {"state": "running", "acknowledged": True}
        next_run = self.run_reserved(session, expected=execution_id)["program"]
        self.assertEqual(next_run["state"], "running")
        self.assertFalse(session._stop_event.is_set())

    def test_interrupt_stale_handle_and_timeout_validation_write_nothing(self):
        session = self.target()
        with mock.patch.object(service_module, "synchronize_raw_repl") as sync:
            self.assert_service_error(lambda: session.interrupt_program(expected_execution_id="stale"), code="program_generation_conflict", status=409)
            for timeout in (True, 0, 121, float("nan")):
                self.assert_service_error(lambda: session.interrupt_program(expected_execution_id="stale", timeout_seconds=timeout), code="invalid_program", status=400)
            sync.assert_not_called()
        self.assertFalse(session.program_path.exists())

    def test_recovery_confirms_prior_replacement_only_after_real_sync_receipt(self):
        session = self.target()
        old = self.run_reserved(session)["program"]
        cancel = threading.Event()
        def interrupted_before_prompt(*args, **kwargs):
            cancel.set()
            raise UIFlowRuntimeError("program_cancelled", "fixture no prompt")
        self.deploy.side_effect = interrupted_before_prompt
        self.assert_service_error(lambda: self.run_reserved(session, expected=old["execution_id"], cancelled=cancel.is_set),
                                  code="program_cancelled")
        replacement_id = session._program["execution_id"]
        self.assertEqual(self.record(session, old["execution_id"])["state"], "unknown")
        def confirm(*args, **kwargs):
            self.assertFalse(self.record(session, old["execution_id"])["interruption_confirmed"])
            return {"interruption_confirmed": True, "prompt_end": 30, "serial_offset": 0}
        with mock.patch.object(service_module, "synchronize_raw_repl", side_effect=confirm):
            session.interrupt_program(expected_execution_id=replacement_id)
        self.assertTrue(self.record(session, old["execution_id"])["interruption_confirmed"])
        self.assertEqual(self.record(session, old["execution_id"])["state"], "interrupted")

    def test_idle_interrupt_confirms_prompt_with_exact_none_owner_and_no_execution(self):
        session = self.target()
        ack = {"serial_offset": 0, "prompt_end": 30, "interruption_confirmed": True, "cleanup_mode": "interrupt-only"}
        with mock.patch.object(service_module, "synchronize_raw_repl", return_value=ack) as sync:
            result = session.interrupt_program(expected_execution_id=None)
            self.assertIsNone(result["program"])
            self.assertEqual(result["interrupt_ack"], ack)
            self.assertFalse(session.program_path.exists())
            self.run_reserved(session)
            self.assert_service_error(lambda: session.interrupt_program(expected_execution_id=None), code="program_generation_conflict", status=409)
            self.assertEqual(sync.call_count, 1)

    def test_purge_fences_independent_interrupt_late_success_and_error(self):
        for late_error in (False, True):
            session = self.target()
            program = self.run_reserved(session)["program"]
            entered, release = threading.Event(), threading.Event()
            def sync(*args, **kwargs):
                entered.set()
                self.assertTrue(release.wait(2))
                if late_error:
                    raise GuestConsoleError("console_closed", "fixture purged")
                return {"interruption_confirmed": True}
            with mock.patch.object(service_module, "synchronize_raw_repl", side_effect=sync):
                thread, result = self.background(lambda: session.interrupt_program(expected_execution_id=program["execution_id"]))
                try:
                    self.assertTrue(entered.wait(1))
                    session.stop(purge=True)
                finally:
                    release.set()
                thread.join(timeout=1)
            self.assertIsInstance(result["error"], ServiceError)
            self.assertFalse(session.dir.exists(), "late prompt must not resurrect purged history")

    def test_managed_handle_is_session_local_persisted_binding_is_not_a_capability(self):
        binding = {"preview_id": "preview-fixture", "owner_epoch": "epoch-fixture", "expected_reference_sha256": "c" * 64}
        session = self.target(management_binding=binding)
        other = self.target(management_binding=binding)
        handle = session._management_handle
        self.assertEqual(session.snapshot()["management_binding"], binding)
        record = json.loads(session.session_record_path.read_text())
        self.assertEqual(record["management_binding"], binding)
        self.assertNotIn("management_handle", record)
        for wrong in (None, {}, binding, object(), other._management_handle):
            self.assert_service_error(lambda: session.require_management_handle(wrong), code="session_managed_by_preview", status=409)
            self.assert_service_error(lambda: self.run_reserved(session, management_handle=wrong), code="session_managed_by_preview", status=409)
        self.assert_service_error(lambda: session.run_program({"source": "print(1)", "expected_execution_id": None}),
                                  code="session_managed_by_preview", status=409)
        program = self.run_reserved(session, management_handle=handle)["program"]
        self.assertEqual(program["state"], "running")
        self.assert_service_error(lambda: session.interrupt_program(expected_execution_id=program["execution_id"]),
                                  code="session_managed_by_preview", status=409)

    def test_history_restore_preserves_binding_and_issues_a_new_local_handle(self):
        binding = {"preview_id": "preview-fixture", "owner_epoch": "epoch-fixture", "expected_reference_sha256": "c" * 64}
        session = self.target(management_binding=binding)
        session.stop()
        restored = object.__new__(DeviceService)
        restored.__dict__.update(self.service.__dict__)
        restored.specs = {self.spec.id: self.spec}
        restored._sessions = {}
        restored._lock = threading.RLock()
        restored._restore_history()
        self.sessions.extend(restored._sessions.values())
        recovered = restored.get_session(session.id)
        self.assertEqual(recovered.management_binding, binding)
        handle = restored.recover_management_handle(session.id, **binding)
        self.assertIsNot(handle, session._management_handle)
        recovered.require_management_handle(handle)
        self.assert_service_error(lambda: recovered.require_management_handle(session._management_handle), code="session_managed_by_preview")
        for field in binding:
            wrong = {**binding, field: "d" * 64 if field == "expected_reference_sha256" else "different"}
            self.assert_service_error(lambda: restored.recover_management_handle(session.id, **wrong), code="session_managed_by_preview", status=409)
        legacy = self.target()
        restored._sessions[legacy.id] = legacy
        self.assert_service_error(lambda: restored.recover_management_handle(legacy.id, **binding), code="session_managed_by_preview", status=409)


class DevicePreviewManagementTests(unittest.TestCase):
    """Real service construction/registration with inert files and no start."""

    def setUp(self):
        import test_device_service
        test_device_service.DeviceServiceUnitTests.setUp(self)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.service.close_all)
        self.binding = {"preview_id": "preview-fixture", "owner_epoch": "epoch-fixture", "expected_reference_sha256": "c" * 64}
        self.firmware = {"firmware_id": "b" * 64, "sha256": "b" * 64, "device_id": "cores3",
                         "source": {"kind": "uiflow", "artifact_id": "a" * 64, "metadata": {"source_sha256": "a" * 64}}}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.compose = self.stack.enter_context(mock.patch.object(self.service, "create_uiflow_firmware", return_value=self.firmware))
        self.stack.enter_context(mock.patch.object(self.service.firmware, "get", return_value=self.firmware))
        self.stack.enter_context(mock.patch.object(self.service.firmware, "path", return_value=self.service.specs["cores3"].reference_path))
        self.start = self.stack.enter_context(mock.patch.object(DeviceSession, "start", autospec=True))
        self.stack.enter_context(mock.patch.object(service_module.subprocess, "Popen", side_effect=AssertionError("real process forbidden")))
        self.request = {"device_id": "cores3", "program_mode": "uiflow-live", "idempotency_key": "managed-allocation-fixture"}

    def test_binding_persisted_before_publication_start_and_replay_keeps_same_capability(self):
        persisted = []
        original = DeviceSession._persist_session
        def persist(session):
            original(session)
            persisted.append((session.id in self.service._sessions, json.loads(session.session_record_path.read_text())))
        with mock.patch.object(DeviceSession, "_persist_session", autospec=True, side_effect=persist):
            snapshot, handle = self.service.create_managed_session(self.request, **self.binding)
            replay, repeated_handle = self.service.create_managed_session(dict(self.request), **self.binding)
        self.assertEqual(snapshot["session_id"], replay["session_id"])
        self.assertIs(handle, repeated_handle)
        self.assertFalse(persisted[0][0], "binding must persist before _sessions publication")
        self.assertEqual(persisted[0][1]["management_binding"], self.binding)
        self.assertEqual(snapshot["management_binding"], self.binding)
        self.assertEqual(self.compose.call_args.args[0]["expected_base_sha256"], self.binding["expected_reference_sha256"])
        self.assertEqual(self.compose.call_count, 1)
        self.assertEqual(self.start.call_count, 1)
        for field in self.binding:
            wrong = {**self.binding, field: "d" * 64 if field == "expected_reference_sha256" else "different"}
            with self.subTest(field=field), self.assertRaises(ServiceError) as caught:
                self.service.create_managed_session(self.request, **wrong)
            self.assertEqual(caught.exception.code, "session_managed_by_preview")
        with self.assertRaises(ServiceError) as caught:
            self.service.create_session(self.request)
        self.assertEqual(caught.exception.code, "session_managed_by_preview")

    def test_managed_creation_cannot_adopt_a_legacy_idempotent_session(self):
        legacy = self.service.create_session(self.request)
        with self.assertRaises(ServiceError) as caught:
            self.service.create_managed_session(self.request, **self.binding)
        self.assertEqual(caught.exception.code, "session_managed_by_preview")
        self.assertNotIn("management_binding", legacy)
        self.assertEqual(len(self.service._sessions), 1)
        self.assertEqual(self.start.call_count, 1)
        self.assertNotIn("expected_base_sha256", self.compose.call_args.args[0])

    def test_managed_source_pin_is_passed_into_composer_and_failure_allocates_nothing(self):
        self.compose.side_effect = ServiceError("uiflow_base_sha256_mismatch", "fixture reference changed", 409)
        with self.assertRaises(ServiceError) as caught:
            self.service.create_managed_session(self.request, **self.binding)
        self.assertEqual(caught.exception.code, "uiflow_base_sha256_mismatch")
        self.assertEqual(self.compose.call_args.args[0]["expected_base_sha256"], "c" * 64)
        self.assertFalse(self.service._sessions)
        self.assertEqual(self.service.worker.snapshot()["active_lease_count"], 0)
        self.start.assert_not_called()

    def test_public_session_body_cannot_supply_any_management_fields(self):
        for field in ("management_binding", "management_handle", "_management_binding", "preview_id", "owner_epoch", "expected_reference_sha256"):
            with self.subTest(field=field), self.assertRaises(ServiceError) as caught:
                self.service.create_session({**self.request, field: "forged"})
            self.assertEqual(caught.exception.code, "invalid_request")
        self.compose.assert_not_called()
        self.start.assert_not_called()

    def test_preview_control_is_one_lazy_instance_and_shutdown_runs_outside_service_lock(self):
        entered, release = threading.Event(), threading.Event()
        control = SimpleNamespace(shutdown=mock.Mock())
        def construct(service):
            self.assertIs(service, self.service)
            self.assertFalse(service._lock._is_owned())
            entered.set()
            self.assertTrue(release.wait(2))
            return control
        factory = mock.Mock(side_effect=construct)
        results = []
        def get():
            results.append(self.service.preview_control())
        with mock.patch.dict(sys.modules, {"preview_service": SimpleNamespace(PreviewService=factory)}):
            threads = [threading.Thread(target=get) for _ in range(4)]
            for thread in threads:
                thread.start()
            try:
                self.assertTrue(entered.wait(1))
            finally:
                release.set()
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
        self.assertEqual(results, [control] * 4)
        factory.assert_called_once_with(self.service)
        control.shutdown.side_effect = lambda: self.assertFalse(self.service._lock._is_owned())
        self.service.close_all()
        control.shutdown.assert_called_once_with()
        with self.assertRaises(ServiceError) as caught:
            self.service.preview_control()
        self.assertEqual(caught.exception.code, "service_stopping")


class DeviceProgramHttpTests(_ProgramFixture):
    def setUp(self):
        super().setUp()
        self.target = self.session()
        self.console(self.target)
        self.execute = self.run_stub("completed")
        service = SimpleNamespace(get_session=mock.Mock(return_value=self.target))

        class ProgramHandler(Handler):
            api_token = "synthetic-program-test-token"
            previous_api_token = None

            def log_message(self, *args):
                pass

        ProgramHandler.service = service
        self.http_service = service
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ProgramHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def request(self, method, *, payload=None, raw=None, authorized=True, body_length=None):
        headers = {}
        if authorized:
            headers["Authorization"] = "Bearer synthetic-program-test-token"
        if payload is not None:
            raw = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if body_length is not None:
            headers["Content-Length"] = str(body_length)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.request(method, f"/api/v1/sessions/{self.target.id}/program", body=raw, headers=headers)
            response = connection.getresponse()
            data = response.read()
            self.assertEqual(len(response.getheader("X-Request-ID", "")), 32)
            return response.status, json.loads(data)
        finally:
            connection.close()

    def test_get_and_post_inherit_bearer_authorization(self):
        for method in ("GET", "POST"):
            status, result = self.request(method, payload={"source": "print(1)", "expected_execution_id": None} if method == "POST" else None, authorized=False)
            self.assertEqual(status, 401)
            self.assertEqual(result["error"]["code"], "unauthorized")
        self.http_service.get_session.assert_not_called()
        self.execute.assert_not_called()

    def test_get_status_and_post_program_route_actual_session_methods(self):
        status, first = self.request("GET")
        self.assertEqual(status, 200)
        self.assertIsNone(first["program"])
        status, submitted = self.request("POST", payload={"source": "print('HTTP fixture')", "expected_execution_id": None})
        self.assertEqual(status, 200)
        self.assertEqual(submitted["program"]["state"], "completed")
        self.assertEqual(self.execute.call_args.args[1], "print('HTTP fixture')")
        status, observed = self.request("GET")
        self.assertEqual(status, 200)
        self.assertEqual(observed, submitted)
        self.assertTrue(all(call.args == (self.target.id,) for call in self.http_service.get_session.call_args_list))

    def test_invalid_json_shape_empty_body_and_program_fields_are_400(self):
        for raw in (b"{", b"[]", b"{}", b"", b'{"source":"print(1)"}'):
            with self.subTest(raw=raw):
                status, payload = self.request("POST", raw=raw)
                self.assertEqual(status, 400)
                self.assertIn(payload["error"]["code"], {"invalid_json", "invalid_program"})
        self.execute.assert_not_called()

    def test_program_json_boundary_is_two_mib(self):
        status, payload = self.request("POST", body_length=2 * 1024 * 1024 + 1)
        self.assertEqual(status, 413)
        self.assertEqual(payload["error"]["code"], "body_too_large")
        self.execute.assert_not_called()

    def test_stopped_program_post_is_classified_conflict_not_internal_error(self):
        self.target.stop()
        status, payload = self.request("POST", payload={"source": "print(1)", "expected_execution_id": None})
        self.assertEqual(status, 409)
        self.assertNotEqual(payload["error"]["code"], "internal_error")
        self.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
