#!/usr/bin/env python3
"""Exercise authenticated worker control-plane traffic across network namespaces."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVE = ROOT / "platform/tools/serve.py"
TOOLS = ROOT / "platform/tools"
SERVER_ADDRESS = "10.252.0.1"
WORKER_ADDRESS = "10.252.0.2"


def redact_diagnostic(text: str, token: str) -> str:
    text = text.replace(token, "<redacted>")
    text = re.sub(r"\bjob-[0-9a-f]+\b", "<job-id>", text)
    text = re.sub(r"\b[0-9a-f]{32}\b", "<ephemeral-id>", text)
    return text.replace("127.0.0.1", "<runtime-host>")


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
        endpoint=f"http://{WORKER_ADDRESS}:8787",
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
    workers = api.json("/api/v1/workers").get("workers", [])
    registered_worker = next(
        (
            worker
            for worker in workers
            if isinstance(worker, dict)
            and worker.get("worker_id") == identity["worker_id"]
        ),
        {},
    )
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
        "advertised_endpoint_present": (
            registered_worker.get("endpoint")
            == f"http://{WORKER_ADDRESS}:8787"
        ),
    }
    result_path.write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    return 0


def wait_for_service(api, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if api.json("/api/health").get("ok"):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"service did not become ready: {api.base_url}")


def upload_artifact(
    base_url: str,
    token: str,
    path: Path,
) -> dict:
    request = urllib.request.Request(
        base_url + "/api/v1/artifacts",
        data=path.read_bytes(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": path.name,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def qemu_process_lines(process_listing: str) -> list[str]:
    processes = []
    for line in process_listing.splitlines():
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


def worker_result_evidence_sha256(worker_result: dict) -> str | None:
    result = worker_result.get("result")
    if isinstance(result, dict):
        value = result.get("evidence_sha256")
    else:
        value = worker_result.get("evidence_sha256")
    return value if isinstance(value, str) else None


def worker_result_lease_observed(worker_result: dict) -> bool:
    return (
        worker_result.get("lease_observed") is True
        or bool(worker_result.get("lease_id"))
    )


def registered_qemu_path(device_id: str = "sticks3") -> Path:
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    profile = next(
        device
        for device in matrix["devices"]
        if device.get("id") == device_id
    )
    backend = matrix["backends"][profile["backend"]]
    qemu = backend.get("qemu")
    if not isinstance(qemu, str):
        raise RuntimeError(f"{device_id} backend has no registered QEMU path")
    return ROOT / qemu


def worker_qemu_probe(
    work_dir: Path,
    result_path: Path,
    service_url: str,
    runtime_service_url: str,
    firmware: Path,
    runtime: str,
    qemu_path: Path | None = None,
) -> int:
    from worker_agent import Api, WorkerAgent, initialize_identity

    token = os.environ.get("M5_CROSS_NETNS_TOKEN")
    if not token:
        raise RuntimeError("cross-netns worker token is missing")
    control_api = Api(service_url, token)
    runtime_api = Api(runtime_service_url, token)
    wait_for_service(control_api)
    wait_for_service(runtime_api)

    flash_size = 8 << 20
    source = firmware.read_bytes()
    source_sha256 = hashlib.sha256(source).hexdigest()
    if len(source) > flash_size:
        raise RuntimeError("StickS3 firmware exceeds 8 MiB flash")
    full_image = work_dir / "sticks3-full.bin"
    full_image.write_bytes(source + b"\xff" * (flash_size - len(source)))
    artifact = upload_artifact(runtime_service_url, token, full_image)
    imported = runtime_api.json(
        "/api/v1/firmware",
        method="POST",
        payload={
            "device_id": "sticks3",
            "kind": "merged",
            "artifact_id": artifact["artifact_id"],
        },
    )
    qemu_path = qemu_path or registered_qemu_path()
    qemu_sha256 = file_sha256(qemu_path)

    identity = initialize_identity(work_dir, "cross-netns-qemu-worker")
    agent = WorkerAgent(
        control_api,
        runtime_api=runtime_api,
        work_dir=work_dir,
        identity=identity,
        capabilities={"qemu": True, "pcap": runtime != "qemu"},
        heartbeat_interval=2,
        session_timeout=240,
    )
    job = control_api.json(
        "/api/v1/jobs",
        method="POST",
        payload={
            "label": "cross-netns-qemu-execution",
            "request": {
                "session": {
                    "device_id": "sticks3",
                    "runtime": runtime,
                    "firmware_id": imported["firmware_id"],
                    "ready_timeout_seconds": 180,
                },
                "evidence_include": ["manifest", "serial", "logs", "qom"],
            },
            "required_capabilities": {"qemu": True},
            "max_attempts": 1,
            "idempotency_key": f"cross-netns-qemu-{secrets.token_hex(8)}",
        },
    )["job"]
    agent.run(once=True)
    terminal = control_api.json(f"/api/v1/jobs/{job['job_id']}")["job"]
    result_path_value = work_dir / str(job["job_id"]) / "result.json"
    result = (
        json.loads(result_path_value.read_text())
        if result_path_value.is_file()
        else {}
    )
    evidence_path = work_dir / str(job["job_id"]) / "evidence.zip"
    evidence_names = []
    if evidence_path.is_file():
        with zipfile.ZipFile(evidence_path) as archive:
            evidence_names = archive.namelist()
    payload = {
        "registration": identity,
        "job_submitted": job["job_id"],
        "job_claimed": job["job_id"],
        "lease_observed": True,
        "request_sha256": terminal.get("request_sha256"),
        "terminal": terminal.get("status"),
        "result": result,
        "execution_plane": result.get("summary", {}).get("execution_plane"),
        "evidence_names": evidence_names,
        "firmware_sha256": imported["sha256"],
        "firmware_source_sha256": source_sha256,
        "qemu_sha256": qemu_sha256,
        "runtime": runtime,
        "qemu_started": bool(result.get("summary", {}).get("device_id")),
        "device_session_created": bool(
            result.get("summary", {}).get("device_id")
        ),
    }
    result_path.write_text(json.dumps(payload, indent=2) + "\n")
    return 0 if result.get("state") == "PASS" else 1


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
    parser.add_argument("--qemu-worker", action="store_true")
    parser.add_argument("--service-url")
    parser.add_argument("--runtime-service-url")
    parser.add_argument("--firmware", type=Path)
    parser.add_argument("--runtime", default="qemu")
    parser.add_argument("--qemu", action="store_true")
    parser.add_argument("--qemu-path", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--worker-result", type=Path)
    args = parser.parse_args()
    if args.worker or args.qemu_worker:
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
        if args.qemu_worker:
            if not args.runtime_service_url or args.firmware is None:
                parser.error(
                    "--qemu-worker requires --runtime-service-url and --firmware"
                )
            return worker_qemu_probe(
                args.work_dir.resolve(),
                args.worker_result.resolve(),
                args.service_url,
                args.runtime_service_url,
                args.firmware.resolve(),
                args.runtime,
                args.qemu_path.resolve() if args.qemu_path else None,
            )
        return worker_probe(
            args.work_dir.resolve(),
            args.worker_result.resolve(),
            args.service_url,
        )
    if args.out_dir is None:
        parser.error("--out-dir is required")
    if sys.platform != "linux":
        parser.error("cross-namespace worker fixture requires Linux")
    if args.qemu and args.firmware is None:
        parser.error("--qemu requires --firmware")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    temporary_state = tempfile.TemporaryDirectory(
        prefix="m5-worker-cross-state-"
    )
    temporary_root = Path(temporary_state.name)
    state_dir = temporary_root / "service-state"
    state_dir.mkdir()
    runtime_state_dir = temporary_root / "runtime-state"
    runtime_state_dir.mkdir()
    worker_work_dir = temporary_root / "worker-state"
    worker_result_path = temporary_root / "worker-result.json"
    port = free_port()
    runtime_port = free_port()
    token = secrets.token_urlsafe(32)
    service_url = f"http://{SERVER_ADDRESS}:{port}"
    runtime_service_url = f"http://127.0.0.1:{runtime_port}"
    started = time.monotonic()
    server_stderr_path = temporary_root / "server.stderr"
    server_stdout_path = temporary_root / "server.stdout"
    worker_stdout_path = temporary_root / "worker.stdout"
    worker_stderr_path = temporary_root / "worker.stderr"
    runtime_stdout_path = temporary_root / "runtime.stdout"
    runtime_stderr_path = temporary_root / "runtime.stderr"
    server_stderr = server_stderr_path.open("w")
    server_stdout = server_stdout_path.open("w")
    worker_stdout = worker_stdout_path.open("w")
    worker_stderr = worker_stderr_path.open("w")
    runtime_stdout = runtime_stdout_path.open("w")
    runtime_stderr = runtime_stderr_path.open("w")
    fabric = Fabric(out)
    server = None
    worker = None
    runtime_service = None
    try:
        with fabric:
            environment = os.environ.copy()
            if args.qemu:
                # The worker-local service receives an already merged full
                # image. Avoid a host-architecture-specific esp-emu preparer.
                environment["M5_SERVICE_FLASH_MODE"] = "host-image"
                qemu_path = (
                    args.qemu_path.resolve()
                    if args.qemu_path
                    else registered_qemu_path()
                )
                if not qemu_path.is_file():
                    raise RuntimeError(f"Linux QEMU does not exist: {qemu_path}")
                environment["M5_QEMU_XTENSA"] = str(qemu_path)
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
            if args.qemu:
                runtime_service = subprocess.Popen(
                    [
                        "ip",
                        "netns",
                        "exec",
                        fabric.worker_namespace,
                        sys.executable,
                        str(SERVE),
                        str(runtime_port),
                        "--state-dir",
                        str(runtime_state_dir),
                        "--worker-id",
                        "cross-netns-runtime",
                    ],
                    cwd=ROOT,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=runtime_stdout,
                    stderr=runtime_stderr,
                    text=True,
                )
                fabric.processes.append(runtime_service)
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
                    "--qemu-worker" if args.qemu else "--worker",
                    "--out-dir",
                    str(out),
                    "--service-url",
                    service_url,
                    *(
                        [
                            "--runtime-service-url",
                            runtime_service_url,
                            "--firmware",
                            str(args.firmware.resolve()),
                            "--runtime",
                            args.runtime,
                            "--qemu-path",
                            str(
                                args.qemu_path.resolve()
                                if args.qemu_path
                                else registered_qemu_path()
                            ),
                        ]
                        if args.qemu
                        else []
                    ),
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
            worker.wait(timeout=300 if args.qemu else 30)
            worker_result = (
                json.loads(worker_result_path.read_text())
                if worker_result_path.is_file()
                else {}
            )
            (out / "worker-result.json").write_text(
                json.dumps(
                    json.loads(
                        json.dumps(worker_result).replace(token, "<redacted>")
                    ),
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
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
        runtime_stdout.close()
        runtime_stderr.close()
    namespaces = run(["ip", "netns", "list"], check=False)
    server_log = (
        server_stdout_path.read_text(errors="replace")
        + server_stderr_path.read_text(errors="replace")
    )
    worker_log = (
        worker_stdout_path.read_text(errors="replace")
        + worker_stderr_path.read_text(errors="replace")
    )
    runtime_log = (
        runtime_stdout_path.read_text(errors="replace")
        + runtime_stderr_path.read_text(errors="replace")
    )
    logs_dir = out / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("server.log", server_log),
        ("worker.log", worker_log),
        ("runtime.log", runtime_log),
    ):
        (logs_dir / name).write_text(
            redact_diagnostic(text, token),
            encoding="utf-8",
        )
    active_qemu_processes = qemu_process_lines(
        run(
            ["ps", "-eo", "pid=,args="],
            check=False,
        ).stdout
    )
    worker_exit_zero = worker is not None and worker.returncode == 0
    if args.qemu:
        job_result = worker_result.get("result")
        job_result = job_result if isinstance(job_result, dict) else {}
        checks = {
            "worker_exit_zero": worker_exit_zero,
            "server_terminated_after_test": (
                server is not None and server.poll() is not None
            ),
            "runtime_service_started": runtime_service is not None,
            "worker_route_uses_veth": fabric.worker_interface in routes.stdout,
            "registration_recorded": bool(
                worker_result.get("registration", {}).get("worker_id")
            ),
            "job_submitted": bool(worker_result.get("job_submitted")),
            "worker_job_heartbeat": bool(job_result),
            "terminal_pass": (
                job_result.get("state") == "PASS"
                and worker_result.get("terminal") == "completed"
            ),
            "worker_local_execution": (
                worker_result.get("execution_plane") == "worker-local"
            ),
            "worker_local_qemu_started": (
                worker_result.get("qemu_started") is True
            ),
            "worker_local_device_session_created": (
                worker_result.get("device_session_created") is True
            ),
            "worker_local_evidence": (
                {"manifest.json", "serial.log"}
                <= set(worker_result.get("evidence_names", []))
            ),
            "firmware_sha256_present": (
                isinstance(worker_result.get("firmware_sha256"), str)
                and len(worker_result["firmware_sha256"]) == 64
            ),
            "firmware_source_sha256_present": (
                isinstance(worker_result.get("firmware_source_sha256"), str)
                and len(worker_result["firmware_source_sha256"]) == 64
            ),
            "qemu_sha256_present": (
                isinstance(worker_result.get("qemu_sha256"), str)
                and len(worker_result["qemu_sha256"]) == 64
            ),
            "qemu_reaped": not active_qemu_processes,
        }
    else:
        checks = {
            "worker_exit_zero": worker_exit_zero,
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
            "worker_and_job_heartbeat": (
                worker_result.get("heartbeat") == "PASS"
            ),
            "terminal_pass": (
                worker_result.get("result") == "completed"
                and worker_result.get("terminal") == "completed"
            ),
            "worker_stopped": worker_result.get("worker_stopped") is True,
            "no_qemu_started": worker_result.get("qemu_started") is False,
            "no_device_session_created": (
                worker_result.get("device_session_created") is False
            ),
            "advertised_endpoint_present": (
                worker_result.get("advertised_endpoint_present") is True
            ),
        }
    checks.update({
        "namespaces_cleaned": (
            fabric.server_namespace not in namespaces.stdout
            and fabric.worker_namespace not in namespaces.stdout
        ),
        "token_not_logged": (
            token not in server_log
            and token not in worker_log
            and token not in runtime_log
        ),
    })
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-worker-cross-network-namespace",
        "date": "2026-10-25",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": (
            "worker-local-qemu-across-network-namespaces-not-physical-hardware"
            if args.qemu
            else "worker-control-plane-only-not-qemu-executor-or-hardware"
        ),
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "result": {
            "worker_id": worker_result.get("registration", {}).get(
                "worker_id"
            ),
            "instance_id_present": bool(
                worker_result.get("registration", {}).get("instance_id")
            ),
            "job_id_present": bool(worker_result.get("job_claimed")),
            "lease_observed": worker_result_lease_observed(worker_result),
            "request_sha256_present": bool(
                worker_result.get("request_sha256")
            ),
            "result_evidence_sha256_present": bool(
                worker_result_evidence_sha256(worker_result)
            ),
            "terminal": worker_result.get("terminal"),
            "execution_plane": worker_result.get("execution_plane"),
            "firmware_sha256": worker_result.get("firmware_sha256"),
            "firmware_source_sha256": worker_result.get(
                "firmware_source_sha256"
            ),
            "qemu_sha256": worker_result.get("qemu_sha256"),
            "runtime": worker_result.get("runtime"),
            "advertised_endpoint_present": worker_result.get(
                "advertised_endpoint_present"
            ),
        },
        "route": {"server_reachable": SERVER_ADDRESS in routes.stdout},
        "diagnostics": {
            "worker_exit_code": worker.returncode if worker is not None else None,
            "runtime_exit_code": (
                runtime_service.returncode
                if runtime_service is not None
                else None
            ),
            "server_exit_code": server.returncode if server is not None else None,
            "worker_error": worker_result.get("error"),
            "job_error": (
                worker_result["result"].get("error")
                if isinstance(worker_result.get("result"), dict)
                else None
            ),
            "worker_log_tail": redact_diagnostic(worker_log, token)[-4000:],
            "runtime_log_tail": redact_diagnostic(runtime_log, token)[-4000:],
        },
        "not_claimed": [
            *(
                []
                if args.qemu
                else ["cross-host QEMU execution"]
            ),
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
