#!/usr/bin/env python3
"""Verify concurrent and persisted idempotent session creation."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 60,
) -> Any:
    body = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def start_service(
    *,
    port: int,
    state_dir: Path,
    token_file: Path,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            str(SERVICE),
            str(port),
            "--bind",
            "127.0.0.1",
            "--state-dir",
            str(state_dir),
            "--api-token-file",
            str(token_file),
            "--max-sessions",
            "4",
            "--max-per-device",
            "2",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )


def wait_health(
    base_url: str,
    process: subprocess.Popen[str],
    timeout: float = 20,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("service exited before becoming healthy")
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=1) as response:
                if json.loads(response.read()).get("ok"):
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("service did not become healthy")


def stop_service(process: subprocess.Popen[str]) -> str:
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
    output, _ = process.communicate(timeout=30)
    return output or ""


def wait_session_running(
    base_url: str,
    token: str,
    session_id: str,
    *,
    timeout: float = 90,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = request_json(
            base_url + f"/api/v1/sessions/{session_id}",
            token,
        )
        if latest.get("state") == "running":
            return latest
        if latest.get("state") == "failed":
            raise RuntimeError(f"session failed: {latest.get('error')}")
        time.sleep(0.1)
    raise RuntimeError(f"session did not become running: {latest}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    token = secrets.token_hex(32)
    token_file = args.out_dir / "service.token"
    token_file.write_text(token + "\n")
    token_file.chmod(0o600)
    state_dir = args.out_dir / "service-state"
    idempotency_key = "session-idempotency-live-001"
    payload = {
        "device_id": "sticks3",
        "runtime": "qemu",
        "ttl_seconds": 90,
        "ready_timeout_seconds": 90,
        "idempotency_key": idempotency_key,
    }
    service = start_service(
        port=port,
        state_dir=state_dir,
        token_file=token_file,
    )
    restarted = None
    service_logs: list[str] = []
    try:
        wait_health(base_url, service)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    request_json,
                    base_url + "/api/v1/sessions",
                    token,
                    method="POST",
                    payload=payload,
                )
                for _ in range(2)
            ]
            responses = [future.result(timeout=90) for future in futures]
        session_ids = {row["session_id"] for row in responses}
        session_id = next(iter(session_ids))
        running = wait_session_running(base_url, token, session_id)
        sessions = request_json(
            base_url + "/api/v1/sessions",
            token,
        )["sessions"]
        conflict_status = None
        try:
            request_json(
                base_url + "/api/v1/sessions",
                token,
                method="POST",
                payload={**payload, "ttl_seconds": 91},
            )
        except urllib.error.HTTPError as error:
            conflict_status = error.code
        mapping_path = state_dir / "session-idempotency.json"
        mapping_text = mapping_path.read_text()

        service_logs.append(stop_service(service))
        restarted = start_service(
            port=port,
            state_dir=state_dir,
            token_file=token_file,
        )
        wait_health(base_url, restarted)
        persisted_replay = request_json(
            base_url + "/api/v1/sessions",
            token,
            method="POST",
            payload=payload,
        )
        sessions_after_restart = request_json(
            base_url + "/api/v1/sessions",
            token,
        )["sessions"]
        service_logs.append(stop_service(restarted))
        restarted = None
        checks = {
            "concurrent_same_key_returns_one_session": len(session_ids) == 1,
            "concurrent_responses_use_idempotent_flag": all(
                isinstance(row.get("idempotent_replay"), bool)
                for row in responses
            ),
            "one_running_session_with_pid": (
                running.get("state") == "running"
                and isinstance(running.get("pid"), int)
                and running["pid"] > 0
            ),
            "one_session_recorded": len(sessions) == 1,
            "different_request_conflicts_409": conflict_status == 409,
            "mapping_persisted": mapping_path.is_file(),
            "mapping_mode_0600": (
                mapping_path.stat().st_mode & 0o777 == 0o600
            ),
            "raw_key_not_persisted": idempotency_key not in mapping_text,
            "raw_device_not_persisted": '"sticks3"' not in mapping_text,
            "persisted_replay_same_session": (
                persisted_replay.get("session_id") in session_ids
                and persisted_replay.get("idempotent_replay") is True
            ),
            "one_session_after_restart": len(sessions_after_restart) == 1,
            "token_absent_from_service_log": all(
                token not in output for output in service_logs
            ),
        }
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-session-create-idempotency",
            "date": "2026-10-25",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": "virtual-device-session-create-idempotency",
            "idempotency": {
                "key_sha256": hashlib.sha256(
                    idempotency_key.encode()
                ).hexdigest(),
                "concurrent_requests": 2,
                "session_count": len(session_ids),
                "running_pid": running.get("pid"),
                "conflict_status": conflict_status,
                "mapping_persisted": mapping_path.is_file(),
                "mapping_mode": oct(mapping_path.stat().st_mode & 0o777),
            },
            "responses": [
                {
                    "session_id": row.get("session_id"),
                    "idempotent_replay": row.get("idempotent_replay"),
                    "state": row.get("state"),
                }
                for row in responses
            ],
            "service_restart": {
                "same_state_dir": True,
                "persisted_replay_session_id": persisted_replay.get(
                    "session_id"
                ),
                "session_count": len(sessions_after_restart),
            },
            "checks": checks,
            "not_claimed": [
                "cross-host idempotency storage",
                "idempotency across different API tokens or tenants",
                "firmware execution semantics beyond session creation",
                "physical hardware validation",
            ],
        }
        (args.out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        if restarted is None and service.poll() is None:
            stop_service(service)
        elif restarted is not None:
            stop_service(restarted)
        token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
