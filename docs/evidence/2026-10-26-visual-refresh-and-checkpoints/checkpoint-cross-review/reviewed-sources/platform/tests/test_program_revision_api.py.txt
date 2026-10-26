"""Real HTTP/store contracts for immutable checkpoints and revision execution.

Only the host handler, persistence and admission run. Guest deployment/execution
and process creation are mocked; no guest, firmware or port 8787 is used.
"""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
import json
import threading
from unittest import mock

from device_service import DeviceService
from program_packages import ProgramPackageStore
from serve import Handler
from test_device_program_packages import _PackageFixture, _binary
from test_mpy_bytecode import HELPER, NATIVE
from uiflow_runtime import UIFlowRuntimeError


class ProgramRevisionApiTests(_PackageFixture):
    def setUp(self):
        super().setUp()
        self.target = self.running_session()
        self.api = object.__new__(DeviceService)
        self.api.program_packages = self.service.program_packages
        self.api.get_session = mock.Mock(return_value=self.target)

        class RevisionHandler(Handler):
            api_token = "synthetic-revision-test-token"
            previous_api_token = None

            def log_message(self, *args):
                pass

        RevisionHandler.service = self.api
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RevisionHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.assertFalse(self.server_thread.is_alive())

    def checkpoint(self, **changes):
        payload = self.payload()
        payload.pop("expected_execution_id")
        payload.update(source_kind="uiflow2-package", entrypoint="main.py")
        payload["files"]["driver.mpy"] = _binary(HELPER)
        payload.update(changes)
        return payload

    def request(self, method, path, *, payload=None, raw=None, body_length=None, authorized=True):
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer synthetic-revision-test-token"
        if payload is not None:
            raw = json.dumps(payload).encode()
        if body_length is not None:
            headers["Content-Length"] = str(body_length)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=raw, headers=headers)
            response = connection.getresponse()
            body = response.read()
            self.assertEqual(len(response.getheader("X-Request-ID", "")), 32)
            return response.status, json.loads(body), dict(response.getheaders())
        finally:
            connection.close()

    def create(self, payload=None):
        status, body, headers = self.request("POST", "/api/v1/program-revisions", payload=self.checkpoint() if payload is None else payload)
        self.assertEqual(status, 201, body)
        self.assertEqual(headers["Location"], "/api/v1/program-revisions/" + body["revision"]["revision_id"])
        return body["revision"]

    def run_request(self, payload):
        return self.request("POST", f"/api/v1/sessions/{self.target.id}/program", payload=payload)

    def reference(self, revision, expected=None, **changes):
        return {"revision_id": revision["revision_id"], "expected_execution_id": expected, **changes}

    def assert_no_execution(self):
        self.assertFalse(self.target.program_path.exists())
        self.assertEqual(list((self.target.dir / "programs").glob("*.json")), [])
        self.assertFalse(any(e["event"] == "program_submitted" for e in self.target.events))
        self.deploy.assert_not_called()
        self.execute.assert_not_called()
        self.popen.assert_not_called()
        self.assertFalse(self.target._program_lock.locked())

    def test_public_save_get_and_duplicate_are_immutable_without_guest_work(self):
        first = self.create()
        record = self.api.program_packages.root / (first["revision_id"] + ".json")
        original = record.read_bytes()
        second_payload = self.checkpoint()
        second_payload["files"]["helper.py"] = _binary("VALUE = '中文'\n".encode())
        second_payload["files"] = dict(reversed(list(second_payload["files"].items())))
        self.assertEqual(self.create(second_payload), first)
        self.assertEqual(record.read_bytes(), original)
        status, body, _ = self.request("GET", "/api/v1/program-revisions/" + first["revision_id"])
        self.assertEqual(status, 200)
        self.assertEqual(body["revision"], first)
        self.assertEqual(body["limits"], {"max_revisions": 256, "max_files": 64, "max_file_bytes": 262144,
                                          "max_total_file_bytes": 1048576, "max_http_body_bytes": 2097152, "gc_enabled": False})
        self.assertEqual(first["source_kind"], "uiflow2-package")
        self.assertEqual(first["entrypoint"], "main.py")
        self.assertTrue(all(set(row) == {"path", "size", "sha256", "kind"} for row in first["files"]))
        self.assertEqual(len(list(self.api.program_packages.root.glob("*.json"))), 1)
        self.api.get_session.assert_not_called()
        self.assert_no_execution()

    def test_duplicate_is_reusable_at_quota_but_new_checkpoint_is_not(self):
        self.api.program_packages = self.service.program_packages = ProgramPackageStore(self.root / "one-package", max_count=1)
        first = self.create()
        self.assertEqual(self.create(), first)
        payload = self.checkpoint()
        payload["files"]["main.py"]["data"] += "print('different')\n"
        status, body, _ = self.request("POST", "/api/v1/program-revisions", payload=payload)
        self.assertEqual((status, body["error"]["code"]), (429, "program_package_quota_exceeded"))
        status, body, _ = self.request("GET", "/api/v1/program-revisions/" + first["revision_id"])
        self.assertEqual((status, body["limits"]["max_revisions"]), (200, 1))
        status, body, _ = self.run_request(self.reference(first))
        self.assertEqual(status, 200)
        self.assertEqual(body["program"]["revision_id"], first["revision_id"])

    def test_reference_executes_complete_frozen_bytes_without_any_store_create(self):
        payload = self.checkpoint()
        revision = self.create(payload)
        payload["files"]["main.py"]["data"] = "raise AssertionError('mutable caller')"
        frozen = self.api.program_packages.read_files(revision["revision_id"])
        with mock.patch.object(self.api.program_packages, "create", side_effect=AssertionError("reference must not create")), \
             mock.patch.object(self.service.program_revisions, "create", side_effect=AssertionError("reference must not create source")):
            status, body, _ = self.run_request(self.reference(revision))
        self.assertEqual(status, 200, body)
        program = body["program"]
        self.assertEqual((program["revision_id"], program["source_sha256"]), (revision["revision_id"], revision["source_sha256"]))
        self.assertEqual((program["source_kind"], program["file_count"]), ("uiflow2-package", len(frozen)))
        self.assertEqual(program["source_bytes"], len(frozen["main.py"]))
        self.assertEqual(self.deploy.call_args.args[1:], (frozen, revision))
        self.assertEqual(self.execute.call_args.args[1], "")
        self.assertEqual(self.execute.call_args.kwargs["source_path"], "main.py")
        self.assertEqual(self.deploy.call_args.kwargs["timeout"], 120.0)
        self.assertEqual(program["execution_mode"], "same-guest-uart-repl")
        self.assertEqual(self.record(self.target, program["execution_id"]), program)
        self.popen.assert_not_called()

    def test_stale_reference_does_not_read_store_or_interrupt_current_program(self):
        self.execute.return_value = {"state": "running", "acknowledged": True}
        status, body, _ = self.run_request({"source": "while True: pass", "expected_execution_id": None})
        self.assertEqual(status, 200)
        original = self.target.program_path.read_bytes()
        with mock.patch.object(self.api.program_packages, "get", side_effect=AssertionError("stale must not resolve")):
            status, body, _ = self.run_request({"revision_id": "f" * 64, "expected_execution_id": None})
        self.assertEqual((status, body["error"]["code"]), (409, "program_generation_conflict"))
        self.assertEqual(self.target.program_path.read_bytes(), original)
        self.deploy.assert_not_called()
        self.assertEqual(self.execute.call_count, 1)

    def test_reference_fields_are_strict_and_invalid_requests_do_not_allocate(self):
        revision = self.create()
        base = self.reference(revision)
        invalid = [{}, {"revision_id": revision["revision_id"]},
                   {**base, "source": "pass"}, {**base, "files": {}}, {**base, "source_kind": "uiflow2-package"},
                   {**base, "entrypoint": "main.py"}, {**base, "unknown": 1},
                   {**base, "source": "pass", "files": {}},
                   {**base, "timeout_seconds": True}, {**base, "timeout_seconds": 0}, {**base, "timeout_seconds": 121}]
        invalid += [{**base, "revision_id": value} for value in (None, 1, [], {}, "", "A" * 64, "a" * 63, "../x", "a" * 64 + "\n")]
        for payload in invalid:
            with self.subTest(payload=payload):
                status, body, _ = self.run_request(payload)
                self.assertEqual((status, body["error"]["code"]), (400, "invalid_program"))
        self.assert_no_execution()

    def test_unknown_corrupt_and_python_only_revisions_do_not_submit(self):
        legacy = self.service.program_revisions.create({"files": {"main.py": "import helper\n", "helper.py": "X=1\n"}})
        for revision_id in ("f" * 64, legacy["revision_id"]):
            for path in ("/api/v1/program-revisions/" + revision_id,):
                status, body, _ = self.request("GET", path)
                self.assertEqual((status, body["error"]["code"]), (404, "unknown_program_package"))
            status, body, _ = self.run_request({"revision_id": revision_id, "expected_execution_id": None})
            self.assertEqual((status, body["error"]["code"]), (404, "unknown_program_package"))
        revision = self.create()
        path = self.api.program_packages.root / (revision["revision_id"] + ".json")
        path.write_text("{}")
        for method, route, payload in (("GET", "/api/v1/program-revisions/" + revision["revision_id"], None),
                                       ("POST", f"/api/v1/sessions/{self.target.id}/program", self.reference(revision))):
            status, body, _ = self.request(method, route, payload=payload)
            self.assertEqual((status, body["error"]["code"]), (500, "program_package_corrupt"))
        self.assert_no_execution()

    def test_public_post_requires_explicit_complete_package_fields(self):
        good = self.checkpoint()
        invalid = [({k: v for k, v in good.items() if k != missing}, 400, "invalid_program_revision") for missing in good]
        invalid += [({**good, "owner": "another"}, 400, "invalid_program_revision"),
                    ({**good, "source": "pass"}, 400, "invalid_program_revision"),
                    ({**good, "source_kind": "uiflow2-python"}, 409, "unsupported_program_source_kind"),
                    ({**good, "entrypoint": "main.mpy"}, 409, "unsupported_program_entrypoint"),
                    ({**good, "files": {"main.py": _binary(b"\xff")}}, 400, "invalid_program_package_source"),
                    ({**good, "files": {"main.py": {"encoding": "utf8", "data": "pass"}, "boot.py": _binary(b"pass")}}, 409, "reserved_program_package_path")]
        for payload, expected_status, code in invalid:
            with self.subTest(code=code, payload=payload):
                status, body, _ = self.request("POST", "/api/v1/program-revisions", payload=payload)
                self.assertEqual((status, body["error"]["code"]), (expected_status, code))
        self.assertEqual(list(self.api.program_packages.root.glob("*.json")), [])
        self.assert_no_execution()

    def test_public_complete_decoded_byte_limit_and_binary_resources(self):
        files = {"main.py": _binary(b""), **{
            f"resource-{i}.bin": _binary(b"\xff" * (256 * 1024)) for i in range(4)
        }}
        payload = self.checkpoint(files=files)
        self.assertGreater(len(json.dumps(payload).encode()), 1024 * 1024)
        revision = self.create(payload)
        self.assertEqual(revision["total_file_bytes"], 1048576)
        payload["files"]["one-byte"] = _binary(b"x")
        status, body, _ = self.request("POST", "/api/v1/program-revisions", payload=payload)
        self.assertEqual((status, body["error"]["code"]), (413, "program_package_too_large"))
        self.assertEqual(len(list(self.api.program_packages.root.glob("*.json"))), 1)
        self.assert_no_execution()

    def test_native_and_invalid_mpy_preflight_never_change_old_execution(self):
        self.execute.return_value = {"state": "running", "acknowledged": True}
        status, body, _ = self.run_request({"source": "while True: pass", "expected_execution_id": None})
        original = self.target.program_path.read_bytes()
        old_id = body["program"]["execution_id"]
        for data, code in ((NATIVE, "program_mpy_native_unsupported"), (HELPER[:-1], "program_mpy_invalid"),
                           (HELPER[:4] + b"\xff", "program_mpy_invalid")):
            payload = self.checkpoint()
            payload["files"]["driver.mpy"] = _binary(data)
            status, body, _ = self.request("POST", "/api/v1/program-revisions", payload=payload)
            self.assertEqual((status, body["error"]["code"]), (409, code))
            # Legacy file submissions can already have stored a package before
            # guest preflight; reference admission must independently recheck it.
            revision = self.api.program_packages.create(payload)
            status, body, _ = self.run_request(self.reference(revision, old_id))
            self.assertEqual((status, body["error"]["code"]), (409, code))
            self.assertEqual(self.target.program_path.read_bytes(), original)
        self.assertEqual(len(list((self.target.dir / "programs").glob("*.json"))), 1)
        self.deploy.assert_not_called()
        self.assertEqual(self.execute.call_count, 1)
        self.assertFalse(self.target._program_lock.locked())

    def test_old_source_keeps_exact_python_identity_and_direct_execution(self):
        source = "print('旧的 source 兼容')\n"
        expected = self.service.program_revisions.create({"files": {"main.py": source}})
        status, body, _ = self.run_request({"source": source, "expected_execution_id": None})
        self.assertEqual(status, 200)
        program = body["program"]
        self.assertEqual((program["revision_id"], program["source_sha256"]), (expected["revision_id"], expected["source_sha256"]))
        self.assertNotIn("source_kind", program)
        self.assertEqual(self.execute.call_args.args[1], source)
        self.assertEqual(self.execute.call_args.kwargs["timeout"], 10.0)
        self.assertNotIn("source_path", self.execute.call_args.kwargs)
        self.deploy.assert_not_called()

    def test_stop_during_reference_read_fences_late_execution(self):
        revision = self.create()
        entered, release = threading.Event(), threading.Event()
        read_files = self.api.program_packages.read_files

        def delayed(revision_id):
            entered.set()
            if not release.wait(2):
                raise AssertionError("reference reader was not released")
            return read_files(revision_id)

        with mock.patch.object(self.api.program_packages, "read_files", side_effect=delayed):
            thread, result = self.background(lambda: self.run_request(self.reference(revision)))
            try:
                self.assertTrue(entered.wait(1))
                self.target.stop()
            finally:
                release.set()
            thread.join(timeout=2)
        self.assertNotIn("error", result)
        status, body, _ = result["value"]
        self.assertEqual((status, body["error"]["code"]), (409, "program_cancelled"))
        self.assert_no_execution()

    def test_reference_owns_same_console_lock_against_source_and_other_references(self):
        revision = self.create()
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise AssertionError("reference deployment was not released")
            return self.deploy_success(*args, **kwargs)

        self.deploy.side_effect = delayed
        thread, result = self.background(lambda: self.run_request(self.reference(revision)))
        try:
            self.assertTrue(entered.wait(1))
            current = self.target._program["execution_id"]
            for payload in (self.reference(revision, current), {"source": "pass", "expected_execution_id": current}):
                status, body, _ = self.run_request(payload)
                self.assertEqual((status, body["error"]["code"]), (409, "program_busy"))
        finally:
            release.set()
        thread.join(timeout=2)
        self.assertNotIn("error", result)
        self.assertEqual(result["value"][0], 200)
        self.assertEqual(self.deploy.call_count, 1)
        self.assertEqual(self.execute.call_count, 1)
        self.assertFalse(self.target._program_lock.locked())

    def test_stop_during_reference_deployment_retains_cancellation_and_never_starts(self):
        revision = self.create()
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, cancelled, on_synchronized, on_progress, **kwargs):
            on_synchronized()
            on_progress({"phase": "writing"})
            entered.set()
            if not release.wait(2):
                raise AssertionError("reference cancellation was not released")
            self.assertTrue(cancelled())
            raise UIFlowRuntimeError("program_cancelled", "synthetic session stopping")

        self.deploy.side_effect = delayed
        thread, result = self.background(lambda: self.run_request(self.reference(revision)))
        try:
            self.assertTrue(entered.wait(1))
            self.target.stop()
        finally:
            release.set()
        thread.join(timeout=2)
        self.assertNotIn("error", result)
        status, body, _ = result["value"]
        self.assertEqual((status, body["error"]["code"]), (409, "program_cancelled"))
        record = self.record(self.target)
        self.assertEqual(record["state"], "cancelled")
        self.assertEqual(record["revision_id"], revision["revision_id"])
        self.execute.assert_not_called()
        self.assertFalse(self.target._program_lock.locked())

    def test_reference_transport_errors_preserve_existing_unknown_and_interrupt_semantics(self):
        revision = self.create()
        for synchronized in (False, True):
            with self.subTest(synchronized=synchronized):
                self.target = self.running_session()
                self.api.get_session.return_value = self.target
                self.execute.return_value = {"state": "running", "acknowledged": True}
                status, body, _ = self.run_request({"source": "while True: pass", "expected_execution_id": None})
                old_id = body["program"]["execution_id"]

                def failure(*args, on_synchronized, **kwargs):
                    if synchronized:
                        on_synchronized()
                    raise UIFlowRuntimeError("program_timeout", "synthetic missing receipt")

                self.deploy.side_effect = failure
                status, body, _ = self.run_request(self.reference(revision, old_id))
                self.assertEqual((status, body["error"]["code"]), (504, "program_timeout"))
                record = self.record(self.target)
                self.assertEqual(record["state"], "unknown")
                self.assertEqual(record["execution_id"], body["error"]["execution_id"])
                old = self.record(self.target, old_id)
                self.assertEqual(old["state"], "interrupted" if synchronized else "unknown")
                self.assertEqual(old["interruption_confirmed"], synchronized)
                self.assertFalse(self.target._program_lock.locked())

    def test_http_auth_body_size_and_duplicate_key_boundaries(self):
        for method, path in (("POST", "/api/v1/program-revisions"), ("GET", "/api/v1/program-revisions/" + "a" * 64)):
            status, body, _ = self.request(method, path, payload=self.checkpoint() if method == "POST" else None, authorized=False)
            self.assertEqual((status, body["error"]["code"]), (401, "unauthorized"))
        self.assertEqual(list(self.api.program_packages.root.glob("*.json")), [])
        raw = json.dumps(self.checkpoint()).encode()
        status, body, _ = self.request("POST", "/api/v1/program-revisions", raw=raw + b" " * (2097152 - len(raw)))
        self.assertEqual(status, 201)
        status, body, _ = self.request("POST", "/api/v1/program-revisions", body_length=2097153)
        self.assertEqual((status, body["error"]["code"]), (413, "body_too_large"))
        duplicate = b'{"source_kind":"uiflow2-package","source_kind":"uiflow2-package","entrypoint":"main.py","files":{"main.py":{"encoding":"utf8","data":"pass"}}}'
        status, body, _ = self.request("POST", "/api/v1/program-revisions", raw=duplicate)
        self.assertEqual((status, body["error"]["code"]), (400, "invalid_json"))
        self.assert_no_execution()


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
