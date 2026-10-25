#!/usr/bin/env python3
"""Run central control and worker-local QEMU in separate Docker containers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
WORKER_FIXTURE = ROOT / "tests/network/worker_cross_netns/run_test.py"
DEFAULT_IMAGE = "m5-emulator-cross-container:latest"
DEFAULT_QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu-linux-arm64/qemu-system-xtensa"
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
CENTRAL_PORT = 8787
RUNTIME_PORT = 8787


class RunnerError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RunnerError(f"command failed ({shlex.join(command)}): {detail}")
    return completed


def docker(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return run(["docker", *args], **kwargs)


def docker_json(*args: str) -> Any:
    completed = docker(*args)
    return json.loads(completed.stdout)


def wait_container_removed(name: str, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = docker(
            "ps",
            "-a",
            "--filter",
            f"name=^{re.escape(name)}$",
            "--format",
            "{{.Names}}",
        )
        if not result.stdout.strip():
            return True
        time.sleep(0.2)
    return False


def wait_network_removed(name: str, timeout: float = 15) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = docker(
            "network",
            "ls",
            "--filter",
            f"name=^{re.escape(name)}$",
            "--format",
            "{{.Name}}",
        )
        if not result.stdout.strip():
            return True
        time.sleep(0.2)
    return False


def qemu_processes(listing: str) -> list[str]:
    live = []
    for line in listing.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        try:
            argv = shlex.split(fields[1])
        except ValueError:
            continue
        if argv and Path(argv[0]).name.startswith("qemu-system-"):
            live.append(line)
    return live


def inside_workspace(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as error:
        raise RunnerError(f"path must be under repository root: {path}") from error


def query_central(container: str, token: str, job_id: str) -> dict[str, Any]:
    code = """
