#!/usr/bin/env python3
"""Stream and verify one real IMX219 RG10 frame through Linux V4L2."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_FRAME_SHA256 = (
    "5568cf027da59228168e211e27283adaad4eaf6c299a4ad44026b0b703f7af4c"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / ".work/cardputerzero/cardputerzero-work.img",
    )
    parser.add_argument(
        "--kernel",
        type=Path,
        default=ROOT / ".work/cardputerzero/boot/kernel8.img",
    )
    parser.add_argument(
        "--dtb",
        type=Path,
        default=ROOT / ".work/cardputerzero/boot/cardputerzero-v5-imx219.dtb",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-cardputerzero-camera"),
    )
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument(
        "--expected-sha256", default=DEFAULT_FRAME_SHA256
    )
    parser.add_argument("--controls", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    append = (
        "console=ttyAMA1,115200 root=PARTUUID=f6c408b0-02 "
        "rootfstype=ext4 rootwait rw earlycon=pl011,0x3f201000 "
        "systemd.unit=multi-user.target deferred_probe_timeout=10 "
        "fw_devlink=permissive m5.camera_probe=1"
    )
    if args.controls:
        append += " m5.camera_controls_probe=1"
    command = [
        "python3",
        str(HERE / "run_linux_boot.py"),
        "--machine", "raspi3b",
        "--memory", "512M",
        "--image", str(args.image),
        "--kernel", str(args.kernel),
        "--dtb", str(args.dtb),
        "--append", append,
        "--out-dir", str(args.out_dir),
        "--complete-marker", "M5_CZ_PROBE_DONE",
        "--imx219",
        "--camera-probe",
        "--expect-camera-capture",
        "--expected-camera-bytes", "614400",
        "--transient",
        "--timeout", str(args.timeout),
    ]
    if args.expected_sha256:
        command.extend(
            ["--expected-camera-sha256", args.expected_sha256]
        )
    if args.controls:
        command.append("--expect-imx219-controls")
    subprocess.run(command, cwd=ROOT, check=True)

    result = json.loads((args.out_dir / "result.json").read_text())
    print(
        "CAMERA_PROBE",
        result["status"],
        f"bytes={result['camera_frame_bytes']}",
        f"sha256={result['camera_frame_sha256']}",
    )


if __name__ == "__main__":
    main()
