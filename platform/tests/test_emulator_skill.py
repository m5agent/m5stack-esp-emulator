"""HOST_ONLY_NOT_GUEST: portable CLI against ephemeral recording HTTP servers.

No Device Service, firmware execution, model call, physical device or port 8787
is used. The fixtures test transport/ownership/evidence contracts only.
"""
from contextlib import contextmanager, redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit


SCRIPT = Path(__file__).resolve().parents[2] / "skills/m5stack-esp-emulator/scripts/emulator.py"
SPEC = importlib.util.spec_from_file_location("portable_emulator_skill", SCRIPT)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
TOKEN = "fake-portable-emulator-token"
SID, PID, EPOCH = "fake-session", "fake-preview", "fake-epoch"
FIRMWARE, REVISION = "a" * 64, "b" * 64
PNG = b"\x89PNG\r\n\x1a\nFAKE_FRAME_ONLY"


def session(**changes):
    return {"session_id": SID, "device_id": "fake-board", "runtime": "qemu", "firmware_sha256": FIRMWARE,
            "created_at": "2030-01-01T00:00:00Z", "state": "running", "worker": {"lease_active": False}, **changes}


def preview(**changes):
    return {"preview_id": PID, "owner_epoch": EPOCH, "session_id": SID, "generation": 2, "state": "ready", **changes}


@contextmanager
def server(callback):
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw) if raw and "application/json" in self.headers.get("Content-Type", "") else raw
            request = {"method": self.command, "path": self.path, "headers": dict(self.headers.items()), "body": body}
            self.server.requests.append(request)
            code, value, headers = callback(request, self.server)
            blob = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Content-Type", "application/octet-stream" if isinstance(value, bytes) else "application/json")
            for name, item in headers.items():
                self.send_header(name, item)
            self.end_headers()
            self.wfile.write(blob)

        do_GET = do_POST = do_DELETE = handle_request

        def log_message(self, *_args):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    instance.requests = []
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance, f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(5)


class EmulatorSkillTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state.json"
        self.environment = mock.patch.dict(os.environ, {"M5_EMULATOR_TOKEN": TOKEN, "no_proxy": "127.0.0.1", "NO_PROXY": "127.0.0.1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in ("M5_EMULATOR_BASE_URL", "M5_EMULATOR_TOKEN_FILE", "M5_EMULATOR_PUBLIC_URL"):
            os.environ.pop(name, None)

    def configured(self, base, *, owned=False, managed=False):
        os.environ["M5_EMULATOR_BASE_URL"] = base
        if owned:
            value = {"schema_version": 1, "base_url": base, "session": {key: item for key, item in session().items() if key != "state"}}
            if managed:
                value["preview"] = {"preview_id": PID, "owner_epoch": EPOCH}
            self.state.write_text(json.dumps(value))

    def file(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def invoke(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            status = CLI.main(["--state", str(self.state), *map(str, args)])
        self.assertNotIn(TOKEN, output.getvalue())
        return status, json.loads(output.getvalue())

    def test_base_url_is_required_without_inventing_a_host_or_port(self):
        status, result = self.invoke("discover")
        self.assertEqual(status, 2)
        self.assertEqual(result["error"]["code"], "base_url_required")
        self.assertFalse(self.state.exists())

    def test_transport_origin_boundaries(self):
        for url in ("http://127.0.0.1:19001", "http://[::1]:19001", "http://localhost:19001", "http://10.0.0.1:19001",
                    "http://172.31.1.1:19001", "http://192.168.1.1:19001", "https://service.example.test"):
            with self.subTest(allowed=url):
                self.assertEqual(CLI.origin(url)[0], url)
        for url in ("http://service.example.test", "http://8.8.8.8", "http://169.254.1.1", "http://100.64.0.1", "http://[fd00::1]",
                    "https://user:password@example.test", "https://example.test/path", "https://example.test/?token=bad", "file:///tmp/api"):
            with self.subTest(rejected=url), self.assertRaises(CLI.Error):
                CLI.origin(url)

    def test_routes_reject_destination_and_query_credentials(self):
        for path in ("https://outside.example/api/v1/health", "//outside.example/api/v1/health", "/api/v1/../worker",
                     "/api/v1/%2e%2e/worker", "/api/v1/sessions//fake/input", "/api/v1/health?token=secret", "/api/v1/health#fragment"):
            with self.subTest(path=path), self.assertRaises(CLI.Error):
                CLI.route(path)
        self.assertEqual(CLI.route("/api/v1/sessions/fake/qom?path=%2Fmachine%2Funits&property=source-count"), ["sessions", "fake", "qom"])
        self.assertEqual(CLI.route("/api/v1/sessions/fake/network?fixture=http://fixture.example.test/path"), ["sessions", "fake", "network"])
        with self.assertRaises(CLI.Error):
            CLI.route("/api/v1/health?%74oken=hidden")

    def test_discover_preserves_unit_admission_without_guessing_attachments(self):
        def callback(request, _server):
            return 200, {"units": [{"id": "fake-unit", "host_admission": {"admitted": False}}]} if "/units" in request["path"] else {"devices": []}, {}
        with server(callback) as (recording, base):
            self.configured(base)
            status, result = self.invoke("discover", "--device", "fake-board")
            self.assertEqual(status, 0)
            self.assertFalse(result["units"]["units"][0]["host_admission"]["admitted"])
            self.assertEqual(recording.requests[1]["path"], "/api/v1/units?device_id=fake-board")

    def test_raw_artifact_upload_verifies_server_hash_and_keeps_exact_bytes(self):
        blob = b"\xe9\x00\xffFAKE_FIRMWARE"
        path = self.root / "sample.bin"
        path.write_bytes(blob)
        def callback(request, _server):
            self.assertEqual(request["path"], "/api/v1/artifacts")
            self.assertEqual(request["body"], blob)
            self.assertEqual(request["headers"]["X-Artifact-Name"], "sample.bin")
            return 201, {"artifact_id": hashlib.sha256(blob).hexdigest(), "sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)}, {}
        with server(callback) as (_, base):
            self.configured(base)
            self.assertEqual(self.invoke("upload", path)[0], 0)

    def test_artifact_receipt_mismatch_is_not_accepted(self):
        path = self.root / "sample.bin"
        path.write_bytes(b"FAKE")
        with server(lambda request, recording: (201, {"artifact_id": FIRMWARE, "sha256": FIRMWARE, "size": 4}, {})) as (_, base):
            self.configured(base)
            self.assertEqual(self.invoke("upload", path)[1]["error"]["code"], "artifact_hash_mismatch")

    def test_upload_ambiguous_error_is_not_automatically_retried(self):
        path = self.root / "sample.bin"
        path.write_bytes(b"FAKE")
        with server(lambda request, recording: (503, {"error": {"code": "unavailable"}}, {})) as (recording, base):
            self.configured(base)
            status, result = self.invoke("upload", path)
            self.assertEqual(status, 2)
            self.assertTrue(result["error"]["outcome_unknown"])
            self.assertEqual(len(recording.requests), 1)

    def test_compose_keeps_explicit_merged_and_segmented_recipes(self):
        for recipe in ({"device_id": "fake-board", "kind": "merged", "artifact_id": FIRMWARE},
                       {"device_id": "fake-board", "kind": "segmented", "segments": [{"offset": "0x1000", "artifact_id": FIRMWARE}]}):
            with self.subTest(kind=recipe["kind"]):
                path = self.file("recipe.json", recipe)
                with server(lambda request, recording: (201, {"firmware_id": REVISION, "request": request["body"]}, {})) as (recording, base):
                    self.configured(base)
                    status, result = self.invoke("compose", "--json", path)
                    self.assertEqual(status, 0)
                    self.assertEqual(recording.requests[0]["path"], "/api/v1/firmware")
                    self.assertEqual(result["firmware"]["request"], recipe)

    def test_create_persists_original_body_key_and_replays_after_uncertain_admission(self):
        path = self.file("create.json", {"device_id": "fake-board", "runtime": "qemu", "ttl_seconds": 300})
        first = True
        def callback(request, _server):
            nonlocal first
            if request["method"] == "POST":
                pending = json.loads(self.state.read_text())["pending"]
                self.assertEqual(request["body"], pending["request"])
                self.assertIn("idempotency_key", request["body"])
                self.assertNotIn("Idempotency-Key", request["headers"])
                if first:
                    first = False
                    return 503, {"error": {"code": "receipt_lost"}}, {}
                return 202, session(state="provisioning"), {}
            return 200, session(), {}
        with server(callback) as (recording, base):
            self.configured(base)
            self.assertEqual(self.invoke("create", "--json", path, "--wait", 0)[0], 2)
            count = len(recording.requests)
            changed = self.file("different.json", {"device_id": "another-board", "runtime": "qemu"})
            self.assertEqual(self.invoke("create", "--json", changed, "--wait", 0)[1]["error"]["code"], "pending_admission")
            self.assertEqual(len(recording.requests), count)
            self.assertTrue(self.invoke("status")[1]["outcome_unknown"])
            self.assertEqual(self.invoke("create", "--json", path, "--wait", 0)[0], 0)
            writes = [item for item in recording.requests if item["method"] == "POST"]
            self.assertEqual(writes[0]["body"], writes[1]["body"])
            self.assertNotIn("pending", json.loads(self.state.read_text()))
            self.assertNotIn(TOKEN, self.state.read_text())
            self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_creation_requires_explicit_runtime_and_keeps_definite_rejection_resolved(self):
        incomplete = self.file("incomplete.json", {"device_id": "fake-board"})
        with server(lambda request, recording: (409, {"error": {"code": "runtime_model_gap"}}, {})) as (recording, base):
            self.configured(base)
            self.assertEqual(self.invoke("create", "--json", incomplete)[1]["error"]["code"], "explicit_target_required")
            self.assertFalse(recording.requests)
            complete = self.file("complete.json", {"device_id": "fake-board", "runtime": "qemu"})
            self.assertEqual(self.invoke("create", "--json", complete, "--wait", 0)[0], 2)
            value = json.loads(self.state.read_text())
            self.assertNotIn("pending", value)
            self.assertEqual(value["rejected_admission"]["kind"], "session")

    def test_preview_creation_uses_header_key_and_same_request_recovery(self):
        path = self.file("preview.json", {"device_id": "fake-board", "ttl_seconds": 300})
        first = True
        def callback(request, _server):
            nonlocal first
            if request["method"] == "POST":
                self.assertEqual(json.loads(self.state.read_text())["pending"]["key"], request["headers"]["Idempotency-Key"])
                self.assertNotIn("idempotency_key", request["body"])
                if first:
                    first = False
                    return 503, {"error": {}}, {}
                return 202, preview(session_id=None), {}
            return 200, preview(session_id=None), {}
        with server(callback) as (recording, base):
            self.configured(base)
            args = ("request", "POST", "/api/v1/previews", "--json", path)
            self.assertEqual(self.invoke(*args)[0], 2)
            self.assertEqual(self.invoke(*args)[0], 0)
            writes = [item for item in recording.requests if item["method"] == "POST"]
            self.assertEqual(writes[0]["headers"]["Idempotency-Key"], writes[1]["headers"]["Idempotency-Key"])
            self.assertEqual(writes[0]["body"], writes[1]["body"])

    def test_generic_mutations_cannot_target_another_session(self):
        path = self.file("input.json", {"kind": "key", "key": "a", "action": "press"})
        with server(lambda request, recording: (200, session(), {})) as (recording, base):
            self.configured(base, owned=True)
            status, result = self.invoke("request", "POST", "/api/v1/sessions/someone-else/input", "--json", path)
            self.assertEqual(status, 2)
            self.assertEqual(result["error"]["code"], "session_not_owned")
            self.assertFalse(any(item["method"] == "POST" for item in recording.requests))
            self.assertEqual(self.invoke("request", "POST", f"/api/v1/sessions/{SID}/input", "--json", path)[0], 0)

    def test_control_plane_admin_and_lifecycle_bypass_are_rejected(self):
        with server(lambda request, recording: (200, session(), {})) as (recording, base):
            self.configured(base, owned=True)
            for method, path in (("POST", "/api/v1/storage/prune"), ("POST", "/api/v1/workers"),
                                 ("GET", "/api/v1/reviews"), ("POST", "/api/v1/sessions"),
                                 ("POST", f"/api/v1/sessions/{SID}/stop")):
                with self.subTest(path=path):
                    self.assertEqual(self.invoke("request", method, path)[0], 2)
            self.assertFalse(any(item["method"] == "POST" for item in recording.requests))

    def test_managed_session_legacy_mutation_is_rejected(self):
        managed = session(management_binding={"preview_id": PID, "owner_epoch": EPOCH})
        with server(lambda request, recording: (200, managed, {})) as (recording, base):
            self.configured(base, owned=True)
            status, result = self.invoke("request", "POST", f"/api/v1/sessions/{SID}/reset")
            self.assertEqual(status, 2)
            self.assertEqual(result["error"]["code"], "managed_session")
            self.assertFalse(any(item["method"] == "POST" for item in recording.requests))

    def test_preview_run_requires_explicit_current_epoch_generation_and_key(self):
        def callback(request, _server):
            if request["method"] == "POST":
                return 202, {"preview_id": PID, "run_id": "fake-run", "execution_id": "fake-execution", "revision_id": REVISION, "generation": 3}, {}
            return 200, preview(), {}
        with server(callback) as (recording, base):
            self.configured(base, owned=True, managed=True)
            for epoch, generation, key in (("wrong", 2, "stable"), (EPOCH, 1, "stable"), (EPOCH, 2, None)):
                path = self.file("run.json", {"revision_id": REVISION, "expected_owner_epoch": epoch, "expected_generation": generation})
                args = ["request", "POST", f"/api/v1/previews/{PID}/runs", "--json", path]
                if key:
                    args += ["--idempotency-key", key]
                self.assertEqual(self.invoke(*args)[0], 2)
            self.assertFalse(any(item["method"] == "POST" for item in recording.requests))
            path = self.file("run.json", {"revision_id": REVISION, "expected_owner_epoch": EPOCH, "expected_generation": 2})
            self.assertEqual(self.invoke("request", "POST", f"/api/v1/previews/{PID}/runs", "--json", path, "--idempotency-key", "stable")[0], 0)

    def test_preview_run_replays_original_fence_after_ambiguous_generation_advance(self):
        body = {"revision_id": REVISION, "expected_owner_epoch": EPOCH, "expected_generation": 2}
        path = self.file("run.json", body)
        accepted = False
        def callback(request, _server):
            nonlocal accepted
            if request["method"] == "GET":
                return 200, preview(generation=3 if accepted else 2), {}
            self.assertEqual(json.loads(self.state.read_text())["pending_run"]["request"], request["body"])
            if not accepted:
                accepted = True
                return 503, {"error": {"code": "receipt_lost"}}, {}
            return 202, {"preview_id": PID, "run_id": "fake-run", "execution_id": "fake-execution", "revision_id": REVISION, "generation": 3}, {}
        with server(callback) as (recording, base):
            self.configured(base, owned=True, managed=True)
            args = ("request", "POST", f"/api/v1/previews/{PID}/runs", "--json", path, "--idempotency-key", "stable-run")
            self.assertEqual(self.invoke(*args)[0], 2)
            self.assertIn("pending_run", json.loads(self.state.read_text()))
            changed = self.file("changed-run.json", {**body, "expected_generation": 3})
            self.assertEqual(self.invoke("request", "POST", f"/api/v1/previews/{PID}/runs", "--json", changed,
                                         "--idempotency-key", "new-run")[1]["error"]["code"], "pending_run")
            self.assertEqual(self.invoke(*args)[0], 0)
            writes = [item for item in recording.requests if item["method"] == "POST"]
            self.assertEqual(len(writes), 2)
            self.assertEqual(writes[0]["body"], writes[1]["body"])
            self.assertEqual(writes[0]["headers"]["Idempotency-Key"], writes[1]["headers"]["Idempotency-Key"])
            self.assertNotIn("pending_run", json.loads(self.state.read_text()))

    def test_preview_stop_closes_owned_guest_without_replaying_uncertain_run(self):
        closed = False
        def callback(request, _server):
            nonlocal closed
            if request["path"].endswith("/evidence"):
                self.assertFalse(closed)
                return 200, b"PK-FAKE", {}
            if request["method"] == "POST":
                self.assertEqual(request["path"], f"/api/v1/previews/{PID}/close")
                closed = True
                return 202, preview(state="closing"), {}
            if "/previews/" in request["path"]:
                return 200, preview(state="closed" if closed else "ready"), {}
            return 200, session(state="stopped" if closed else "running", management_binding={"preview_id": PID, "owner_epoch": EPOCH}), {}
        with server(callback) as (recording, base):
            self.configured(base, owned=True, managed=True)
            journal = json.loads(self.state.read_text())
            journal["pending_run"] = {"path": f"/api/v1/previews/{PID}/runs", "request": {"revision_id": REVISION}, "key": "unresolved"}
            self.state.write_text(json.dumps(journal))
            status, result = self.invoke("stop", "--wait", 0, "--out-dir", self.root)
            self.assertEqual(status, 0)
            self.assertTrue(result["history_retained"])
            self.assertTrue(result["run_admission_was_unresolved"])
            self.assertIn("unresolved_run_at_close", json.loads(self.state.read_text()))
            self.assertFalse(any(item["path"].endswith("/runs") and item["method"] == "POST" for item in recording.requests))

    def test_encoded_qom_query_reaches_the_service_without_weakening_path_guard(self):
        with server(lambda request, recording: (200, {"value": 1}, {})) as (recording, base):
            self.configured(base)
            path = "/api/v1/sessions/explicit-read-only/qom?path=%2Fmachine%2Funits&property=source-count"
            self.assertEqual(self.invoke("request", "GET", path)[0], 0)
            self.assertEqual(recording.requests[0]["path"], path)

    def test_observe_advances_byte_cursor_not_character_count(self):
        def callback(request, _server):
            parsed = urlsplit(request["path"])
            if parsed.path.endswith("/serial"):
                offset = int(parse_qs(parsed.query)["offset"][0])
                return 200, {"session_id": SID, "offset": offset, "next_offset": offset + 3, "bytes": 3, "data": "中"}, {}
            return 200, session() if parsed.path.endswith(SID) else {}, {}
        with server(callback) as (recording, base):
            self.configured(base, owned=True)
            self.assertEqual(self.invoke("observe")[1]["serial"]["offset"], 0)
            status, result = self.invoke("observe")
            self.assertEqual(status, 0)
            self.assertEqual(result["serial"]["offset"], 3)
            self.assertEqual(json.loads(self.state.read_text())["serial_offset"], 6)
            self.assertIsNone(result["functional_pass"])

    def test_frames_only_claim_current_program_when_before_headers_and_after_match(self):
        for mode in ("current", "mismatch", "no-program", "bad-sha", "stopped", "persisted", "last-known"):
            with self.subTest(mode=mode):
                program = {"execution_id": "exec-fake", "revision_id": REVISION}
                def callback(request, _server):
                    path = urlsplit(request["path"]).path
                    if path.endswith("/serial"):
                        return 200, {"session_id": SID, "offset": 0, "next_offset": 0, "data": ""}, {}
                    if path.endswith("/program"):
                        return 200, {"program": None if mode == "no-program" else program}, {}
                    if path.endswith("/frame.png"):
                        return 200, PNG, {"X-Frame-SHA256": "wrong" if mode == "bad-sha" else hashlib.sha256(PNG).hexdigest(),
                                          "X-Frame-Source": mode if mode in {"persisted", "last-known"} else "live", "X-Frame-Execution-ID": "different" if mode == "mismatch" else "exec-fake",
                                          "X-Frame-Revision-ID": REVISION}
                    return 200, session(state="stopped" if mode == "stopped" else "running"), {}
                with server(callback) as (_, base):
                    self.configured(base, owned=True)
                    status, result = self.invoke("observe", "--frame", "--out-dir", self.root / mode)
                    self.assertEqual(status, 0)
                    self.assertIsNone(result["functional_pass"])
                    if mode == "bad-sha":
                        self.assertIn("unavailable", result["frame"])
                        self.assertFalse((self.root / mode / "frame.png").exists())
                    else:
                        self.assertEqual(result["frame"]["program_identity"], "current_program" if mode == "current" else "historical_sample" if mode in {"stopped", "persisted", "last-known"} else "unattributed_sample")

    def test_stop_downloads_evidence_before_delete_and_preserves_history(self):
        stopped = False
        def callback(request, _server):
            nonlocal stopped
            if request["path"].endswith("/evidence"):
                self.assertFalse(stopped)
                return 200, b"PK-FAKE-EVIDENCE", {}
            if request["method"] == "DELETE":
                self.assertEqual(request["path"], f"/api/v1/sessions/{SID}?purge=0")
                stopped = True
                return 200, session(state="stopping", stop_pending=True), {}
            return 200, session(state="stopped" if stopped else "running"), {}
        with server(callback) as (recording, base):
            self.configured(base, owned=True)
            status, result = self.invoke("stop", "--wait", 0, "--out-dir", self.root / "out")
            self.assertEqual(status, 0)
            self.assertTrue(result["history_retained"])
            self.assertEqual((self.root / "out" / f"evidence-{SID}.zip").read_bytes(), b"PK-FAKE-EVIDENCE")
            self.assertEqual([item["method"] for item in recording.requests], ["GET", "GET", "DELETE", "GET"])

    def test_evidence_failure_does_not_strand_owned_guest_and_retention_is_explicit(self):
        stopped = False
        def callback(request, _server):
            nonlocal stopped
            if request["path"].endswith("/evidence"):
                return 503, {"error": {"code": "capture_failed"}}, {}
            if request["method"] == "DELETE":
                self.assertIn("purge=0&retain_flash=1", request["path"])
                stopped = True
                return 200, session(state="stopped"), {}
            return 200, session(state="stopped" if stopped else "failed"), {}
        with server(callback) as (_, base):
            self.configured(base, owned=True)
            status, result = self.invoke("stop", "--retain-flash", "--wait", 0, "--out-dir", self.root)
            self.assertEqual(status, 0)
            self.assertIn("unavailable", result["evidence"])
            self.assertTrue(result["history_retained"])

    def test_stop_pending_is_not_claimed_finished(self):
        def callback(request, _server):
            return (200, b"PK-FAKE", {}) if request["path"].endswith("/evidence") else (200, session(state="stopping", stop_pending=True), {})
        with server(callback) as (_, base):
            self.configured(base, owned=True)
            status, result = self.invoke("stop", "--wait", 0, "--out-dir", self.root)
            self.assertEqual(status, 0)
            self.assertFalse(result["history_retained"])

    def test_terminal_state_without_worker_lease_release_remains_unconfirmed(self):
        def callback(request, _server):
            return 200, session(state="failed", worker={"lease_active": True}), {}
        with server(callback) as (_, base):
            self.configured(base, owned=True)
            status, result = self.invoke("stop", "--wait", 0, "--out-dir", self.root)
            self.assertEqual(status, 0)
            self.assertFalse(result["cleanup_confirmed"])
            self.assertFalse(result["history_retained"])

    def test_state_origin_and_immutable_session_identity_are_checked(self):
        with server(lambda request, recording: (200, session(firmware_sha256=REVISION), {})) as (recording, base):
            self.configured(base, owned=True)
            self.assertEqual(self.invoke("request", "POST", f"/api/v1/sessions/{SID}/reset")[1]["error"]["code"], "identity_changed")
            self.assertFalse(any(item["method"] == "POST" for item in recording.requests))
            os.environ["M5_EMULATOR_BASE_URL"] = "http://127.0.0.1:19002"
            self.assertEqual(self.invoke("status")[1]["error"]["code"], "state_origin_mismatch")

    def test_token_file_auth_public_url_and_no_secret_echo(self):
        token_file = self.root / "control.token"
        token_file.write_text(TOKEN)
        os.environ.pop("M5_EMULATOR_TOKEN")
        os.environ["M5_EMULATOR_TOKEN_FILE"] = str(token_file)
        def callback(request, _server):
            self.assertEqual(request["headers"]["Authorization"], "Bearer " + TOKEN)
            return 409, {"error": {"code": "fake_failure", "message": "hidden " + TOKEN}}, {}
        with server(callback) as (_, base):
            self.configured(base, owned=True)
            status, result = self.invoke("status")
            self.assertEqual(status, 2)
            self.assertEqual(result["error"]["http_status"], 409)
            self.assertIn("[REDACTED]", result["error"]["message"])
        with server(lambda request, recording: (200, session(), {})) as (_, base):
            self.configured(base, owned=True)
            os.environ["M5_EMULATOR_PUBLIC_URL"] = "https://preview.example.test"
            result = self.invoke("status")[1]
            self.assertEqual(result["browser"]["url"], "https://preview.example.test/platform/web/sessions.html")
            self.assertFalse(result["browser"]["local_only"])
            self.assertNotIn(TOKEN, self.state.read_text())

    def test_redirect_cannot_forward_control_credential(self):
        with server(lambda request, recording: (302, {}, {"Location": "https://outside.example.test/api/v1/health"})) as (recording, base):
            self.configured(base)
            status, result = self.invoke("discover")
            self.assertEqual(status, 2)
            self.assertEqual(result["error"]["http_status"], 302)
            self.assertEqual(len(recording.requests), 1)

    def test_runtime_proxy_is_respected(self):
        with server(lambda request, recording: (200, {"ok": True}, {})) as (recording, base):
            with mock.patch.dict(os.environ, {"HTTP_PROXY": base, "http_proxy": base, "NO_PROXY": "", "no_proxy": ""}):
                self.assertEqual(CLI.Client("http://192.168.1.9:19001", TOKEN).json("GET", "/api/v1/health"), {"ok": True})
            self.assertEqual(recording.requests[0]["path"], "http://192.168.1.9:19001/api/v1/health")

    def test_control_token_cannot_be_saved_inside_creation_request(self):
        path = self.file("secret-create.json", {"device_id": "fake-board", "runtime": "qemu", "runtime_env": {"DO_NOT_SEND": TOKEN}})
        os.environ["M5_EMULATOR_BASE_URL"] = "http://127.0.0.1:19001"
        self.assertEqual(self.invoke("create", "--json", path, "--wait", 0)[1]["error"]["code"], "credential_in_request")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