import json, os, urllib.request
token = os.environ["M5_SERVICE_API_TOKEN"]
job_id = os.environ["M5_JOB_ID"]
def get(path):
    request = urllib.request.Request(
        "http://127.0.0.1:8787/api/v1/" + path,
        headers={"Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())
print(json.dumps({
    "job": get("jobs/" + job_id),
    "workers": get("workers"),
}))
"""
    completed = docker(
        "exec",
        "-e",
        f"M5_SERVICE_API_TOKEN={token}",
        "-e",
        f"M5_JOB_ID={job_id}",
        container,
        "python3",
        "-c",
        code,
    )
    return json.loads(completed.stdout)


def build_image(image: str) -> None:
    docker(
        "build",
        "-t",
        image,
        "-f",
        inside_workspace(ROOT / "tests/network/worker_cross_container/Dockerfile"),
        ".",
        timeout=600,
        capture=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--build-image", action="store_true")
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()

    out = args.out_dir.resolve()
    inside_workspace(out)
    if not args.qemu.is_file():
        parser.error("--qemu must exist")
    if not args.rom_dir.is_dir():
        parser.error("--rom-dir must exist")
    if not args.firmware.is_file():
        parser.error("--firmware must exist")
    out.mkdir(parents=True, exist_ok=True)
    if args.build_image:
        build_image(args.image)
    image_info = docker_json(
        "image",
        "inspect",
        args.image,
    )[0]
    if not shutil.which("docker"):
        raise RunnerError("docker CLI is unavailable")
    docker_info = docker_json("info", "--format", "{{json .}}")
    suffix = secrets.token_hex(4)
    network = f"m5-cross-{suffix}"
    central = f"m5-cross-central-{suffix}"
    worker = f"m5-cross-worker-{suffix}"
    token = secrets.token_urlsafe(32)
    central_state = out / "central-state"
    runtime_state = out / "runtime-state"
    worker_state = out / "worker-state"
    for path in (central_state, runtime_state, worker_state):
        path.mkdir(parents=True, exist_ok=True)
    central_log = out / "central.log"
    runtime_log = out / "runtime.log"
    worker_stdout_path = out / "worker.stdout"
    worker_stderr_path = out / "worker.stderr"
    process_path = out / "qemu-processes.txt"
    result_path = out / "worker-result.json"
    central_result_path = out / "central-result.json"
    image_id = str(image_info.get("Id", ""))
    qemu_container_path = "/workspace/" + inside_workspace(args.qemu)
    rom_container_path = "/workspace/" + inside_workspace(args.rom_dir)
    network_id = ""
    central_id = ""
    worker_id = ""
    central_network_mode = ""
    worker_network_mode = ""
    worker_completed: subprocess.CompletedProcess[str] | None = None
    central_payload: dict[str, Any] = {}
    error_text = ""
    started = time.monotonic()
    cleaned = {"central": False, "worker": False, "network": False}
    try:
        docker("network", "create", network)
        network_id = docker(
            "network",
            "inspect",
            network,
            "--format",
            "{{.Id}}",
        ).stdout.strip()
        central_command = (
            f"PYTHONPATH=platform/tools python3 platform/tools/serve.py "
            f"{CENTRAL_PORT} --bind 0.0.0.0 "
            f"--state-dir {inside_workspace(central_state)} "
            f"--worker-id cross-container-central "
            f"> {inside_workspace(central_log)} 2>&1"
        )
        central_id = docker(
            "run",
            "-d",
            "--rm",
            "--name",
            central,
            "--network",
            network,
            "-v",
            f"{ROOT}:/workspace",
            "-w",
            "/workspace",
            "-e",
            f"M5_SERVICE_API_TOKEN={token}",
            "-e",
            "HTTP_PROXY=",
            "-e",
            "HTTPS_PROXY=",
            "-e",
            "ALL_PROXY=",
            "-e",
            "http_proxy=",
            "-e",
            "https_proxy=",
            "-e",
            "all_proxy=",
            "-e",
            "NO_PROXY=*",
            "-e",
            "no_proxy=*",
            "--entrypoint",
            "bash",
            args.image,
            "-lc",
            central_command,
        ).stdout.strip()
        worker_command = f"""
set -eu
PYTHONPATH=platform/tools python3 platform/tools/serve.py \
  {RUNTIME_PORT} --bind 127.0.0.1 \
  --state-dir {inside_workspace(runtime_state)} \
  --worker-id cross-container-runtime \
  > {inside_workspace(runtime_log)} 2>&1 &
runtime_pid=$!
cleanup_runtime() {{
  kill "$runtime_pid" >/dev/null 2>&1 || true
  wait "$runtime_pid" 2>/dev/null || true
}}
trap cleanup_runtime EXIT
PYTHONPATH=platform/tools python3 {inside_workspace(WORKER_FIXTURE)} \
  --qemu-worker \
  --work-dir {inside_workspace(worker_state)} \
  --worker-result {inside_workspace(result_path)} \
  --service-url http://{central}:{CENTRAL_PORT} \
  --runtime-service-url http://127.0.0.1:{RUNTIME_PORT} \
  --firmware {inside_workspace(args.firmware)} \
  --runtime qemu \
  --qemu-path {inside_workspace(args.qemu)}
ps -eo pid,args > {inside_workspace(process_path)}
"""
        worker_id = docker(
            "create",
            "--rm",
            "--name",
            worker,
            "--network",
            network,
            "--privileged",
            "-v",
            f"{ROOT}:/workspace",
            "-w",
            "/workspace",
            "-e",
            f"M5_SERVICE_API_TOKEN={token}",
            "-e",
            f"M5_CROSS_NETNS_TOKEN={token}",
            "-e",
            "HTTP_PROXY=",
            "-e",
            "HTTPS_PROXY=",
            "-e",
            "ALL_PROXY=",
            "-e",
            "http_proxy=",
            "-e",
            "https_proxy=",
            "-e",
            "all_proxy=",
            "-e",
            "NO_PROXY=*",
            "-e",
            "no_proxy=*",
            "-e",
            f"M5_QEMU_XTENSA={qemu_container_path}",
            "-e",
            f"M5_QEMU_XTENSA_ROM_DIR={rom_container_path}",
            "-e",
            "M5_SERVICE_FLASH_MODE=host-image",
            "--entrypoint",
            "bash",
            args.image,
            "-lc",
            worker_command,
        ).stdout.strip()
        central_network_mode = docker(
            "inspect",
            "--format",
            "{{.HostConfig.NetworkMode}}",
            central_id,
        ).stdout.strip()
        worker_network_mode = docker(
            "inspect",
            "--format",
            "{{.HostConfig.NetworkMode}}",
            worker_id,
        ).stdout.strip()
        worker_completed = run(
            ["docker", "start", "-a", worker_id],
            timeout=args.timeout,
            check=False,
        )
        worker_stdout_path.write_text(worker_completed.stdout)
        worker_stderr_path.write_text(worker_completed.stderr)
        worker_result = (
            json.loads(result_path.read_text()) if result_path.is_file() else {}
        )
        job_id = str(worker_result.get("job_submitted", ""))
        if job_id:
            central_payload = query_central(central, token, job_id)
            central_result_path.write_text(json.dumps(central_payload, indent=2) + "\n")
    except Exception as error:
        error_text = str(error).replace(token, "<redacted>")
    finally:
        if worker:
            docker("rm", "-f", worker, check=False)
            cleaned["worker"] = wait_container_removed(worker)
        if central:
            docker("stop", "--time", "10", central, check=False)
            docker("rm", "-f", central, check=False)
            cleaned["central"] = wait_container_removed(central)
        if network:
            docker("network", "rm", network, check=False)
            cleaned["network"] = wait_network_removed(network)

    worker_stdout = (
        worker_stdout_path.read_text(errors="replace")
        if worker_stdout_path.is_file()
        else ""
    )
    worker_stderr = (
        worker_stderr_path.read_text(errors="replace")
        if worker_stderr_path.is_file()
        else ""
    )
    worker_result = json.loads(result_path.read_text()) if result_path.is_file() else {}
    process_listing = (
        process_path.read_text(errors="replace") if process_path.is_file() else ""
    )
    central_text = (
        central_log.read_text(errors="replace") if central_log.is_file() else ""
    )
    runtime_text = (
        runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    )
    logs = {
        "central": central_text,
        "runtime": runtime_text,
        "worker_stdout": worker_stdout,
        "worker_stderr": worker_stderr,
    }
    result_summary = worker_result.get("result", {}).get("summary", {})
    evidence_names = worker_result.get("evidence_names", [])
    worker_rows = central_payload.get("workers", {}).get("workers", [])
    central_job = central_payload.get("job", {}).get("job", {})
    checks = {
        "worker_exit_zero": (
            worker_completed is not None and worker_completed.returncode == 0
        ),
        "central_api_reachable_over_container_network": bool(central_payload),
        "worker_registered": bool(worker_rows),
        "job_terminal_completed": central_job.get("status") == "completed",
        "worker_result_pass": worker_result.get("result", {}).get("state") == "PASS",
        "worker_local_execution": worker_result.get("execution_plane")
        == "worker-local",
        "qemu_started": worker_result.get("qemu_started") is True,
        "device_session_created": (worker_result.get("device_session_created") is True),
        "evidence_manifest": "manifest.json" in evidence_names,
        "evidence_serial": "serial.log" in evidence_names,
        "source_firmware_hash": bool(worker_result.get("firmware_source_sha256")),
        "normalized_firmware_hash": bool(worker_result.get("firmware_sha256")),
        "qemu_hash": bool(worker_result.get("qemu_sha256")),
        "qemu_reaped": not qemu_processes(process_listing),
        "central_worker_directory_readback": bool(worker_rows),
        "token_absent_from_logs": all(token not in text for text in logs.values()),
        "container_interfaces_independent": (
            central_id != worker_id and bool(central_id) and bool(worker_id)
        ),
        "central_container_cleaned": cleaned["central"],
        "worker_container_cleaned": cleaned["worker"],
        "network_cleaned": cleaned["network"],
        "no_docker_host_network": (
            central_network_mode == network and worker_network_mode == network
        ),
    }
    status = "PASS" if all(checks.values()) and not error_text else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-worker-qemu-cross-container",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "validation": "virtual-device validation",
        "scope": "two-independent-containers-one-docker-daemon-not-physical-hosts",
        "environment": {
            "host_os": sys.platform,
            "docker_os": docker_info.get("OSType"),
            "docker_arch": docker_info.get("Architecture"),
            "docker_version": docker_info.get("ServerVersion"),
            "image": args.image,
            "image_id_sha256": sha256_bytes(image_id.encode()),
            "network_id_sha256": (
                sha256_bytes(network_id.encode()) if network_id else None
            ),
            "central_container_sha256": (
                sha256_bytes(central_id.encode()) if central_id else None
            ),
            "worker_container_sha256": (
                sha256_bytes(worker_id.encode()) if worker_id else None
            ),
            "duration_seconds": round(time.monotonic() - started, 3),
        },
        "artifacts": {
            "firmware_source_sha256": worker_result.get("firmware_source_sha256"),
            "firmware_normalized_sha256": worker_result.get("firmware_sha256"),
            "qemu_sha256": worker_result.get("qemu_sha256"),
            "worker_result_sha256": sha256_file(result_path),
            "worker_stdout_sha256": sha256_bytes(worker_stdout.encode()),
            "worker_stderr_sha256": sha256_bytes(worker_stderr.encode()),
            "central_log_sha256": sha256_bytes(central_text.encode()),
            "runtime_log_sha256": sha256_bytes(runtime_text.encode()),
            "runner_sha256": sha256_file(Path(__file__)),
            "worker_fixture_sha256": sha256_file(WORKER_FIXTURE),
            "device_service_sha256": sha256_file(
                ROOT / "platform/tools/device_service.py"
            ),
            "worker_agent_sha256": sha256_file(ROOT / "platform/tools/worker_agent.py"),
            "dockerfile_sha256": sha256_file(
                ROOT / "tests/network/worker_cross_container/Dockerfile"
            ),
        },
        "checks": checks,
        "evidence_names": evidence_names,
        "job": {
            "terminal": central_job.get("status"),
            "worker_count": len(worker_rows),
            "execution_plane": result_summary.get("execution_plane"),
        },
        "error": error_text,
        "not_claimed": [
            "physically separate hosts",
            "cross-host process migration or re-attach",
            "NAT or cross-subnet discovery",
            "companion HTTP/BLE continuity",
            "production multi-host scheduling",
            "physical RF or hardware validation",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
