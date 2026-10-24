#!/usr/bin/env python3
"""Exercise authenticated worker discovery with a real service and WorkerAgent."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"
WORKER = ROOT / "platform/tools/worker_agent.py"
GROUP = "239.255.77.77"


def free_port(kind: int) -> int:
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def api_json(url: str, token: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def wait_health(url: str, process: subprocess.Popen[str], timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"service exited before health: {output[-2000:]}")
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                if json.loads(response.read()).get("ok"):
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("service did not become healthy")


def run_worker(
    *,
    token_file: Path,
    work_dir: Path,
    worker_id: str,
    discovery_port: int,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(WORKER),
        "--discover-control",
        "--discover-control-group",
        GROUP,
        "--discover-control-port",
        str(discovery_port),
        "--discover-control-timeout",
        str(timeout),
        "--token-file",
        str(token_file),
        "--worker-id",
        worker_id,
        "--work-dir",
        str(work_dir),
        "--poll-seconds",
        "0.1",
        "--heartbeat-interval",
        "1",
        "--once",
    ]
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout + 15,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    service_port = free_port(socket.SOCK_STREAM)
    discovery_port = free_port(socket.SOCK_DGRAM)
    base_url = f"http://127.0.0.1:{service_port}"
    token = secrets.token_hex(32)
    rotated_token = secrets.token_hex(32)
    wrong_token = secrets.token_hex(32)
    token_file = args.out_dir / "service.token"
    old_token_file = args.out_dir / "old.token"
    wrong_token_file = args.out_dir / "wrong.token"
    token_file.write_text(token + "\n")
    old_token_file.write_text(token + "\n")
    wrong_token_file.write_text(wrong_token + "\n")
    token_file.chmod(0o600)
    old_token_file.chmod(0o600)
    wrong_token_file.chmod(0o600)

    state_dir = args.out_dir / "service-state"
    service_command = [
        sys.executable,
        str(SERVICE),
        str(service_port),
        "--bind",
        "127.0.0.1",
        "--state-dir",
        str(state_dir),
        "--api-token-file",
        str(token_file),
        "--worker-discovery-group",
        GROUP,
        "--worker-discovery-port",
        str(discovery_port),
        "--worker-discovery-advertise-url",
        base_url,
        "--worker-discovery-interval",
        "0.2",
        "--worker-discovery-ttl",
        "2",
    ]
    service = subprocess.Popen(
        service_command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    service_log_lines: list[str] = []

    def consume_service_log() -> None:
        if service.stdout is None:
            return
        for line in service.stdout:
            service_log_lines.append(line)

    log_reader = threading.Thread(target=consume_service_log, daemon=True)
    log_reader.start()
    try:
        wait_health(base_url, service)
        good = run_worker(
            token_file=token_file,
            work_dir=args.out_dir / "worker-good",
            worker_id="discovered-bootstrap-worker",
            discovery_port=discovery_port,
            timeout=8,
        )
        bad = run_worker(
            token_file=wrong_token_file,
            work_dir=args.out_dir / "worker-wrong-token",
            worker_id="wrong-token-worker",
            discovery_port=discovery_port,
            timeout=2,
        )
        token_file.write_text(rotated_token + "\n")
        service.send_signal(signal.SIGHUP)
        rotation_deadline = time.monotonic() + 10
        while True:
            try:
                api_json(base_url + "/api/v1/workers", rotated_token)
                break
            except Exception:
                if time.monotonic() >= rotation_deadline:
                    raise
                time.sleep(0.1)
        rotated = run_worker(
            token_file=token_file,
            work_dir=args.out_dir / "worker-rotated",
            worker_id="rotated-discovery-worker",
            discovery_port=discovery_port,
            timeout=8,
        )
        old = run_worker(
            token_file=old_token_file,
            work_dir=args.out_dir / "worker-old-token",
            worker_id="old-token-worker",
            discovery_port=discovery_port,
            timeout=2,
        )
        workers = api_json(
            base_url + "/api/v1/workers",
            rotated_token,
        )["workers"]
        sessions = api_json(
            base_url + "/api/v1/sessions",
            rotated_token,
        )["sessions"]
        good_worker = next(
            (
                worker
                for worker in workers
                if worker.get("worker_id") == "discovered-bootstrap-worker"
            ),
            {},
        )
        wrong_worker_present = any(
            worker.get("worker_id") == "wrong-token-worker"
            for worker in workers
        )
        rotated_worker = next(
            (
                worker
                for worker in workers
                if worker.get("worker_id") == "rotated-discovery-worker"
            ),
            {},
        )
        old_worker_present = any(
            worker.get("worker_id") == "old-token-worker"
            for worker in workers
        )
        good_output = good.stdout + good.stderr
        bad_output = bad.stdout + bad.stderr
        rotated_output = rotated.stdout + rotated.stderr
        old_output = old.stdout + old.stderr
        service_log = "".join(service_log_lines)
        checks = {
            "service_healthy": True,
            "worker_discovered_control_url": (
                f"worker control service discovered: {base_url}"
                in good_output
            ),
            "worker_exit_zero": good.returncode == 0,
            "worker_registered": bool(good_worker),
            "worker_stopped": good_worker.get("state") == "stopped",
            "worker_generation_positive": int(
                good_worker.get("generation") or 0
            ) >= 1,
            "wrong_token_worker_rejected": bad.returncode != 0,
            "wrong_token_worker_not_registered": not wrong_worker_present,
            "rotated_worker_discovered": (
                f"worker control service discovered: {base_url}"
                in rotated_output
            ),
            "rotated_worker_registered": bool(rotated_worker),
            "old_token_worker_rejected": old.returncode != 0,
            "old_token_worker_not_registered": not old_worker_present,
            "token_absent_from_service_log": token not in service_log,
            "token_absent_from_worker_log": token not in good_output,
            "wrong_token_absent": wrong_token not in bad_output,
            "rotated_token_absent": rotated_token not in rotated_output,
            "no_device_session_created": not sessions,
        }
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-worker-discovery-live",
            "date": "2026-10-25",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": "virtual-control-plane-not-hardware",
            "discovery": {
                "group": GROUP,
                "port": discovery_port,
                "service_url": base_url,
                "initial_token_sha256": hashlib.sha256(
                    token.encode()
                ).hexdigest(),
                "rotated_token_sha256": hashlib.sha256(
                    rotated_token.encode()
                ).hexdigest(),
            },
            "worker": {
                "worker_id": "discovered-bootstrap-worker",
                "returncode": good.returncode,
                "state": good_worker.get("state"),
                "generation": good_worker.get("generation"),
            },
            "authentication": {
                "wrong_token_returncode": bad.returncode,
                "wrong_token_worker_registered": wrong_worker_present,
                "wrong_token_error_redacted": bad_output.strip()[-500:],
                "rotation_sighup": "PASS",
                "rotated_worker": {
                    "returncode": rotated.returncode,
                    "state": rotated_worker.get("state"),
                    "generation": rotated_worker.get("generation"),
                },
                "old_token_returncode": old.returncode,
                "old_token_worker_registered": old_worker_present,
                "old_token_error_redacted": old_output.strip()[-500:],
            },
            "checks": checks,
            "not_claimed": [
                "QEMU execution through the discovered control plane",
                "NAT or cross-subnet multicast forwarding",
                "production multi-host scheduling",
                "physical hardware validation",
            ],
        }
        (args.out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        if service.poll() is None:
            service.send_signal(signal.SIGTERM)
        service.wait(timeout=15)
        log_reader.join(timeout=2)
        token_file.unlink(missing_ok=True)
        old_token_file.unlink(missing_ok=True)
        wrong_token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
