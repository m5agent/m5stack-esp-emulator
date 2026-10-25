#!/usr/bin/env python3
"""Prove a firmware-guest CNAME-to-HTTP lifecycle through Device Service."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PROBE = Path(__file__).resolve().parent
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
DEVICE_SERVICE = ROOT / "platform/tools/serve.py"
DEFAULT_BASE = ROOT / "platform/.cache/firmware/sticks3/uiflow2.bin"
DEFAULT_QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu-linux-arm64/qemu-system-xtensa"
DEFAULT_ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu-linux-arm64/pc-bios"
ALIAS = "alias.cname.test"
TERMINAL = "origin.cname.test"
DENIED = "denied.cname.test"
TERMINAL_IP = "10.0.2.2"
HTTP_PORT = 18080
DENIED_PORT = 18081
MARKERS = (
    "CNAME_GUEST_WIFI_READY",
    "CNAME_GUEST_RESOLVED 10.0.2.2",
    "CNAME_GUEST_HTTP PASS",
    "CNAME_GUEST_DENIED_NAME PASS",
    "CNAME_GUEST_DENIED_PORT BLOCKED",
    "CNAME_GUEST_RESULT PASS",
)
FINAL_MARKER = MARKERS[-1]


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
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RunnerError(
                f"{method} {path} returned HTTP {error.code}: {detail}"
            ) from error

    def request(self, path: str, **kwargs: Any) -> object:
        raw = self.request_bytes(path, **kwargs)
        return json.loads(raw) if raw else {}


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


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_health(base_url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RunnerError("Device Service exited before readiness")
        try:
            with urllib.request.urlopen(
                f"{base_url}/api/health",
                timeout=1,
            ) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise RunnerError("Device Service did not become ready")


def build_probe(out: Path, base_image: Path) -> Path:
    generated = out / "probe-files"
    generated.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROBE / "boot.py", generated / "boot.py")
    shutil.copyfile(PROBE / "main.py", generated / "main.py")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(ROOT / ".work/py"),
                environment.get("PYTHONPATH", ""),
            ],
        )
    )
    subprocess.run(
        [
            sys.executable,
            str(PROFILE_RUNNER),
            "--base",
            str(base_image),
            "--machine",
            "m5sticks3",
            "--files-dir",
            str(generated),
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
            str(out / "build"),
            "--build-only",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        timeout=120,
    )
    image = out / "build/uiflow2-ui-test.bin"
    if not image.is_file():
        raise RunnerError("CNAME guest probe image was not created")
    result = out / "probe.bin"
    shutil.copyfile(image, result)
    return result


def read_archive_json(archive: zipfile.ZipFile, name: str) -> Any:
    if name not in archive.namelist():
        return None
    return json.loads(archive.read(name))


def run_service_session(
    *,
    image: Path,
    qemu: Path,
    rom_dir: Path,
    out: Path,
    timeout: float,
) -> dict[str, Any]:
    port = free_tcp_port()
    base_url = f"http://127.0.0.1:{port}"
    state_dir = out / "service-state"
    log_path = out / "device-service.log"
    environment = os.environ.copy()
    environment.update(
        {
            "M5_QEMU_XTENSA": str(qemu),
            "M5_QEMU_XTENSA_ROM_DIR": str(rom_dir),
            "M5_SERVICE_FLASH_MODE": "host-image",
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    [
                        str(ROOT / "platform/tools"),
                        environment.get("PYTHONPATH", ""),
                    ],
                )
            ),
        }
    )
    process: subprocess.Popen | None = None
    session_id: str | None = None
    serial = ""
    last_session: dict[str, Any] = {}
    network: dict[str, Any] = {}
    final_session: dict[str, Any] = {}
    evidence_zip: bytes = b""
    try:
        log = log_path.open("wb")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(DEVICE_SERVICE),
                    "--bind",
                    "127.0.0.1",
                    "--state-dir",
                    str(state_dir),
                    "--max-sessions",
                    "2",
                    "--max-per-device",
                    "1",
                    str(port),
                ],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log.close()
        wait_health(base_url, process)
        client = ServiceClient(base_url)
        artifact = client.request(
            "artifacts",
            method="POST",
            body=image.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": "sticks3-cname-guest.bin",
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
        created = client.request(
            "sessions",
            method="POST",
            payload={
                "device_id": "sticks3",
                "firmware_id": firmware["firmware_id"],
                "runtime": "qemu-wifi",
                "ttl_seconds": max(180, int(timeout) + 60),
                "ready_timeout_seconds": timeout,
                "network": {
                    "profile": "uiflow2-sticks3-wifi",
                    "attempts": 1,
                    "capture_pcap": True,
                    "expected_markers": list(MARKERS),
                    "policy": {
                        "isolation": "namespace",
                        "egress": "allowlist",
                        "dns": "controlled",
                        "allowed_hosts": [ALIAS, TERMINAL],
                        "allowed_endpoints": [
                            {
                                "protocol": "tcp",
                                "address": TERMINAL_IP,
                                "port": HTTP_PORT,
                            }
                        ],
                    },
                    "cname_records": {ALIAS: TERMINAL},
                },
            },
        )
        session_id = str(created["session_id"])
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            last_session = client.request(f"sessions/{session_id}")
            logs = client.request(f"sessions/{session_id}/logs?offset=0&limit=262144")
            serial = str(logs.get("data", ""))
            if FINAL_MARKER in serial:
                break
            if last_session.get("state") in {"failed", "stopped"}:
                break
            if "CNAME_GUEST_ERROR" in serial:
                break
            time.sleep(0.25)
        network = client.request(f"sessions/{session_id}/network")
        final_session = client.request(
            f"sessions/{session_id}?purge=0",
            method="DELETE",
        )
        evidence_zip = client.request_bytes(
            f"sessions/{session_id}/evidence?include=manifest,serial,logs,network",
        )
        (out / "service-evidence.zip").write_bytes(evidence_zip)
        network = client.request(f"sessions/{session_id}/network")
    finally:
        stop_process(process)
    return {
        "serial": serial,
        "session": last_session,
        "final_session": final_session,
        "network": network,
        "evidence_zip": evidence_zip,
        "service_log": (
            log_path.read_text(errors="replace") if log_path.is_file() else ""
        ),
    }


def archive_evidence(archive_bytes: bytes) -> dict[str, Any]:
    if not archive_bytes:
        return {}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        return {
            "manifest": read_archive_json(archive, "manifest.json") or {},
            "network": read_archive_json(
                archive,
                "network/evidence.json",
            )
            or {},
            "dns_requests": read_archive_json(
                archive,
                "network/dns-requests.json",
            )
            or [],
            "http_requests": read_archive_json(
                archive,
                "network/http-fixture.json",
            )
            or [],
            "isolation": read_archive_json(
                archive,
                "network/isolation.json",
            )
            or {},
            "pcap_summary": read_archive_json(
                archive,
                "network/pcap-summary.json",
            )
            or {},
            "names": sorted(archive.namelist()),
        }


def sanitize_serial(serial: str) -> str:
    lines = []
    for line in serial.splitlines()[-100:]:
        if "CNAME_GUEST_WIFI_READY" in line:
            line = "CNAME_GUEST_WIFI_READY <redacted>"
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--base-image", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--prebuilt-image", type=Path)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM_DIR)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.prebuilt_image is not None:
        if not args.prebuilt_image.is_file():
            parser.error("--prebuilt-image must exist")
        image = args.prebuilt_image.resolve()
        probe_source = "prebuilt"
    else:
        if not args.base_image.is_file():
            parser.error("--base-image must exist")
        image = build_probe(out, args.base_image.resolve())
        probe_source = "generated"
    if args.build_only:
        print(json.dumps({"probe_image": str(image)}, indent=2))
        return 0
    if not args.qemu.is_file() or not args.rom_dir.is_dir():
        parser.error("--qemu and --rom-dir must exist")

    started = time.monotonic()
    run = run_service_session(
        image=image,
        qemu=args.qemu.resolve(),
        rom_dir=args.rom_dir.resolve(),
        out=out,
        timeout=args.timeout,
    )
    serial = str(run["serial"])
    session = run["session"]
    final_session = run["final_session"]
    network = run["network"]
    archived = archive_evidence(run["evidence_zip"])
    dns_requests = archived.get("dns_requests", [])
    http_requests = archived.get("http_requests", [])
    isolation = archived.get("isolation", {})
    pcap_summary = archived.get("pcap_summary", {})
    chain_row = next(
        (
            row
            for row in dns_requests
            if row.get("name") == ALIAS and row.get("qtype") == "1"
        ),
        {},
    )
    denied_row = next(
        (
            row
            for row in dns_requests
            if row.get("name") == DENIED and row.get("qtype") == "1"
        ),
        {},
    )
    destinations = pcap_summary.get("egress_destinations", [])
    checks = {
        "wifi_ready": "CNAME_GUEST_WIFI_READY" in serial,
        "guest_resolved_terminal": (f"CNAME_GUEST_RESOLVED {TERMINAL_IP}" in serial),
        "guest_http": "CNAME_GUEST_HTTP PASS" in serial,
        "guest_denied_name": "CNAME_GUEST_DENIED_NAME PASS" in serial,
        "guest_denied_port": "CNAME_GUEST_DENIED_PORT BLOCKED" in serial,
        "guest_result": FINAL_MARKER in serial,
        "cname_alias_query": (
            chain_row.get("decision") == "allow"
            and chain_row.get("cname_terminal") == TERMINAL
            and len(chain_row.get("cname_chain", [])) == 1
        ),
        "cname_terminal_a": (
            chain_row.get("status") == "A"
            and chain_row.get("rule") == f"exact:{TERMINAL}"
        ),
        "denied_name_nxdomain": (
            denied_row.get("decision") == "deny"
            and denied_row.get("status") == "NXDOMAIN"
        ),
        "http_fixture_request": any(
            str(row.get("host", "")).rsplit(":", 1)[0] == ALIAS
            and row.get("decision") == "allow"
            and row.get("status") == "200"
            for row in http_requests
        ),
        "pcap_allowed_http": any(
            row.get("address") == TERMINAL_IP
            and row.get("port") == HTTP_PORT
            and "TCP" in row.get("protocols", [])
            for row in destinations
        ),
        "pcap_denied_port": any(
            row.get("address") == TERMINAL_IP and row.get("port") == DENIED_PORT
            for row in destinations
        ),
        "service_cname_check": (
            network.get("checks", {}).get("dns:cname_chain") is True
        ),
        "service_http_check": (
            network.get("checks", {}).get("http:controlled_request") is True
        ),
        "private_namespace": (isolation.get("private_network_namespace") is True),
        "no_external_route": isolation.get("external_route") is False,
        "cleanup_completed": (
            isolation.get("cleanup_completed") is True
            and isolation.get("qemu_process_reaped") is True
            and isolation.get("dns_closed") is True
            and isolation.get("http_closed") is True
        ),
        "session_stopped": final_session.get("state") == "stopped",
        "evidence_archive_complete": all(
            name in archived.get("names", [])
            for name in (
                "network/dns-requests.json",
                "network/http-fixture.json",
                "network/isolation.json",
                "network/capture.pcap",
                "network/pcap-summary.json",
            )
        ),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-firmware-guest-cname-lifecycle",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "validation": "virtual-device validation",
        "scope": "single-device-service-lease-not-physical-rf",
        "runtime": {
            "machine": "m5sticks3",
            "runtime": "qemu-wifi",
            "profile": "uiflow2-sticks3-wifi",
            "isolation": "namespace",
            "egress": "allowlist",
            "dns": "controlled",
            "duration_seconds": round(time.monotonic() - started, 3),
        },
        "hashes": {
            "probe_image": sha256_file(image),
            "qemu": sha256_file(args.qemu),
            "runner": sha256_file(Path(__file__)),
            "device_service": sha256_file(ROOT / "platform/tools/device_service.py"),
            "network_sandbox": sha256_file(ROOT / "platform/tools/network_sandbox.py"),
            "evidence_zip": (
                sha256_bytes(run["evidence_zip"]) if run["evidence_zip"] else None
            ),
        },
        "probe_image_source": probe_source,
        "session_id_sha256": (
            sha256_bytes(str(session.get("session_id", "")).encode())
            if session.get("session_id")
            else None
        ),
        "checks": checks,
        "dns": {
            "alias": ALIAS,
            "terminal": TERMINAL,
            "terminal_address": TERMINAL_IP,
            "allowed_query": chain_row,
            "denied_query": denied_row,
        },
        "http": {
            "host": ALIAS,
            "path": "/cname",
            "requests": http_requests,
        },
        "pcap_destinations": destinations,
        "isolation": isolation,
        "service_network_checks": network.get("checks", {}),
        "serial_tail": sanitize_serial(serial),
        "not_claimed": [
            "public DNS or DNSSEC",
            "DNS rebinding resistance",
            "arbitrary public domain resolution",
            "physical RF, power or electrical behavior",
            "physical hardware validation",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
