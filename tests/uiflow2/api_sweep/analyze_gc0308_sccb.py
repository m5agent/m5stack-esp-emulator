#!/usr/bin/env python3
"""Compare same-firmware visible GC0308 preimage/fixed SCCB lifecycles."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def retained(folder):
    report = json.loads((folder / "report.json").read_text())
    serial = (folder / "serial.txt").read_text()
    rows = [json.loads(line.split(" ", 1)[1]) for line in serial.splitlines() if line.startswith("GC0308_SCCB ")]
    with zipfile.ZipFile(folder / "evidence.zip") as archive:
        valid = archive.testzip() is None
    valid &= hashlib.sha256((folder / "evidence.zip").read_bytes()).hexdigest() == report["evidence_sha256"]
    return report, serial, rows, valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("fixed", type=Path)
    args = parser.parse_args()
    old, old_serial, baseline, old_zip = retained(args.baseline)
    new, serial, rows, new_zip = retained(args.fixed)
    indexed = {(row.get("cycle"), row["phase"]): row for row in rows}
    old_index = {(row.get("cycle"), row["phase"]): row for row in baseline}
    phases = ("before-init-pid", "init", "after-init-pid", "page-one-default", "after-init-capture",
              "framesize", "after-framesize-pid", "after-framesize-capture", "deinit", "after-deinit-pid")
    checks = {
        "same_stock_firmware": old["firmware_sha256"] == new["firmware_sha256"] and old.get("firmware_lane") == new.get("firmware_lane") == "stock-frozen",
        "same_guest_source": old["source_sha256"] == new["source_sha256"],
        "changed_runtime": old["runtime_binary_sha256"] != new["runtime_binary_sha256"],
        "old_init_corrupts_page_zero_pid": old_index.get((0, "before-init-pid"), {}).get("pid") == 0x9b
            and old_index.get((0, "init"), {}).get("returned") is True
            and old_index.get((0, "after-init-pid"), {}).get("pid") == 0xf5,
        "old_full_capture_then_reprobe_rejected": old_index.get((0, "after-init-capture"), {}).get("bytes") == 153600
            and old_index.get((0, "framesize"), {}).get("returned") is False and "Detected camera not supported" in old_serial,
        "exact_three_complete_cycles": len(rows) == 30 and set(indexed) == {(cycle, phase) for cycle in range(3) for phase in phases},
        "no_failed_fixed_assertions": bool(rows) and all(row["status"] in ("PASS", "OBSERVED") for row in rows),
        "page_zero_pid_preserved": all(indexed.get((cycle, phase), {}).get("pid") == 0x9b for cycle in range(3)
            for phase in ("before-init-pid", "after-init-pid", "after-framesize-pid", "after-deinit-pid")),
        "page_one_register_zero_independent": all(indexed.get((cycle, "page-one-default"), {}).get("value") == 0xf5 for cycle in range(3)),
        "six_complete_qvga_observations": all(indexed.get((cycle, phase), {}).get("bytes") == 153600 for cycle in range(3)
            for phase in ("after-init-capture", "after-framesize-capture")),
        "no_panic_in_either_run": all(marker not in old_serial + serial for marker in ("Guru Meditation", "abort() was called", "panic'ed")),
        "evidence_archives_valid": bool(old_zip and new_zip),
        "both_stopped_history_preserved": all(report.get("stopped") is True and report.get("cleanup", {}).get("runtime_pid_gone") is True
            and report.get("cleanup", {}).get("history_preserved") is True for report in (old, new)),
    }
    result = {"schema_version": 1, "status": "DATA_PLANE_PASS" if all(checks.values()) else "FAIL",
        "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "checks": checks,
        "scope": "Same-firmware CoreS3 GC0308 SCCB page identity across three init/QVGA-framesize/deinit cycles. Capture lengths are observed; exact pixels, other geometries and physical optics are separate.",
        "baseline": {"report": str(args.baseline / "report.json"), **{key: old.get(key) for key in ("session_id", "source_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}},
        "fixed": {"report": str(args.fixed / "report.json"), **{key: new.get(key) for key in ("session_id", "source_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}}}
    (args.fixed / "gc0308-sccb-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": checks}))
    return 0 if result["status"] == "DATA_PLANE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
