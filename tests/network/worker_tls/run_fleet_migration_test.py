#!/usr/bin/env python3
"""Automate same-host worker credential migration and final cutover."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR))
sys.path.insert(0, str(ROOT / "platform/tools"))

from run_rotation_test import (  # noqa: E402
    atomic_copy,
    install_active_security,
    wait_for_log_marker,
    wait_for_worker,
    write_token_file,
)
from run_test import (  # noqa: E402
    free_tcp_port,
    generate_certificates,
    wait_for_https,
    write_evidence,
)
from transport_security import build_client_tls_context  # noqa: E402
from worker_agent import (  # noqa: E402
    Api,
    WorkerAgentError,
    atomic_write,
    credential_file_fingerprint,
)


def start_worker(
    *,
    base_url: str,
    generation_file: Path,
    worker_id: str,
    work_dir: Path,
    receipt_dir: Path,
    log_path: Path,
) -> subprocess.Popen:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "platform/tools")
    with log_path.open("wb") as output:
        return subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "platform/tools/worker_agent.py"),
                "--service-url",
                base_url,
                "--credential-generation-file",
                str(generation_file),
                "--credential-receipt-dir",
                str(receipt_dir),
                "--worker-id",
                worker_id,
                "--work-dir",
                str(work_dir),
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
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def publish_worker_generation(
    pointer: Path,
    generation_dir: Path,
    generation: str,
) -> None:
    relative = generation_dir.relative_to(pointer.parent)
    payload = {
        "schema_version": 1,
        "generation": generation,
        "token_file": str(relative / "token"),
        "ca_file": str(relative / "ca.crt"),
        "client_cert": str(relative / "client.crt"),
        "client_key": str(relative / "client.key"),
    }
    atomic_write(
        pointer,
        (json.dumps(payload, sort_keys=True) + "\n").encode(),
    )


def wait_for_fleet_receipts(
    receipt_dir: Path,
    worker_ids: set[str],
    expected_fingerprint: str,
    timeout: float = 20,
) -> dict[str, dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        receipts: dict[str, dict] = {}
        for path in receipt_dir.glob("worker-*.json"):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            worker_id = payload.get("worker_id")
            if (
                worker_id in worker_ids
                and payload.get("credential_fingerprint")
                == expected_fingerprint
            ):
                receipts[str(worker_id)] = payload
        if set(receipts) == worker_ids:
            return receipts
        time.sleep(0.1)
    raise TimeoutError("not all workers published the expected credential receipt")


def terminate_group(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=(
            TEST_DIR
            / "evidence-2026-10-24-fleet-credential-migration-pass.json"
        ),
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="m5-worker-fleet-") as temp:
        temp_dir = Path(temp)
        pki_a = temp_dir / "pki-a"
        pki_b = temp_dir / "pki-b"
        service_active = temp_dir / "service-active"
        worker_generation_a = temp_dir / "worker-generations/a"
        worker_generation_bridge = temp_dir / "worker-generations/bridge"
        worker_generation_b = temp_dir / "worker-generations/b"
        worker_generation_file = temp_dir / "worker-generation.json"
        receipts_dir = temp_dir / "receipts"
        pki_a.mkdir()
        pki_b.mkdir()
        service_active.mkdir()
        worker_generation_a.mkdir(parents=True)
        worker_generation_bridge.mkdir(parents=True)
        worker_generation_b.mkdir(parents=True)
        receipts_dir.mkdir()
        generate_certificates(pki_a)
        generate_certificates(pki_b)
        token_a = secrets.token_urlsafe(32)
        token_b = secrets.token_urlsafe(32)
        install_active_security(pki_a, service_active, token_a)
        install_active_security(pki_a, worker_generation_a, token_a)
        install_active_security(pki_b, worker_generation_b, token_b)
        publish_worker_generation(
            worker_generation_file,
            worker_generation_a,
            "A",
        )

        client_a = build_client_tls_context(
            pki_a / "ca.crt",
            pki_a / "client.crt",
            pki_a / "client.key",
        )
        client_b = build_client_tls_context(
            pki_b / "ca.crt",
            pki_b / "client.crt",
            pki_b / "client.key",
        )
        combined_ca = temp_dir / "combined-ca.crt"
        combined_ca.write_bytes(
            (pki_a / "ca.crt").read_bytes()
            + b"\n"
            + (pki_b / "ca.crt").read_bytes()
        )
        client_a_overlap = build_client_tls_context(
            combined_ca,
            pki_a / "client.crt",
            pki_a / "client.key",
        )

        port = free_tcp_port()
        base_url = f"https://127.0.0.1:{port}"
        api_a = Api(base_url, token_a, ssl_context=client_a)
        api_b = Api(base_url, token_b, ssl_context=client_b)
        service_log = temp_dir / "service.log"
        service_state = temp_dir / "service"
        with service_log.open("wb") as output:
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
                    str(service_active / "token"),
                    "--tls-cert",
                    str(service_active / "server.crt"),
                    "--tls-key",
                    str(service_active / "server.key"),
                    "--tls-client-ca",
                    str(service_active / "ca.crt"),
                    "--api-token-previous-file",
                    str(service_active / "previous-token"),
                    "--tls-client-ca-previous",
                    str(service_active / "previous-ca.crt"),
                ],
                cwd=ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        worker_ids = {"fleet-worker-a", "fleet-worker-b"}
        workers: list[subprocess.Popen] = []
        worker_logs: dict[str, Path] = {}
        checks = {
            "initial_https_credentials": "FAIL",
            "two_workers_registered_before_rotation": "FAIL",
            "server_security_reload": "FAIL",
            "worker_trust_bridge_receipts": "FAIL",
            "overlap_workers_reach_new_server": "FAIL",
            "automated_worker_reload_receipts": "FAIL",
            "both_workers_heartbeat_new_identity": "FAIL",
            "overlap_old_credentials_accepted": "FAIL",
            "final_security_reload": "FAIL",
            "final_old_identity_rejected": "FAIL",
            "final_new_identity_accepted": "FAIL",
            "worker_sighup_not_required": "PASS",
        }
        try:
            wait_for_https(api_a, service, 15)
            checks["initial_https_credentials"] = "PASS"

            for worker_id in sorted(worker_ids):
                work_dir = temp_dir / worker_id
                log_path = temp_dir / f"{worker_id}.log"
                worker_logs[worker_id] = log_path
                workers.append(
                    start_worker(
                        base_url=base_url,
                        generation_file=worker_generation_file,
                        worker_id=worker_id,
                        work_dir=work_dir,
                        receipt_dir=receipts_dir,
                        log_path=log_path,
                    )
                )
            for worker_id in worker_ids:
                wait_for_worker(api_a, worker_id)
            checks["two_workers_registered_before_rotation"] = "PASS"

            atomic_copy(
                combined_ca,
                worker_generation_bridge / "ca.crt",
            )
            atomic_copy(
                pki_a / "client.crt",
                worker_generation_bridge / "client.crt",
            )
            atomic_copy(
                pki_a / "client.key",
                worker_generation_bridge / "client.key",
            )
            write_token_file(worker_generation_bridge / "token", token_a)
            publish_worker_generation(
                worker_generation_file,
                worker_generation_bridge,
                "A-to-B-trust",
            )
            bridge_fingerprint = credential_file_fingerprint(
                [worker_generation_file]
            )
            wait_for_fleet_receipts(
                receipts_dir,
                worker_ids,
                bridge_fingerprint,
            )
            checks["worker_trust_bridge_receipts"] = "PASS"

            atomic_copy(
                pki_a / "ca.crt",
                service_active / "previous-ca.crt",
            )
            write_token_file(service_active / "previous-token", token_a)
            install_active_security(pki_b, service_active, token_b)
            os.kill(service.pid, signal.SIGHUP)
            wait_for_log_marker(
                service_log,
                "security configuration reloaded",
                15,
            )
            wait_for_https(api_b, service, 15)
            checks["server_security_reload"] = "PASS"

            overlap_api = Api(
                base_url,
                token_a,
                ssl_context=client_a_overlap,
            )
            for worker_id in worker_ids:
                wait_for_worker(overlap_api, worker_id)
            checks["overlap_workers_reach_new_server"] = "PASS"

            publish_worker_generation(
                worker_generation_file,
                worker_generation_b,
                "B",
            )
            expected_fingerprint = credential_file_fingerprint(
                [worker_generation_file]
            )
            receipts = wait_for_fleet_receipts(
                receipts_dir,
                worker_ids,
                expected_fingerprint,
            )
            checks["automated_worker_reload_receipts"] = "PASS"
            for worker_id in worker_ids:
                wait_for_worker(api_b, worker_id)
            checks["both_workers_heartbeat_new_identity"] = "PASS"

            overlap_api.json("/api/v1/health")
            overlap_api.json("/api/v1/workers")
            checks["overlap_old_credentials_accepted"] = "PASS"

            (service_active / "previous-token").unlink()
            (service_active / "previous-ca.crt").unlink()
            os.kill(service.pid, signal.SIGHUP)
            wait_for_log_marker(
                service_log,
                "security configuration reloaded",
                15,
                count=2,
            )
            wait_for_https(api_b, service, 15)
            checks["final_security_reload"] = "PASS"
            checks["final_new_identity_accepted"] = "PASS"

            try:
                Api(
                    base_url,
                    token_a,
                    ssl_context=client_a_overlap,
                ).json("/api/health")
            except WorkerAgentError:
                checks["final_old_identity_rejected"] = "PASS"
            else:
                raise RuntimeError(
                    "old certificate/token remained accepted after cutover"
                )

            for worker_id in worker_ids:
                wait_for_worker(api_b, worker_id)

            payload = {
                "schema_version": 1,
                "kind": "m5stack-worker-fleet-credential-migration",
                "date": "2026-10-24",
                "status": "PASS",
                "validation": "transport-security validation",
                "scope": "same-host-loopback-file-generation-migration",
                "rotation": {
                    "server_certificate": "A-to-B",
                    "client_ca_overlap": "A-and-B",
                    "client_ca_final": "B",
                    "worker_client_certificate": "A-to-B",
                    "worker_server_trust": "A-then-A+B-then-B",
                    "master_token_overlap": "A-and-B",
                    "master_token_final": "B",
                    "server_reload_signal": "SIGHUP",
                    "worker_reload_signal": None,
                    "worker_credential_commit": (
                        "atomic-generation-pointer-replacement"
                    ),
                    "migration": "automatic-on-next-request",
                    "final_cutover": "manual-remove-previous-then-SIGHUP-server",
                },
                "fleet": {
                    "workers": sorted(worker_ids),
                    "receipts": receipts,
                    "credential_fingerprint": expected_fingerprint,
                },
                "checks": checks,
                "not_claimed": [
                    "cross-host network topology",
                    "automated discovery of worker hosts",
                    "production CA or secret-manager integration",
                    "worker or QEMU continuity across restart",
                    "multi-host scheduling",
                    "hardware validation",
                ],
            }
            if not all(value == "PASS" for value in checks.values()):
                raise RuntimeError(f"fleet migration checks incomplete: {checks}")
            write_evidence(args.out, payload)
            print(f"evidence={args.out}")
            print(json.dumps(payload, indent=2))
        except Exception:
            print("--- service log ---", file=sys.stderr)
            print(service_log.read_text(errors="replace")[-4000:], file=sys.stderr)
            for worker_id, log_path in sorted(worker_logs.items()):
                print(f"--- {worker_id} log ---", file=sys.stderr)
                print(log_path.read_text(errors="replace")[-4000:], file=sys.stderr)
            raise
        finally:
            for worker in workers:
                terminate_group(worker)
            terminate_group(service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
