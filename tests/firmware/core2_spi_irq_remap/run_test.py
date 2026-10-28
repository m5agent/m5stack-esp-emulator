#!/usr/bin/env python3
"""Validate Core2 SPI completion when an IRQ mapping changes while pending."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVE = ROOT / "platform/tools/serve.py"
DEFAULT_QEMU = (
    ROOT
    / ".work/uiflow-apisweep-runtime/source/build/qemu-system-xtensa"
)
DEFAULT_IMAGE_SHA256 = (
    "1f4d1b405425f093c40459e31e3e3c643e4ac49ccd529b9018a7dc346470faf9"
)
DEFAULT_ELF_SHA256 = (
    "00d946fe3f6ca6a5bf431a609afa32beb8c71fc4ea753baa9e6920cb4ed3387d"
)


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: float = 60,
    ) -> tuple[int, bytes, str]:
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:2000]
            raise RuntimeError(
                f"{path} returned HTTP {error.code}: {detail}"
            ) from error

    def json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        data = None
        content_type = None
        if payload is not None:
            data = json.dumps(payload).encode()
            content_type = "application/json"
        status, body, _ = self.request(
            path,
            method=method,
            data=data,
            content_type=content_type,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise RuntimeError(f"{path} returned HTTP {status}")
        return json.loads(body)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(api: Api, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Device Service exited during startup with {process.returncode}"
            )
        try:
            status, _, _ = api.request("/api/health", timeout=2)
            if status == 200:
                return
        except (OSError, RuntimeError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Device Service did not become healthy")


def stop_service(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def collect_serial(
    api: Api,
    session_id: str,
    *,
    timeout: float,
) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + timeout
    running: dict[str, Any] = {}
    serial = ""
    while time.monotonic() < deadline:
        running = api.json(f"/api/v1/sessions/{session_id}")
        payload = api.json(
            f"/api/v1/sessions/{session_id}/serial?offset=0&limit=65536"
        )
        serial = str(payload.get("data") or "")
        if (
            "CORE2_SPI_IRQ_REMAP_PASS" in serial
            or "CORE2_SPI_IRQ_REMAP_FAIL" in serial
        ):
            break
        if running.get("state") in {"failed", "stopped"}:
            break
        time.sleep(0.25)
    return running, serial


def classify(serial: str) -> dict[str, Any]:
    pass_count = serial.count("CORE2_SPI_IRQ_REMAP_PASS")
    callback_count = serial.count("CORE2_SPI_IRQ_REMAP_CALLBACK_OK")
    result_count = serial.count("CORE2_SPI_IRQ_REMAP_RESULT_OK")
    fail_count = serial.count("CORE2_SPI_IRQ_REMAP_FAIL")
    return {
        "status": (
            "PASS"
            if pass_count == 1
            and callback_count == 1
            and result_count == 1
            and fail_count == 0
            else "FAIL"
        ),
        "queue_observed": "CORE2_SPI_IRQ_REMAP_QUEUE_OK" in serial,
        "callback_count": callback_count,
        "result_count": result_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
    }


def run_attempt(
    api: Api,
    firmware_id: str,
    out_dir: Path,
    *,
    timeout: float,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    session_id = ""
    try:
        created = api.json(
            "/api/v1/sessions",
            method="POST",
            payload={
                "device_id": "core2",
                "firmware_id": firmware_id,
                "runtime": "qemu",
                "ttl_seconds": 180,
            },
        )
        session_id = str(created["session_id"])
        observed, serial = collect_serial(api, session_id, timeout=timeout)
        (out_dir / "serial.log").write_text(serial)

        status, evidence, _ = api.request(
            f"/api/v1/sessions/{session_id}/evidence"
            "?include=manifest,serial,logs",
            timeout=timeout,
        )
        if evidence:
            (out_dir / "evidence.zip").write_bytes(evidence)

        result = classify(serial)
        result.update(
            {
                "session_id_sha256": hashlib.sha256(
                    session_id.encode()
                ).hexdigest(),
                "session_state": observed.get("state"),
                "evidence_zip": (
                    status == 200 and evidence.startswith(b"PK\x03\x04")
                ),
            }
        )
        return result
    finally:
        if session_id:
            try:
                api.json(
                    f"/api/v1/sessions/{session_id}?purge=0",
                    method="DELETE",
                    payload={},
                )
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument(
        "--expected-image-sha256", default=DEFAULT_IMAGE_SHA256
    )
    parser.add_argument("--expected-elf-sha256", default=DEFAULT_ELF_SHA256)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 10:
        parser.error("--attempts must be from 1 to 10")
    image_sha256 = sha256_file(args.image)
    elf_sha256 = sha256_file(args.elf)
    if image_sha256 != args.expected_image_sha256:
        parser.error(
            f"image SHA256 mismatch: expected {args.expected_image_sha256}, "
            f"got {image_sha256}"
        )
    if elf_sha256 != args.expected_elf_sha256:
        parser.error(
            f"ELF SHA256 mismatch: expected {args.expected_elf_sha256}, "
            f"got {elf_sha256}"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    state_dir = args.out_dir / "service-state"
    port = free_port()
    api = Api(f"http://127.0.0.1:{port}")
    env = os.environ.copy()
    env.update(
        {
            "M5_QEMU_XTENSA": str(args.qemu),
            "M5_CORE2_RADIO_QEMU": str(args.qemu),
        }
    )
    service_log = (args.out_dir / "device-service.log").open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVE),
            str(port),
            "--bind",
            "127.0.0.1",
            "--state-dir",
            str(state_dir),
            "--max-sessions",
            "1",
            "--max-per-device",
            "1",
            "--session-ttl",
            "180",
        ],
        cwd=ROOT,
        env=env,
        stdout=service_log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_health(api, process, timeout=10)
        status, body, _ = api.request(
            "/api/v1/artifacts",
            method="POST",
            data=args.image.read_bytes(),
            content_type="application/octet-stream",
            timeout=120,
        )
        if status != 201:
            raise RuntimeError(f"artifact upload returned HTTP {status}")
        artifact = json.loads(body)
        firmware = api.json(
            "/api/v1/firmware",
            method="POST",
            payload={
                "device_id": "core2",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            },
        )
        runs = [
            run_attempt(
                api,
                str(firmware["firmware_id"]),
                args.out_dir / f"attempt-{attempt}",
                timeout=args.timeout,
            )
            for attempt in range(1, args.attempts + 1)
        ]
    finally:
        stop_service(process)
        service_log.close()
        shutil.rmtree(state_dir, ignore_errors=True)

    passed = sum(run["status"] == "PASS" for run in runs)
    result = {
        "schema_version": 1,
        "kind": "core2-spi-irq-remap",
        "validation": "virtual-device validation",
        "status": "PASS" if passed == args.attempts else "FAIL",
        "firmware_sha256": image_sha256,
        "elf_sha256": elf_sha256,
        "qemu_binary_sha256": sha256_file(args.qemu),
        "attempts_requested": args.attempts,
        "attempts_passed": passed,
        "runs": runs,
        "guest_path": (
            "ESP-IDF 5.5.4 spi_master queues a 16-byte SPI3 transaction; "
            "the guest remaps the pending SPI3 level IRQ before enabling it"
        ),
        "boundary": {
            "proven": [
                "SPI_SLAVE.TRANS_DONE and TRANS_INTEN level semantics",
                "interrupt-matrix remap while the source level is pending",
                "guest ISR post_callback and queued-transaction completion",
            ],
            "not_proven": [
                "physical ESP32 SPI DMA timing",
                "legacy UIFlow boot completion",
            ],
        },
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"evidence={evidence_path}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
