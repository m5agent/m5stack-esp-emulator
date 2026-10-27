#!/usr/bin/env python3
"""Verify this archive offline; do not start a guest or contact a service."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


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
    for relative in acceptance["portable_verifiers"]:
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
