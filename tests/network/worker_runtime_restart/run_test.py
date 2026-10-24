#!/usr/bin/env python3
"""Prove worker evidence survives a runtime Device Service restart."""

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
import zipfile
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


def upload_artifact(
    base_url: str,
    token: str,
    path: Path,
) -> dict[str, Any]:
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


def import_merged_firmware(
    runtime_url: str,
    token: str,
    artifact_id: str,
) -> dict[str, Any]:
    return request_json(
        runtime_url + "/api/v1/firmware",
        token,
        method="POST",
        payload={
            "device_id": "sticks3",
            "kind": "merged",
            "artifact_id": artifact_id,
        },
    )


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


def wait_running_session(
    runtime_url: str,
    token: str,
    *,
    timeout: float = 90,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        try:
            latest = request_json(
                runtime_url + "/api/v1/sessions",
                token,
            )["sessions"]
            running = [
                session for session in latest
                if session.get("state") == "running"
            ]
            if len(running) == 1:
                return running[0]
            if latest:
                session_id = str(latest[0].get("session_id") or "")
                if session_id:
                    detail = request_json(
                        runtime_url + f"/api/v1/sessions/{session_id}",
                        token,
                    )
                    if detail.get("state") == "failed":
                        raise RuntimeError(
                            f"runtime session failed before restart: "
                            f"{detail.get('error')}"
                        )
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.05)
    raise RuntimeError(f"no running runtime session observed: {latest}")


def wait_reattached_session(
    runtime_url: str,
    token: str,
    session_id: str,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            latest = request_json(
                runtime_url + f"/api/v1/sessions/{session_id}",
                token,
            )
            if latest.get("reattached_process") is True:
                return latest
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.05)
    raise RuntimeError(f"runtime session was not reattached: {latest}")


def wait_serial_markers(
    runtime_url: str,
    token: str,
    session_id: str,
    markers: list[str],
    *,
    timeout: float = 60,
) -> str:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        try:
            latest = request_json(
                runtime_url
                + f"/api/v1/sessions/{session_id}/serial?offset=0&limit=65536",
                token,
            ).get("data", "")
            if all(marker in latest for marker in markers):
                return latest
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.1)
    raise RuntimeError(
        f"serial markers were not observed: {markers}; latest={latest!r}"
    )


def wait_text_file(
    path: Path,
    markers: list[str],
    *,
    timeout: float = 60,
) -> str:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        if path.is_file():
            latest = path.read_text(errors="replace")
            if all(marker in latest for marker in markers):
                return latest
        time.sleep(0.1)
    raise RuntimeError(
        f"file markers were not observed in {path}: "
        f"{markers}; latest={latest!r}"
    )


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


