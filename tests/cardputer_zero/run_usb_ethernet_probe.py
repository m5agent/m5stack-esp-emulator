#!/usr/bin/env python3
"""Verify SR9900A through Linux r8152 and a host Ethernet packet peer."""
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
        default=Path("/tmp/m5-cardputerzero-usb-ethernet"),
    )
    parser.add_argument("--net-socket-port", type=int, default=45555)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--full-speed", action="store_true")
    parser.add_argument("--tt-compat", action="store_true")
    args = parser.parse_args()

    append = (
        "console=ttyAMA1,115200 root=PARTUUID=f6c408b0-02 "
        "rootfstype=ext4 rootwait rw earlycon=pl011,0x3f201000 "
        "systemd.unit=multi-user.target"
    )
    expected_speed = (
        "full"
        if args.full_speed and (args.direct or not args.tt_compat)
        else "high"
    )
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
        "--usb-ethernet",
        "--net-socket-port", str(args.net_socket_port),
        "--expect-sr9900a-roundtrip",
        "--expected-usb-speed", expected_speed,
        "--transient",
        "--timeout", str(args.timeout),
    ]
    if args.direct:
        command.append("--usb-ethernet-direct")
    else:
        command.append("--hub-high-speed")
        if args.tt_compat:
            command.append("--hub-tt-compat")
            command.append("--expect-hub-tt")
    if args.full_speed:
        command.append("--usb-ethernet-full-speed")
    subprocess.run(command, cwd=ROOT, check=True)
    result = json.loads((args.out_dir / "result.json").read_text())
    print(
        "USB_ETHERNET",
        result["status"],
        result["ethernet_peer"]["status"],
        f"speed={result['usb_device_speed']}",
        result["elapsed_seconds"],
    )


if __name__ == "__main__":
    main()
