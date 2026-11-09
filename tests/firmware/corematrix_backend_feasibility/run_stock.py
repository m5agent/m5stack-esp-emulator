#!/usr/bin/env python3
"""Reproduce the CoreMatrix stock boot on a candidate ESP32-C61 QEMU."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


FIRMWARE_SIZE = 16_773_120
FIRMWARE_SHA256 = "0bfbe5a4acb467d93a7ded2186a4f73adea37511869328b563c15ab73163a018"
ROM_SHA256 = "ba93108d967771826a8ba024da8c7002cf3c2c4346d600246b2fa882d95b30ec"
FLASH_SIZE = 16 * 1024 * 1024


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--corematrix", action="store_true", help="enable the candidate C158 board wiring")
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("--timeout must be greater than 0 and at most 120 seconds")
    if args.firmware.stat().st_size != FIRMWARE_SIZE or sha256(args.firmware) != FIRMWARE_SHA256:
        parser.error("firmware must be the pinned CoreMatrix UIFlow2 v2.5.4 image")
    if sha256(args.rom) != ROM_SHA256:
        parser.error("ROM must match the pinned upstream ESP32-C61 ROM")

    qemu = args.qemu.resolve(strict=True)
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    flash = output / "flash.bin"
    flash.write_bytes(args.firmware.read_bytes() + b"\xff" * (FLASH_SIZE - FIRMWARE_SIZE))
    flash_sha256 = sha256(flash)
    machine = "esp32c61,m5corematrix=on" if args.corematrix else "esp32c61"
    command = [
        str(qemu), "-machine", machine, "-bios", str(args.rom.resolve()),
        "-drive", f"file={flash.name},if=mtd,format=raw", "-display", "none",
        "-monitor", "none", "-nic", "none", "-no-reboot",
        "-serial", "file:uart0.log", "-serial", "null", "-serial", "null",
        "-serial", "file:usb-serial.log",
    ]
    returncode = None
    frame = None
    timed_out = False
    if args.corematrix:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "uiflow2"))
        from run_profile_ui_test import read_ppm, wait_qmp
        command.extend(["-qmp", "unix:monitor.sock,server=on,wait=off"])

    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        with subprocess.Popen(command, cwd=output, stdout=stdout, stderr=stderr,
                              stdin=subprocess.DEVNULL) as proc:
            try:
                returncode = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    if args.corematrix:
                        qmp = wait_qmp(output / "monitor.sock", timeout=3)
                        try:
                            ppm = output / "stock.ppm"
                            qmp.cmd("screendump", filename=str(ppm))
                            width, height, rgb = read_ppm(ppm)
                            frame = {"width": width, "height": height,
                                     "nonzero_channels": sum(byte != 0 for byte in rgb),
                                     "sha256": sha256(ppm)}
                            qmp.cmd("quit")
                        finally:
                            qmp.close()
                        returncode = proc.wait(timeout=3)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()

    serial_sizes = {}
    for name in ("uart0.log", "usb-serial.log", "stdout.log", "stderr.log"):
        log = output / name
        serial_sizes[name] = log.stat().st_size if log.exists() else 0
    summary = {
        "machine": machine,
        "qemu_sha256": sha256(qemu),
        "rom_sha256": ROM_SHA256,
        "firmware_sha256": FIRMWARE_SHA256,
        "padded_flash_sha256": flash_sha256,
        "timeout_seconds": args.timeout,
        "timed_out": timed_out,
        "returncode": returncode,
        "captured_bytes": serial_sizes,
        "frame": frame,
    }
    (output / "run-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
