#!/usr/bin/env python3
"""Exercise local worker drain and restart classification with real QEMU."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    base: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10,
) -> tuple[int, dict[str, Any]]:
    data = (
        json.dumps(payload).encode()
        if payload is not None
        else None
    )
    req = Request(
        base + path,
        method=method,
        data=data,
        headers=(
            {"Content-Type": "application/json"}
            if data is not None
            else {}
        ),
    )
    with urlopen(req, timeout=timeout) as response:
        return response.status, json.load(response)


def request_error(
    base: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10,
) -> tuple[int, dict[str, Any]]:
    data = (
        json.dumps(payload).encode()
        if payload is not None
        else None
    )
    req = Request(
        base + path,
        method=method,
        data=data,
        headers=(
            {"Content-Type": "application/json"}
            if data is not None
            else {}
        ),
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def frame(base: str, session_id: str) -> bytes:
    with urlopen(
        base + f"/api/v1/sessions/{session_id}/frame.png",
        timeout=20,
    ) as response:
        return response.read()


def upload_reference_firmware(base: str) -> dict[str, Any]:
    reference = ROOT / "platform/.cache/firmware/sticks3/uiflow2.bin"
    if not reference.is_file():
        raise RuntimeError(
            "StickS3 reference firmware is missing; run fetch_firmware.py sticks3"
        )
    req = Request(
        base + "/api/v1/artifacts",
        method="POST",
        data=reference.read_bytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": "sticks3-worker-reference.bin",
        },
    )
    with urlopen(req, timeout=60) as response:
        artifact = json.load(response)
    status, firmware = request(
        base,
        "/api/v1/firmware",
        method="POST",
        payload={
            "device_id": "sticks3",
            "kind": "merged",
            "artifact_id": artifact["artifact_id"],
        },
        timeout=60,
    )
    if status != 201:
        raise RuntimeError(f"firmware normalize returned {status}")
    if firmware["size"] != 8 << 20:
        raise RuntimeError("normalized firmware is not exactly 8 MiB")
    return firmware


def wait_for(
    predicate,
    *,
    timeout: float,
    interval: float = 0.2,
    label: str,
) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as error:
            last_error = error
        time.sleep(interval)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"timed out waiting for {label}{detail}")


def stop_process_group(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


def start_service(
    *,
    port: int,
    state_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> subprocess.Popen:
    stdout = stdout_path.open("wb")
    stderr = stderr_path.open("wb")
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(SERVICE),
                str(port),
                "--bind",
                "127.0.0.1",
                "--state-dir",
                str(state_dir),
                "--worker-id",
                "worker-lab",
                "--worker-heartbeat-interval",
                "0.2",
                "--worker-stale-after",
                "2",
                "--session-ttl",
                "300",
            ],
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    finally:
        stdout.close()
        stderr.close()
    return process


def wait_ready(base: str, *, timeout: float = 20) -> dict[str, Any]:
    def check() -> dict[str, Any] | None:
        status, worker = request(base, "/api/v1/worker")
        if status == 200 and worker.get("state") == "ready":
            return worker
        return None

    return wait_for(check, timeout=timeout, label="worker ready")


def wait_session_running(
    base: str,
    session_id: str,
    *,
    timeout: float = 90,
) -> dict[str, Any]:
    def check() -> dict[str, Any] | None:
        status, session = request(
            base,
            f"/api/v1/sessions/{session_id}",
        )
        if status != 200:
            return None
        if session.get("state") == "failed":
            raise RuntimeError(
                f"session failed before running: {session.get('error')}"
            )
        return session if session.get("state") == "running" else None

    return wait_for(check, timeout=timeout, label="QEMU session running")


def wait_frame(
    base: str,
    session_id: str,
    *,
    timeout: float = 60,
) -> bytes:
    def check() -> bytes | None:
        png = frame(base, session_id)
        return png if png.startswith(b"\x89PNG") and len(png) > 1024 else None

    return wait_for(check, timeout=timeout, label="QEMU framebuffer")


def qemu_processes_for_session(session_id: str) -> list[str]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if session_id in line and "qemu-system-" in line
    ]


def create_session(base: str, firmware_id: str) -> dict[str, Any]:
    status, session = request(
        base,
        "/api/v1/sessions",
        method="POST",
        payload={
            "device_id": "sticks3",
            "firmware_id": firmware_id,
            "runtime": "qemu-wifi",
            "ttl_seconds": 300,
            "owner": "worker-lifecycle-fixture",
            "network": {
                "profile": "uiflow2-sticks3-wifi",
                "capture_pcap": True,
            },
        },
    )
    if status != 202:
        raise RuntimeError(f"session create returned {status}")
    return session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    state_dir = out / "state"
    processes: list[subprocess.Popen] = []
    started = time.monotonic()
    checks: dict[str, bool] = {}
    first_worker: dict[str, Any] = {}
    first_session: dict[str, Any] = {}
    second_session: dict[str, Any] = {}
    restarted_worker: dict[str, Any] = {}
    restored_session: dict[str, Any] = {}
    frame_sha256 = None
    pcap_retained = False
    try:
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        service = start_service(
            port=port,
            state_dir=state_dir,
            stdout_path=out / "service-1.stdout",
            stderr_path=out / "service-1.stderr",
        )
        processes.append(service)
        first_worker = wait_ready(base, timeout=20)
        checks["worker_ready"] = first_worker["state"] == "ready"
        checks["heartbeat_fresh"] = not first_worker["stale"]
        checks["worker_identity_stable"] = first_worker["worker_id"] == "worker-lab"
        firmware = upload_reference_firmware(base)
        checks["reference_normalized"] = firmware["size"] == 8 << 20

        first_session = create_session(base, firmware["firmware_id"])
        first_session_id = first_session["session_id"]
        first_session = wait_session_running(
            base,
            first_session_id,
            timeout=args.timeout,
        )
        active_worker = request(base, "/api/v1/worker")[1]
        checks["active_lease_visible"] = (
            first_session_id in active_worker["active_lease_ids"]
        )

        status, draining = request(
            base,
            "/api/v1/worker/drain",
            method="POST",
            payload={},
        )
        checks["drain_state"] = (
            status == 200
            and draining["worker"]["state"] == "draining"
            and draining["worker"]["active_lease_count"] == 1
        )
        rejected_status, rejected = request_error(
            base,
            "/api/v1/sessions",
            method="POST",
            payload={
                "device_id": "sticks3",
                "runtime": "qemu",
                "ttl_seconds": 300,
            },
        )
        checks["drain_blocks_new_lease"] = (
            rejected_status == 503
            and rejected.get("error", {}).get("code")
            == "worker_not_accepting"
        )

        active_frame = wait_frame(
            base,
            first_session_id,
            timeout=args.timeout,
        )
        frame_sha256 = hashlib.sha256(active_frame).hexdigest()
        active_qemu = qemu_processes_for_session(first_session_id)
        checks["active_session_survives_drain"] = (
            len(active_frame) > 1024
            and any(
                first_session_id in command for command in active_qemu
            )
        )

        status, stopped = request(
            base,
            f"/api/v1/sessions/{first_session_id}/stop",
            method="POST",
            payload={},
        )
        drained_worker = request(base, "/api/v1/worker")[1]
        checks["drained_after_last_lease"] = (
            status == 200
            and stopped["state"] == "stopped"
            and drained_worker["state"] == "drained"
            and drained_worker["active_lease_count"] == 0
        )
        lease_result = next(
            (
                item
                for item in drained_worker.get("recent_results", [])
                if item.get("lease_id") == first_session_id
            ),
            {},
        )
        checks["lease_result_recorded"] = lease_result.get("state") == "stopped"
        pcap_retained = (
            lease_result.get("network_pcap_available") is True
        )
        checks["pcap_result_recorded"] = pcap_retained

        status, resumed = request(
            base,
            "/api/v1/worker/resume",
            method="POST",
            payload={},
        )
        checks["resume_ready"] = (
            status == 200 and resumed["worker"]["state"] == "ready"
        )

        second_session = create_session(base, firmware["firmware_id"])
        second_session_id = second_session["session_id"]
        second_session = wait_session_running(
            base,
            second_session_id,
            timeout=args.timeout,
        )
        wait_for(
            lambda: bool(qemu_processes_for_session(second_session_id)),
            timeout=20,
            label="second QEMU process",
        )
        try:
            os.killpg(service.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        service.wait(timeout=10)
        wait_for(
            lambda: not qemu_processes_for_session(second_session_id),
            timeout=20,
            label="crashed QEMU process cleanup",
        )
        checks["process_group_cleanup"] = True

        restarted_port = free_port()
        restarted_base = f"http://127.0.0.1:{restarted_port}"
        restarted = start_service(
            port=restarted_port,
            state_dir=state_dir,
            stdout_path=out / "service-2.stdout",
            stderr_path=out / "service-2.stderr",
        )
        processes.append(restarted)
        restarted_worker = wait_ready(restarted_base, timeout=20)
        checks["generation_advanced"] = restarted_worker["generation"] == 2
        checks["abandoned_lease_recorded"] = any(
            item.get("lease_id") == second_session_id
            and item.get("reason") == "worker process restarted"
            for item in restarted_worker.get("abandoned_leases", [])
        )
        restored_session = request(
            restarted_base,
            f"/api/v1/sessions/{second_session_id}",
        )[1]
        checks["interrupted_session_failed"] = (
            restored_session["state"] == "failed"
            and restored_session["restored"]
            and restored_session["interrupted"]
            and "service restarted" in str(restored_session.get("error"))
        )
        checks["restart_has_no_active_lease"] = (
            restarted_worker["active_lease_count"] == 0
        )
    finally:
        for process in reversed(processes):
            stop_process_group(process)

    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-local-worker-lifecycle",
        "scope": "virtual-device-worker-control-not-remote-scheduler",
        "date": "2026-10-24",
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "worker": {
            "initial": {
                key: first_worker.get(key)
                for key in (
                    "worker_id",
                    "instance_id",
                    "generation",
                    "state",
                    "accepting_leases",
                )
            },
            "restarted": {
                **{
                    key: restarted_worker.get(key)
                    for key in (
                        "worker_id",
                        "instance_id",
                        "generation",
                        "state",
                        "accepting_leases",
                    )
                },
                "abandoned_lease_count": len(
                    restarted_worker.get("abandoned_leases", [])
                ),
                "abandoned_lease_id_sha256": [
                    hashlib.sha256(str(item.get("lease_id", "")).encode()).hexdigest()
                    for item in restarted_worker.get("abandoned_leases", [])
                ],
            },
        },
        "sessions": {
            "first": {
                "id_sha256": hashlib.sha256(
                    str(first_session.get("session_id", "")).encode()
                ).hexdigest(),
                "state": first_session.get("state"),
                "runtime": first_session.get("runtime"),
                "firmware_sha256": first_session.get("firmware_sha256"),
                "network_status": stopped.get("network", {}).get("status"),
                "network_pcap_available": pcap_retained,
                "frame_sha256": frame_sha256,
            },
            "restored_after_crash": {
                "id_sha256": hashlib.sha256(
                    str(second_session.get("session_id", "")).encode()
                ).hexdigest(),
                "state": restored_session.get("state"),
                "restored": restored_session.get("restored"),
                "interrupted": restored_session.get("interrupted"),
                "error": restored_session.get("error"),
            },
        },
        "not_claimed": [
            "remote worker registration",
            "task queueing or multi-host scheduling",
            "active QEMU process re-attach",
            "warm pool behavior",
            "physical hardware",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