def companion_processes(needle: str | None = None) -> list[str]:
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
        if (
            len(argv) >= 2
            and Path(argv[1]).name == "ble_probe.py"
            and (needle is None or needle in line)
        ):
            processes.append(line)
    return processes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--unified-image",
        type=Path,
        help="8 MiB StickS3 UIFlow2 unified image for companion continuity",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    unified_image = (
        args.unified_image.resolve()
        if args.unified_image is not None
        else None
    )
    if unified_image is not None and (
        not unified_image.is_file()
        or unified_image.stat().st_size != (8 << 20)
    ):
        raise RuntimeError(
            "--unified-image must be an existing exactly 8 MiB image"
        )

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
    restarted_runtime = None
    worker_log = ""
    firmware_info: dict[str, Any] = {}
    try:
        wait_health(control_url, control)
        wait_health(runtime_url, runtime)
        firmware_id = None
        if unified_image is not None:
            artifact = upload_artifact(
                runtime_url,
                token,
                unified_image,
            )
            firmware = import_merged_firmware(
                runtime_url,
                token,
                str(artifact["artifact_id"]),
            )
            firmware_id = str(firmware["firmware_id"])
            firmware_info = {
                "artifact_sha256": str(artifact["artifact_id"]),
                "firmware_id": firmware_id,
                "sha256": str(firmware.get("sha256") or ""),
            }
        session_payload: dict[str, Any] = {
            "device_id": "sticks3",
            "runtime": "qemu-unified" if firmware_id else "qemu",
            "ready_timeout_seconds": 240 if firmware_id else 120,
        }
        if firmware_id:
            session_payload.update(
                {
                    "firmware_id": firmware_id,
                    "network": {
                        "profile": "uiflow2-sticks3-unified",
                        "attempts": 1,
                        "capture_pcap": True,
                        "ble_reconnect_cycles": 1,
                        "ble_reconnect_delay_seconds": 2,
                        "ble_linger_seconds": 10,
                        "ble_post_pass_continuity": True,
                    },
                }
            )
        evidence_include = ["manifest", "serial", "logs", "qom"]
        if firmware_id:
            evidence_include.extend(["network", "frames"])
        submitted = request_json(
            control_url + "/api/v1/jobs",
            token,
            method="POST",
            payload={
                "label": (
                    "runtime-restart-companion-continuity"
                    if firmware_id
                    else "runtime-restart-continuity"
                ),
                "request": {
                    "session": session_payload,
                    "evidence_include": evidence_include,
                    "evidence_delay_seconds": 40 if firmware_id else 0,
                },
                "required_capabilities": {"qemu": True},
                "max_attempts": 1,
                "idempotency_key": (
                    "runtime-restart-companion-continuity"
                    if firmware_id
                    else "runtime-restart-continuity"
                ),
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
                "runtime-restart-survivor",
                "--work-dir",
                str(args.out_dir / "worker"),
                "--poll-seconds",
                "0.1",
                "--heartbeat-interval",
                "1",
                "--control-reconnect-timeout",
                "30",
                "--runtime-reconnect-timeout",
                "30",
                "--session-timeout",
                "300" if firmware_id else "150",
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
        before_restart = wait_running_session(runtime_url, token)
        session_id = str(before_restart["session_id"])
        original_pid = before_restart.get("pid")
        before_companions = before_restart.get("companions") or {}
        runtime.kill()
        runtime.wait(timeout=15)
        time.sleep(2.2)
        restarted_runtime = start_service(
            port=runtime_port,
            state_dir=args.out_dir / "runtime-state",
            token_file=token_file,
        )
        wait_health(runtime_url, restarted_runtime)
        reattached = wait_reattached_session(
            runtime_url,
            token,
            session_id,
        )
        post_restart_serial = ""
        continuity_peer_log = ""
        http_fixture: list[dict[str, Any]] = []
        if firmware_id:
            trigger = (
                args.out_dir
                / "runtime-state"
                / "sessions"
                / session_id
                / "ble-continuity.trigger"
            )
            trigger.write_text("continue\n")
            post_restart_serial = wait_serial_markers(
                runtime_url,
                token,
                session_id,
                ["UNIFIED_STICKS3_HTTP_RECHECK_PASS"],
                timeout=90,
            )
            continuity_peer_log = wait_text_file(
                args.out_dir
                / "runtime-state"
                / "sessions"
                / session_id
                / "ble-probe.log",
                ["BLE_BUMBLE_CONTINUITY_PASS 2"],
                timeout=30,
            )
            http_log_path = (
                args.out_dir
                / "runtime-state"
                / "sessions"
                / session_id
                / "http-fixture.json"
            )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if http_log_path.is_file():
                    try:
                        http_fixture = json.loads(
                            http_log_path.read_text()
                        )
                    except json.JSONDecodeError:
                        http_fixture = []
                if isinstance(http_fixture, list) and len(http_fixture) >= 2:
                    break
                time.sleep(0.1)
        worker_log, _ = worker.communicate(timeout=360 if firmware_id else 180)
        worker_log = worker_log or ""
        terminal = wait_job(
            control_url,
            token,
            job_id,
            statuses={"completed", "failed", "cancelled"},
            timeout=30,
        )
        final_session = request_json(
            runtime_url + f"/api/v1/sessions/{session_id}",
            token,
        )
        evidence_path = args.out_dir / "worker" / job_id / "evidence.zip"
        evidence_names = []
        if evidence_path.is_file():
            with zipfile.ZipFile(evidence_path) as archive:
                evidence_names = sorted(archive.namelist())
        leaked_qemu = qemu_processes()
        leaked_companions = companion_processes(
            (
                str(
                    args.out_dir
                    / "runtime-state"
                    / "sessions"
                    / session_id
                )
                if firmware_id
                else None
            )
        )
        claimed_worker = {
            key: (claimed.get("lease") or {}).get(key)
            for key in ("worker_id", "instance_id", "generation")
        }
        terminal_worker = (
            (terminal.get("result") or {}).get("worker") or {}
        )
        checks = {
            "job_claimed_before_restart": claimed.get("status") == "leased",
            "runtime_session_running_before_restart": True,
            "runtime_pid_preserved": (
                reattached.get("pid") == original_pid
                and original_pid is not None
            ),
            "runtime_reattached_once": (
                reattached.get("reattached_process") is True
            ),
            "worker_runtime_retry_observed": (
                "worker runtime service unavailable; retrying" in worker_log
                and "worker runtime service reconnected" in worker_log
            ),
            "terminal_completed": terminal.get("status") == "completed",
            "terminal_pass": (
                (terminal.get("result") or {}).get("state") == "PASS"
            ),
            "same_lease": (
                str((terminal.get("result") or {}).get("lease_id") or "")
                == lease_id
            ),
            "same_worker_identity": all(
                terminal_worker.get(key) == value
                for key, value in claimed_worker.items()
            ),
            "evidence_zip_present": evidence_path.is_file(),
            "evidence_contains_manifest_and_serial": (
                "manifest.json" in evidence_names
                and "serial.log" in evidence_names
            ),
            "runtime_session_stopped": final_session.get("state") == "stopped",
            "runtime_pid_released": final_session.get("pid") is None,
            "qemu_process_absent_after_cleanup": not leaked_qemu,
            "companion_process_absent_after_cleanup": (
                not leaked_companions
            ),
            "token_absent_from_worker_log": token not in worker_log,
        }
        network_evidence: dict[str, Any] = {}
        if firmware_id and evidence_path.is_file():
            with zipfile.ZipFile(evidence_path) as archive:
                if "network/evidence.json" in archive.namelist():
                    network_evidence = json.loads(
                        archive.read("network/evidence.json")
                    )
        if firmware_id:
            http_generations = [
                item.get("fixture_generation")
                for item in http_fixture
                if isinstance(item, dict)
            ]
            checks.update(
                {
                    "before_restart_http_generation_1": (
                        (before_companions.get("http_fixture") or {}).get(
                            "generation"
                        )
                        == 1
                    ),
                    "before_restart_ble_peer_running": (
                        (before_companions.get("ble_probe") or {}).get(
                            "state"
                        )
                        == "running"
                    ),
                    "post_restart_http_recreated_generation_2": (
                        (
                            (reattached.get("companions") or {}).get(
                                "http_fixture"
                            )
                            or {}
                        ).get("generation")
                        == 2
                    ),
                    "post_restart_ble_peer_adopted": (
                        (
                            (reattached.get("companions") or {}).get(
                                "ble_probe"
                            )
                            or {}
                        ).get("state")
                        == "adopted"
                    ),
                    "post_restart_http_requests_two_generations": (
                        http_generations == [1, 2]
                    ),
                    "post_restart_ble_continuity_cycle": (
                        "BLE_BUMBLE_CYCLE_PASS 2"
                        in continuity_peer_log
                    ),
                    "post_restart_guest_http_recheck": (
                        "UNIFIED_STICKS3_HTTP_RECHECK_PASS"
                        in post_restart_serial
                    ),
                    "network_evidence_pass": (
                        network_evidence.get("status") == "PASS"
                    ),
                    "network_evidence_two_http_requests": (
                        len(network_evidence.get("http_requests") or [])
                        == 2
                    ),
                    "firmware_sha_matches_input": (
                        firmware_info.get("sha256")
                        == hashlib.sha256(
                            unified_image.read_bytes()
                        ).hexdigest()
                    ),
                }
            )
        not_claimed = [
            "cross-host QEMU process migration",
            "session create response-loss recovery",
            "production multi-host scheduler",
            "physical hardware validation",
        ]
        if not firmware_id:
            not_claimed.insert(1, "companion HTTP/BLE helper continuity")
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-worker-runtime-service-restart-continuity",
            "date": "2026-10-25",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "scope": (
                "virtual-device-runtime-and-companion-restart-not-hardware"
                if firmware_id
                else "virtual-device-runtime-service-restart-not-hardware"
            ),
            "runtime_restart": {
                "downtime_seconds": 2.2,
                "same_state_dir": True,
                "same_session": reattached.get("session_id") == session_id,
                "same_pid": reattached.get("pid") == original_pid,
                "process_start_token_checked_by_reattach": True,
                "reattached_process": reattached.get("reattached_process"),
                "recovery_scope": reattached.get("recovery_scope"),
            },
            "companion_continuity": (
                {
                    "before_restart": before_companions,
                    "after_restart": reattached.get("companions"),
                    "http_fixture_requests": http_fixture,
                    "ble_continuity_cycle_observed": (
                        "BLE_BUMBLE_CYCLE_PASS 2"
                        in continuity_peer_log
                    ),
                    "guest_http_recheck_observed": (
                        "UNIFIED_STICKS3_HTTP_RECHECK_PASS"
                        in post_restart_serial
                    ),
                    "network_evidence_status": network_evidence.get(
                        "status"
                    ),
                }
                if firmware_id
                else {
                    "status": "NOT RUN",
                    "reason": "default runtime=qemu workload has no companions",
                }
            ),
            "firmware": firmware_info,
            "job": {
                "job_id": job_id,
                "lease_id": lease_id,
                "status": terminal.get("status"),
                "result_state": (terminal.get("result") or {}).get("state"),
                "worker_identity": claimed_worker,
            },
            "worker": {
                "worker_id": "runtime-restart-survivor",
                "returncode": worker.returncode,
                "runtime_retry_observed": (
                    "worker runtime service unavailable; retrying" in worker_log
                ),
            },
            "evidence": {
                "zip_present": evidence_path.is_file(),
                "bytes": evidence_path.stat().st_size if evidence_path.is_file() else 0,
                "names": evidence_names,
                "sha256": (
                    hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                    if evidence_path.is_file()
                    else None
                ),
            },
            "checks": checks,
            "not_claimed": not_claimed,
        }
        (args.out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        stop_service(control)
        if restarted_runtime is not None:
            stop_service(restarted_runtime)
        if runtime.poll() is None:
            stop_service(runtime)
        token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
