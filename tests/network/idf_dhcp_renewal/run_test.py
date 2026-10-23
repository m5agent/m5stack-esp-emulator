#!/usr/bin/env python3
"""Run the ESP-IDF DHCP renewal probe through Device Service."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from firmware_manifest import import_package  # noqa: E402


class RunnerError(RuntimeError):
    pass


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: object = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/{path.lstrip('/')}",
            data=body,
            headers=request_headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RunnerError("Device Service exited before readiness")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise RunnerError("Device Service did not become ready")


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: argparse.Namespace) -> dict:
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build_dir = args.build_dir.resolve()
    if not build_dir.is_dir():
        raise RunnerError(f"build directory is missing: {build_dir}")
    normalized = import_package(
        build_dir,
        out / "manifest",
        device_id="sticks3",
        flash_size=8 << 20,
        required_capabilities=["wifi"],
    )
    if normalized["manifest"]["validation"]["status"] != "PASS":
        raise RunnerError("DHCP renewal firmware manifest did not PASS")
    image = Path(normalized["image_path"])

    service_process: subprocess.Popen | None = None
    service_dir: tempfile.TemporaryDirectory | None = None
    if args.service_url:
        base_url = args.service_url
    else:
        port = free_tcp_port()
        service_dir = tempfile.TemporaryDirectory(
            prefix="m5-dhcp-renew-service-"
        )
        service_process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "platform/tools/serve.py"),
                str(port),
                "--state-dir",
                service_dir.name,
                "--max-sessions",
                "1",
                "--max-per-device",
                "1",
                "--session-ttl",
                "300",
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        wait_health(port, service_process)
        base_url = f"http://127.0.0.1:{port}"

    client = ServiceClient(base_url)
    session_id: str | None = None
    try:
        artifact = client.request(
            "artifacts",
            method="POST",
            body=image.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": "idf-dhcp-renewal.bin",
            },
        )
        firmware = client.request(
            "firmware",
            method="POST",
            payload={
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            },
        )
        session = client.request(
            "sessions",
            method="POST",
            payload={
                "device_id": "sticks3",
                "firmware_id": firmware["firmware_id"],
                "runtime": "qemu-wifi",
                "ttl_seconds": 180,
                "ready_timeout_seconds": 45,
                "network": {
                    "profile": "uiflow2-sticks3-wifi",
                    "attempts": 1,
                    "capture_pcap": True,
                    "expected_markers": [
                        "DHCP_RENEW_RESULT: PASSED"
                    ],
                },
            },
        )
        session_id = str(session["session_id"])
        deadline = time.monotonic() + args.timeout
        serial = ""
        last: dict = {}
        while time.monotonic() < deadline:
            last = client.request(f"sessions/{session_id}")
            logs = client.request(
                f"sessions/{session_id}/logs?offset=0&limit=262144"
            )
            serial = str(logs.get("data", ""))
            if "DHCP_RENEW_RESULT:" in serial:
                break
            if last.get("state") in {"failed", "stopped"}:
                break
            time.sleep(0.5)
        (out / "serial.log").write_text(serial)
        if "DHCP_RENEW_RESULT: PASSED" not in serial:
            raise RunnerError("DHCP renewal guest did not PASS")

        client.request(
            f"sessions/{session_id}?purge=0",
            method="DELETE",
        )
        network = client.request(f"sessions/{session_id}/network")
    finally:
        if session_id is not None:
            try:
                client.request(
                    f"sessions/{session_id}?purge=0",
                    method="DELETE",
                )
            except Exception as error:
                print(
                    f"DHCP renewal cleanup failed: {error}",
                    file=sys.stderr,
                )
        stop_process(service_process)
        if service_dir is not None:
            service_dir.cleanup()

    (out / "network.json").write_text(
        json.dumps(network, ensure_ascii=False, indent=2) + "\n"
    )
    dhcp = network.get("packet_capture", {}).get("dhcp", {})
    transactions = dhcp.get("transactions", [])
    renewal_transactions = [
        row for row in transactions if row.get("renewal") is True
    ]
    sequence = (
        renewal_transactions[0].get("message_sequence", [])
        if renewal_transactions
        else []
    )
    checks = {
        "serial_result_passed": "DHCP_RENEW_RESULT: PASSED" in serial,
        "serial_http_passed": "DHCP_RENEW_HTTP: PASSED" in serial,
        "manifest_roundtrip": (
            normalized["manifest"]["validation"]["status"] == "PASS"
        ),
        "dhcp_renewal_request_observed": (
            int(dhcp.get("renewal_requests") or 0) >= 1
        ),
        "dhcp_renewal_ack_observed": (
            int(dhcp.get("renewal_acks") or 0) >= 1
        ),
        "renewal_transaction_marked": bool(renewal_transactions),
        "renewal_sequence_request_ack": (
            len(sequence) >= 2
            and sequence[-2:] == ["REQUEST", "ACK"]
        ),
        "lease_seconds_observed": any(
            int(row.get("lease_seconds") or 0) > 0
            for row in transactions
        ),
        "pcap_written": bool(network.get("packet_capture")),
        "dhcp_address_preserved": (
            dhcp.get("guest_addresses") == ["10.0.2.15"]
        ),
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-idf-dhcp-renewal",
        "date": "2026-10-24",
        "scope": "virtual-device-dhcp-renewal-not-hardware-rf",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "session": {
            "session_id": session_id,
            "runtime": "qemu-wifi",
            "profile": "uiflow2-sticks3-wifi",
            "state": last.get("state"),
        },
        "firmware": {
            "image_sha256": sha256(image),
            "manifest_id": normalized["manifest"]["manifest_id"],
            "source_format": normalized["manifest"]["provenance"][
                "source_format"
            ],
        },
        "dhcp": dhcp,
        "not_claimed": [
            "physical AP loss or RF behavior",
            "WPA2/WPA3 security",
            "physical hardware",
            "malicious-firmware safety",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=ROOT / "tests/network/idf_dhcp_renewal/build_esp32s3",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--service-url")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    try:
        evidence = run(args)
    except (OSError, RunnerError, RuntimeError) as error:
        print(f"DHCP renewal test failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
