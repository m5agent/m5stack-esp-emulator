#!/usr/bin/env python3
"""Verify a retained official-source USB Buffer before/candidate comparison.

The oracle checks real guest byte assertions and exact module provenance. It
does not establish USB host enumeration, endpoint transfer or stock-firmware
correction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


CASES = (
    "empty read returns zero",
    "zero-length destination does not consume",
    "partial read returns four and preserves tail",
    "remaining tail returns two",
    "all destination lengths zero through capacity",
    "read during pending write preserves compacted byte order",
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(folder, metadata):
    report = json.loads((folder / "report.json").read_text())
    rows = []
    for line in (folder / "serial.txt").read_text().splitlines():
        if line.startswith("USB_CANDIDATE "):
            rows.append(json.loads(line[len("USB_CANDIDATE "):]))
    original = [row for row in rows if row.get("phase") == "official-preimage"]
    candidate = [row for row in rows if row.get("phase") == "corrected-source"]
    try:
        with zipfile.ZipFile(folder / "evidence.zip") as archive:
            zip_valid = archive.testzip() is None
    except (OSError, zipfile.BadZipFile):
        zip_valid = False
    checks = {
        "executed": report.get("status") == "EXECUTED",
        "separate_candidate_lane": report.get("firmware_lane") == "candidate-python-source",
        "official_source_hash": sha256(folder / "files/usb_core_before.py") == metadata["preimage_sha256"],
        "corrected_source_hash": sha256(folder / "files/usb_core_candidate.py") == metadata["candidate_sha256"],
        "original_nameerror_and_consumption": len(original) == 1 and original[0].get("status") == "EXPECTED_FAILURE"
            and "to_r4" in original[0].get("error", "") and original[0].get("copied") == [65, 66, 67, 68]
            and original[0].get("remaining") == [69, 70],
        "all_six_corrected_cases": len(candidate) == 1 and candidate[0].get("status") == "PASS"
            and candidate[0].get("cases") == list(CASES),
        "no_failed_assertions": all(row.get("status") in ("PASS", "EXPECTED_FAILURE") for row in rows),
        "evidence_zip_valid": zip_valid,
        "evidence_zip_hash": sha256(folder / "evidence.zip") == report.get("evidence_sha256"),
        "stopped_history_preserved": report.get("stopped") is True and report.get("cleanup", {}).get("history_preserved") is True,
        "runtime_pid_gone": report.get("cleanup", {}).get("runtime_pid_gone") is True,
    }
    result = {
        "schema_version": 1,
        "status": "CANDIDATE_PASS" if all(checks.values()) else "FAIL",
        "api": "usb.device.core.Buffer.readinto",
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "scope": metadata["boundary"],
        "checks": checks,
        "cases": list(CASES),
        "evidence": {key: report.get(key) for key in ("device_id", "session_id", "source_sha256", "firmware_sha256", "base_sha256", "runtime_binary_sha256", "evidence_sha256", "firmware_lane")},
        "provenance": {key: metadata[key] for key in ("upstream", "commit", "path", "preimage_sha256", "candidate_sha256", "patch_sha256")},
    }
    (folder / "usb-buffer-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", type=Path, nargs="+")
    parser.add_argument("--metadata", type=Path, default=Path(__file__).parents[3] / "patches/uiflow2-api/0011-usb-buffer-readinto.json")
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text())
    failed = False
    for folder in args.folders:
        result = analyze(folder, metadata)
        print(json.dumps({"folder": str(folder), "status": result["status"], "checks": result["checks"]}))
        failed |= result["status"] != "CANDIDATE_PASS"
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
