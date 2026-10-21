#!/usr/bin/env python3
"""Run focused UIFlow2 peripheral probes on StickS3 and CoreS3."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"

CASES = [
    {
        "id": "sticks3-peripherals",
        "expected_status": "PARTIAL",
        "reason": (
            "A/B/P buttons and M5PM1 power telemetry pass; BMI270 is "
            "detected and enabled but accel/gyro values remain zero."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PARTIAL"},
            {"name": "buttons_a_b_pwr", "status": "PASS"},
            {"name": "power", "status": "PASS"},
        ],
        "machine": "m5sticks3",
        "base": "platform/.cache/firmware/sticks3/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_peripherals",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "135x240",
        "efuse_pkg_version": "1",
        "wait": "5",
        "inputs": ["key:a", "key:b", "key:p"],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
        ],
    },
    {
        "id": "cores3-peripherals",
        "expected_status": "PARTIAL",
        "reason": (
            "Touch, PWR, AXP2101 power telemetry and PCF8563 RTC pass; "
            "BMI270 values and BMM150 magnetometer remain incomplete."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PARTIAL"},
            {"name": "magnetometer", "status": "FAIL"},
            {"name": "touch", "status": "PASS"},
            {"name": "btn_pwr", "status": "PASS"},
            {"name": "power", "status": "PASS"},
            {"name": "rtc", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_peripherals",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "6",
        "inputs": ["touch:160,183", "key:p"],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
        ],
    },
    {
        "id": "cores3-camera",
        "expected_status": "PARTIAL",
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_camera",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:p"],
        "qom": [],
        "allow_static_frame": True,
        "reason": (
            "GC0308 init reaches the UIFlow2 camera API, but snapshot "
            "returns None because ESP32-S3 LCD_CAM capture/DMA is not modeled."
        ),
        "checks": [
            {"name": "camera_init", "status": "PASS"},
            {"name": "camera_snapshot", "status": "PARTIAL"},
        ],
    },
]


def command_for(case: dict, out_dir: Path) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--base", str(ROOT / case["base"]),
        "--machine", case["machine"],
        "--files-dir", str(ROOT / case["files_dir"]),
        "--vfs-offset", case["vfs_offset"],
        "--vfs-size", case["vfs_size"],
        "--flash-size", case["flash_size"],
        "--expected-size", case["expected_size"],
        "--wait", case["wait"],
        "--post-input-wait", "1",
        "--efuse-driver", "nvram.esp32s3.efuse",
        "--efuse-pkg-version", case["efuse_pkg_version"],
        "--qemu", str(QEMU),
        "--rom-dir", str(ROM_DIR),
        "--out-dir", str(out_dir),
    ]
    for input_spec in case["inputs"]:
        command.extend(["--input", input_spec])
    for path, prop, value in case["qom"]:
        command.extend(["--qom-set", path, prop, value])
    if case.get("allow_static_frame"):
        command.append("--allow-static-frame")
    return command


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-uiflow2-peripheral-matrix"),
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )

    results = {}
    for case in CASES:
        case_out = args.out_dir / case["id"]
        command = command_for(case, case_out)
        stdout_path = args.out_dir / f"{case['id']}.stdout"
        stderr_path = args.out_dir / f"{case['id']}.stderr"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        executed = process.returncode == 0
        status = case["expected_status"] if executed else "FAIL"
        results[case["id"]] = {
            "status": status,
            "exit_code": process.returncode,
            "command": command,
            "output": str(case_out),
            "before": str(case_out / "before.png"),
            "after": str(case_out / "after.png"),
            "checks": case["checks"],
            **({"reason": case["reason"]} if case.get("reason") else {}),
        }

    counts = {}
    for result in results.values():
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "out_dir": str(args.out_dir),
        "results": results,
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(counts, sort_keys=True))
    if counts.get("FAIL"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
