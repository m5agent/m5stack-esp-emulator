#!/usr/bin/env python3
"""Compare an unchanged guest/firmware's exact-coordinate input subcase.

The legacy PMIC short-click oracle in the original probe is unrelated to this
coordinate regression and is not granted a PASS by the touch result.
"""
import argparse
import json
from pathlib import Path


def retained(folder):
    report = json.loads((folder / "report.json").read_text())
    rows = {}
    for line in (folder / "serial.txt").read_text().splitlines():
        if "HARDWARE_API " in line:
            row = json.loads(line.split("HARDWARE_API ", 1)[1])
            rows[row["api"]] = row
    return report, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("fixed", type=Path)
    args = parser.parse_args()
    old, old_rows = retained(args.baseline)
    new, new_rows = retained(args.fixed)
    methods = ("M5.Touch.getX", "M5.Touch.getY", "M5.Touch.getTouchPointRaw", "M5.Touch.getDetail", "M5.Touch.getCount")
    actions = json.loads((args.fixed / "host-actions.json").read_text())
    touch_actions = [row for row in actions if row.get("endpoint") == "input" and row.get("payload", {}).get("kind") == "longpress"]
    checks = {
        "same_firmware_sha256": old["firmware_sha256"] == new["firmware_sha256"],
        "same_guest_source_sha256": old["source_sha256"] == new["source_sha256"],
        "original_point_showed_quantization": old_rows["M5.Touch.getX"]["value"] == 60 and old_rows["M5.Touch.getY"]["value"] == 72,
        "exact_fixed_coordinates": new_rows["M5.Touch.getX"]["value"] == 61 and new_rows["M5.Touch.getY"]["value"] == 73,
        "exact_fixed_controller_point": new_rows["M5.Touch.getTouchPointRaw"]["value"][:2] == [61, 73],
        "all_five_touch_assertions_pass": all(new_rows[method]["status"] == "API_ASSERTION_PASS" for method in methods),
        "same_requested_device_service_point": len(touch_actions) == 1 and touch_actions[0].get("status") == "OBSERVED" and touch_actions[0]["payload"]["x"] == 61 and touch_actions[0]["payload"]["y"] == 73,
        "runtime_stopped": new.get("cleanup", {}).get("runtime_pid_gone") is True,
    }
    result = {"schema_version": 1, "status": "DATA_PLANE_PASS" if all(checks.values()) else "FAIL",
        "scope": "Exact (61,73) Device Service/QMP to FT6336/M5.Touch regression on unchanged guest firmware. Multi-touch, movement and physical touchscreen validation remain separate.",
        "oracle": "The same requested point and unchanged firmware originally reported (60,72); after the host coordinate inverse fix, both processed and raw native controller coordinates equal (61,73), with actual pressed/released transition.",
        "checks": checks, "touch_observations": {method: new_rows[method] for method in methods},
        "baseline": {"report": str(args.baseline / "report.json"), **{key: old.get(key) for key in ("session_id", "source_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}},
        "fixed": {"report": str(args.fixed / "report.json"), **{key: new.get(key) for key in ("session_id", "source_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}}}
    (args.fixed / "touch-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": checks}))
    return 0 if result["status"] == "DATA_PLANE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
