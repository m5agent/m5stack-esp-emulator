#!/usr/bin/env python3
"""Verify lease-bound evidence persistence through the real worker HTTP paths."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from worker_agent import Api, WorkerAgent, WorkerAgentError

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"
OPENAPI = ROOT / "docs/device-service.openapi.yaml"
EVIDENCE_STORE = ROOT / "platform/tools/evidence_store.py"
WORKER_AGENT = ROOT / "platform/tools/worker_agent.py"


class LostEvidenceResponseApi(Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence_attempts = 0
        self.lost_response = False

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60,
    ) -> tuple[int, bytes, str]:
        response = super().request(
            path,
            method=method,
            payload=payload,
            data=data,
            headers=headers,
            timeout=timeout,
        )
        if path == "/api/v1/evidence":
            self.evidence_attempts += 1
            if not self.lost_response:
                self.lost_response = True
                raise WorkerAgentError(
                    "injected evidence upload response loss",
                    transient=True,
                )
        return response


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
        env={
            **os.environ,
            "M5_JOB_LEASE_SECONDS": "180",
            "M5_EVIDENCE_RETENTION_SECONDS": "86400",
        },
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


def request_json(
    url: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
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
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def evidence_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "kind": "remote-evidence-persistence",
                    "firmware_execution": "NOT RUN",
                }
            ),
        )
        archive.writestr("serial.log", secrets.token_bytes(2 * 1024 * 1024))
    return output.getvalue()


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
    identity = {
        "worker_id": "evidence-worker",
        "instance_id": "evidence-instance",
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
        api = LostEvidenceResponseApi(base_url, token)
        agent = WorkerAgent(
            api,
            work_dir=args.out_dir / "worker",
            identity=identity,
            capabilities={"evidence_storage": True},
            control_reconnect_timeout=2,
        )
        agent.register()
        submitted = request_json(
            base_url + "/api/v1/jobs",
            token,
            method="POST",
            payload={
                "label": "evidence-persistence",
                "request": {"scope": "control-plane-only"},
                "required_capabilities": {"evidence_storage": True},
                "idempotency_key": "evidence-job-1",
            },
        )["job"]
        job_id = str(submitted["job_id"])
        claimed = agent.claim()
        if not isinstance(claimed, dict) or claimed.get("job_id") != job_id:
            raise RuntimeError("worker did not claim the evidence job")
        lease_id = str(claimed["lease"]["lease_id"])
        payload = evidence_zip()
        digest = hashlib.sha256(payload).hexdigest()
        uploaded = agent.upload_evidence(
            job_id,
            lease_id,
            payload,
            digest,
        )
        evidence_id = str(uploaded["evidence_id"])
        checks = {
            "worker_agent_lost_upload_response": (
                api.lost_response and api.evidence_attempts == 2
            ),
            "replayed_same_evidence_id": (
                uploaded.get("idempotent_replay") is True
            ),
            "lease_bound_job": uploaded.get("job_id") == job_id,
            "lease_bound_lease": uploaded.get("lease_id") == lease_id,
            "content_digest": uploaded.get("content_sha256") == digest,
            "multi_megabyte_zip": int(uploaded.get("size", 0)) > 1024 * 1024,
        }

        service_logs.append(stop_service(service))
        restarted = start_service(
            port=port,
            state_dir=state_dir,
            token_file=token_file,
        )
        wait_health(base_url, restarted)
        agent.register()
        metadata_request = urllib.request.Request(
            base_url + f"/api/v1/evidence/{evidence_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(metadata_request, timeout=30) as response:
            stored = json.loads(response.read())["evidence"]
        content_request = urllib.request.Request(
            base_url + f"/api/v1/evidence/{evidence_id}/content",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(content_request, timeout=30) as response:
            downloaded = response.read()
        checks.update(
            {
                "metadata_survives_restart": (
                    stored["evidence_id"] == evidence_id
                    and stored["content_sha256"] == digest
                ),
                "content_survives_restart": (
                    hashlib.sha256(downloaded).hexdigest() == digest
                    and downloaded == payload
                ),
            }
        )

        different = evidence_zip()
        try:
            agent.upload_evidence(
                job_id,
                lease_id,
                different,
                hashlib.sha256(different).hexdigest(),
            )
        except WorkerAgentError as error:
            checks["different_bytes_conflict"] = error.status == 409
        else:
            checks["different_bytes_conflict"] = False

        try:
            agent.report_result(
                job_id,
                lease_id,
                state="PASS",
                evidence_id="0" * 64,
                evidence_sha256=digest,
                summary={"scope": "control-plane-only"},
            )
        except WorkerAgentError as error:
            checks["wrong_evidence_id_rejected"] = error.status == 409
        else:
            checks["wrong_evidence_id_rejected"] = False

        completed = agent.report_result(
            job_id,
            lease_id,
            state="PASS",
            evidence_id=evidence_id,
            evidence_sha256=digest,
            summary={"scope": "control-plane-only"},
        )
        checks.update(
            {
                "result_records_evidence_id": (
                    completed["result"]["evidence_id"] == evidence_id
                ),
                "result_records_digest": (
                    completed["result"]["evidence_sha256"] == digest
                ),
            }
        )
        queue_text = (state_dir / "jobs.json").read_text()
        metadata_path = state_dir / "evidence" / "records" / f"{evidence_id}.json"
        blob_path = state_dir / "evidence" / "blobs" / f"{digest}.zip"
        metadata_text = metadata_path.read_text()
        checks.update(
            {
                "raw_evidence_not_in_jobs": "remote-evidence-persistence" not in queue_text,
                "raw_evidence_not_in_metadata": "remote-evidence-persistence" not in metadata_text,
                "metadata_mode_0600": (metadata_path.stat().st_mode & 0o777) == 0o600,
                "blob_mode_0600": (blob_path.stat().st_mode & 0o777) == 0o600,
                "token_absent_from_service_log": all(
                    token not in output for output in service_logs
                ),
            }
        )
        result = {
            "schema_version": 1,
            "kind": "m5stack-lease-bound-evidence-store",
            "date": "2026-10-29",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": "real HTTP worker/control path; no QEMU guest",
            "source_sha256": {
                "openapi": hashlib.sha256(OPENAPI.read_bytes()).hexdigest(),
                "evidence_store": hashlib.sha256(EVIDENCE_STORE.read_bytes()).hexdigest(),
                "worker_agent": hashlib.sha256(WORKER_AGENT.read_bytes()).hexdigest(),
            },
            "binding": {
                "job_id_sha256": hashlib.sha256(job_id.encode()).hexdigest(),
                "lease_id_sha256": hashlib.sha256(lease_id.encode()).hexdigest(),
                "evidence_id": evidence_id,
            },
            "archive": {
                "bytes": len(payload),
                "content_sha256": digest,
                "entry_count": 2,
            },
            "checks": checks,
            "not_claimed": [
                "physical cross-host execution",
                "QEMU guest execution",
                "external side-effect fencing",
                "object-store replication",
                "physical hardware",
            ],
        }
        (args.out_dir / "evidence.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    finally:
        active = restarted or service
        if active.poll() is None:
            stop_service(active)
        token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
