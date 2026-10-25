#!/usr/bin/env python3
"""Minimal authenticated runtime API with a controllable child side effect."""

from __future__ import annotations

import argparse
import io
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_auth import read_master_token_file  # noqa: E402


def write_state(path: Path, sessions: dict[str, dict[str, Any]]) -> None:
    payload = {
        "updated_at": time.time(),
        "sessions": sessions,
    }
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(temporary, path)


def evidence_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", "{}\n")
        archive.writestr("serial.log", "PARTITION_RETRY_EVIDENCE\n")
    return output.getvalue()


class RuntimeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    token_file: Path
    state_file: Path
    sessions: dict[str, dict[str, Any]]
    lock: threading.RLock


class Handler(BaseHTTPRequestHandler):
    server: RuntimeServer

    def _authorized(self) -> bool:
        token = read_master_token_file(self.server.token_file)
        return self.headers.get("Authorization") == f"Bearer {token}"

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _snapshot(self, session: dict[str, Any]) -> dict[str, Any]:
        process = session.get("_process")
        if (
            isinstance(process, subprocess.Popen)
            and process.poll() is not None
            and session.get("state") == "running"
        ):
            session["state"] = "failed"
            session["exit_code"] = process.returncode
        return {
            key: value
            for key, value in session.items()
            if not key.startswith("_")
        }

    def _persist(self) -> None:
        with self.server.lock:
            snapshots = {
                session_id: self._snapshot(session)
                for session_id, session in self.server.sessions.items()
            }
            write_state(self.server.state_file, snapshots)

    def _stop_session(self, session_id: str) -> dict[str, Any] | None:
        with self.server.lock:
            session = self.server.sessions.get(session_id)
            if session is None:
                return None
            process = session.get("_process")
            if (
                isinstance(process, subprocess.Popen)
                and process.poll() is None
            ):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if session.get("state") not in {"failed", "stopped"}:
                session["state"] = "stopped"
            session["stopped_at"] = time.time()
            session["side_effect_reaped"] = (
                not isinstance(process, subprocess.Popen)
                or process.poll() is not None
            )
            snapshot = self._snapshot(session)
            self._persist()
            return snapshot

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({"ok": True})
            return
        if not self._authorized():
            self._json({"error": "unauthorized"}, 401)
            return
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "v1"] and parts[2] == "sessions":
            with self.server.lock:
                sessions = [
                    self._snapshot(session)
                    for session in self.server.sessions.values()
                ]
            self._json({"sessions": sessions})
            return
        if len(parts) == 4 and parts[:3] == ["api", "v1", "sessions"]:
            with self.server.lock:
                session = self.server.sessions.get(parts[3])
                if session is None:
                    self._json({"error": "not_found"}, 404)
                    return
                snapshot = self._snapshot(session)
                self._persist()
            self._json(snapshot)
            return
        if (
            len(parts) == 5
            and parts[:3] == ["api", "v1", "sessions"]
            and parts[4] == "evidence"
        ):
            with self.server.lock:
                if parts[3] not in self.server.sessions:
                    self._json({"error": "not_found"}, 404)
                    return
            body = evidence_zip()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"error": "not_found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            self._json({"error": "unauthorized"}, 401)
            return
        if parsed.path != "/api/v1/sessions":
            self._json({"error": "not_found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(min(length, 64 * 1024))
        try:
            request = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid_json"}, 400)
            return
        if not isinstance(request, dict):
            self._json({"error": "invalid_request"}, 400)
            return
        side_effect = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(600)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        session_id = uuid.uuid4().hex
        with self.server.lock:
            self.server.sessions[session_id] = {
                "session_id": session_id,
                "device_id": request.get("device_id", "sticks3"),
                "runtime": request.get("runtime", "qemu"),
                "state": "running",
                "created_at": time.time(),
                "side_effect_pid": side_effect.pid,
                "side_effect_reaped": False,
                "_process": side_effect,
            }
            self._persist()
        self._json({"session_id": session_id}, 201)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            self._json({"error": "unauthorized"}, 401)
            return
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 4 and parts[:3] == ["api", "v1", "sessions"]:
            snapshot = self._stop_session(parts[3])
            if snapshot is None:
                self._json({"error": "not_found"}, 404)
                return
            self._json(snapshot)
            return
        self._json({"error": "not_found"}, 404)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    server = RuntimeServer((args.bind, args.port), Handler)
    server.token_file = args.token_file
    server.state_file = args.state_file
    server.sessions = {}
    server.lock = threading.RLock()
    write_state(server.state_file, {})

    def shutdown(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"partition runtime fixture: {args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        with server.lock:
            for session in server.sessions.values():
                process = session.get("_process")
                if (
                    isinstance(process, subprocess.Popen)
                    and process.poll() is None
                ):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                session["state"] = "stopped"
                session["side_effect_reaped"] = (
                    not isinstance(process, subprocess.Popen)
                    or process.poll() is not None
                )
            snapshots = {
                session_id: {
                    key: value
                    for key, value in session.items()
                    if not key.startswith("_")
                }
                for session_id, session in server.sessions.items()
            }
            write_state(server.state_file, snapshots)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
