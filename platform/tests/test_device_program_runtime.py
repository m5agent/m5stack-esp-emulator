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

    def session(self, *, transport="uart-repl", state="running", sid=None, restored=False):
        session = DeviceSession(
            self.service, session_id=sid or uuid.uuid4().hex, spec=self.spec,
            firmware_id="a" * 64, firmware_path=self.prepared,
            firmware_sha=hashlib.sha256(self.prepared.read_bytes()).hexdigest(),
            firmware_source="reference", source_artifacts=[], ttl_seconds=60,
            ready_marker=None, ready_timeout=1, ready_conditions=None,
            initial_state=state, program_transport=transport, restored=restored,
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

    def test_json_boundary_is_one_mib(self):
        status, payload = self.request("POST", body_length=1024 * 1024 + 1)
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
