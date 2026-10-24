#!/usr/bin/env python3
"""Exercise the Core2 native-HCI runtime through the Device Service API."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

PROFILE = "core2-native-hci"
READY_MARKER = "UNIFIED_CORE2_READY"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Api:
    def __init__(self, base_url: str, token: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        method: str | None = None,
        timeout: float = 240,
    ) -> tuple[int, bytes, str]:
        request_headers = dict(headers or {})
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            body = error.read()
            raise RuntimeError(
                f"{path} returned HTTP {error.code}: {body[:1000]!r}"
            ) from error

    def json(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 240,
        method: str | None = None,
    ) -> Any:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        status, body, _ = self.request(
            path,
            data=data,
            headers=headers,
            method=method,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise RuntimeError(f"{path} returned HTTP {status}")
        return json.loads(body)

    def upload(self, path: Path) -> str:
        status, body, _ = self.request(
            "/api/v1/artifacts",
            data=path.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": path.name,
            },
        )
        if status != 201:
            raise RuntimeError(f"artifact upload returned HTTP {status}")
        return str(json.loads(body)["artifact_id"])


def wait_for_network(
    api: Api,
    session_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = api.json(f"/api/v1/sessions/{session_id}/network")
        if latest.get("status") in {"PASS", "FAIL"}:
            return latest
        time.sleep(0.5)
    raise RuntimeError(
        "network evidence did not reach PASS/FAIL: "
        + json.dumps(latest, sort_keys=True)
    )


def run_attempt(
    api: Api,
    firmware_id: str,
    elf_artifact_id: str,
    attempt_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    session = api.json(
        "/api/v1/sessions",
        payload={
            "device_id": "core2",
            "runtime": "qemu-unified",
            "firmware_id": firmware_id,
            "ready_timeout_seconds": timeout,
            "network": {
                "profile": PROFILE,
                "elf_artifact_id": elf_artifact_id,
                "attempts": 1,
                "capture_pcap": True,
            },
        },
    )
    session_id = str(session["session_id"])
    try:
        api.json(
            f"/api/v1/sessions/{session_id}/wait",
            payload={
                "ready_marker": READY_MARKER,
                "timeout_seconds": timeout,
            },
            timeout=timeout + 15,
        )
        network = wait_for_network(api, session_id, timeout)
        frame_status, frame, _ = api.request(
            f"/api/v1/sessions/{session_id}/frame.png"
        )
        qom = api.json(
            f"/api/v1/sessions/{session_id}/qom-snapshot",
            payload={
                "path": "/machine",
                "depth": 2,
                "max_nodes": 250,
            },
        )
        evidence_status, evidence, _ = api.request(
            (
                f"/api/v1/sessions/{session_id}/evidence"
                "?include=manifest,serial,frames,logs,network,qom"
            )
        )
        (attempt_dir / "frame.png").write_bytes(frame)
        (attempt_dir / "qom.json").write_text(
            json.dumps(qom, indent=2) + "\n"
        )
        (attempt_dir / "evidence.zip").write_bytes(evidence)
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            serial = (
                archive.read("serial.log")
                if "serial.log" in names
                else b""
            )
            peer_log = (
                archive.read("ble-probe.log")
                if "ble-probe.log" in names
                else b""
            )
            pcap = (
                archive.read("network/capture.pcap")
                if "network/capture.pcap" in names
                else b""
            )
        network_checks = network.get("checks")
        network_checks = (
            network_checks if isinstance(network_checks, dict) else {}
        )
        transport = network.get("runtime", {}).get("hci_transport")
        expected_transport = "ESP32 native HCI device + HLI to Bumble"
        evidence_names = {
            "serial.log",
            "frames/current.png",
            "qom/snapshot.json",
            "network/evidence.json",
            "network/capture.pcap",
            "ble-probe.log",
            "manifest.json",
        }
        checks = {
            "api_evidence": evidence_status == 200,
            "frame_png": (
                frame_status == 200
                and frame.startswith(b"\x89PNG\r\n\x1a\n")
                and len(frame) > 1000
            ),
            "wifi_dhcp_http": all(
                network_checks.get(f"serial:{marker}", False)
                for marker in (
                    "UNIFIED_CORE2_WIFI_CONNECTED",
                    "UNIFIED_CORE2_HTTP_PASS",
                )
            ),
            "public_dns_http": all(
                network_checks.get(f"serial:{marker}", False)
                for marker in (
                    "UNIFIED_CORE2_PUBLIC_DNS",
                    "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
                )
            ),
            "external_nus_gatt": (
                network.get("status") == "PASS"
                and bool(network_checks)
                and all(network_checks.values())
                and all(
                    network_checks.get(f"serial:{marker}", False)
                    for marker in (
                        "UNIFIED_CORE2_BLE_RX",
                        "UNIFIED_CORE2_BLE_ACK_SENT",
                    )
                )
                and any(key.startswith("peer:") for key in network_checks)
                and all(
                    value
                    for key, value in network_checks.items()
                    if key.startswith("peer:")
                )
            ),
            "native_hci_transport": transport == expected_transport,
            "evidence_zip": evidence_names.issubset(names),
            "pcap_file_in_evidence_zip": len(pcap) > 0,
            "manifest_session_binding": (
                manifest.get("session", {}).get("session_id")
                == session_id
            ),
        }
        if not qom.get("nodes"):
            checks["api_evidence"] = False
        return {
            "attempt": attempt_dir.name,
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "frame_bytes": len(frame),
            "frame_sha256": hashlib.sha256(frame).hexdigest(),
            "qom_nodes": len(qom.get("nodes", [])),
            "evidence_bytes": len(evidence),
            "serial_sha256": hashlib.sha256(serial).hexdigest(),
            "peer_log_sha256": hashlib.sha256(peer_log).hexdigest(),
            "pcap_bytes": len(pcap),
            "hci_transport": str(transport or ""),
        }
    finally:
        try:
            api.json(
                f"/api/v1/sessions/{session_id}?purge=0",
                payload={},
                method="DELETE",
            )
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--token")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 10:
        parser.error("--attempts must be from 1 to 10")
    for label, path in (
        ("image", args.image),
        ("ELF", args.elf),
        ("QEMU", args.qemu),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    api = Api(args.base_url, args.token)
    firmware_artifact = api.upload(args.image)
    elf_artifact = api.upload(args.elf)
    firmware = api.json(
        "/api/v1/firmware",
        payload={
            "device_id": "core2",
            "kind": "merged",
            "artifact_id": firmware_artifact,
        },
    )
    runs = []
    for attempt in range(1, args.attempts + 1):
        result = run_attempt(
            api,
            str(firmware["firmware_id"]),
            elf_artifact,
            args.out_dir / f"attempt-{attempt}",
            args.timeout,
        )
        runs.append(result)
        if result["status"] != "PASS":
            break
    attempts_passed = sum(run["status"] == "PASS" for run in runs)
    all_checks_passed = all(all(run["checks"].values()) for run in runs)
    frame_hashes = {run["frame_sha256"] for run in runs}
    qom_node_counts = {run["qom_nodes"] for run in runs}
    checks_per_attempt = {
        name: (
            "PASS"
            if all(run["checks"].get(name, False) for run in runs)
            else "FAIL"
        )
        for name in sorted(runs[0]["checks"])
    } if runs else {}
    if runs:
        transport_pass = checks_per_attempt.pop("native_hci_transport")
        checks_per_attempt["hci_transport"] = (
            runs[0]["hci_transport"] if transport_pass == "PASS" else "FAIL"
        )
    checks_per_attempt.update(
        {
            "frame_sha256": (
                next(iter(frame_hashes))
                if len(frame_hashes) == 1
                else "MISMATCH"
            ),
            "qom_nodes": (
                next(iter(qom_node_counts))
                if len(qom_node_counts) == 1
                else "MISMATCH"
            ),
        }
    )
    status = (
        "PASS"
        if len(runs) == args.attempts
        and attempts_passed == args.attempts
        and all_checks_passed
        else "FAIL"
    )
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-native-hci-service-attempts",
        "stage": "HCI-4",
        "gate_result": status,
        "status": status,
        "validation": "virtual-device validation",
        "profile": PROFILE,
        "runtime": "qemu-unified",
        "service_api": "/api/v1",
        "firmware": {
            "sha256": sha256(args.image),
            "bytes": args.image.stat().st_size,
        },
        "elf_sha256": sha256(args.elf),
        "qemu_sha256": sha256(args.qemu),
        "attempts_requested": args.attempts,
        "attempts_passed": attempts_passed,
        "checks_per_attempt": checks_per_attempt,
        "runs": [
            {
                key: value
                for key, value in run.items()
                if key not in {"checks", "hci_transport"}
            }
            for run in runs
        ],
        "boundary": {
            "isolation": "trusted-host",
            "gdb_bridge": False,
            "session_reuse": (
                f"{args.attempts} independent sequential leases "
                "and QEMU processes"
            ),
            "pcap": (
                "captured in each evidence ZIP; packet summaries are "
                "finalized during stop/retention handling"
            ),
            "not_claimed": [
                "bit-exact Espressif BT controller/baseband",
                "physical hardware or RF validation",
                "malware sandboxing",
            ],
        },
    }
    output = args.out_dir / "evidence.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print(f"evidence={output}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
