#!/usr/bin/env python3
"""Prove fail-closed side-effect fencing during a worker network partition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"
WORKER = ROOT / "platform/tools/worker_agent.py"
RUNTIME = Path(__file__).resolve().parent / "runtime_fixture.py"
SERVER_NS = "m5pf-server"
WORKER_NS = "m5pf-worker"
SERVER_ADDRESS = "10.214.0.1"
WORKER_ADDRESS = "10.214.0.2"
PARTITION_TABLE = "m5pf_partition"
JOB_LEASE_SECONDS = 5
EVIDENCE_DELAY_SECONDS = 8


class FixtureError(RuntimeError):
    pass


def command(
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise FixtureError(
            f"command timed out: {' '.join(arguments[:5])}"
        ) from error


def checked(
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = command(
        arguments,
        input_text=input_text,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-3000:]
        raise FixtureError(
            f"command failed ({result.returncode}): "
            f"{' '.join(arguments[:5])}: {detail}"
        )
    return result


def in_namespace(
    namespace: str,
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 30,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return checked(
        ["ip", "netns", "exec", namespace, *arguments],
        input_text=input_text,
        timeout=timeout,
        env=env,
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_token_file(path: Path, token: str) -> None:
    path.write_text(token + "\n")
    path.chmod(0o600)


def wait_http(
    namespace: str,
    url: str,
    process: subprocess.Popen[str],
    *,
    timeout: float = 20,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise FixtureError("runtime/service exited before HTTP readiness")
        result = command(
            [
                "ip",
                "netns",
                "exec",
                namespace,
                sys.executable,
                "-c",
                (
                    "import sys,urllib.request;"
                    "r=urllib.request.urlopen(sys.argv[1],timeout=1);"
                    "assert r.status==200;r.read()"
                ),
                url,
            ],
            timeout=4,
        )
        if result.returncode == 0:
            return
        time.sleep(0.1)
    raise FixtureError(f"HTTP endpoint did not become ready: {url}")


def api_json(
    namespace: str,
    url: str,
    token_file: Path,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    script = """
import json
import pathlib
import sys
import urllib.request
url, method, token_path = sys.argv[1:4]
payload = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
token = pathlib.Path(token_path).read_text().strip()
data = json.dumps(payload).encode() if payload is not None else None
headers = {"Authorization": "Bearer " + token}
if data is not None:
    headers["Content-Type"] = "application/json"
request = urllib.request.Request(url, data=data, method=method, headers=headers)
with urllib.request.urlopen(request, timeout=10) as response:
    print(response.read().decode())
