#!/usr/bin/env python3
"""Check the retained frame from probe_draw_pixel_transaction.py."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from check_ui_frame import check_frame


def load_oracle(serial):
    for line in serial.splitlines():
        if not line.startswith("M5EMU_UI_FRAME_ORACLE "):
            continue
        record = json.loads(line.split(" ", 1)[1])
        return record["oracle"], record.get("tolerance", 8)
    raise ValueError("drawPixel frame oracle was not emitted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads((args.run_dir / "report.json").read_text())
    frame = (args.run_dir / "frame.png").read_bytes()
    oracle, tolerance = load_oracle((args.run_dir / "serial.txt").read_text())
    checked = check_frame(frame, oracle, tolerance)
    result = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "device_id": report["device_id"],
        "base_sha256": report["base_sha256"],
        "firmware_sha256": report["firmware_sha256"],
        "runtime_binary_sha256": report["runtime_binary_sha256"],
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
        "status": checked["status"],
        **checked,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["status"] == "FRAME_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
