#!/usr/bin/env python3
"""Verify this archive offline; do not start a guest or contact a service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REQUIRED_VERIFIERS = ("controller/verify.py", "build/verify.py", "testing/verify.py", "live/verify.py")
RUNTIME_SHA256 = "3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    manifest = json.loads((ROOT / "artifact-manifest.json").read_bytes())
    require(manifest["schema_version"] == 1, "manifest version")
    seen = set()
    total = 0
    for item in manifest["files"]:
        relative = item["path"]
        require(relative not in seen and not Path(relative).is_absolute()
                and ".." not in Path(relative).parts, "unsafe or duplicate path")
        path = ROOT / relative
        require(path.is_file() and not path.is_symlink(), "missing or linked file: " + relative)
        raw = path.read_bytes()
        require(len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"],
                "changed file: " + relative)
        seen.add(relative)
        total += len(raw)
    actual = {str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file()}
    require(actual == seen | {"artifact-manifest.json"}, "unlisted or missing files")
    acceptance = json.loads((ROOT / "final-acceptance.json").read_bytes())
    require(acceptance["status"] == "PASS_FOR_UNIT_HOST38_SCOPE", "scoped acceptance")
    require(acceptance["portable_verifiers"] == list(REQUIRED_VERIFIERS),
            "all four required child verifiers must be declared")
    require(acceptance["hardware"] == "NOT RUN", "hardware boundary")
    require(acceptance["unit_host_37"] == "OPEN", "cold-route boundary")
    require(acceptance["unit_goal"] == "ACTIVE", "overall Unit goal boundary")
    require(acceptance["platform"]["status"] == "PASS"
            and acceptance["platform"]["tests"] == 1220, "platform regression")
    matrix = acceptance["shared_controller_matrix"]
    require(matrix["status"] == "FAIL" and matrix["cases"] == 67
            and matrix["pass"] == 66 and matrix["failed_cases"] == ["core2-imu"]
            and matrix["checks"] == 274 and matrix["attempts_per_case"] == 1,
            "preserved independent full-matrix failure")
    require(acceptance["service"]["source_files_match"] == 83
            and acceptance["service"]["active_sessions"] == 0
            and acceptance["service"]["active_leases"] == 0, "service final state")
    live = json.loads((ROOT / "live/index.json").read_bytes())["summary"]
    for key, expected in {
        "eight_lane_status": "PASS", "lanes": 8, "executions": 168,
        "runtime_sha256": RUNTIME_SHA256, "generation": 47,
        "web_mandatory_status": "PASS", "web_mandatory_phases": 13,
        "web_owner_executions": 14, "web_optional_capture_status": "PARTIAL",
        "web_optional_empty_200": 7, "browser_responses": 1062,
        "browser_200": 386, "browser_304": 676,
    }.items():
        require(live[key] == expected, "live evidence summary: " + key)
    require(live["cleanup"] == {
        "owned_sessions": 13, "original_pass": 12, "original_unconfirmed": 1,
        "separate_finalization_confirmed": 1, "confirmed_resource_finalizations": 13,
    }, "original cleanup uncertainty and independent finalization must stay separate")
    service = json.loads((ROOT / "service/final-receipt.json").read_bytes())
    require(service["status"] == "PASS" and service["source_files_match"] == 83
            and service["runtime_sha256"] == RUNTIME_SHA256 and service["generation"] == 47
            and service["active_sessions"] == service["active_leases"] == 0,
            "original final service receipt")
    for relative in REQUIRED_VERIFIERS:
        require(relative in seen and relative.endswith(".py"), "unlisted verifier")
        result = subprocess.run([sys.executable, "-B", str(ROOT / relative)],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        require(result.returncode == 0, relative + ": " + result.stdout + result.stderr)
    print(json.dumps({"status": "PASS", "category": "OFFLINE_SCOPED_ARCHIVE_INTEGRITY",
                      "files": len(seen), "bytes": total,
                      "child_verifiers": len(acceptance["portable_verifiers"]),
                      "matrix": "66 PASS / 1 FAIL (core2-imu)",
                      "unit_host_37": "OPEN", "unit_goal": "ACTIVE",
                      "api_contacted": False, "new_guests": 0, "hardware": "NOT RUN"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
