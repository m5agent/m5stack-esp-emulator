#!/usr/bin/env python3
"""Summarize independent CNAME guest runs and preserve startup diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_startup_failure(run: Path) -> dict[str, Any]:
    session_root = run / "service-state" / "sessions"
    session_file = next(iter(sorted(session_root.glob("*/session.json"))), None)
    session = load_json(session_file) if session_file is not None else {}
    qemu_stderr_path = (
        session_file.parent / "qemu.stderr" if session_file is not None else None
    )
    qemu_stderr = (
        qemu_stderr_path.read_text(errors="replace")
        if qemu_stderr_path is not None and qemu_stderr_path.is_file()
        else ""
    )
    if "sandbox DNS record addresses must" in qemu_stderr:
        stage = "sandbox_dns_record_renormalization"
    elif "ROM code binary not found" in qemu_stderr:
        stage = "qemu_rom_directory_missing_machine_rom"
    else:
        stage = "unclassified_pre_guest_failure"
    evidence = (
        load_json(run / "evidence.json") if (run / "evidence.json").is_file() else {}
    )
    return {
        "label": run.name,
        "status": "FAIL",
        "stage": stage,
        "session_state": session.get("state"),
        "session_error": session.get("error"),
        "guest_serial_bytes": len(str(evidence.get("serial_tail", "")).encode()),
        "qemu_stderr": qemu_stderr.strip(),
        "classification": "pre-guest service/QEMU startup failure, not firmware",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument(
        "--diagnostic-failure",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    runs = []
    common_hashes: dict[str, str | None] | None = None
    common_checks: dict[str, bool] | None = None
    for run in args.run:
        evidence = load_json(run / "evidence.json")
        if evidence.get("status") != "PASS":
            raise SystemExit(f"run is not PASS: {run}")
        checks = evidence.get("checks")
        if not isinstance(checks, dict) or not checks or not all(checks.values()):
            raise SystemExit(f"run has incomplete checks: {run}")
        hashes = {
            key: evidence.get("hashes", {}).get(key)
            for key in (
                "probe_image",
                "qemu",
                "runner",
                "device_service",
                "network_sandbox",
            )
        }
        if common_hashes is None:
            common_hashes = hashes
            common_checks = checks
        elif hashes != common_hashes:
            raise SystemExit(f"artifact/tool hash drift: {run}")
        elif checks != common_checks:
            raise SystemExit(f"check-set drift: {run}")
        runs.append(
            {
                "label": run.name,
                "status": "PASS",
                "duration_seconds": evidence.get("runtime", {}).get("duration_seconds"),
                "session_id_sha256": evidence.get("session_id_sha256"),
                "evidence_zip_sha256": evidence.get("hashes", {}).get("evidence_zip"),
                "dns_alias_query": evidence.get("dns", {}).get("allowed_query"),
                "dns_denied_query": evidence.get("dns", {}).get("denied_query"),
                "http_requests": evidence.get("http", {}).get(
                    "requests",
                    [],
                ),
                "pcap_destinations": [
                    row
                    for row in evidence.get("pcap_destinations", [])
                    if row.get("address") == "10.0.2.2"
                    and row.get("port") in {18080, 18081}
                ],
                "cleanup": {
                    key: evidence.get("isolation", {}).get(key)
                    for key in (
                        "private_network_namespace",
                        "external_route",
                        "cleanup_completed",
                        "qemu_process_reaped",
                        "dns_closed",
                        "http_closed",
                    )
                },
            }
        )

    current_code_hashes = {
        "runner": sha256_file(ROOT / "tests/network/cname_guest_lifecycle/run_test.py"),
        "device_service": sha256_file(ROOT / "platform/tools/device_service.py"),
        "network_sandbox": sha256_file(ROOT / "platform/tools/network_sandbox.py"),
    }
    code_drift = {
        key: {
            "run": (common_hashes or {}).get(key),
            "current": value,
        }
        for key, value in current_code_hashes.items()
        if (common_hashes or {}).get(key) != value
    }
    if code_drift:
        raise SystemExit(
            "current code drifted from evidence runs: "
            + json.dumps(code_drift, sort_keys=True)
        )

    aggregate = {
        "schema_version": 1,
        "kind": "m5stack-firmware-guest-cname-lifecycle",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "validation": "virtual-device validation",
        "scope": "three-independent-device-service-leases-not-physical-rf",
        "runtime": {
            "machine": "m5sticks3",
            "runtime": "qemu-wifi",
            "profile": "uiflow2-sticks3-wifi",
            "isolation": "namespace",
            "egress": "allowlist",
            "dns": "controlled",
            "lease_count": len(runs),
        },
        "hashes": {
            **common_hashes,
            "summarizer": sha256_file(Path(__file__)),
        },
        "checks": common_checks,
        "runs": runs,
        "diagnostic_failures": [
            classify_startup_failure(path) for path in args.diagnostic_failure
        ],
        "not_claimed": [
            "public DNS or DNSSEC",
            "DNS rebinding resistance",
            "arbitrary public domain resolution",
            "physical RF, power or electrical behavior",
            "physical hardware validation",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
