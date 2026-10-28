#!/usr/bin/env python3
"""Strict same-firmware A/B for isolated camera reconfiguration lanes."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from analyze_camera_frames import pattern_sha256


def retained(folder):
    report = json.loads((folder / "report.json").read_text())
    serial = (folder / "serial.txt").read_text()
    rows = {row["phase"]: row for row in (json.loads(line.split(" ", 1)[1]) for line in serial.splitlines() if line.startswith("CAMERA_PHASE "))}
    with zipfile.ZipFile(folder / "evidence.zip") as archive:
        archive_valid = archive.testzip() is None
    archive_valid &= hashlib.sha256((folder / "evidence.zip").read_bytes()).hexdigest() == report.get("evidence_sha256")
    return report, serial, rows, archive_valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--baseline-template", default="cores3-camera-{case}-phase-baseline-r1")
    parser.add_argument("--fixed-template", default="cores3-camera-{case}-phase-fixed-exact-r1")
    args = parser.parse_args()
    results = {}
    for kind in ("raw", "jpg", "bmp", "snapshot"):
        old_folder = args.raw_root / args.baseline_template.format(case=kind)
        new_folder = args.raw_root / args.fixed_template.format(case=kind)
        old, old_serial, baseline, old_zip = retained(old_folder)
        new, serial, fixed, new_zip = retained(new_folder)
        native = fixed.get("native-result", {})
        checks = {
            "same_whole_firmware": old["firmware_sha256"] == new["firmware_sha256"],
            "same_guest_and_fixture_bytes": old["source_sha256"] == new["source_sha256"] and old["fixture_sha256"] == new["fixture_sha256"],
            "stock_firmware_lane": old.get("firmware_lane") == new.get("firmware_lane") == "stock-frozen",
            "runtime_changed": old.get("runtime_binary_sha256") != new.get("runtime_binary_sha256"),
            "old_post_framesize_contract_failed": baseline.get("capture-after-framesize", {}).get("bytes") != 153600 or "stack overflow" in old_serial,
            "new_guest_completed": new.get("status") == "EXECUTED" and "CAMERA_PHASE_DONE" in serial,
            "new_native_result": native.get("bytes", 0) > 0 and (kind not in ("raw", "snapshot") or native.get("sha256") == pattern_sha256(0)),
            "yield_boundary_completed": "scheduled-after-native" in fixed,
            "reprobe_succeeded": fixed.get("framesize", {}).get("returned") is True,
            "complete_exact_frame_after_reprobe": fixed.get("capture-after-framesize", {}).get("bytes") == 153600 and fixed.get("capture-after-framesize", {}).get("sha256") == pattern_sha256(0),
            "driver_teardown_rejects_capture": fixed.get("deinit", {}).get("returned") is True and fixed.get("deinit", {}).get("capture_after_deinit") is False,
            "actual_eight_bit_no_conversion_no_bit_swap": all(
                rows.get(phase, {}).get("cam_ctrl", 1 << 6) & ((1 << 5) | (1 << 6)) == 0
                and rows.get(phase, {}).get("cam_ctrl1", 1 << 24) & (1 << 24) == 0
                and rows.get(phase, {}).get("cam_rgb", 1 << 31) & (1 << 31) == 0
                for rows in (baseline, fixed) for phase in ("registers-before", "registers-after")),
            "no_new_native_crash": not any(marker in serial for marker in ("A fatal error occurred", "Guru Meditation", "stack overflow", "abort() was called")),
            "archives_valid": bool(old_zip and new_zip),
            "both_stopped_and_history_preserved": all(report.get("cleanup", {}).get("runtime_pid_gone") is True and report.get("cleanup", {}).get("history_preserved") is True for report in (old, new)),
        }
        receipt = {"status": "DATA_PLANE_PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "scope": "Same-firmware isolated native lane, explicit scheduler yield, QVGA re-probe and exact subsequent wire frame. Encoded image color correctness belongs to the separate full-interface Pillow oracle.",
            "baseline": {"report": str(old_folder / "report.json"), **{key: old.get(key) for key in ("session_id", "source_sha256", "fixture_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}},
            "fixed": {"report": str(new_folder / "report.json"), **{key: new.get(key) for key in ("session_id", "source_sha256", "fixture_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}}}
        (new_folder / "camera-phase-oracle.json").write_text(json.dumps(receipt, indent=2) + "\n")
        results[kind] = receipt
    output = {"validation": "virtual-device validation", "hardware_validation": "NOT RUN", "status": "DATA_PLANE_PASS" if all(row["status"] == "DATA_PLANE_PASS" for row in results.values()) else "FAIL", "cases": results}
    (args.raw_root / "camera-phase-comparison.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"status": output["status"], "cases": {kind: {"status": row["status"], "checks": row["checks"]} for kind, row in results.items()}}))
    return 0 if output["status"] == "DATA_PLANE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
