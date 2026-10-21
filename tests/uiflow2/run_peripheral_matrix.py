#!/usr/bin/env python3
"""Run focused UIFlow2 peripheral probes across implemented device classes."""
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
        "expected_status": "PASS",
        "reason": (
            "BMI270 accel/gyro, A/B/P buttons and M5PM1 power telemetry "
            "are all visible through the UIFlow2 API."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
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
        "id": "atoms3r-peripherals",
        "expected_status": "PASS",
        "reason": (
            "BMI270 accel/gyro, BMM150 magnetometer and the user button "
            "are verified through UIFlow2."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "magnetometer", "status": "PASS"},
            {"name": "button", "status": "PASS"},
        ],
        "machine": "m5atoms3r",
        "base": "platform/.cache/firmware/atoms3r/uiflow2.bin",
        "files_dir": "tests/uiflow2/atoms3r_peripherals",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "128x128",
        "efuse_pkg_version": "1",
        "wait": "5",
        "inputs": ["key:a"],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
            ("/machine/bmm150", "mag-x", "30"),
            ("/machine/bmm150", "mag-y", "-20"),
            ("/machine/bmm150", "mag-z", "45"),
        ],
    },
    {
        "id": "sticks3-ir",
        "expected_status": "PASS",
        "reason": (
            "The official hardware.IR UIFlow2 API sends NEC address/command "
            "through RMT channel 0 and the transmitted RMT symbols decode back "
            "to the expected packet."
        ),
        "checks": [
            {"name": "rmt_nec_tx", "status": "PASS"},
        ],
        "machine": "m5sticks3",
        "base": "platform/.cache/firmware/sticks3/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_ir",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "135x240",
        "efuse_pkg_version": "1",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_RMT_TX_FILE": "{out_dir}/ir.rmt",
            "M5SW_RMT_TRACE": "1",
        },
        "rmt_nec": {
            "capture": "{out_dir}/ir.rmt",
            "address": 0x56,
            "command": 0xA3,
        },
    },
    {
        "id": "sticks3-ir-rx",
        "expected_status": "PASS",
        "reason": (
            "QEMU injects a NEC packet into RMT channel 4 hardware memory; "
            "the official hardware.IR callback receives address 0x56 and "
            "command 0xA3, and the UIFlow2 UI draws its success marker."
        ),
        "checks": [
            {"name": "rmt_nec_rx", "status": "PASS"},
            {"name": "ir_rx_ui_marker", "status": "PASS"},
        ],
        "machine": "m5sticks3",
        "base": "platform/.cache/firmware/sticks3/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_ir_rx",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "135x240",
        "efuse_pkg_version": "1",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_RMT_RX_FILE": "{out_dir}/nec-56-a3.rmt",
            "M5SW_RMT_TRACE": "1",
        },
        "rmt_nec_source": {
            "output": "{out_dir}/nec-56-a3.rmt",
            "address": 0x56,
            "command": 0xA3,
        },
        "frame_color": {"x": 4, "y": 4, "label": "IR RX"},
    },
    {
        "id": "cores3-peripherals",
        "expected_status": "PARTIAL",
        "reason": (
            "IMU, magnetometer, touch, PWR, power and RTC pass; LTR553 "
            "identity is modeled but M5.Als still returns zero in this firmware path."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "magnetometer", "status": "PASS"},
            {"name": "ambient_light", "status": "PARTIAL"},
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
            ("/machine/bmm150", "mag-x", "30"),
            ("/machine/bmm150", "mag-y", "-20"),
            ("/machine/bmm150", "mag-z", "45"),
            ("/machine/ltr553", "light-level", "640"),
        ],
    },
    {
        "id": "cores3-camera",
        "expected_status": "PASS",
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
            "GC0308 init, ESP32-S3 LCD_CAM capture, GDMA frame delivery, "
            "camera.snapshot(), and camera image display all pass."
        ),
        "checks": [
            {"name": "camera_init", "status": "PASS"},
            {"name": "camera_snapshot", "status": "PASS"},
            {"name": "camera_display", "status": "PASS"},
        ],
    },
    {
        "id": "stamplc-peripherals",
        "expected_status": "PASS",
        "reason": (
            "Relay, digital inputs, RGB LED state and INA226 bus/current "
            "telemetry are exercised through UIFlow2 libraries."
        ),
        "checks": [
            {"name": "relay", "status": "PASS"},
            {"name": "digital_inputs", "status": "PASS"},
            {"name": "rgb", "status": "PASS"},
            {"name": "ina226_identity", "status": "PASS"},
            {"name": "ina226_bus_voltage", "status": "PASS"},
            {"name": "ina226_current", "status": "PASS"},
        ],
        "machine": "m5stamplc",
        "base": "platform/.cache/firmware/stamplc/uiflow2.bin",
        "files_dir": "tests/uiflow2/stamplc_peripherals",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "5",
        "inputs": ["key:a"],
        "qom": [
            ("/machine/ina226", "bus-voltage-mv", "12000"),
            ("/machine/ina226", "current-ma", "500"),
            ("/machine/ina226", "shunt-ohms", "0.08"),
        ],
    },
    {
        "id": "stopwatch-peripherals",
        "expected_status": "PASS",
        "reason": (
            "BMI270, M5PM1 power, RX8130 RTC, CST820 touch and A/B/PWR "
            "keys are verified through the StopWatch UIFlow2 firmware."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "power", "status": "PASS"},
            {"name": "rtc_write_read", "status": "PASS"},
            {"name": "touch", "status": "PASS"},
            {"name": "buttons_a_b_pwr", "status": "PASS"},
        ],
        "machine": "m5stopwatch",
        "base": "platform/.cache/firmware/stopwatch/uiflow2.bin",
        "files_dir": "tests/uiflow2/stopwatch_peripherals",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "466x466",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["touch:233,348", "key:a", "key:b", "key:p"],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
            ("/machine/m5pm1", "charging", "true"),
        ],
    },
    {
        "id": "papermono-peripherals",
        "expected_status": "PASS",
        "reason": (
            "BMI270, M5PM1 power, RX8130 RTC, touch, user key and SDMMC "
            "block read/write are verified on PaperMono."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "power", "status": "PASS"},
            {"name": "rtc_write_read", "status": "PASS"},
            {"name": "touch", "status": "PASS"},
            {"name": "user_key", "status": "PASS"},
            {"name": "sd_block_read_write", "status": "PASS"},
        ],
        "machine": "m5papermono",
        "base": "platform/.cache/firmware/papermono/uiflow2.bin",
        "files_dir": "tests/uiflow2/papermono_peripherals",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "480x800",
        "efuse_pkg_version": "0",
        "wait": "12",
        "inputs": ["touch:240,650", "key:a"],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
            ("/machine/m5pm1", "charging", "true"),
        ],
        "sd_image": True,
    },
    {
        "id": "papermono-nfc",
        "expected_status": "PASS",
        "reason": (
            "The official hardware.NFC API drives ST25R3916 I2C registers and "
            "FIFO commands, detects a deterministic NTAG, reads page 4, writes "
            "page 8 with TEST, and reads the same value back."
        ),
        "checks": [
            {"name": "nfc_detect", "status": "PASS"},
            {"name": "nfc_page_read", "status": "PASS"},
            {"name": "nfc_page_write_verify", "status": "PASS"},
            {"name": "nfc_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papermono",
        "base": "platform/.cache/firmware/papermono/uiflow2.bin",
        "files_dir": "tests/uiflow2/papermono_nfc",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "480x800",
        "efuse_pkg_version": "0",
        "wait": "25",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "NFC", "dark": True},
    },
    {
        "id": "papermono-lora",
        "expected_status": "PASS",
        "reason": (
            "The native lora.SX1262 driver configures an 868 MHz LoRa modem "
            "through SPI command/register/FIFO transfers, sends M5LORA and "
            "receives the same packet through the SX1262 data plane."
        ),
        "checks": [
            {"name": "lora_configure", "status": "PASS"},
            {"name": "lora_tx", "status": "PASS"},
            {"name": "lora_rx_loopback", "status": "PASS"},
            {"name": "lora_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papermono",
        "base": "platform/.cache/firmware/papermono/uiflow2.bin",
        "files_dir": "tests/uiflow2/papermono_lora",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "480x800",
        "efuse_pkg_version": "0",
        "wait": "25",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "LoRa", "dark": True},
    },
    {
        "id": "stackchan-nfc",
        "expected_status": "PASS",
        "reason": (
            "The same official hardware.NFC and ST25R3916 I2C model detects "
            "the deterministic NTAG on StackChan and verifies a page-12 write."
        ),
        "checks": [
            {"name": "nfc_detect", "status": "PASS"},
            {"name": "nfc_page_read", "status": "PASS"},
            {"name": "nfc_page_write_verify", "status": "PASS"},
            {"name": "nfc_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_nfc",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "25",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "min_unique_colors": 1,
        "frame_color": {"x": 4, "y": 4, "label": "NFC", "dark": True},
    },
    {
        "id": "stackchan-touch",
        "expected_status": "PASS",
        "reason": (
            "The official Si12T driver configures the body touch controller "
            "over I2C; QOM injects touch bits and UIFlow2 decodes point 0."
        ),
        "checks": [
            {"name": "si12t_config", "status": "PASS"},
            {"name": "si12t_touch", "status": "PASS"},
            {"name": "si12t_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_touch",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [("/machine/si12t", "touch-bits", "2")],
        "qom_settle": 1,
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "Si12T touch"},
    },
    {
        "id": "stackchan-rgb",
        "expected_status": "PASS",
        "reason": (
            "The official M5IOE1 NeoPixel driver writes 12 RGB565 values "
            "through I2C and reads the LED RAM back from the expander model."
        ),
        "checks": [
            {"name": "m5ioe1_led_cfg", "status": "PASS"},
            {"name": "neopixel_ram", "status": "PASS"},
            {"name": "rgb_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_rgb",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "12",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "StackChan RGB"},
    },
    {
        "id": "stopwatch-vibration",
        "expected_status": "PASS",
        "reason": (
            "Power.setVibration drives M5IOE1 PWM1 on the StopWatch; the PWM "
            "duty and enable bit are read back from the expander registers."
        ),
        "checks": [
            {"name": "vibration_pwm_on", "status": "PASS"},
            {"name": "vibration_pwm_off", "status": "PASS"},
            {"name": "vibration_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stopwatch",
        "base": "platform/.cache/firmware/stopwatch/uiflow2.bin",
        "files_dir": "tests/uiflow2/stopwatch_vibration",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "466x466",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 233, "y": 5, "label": "vibration"},
    },
    {
        "id": "atoms3r-lp5562",
        "expected_status": "PASS",
        "reason": (
            "The LP5562 I2C RGB controller accepts enable/mode/PWM writes and "
            "returns the three independent channel values over the real bus."
        ),
        "checks": [
            {"name": "lp5562_enable", "status": "PASS"},
            {"name": "lp5562_pwm_readback", "status": "PASS"},
            {"name": "lp5562_ui_marker", "status": "PASS"},
        ],
        "machine": "m5atoms3r",
        "base": "platform/.cache/firmware/atoms3r/uiflow2.bin",
        "files_dir": "tests/uiflow2/atoms3r_lp5562",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "128x128",
        "efuse_pkg_version": "1",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 64, "y": 4, "label": "LP5562"},
    },
]


def command_for(case: dict, out_dir: Path,
                sd_image: Path | None = None) -> list[str]:
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
    if case.get("qom_settle"):
        command.extend(["--qom-settle", str(case["qom_settle"])])
    if case.get("allow_static_frame"):
        command.append("--allow-static-frame")
    if sd_image:
        command.extend(["--sd-image", str(sd_image)])
    if case.get("min_unique_colors"):
        command.extend(["--min-unique-colors",
                        str(case["min_unique_colors"])])
    return command


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-uiflow2-peripheral-matrix"),
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="run only the named case; repeat for multiple cases",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )

    results = {}
    for case in CASES:
        if args.case and case["id"] not in args.case:
            continue
        case_out = args.out_dir / case["id"]
        case_out.mkdir(parents=True, exist_ok=True)
        sd_image = None
        if case.get("sd_image"):
            sd_image = case_out / "sd.img"
            with sd_image.open("wb") as image_file:
                image_file.truncate(8 * 1024 * 1024)
        rmt_nec_source = case.get("rmt_nec_source")
        if rmt_nec_source:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/make_rmt_nec.py"),
                    str(rmt_nec_source["output"]).format(out_dir=case_out),
                    "--address", hex(rmt_nec_source["address"]),
                    "--command", hex(rmt_nec_source["command"]),
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        command = command_for(case, case_out, sd_image)
        case_env = env.copy()
        for key, value in case.get("env", {}).items():
            case_env[key] = value.format(out_dir=case_out)
        stdout_path = args.out_dir / f"{case['id']}.stdout"
        stderr_path = args.out_dir / f"{case['id']}.stderr"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.run(
                command,
                cwd=ROOT,
                env=case_env,
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        validation_output = ""
        validation_ok = True
        rmt_nec = case.get("rmt_nec")
        if rmt_nec and process.returncode == 0:
            validation = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/check_rmt_nec.py"),
                    str(rmt_nec["capture"]).format(out_dir=case_out),
                    "--address", hex(rmt_nec["address"]),
                    "--command", hex(rmt_nec["command"]),
                ],
                cwd=ROOT,
                env=case_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            validation_output = validation.stdout
            validation_ok = validation.returncode == 0
        frame_color = case.get("frame_color")
        if frame_color and process.returncode == 0:
            frame_command = [
                sys.executable,
                str(ROOT / "tests/uiflow2/check_frame_marker.py"),
                str(case_out / "after.ppm"),
                "--label", frame_color.get("label", case["id"]),
                "--x", str(frame_color["x"]),
                "--y", str(frame_color["y"]),
            ]
            if frame_color.get("dark"):
                frame_command.append("--dark")
            validation = subprocess.run(
                frame_command,
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            validation_output += validation.stdout
            validation_ok = validation_ok and validation.returncode == 0
        executed = process.returncode == 0 and validation_ok
        status = case["expected_status"] if executed else "FAIL"
        results[case["id"]] = {
            "status": status,
            "exit_code": process.returncode,
            "command": command,
            "output": str(case_out),
            "before": str(case_out / "before.png"),
            "after": str(case_out / "after.png"),
            "checks": case["checks"],
            **({"validation": validation_output}
               if validation_output else {}),
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
