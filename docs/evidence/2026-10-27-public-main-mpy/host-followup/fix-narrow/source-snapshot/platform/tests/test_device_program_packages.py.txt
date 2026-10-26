"""Host contracts for package admission, persistence, fences and HTTP limits.

The actual DeviceSession and HTTP handler run with real temporary stores.
Filesystem deployment and source execution are explicit mocks: these tests
do not execute a guest, verify .mpy compatibility or contact port 8787.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import device_service as service_module
from device_service import ServiceError
from program_packages import ProgramPackageError, ProgramPackageStore
from serve import Handler
from test_device_program_runtime import _ProgramFixture
from uiflow_runtime import UIFlowRuntimeError


def _binary(data):
    return {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")}


class _PackageFixture(_ProgramFixture):
    def setUp(self):
        super().setUp()
        self.service.program_packages = ProgramPackageStore(self.root / "packages")
        self.service.get_device = lambda device_id: {"id": device_id}
        self.deploy = self.stack.enter_context(mock.patch.object(
            service_module, "deploy_package", side_effect=self.deploy_success,
        ))
        self.execute = self.run_stub("completed")

    def payload(self, *, expected=None, **changes):
        result = {
            "files": {
                "main.py": {"encoding": "utf8", "data": "import helper\nprint('实时包')\n"},
                "helper.py": {"encoding": "utf8", "data": "VALUE = '中文'\n"},
                "driver.mpy": _binary(b"M\x06\x00\x1f\x00\xff"),
                "assets/pixels.bin": _binary(b"\x00\xff\x89PNG\r\n"),
                "assets/empty": _binary(b""),
            },
            "expected_execution_id": expected,
        }
        result.update(changes)
        return result

    def deploy_success(self, console, files, revision, *, on_synchronized, on_progress, **kwargs):
        on_synchronized()
        inventory = {path: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for path, data in files.items()}
        for phase in ("preflight", "capabilities", "writing", "verified", "published", "activated"):
            values = {"phase": phase}
            if phase in {"verified", "published", "activated"}:
                values["inventory"] = inventory
            if phase == "activated":
                values.update(package_path="/synthetic/package/" + revision["revision_id"], reused=False)
            on_progress(values)
        return {"phase": "activated", "inventory": inventory}

    def running_session(self):
        session = self.session()
        self.console(session)
        return session


class DeviceProgramPackageTests(_PackageFixture):
    def test_legacy_source_keeps_its_identity_timeout_and_direct_run_path(self):
        session = self.running_session()
        source = "print('legacy source')\n"
        result = session.run_program({"source": source, "expected_execution_id": None})["program"]
        revision = self.service.program_revisions.get(result["revision_id"])
        self.assertEqual(result["source_sha256"], revision["source_sha256"])
        self.assertEqual(self.execute.call_args.args[1], source)
        self.assertEqual(self.execute.call_args.kwargs["timeout"], 10.0)
        self.assertNotIn("source_path", self.execute.call_args.kwargs)
        self.assertNotIn("source_kind", result)
        self.deploy.assert_not_called()
        self.assertEqual(list(self.service.program_packages.root.glob("*.json")), [])
        self.popen.assert_not_called()

    def test_files_deploy_complete_bytes_and_publish_package_identity_before_launch(self):
        session = self.running_session()
        payload = self.payload()
        expected = self.service.program_packages.create({"files": payload["files"]})
        result = session.run_program(payload)["program"]
        self.assertEqual(result["source_kind"], "uiflow2-package")
        self.assertEqual(result["revision_id"], expected["revision_id"])
        self.assertEqual(result["source_sha256"], expected["source_sha256"])
        self.assertEqual(result["file_count"], 5)
        files = self.service.program_packages.read_files(result["revision_id"])
        self.assertEqual(self.deploy.call_args.args[1:], (files, expected))
        self.assertEqual(self.execute.call_args.args[0], self.deploy.call_args.args[0])
        self.assertEqual(self.execute.call_args.args[1], "")
        self.assertEqual(self.execute.call_args.kwargs["source_path"], "main.py")
        self.assertEqual(result["source_bytes"], len(files["main.py"]))
        self.assertEqual(result["total_file_bytes"], sum(map(len, files.values())))
        self.assertEqual(result["deployment"]["phase"], "activated")
        self.assertEqual([event["phase"] for event in result["deployment"]["events"]],
                         ["preflight", "capabilities", "writing", "verified", "published", "activated"])
        self.assertEqual(self.record(session), result)
        self.assertEqual(self.record(session, result["execution_id"]), result)
        self.assertEqual(list(self.service.program_revisions.root.glob("*.json")), [])
        self.popen.assert_not_called()

    def test_default_120_seconds_is_one_budget_shared_with_entrypoint_acknowledgement(self):
        session = self.running_session()
        clock = mock.Mock(wraps=time)
        clock.monotonic.return_value = 100.0
        def deploy(*args, **kwargs):
            receipt = self.deploy_success(*args, **kwargs)
            clock.monotonic.return_value = 102.5
            return receipt
        self.deploy.side_effect = deploy
        with mock.patch.object(service_module, "time", clock):
            session.run_program(self.payload())
        self.assertEqual(self.deploy.call_args.kwargs["timeout"], 120.0)
        self.assertEqual(self.execute.call_args.kwargs["timeout"], 117.5)

    def test_package_timeout_validation_does_not_borrow_the_legacy_30_second_limit(self):
        for timeout in (True, 0, 121, float("nan"), float("inf"), "120"):
            with self.subTest(timeout=timeout):
                session = self.running_session()
                self.assert_service_error(lambda: session.run_program(self.payload(timeout_seconds=timeout)),
                                          code="invalid_program", status=400)
        self.deploy.assert_not_called()
        self.execute.assert_not_called()
        session = self.running_session()
        session.run_program(self.payload(timeout_seconds=60))
        self.assertEqual(self.deploy.call_args.kwargs["timeout"], 60.0)

    def test_deployment_budget_exhaustion_prevents_entrypoint_launch(self):
        session = self.running_session()
        clock = mock.Mock(wraps=time)
        clock.monotonic.return_value = 100.0
        def deploy(*args, **kwargs):
            receipt = self.deploy_success(*args, **kwargs)
            clock.monotonic.return_value = 220.1
            return receipt
        self.deploy.side_effect = deploy
        with mock.patch.object(service_module, "time", clock):
            self.assert_service_error(lambda: session.run_program(self.payload()), code="program_timeout", status=504)
        self.assertEqual(self.record(session)["state"], "unknown")
        self.assertEqual(self.record(session)["deployment"]["phase"], "activated")
        self.execute.assert_not_called()

    def test_stale_execution_fences_both_source_and_file_replacements(self):
        session = self.running_session()
        first = session.run_program(self.payload())["program"]
        for payload in (self.payload(), {"source": "print(2)", "expected_execution_id": None}):
            self.assert_service_error(lambda: session.run_program(payload), code="program_generation_conflict", status=409)
        self.assertEqual(self.deploy.call_count, 1)
        self.assertEqual(self.execute.call_count, 1)
        second = session.run_program(self.payload(expected=first["execution_id"]))["program"]
        self.assertEqual(second["revision_id"], first["revision_id"])
        self.assertNotEqual(second["execution_id"], first["execution_id"])

    def test_one_program_lock_fences_concurrent_packages_and_legacy_source(self):
        session = self.running_session()
        entered, release = threading.Event(), threading.Event()
        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("package deployment fixture was not released")
            return self.deploy_success(*args, **kwargs)
        self.deploy.side_effect = delayed
        thread, result = self.background(lambda: session.run_program(self.payload()))
        try:
            self.assertTrue(entered.wait(1))
            current = session._program["execution_id"]
            for payload in (self.payload(expected=current), {"source": "pass", "expected_execution_id": current}):
                self.assert_service_error(lambda: session.run_program(payload), code="program_busy", status=409)
        finally:
            release.set()
        thread.join(timeout=1)
        self.assertNotIn("error", result)
        self.assertEqual(self.deploy.call_count, 1)
        self.assertEqual(self.execute.call_count, 1)
        self.assertFalse(session._program_lock.locked())

    def test_stop_during_package_storage_prevents_submission_or_any_guest_work(self):
        session = self.running_session()
        entered, release = threading.Event(), threading.Event()
        create = self.service.program_packages.create
        def delayed(payload):
            entered.set()
            if not release.wait(2):
                raise AssertionError("package store fixture was not released")
            return create(payload)
        with mock.patch.object(self.service.program_packages, "create", side_effect=delayed):
            thread, result = self.background(lambda: session.run_program(self.payload()))
            try:
                self.assertTrue(entered.wait(1))
                session.stop()
            finally:
                release.set()
            thread.join(timeout=1)
        self.assertIsInstance(result.get("error"), ServiceError)
        self.assertEqual(result["error"].code, "program_cancelled")
        self.assertEqual(result["error"].status, 409)
        self.assertFalse(session.program_path.exists())
        self.assertFalse(any(event["event"] == "program_submitted" for event in session.events))
        self.deploy.assert_not_called()
        self.execute.assert_not_called()
        self.assertFalse(session._program_lock.locked())

    def test_stop_and_purge_during_stage_fence_late_progress_and_launch(self):
        for purge in (False, True):
            with self.subTest(purge=purge):
                session = self.running_session()
                entered, release = threading.Event(), threading.Event()
                def delayed(*args, cancelled, on_synchronized, on_progress, **kwargs):
                    on_synchronized()
                    on_progress({"phase": "writing", "written_bytes": 2})
                    entered.set()
                    if not release.wait(2):
                        raise AssertionError("stage fixture was not released")
                    self.assertTrue(cancelled())
                    on_progress({"phase": "activated", "inventory": {"synthetic-receipt": True}})
                    raise AssertionError("cancelled progress must not be accepted as active")
                self.deploy.side_effect = delayed
                thread, result = self.background(lambda: session.run_program(self.payload()))
                try:
                    self.assertTrue(entered.wait(1))
                    session.stop(purge=purge)
                finally:
                    release.set()
                thread.join(timeout=1)
                self.assertIsInstance(result.get("error"), ServiceError)
                self.assertEqual(result["error"].status, 409)
                if purge:
                    self.assertFalse(session.dir.exists(), "late package progress resurrected purged history")
                else:
                    self.assertIn(self.record(session)["state"], {"cancelled", "interrupted"})
                    self.assertEqual(self.record(session)["deployment"]["phase"], "activated")
                    self.assertEqual(self.record(session)["deployment"]["inventory"], {"synthetic-receipt": True})
                self.assertFalse(session._program_lock.locked())
        self.execute.assert_not_called()

    def test_confirmed_stage_failures_never_start_the_entrypoint(self):
        for code in ("program_package_integrity", "program_mpy_incompatible", "program_package_short_write"):
            with self.subTest(code=code):
                session = self.running_session()
                def failure(*args, on_synchronized, on_progress, **kwargs):
                    on_synchronized()
                    on_progress({"phase": "writing"})
                    raise UIFlowRuntimeError(code, "synthetic deployment failure")
                self.deploy.side_effect = failure
                error = self.assert_service_error(lambda: session.run_program(self.payload()), code=code, status=409)
                record = self.record(session)
                self.assertEqual(record["state"], "failed")
                self.assertEqual(record["deployment"]["phase"], "writing")
                self.assertEqual(error.extra["execution_id"], record["execution_id"])
        self.execute.assert_not_called()

    def test_unconfirmed_activation_or_transport_timeout_remains_unknown(self):
        for code in ("program_package_activation_unconfirmed", "program_timeout"):
            with self.subTest(code=code):
                session = self.running_session()
                def failure(*args, on_synchronized, on_progress, **kwargs):
                    on_synchronized()
                    on_progress({"phase": "published"})
                    raise UIFlowRuntimeError(code, "synthetic lost guest receipt")
                self.deploy.side_effect = failure
                self.assert_service_error(lambda: session.run_program(self.payload()), code=code, status=504)
                self.assertEqual(self.record(session)["state"], "unknown")
                self.assertEqual(self.record(session)["deployment"]["phase"], "published")
        self.execute.assert_not_called()

    def test_old_program_interruption_requires_guest_synchronization(self):
        for synchronized in (False, True):
            with self.subTest(synchronized=synchronized):
                session = self.running_session()
                self.execute.return_value = {"state": "running", "acknowledged": True}
                old = session.run_program({"source": "while True: pass", "expected_execution_id": None})["program"]
                def failure(*args, on_synchronized, **kwargs):
                    if synchronized:
                        on_synchronized()
                    raise UIFlowRuntimeError("program_timeout", "synthetic missing package acknowledgement")
                self.deploy.side_effect = failure
                self.assert_service_error(lambda: session.run_program(self.payload(expected=old["execution_id"])), status=504)
                previous = self.record(session, old["execution_id"])
                self.assertEqual(previous["state"], "interrupted" if synchronized else "unknown")
                self.assertEqual(previous["interruption_confirmed"], synchronized)

    def test_store_errors_and_invalid_packages_do_not_submit_or_deploy(self):
        session = self.running_session()
        with mock.patch.object(self.service.program_packages, "create", side_effect=ProgramPackageError("program_package_storage_error", "synthetic store failure", 503)):
            self.assert_service_error(lambda: session.run_program(self.payload()), code="program_package_storage_error", status=503)
        for payload in (self.payload(source="pass"), self.payload(entrypoint="main.mpy"), self.payload(files={"boot.py": _binary(b"pass")})):
            self.assert_service_error(lambda: session.run_program(payload), status=400 if "source" in payload else 409)
        self.assertFalse(session.program_path.exists())
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_evidence_retains_exact_resource_mpy_and_source_bytes_plus_identity(self):
        session = self.running_session()
        payload = self.payload()
        record = session.run_program(payload)["program"]
        revision = record["revision_id"]
        expected = self.service.program_packages.read_files(revision)
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"manifest", "serial"}))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(json.loads(archive.read(f"programs/{record['execution_id']}.json")), record)
            self.assertEqual(json.loads(archive.read(f"programs/{revision}/source.json")), self.service.program_packages.source(revision))
            self.assertEqual(json.loads(archive.read(f"programs/{revision}/revision.json")), self.service.program_packages.get(revision))
            for path, data in expected.items():
                name = f"programs/{revision}/files/{path}"
                self.assertEqual(archive.read(name), data)
                self.assertEqual(manifest["files"][name]["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(manifest["files"][name]["size"], len(data))

    def test_restore_during_any_deployment_phase_is_unknown_and_preserves_receipts(self):
        for phase in ("preflight", "writing", "verified", "published", "activated"):
            with self.subTest(phase=phase):
                session = self.running_session()
                def failure(*args, on_progress, **kwargs):
                    on_progress({"phase": phase, "synthetic_receipt": "retained"})
                    raise UIFlowRuntimeError("program_timeout", "synthetic transport loss")
                self.deploy.side_effect = failure
                self.assert_service_error(lambda: session.run_program(self.payload()), status=504)
                record = self.record(session)
                # Model a host crash while this persisted phase was still
                # submitting; there is no guest acknowledgement after restart.
                session._program["state"] = "submitting"
                session._persist_program()
                restored = self.session(sid=session.id, state="failed", restored=True)
                observed = restored.program_status()["program"]
                self.assertEqual(observed["execution_id"], record["execution_id"])
                self.assertEqual(observed["source_kind"], "uiflow2-package")
                self.assertEqual(observed["state"], "unknown")
                self.assertTrue(observed["output_gap_possible"])
                self.assertEqual(observed["deployment"], record["deployment"])


class DeviceProgramPackageHttpTests(_PackageFixture):
    def setUp(self):
        super().setUp()
        self.target = self.running_session()
        service = SimpleNamespace(get_session=mock.Mock(return_value=self.target), create_session=mock.Mock())
        class PackageHandler(Handler):
            api_token = "synthetic-package-test-token"
            previous_api_token = None
            def log_message(self, *args):
                pass
        PackageHandler.service = service
        self.http_service = service
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PackageHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.assertFalse(self.server_thread.is_alive())

    def request(self, *, action="program", payload=None, raw=None, body_length=None, authorized=True, path=None):
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer synthetic-package-test-token"
        if payload is not None:
            raw = json.dumps(payload).encode()
        if body_length is not None:
            headers["Content-Length"] = str(body_length)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("POST", path or f"/api/v1/sessions/{self.target.id}/{action}", body=raw, headers=headers)
            response = connection.getresponse()
            data = response.read()
            self.assertEqual(len(response.getheader("X-Request-ID", "")), 32)
            return response.status, json.loads(data)
        finally:
            connection.close()

    def test_full_one_mib_decoded_package_can_cross_the_old_http_envelope_limit(self):
        payload = self.payload(files={"main.py": _binary(b""), **{f"resource-{index}": _binary(b"\xff" * (256 * 1024)) for index in range(4)}})
        self.assertGreater(len(json.dumps(payload).encode()), 1024 * 1024)
        status, result = self.request(payload=payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["program"]["total_file_bytes"], 1024 * 1024)
        self.assertEqual(sum(map(len, self.deploy.call_args.args[1].values())), 1024 * 1024)
        self.execute.assert_called_once()

    def test_program_http_boundary_accepts_two_mib_and_rejects_one_byte_more(self):
        encoded = json.dumps(self.payload()).encode()
        raw = encoded + b" " * (2 * 1024 * 1024 - len(encoded))
        status, _ = self.request(raw=raw)
        self.assertEqual(status, 200)
        status, result = self.request(body_length=2 * 1024 * 1024 + 1)
        self.assertEqual(status, 413)
        self.assertEqual(result["error"]["code"], "body_too_large")
        self.assertEqual(self.execute.call_count, 1)

    def test_nonprogram_session_and_creation_routes_keep_one_mib_limit(self):
        for action in ("input", "unit-input", "qom", "network-fault", "qom-snapshot"):
            with self.subTest(action=action):
                status, result = self.request(action=action, body_length=1024 * 1024 + 1)
                self.assertEqual(status, 413)
                self.assertEqual(result["error"]["code"], "body_too_large")
        status, result = self.request(path="/api/v1/sessions", body_length=1024 * 1024 + 1)
        self.assertEqual(status, 413)
        self.assertEqual(result["error"]["code"], "body_too_large")
        self.http_service.create_session.assert_not_called()
        self.deploy.assert_not_called()
        self.execute.assert_not_called()

    def test_file_submission_requires_bearer_before_resolving_any_session(self):
        status, result = self.request(payload=self.payload(), authorized=False)
        self.assertEqual(status, 401)
        self.assertEqual(result["error"]["code"], "unauthorized")
        self.http_service.get_session.assert_not_called()
        self.deploy.assert_not_called()
        self.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
