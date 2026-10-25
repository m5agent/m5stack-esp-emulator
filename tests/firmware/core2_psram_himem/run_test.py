#!/usr/bin/env python3
"""Run the Core2 upper-PSRAM bank-switch probe through Device Service."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

READY_MARKER = "CORE2_HIMEM_BANK_PASS"
EXPECTED_MACHINE_BYTES = 8 << 20


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qom_memory_bytes(qom: dict[str, Any]) -> int | None:
    memory = qom.get("nodes", {}).get("memory")
    if not isinstance(memory, dict):
        return None
    value = memory.get("value")
    if not isinstance(value, dict):
        return None
    size = value.get("size")
    return size if isinstance(size, int) and not isinstance(size, bool) else None


def parse_serial(serial: str) -> dict[str, Any]:
    physical_match = re.search(
        r"(?m)^CORE2_HIMEM_PHYS_BYTES\s+(\d+)\s*$",
        serial,
    )
    reserved_match = re.search(
        r"(?m)^CORE2_HIMEM_RESERVED_BYTES\s+(\d+)\s*$",
        serial,
    )
    return {
        "physical_bytes": int(physical_match.group(1)) if physical_match else None,
        "reserved_bytes": int(reserved_match.group(1)) if reserved_match else None,
        "bank_pass_count": serial.count(READY_MARKER),
        "mismatch_count": serial.count("CORE2_HIMEM_MISMATCH"),
        "failure_markers": re.findall(
            r"(?m)^CORE2_HIMEM_(?:FAIL|ALLOC_ERROR|RANGE_ERROR|MAP_.*_ERROR).*$",
            serial,
        ),
    }


def wait_running(
    api: Api,
    session_id: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = api.json(f"/api/v1/sessions/{session_id}")
        if latest.get("state") == "running":
            return latest
        if latest.get("state") in {"failed", "stopped"}:
            raise RuntimeError(
                f"session reached {latest.get('state')}: {latest.get('error')}"
            )
        time.sleep(0.25)
    raise RuntimeError("session did not reach running before timeout")


def run_attempt(
    api: Api,
    firmware_id: str,
    attempt_dir: Path,
    *,
    timeout: float,
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    session_id = ""
    try:
        created = api.json(
            "/api/v1/sessions",
            method="POST",
            payload={
                "device_id": "core2",
                "firmware_id": firmware_id,
                "runtime": "qemu",
                "ready_marker": READY_MARKER,
                "ready_timeout_seconds": timeout,
                "ttl_seconds": 180,
            },
        )
        session_id = str(created["session_id"])
        running = wait_running(api, session_id, timeout=timeout)
        serial_payload = api.json(
            f"/api/v1/sessions/{session_id}/serial?tail=20000"
        )
        serial = str(serial_payload.get("data") or "")
        (attempt_dir / "serial.log").write_text(serial)
        qom = api.json(
            f"/api/v1/sessions/{session_id}/qom-snapshot",
            method="POST",
            payload={
                "path": "/machine",
                "depth": 2,
                "max_nodes": 1000,
            },
        )
        (attempt_dir / "qom.json").write_text(
            json.dumps(qom, indent=2) + "\n"
        )
        status, evidence, _ = api.request(
            f"/api/v1/sessions/{session_id}/evidence"
            "?include=manifest,serial,logs,qom",
            timeout=timeout,
        )
        if evidence:
            (attempt_dir / "evidence.zip").write_bytes(evidence)
        parsed = parse_serial(serial)
        machine_memory = qom_memory_bytes(qom)
        checks = {
            "session_running": running.get("state") == "running",
            "physical_himem_bytes": (
                isinstance(parsed["physical_bytes"], int)
                and parsed["physical_bytes"] >= 4 << 20
            ),
            "reserved_mmu_bytes": parsed["reserved_bytes"] == 8 * 0x8000,
            "bank_switch_pass": parsed["bank_pass_count"] == 1,
            "no_mismatch": parsed["mismatch_count"] == 0,
            "no_failure_marker": not parsed["failure_markers"],
            "machine_memory_8_mib": machine_memory == EXPECTED_MACHINE_BYTES,
            "evidence_zip": status == 200 and evidence.startswith(b"PK\x03\x04"),
        }
        return {
            "session_id_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
            "physical_himem_bytes": parsed["physical_bytes"],
            "reserved_mmu_bytes": parsed["reserved_bytes"],
            "machine_memory_bytes": machine_memory,
            "evidence_bytes": len(evidence),
        }
    finally:
        if session_id:
            api.json(
                f"/api/v1/sessions/{session_id}?purge=0",
                method="DELETE",
                payload={},
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 10:
        parser.error("--attempts must be from 1 to 10")
    if not args.image.is_file():
        parser.error(f"--image does not exist: {args.image}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    image_sha256 = sha256(args.image)
    api = Api(args.base_url)
    status, body, _ = api.request(
        "/api/v1/artifacts",
        method="POST",
        data=args.image.read_bytes(),
        content_type="application/octet-stream",
        timeout=120,
    )
    artifact = json.loads(body)
    if status != 201 or artifact.get("sha256") != image_sha256:
        raise SystemExit("artifact upload did not preserve the image hash")
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
    checks = {
        name: all(run["checks"].get(name, False) for run in runs)
        for name in runs[0]["checks"]
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-psram-himem-bank-switch",
        "validation": "virtual-device validation",
        "status": (
            "PASS"
            if len(runs) == args.attempts and all(checks.values())
            else "FAIL"
        ),
        "firmware_sha256": image_sha256,
        "firmware_bytes": args.image.stat().st_size,
        "attempts_requested": args.attempts,
        "attempts_completed": len(runs),
        "attempts_passed": sum(run["status"] == "PASS" for run in runs),
        "checks": checks,
        "runs": runs,
        "boundary": {
            "guest_data_path": "esp_himem upper 4 MiB with DRAM1 MMU remap",
            "not_claimed": [
                "physical PSRAM capacity",
                "physical cache/PSRAM timing",
                "physical hardware validation",
                "RF or electrical behavior",
            ],
        },
    }
    path = args.out_dir / "evidence.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print(f"evidence={path}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