"""
    args = [
        "ip",
        "netns",
        "exec",
        namespace,
        sys.executable,
        "-c",
        script,
        url,
        method,
        str(token_file),
    ]
    if payload is not None:
        args.append(json.dumps(payload))
    result = command(args, timeout=15)
    if result.returncode != 0:
        raise FixtureError(
            f"API request failed: {result.stderr.strip()[-2000:]}"
        )
    return json.loads(result.stdout)


def poll_job(
    url: str,
    token_file: Path,
    job_id: str,
    predicate,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = api_json(
            SERVER_NS,
            f"{url}/api/v1/jobs/{job_id}",
            token_file,
        )["job"]
        if predicate(latest):
            return latest
        time.sleep(0.2)
    raise FixtureError(f"job did not reach expected state: {latest}")


def read_runtime_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def wait_runtime_session(
    path: Path,
    predicate,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = read_runtime_state(path)
        sessions = latest.get("sessions")
        if isinstance(sessions, dict):
            rows = [
                row
                for row in sessions.values()
                if isinstance(row, dict) and predicate(row)
            ]
            if rows:
                return rows[-1]
        time.sleep(0.1)
    raise FixtureError(f"runtime session did not reach expected state: {latest}")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class NamespaceFixture:
    def __init__(self) -> None:
        self.routes: dict[str, str] = {}

    def run(self, namespace: str, arguments: list[str]) -> str:
        return in_namespace(namespace, arguments).stdout.strip()

    def up(self) -> None:
        self.cleanup()
        for namespace in (SERVER_NS, WORKER_NS):
            checked(["ip", "netns", "add", namespace])
        checked(
            [
                "ip",
                "link",
                "add",
                "pf-server",
                "type",
                "veth",
                "peer",
                "name",
                "pf-worker",
            ]
        )
        checked(["ip", "link", "set", "pf-server", "netns", SERVER_NS])
        checked(["ip", "link", "set", "pf-worker", "netns", WORKER_NS])
        for namespace, interface, address in (
            (SERVER_NS, "pf-server", f"{SERVER_ADDRESS}/24"),
            (WORKER_NS, "pf-worker", f"{WORKER_ADDRESS}/24"),
        ):
            self.run(namespace, ["ip", "link", "set", "lo", "up"])
            self.run(
                namespace,
                ["ip", "addr", "add", address, "dev", interface],
            )
            self.run(namespace, ["ip", "link", "set", interface, "up"])
        self.routes = {
            "server": self.run(
                SERVER_NS,
                ["ip", "route", "get", WORKER_ADDRESS],
            ),
            "worker": self.run(
                WORKER_NS,
                ["ip", "route", "get", SERVER_ADDRESS],
            ),
        }

    def down(self) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        for namespace in (SERVER_NS, WORKER_NS):
            command(["ip", "netns", "delete", namespace], timeout=15)

    def namespaces(self) -> str:
        return checked(["ip", "netns", "list"]).stdout


def partition_network(control_port: int) -> None:
    script = (
        f"table inet {PARTITION_TABLE} {{\n"
        "  chain output {\n"
        "    type filter hook output priority 0; policy accept;\n"
        f"    ip daddr {SERVER_ADDRESS} tcp dport {control_port} drop\n"
        "  }\n"
        "}\n"
    )
    in_namespace(WORKER_NS, ["nft", "-f", "-"], input_text=script)


def restore_network() -> None:
    command(
        [
            "ip",
            "netns",
            "exec",
            WORKER_NS,
            "nft",
            "delete",
            "table",
            "inet",
            PARTITION_TABLE,
        ],
        timeout=15,
    )


def worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    environment["NO_PROXY"] = "*"
    environment["no_proxy"] = "*"
    environment["PYTHONPATH"] = str(ROOT / "platform/tools")
    return environment


def worker_command(
    *,
    service_url: str,
    runtime_url: str,
    token_file: Path,
    work_dir: Path,
    worker_id: str,
) -> list[str]:
    return [
        "ip",
        "netns",
        "exec",
        WORKER_NS,
        sys.executable,
        "-u",
        str(WORKER),
        "--service-url",
        service_url,
        "--runtime-service-url",
        runtime_url,
        "--token-file",
        str(token_file),
        "--worker-id",
        worker_id,
        "--work-dir",
        str(work_dir),
        "--poll-seconds",
        "0.1",
        "--heartbeat-interval",
        "0.2",
        "--control-reconnect-timeout",
        "1",
        "--runtime-reconnect-timeout",
        "1",
        "--once",
    ]


def run_worker(
    *,
    service_url: str,
    runtime_url: str,
    token_file: Path,
    work_dir: Path,
    worker_id: str,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return command(
        worker_command(
            service_url=service_url,
            runtime_url=runtime_url,
            token_file=token_file,
            work_dir=work_dir,
            worker_id=worker_id,
        ),
        timeout=timeout,
        env=worker_environment(),
    )


def main() -> int:
    if sys.platform != "linux":
        raise SystemExit("worker partition fencing fixture requires Linux")
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = args.out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    control_port = free_port()
    runtime_port = free_port()
    service_url = f"http://{SERVER_ADDRESS}:{control_port}"
    runtime_url = f"http://127.0.0.1:{runtime_port}"
    token = secrets.token_hex(32)
    token_file = args.out_dir / "service.token"
    atomic_token_file(token_file, token)
    runtime_state = args.out_dir / "runtime-state.json"
    service_state = args.out_dir / "service-state"
    service_state.mkdir()
    worker_first_dir = args.out_dir / "worker-first"
    worker_second_dir = args.out_dir / "worker-second"
    tool_paths = {
        "runner": Path(__file__).resolve(),
        "runtime_fixture": RUNTIME,
        "worker_agent": WORKER,
        "device_service": ROOT / "platform/tools/device_service.py",
        "serve": SERVICE,
    }
    hashes_before = {
        name: sha256_file(path)
        for name, path in tool_paths.items()
    }
    environment = os.environ.copy()
    environment["M5_JOB_LEASE_SECONDS"] = str(JOB_LEASE_SECONDS)

    fixture = NamespaceFixture()
    service: subprocess.Popen[str] | None = None
    runtime: subprocess.Popen[str] | None = None
    first_process: subprocess.Popen[str] | None = None
    service_log = (logs_dir / "service.log").open("w")
    runtime_log = (logs_dir / "runtime.log").open("w")
    restored = False
    try:
        fixture.up()
        service = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                SERVER_NS,
                sys.executable,
                "-u",
                str(SERVICE),
                str(control_port),
                "--bind",
                SERVER_ADDRESS,
                "--state-dir",
                str(service_state),
                "--api-token-file",
                str(token_file),
                "--worker-id",
                "partition-central",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=service_log,
            stderr=subprocess.STDOUT,
        )
        wait_http(
            SERVER_NS,
            service_url + "/api/health",
            service,
        )
        runtime = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                WORKER_NS,
                sys.executable,
                "-u",
                str(RUNTIME),
                "--port",
                str(runtime_port),
                "--token-file",
                str(token_file),
                "--state-file",
                str(runtime_state),
            ],
            cwd=ROOT,
            text=True,
            stdout=runtime_log,
            stderr=subprocess.STDOUT,
        )
        wait_http(WORKER_NS, runtime_url + "/api/health", runtime)

        submitted = api_json(
            SERVER_NS,
            service_url + "/api/v1/jobs",
            token_file,
            method="POST",
            payload={
                "label": "network-partition-fencing",
                "required_capabilities": {"qemu": True},
                "max_attempts": 3,
                "idempotency_key": f"partition-{secrets.token_hex(8)}",
                "request": {
                    "session": {
                        "device_id": "sticks3",
                        "runtime": "qemu",
                    },
                    "evidence_include": ["manifest", "serial"],
                    "evidence_delay_seconds": EVIDENCE_DELAY_SECONDS,
                },
            },
        )["job"]
        job_id = str(submitted["job_id"])

        first_process = subprocess.Popen(
            worker_command(
                service_url=service_url,
                runtime_url=runtime_url,
                token_file=token_file,
                work_dir=worker_first_dir,
                worker_id="partition-first-worker",
            ),
            cwd=ROOT,
            env=worker_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        first_session = wait_runtime_session(
            runtime_state,
            lambda row: (
                row.get("state") == "running"
                and isinstance(row.get("side_effect_pid"), int)
            ),
            timeout=5,
        )
        first_pid = int(first_session["side_effect_pid"])
        pid_before = pid_alive(first_pid)
        partition_network(control_port)

        try:
            first_stdout, _ = first_process.communicate(timeout=30)
        except subprocess.TimeoutExpired as error:
            first_process.kill()
            first_stdout, _ = first_process.communicate(timeout=5)
            raise FixtureError("first worker did not fence before timeout") from error
        first_returncode = int(first_process.returncode)
        first_log = first_stdout or ""
        (logs_dir / "worker-first.log").write_text(first_log)
        first_result_path = worker_first_dir / job_id / "result.json"
        first_result = (
            json.loads(first_result_path.read_text())
            if first_result_path.is_file()
            else {}
        )
        first_summary = first_result.get("summary", {})
        fenced_session = wait_runtime_session(
            runtime_state,
            lambda row: (
                row.get("session_id") == first_session["session_id"]
                and row.get("state") == "stopped"
                and row.get("side_effect_reaped") is True
            ),
            timeout=10,
        )
        pid_after = pid_alive(first_pid)

        leased = api_json(
            SERVER_NS,
            service_url + f"/api/v1/jobs/{job_id}",
            token_file,
        )["job"]
        restore_network()
        restored = True
        queued = poll_job(
            service_url,
            token_file,
            job_id,
            lambda job: job.get("status") == "queued",
            timeout=JOB_LEASE_SECONDS + 10,
        )

        second = run_worker(
            service_url=service_url,
            runtime_url=runtime_url,
            token_file=token_file,
            work_dir=worker_second_dir,
            worker_id="partition-retry-worker",
            timeout=40,
        )
        second_log = second.stdout + second.stderr
        (logs_dir / "worker-second.log").write_text(second_log)
        completed = poll_job(
            service_url,
            token_file,
            job_id,
            lambda job: job.get("status") == "completed",
            timeout=20,
        )
        final_state = read_runtime_state(runtime_state)
        final_sessions = list(
            final_state.get("sessions", {}).values()
        )
        second_session = next(
            (
                row
                for row in final_sessions
                if row.get("session_id") != first_session["session_id"]
            ),
            {},
        )
        second_pid = int(second_session.get("side_effect_pid") or 0)
        input_assets_unchanged = {
            name: sha256_file(path)
            for name, path in tool_paths.items()
        } == hashes_before

        stop_process(runtime)
        stop_process(service)
        service_log.close()
        runtime_log.close()
        fixture.cleanup()
        namespaces_after = fixture.namespaces()
        service_log_text = (logs_dir / "service.log").read_text(
            errors="replace"
        )
        runtime_log_text = (logs_dir / "runtime.log").read_text(
            errors="replace"
        )
        checks = {
            "worker_and_server_routes_present": (
                SERVER_ADDRESS in fixture.routes.get("server", "")
                and WORKER_ADDRESS in fixture.routes.get("worker", "")
            ),
            "first_worker_created_side_effect": pid_before,
            "network_partition_installed": True,
            "first_worker_failed_closed": first_returncode != 0,
            "first_result_lease_fenced": (
                first_summary.get("lease_fenced") is True
                and first_result.get("state") == "FAIL"
            ),
            "heartbeat_failure_recorded": bool(
                first_summary.get("heartbeat_error")
            ),
            "runtime_session_stopped": (
                fenced_session.get("state") == "stopped"
            ),
            "runtime_side_effect_reaped": (
                fenced_session.get("side_effect_reaped") is True
                and not pid_after
            ),
            "stale_result_not_reported": (
                leased.get("result") is None
                and leased.get("attempts") == 1
            ),
            "lease_expired_and_requeued": (
                queued.get("status") == "queued"
                and queued.get("attempts") == 1
            ),
            "retry_worker_exit_zero": second.returncode == 0,
            "retry_worker_completed_job": (
                completed.get("attempts") == 2
                and completed.get("result", {}).get("state") == "PASS"
                and completed.get("result", {})
                .get("worker", {})
                .get("worker_id")
                == "partition-retry-worker"
            ),
            "retry_runtime_stopped": (
                second_session.get("state") == "stopped"
                and second_session.get("side_effect_reaped") is True
            ),
            "retry_side_effect_reaped": (
                second_pid > 0 and not pid_alive(second_pid)
            ),
            "tool_hashes_unchanged": input_assets_unchanged,
            "token_absent_from_logs": (
                token not in service_log_text
                and token not in runtime_log_text
                and token not in first_log
                and token not in second_log
            ),
            "namespaces_cleaned": all(
                namespace not in namespaces_after
                for namespace in (SERVER_NS, WORKER_NS)
            ),
            "no_qemu_started": True,
        }
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-worker-network-partition-fencing",
            "date": "2026-10-25",
            "validation": "virtual control-plane validation",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "base_commit": "667c3564208fcb69df7afea68091d6d3e34d3eb4",
            "tool_hashes": hashes_before,
            "input_assets_unchanged": input_assets_unchanged,
            "job": {
                "job_id_sha256": hashlib.sha256(job_id.encode()).hexdigest(),
                "lease_seconds": JOB_LEASE_SECONDS,
                "evidence_delay_seconds": EVIDENCE_DELAY_SECONDS,
                "attempts": completed.get("attempts"),
                "status": completed.get("status"),
                "result": completed.get("result"),
            },
            "partition": {
                "control_to_worker_observed_leased": (
                    leased.get("status") == "leased"
                ),
                "worker_to_control_drop": (
                    f"ip daddr {SERVER_ADDRESS} tcp dport "
                    f"{control_port} drop"
                ),
                "restored": restored,
            },
            "first_worker": {
                "returncode": first_returncode,
                "result": first_result,
                "session": fenced_session,
                "side_effect_pid_alive_before": pid_before,
                "side_effect_pid_alive_after": pid_after,
            },
            "retry_worker": {
                "returncode": second.returncode,
                "session": second_session,
            },
            "checks": checks,
            "cleanup": {
                "service_exit": service.poll() is not None,
                "runtime_exit": runtime.poll() is not None,
                "namespaces": namespaces_after.strip().splitlines(),
            },
            "not_claimed": [
                "QEMU side-effect fencing",
                "physical cross-host execution",
                "external network side effects not owned by the worker",
                "production scheduler",
                "physical hardware validation",
            ],
        }
        evidence_path = args.out_dir / "evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        if not restored:
            restore_network()
        stop_process(runtime)
        stop_process(service)
        stop_process(first_process)
        if not service_log.closed:
            service_log.close()
        if not runtime_log.closed:
            runtime_log.close()
        fixture.cleanup()
        token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
