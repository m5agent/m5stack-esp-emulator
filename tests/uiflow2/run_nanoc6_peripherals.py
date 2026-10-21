#!/usr/bin/env python3
"""Run NanoC6 RGB LED and GPIO9 button probes."""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32"
ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/pc-bios"
BASE = ROOT / "platform/.cache/firmware/nanoc6/uiflow2.bin"
HERE = Path(__file__).resolve().parent


class QMP:
    def __init__(self, path: Path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(path))
        self.file = self.sock.makefile("rwb")
        self.file.readline()
        self.command("qmp_capabilities")

    def command(self, name: str, **arguments):
        request = {"execute": name}
        if arguments:
            request["arguments"] = arguments
        self.file.write((json.dumps(request) + "\n").encode())
        self.file.flush()
        while True:
            line = self.file.readline()
            if not line:
                raise RuntimeError("QMP connection closed")
            message = json.loads(line)
            if "event" in message:
                continue
            if "error" in message:
                raise RuntimeError(f"QMP {name}: {message['error']}")
            return message.get("return")


def wait_for_text(path: Path, marker: str, proc: subprocess.Popen,
                  timeout: float) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = path.read_text(errors="replace") if path.exists() else ""
        if marker in text:
            return text
        if proc.poll() is not None:
            raise RuntimeError(f"QEMU exited before marker {marker!r}")
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {marker!r}")


def decode_ws2812(path: Path, expected: bytes) -> str:
    raw = path.read_bytes()
    if len(raw) < 4 or len(raw) % 4:
        raise RuntimeError(f"invalid RMT capture size: {len(raw)}")
    symbols = list(struct.unpack(f"<{len(raw) // 4}I", raw))
    for offset in range(0, len(symbols) - 23):
        chunk = symbols[offset:offset + 24]
        highs = [symbol & 0x7FFF for symbol in chunk]
        if max(highs) <= min(highs):
            continue
        threshold = (min(highs) + max(highs)) / 2
        bits = "".join("1" if value > threshold else "0" for value in highs)
        decoded = bytes(int(bits[i:i + 8], 2) for i in range(0, 24, 8))
        if decoded == expected:
            return decoded.hex()
    raise RuntimeError(f"WS2812 mismatch; expected {expected.hex()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--qemu", type=Path, default=QEMU)
    parser.add_argument("--rom-dir", type=Path, default=ROM_DIR)
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/tmp/m5-nanoc6-peripherals"))
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    image = args.out_dir / "nanoc6-peripherals.bin"
    image_env = os.environ.copy()
    image_env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"),
                      image_env.get("PYTHONPATH", "")])
    )
    subprocess.run(
        [
            sys.executable,
            str(HERE / "nanoc6_peripherals/make_image.py"),
            "--base", str(args.base),
            "--out", str(image),
        ],
        cwd=ROOT,
        env=image_env,
        check=True,
    )

    serial_log = args.out_dir / "serial.log"
    qmp_path = args.out_dir / "qmp.sock"
    try:
        qmp_path.unlink()
    except FileNotFoundError:
        pass
    rmt_path = args.out_dir / "rgb.rmt"
    env = os.environ.copy()
    env["M5SW_RMT_TX_FILE"] = str(rmt_path)
    env["M5SW_C6_BOARD"] = "nanoc6"
    command = [
        str(args.qemu),
        "-M", "esp32c6",
        "-drive", f"file={image},if=mtd,format=raw",
        "-L", str(args.rom_dir),
        "-display", "none",
        "-serial", "null",
        "-serial", "null",
        "-serial", f"file:{serial_log}",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
    ]
    with serial_log.open("wb") as output:
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    try:
        wait_for_text(serial_log, "NANOC6_BUTTON_READY", proc, args.timeout)
        deadline = time.time() + 15
        while not qmp_path.exists() and time.time() < deadline:
            time.sleep(0.1)
        qmp = QMP(qmp_path)
        gpio_before = {
            "gpio7": qmp.command(
                "qom-get", path="/machine", property="gpio7-level"
            ),
            "gpio9": qmp.command(
                "qom-get", path="/machine", property="gpio9-level"
            ),
            "gpio19": qmp.command(
                "qom-get", path="/machine", property="gpio19-level"
            ),
        }
        qmp.command("qom-set", path="/machine",
                    property="button-gpio9", value=True)
        time.sleep(0.3)
        qmp.command("qom-set", path="/machine",
                    property="button-gpio9", value=False)
        text = wait_for_text(
            serial_log, "NANOC6_PERIPHERAL_DONE", proc, args.timeout
        )
        gpio_after = {
            "gpio7": qmp.command(
                "qom-get", path="/machine", property="gpio7-level"
            ),
            "gpio9": qmp.command(
                "qom-get", path="/machine", property="gpio9-level"
            ),
            "gpio19": qmp.command(
                "qom-get", path="/machine", property="gpio19-level"
            ),
        }
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    checks = {
        "rgb_configured": "NANOC6_RGB_SET 0xFF0000" in text,
        "rgb_power_enabled": gpio_before["gpio19"] is True,
        "blue_on": gpio_before["gpio7"] is True,
        "blue_off": gpio_after["gpio7"] is False,
        "button_idle_high": gpio_before["gpio9"] is True,
        "button_idle_high_after": gpio_after["gpio9"] is True,
        "button_press": "NANOC6_BUTTON_PRESS 1" in text,
        "button_release": "NANOC6_BUTTON_RELEASE 0" in text,
    }
    decoded = decode_ws2812(rmt_path, bytes((0, 255, 0)))
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "gpio_before": gpio_before,
        "gpio_after": gpio_after,
        "ws2812_grb": decoded,
        "rmt_capture_bytes": rmt_path.stat().st_size,
        "command": command,
    }
    (args.out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        "NANOC6_PERIPHERALS",
        result["status"],
        f"rgb_grb={decoded}",
        f"button={checks['button_press'] and checks['button_release']}",
    )
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
