#!/usr/bin/env python3
"""Run the wrong-password network P0 and emit sanitized evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LANE = ROOT / "platform/tools/network_lane.py"
DEFAULT_EMULATOR = (
    ROOT
    / ".work/esp-emu-versions/0.50.0"
    / "esp-emu-0.50.0-aarch64-apple-darwin/esp-emu"
)
DEFAULT_FIRMWARE = (
    ROOT
    / ".work/esp-emu-main/test_apps/http_throughput/build_esp32s3/merged.bin"
)
DEFAULT_ELF = (
    ROOT
    / ".work/esp-emu-main/test_apps/http_throughput/build_esp32s3/"
    "http_throughput.elf"
)
REQUIRED_CHECKS = (
    "auth_attempted",
    "wrong_password_rejected",
    "retry_observed",
    "no_dhcp_lease",
    "no_http_progress",
    "failure_marker",
    "softap_wrong_password_warning",
)


def _git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _artifact_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("role", "bytes", "sha256")
        if key in item
    }


def sanitize_evidence(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop host paths and secret-bearing command text from lane evidence."""
    checks = raw.get("checks", {})
    missing = [name for name in REQUIRED_CHECKS if name not in checks]
    if missing:
        raise RuntimeError(f"lane evidence lacks required checks: {missing}")
    if raw.get("status") == "PASS" and not all(
        checks[name] is True for name in REQUIRED_CHECKS
    ):
        raise RuntimeError("lane reported PASS without all negative checks true")

    runtime = raw.get("runtime", {})
    result = raw.get("result", {})
    return {
        "schema_version": 1,
        "kind": "m5stack-wrong-password-regression",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "simulation-only-not-hardware-validation",
        "status": raw.get("status", "FAIL"),
        "profile": raw.get("profile", "esp-idf-wrong-password"),
        "chip": raw.get("chip", "esp32s3"),
        "source": {
            "repository": "https://github.com/m5agent/m5stack-esp-emulator",
            "base_commit": _git_value("rev-parse", "HEAD"),
            "working_tree_dirty": bool(_git_value("status", "--porcelain")),
        },
        "runtime": {
            "name": runtime.get("name"),
            "expected_version": runtime.get("expected_version"),
            "network_backend": runtime.get("network_backend"),
            "console": runtime.get("console"),
            "wifi": {
                "enabled": runtime.get("wifi", {}).get("enabled"),
                "auth": runtime.get("wifi", {}).get("auth"),
                "password": "<redacted>",
            },
        },
        "artifacts": [
            _artifact_summary(item)
            for item in raw.get("artifacts", [])
            if item.get("role") != "firmware-runtime-copy"
        ],
        "checks": {
            name: checks[name] is True
            for name in REQUIRED_CHECKS
        },
        "result": {
            "status": result.get("status"),
            "passed": result.get("passed"),
            "timed_out": result.get("timed_out"),
            "duration_seconds": result.get("duration_seconds"),
            "emulator_exit_code": result.get("emulator_exit_code"),
            "serial_bytes": result.get("serial_bytes"),
            "serial_sha256": result.get("serial_sha256"),
        },
        "not_claimed": raw.get("not_claimed", []),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", type=Path, default=DEFAULT_FIRMWARE)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--emulator", type=Path, default=DEFAULT_EMULATOR)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--wifi-auth", default="wpa2-wpa3")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for label, path in (
        ("firmware", args.firmware),
        ("ELF", args.elf),
        ("emulator", args.emulator),
    ):
        if not path.is_file():
            raise SystemExit(f"{label} not found: {path}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m5-wrong-password-") as raw_dir:
        command = [
            sys.executable,
            str(LANE),
            "--profile",
            "esp-idf-wrong-password",
            "--chip",
            "esp32s3",
            "--firmware",
            str(args.firmware),
            "--elf",
            str(args.elf),
            "--emulator",
            str(args.emulator),
            "--password",
            "m5-wrong-password",
            "--wifi-auth",
            args.wifi_auth,
            "--timeout",
            str(args.timeout),
            "--out-dir",
            raw_dir,
        ]
        completed = subprocess.run(command, cwd=ROOT, check=False)
        raw_path = Path(raw_dir) / "evidence.json"
        if not raw_path.is_file():
            raise SystemExit(
                f"network lane exited {completed.returncode} without evidence"
            )
        evidence = sanitize_evidence(json.loads(raw_path.read_text()))

    destination = args.out_dir / "evidence.json"
    destination.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        f"status={evidence['status']} evidence={destination} "
        f"serial_sha256={evidence['result']['serial_sha256']}"
    )
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
