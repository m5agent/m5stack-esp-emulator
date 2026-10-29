#!/usr/bin/env python3
"""Verify durable idempotent job-claim retries through the real HTTP API."""

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
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from worker_auth import sign_worker_request
from worker_agent import Api, WorkerAgent, WorkerAgentError

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"
OPENAPI = ROOT / "docs/device-service.openapi.yaml"
QUEUE = ROOT / "platform/tools/worker_queue.py"
AGENT = ROOT / "platform/tools/worker_agent.py"


class LostClaimResponseApi(Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lost_claim_response = False
        self.claim_payloads: list[dict[str, Any]] = []

    def json(self, path, *, method="GET", payload=None, timeout=60):
        response = super().json(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )
        if path == "/api/v1/jobs/claim" and not self.lost_claim_response:
            self.lost_claim_response = True
            self.claim_payloads.append(dict(payload or {}))
            raise WorkerAgentError(
                "injected claim response loss",
                transient=True,
            )
        if path == "/api/v1/jobs/claim":
            self.claim_payloads.append(dict(payload or {}))
        return response


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
    worker_identity: dict[str, Any] | None = None,
    timeout: float = 30,
) -> Any:
    body = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if worker_identity is not None:
        headers.update(
            sign_worker_request(
                token,
                worker_identity,
                method,
                urlsplit(url).path,
                body or b"",
            )
        )
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
            "2",
            "--max-per-device",
            "1",
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
            with urllib.request.urlopen(
                base_url + "/api/health",
                timeout=1,
            ) as response:
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


def error_code(
    url: str,
    token: str,
    *,
    payload: dict[str, Any],
    worker_identity: dict[str, Any] | None = None,
) -> tuple[int, str | None]:
    body = json.dumps(payload).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if worker_identity is not None:
        headers.update(
            sign_worker_request(
                token,
                worker_identity,
                "POST",
                urlsplit(url).path,
                body,
            )
        )
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read())
        except (TypeError, ValueError):
            body = {}
        return error.code, body.get("error", {}).get("code")
    raise RuntimeError("request unexpectedly succeeded")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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
    worker = {
        "worker_id": "claim-worker",
        "instance_id": "claim-instance",
        "generation": 1,
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
        jobs = []
        for label in ("first", "second"):
            response = request_json(
                base_url + "/api/v1/jobs",
                token,
                method="POST",
                payload={
                    "label": label,
                    "request": {"device_id": "sticks3"},
                    "required_capabilities": {"qemu": True},
                    "idempotency_key": f"submit-{label}",
                },
            )
            jobs.append(response["job"])
        first_job_id = jobs[0]["job_id"]
        second_job_id = jobs[1]["job_id"]
        lossy_api = LostClaimResponseApi(base_url, token)
        agent = WorkerAgent(
            lossy_api,
            work_dir=args.out_dir / "worker-agent",
            identity=worker,
            capabilities={"qemu": True},
            control_reconnect_timeout=2,
        )
        agent.register()
        first_claim = agent.claim()
        claim_key = str(
            lossy_api.claim_payloads[0]["claim_idempotency_key"]
        )
        claim_payload = {
            **worker,
            "claim_idempotency_key": claim_key,
        }
        first_lease_id = first_claim["lease"]["lease_id"]

        service_logs.append(stop_service(service))
        restarted = start_service(
            port=port,
            state_dir=state_dir,
            token_file=token_file,
        )
        wait_health(base_url, restarted)
        replay = request_json(
            base_url + "/api/v1/jobs/claim",
            token,
            method="POST",
            payload=claim_payload,
            worker_identity=worker,
        )["job"]
        second_before = request_json(
            base_url + f"/api/v1/jobs/{second_job_id}",
            token,
        )["job"]
        conflict_status, conflict_code = error_code(
            base_url + "/api/v1/jobs/claim",
            token,
            payload={
                **claim_payload,
                "job_id": second_job_id,
            },
            worker_identity=worker,
        )
        second_claim = request_json(
            base_url + "/api/v1/jobs/claim",
            token,
            method="POST",
            payload={
                **worker,
                "job_id": second_job_id,
                "claim_idempotency_key": "claim-live-002",
            },
            worker_identity=worker,
        )["job"]
        queue_path = state_dir / "jobs.json"
        queue_text = queue_path.read_text()
        checks = {
            "worker_agent_retried_lost_response": (
                lossy_api.lost_claim_response
                and len(lossy_api.claim_payloads) == 2
            ),
            "worker_agent_reused_claim_key": (
                lossy_api.claim_payloads[0].get("claim_idempotency_key")
                == lossy_api.claim_payloads[1].get("claim_idempotency_key")
            ),
            "replay_same_job": replay["job_id"] == first_job_id,
            "replay_same_lease": (
                replay["lease"]["lease_id"] == first_lease_id
            ),
            "replay_flag": replay.get("claim_idempotent_replay") is True,
            "second_job_remains_queued": second_before["status"] == "queued",
            "different_job_conflicts_409": (
                conflict_status == 409
                and conflict_code == "claim_idempotency_conflict"
            ),
            "new_key_claims_second_job": (
                second_claim["job_id"] == second_job_id
                and second_claim.get("claim_idempotent_replay") is False
            ),
            "claim_key_not_persisted": claim_key not in queue_text,
            "queue_mode_0600": (
                queue_path.stat().st_mode & 0o777
            ) == 0o600,
            "token_absent_from_service_log": all(
                token not in output for output in service_logs
            ),
        }
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-worker-claim-idempotency",
            "date": "2026-10-29",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": "real HTTP control-plane; no QEMU guest",
            "source_sha256": {
                "openapi": hashlib.sha256(OPENAPI.read_bytes()).hexdigest(),
                "worker_queue": hashlib.sha256(QUEUE.read_bytes()).hexdigest(),
                "worker_agent": hashlib.sha256(AGENT.read_bytes()).hexdigest(),
            },
            "claim": {
                "key_sha256": digest(claim_key),
                "job_id_sha256": digest(first_job_id),
                "lease_id_sha256": digest(first_lease_id),
                "second_job_id_sha256": digest(second_job_id),
            },
            "service_restart": {
                "same_state_dir": True,
                "same_job": checks["replay_same_job"],
                "same_lease": checks["replay_same_lease"],
            },
            "checks": checks,
            "not_claimed": [
                "physical cross-host execution",
                "actual network-packet blackhole",
                "QEMU guest execution",
                "external side-effect fencing",
                "physical hardware",
            ],
        }
        service_logs.append(stop_service(restarted))
        restarted = None
        (args.out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        active = restarted or service
        if active.poll() is None:
            stop_service(active)
        token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
