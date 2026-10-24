#!/usr/bin/env python3
"""Run radio loss/recovery through Device Service and emit audited evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE = ROOT / "platform/.cache/firmware/sticks3/uiflow2.bin"
DEFAULT_BUILD = (
    ROOT / ".work/uiflow-core2-2.5.3/m5stack/build-M5STACK_StickS3-unified"
)
DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
FINAL_MARKER = "RECONNECT RESULT: PASSED"


class RunnerError(RuntimeError):
    pass


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 180):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request_bytes(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: object = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
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
            return response.read()

    def request(self, path: str, **kwargs: Any) -> object:
        raw = self.request_bytes(path, **kwargs)
        return json.loads(raw) if raw else {}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def free_tcp_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(base_url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RunnerError("Device Service exited before readiness")
        try:
            with urllib.request.urlopen(
                f"{base_url}/health", timeout=1
            ) as response:
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


def prepare_image(args: argparse.Namespace, building: Path) -> Path:
    if args.image is not None:
        if not args.image.is_file():
            raise RunnerError(f"image does not exist: {args.image}")
        return args.image.resolve()
    for label, path in (
        ("base image", args.base_image),
        ("unified build directory", args.build_dir),
    ):
        if not path.exists():
            raise RunnerError(f"{label} does not exist: {path}")
    unified = building / "sticks3-unified.bin"
    patched = building / "reconnect"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(ROOT / ".work/py"),
                env.get("PYTHONPATH", ""),
            ],
        )
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/uiflow2/unified_sticks3/make_image.py"),
            "--base",
            str(args.base_image),
            "--build-dir",
            str(args.build_dir),
            "--out",
            str(unified),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/uiflow2/run_profile_ui_test.py"),
            "--base",
            str(unified),
            "--machine",
            "m5sticks3",
            "--files-dir",
            str(Path(__file__).parent),
            "--vfs-offset",
            "0x641000",
            "--vfs-size",
            "0x1BE000",
            "--flash-size",
            "0x800000",
            "--expected-size",
            "135x240",
            "--efuse-pkg-version",
            "1",
            "--out-dir",
            str(patched),
            "--build-only",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    image = patched / "uiflow2-ui-test.bin"
    if not image.is_file():
        raise RunnerError("reconnect image build produced no output")
    return image


def qom_read(client: ServiceClient, session_id: str, path: str) -> Any:
    query = urllib.parse.urlencode(
        {"path": path, "property": "radio-enabled"}
    )
    response = client.request(f"sessions/{session_id}/qom?{query}")
    return response.get("value")


def fault_body(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("network_fault", response)
    return value if isinstance(value, dict) else {}


def run_session(
    client: ServiceClient,
    image: Path,
    timeout: float,
) -> tuple[str, dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    artifact = client.request(
        "artifacts",
        method="POST",
        body=image.read_bytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": "sticks3-reconnect.bin",
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
            "ttl_seconds": 300,
            "ready_timeout_seconds": 60,
            "network": {
                "profile": "uiflow2-sticks3-wifi",
                "attempts": 1,
                "capture_pcap": True,
                "expected_markers": [FINAL_MARKER],
            },
        },
    )
    session_id = str(session["session_id"])
    deadline = time.monotonic() + timeout
    serial = ""
    session_state: dict[str, Any] = {}
    down: dict[str, Any] = {}
    up: dict[str, Any] = {}
    down_qom: Any = None
    up_qom: Any = None
    try:
        while time.monotonic() < deadline:
            session_state = client.request(f"sessions/{session_id}")
            logs = client.request(
                f"sessions/{session_id}/logs?offset=0&limit=262144"
            )
            serial = str(logs.get("data", ""))
            if "RECONNECT DISCONNECTED" in serial and not down:
                down = client.request(
                    f"sessions/{session_id}/network-fault",
                    method="POST",
                    payload={"action": "down", "target": "radio"},
                )
                path = fault_body(down).get("qom_path")
                if isinstance(path, str):
                    down_qom = qom_read(client, session_id, path)
            if "RECONNECT RADIO_DOWN_SCAN 0" in serial and not up:
                up = client.request(
                    f"sessions/{session_id}/network-fault",
                    method="POST",
                    payload={"action": "up", "target": "radio"},
                )
                path = fault_body(up).get("qom_path")
                if isinstance(path, str):
                    up_qom = qom_read(client, session_id, path)
            if FINAL_MARKER in serial or "RECONNECT RESULT: FAILED" in serial:
                break
            if session_state.get("state") in {"failed", "stopped"}:
                break
            time.sleep(0.2)
        if FINAL_MARKER not in serial:
            raise RunnerError("reconnect probe did not reach PASSED")
    finally:
        final_session = client.request(
            f"sessions/{session_id}?purge=0",
            method="DELETE",
        )
    network = client.request(f"sessions/{session_id}/network")
    return session_id, {
        "down": down,
        "up": up,
        "down_qom": down_qom,
        "up_qom": up_qom,
    }, network, serial, final_session


def parse_evidence(
    image: Path,
    qemu: Path,
    fault: dict[str, Any],
    network: dict[str, Any],
    serial: str,
    session_state: dict[str, Any],
) -> dict[str, Any]:
    scan = [int(value) for value in re.findall(r"RECONNECT SCAN (\d+)", serial)]
    down_scan = [
        int(value)
        for value in re.findall(r"RECONNECT RADIO_DOWN_SCAN (\d+)", serial)
    ]
    restored_scan = [
        int(value)
        for value in re.findall(
            r"RECONNECT RADIO_RESTORED_SCAN (\d+)", serial
        )
    ]
    dhcp = network.get("packet_capture", {}).get("dhcp", {})
    http_requests = network.get("http_requests", [])
    dhcp_types = dhcp.get("message_types", dhcp)
    flows = network.get("packet_capture", {}).get("flows", [])
    controlled_http_flows = [
        flow
        for flow in flows
        if flow.get("protocol") == "TCP"
        and str(flow.get("destination", "")).endswith(":18080")
        and int(flow.get("payload_bytes") or 0) > 0
    ]
    controlled_http_count = max(
        len(http_requests),
        len(controlled_http_flows),
    )
    checks = {
        "initial_scan_nonempty": bool(scan and scan[0] > 0),
        "first_dhcp_lease": bool(
            re.search(r"RECONNECT DHCP 1 10\.0\.2\.\d+", serial)
        ),
        "before_http_status_200": bool(
            re.search(
                r"RECONNECT HTTP /before b?'HTTP/1\.0 200 OK",
                serial,
            )
        ),
        "radio_down_signal": bool(fault.get("down")),
        "radio_down_state_false": fault.get("down_qom") is False,
        "radio_down_scan_empty": down_scan == [0],
        "radio_up_signal": bool(fault.get("up")),
        "radio_up_state_true": fault.get("up_qom") is True,
        "radio_restored_scan_nonempty": bool(
            restored_scan and restored_scan[0] > 0
        ),
        "second_dhcp_lease": bool(
            re.search(r"RECONNECT DHCP 2 10\.0\.2\.\d+", serial)
        ),
        "after_http_status_200": bool(
            re.search(
                r"RECONNECT HTTP /after b?'HTTP/1\.0 200 OK",
                serial,
            )
        ),
        "network_marker_pass": FINAL_MARKER in serial,
        "pcap_pass": network.get("packet_capture", {}).get("status") == "PASS",
        "pcap_two_dhcp_exchanges": all(
            int(dhcp_types.get(key) or 0) >= 2
            for key in ("discover", "offer", "request", "ack")
        ),
        "pcap_two_http_requests": controlled_http_count == 2,
        "lease_address_stable": dhcp.get("guest_addresses")
        == ["10.0.2.15"],
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema_version": 1,
        "kind": "m5stack-sticks3-radio-loss-recovery",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "virtual-device-network-radio-not-hardware-rf",
        "status": status,
        "source": {
            "repository": "https://github.com/m5agent/m5stack-esp-emulator",
            "base_commit": git_value("rev-parse", "HEAD"),
            "working_tree_dirty": bool(git_value("status", "--porcelain")),
        },
        "validation": {
            "device_id": "sticks3",
            "runtime": "qemu-wifi",
            "profile": "uiflow2-sticks3-wifi",
            "qemu_sha256": sha256_file(qemu),
            "firmware_sha256": sha256_file(image),
            "firmware_bytes": image.stat().st_size,
            "serial_sha256": sha256_bytes(serial.encode()),
            "final_state": session_state.get("state"),
        },
        "fault": {
            "target": "radio",
            "qom_path": fault_body(fault.get("down", {})).get("qom_path"),
            "property": "radio-enabled",
            "down_value": fault.get("down_qom"),
            "up_value": fault.get("up_qom"),
        },
        "checks": checks,
        "packet_capture": {
            "status": network.get("packet_capture", {}).get("status"),
            "bytes": network.get("packet_capture", {}).get("input", {}).get(
                "bytes"
            ),
            "sha256": network.get("packet_capture", {})
            .get("input", {})
            .get("sha256"),
            "dhcp": dhcp,
            "controlled_http_before_after": controlled_http_count,
        },
        "serial_markers": [
            "RECONNECT SCAN 1",
            "RECONNECT DHCP 1 <guest-address>",
            "RECONNECT HTTP /before HTTP/1.0 200 OK",
            "RECONNECT DISCONNECTED",
            "RECONNECT RADIO_DOWN_SCAN 0",
            "RECONNECT RADIO_RESTORED_SCAN 1",
            "RECONNECT DHCP 2 <guest-address>",
            "RECONNECT HTTP /after HTTP/1.0 200 OK",
            FINAL_MARKER,
        ],
        "not_claimed": [
            "physical RF or antenna behavior",
            "WPA2 or WPA3 security",
            "a different DHCP server or lease address",
            "hardware timing or power",
            "malware safety",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    parser.add_argument("--base-image", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--service-url")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    service_process: subprocess.Popen | None = None
    service_dir: tempfile.TemporaryDirectory | None = None
    build_dir: tempfile.TemporaryDirectory | None = None
    try:
        if args.service_url:
            base_url = args.service_url
        else:
            port = free_tcp_port()
            service_dir = tempfile.TemporaryDirectory(
                prefix="m5-reconnect-service-"
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
            base_url = f"http://127.0.0.1:{port}"
            wait_health(base_url, service_process)
        build_dir = tempfile.TemporaryDirectory(
            prefix="m5-reconnect-build-"
        )
        image = prepare_image(args, Path(build_dir.name))
        client = ServiceClient(base_url)
        _, fault, network, serial, session_state = run_session(
            client,
            image,
            args.timeout,
        )
        (out / "serial.log").write_text(serial)
        evidence = parse_evidence(
            image,
            args.qemu,
            fault,
            network,
            serial,
            session_state,
        )
        (out / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            f"status={evidence['status']} "
            f"firmware_sha256={evidence['validation']['firmware_sha256']} "
            f"pcap_bytes={evidence['packet_capture']['bytes']}"
        )
        return 0 if evidence["status"] == "PASS" else 1
    except (OSError, RunnerError, subprocess.CalledProcessError) as error:
        print(f"reconnect test failed: {error}", file=sys.stderr)
        return 1
    finally:
        stop_process(service_process)
        if service_dir is not None:
            service_dir.cleanup()
        if build_dir is not None:
            build_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
