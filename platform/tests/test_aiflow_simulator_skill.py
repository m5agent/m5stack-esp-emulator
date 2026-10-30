"""Portable AIFlow Skill checks using synthetic HTTP only, never a Device Service."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import types
import unittest
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[2] / "skills" / "uiflow2-simulator"
SCRIPT = SKILL / "scripts" / "simulator.py"
simulator = types.ModuleType("aiflow_simulator_skill")
simulator.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), simulator.__dict__)

TOKEN = "synthetic-recording-control-value"
PREVIEW = "preview-recording"
EPOCH = "epoch-recording"
SESSION = "session-recording"
RUN = "run-recording"
EXECUTION = "execution-recording"
REVISION = "a" * 64


def preview(**changes):
    return {
        "preview_id": PREVIEW, "owner_epoch": EPOCH, "generation": 7,
        "session_id": SESSION, "state": "ready", "active_run_id": RUN, **changes,
    }


def run(**changes):
    return {
        "preview_id": PREVIEW, "run_id": RUN, "execution_id": EXECUTION,
        "revision_id": REVISION, "generation": 8, "state": "running", **changes,
    }


@contextmanager
def recording_server(callback):
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            request = {
                "method": self.command, "path": self.path,
                "headers": dict(self.headers.items()),
                "body": json.loads(content) if content else None,
            }
            self.server.requests.append(request)
            try:
                status, value, headers = callback(request)
            except Exception as error:
                self.server.errors.append(error)
                status, value, headers = 500, {"error": {"code": "recording_callback_failed"}}, {}
            body = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", "application/octet-stream" if isinstance(value, bytes) else "application/json")
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = handle_request

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests, server.errors = [], []
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if server.errors:
        raise server.errors[0]


class AIFlowSimulatorSkillTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        local = patch.object(simulator, "LOCAL_CONFIG", self.root / "missing-config.local.json")
        local.start()
        self.addCleanup(local.stop)

    def configure(self, base, path=None):
        os.environ["AIFLOW_SIMULATOR_BASE_URL"] = base
        os.environ["AIFLOW_SIMULATOR_TOKEN"] = TOKEN
        if path:
            value = json.loads(path.read_text(encoding="utf-8"))
            value["base_url"] = base
            path.write_text(json.dumps(value), encoding="utf-8")

    def state(self, **changes):
        path = self.root / "state.json"
        path.write_text(json.dumps({
            "schema_version": 1, "base_url": "placeholder", "preview_id": PREVIEW,
            "owner_epoch": EPOCH, "generation": 7, "session_id": SESSION,
            "run_id": RUN, "execution_id": EXECUTION, "revision_id": REVISION, **changes,
        }), encoding="utf-8")
        return path

    def invoke(self, path, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = simulator.main(["--state", str(path), *arguments])
        self.assertEqual(error.getvalue(), "")
        self.assertNotIn(TOKEN, output.getvalue())
        return status, json.loads(output.getvalue())

    def test_package_is_self_contained_and_has_no_operator_configuration(self):
        expected = {"SKILL.md", "scripts/simulator.py", "references/workflow.md", "source.json", "LICENSE"}
        actual = {str(path.relative_to(SKILL)) for path in SKILL.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        source = json.loads((SKILL / "source.json").read_text(encoding="utf-8"))
        self.assertEqual(set(source["upstream"]["files_sha256"]), expected - {"source.json", "LICENSE"})
        for digest in source["upstream"]["files_sha256"].values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        allowed_private_network_bases = {"10.0.0.0", "172.16.0.0", "192.168.0.0"}
        for relative in actual:
            text = (SKILL / relative).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)")
            for raw in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
                address = ipaddress.ip_address(raw)
                self.assertTrue(address.is_loopback or raw in allowed_private_network_bases,
                                f"Operator-specific address appeared in {relative}")
        self.assertRegex((SKILL / "SKILL.md").read_text(encoding="utf-8"),
                         r"(?m)^name: uiflow2-simulator$")

    def test_relocated_helper_help_needs_no_source_repository_or_installed_package(self):
        copied = self.root / "relocated-skill"
        shutil.copytree(SKILL, copied)
        project = self.root / "project"
        project.mkdir()
        result = subprocess.run(
            [sys.executable, "-I", str(copied / "scripts" / "simulator.py"), "--help"],
            cwd=project, env=dict(os.environ), capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("discover", result.stdout)
        self.assertIn("run", result.stdout)
        self.assertFalse((project / ".aiflow").exists())

    def test_missing_explicit_origin_fails_without_network_or_state(self):
        path = self.root / "state.json"
        with patch.object(simulator, "Client", side_effect=AssertionError("No implicit service target")):
            status, result = self.invoke(path, "discover")
        self.assertEqual(status, 2)
        self.assertEqual(result["error"]["code"], "base_url_required")
        self.assertFalse(path.exists())

    def test_create_replays_original_journal_after_ambiguous_response(self):
        path = self.root / "state.json"
        admissions = []

        def callback(request):
            self.assertEqual(request["headers"].get("Authorization"), "Bearer " + TOKEN)
            if request["method"] == "POST":
                pending = json.loads(path.read_text(encoding="utf-8"))["pending"]
                self.assertEqual(pending["request"], request["body"])
                self.assertEqual(pending["key"], request["headers"]["Idempotency-Key"])
                admissions.append(request)
                if len(admissions) == 1:
                    return 503, {"error": {"code": "response_lost"}}, {}
                return 202, preview(generation=0, active_run_id=None), {}
            return 200, preview(generation=0, active_run_id=None), {}

        with recording_server(callback) as (server, base):
            self.assertNotEqual(server.server_port, 8787)
            self.configure(base)
            status, result = self.invoke(path, "create", "--device", "cores3", "--wait", "0")
            self.assertEqual(status, 2)
            self.assertTrue(result["error"]["outcome_unknown"])
            count = len(server.requests)
            status, result = self.invoke(path, "create", "--device", "sticks3", "--wait", "0")
            self.assertEqual(result["error"]["code"], "pending_operation")
            self.assertEqual(len(server.requests), count)
            status, result = self.invoke(path, "create", "--device", "cores3", "--wait", "0")
            self.assertEqual(status, 0)
            self.assertTrue(result["ready"])
        self.assertEqual(admissions[0]["body"], admissions[1]["body"])
        self.assertEqual(admissions[0]["headers"]["Idempotency-Key"], admissions[1]["headers"]["Idempotency-Key"])
        self.assertNotIn("pending", json.loads(path.read_text(encoding="utf-8")))
        self.assertNotIn(TOKEN, path.read_text(encoding="utf-8"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_complete_package_run_replay_preserves_binary_resources_and_owner_fence(self):
        path = self.state()
        project = self.root / "project"
        project.mkdir()
        original = "print('APP_READY')\n"
        (project / "main.py").write_text(original, encoding="utf-8")
        (project / "picture.bin").write_bytes(b"\x00\xff\x01")
        submissions = []

        def callback(request):
            if request["method"] == "GET":
                return 200, run() if "/runs/" in request["path"] else preview(), {}
            if request["path"].endswith("/program-revisions"):
                self.assertEqual(set(request["body"]["files"]), {"main.py", "picture.bin"})
                self.assertEqual(base64.b64decode(request["body"]["files"]["picture.bin"]["data"]), b"\x00\xff\x01")
                return 201, {"revision": {"revision_id": REVISION}}, {}
            pending = json.loads(path.read_text(encoding="utf-8"))["pending"]
            self.assertEqual(request["body"], pending["request"])
            self.assertEqual(request["body"]["expected_generation"], 7)
            self.assertEqual(request["body"]["expected_owner_epoch"], EPOCH)
            submissions.append(request)
            return (503, {"error": {"code": "response_lost"}}, {}) if len(submissions) == 1 else (202, run(), {})

        arguments = ("run", "--project-dir", str(project), "--file", "main.py", "--file", "picture.bin", "--wait", "0")
        with recording_server(callback) as (server, base):
            self.configure(base, path)
            self.assertEqual(self.invoke(path, *arguments)[0], 2)
            (project / "main.py").write_text("print('changed')\n", encoding="utf-8")
            count = len(server.requests)
            status, result = self.invoke(path, *arguments)
            self.assertEqual(result["error"]["code"], "pending_operation")
            self.assertEqual(len(server.requests), count)
            (project / "main.py").write_text(original, encoding="utf-8")
            status, result = self.invoke(path, *arguments)
            self.assertEqual(status, 0)
            self.assertEqual(result["application_ready"], "unknown")
            self.assertEqual(sum(row["path"].endswith("/program-revisions") for row in server.requests), 1)
        self.assertEqual(submissions[0]["body"], submissions[1]["body"])
        self.assertEqual(submissions[0]["headers"]["Idempotency-Key"], submissions[1]["headers"]["Idempotency-Key"])

    def test_omitted_previous_resource_does_not_submit_a_partial_snapshot(self):
        path = self.state(package_paths=["main.py", "res/icon.png"])
        (self.root / "main.py").write_text("pass\n", encoding="utf-8")
        with recording_server(lambda _request: (200, preview(), {})) as (server, base):
            self.configure(base, path)
            status, result = self.invoke(path, "run", "--project-dir", str(self.root), "--file", "main.py", "--wait", "0")
            self.assertEqual(status, 2)
            self.assertEqual(result["error"]["code"], "incomplete_package")
            self.assertTrue(all(request["method"] == "GET" for request in server.requests))

    def test_package_whitelist_rejects_private_files_escape_and_symlinks(self):
        (self.root / "main.py").write_text("print('中文')\n", encoding="utf-8")
        for name in ("../main.py", "/main.py", ".env", ".claude/settings.json", "secret.pem", "boot.py"):
            with self.subTest(name=name), self.assertRaises(simulator.SimulatorError):
                simulator.build_package(self.root, files=["main.py", name])
        (self.root / "link.py").symlink_to(self.root / "main.py")
        with self.assertRaises(simulator.SimulatorError):
            simulator.build_package(self.root, files=["main.py", "link.py"])

    def test_stale_frame_is_not_saved_as_current_preview(self):
        path = self.state()
        png = b"\x89PNG\r\n\x1a\nsynthetic-recording-image"

        def callback(request):
            route = request["path"].split("?", 1)[0]
            if route.endswith("/program"):
                return 200, {"program": {"execution_id": EXECUTION, "revision_id": REVISION, "serial_offset": 100}}, {}
            if route.endswith("/serial"):
                return 200, {"session_id": SESSION, "offset": 100, "next_offset": 100, "data": ""}, {}
            if route.endswith("/device-state"):
                return 200, {"session_id": SESSION}, {}
            if route.endswith("/units"):
                return 200, {"session_id": SESSION, "units": []}, {}
            if route.endswith("/frame.png"):
                return 200, png, {
                    "X-Preview-ID": PREVIEW, "X-Run-ID": "stale-run",
                    "X-Frame-Execution-ID": EXECUTION, "X-Frame-Revision-ID": REVISION,
                    "X-Frame-SHA256": hashlib.sha256(png).hexdigest(),
                }
            return 200, run() if "/runs/" in route else preview(), {}

        output = self.root / "artifacts"
        with recording_server(callback) as (_server, base):
            self.configure(base, path)
            status, result = self.invoke(path, "inspect", "--out-dir", str(output))
        self.assertEqual(status, 0)
        self.assertEqual(result["frame"]["status"], "unavailable")
        self.assertEqual(result["frame"]["error"]["code"], "frame_identity_mismatch")
        self.assertFalse((output / "latest.png").exists())


if __name__ == "__main__":
    unittest.main()
