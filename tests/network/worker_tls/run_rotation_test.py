#!/usr/bin/env python3
"""Rotate Device Service TLS and worker credentials, then run a real job."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from run_test import (  # noqa: E402
    free_tcp_port,
    generate_certificates,
    upload_artifact,
    wait_for_https,
    write_evidence,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from transport_security import build_client_tls_context  # noqa: E402
from worker_agent import Api, WorkerAgentError  # noqa: E402


def atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(4)}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, temporary)
    temporary.chmod(0o600)
    os.replace(temporary, destination)


def install_active_security(pki: Path, active: Path, token: str) -> None:
    for name in ("ca.crt", "server.crt", "server.key", "client.crt", "client.key"):
        atomic_copy(pki / name, active / name)
    write_token_file(active / "token", token)


def write_token_file(path: Path, token: str) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    temporary.write_text(token + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def wait_for_worker(
    api: Api,
    worker_id: str,
    timeout: float = 15,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        workers = api.json("/api/v1/workers")["workers"]
        for worker in workers:
            if (
                worker.get("worker_id") == worker_id
                and worker.get("state") in {"ready", "draining", "drained"}
            ):
                return worker
        time.sleep(0.1)
    raise TimeoutError("worker did not register with the original credentials")


def wait_for_log_marker(
    path: Path,
    marker: str,
    timeout: float = 15,
    count: int = 1,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = path.read_text(errors="replace") if path.is_file() else ""
        if text.count(marker) >= count:
            return
        time.sleep(0.1)
    raise TimeoutError(f"log marker not observed {count} times: {marker}")


def start_inflight_request(
    port: int,
    token: str,
    context,
    body: bytes,
) -> http.client.HTTPSConnection:
    connection = http.client.HTTPSConnection(
        "127.0.0.1",
        port,
        timeout=15,
        context=context,
    )
    connection.putrequest("POST", "/api/v1/artifacts")
    connection.putheader("Authorization", f"Bearer {token}")
    connection.putheader("Content-Type", "application/octet-stream")
    connection.putheader("Content-Length", str(len(body)))
    connection.endheaders()
    connection.send(body[:1])
    return connection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=(
            Path(__file__).parent
            / "evidence-2026-10-24-security-rotation-overlap-job-pass.json"
        ),
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="m5-worker-rotation-") as temp:
        temp_dir = Path(temp)
        pki_a = temp_dir / "pki-a"
        pki_b = temp_dir / "pki-b"
        active = temp_dir / "active"
        pki_a.mkdir()
        pki_b.mkdir()
        active.mkdir()
        generate_certificates(pki_a)
        generate_certificates(pki_b)
        token_a = secrets.token_urlsafe(32)
        token_b = secrets.token_urlsafe(32)
        install_active_security(pki_a, active, token_a)

        client_a_context = build_client_tls_context(
            ca_file=pki_a / "ca.crt",
            client_cert_file=pki_a / "client.crt",
            client_key_file=pki_a / "client.key",
        )
        client_b_context = build_client_tls_context(
            ca_file=pki_b / "ca.crt",
            client_cert_file=pki_b / "client.crt",
            client_key_file=pki_b / "client.key",
        )
        combined_ca = temp_dir / "combined-ca.crt"
        combined_ca.write_bytes(
            (pki_a / "ca.crt").read_bytes()
            + b"\n"
            + (pki_b / "ca.crt").read_bytes()
        )
        client_a_overlap_context = build_client_tls_context(
            ca_file=combined_ca,
            client_cert_file=pki_a / "client.crt",
            client_key_file=pki_a / "client.key",
        )
        port = free_tcp_port()
        base_url = f"https://127.0.0.1:{port}"
        api_a = Api(base_url, token_a, ssl_context=client_a_context)
        api_b = Api(base_url, token_b, ssl_context=client_b_context)
        worker_log = temp_dir / "worker.log"
        server_log = temp_dir / "server.log"
        service_state = temp_dir / "service"
        worker_dir = temp_dir / "worker"

        with server_log.open("wb") as output:
            service = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "platform/tools/serve.py"),
                    str(port),
                    "--bind",
                    "127.0.0.1",
                    "--state-dir",
                    str(service_state),
                    "--max-sessions",
                    "1",
                    "--max-per-device",
                    "1",
                    "--api-token-file",
                    str(active / "token"),
                    "--tls-cert",
                    str(active / "server.crt"),
                    "--tls-key",
                    str(active / "server.key"),
                    "--tls-client-ca",
                    str(active / "ca.crt"),
                    "--api-token-previous-file",
                    str(active / "previous-token"),
                    "--tls-client-ca-previous",
                    str(active / "previous-ca.crt"),
                ],
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        worker: subprocess.Popen | None = None
        checks = {
            "initial_https_credentials": "FAIL",
            "worker_registered_before_rotation": "FAIL",
            "server_security_reload": "FAIL",
            "overlap_old_client_certificate_accepted": "FAIL",
            "overlap_old_master_token_accepted": "FAIL",
            "final_security_reload": "FAIL",
            "final_old_tls_identity_rejected": "FAIL",
            "final_old_master_token_rejected": "FAIL",
            "new_tls_identity_accepted": "FAIL",
            "worker_credentials_reload": "FAIL",
            "active_request_drained_across_rotation": "FAIL",
            "signed_job_after_rotation": "FAIL",
            "job_evidence_sha256": "FAIL",
        }
        try:
            wait_for_https(api_a, service, 15)
            checks["initial_https_credentials"] = "PASS"

            worker_env = os.environ.copy()
            worker_env["PYTHONPATH"] = str(ROOT / "platform/tools")
            with worker_log.open("wb") as output:
                worker = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "platform/tools/worker_agent.py"),
                        "--service-url",
                        base_url,
                        "--token-file",
                        str(active / "token"),
                        "--ca-file",
                        str(active / "ca.crt"),
                        "--client-cert",
                        str(active / "client.crt"),
                        "--client-key",
                        str(active / "client.key"),
                        "--worker-id",
                        "rotation-worker",
                        "--work-dir",
                        str(worker_dir),
                        "--capabilities-json",
                        '{"qemu": true}',
                        "--poll-seconds",
                        "0.2",
                        "--heartbeat-interval",
                        "2",
                        "--max-jobs",
                        "1",
                    ],
                    cwd=ROOT,
                    env=worker_env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            worker_record = wait_for_worker(api_a, "rotation-worker")
            checks["worker_registered_before_rotation"] = "PASS"

            inflight_body = b"worker-rotation-drain-probe"
            inflight = start_inflight_request(
                port,
                token_a,
                client_a_context,
                inflight_body,
            )
            time.sleep(0.2)
            os.kill(worker.pid, signal.SIGSTOP)
            atomic_copy(pki_a / "ca.crt", active / "previous-ca.crt")
            write_token_file(active / "previous-token", token_a)
            install_active_security(pki_b, active, token_b)
            os.kill(service.pid, signal.SIGHUP)
            os.kill(worker.pid, signal.SIGHUP)

            wait_for_log_marker(
                server_log,
                "security configuration drain started",
                15,
            )
            time.sleep(0.2)
            if "security configuration reloaded" in server_log.read_text(
                errors="replace"
            ):
                raise RuntimeError(
                    "security reload completed before the active request drained"
                )
            inflight.send(inflight_body[1:])
            response = inflight.getresponse()
            response_body = response.read()
            inflight.close()
            if response.status != 201 or b"artifact_id" not in response_body:
                raise RuntimeError(
                    "in-flight artifact upload did not complete across rotation: "
                    f"HTTP {response.status} {response_body[:500]!r}"
                )
            checks["active_request_drained_across_rotation"] = "PASS"

            wait_for_log_marker(
                server_log,
                "security configuration reloaded",
                15,
            )
            wait_for_https(api_b, service, 15)
            checks["server_security_reload"] = "PASS"
            checks["new_tls_identity_accepted"] = "PASS"

            overlap_old_api = Api(
                base_url,
                token_a,
                ssl_context=client_a_overlap_context,
            )
            overlap_old_api.json("/api/v1/health")
            overlap_old_api.json("/api/v1/workers")
            checks["overlap_old_client_certificate_accepted"] = "PASS"
            checks["overlap_old_master_token_accepted"] = "PASS"

            os.kill(worker.pid, signal.SIGCONT)
            wait_for_log_marker(
                worker_log,
                "worker credentials reloaded",
                15,
            )
            checks["worker_credentials_reload"] = "PASS"

            (active / "previous-token").unlink()
            (active / "previous-ca.crt").unlink()
            os.kill(service.pid, signal.SIGHUP)
            wait_for_log_marker(
                server_log,
                "security configuration reloaded",
                15,
                count=2,
            )
            checks["final_security_reload"] = "PASS"
            wait_for_https(api_b, service, 15)

            try:
                Api(
                    base_url,
                    token_b,
                    ssl_context=client_a_overlap_context,
                ).json("/api/health")
            except WorkerAgentError:
                checks["final_old_tls_identity_rejected"] = "PASS"
            else:
                raise RuntimeError(
                    "old TLS identity remained accepted after final cutover"
                )

            retired_api = Api(
                base_url,
                token_a,
                ssl_context=client_b_context,
            )
            retired_api.worker_identity = {
                "worker_id": worker_record["worker_id"],
                "instance_id": worker_record["instance_id"],
                "generation": worker_record["generation"],
            }
            try:
                retired_api.request(
                    "/api/v1/jobs/claim",
                    method="POST",
                    payload={},
                )
            except WorkerAgentError as error:
                if "HTTP 401" not in str(error):
                    raise RuntimeError(
                        f"old master token failed unexpectedly: {error}"
                    ) from error
                checks["final_old_master_token_rejected"] = "PASS"
            else:
                raise RuntimeError(
                    "old master token remained accepted after final cutover"
                )

            source_image = (
                ROOT / "platform/.cache/firmware/sticks3/uiflow2.bin"
            )
            source = source_image.read_bytes()
            flash_size = 8 << 20
            full_image = temp_dir / "sticks3-full.bin"
            full_image.write_bytes(
                source + b"\xff" * (flash_size - len(source))
            )
            artifact = upload_artifact(
                base_url,
                token_b,
                client_b_context,
                full_image,
            )
            firmware = api_b.json(
                "/api/v1/firmware",
                method="POST",
                payload={
                    "device_id": "sticks3",
                    "kind": "merged",
                    "artifact_id": artifact["artifact_id"],
                },
            )
            job_id = secrets.token_hex(8)
            submitted = api_b.json(
                "/api/v1/jobs",
                method="POST",
                payload={
                    "label": "rotation-sticks3-qemu",
                    "request": {
                        "session": {
                            "device_id": "sticks3",
                            "runtime": "qemu",
                            "firmware_id": firmware["firmware_id"],
                            "ready_timeout_seconds": 120,
                        },
                        "evidence_include": [
                            "manifest",
                            "serial",
                            "frames",
                            "logs",
                            "qom",
                        ],
                    },
                    "required_capabilities": {"qemu": True},
                    "max_attempts": 1,
                    "idempotency_key": f"rotation-{job_id}",
                },
            )
            job_id = str(submitted["job"]["job_id"])
            worker.wait(timeout=60)
            if worker.returncode != 0:
                raise RuntimeError(
                    "worker failed after credential rotation: "
                    + worker_log.read_text(errors="replace")[-1000:]
                )

            job = api_b.json(f"/api/v1/jobs/{job_id}")["job"]
            result = job.get("result")
            result = result if isinstance(result, dict) else {}
            if (
                job.get("status") != "completed"
                or result.get("state") != "PASS"
                or int(job.get("attempts", 0)) != 1
            ):
                raise RuntimeError(f"rotated worker job failed: {job}")
            evidence_path = worker_dir / job_id / "evidence.zip"
            evidence = evidence_path.read_bytes()
            evidence_sha256 = hashlib.sha256(evidence).hexdigest()
            if evidence_sha256 != result.get("evidence_sha256"):
                raise RuntimeError("rotated worker evidence SHA256 mismatch")
            checks["signed_job_after_rotation"] = "PASS"
            checks["job_evidence_sha256"] = "PASS"

            payload = {
                "schema_version": 1,
                "kind": "m5stack-worker-security-rotation-overlap-qemu-job",
                "date": "2026-10-24",
                "status": "PASS",
                "validation": "transport-security validation",
                "scope": (
                    "same-host-loopback-bounded-overlap-"
                    "final-cutover-with-drain"
                ),
                "rotation": {
                    "server_certificate": "A-to-B",
                    "client_ca_overlap": "A-and-B",
                    "client_ca_final": "B",
                    "worker_client_certificate": "A-to-B",
                    "master_token_overlap": "A-and-B",
                    "master_token_final": "B",
                    "reload_signal": "SIGHUP",
                    "active_request_drain": "PASS",
                    "client_fleet_migration": "manual-staged",
                },
                "live_job": {
                    "status": job["status"],
                    "result_state": result["state"],
                    "attempts": job["attempts"],
                    "firmware_sha256": firmware["sha256"],
                    "evidence_bytes": len(evidence),
                    "evidence_sha256": evidence_sha256,
                },
                "checks": checks,
                "not_claimed": [
                    "cross-host network topology",
                    "automated client fleet migration",
                    "production CA or secret manager integration",
                    "multi-host scheduling or worker continuity",
                    "hardware validation",
                ],
            }
            if not all(value == "PASS" for value in checks.values()):
                raise RuntimeError(f"rotation checks incomplete: {checks}")
            write_evidence(args.out, payload)
            print(f"evidence={args.out}")
            print(json.dumps(payload, indent=2))
        finally:
            if worker is not None and worker.poll() is None:
                os.killpg(worker.pid, signal.SIGCONT)
                os.killpg(worker.pid, signal.SIGTERM)
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(worker.pid, signal.SIGKILL)
                    worker.wait(timeout=5)
            if service.poll() is None:
                os.killpg(service.pid, signal.SIGTERM)
                try:
                    service.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(service.pid, signal.SIGKILL)
                    service.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
