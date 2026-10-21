#!/usr/bin/env python3
"""Verify GL852G TT compatibility for a low-speed HID downstream device."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


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
        default=ROOT / ".work/cardputerzero/boot/cardputerzero-v5-test.dtb",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-cardputerzero-usb-low-speed"),
    )
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    append = (
        "console=ttyAMA1,115200 root=PARTUUID=f6c408b0-02 "
        "rootfstype=ext4 rootwait rw earlycon=pl011,0x3f201000 "
        "systemd.unit=multi-user.target"
    )
    subprocess.run(
        [
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
            "--hub-high-speed",
            "--hub-tt-compat",
            "--hub-low-speed-hid",
            "--expect-hub-tt",
            "--expected-tt-mask", "0x2",
            "--expect-low-speed-hid",
            "--expected-usb-speed", "high",
            "--transient",
            "--timeout", str(args.timeout),
        ],
        cwd=ROOT,
        check=True,
    )
    result = json.loads((args.out_dir / "result.json").read_text())
    print(
        "USB_LOW_SPEED_HID",
        result["status"],
        f"tt_mask={result['hub_qom'].get('tt-active-port-mask')}",
        f"elapsed={result['elapsed_seconds']}",
    )


if __name__ == "__main__":
    main()
