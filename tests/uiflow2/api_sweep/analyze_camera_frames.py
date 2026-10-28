#!/usr/bin/env python3
"""Independent exact-pixel oracle for retained CoreS3 LCD_CAM scene captures."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


def pattern_sha256(seed, wire_order="msb-first"):
    pixels = bytearray()
    bands = ((235, 48, 48), (235, 190, 35), (40, 190, 80), (35, 105, 235))
    for y in range(240):
        for x in range(320):
            r, g, b = bands[(y * 4 // 240 + seed) % 4]
            if x % 40 < 2 or y % 40 < 2:
                r = g = b = 245
            pixels.extend(struct.pack(">H" if wire_order == "msb-first" else "<H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)))
    return hashlib.sha256(pixels).hexdigest()


def analyze(folder, wire_order="msb-first"):
    report = json.loads(folder.joinpath("report.json").read_text())
    actions = json.loads(folder.joinpath("host-actions.json").read_text())
    rows = []
    for line in folder.joinpath("serial.txt").read_text().splitlines():
        if "HARDWARE_API " in line:
            try:
                row = json.loads(line.split("HARDWARE_API ", 1)[1])
                if row["api"] == "camera.snapshot.pattern":
                    rows.append(row)
            except ValueError:
                pass
    expected = {"A": pattern_sha256(0, wire_order), "B": pattern_sha256(1, wire_order)}
    checks = {"guest_completed": report["status"] == "EXECUTED",
              "all_eight_captures": len(rows) == 8 and {(row["value"]["phase"], row["value"]["index"]) for row in rows} == {(phase, index) for phase in ("A", "B") for index in range(4)},
              "both_scenes_observed": {row["value"]["phase"] for row in rows} == {"A", "B"},
              "qom_actions_succeeded": len(actions) >= 3 and all(row["status"] == "OBSERVED" for row in actions),
              "exact_qvga_rgb565_pixels": bool(rows) and all(row["status"] == "OBSERVED" and row["value"].get("bytes") == 153600
                    and row["value"].get("width") == 320 and row["value"].get("height") == 240
                    and row["value"].get("sha256") == expected[row["value"]["phase"]] for row in rows),
              "runtime_stopped": report.get("cleanup", {}).get("runtime_pid_gone") is True}
    result = {"schema_version": 1, "device": report["device_id"],
              "status": "DATA_PLANE_PASS" if all(checks.values()) else "FAIL",
              "wire_order": wire_order,
              "legacy_boundary": "Legacy little-endian hashes establish transfer of the old model's contents only; they do not establish correct GC0308 wire order or image colors." if wire_order != "msb-first" else None,
              "oracle": "Eight complete QVGA RGB565 snapshots match independently generated pixel hashes for two real same-session LCD_CAM scenes, including 2.5-second borrowed-frame intervals. This establishes camera init/capture/return through SCCB/LCD_CAM/GDMA; alternate resolutions, orientation controls and physical optical measurements are separate.",
              "checks": checks, "expected_sha256": expected, "frames": rows,
              "evidence": {"report": str(folder / "report.json"), "serial": str(folder / "serial.txt"),
                           "host_actions": str(folder / "host-actions.json"),
                           "session_id": report["session_id"], "firmware_sha256": report["firmware_sha256"],
                           "runtime_binary_sha256": report.get("runtime_binary_sha256"), "evidence_sha256": report["evidence_sha256"]}}
    folder.joinpath("camera-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--wire-order", choices=("msb-first", "legacy-lsb-first"), default="msb-first")
    args = parser.parse_args()
    result = analyze(args.run, args.wire_order)
    print(json.dumps({key: result[key] for key in ("device", "status", "checks", "expected_sha256")}))
    return 0 if result["status"] == "DATA_PLANE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
