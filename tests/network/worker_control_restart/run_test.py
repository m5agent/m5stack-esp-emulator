#!/usr/bin/env python3
"""Prove a worker job survives a central control-plane restart."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"
WORKER = ROOT / "platform/tools/worker_agent.py"


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
    timeout: float = 15,
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
    output, _ = process.communicate(timeout=20)
    return output or ""


def wait_job(
    base_url: str,
    token: str,
    job_id: str,
    *,
    statuses: set[str],
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            latest = request_json(
                base_url + f"/api/v1/jobs/{job_id}",
                token,
            )["job"]
            if latest.get("status") in statuses:
                return latest
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.05)
    raise RuntimeError(f"job did not reach {sorted(statuses)}: {latest}")


def qemu_processes() -> list[str]:
    listing = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        text=True,
        capture_output=True,
        check=False,
    ).stdout
    processes = []
    for line in listing.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        try:
            argv = shlex.split(fields[1])
        except ValueError:
            continue
        if argv and Path(argv[0]).name.startswith("qemu-system-"):
            processes.append(line)
    return processes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    control_port = free_port()
    runtime_port = free_port()
    control_url = f"http://127.0.0.1:{control_port}"
    runtime_url = f"http://127.0.0.1:{runtime_port}"
    token = secrets.token_hex(32)
    token_file = args.out_dir / "service.token"
    token_file.write_text(token + "\n")
    token_file.chmod(0o600)

    control = start_service(
        port=control_port,
        state_dir=args.out_dir / "control-state",
        token_file=token_file,
    )
    runtime = start_service(
        port=runtime_port,
        state_dir=args.out_dir / "runtime-state",
        token_file=token_file,
    )
    control_logs: list[str] = []
    runtime_logs: list[str] = []
    worker_log = ""
    restarted_control = None
    try:
        wait_health(control_url, control)
        wait_health(runtime_url, runtime)
        submitted = request_json(
            control_url + "/api/v1/jobs",
            token,
            method="POST",
            payload={
                "label": "control-restart-continuity",
                "request": {
                    "session": {
                        "device_id": "sticks3",
                        "runtime": "qemu",
                        "ready_timeout_seconds": 120,
                    },
                    "evidence_include": [
                        "manifest",
                        "serial",
                        "logs",
                        "qom",
                    ],
                },
                "required_capabilities": {"qemu": True},
                "max_attempts": 1,
                "idempotency_key": "control-restart-continuity",
            },
        )["job"]
        job_id = str(submitted["job_id"])
        worker = subprocess.Popen(
            [
                sys.executable,
                str(WORKER),
                "--service-url",
                control_url,
                "--runtime-service-url",
                runtime_url,
                "--token-file",
                str(token_file),
                "--worker-id",
                "restart-survivor",
                "--work-dir",
                str(args.out_dir / "worker"),
                "--poll-seconds",
                "0.1",
                "--heartbeat-interval",
                "1",
                "--control-reconnect-timeout",
                "30",
                "--session-timeout",
                "150",
                "--once",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        claimed = wait_job(
            control_url,
            token,
            job_id,
            statuses={"leased"},
            timeout=15,
        )
        lease_id = str((claimed.get("lease") or {}).get("lease_id") or "")
        claimed_worker = {
            key: (claimed.get("lease") or {}).get(key)
            for key in ("worker_id", "instance_id", "generation")
        }
        control_logs.append(stop_service(control))
        time.sleep(2.2)
        restarted_control = start_service(
            port=control_port,
            state_dir=args.out_dir / "control-state",
            token_file=token_file,
        )
        wait_health(control_url, restarted_control)
        worker_output, _ = worker.communicate(timeout=180)
        worker_log = worker_output or ""
        terminal = wait_job(
            control_url,
            token,
            job_id,
            statuses={"completed", "failed", "cancelled"},
            timeout=30,
        )
        runtime_sessions = request_json(
            runtime_url + "/api/v1/sessions",
            token,
        )["sessions"]
        workers = request_json(
            control_url + "/api/v1/workers",
            token,
        )["workers"]
        restarted_worker = next(
            (
                item
                for item in workers
                if item.get("worker_id") == "restart-survivor"
            ),
            {},
        )
        evidence_path = args.out_dir / "worker" / job_id / "evidence.zip"
        terminal_worker = (
            (terminal.get("result") or {}).get("worker") or {}
        )
        leaked_qemu = qemu_processes()
        checks = {
            "job_claimed_before_restart": claimed.get("status") == "leased",
            "lease_id_present": bool(lease_id),
            "worker_reconnected": (
                "worker control plane unavailable; retrying" in worker_log
                and "worker control plane reconnected" in worker_log
            ),
            "worker_exit_zero": worker.returncode == 0,
            "terminal_completed": terminal.get("status") == "completed",
            "terminal_pass": (
                (terminal.get("result") or {}).get("state") == "PASS"
            ),
            "same_lease": (
                str((terminal.get("result") or {}).get("lease_id") or "")
                == lease_id
            ),
            "same_worker_generation": (
                all(
                    terminal_worker.get(key) == value
                    for key, value in claimed_worker.items()
                )
            ),
            "worker_stopped_after_result": (
                restarted_worker.get("state") == "stopped"
            ),
            "evidence_zip_present": evidence_path.is_file(),
            "runtime_session_stopped": (
                len(runtime_sessions) == 1
                and runtime_sessions[0].get("state") == "stopped"
            ),
            "qemu_process_absent_after_cleanup": not leaked_qemu,
            "token_absent_from_worker_log": token not in worker_log,
        }
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-worker-control-plane-restart-continuity",
            "date": "2026-10-25",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": "virtual-device-control-plane-restart-not-hardware",
            "control_plane": {
                "initial_url": control_url,
                "restart_downtime_seconds": 2.2,
                "restart_reused_state": True,
            },
            "job": {
                "job_id": job_id,
                "lease_id": lease_id,
                "worker_identity": claimed_worker,
                "status": terminal.get("status"),
                "result_state": (terminal.get("result") or {}).get("state"),
            },
            "worker": {
                "worker_id": "restart-survivor",
                "returncode": worker.returncode,
                "state_after_result": restarted_worker.get("state"),
            },
            "evidence": {
                "zip_present": evidence_path.is_file(),
                "bytes": evidence_path.stat().st_size if evidence_path.is_file() else 0,
                "sha256": (
                    hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                    if evidence_path.is_file()
                    else None
                ),
            },
            "checks": checks,
            "not_claimed": [
                "cross-host QEMU process migration",
                "runtime service restart",
                "companion HTTP/BLE helper continuity",
                "production multi-host scheduler",
                "physical hardware validation",
            ],
        }
        (args.out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        control_logs.append(stop_service(control))
        if restarted_control is not None:
            control_logs.append(stop_service(restarted_control))
        runtime_logs.append(stop_service(runtime))
        token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
