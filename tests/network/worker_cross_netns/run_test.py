#!/usr/bin/env python3
"""Exercise authenticated worker control-plane traffic across network namespaces."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVE = ROOT / "platform/tools/serve.py"
TOOLS = ROOT / "platform/tools"
SERVER_ADDRESS = "10.252.0.1"
WORKER_ADDRESS = "10.252.0.2"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"command failed ({' '.join(command)}): {detail}"
        )
    return completed


def worker_probe(
    work_dir: Path,
    result_path: Path,
    service_url: str,
) -> int:
    from worker_agent import Api, WorkerAgent, initialize_identity

    token = os.environ.get("M5_CROSS_NETNS_TOKEN")
    if not token:
        raise RuntimeError("cross-netns worker token is missing")
    identity = initialize_identity(work_dir, "cross-netns-worker")
    api = Api(service_url, token)
    agent = WorkerAgent(
        api,
        work_dir=work_dir,
        identity=identity,
        capabilities={
            "qemu": False,
            "network_namespace": True,
            "control_plane_only": True,
        },
        heartbeat_interval=2,
    )
    deadline = time.monotonic() + 15
    while True:
        try:
            agent.register()
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
    job = api.json(
        "/api/v1/jobs",
        method="POST",
        payload={
            "label": "cross-netns-control-plane",
            "request": {
                "scope": "transport-only",
                "no_qemu": True,
            },
            "required_capabilities": {
                "network_namespace": True,
                "control_plane_only": True,
            },
            "max_attempts": 1,
            "idempotency_key": f"cross-netns-{secrets.token_hex(8)}",
        },
    )["job"]
    claimed = agent.claim()
    if not isinstance(claimed, dict):
        raise RuntimeError("worker did not claim the submitted job")
    job_id = str(claimed["job_id"])
    lease = claimed.get("lease")
    if not isinstance(lease, dict) or not lease.get("lease_id"):
        raise RuntimeError("claimed job has no lease")
    lease_id = str(lease["lease_id"])
    agent.heartbeat_worker([job_id])
    agent.heartbeat_job(job_id, lease_id)
    evidence = {
        "kind": "cross-netns-control-plane",
        "worker_id": identity["worker_id"],
        "job_id": job_id,
        "request_sha256": claimed["request_sha256"],
        "scope": "transport-only",
    }
    evidence_bytes = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    result = agent.report_result(
        job_id,
        lease_id,
        state="PASS",
        evidence_sha256=evidence_sha256,
        summary={
            "scope": "control-plane-only",
            "qemu_started": False,
            "device_session_created": False,
        },
    )
    agent.stop_worker()
    terminal = api.json(f"/api/v1/jobs/{job_id}")
    payload = {
        "registration": identity,
        "job_submitted": job["job_id"],
        "job_claimed": job_id,
        "lease_id": lease_id,
        "heartbeat": "PASS",
        "result": result["status"],
        "terminal": terminal["job"]["status"],
        "request_sha256": claimed["request_sha256"],
        "evidence_sha256": evidence_sha256,
        "worker_stopped": True,
        "qemu_started": False,
        "device_session_created": False,
    }
    result_path.write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    return 0


class Fabric:
    def __init__(self, out: Path):
        suffix = secrets.token_hex(3)
        self.server_namespace = f"m5cs-{suffix}"
        self.worker_namespace = f"m5cw-{suffix}"
        self.server_interface = f"m5sv-{suffix}"
        self.worker_interface = f"m5wk-{suffix}"
        self.out = out
        self.started = False
        self.processes: list[subprocess.Popen] = []

    def start(self) -> None:
        run(["ip", "netns", "add", self.server_namespace])
        self.started = True
        run(["ip", "netns", "add", self.worker_namespace])
        run(
            [
                "ip",
                "link",
                "add",
                self.server_interface,
                "type",
                "veth",
                "peer",
                "name",
                self.worker_interface,
            ]
        )
        run(
            [
                "ip",
                "link",
                "set",
                self.server_interface,
                "netns",
                self.server_namespace,
            ]
        )
        run(
            [
                "ip",
                "link",
                "set",
                self.worker_interface,
                "netns",
                self.worker_namespace,
            ]
        )
        for namespace, interface, address in (
            (
                self.server_namespace,
                self.server_interface,
                f"{SERVER_ADDRESS}/30",
            ),
            (
                self.worker_namespace,
                self.worker_interface,
                f"{WORKER_ADDRESS}/30",
            ),
        ):
            run(
                [
                    "ip",
                    "netns",
                    "exec",
                    namespace,
                    "ip",
                    "link",
                    "set",
                    "lo",
                    "up",
                ]
            )
            run(
                [
                    "ip",
                    "netns",
                    "exec",
                    namespace,
                    "ip",
                    "addr",
                    "add",
                    address,
                    "dev",
                    interface,
                ]
            )
            run(
                [
                    "ip",
                    "netns",
                    "exec",
                    namespace,
                    "ip",
                    "link",
                    "set",
                    interface,
                    "up",
                ]
            )

    def close(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self.started:
            for namespace in (
                self.server_namespace,
                self.worker_namespace,
            ):
                run(["ip", "netns", "delete", namespace], check=False)
        self.started = False

    def __enter__(self) -> Fabric:
        try:
            self.start()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--service-url")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--worker-result", type=Path)
    args = parser.parse_args()
    if args.worker:
        if (
            args.work_dir is None
            or args.worker_result is None
            or not args.service_url
        ):
            parser.error(
                "--worker requires --work-dir, --worker-result and "
                "--service-url"
            )
        args.work_dir.mkdir(parents=True, exist_ok=True)
        return worker_probe(
            args.work_dir.resolve(),
            args.worker_result.resolve(),
            args.service_url,
        )
    if args.out_dir is None:
        parser.error("--out-dir is required")
    if sys.platform != "linux":
        parser.error("cross-namespace worker fixture requires Linux")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    temporary_state = tempfile.TemporaryDirectory(
        prefix="m5-worker-cross-state-"
    )
    temporary_root = Path(temporary_state.name)
    state_dir = temporary_root / "service-state"
    state_dir.mkdir()
    worker_work_dir = temporary_root / "worker-state"
    worker_result_path = temporary_root / "worker-result.json"
    port = free_port()
    token = secrets.token_urlsafe(32)
    service_url = f"http://{SERVER_ADDRESS}:{port}"
    started = time.monotonic()
    server_stderr_path = temporary_root / "server.stderr"
    server_stdout_path = temporary_root / "server.stdout"
    worker_stdout_path = temporary_root / "worker.stdout"
    worker_stderr_path = temporary_root / "worker.stderr"
    server_stderr = server_stderr_path.open("w")
    server_stdout = server_stdout_path.open("w")
    worker_stdout = worker_stdout_path.open("w")
    worker_stderr = worker_stderr_path.open("w")
    fabric = Fabric(out)
    server = None
    worker = None
    try:
        with fabric:
            environment = os.environ.copy()
            environment["M5_SERVICE_API_TOKEN"] = token
            server = subprocess.Popen(
                [
                    "ip",
                    "netns",
                    "exec",
                    fabric.server_namespace,
                    sys.executable,
                    str(SERVE),
                    str(port),
                    "--bind",
                    SERVER_ADDRESS,
                    "--state-dir",
                    str(state_dir),
                    "--worker-id",
                    "cross-netns-server",
                ],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=server_stdout,
                stderr=server_stderr,
                text=True,
            )
            fabric.processes.append(server)
            worker_environment = environment.copy()
            for proxy_name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                worker_environment.pop(proxy_name, None)
            worker_environment["NO_PROXY"] = "*"
            worker_environment["no_proxy"] = "*"
            worker_environment["PYTHONPATH"] = str(TOOLS)
            worker_environment["M5_CROSS_NETNS_TOKEN"] = token
            worker = subprocess.Popen(
                [
                    "ip",
                    "netns",
                    "exec",
                    fabric.worker_namespace,
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--out-dir",
                    str(out),
                    "--service-url",
                    service_url,
                    "--work-dir",
                    str(worker_work_dir),
                    "--worker-result",
                    str(worker_result_path),
                ],
                cwd=ROOT,
                env=worker_environment,
                stdin=subprocess.DEVNULL,
                stdout=worker_stdout,
                stderr=worker_stderr,
                text=True,
            )
            fabric.processes.append(worker)
            worker.wait(timeout=30)
            worker_result = (
                json.loads(worker_result_path.read_text())
                if worker_result_path.is_file()
                else {}
            )
            routes = run(
                [
                    "ip",
                    "netns",
                    "exec",
                    fabric.worker_namespace,
                    "ip",
                    "route",
                    "get",
                    SERVER_ADDRESS,
                ],
                check=False,
            )
    finally:
        server_stdout.close()
        server_stderr.close()
        worker_stdout.close()
        worker_stderr.close()
    namespaces = run(["ip", "netns", "list"], check=False)
    server_log = (
        server_stdout_path.read_text(errors="replace")
        + server_stderr_path.read_text(errors="replace")
    )
    worker_log = (
        worker_stdout_path.read_text(errors="replace")
        + worker_stderr_path.read_text(errors="replace")
    )
    checks = {
        "worker_exit_zero": worker is not None and worker.returncode == 0,
        "server_terminated_after_test": (
            server is not None and server.poll() is not None
        ),
        "worker_route_uses_veth": fabric.worker_interface in routes.stdout,
        "registration_recorded": bool(
            worker_result.get("registration", {}).get("worker_id")
        ),
        "job_submitted": bool(worker_result.get("job_submitted")),
        "job_claimed": (
            worker_result.get("job_submitted")
            == worker_result.get("job_claimed")
        ),
        "worker_and_job_heartbeat": worker_result.get("heartbeat") == "PASS",
        "terminal_pass": (
            worker_result.get("result") == "completed"
            and worker_result.get("terminal") == "completed"
        ),
        "worker_stopped": worker_result.get("worker_stopped") is True,
        "no_qemu_started": worker_result.get("qemu_started") is False,
        "no_device_session_created": (
            worker_result.get("device_session_created") is False
        ),
        "namespaces_cleaned": (
            fabric.server_namespace not in namespaces.stdout
            and fabric.worker_namespace not in namespaces.stdout
        ),
        "token_not_logged": token not in server_log and token not in worker_log,
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-worker-cross-network-namespace",
        "date": "2026-10-24",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "worker-control-plane-only-not-qemu-executor-or-hardware",
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "result": {
            "worker_id": "cross-netns-worker",
            "instance_id_present": bool(
                worker_result.get("registration", {}).get("instance_id")
            ),
            "job_id_present": bool(worker_result.get("job_claimed")),
            "lease_id_present": bool(worker_result.get("lease_id")),
            "request_sha256_present": bool(
                worker_result.get("request_sha256")
            ),
            "result_evidence_sha256_present": bool(
                worker_result.get("evidence_sha256")
            ),
            "terminal": worker_result.get("terminal"),
        },
        "route": {"server_reachable": SERVER_ADDRESS in routes.stdout},
        "not_claimed": [
            "cross-host QEMU execution",
            "companion or evidence-stream continuity",
            "cross-host process reattach",
            "multi-host production scheduling",
            "physical hardware"
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    temporary_state.cleanup()
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
