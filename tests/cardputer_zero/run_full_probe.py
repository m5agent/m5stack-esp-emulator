#!/usr/bin/env python3
"""Run the CardputerZero combined display, input, audio and power probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import socket
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CAMERA_FRAME_SHA256 = (
    "5568cf027da59228168e211e27283adaad4eaf6c299a4ad44026b0b703f7af4c"
)


def write_sine(path: Path, *, seconds: int = 2, sample_rate: int = 16000,
               frequency: int = 440, amplitude: int = 12000) -> bytes:
    samples = bytearray()
    count = seconds * sample_rate
    for index in range(count):
        value = int(amplitude * math.sin(2 * math.pi * frequency
                                        * index / sample_rate))
        frame = struct.pack("<h", value)
        samples.extend(frame)
        samples.extend(frame)
    path.write_bytes(samples)
    return bytes(samples)


def canonical_wav(payload: bytes) -> bytes:
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(payload))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 2, 16000, 64000, 4, 16)
        + b"data"
        + struct.pack("<I", len(payload))
    )
    return header + payload


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
        default=Path("/tmp/m5-cardputerzero-full"),
    )
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--usb-ethernet-direct", action="store_true")
    parser.add_argument("--usb-ethernet-full-speed", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rx_pcm = args.out_dir / "rx.pcm"
    payload = write_sine(rx_pcm)[:64000]
    expected_hash = hashlib.sha256(canonical_wav(payload)).hexdigest()
    net_socket_port = free_tcp_port()

    env = os.environ.copy()
    env.update(
        {
            "M5SW_I2S_TX_FILE": str(args.out_dir / "tx.pcm"),
            "M5SW_I2S_TX_LIMIT_BYTES": str(1 << 20),
            "M5SW_I2S_RX_FILE": str(rx_pcm),
            "M5SW_I2S_RX_LIMIT_BYTES": "64000",
            "M5SW_GPIO_TRACE": "1",
        }
    )
    append = (
        "console=ttyAMA1,115200 root=PARTUUID=f6c408b0-02 "
        "rootfstype=ext4 rootwait rw earlycon=pl011,0x3f201000 "
        "systemd.unit=multi-user.target m5.audio_probe=1 "
        "m5.camera_probe=1"
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
        "--complete-marker", "M5_KEY_FRAME_DONE",
        "--qmp-key-event", "129",
        "--qmp-charging-marker", "M5_CHARGE_PROBE_READY",
        "--expect-cardputerzero-peripherals",
        "--expect-audio-gpio24",
        "--expect-audio-capture",
        "--expected-audio-capture-sha256", expected_hash,
        "--imx219",
        "--camera-probe",
        "--expect-camera-capture",
        "--expected-camera-bytes", "614400",
        "--expected-camera-sha256", CAMERA_FRAME_SHA256,
        "--expect-charging-control",
        "--usb-ethernet",
        "--net-socket-port", str(net_socket_port),
        "--expect-sr9900a-roundtrip",
        "--expected-usb-speed",
        (
            "full"
            if args.usb_ethernet_full_speed and args.usb_ethernet_direct
            else "high"
        ),
        "--transient",
        "--timeout", str(args.timeout),
    ]
    if args.usb_ethernet_direct:
        command.append("--usb-ethernet-direct")
    else:
        command.append("--hub-high-speed")
        if args.usb_ethernet_full_speed:
            command.append("--hub-tt-compat")
            command.append("--expect-hub-tt")
    if args.usb_ethernet_full_speed:
        command.append("--usb-ethernet-full-speed")
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    result = json.loads((args.out_dir / "result.json").read_text())
    print(
        "FULL_PROBE",
        result["status"],
        f"audio={result['audio_capture_sha256']}",
        f"charge={result['charge_status_before']}->"
        f"{result['charge_status_after']}",
        f"camera={result['camera_frame_sha256']}",
        f"ethernet={result['ethernet_peer']['status']}",
        f"usb-speed={result['usb_device_speed']}",
    )


if __name__ == "__main__":
    main()
