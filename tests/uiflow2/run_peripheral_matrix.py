#!/usr/bin/env python3
"""Run focused UIFlow2 peripheral probes across implemented device classes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
COVERAGE = ROOT / "platform/peripherals/runtime-coverage.json"
QEMU = Path(os.environ.get("M5_QEMU_XTENSA", ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"))
ROM_DIR = Path(os.environ.get("M5_QEMU_XTENSA_ROM_DIR", ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"))
QEMU_C6 = Path(os.environ.get("M5_QEMU_RISCV32", ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32"))
ROM_DIR_C6 = Path(os.environ.get("M5_QEMU_RISCV32_ROM_DIR", ROOT / ".work/M5StopWatch-QEMU/build/qemu-c6/pc-bios"))

DEFAULT_SERIAL_FAILURES = (
    "Guru Meditation Error:",
    "MPY version :",
    "Traceback (most recent call last):",
    "status=error",
    "FAIL",
)

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
        "serial_expect": [
            "STICKS3_IMU_TYPE 6",
            "STICKS3_BATTERY 87 4000 0",
            "STICKS3_BTN_A 1",
            "STICKS3_BTN_B 1",
            "STICKS3_BTN_PWR 1",
            "STICKS3_IMU 0.250 -0.500 0.750",
        ],
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
        "id": "sticks3-audio",
        "expected_status": "PASS",
        "reason": (
            "Speaker.begin(), ES8311 I2C setup, I2S TX, cyclic GDMA "
            "descriptor completion and host PCM capture all pass."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "i2s_gdma_capture", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5sticks3",
        "base": "platform/.cache/firmware/sticks3/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_audio",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "135x240",
        "efuse_pkg_version": "1",
        "wait": "4",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "qom_expect": [
            ("/machine/m5pm1", "pa-enabled", "true"),
        ],
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "StickS3 audio"},
    },
    {
        "id": "sticks3-mic",
        "expected_status": "PASS",
        "reason": (
            "The official Mic API records through I2S RX and cyclic GDMA; "
            "host PCM injection is returned non-silent to the UIFlow2 buffer."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "mic_record", "status": "PASS"},
            {"name": "i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5sticks3",
        "base": "platform/.cache/firmware/sticks3/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_mic",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "135x240",
        "efuse_pkg_version": "1",
        "wait": "5",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {"x": 4, "y": 4, "label": "StickS3 mic"},
    },
    {
        "id": "cardputer-adv-sd",
        "expected_status": "PASS",
        "reason": (
            "The documented Cardputer-ADV SPI SD pins are used with the "
            "machine.SDCard block API; a 512-byte write and readback match "
            "the raw QEMU SD image."
        ),
        "checks": [
            {"name": "sdspi_init", "status": "PASS"},
            {"name": "sdspi_write_block", "status": "PASS"},
            {"name": "sdspi_readback", "status": "PASS"},
            {"name": "sd_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_sd",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "22",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "sd_image": True,
        "env": {
            "M5SW_SPI_SD_IMAGE": "{out_dir}/sd.img",
        },
        "disk": {
            "image": "{out_dir}/sd.img",
            "sector": 100,
        },
        "frame_color": {"x": 4, "y": 4, "label": "Cardputer-ADV SD"},
    },
    {
        "id": "cores3-sd",
        "expected_status": "PASS",
        "reason": (
            "The board-wired CoreS3 SPI SD path uses the official M5Unified "
            "pin table; native SDCard writes and reads a sector and an "
            "independent host oracle checks the retained raw image."
        ),
        "checks": [
            {"name": "sdspi_init", "status": "PASS"},
            {"name": "sdspi_write_block", "status": "PASS"},
            {"name": "sdspi_readback", "status": "PASS"},
            {"name": "sd_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_sd",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "22",
        "inputs": [],
        "qom": [],
        "allow_static_frame": True,
        "sd_image": True,
        "env": {"M5SW_SPI_SD_IMAGE": "{out_dir}/sd.img"},
        "disk": {"image": "{out_dir}/sd.img", "sector": 100},
        "pre_input_marker": "CORES3_SD_READY",
        "post_input_marker": "CORES3_SD_DRAW_COMPLETE",
        "serial_expect": ["CORES3_SD_RW_PASS", "CORES3_SD_DRAW_COMPLETE"],
        "frame_color": {"x": 4, "y": 4, "label": "CoreS3 SD"},
    },
    {
        "id": "cardputer-adv-imu",
        "expected_status": "PASS",
        "reason": (
            "The Cardputer-ADV BMI270 at I2C 0x69 is initialized by "
            "M5Unified and QOM physical values reach Imu.getAccel/getGyro."
        ),
        "checks": [
            {"name": "cardputer_bmi270_init", "status": "PASS"},
            {"name": "cardputer_bmi270_accel", "status": "PASS"},
            {"name": "cardputer_bmi270_gyro", "status": "PASS"},
            {"name": "cardputer_imu_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_peripherals",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
        ],
        "allow_static_frame": True,
        "frame_color": {
            "x": 4, "y": 4, "label": "Cardputer-ADV BMI270",
        },
    },
    {
        "id": "cardputer-adv-keyboard",
        "expected_status": "PASS",
        "reason": (
            "A QMP key event enters the TCA8418 matrix-controller FIFO, "
            "raises the controller interrupt path, and is decoded by the "
            "official UIFlow2 KeyboardI2C API."
        ),
        "checks": [
            {"name": "tca8418_matrix_event", "status": "PASS"},
            {"name": "keyboard_i2c_decode", "status": "PASS"},
            {"name": "keyboard_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_ui_test",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "post_input_wait": 2,
        "qom": [],
        "frame_color": {
            "x": 4, "y": 4, "label": "Cardputer-ADV TCA8418",
        },
    },
    {
        "id": "cardputer-adv-nfc",
        "expected_status": "PASS",
        "reason": (
            "The Cardputer-ADV ST25R3916 is reached over the shared SPI2 "
            "bus with NFC CS G6; Type 2 UID/page reads and a page-8 write "
            "and readback pass."
        ),
        "checks": [
            {"name": "cardputer_nfc_spi_detect", "status": "PASS"},
            {"name": "cardputer_nfc_page_read", "status": "PASS"},
            {"name": "cardputer_nfc_page_write_verify", "status": "PASS"},
            {"name": "cardputer_nfc_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_nfc",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "12",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_SPI_XFER_TRACE": "1",
        },
        "frame_color": {"x": 4, "y": 4, "label": "Cardputer-ADV NFC"},
    },
    {
        "id": "cardputer-adv-cc1101",
        "expected_status": "PASS",
        "reason": (
            "The Cardputer-ADV CC1101 Cap configures over shared SPI2 "
            "with CS G5, sends M5CC1101 and receives the chip FIFO "
            "loopback through the official cap.CC1101Cap API."
        ),
        "checks": [
            {"name": "cardputer_cc1101_spi_configure", "status": "PASS"},
            {"name": "cardputer_cc1101_tx", "status": "PASS"},
            {"name": "cardputer_cc1101_rx_loopback", "status": "PASS"},
            {"name": "cardputer_cc1101_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_cc1101",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "15",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_SPI_XFER_TRACE": "1",
            "M5SW_CC1101_TRACE": "1",
        },
        "frame_color": {"x": 4, "y": 4, "label": "Cardputer-ADV CC1101"},
    },
    {
        "id": "cardputer-adv-audio",
        "expected_status": "PASS",
        "reason": (
            "The official Speaker API drives ES8311 and NS4150B through I2S "
            "TX and cyclic GDMA; host PCM capture contains the generated tone."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "i2s_gdma_capture", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_audio",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "Cardputer-ADV audio"},
    },
    {
        "id": "cardputer-adv-mic",
        "expected_status": "PASS",
        "reason": (
            "The official Mic API records through ES8311, I2S RX and cyclic "
            "GDMA; deterministic host PCM injection reaches the buffer."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "mic_record", "status": "PASS"},
            {"name": "i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/cardputer_adv_mic",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "9",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {"x": 4, "y": 4, "label": "Cardputer-ADV mic"},
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
        "serial_expect": [
            "ATOMS3R_IMU_TYPE 6",
            "ATOMS3R_BTN 1",
            "ATOMS3R_ACCEL -0.50 -0.25 0.75",
            "ATOMS3R_GYRO -20.02 -10.01 30.03",
            "ATOMS3R_MAG -29.99 -19.49 -89.96",
        ],
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
        "expected_status": "PASS",
        "reason": (
            "IMU, magnetometer, touch, PWR, power, RTC and LTR553 ambient "
            "light/proximity all pass through their real buses."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "magnetometer", "status": "PASS"},
            {"name": "ambient_light", "status": "PASS"},
            {"name": "proximity", "status": "PASS"},
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
        "inputs": ["longpress:160,183,2.5", "key:p"],
        "pre_input_marker": "CORES3_PERIPHERAL_INPUT_READY",
        "post_input_marker": "CORES3_PERIPHERAL_DRAW_COMPLETE",
        "serial_expect": [
            "CORES3_IMU_TYPE 6",
            "CORES3_POWER 87 4000 1",
            "CORES3_ALS 640 321",
            "CORES3_MAG",
            "CORES3_TOUCH",
            "CORES3_BTN_PWR 1",
            "CORES3_IMU 0.250 -0.500 0.750",
            "CORES3_RTC 2026-10-22 06:07:08",
        ],
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
            ("/machine/ltr553", "proximity-level", "321"),
        ],
    },
    {
        "id": "cores3-power-transitions",
        "expected_status": "PASS",
        "reason": (
            "The UIFlow2 application remains running while AXP2101 battery "
            "level, voltage, VBUS and charging state change through a QOM "
            "runtime sequence; the official Power API observes every state."
        ),
        "checks": [
            {"name": "axp2101_initial_power_state", "status": "PASS"},
            {"name": "axp2101_runtime_discharge_state", "status": "PASS"},
            {"name": "axp2101_runtime_charge_state", "status": "PASS"},
            {"name": "power_runtime_sequence_complete", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_power_transitions",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "4",
        "inputs": [],
        "qom_steps": [
            (0.8, "/machine/axp2101", "battery-level", "64"),
            (0, "/machine/axp2101", "vbat-mv", "3600"),
            (0, "/machine/axp2101", "vin-mv", "0"),
            (0, "/machine/axp2101", "charging", "false"),
            (2.0, "/machine/axp2101", "battery-level", "93"),
            (0, "/machine/axp2101", "vbat-mv", "4200"),
            (0, "/machine/axp2101", "vin-mv", "5000"),
            (0, "/machine/axp2101", "charging", "true"),
        ],
        "qom_sequence_settle": 2.0,
        "serial_expect": [
            "CORES3_POWER_TRANS 87 4000 1",
            "CORES3_POWER_TRANS 64 3600 0",
            "CORES3_POWER_TRANS 93 4200 1",
            "CORES3_POWER_TRANS_DONE PASS",
        ],
        "frame_color": {
            "x": 310,
            "y": 230,
            "label": "CoreS3 PMIC transitions",
        },
        "allow_static_frame": True,
    },
    {
        "id": "cores3-usb-hid",
        "expected_status": "PASS",
        "reason": (
            "The official module.USBModule enumerates a MAX3421E HID "
            "device over the CoreS3 M-Bus SPI register/FIFO path and "
            "returns the QOM-injected mouse report."
        ),
        "checks": [
            {"name": "max3421e_config", "status": "PASS"},
            {"name": "usb_chapter9_enumeration", "status": "PASS"},
            {"name": "usb_hid_report_descriptor", "status": "PASS"},
            {"name": "usb_hid_interrupt_in_report", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_usb_hid",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "14",
        "inputs": ["touch:160,183"],
        "qom_set_boot": [
            ("/machine/max3421e-usb", "mouse-x", "5"),
            ("/machine/max3421e-usb", "mouse-y", "-3"),
            ("/machine/max3421e-usb", "mouse-buttons", "1"),
        ],
        "qom_expect": [
            ("/machine/max3421e-usb", "enumerated", "1"),
            ("/machine/max3421e-usb", "last-report", "1"),
        ],
        "allow_static_frame": True,
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
        "qom_set_boot": [
            ("/machine/m5-lcd-cam", "auto-increment", "true"),
        ],
        "post_input_wait": 3.0,
        "allow_static_frame": True,
        "serial_expect": [
            "CORES3_CAMERA_PASS 320x240 153600 bytes",
            "CORES3_CAMERA_FRAMESTREAM PASS 1",
        ],
        "reason": (
            "GC0308 init, ESP32-S3 LCD_CAM capture, GDMA frame delivery, "
            "camera.snapshot(), and camera image display all pass."
        ),
        "checks": [
            {"name": "camera_init", "status": "PASS"},
            {"name": "camera_snapshot", "status": "PASS"},
            {"name": "camera_display", "status": "PASS"},
            {"name": "camera_runtime_frame_change", "status": "PASS"},
            {"name": "camera_runtime_frame_stream", "status": "PASS"},
        ],
    },
    {
        "id": "stackchan-camera",
        "expected_status": "PASS",
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_camera",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["touch:160,183"],
        "qom": [],
        "allow_static_frame": True,
        "serial_expect": [
            "CORES3_CAMERA_PASS 320x240 153600 bytes",
        ],
        "reason": (
            "StackChan GC0308 SCCB, ESP32-S3 LCD_CAM, GDMA frame delivery, "
            "snapshot and camera image display all pass."
        ),
        "checks": [
            {"name": "stackchan_camera_init", "status": "PASS"},
            {"name": "stackchan_camera_snapshot", "status": "PASS"},
            {"name": "stackchan_camera_display", "status": "PASS"},
        ],
    },
    {
        "id": "cores3-audio",
        "expected_status": "PASS",
        "reason": (
            "Speaker.begin(), AW88298 setup, I2S TX, cyclic GDMA "
            "descriptor completion and host PCM capture all pass."
        ),
        "checks": [
            {"name": "aw88298_configure", "status": "PASS"},
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "i2s_gdma_capture", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_audio",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "4",
        "pre_input_marker": "CORES3_AUDIO_DRAW_COMPLETE ok",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "CoreS3 audio"},
    },
    {
        "id": "cores3-mic",
        "expected_status": "PASS",
        "reason": (
            "The official Mic API records through ES7210, I2S RX and cyclic "
            "GDMA; deterministic host PCM injection reaches the buffer."
        ),
        "checks": [
            {"name": "es7210_configure", "status": "PASS"},
            {"name": "mic_record", "status": "PASS"},
            {"name": "i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_mic",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "6",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {"x": 4, "y": 4, "label": "CoreS3 mic"},
    },
    {
        "id": "stamplc-peripherals",
        "expected_status": "PASS",
        "reason": (
            "Relay, digital inputs, RGB LED state, RX8130 RTC and INA226 "
            "bus/current telemetry are exercised through UIFlow2 libraries."
        ),
        "checks": [
            {"name": "relay", "status": "PASS"},
            {"name": "digital_inputs", "status": "PASS"},
            {"name": "rgb", "status": "PASS"},
            {"name": "ina226_identity", "status": "PASS"},
            {"name": "ina226_bus_voltage", "status": "PASS"},
            {"name": "ina226_current", "status": "PASS"},
            {"name": "ina226_runtime_transition", "status": "PASS"},
            {"name": "rx8130_rtc_write_read", "status": "PASS"},
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
        "serial_expect": [
            "STAMPLC_PERIPHERAL_MAIN",
            "STAMPLC_RELAY 1 PRESS 1",
            "STAMPLC_INPUTS",
            "STAMPLC_INA 12.00 0.500",
            "STAMPLC_INA 15.00 0.750",
            "STAMPLC_RGB True False False",
            "STAMPLC_RTC 2026-10-22 07:08:09",
        ],
        "qom": [
            ("/machine/ina226-40", "bus-voltage-mv", "12000"),
            ("/machine/ina226-40", "current-ma", "500"),
            ("/machine/ina226-40", "shunt-ohms", "0.08"),
        ],
        "qom_steps": [
            (1.0, "/machine/ina226-40", "bus-voltage-mv", "15000"),
            (0, "/machine/ina226-40", "current-ma", "750"),
        ],
        "qom_sequence_settle": 1.5,
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
        "serial_expect": [
            "STOPWATCH_IMU_TYPE 6",
            "STOPWATCH_POWER 87 4000 1",
            "STOPWATCH_RTC 2026-10-22 07:08:09",
            "STOPWATCH_TOUCH",
            "STOPWATCH_BTN_A 1",
            "STOPWATCH_BTN_B 1",
            "STOPWATCH_BTN_PWR 1",
            "STOPWATCH_ACCEL 0.25 -0.50 0.75",
        ],
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
            "BMI270, M5PM1 power, RX8130 RTC, touch, user and power keys, "
            "and SDMMC block read/write are verified on PaperMono."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "power", "status": "PASS"},
            {"name": "rtc_write_read", "status": "PASS"},
            {"name": "touch", "status": "PASS"},
            {"name": "user_key", "status": "PASS"},
            {"name": "power_key", "status": "PASS"},
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
        "inputs": ["touch:240,650", "key:a", "key:p"],
        "qom_set_boot": [
            ("/machine/ip2315", "charging", "true"),
        ],
        "serial_expect": [
            "PAPERMONO_IMU_TYPE 6",
            "PAPERMONO_POWER 87 4000 1",
            "PAPERMONO_RTC 2026-10-22 07:08:09",
            "PAPERMONO_SD rw ok",
            "PAPERMONO_TOUCH",
            "PAPERMONO_KEY 1",
            "PAPERMONO_PWR 1",
            "PAPERMONO_ACCEL 0.25 -0.50 0.75",
        ],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
        ],
        "sd_image": True,
    },
    {
        "id": "papermono-buzzer",
        "expected_status": "PASS",
        "reason": (
            "The official Speaker API drives PaperMono GPIO42 through ESP32-S3 "
            "I2S TX and cyclic GDMA; host PCM capture contains the buzzer tone."
        ),
        "checks": [
            {"name": "speaker_begin", "status": "PASS"},
            {"name": "gpio42_i2s_tx", "status": "PASS"},
            {"name": "buzzer_pcm_capture", "status": "PASS"},
            {"name": "papermono_buzzer_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papermono",
        "base": "platform/.cache/firmware/papermono/uiflow2.bin",
        "files_dir": "tests/uiflow2/papermono_buzzer",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "480x800",
        "efuse_pkg_version": "0",
        "wait": "6",
        "inputs": [],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/buzzer.pcm",
        },
        "serial_expect": [
            "PAPERMONO_BUZZER ok 3500Hz",
        ],
        "pcm": {
            "capture": "{out_dir}/buzzer.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 30000,
        },
        "frame_color": {
            "x": 4, "y": 4, "label": "PaperMono buzzer", "dark": True,
        },
    },
    {
        "id": "papermono-pdm-mic",
        "expected_status": "PASS",
        "reason": (
            "The built-in PDM microphone records through I2S RX and cyclic "
            "GDMA; deterministic host PCM injection reaches the UIFlow2 buffer."
        ),
        "checks": [
            {"name": "pdm_mic_begin", "status": "PASS"},
            {"name": "pdm_mic_record", "status": "PASS"},
            {"name": "pdm_i2s_rx_injection", "status": "PASS"},
            {"name": "pdm_mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papermono",
        "base": "platform/.cache/firmware/papermono/uiflow2.bin",
        "files_dir": "tests/uiflow2/papermono_mic",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "480x800",
        "efuse_pkg_version": "0",
        "wait": "6",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {
            "x": 4, "y": 4, "label": "PaperMono PDM mic", "dark": True,
        },
    },
    {
        "id": "papermono-rgb",
        "expected_status": "PASS",
        "reason": (
            "M5.Led programs the PaperMono RGB LED and the RGB565 value is "
            "read back from the M5PM1 NeoPixel RAM over I2C."
        ),
        "checks": [
            {"name": "papermono_rgb_set", "status": "PASS"},
            {"name": "papermono_m5pm1_neopixel_ram", "status": "PASS"},
            {"name": "papermono_rgb_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papermono",
        "base": "platform/.cache/firmware/papermono/uiflow2.bin",
        "files_dir": "tests/uiflow2/papermono_rgb",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "480x800",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "PaperMono RGB", "dark": True},
    },
    {
        "id": "papercolor-peripherals",
        "expected_status": "PASS",
        "reason": (
            "The PaperColor M5PM1 power telemetry, RX8130 RTC, user key and "
            "power key are exercised through their board data paths."
        ),
        "checks": [
            {"name": "m5pm1_power", "status": "PASS"},
            {"name": "m5pm1_runtime_transition", "status": "PASS"},
            {"name": "rx8130_rtc_write_read", "status": "PASS"},
            {"name": "user_key", "status": "PASS"},
            {"name": "power_key", "status": "PASS"},
            {"name": "papercolor_peripheral_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/papercolor_peripherals",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "12",
        "inputs": ["key:a", "key:p", "key:a"],
        "qom": [],
        "qom_set_boot": [
            ("/machine/m5pm1", "vbat-mv", "4000"),
            ("/machine/m5pm1", "vin-mv", "5000"),
            ("/machine/m5pm1", "charging", "true"),
        ],
        "qom_steps": [
            (0.8, "/machine/m5pm1", "vbat-mv", "3400"),
            (1.5, "/machine/m5pm1", "vbat-mv", "4200"),
        ],
        "qom_sequence_settle": 5.0,
        "serial_expect": [
            "PAPERCOLOR_PERIPHERAL_MAIN",
            "PAPERCOLOR_POWER 87 4000 1",
            "PAPERCOLOR_POWER_STATE 3400 1",
            "PAPERCOLOR_POWER_STATE 4200 1",
            "PAPERCOLOR_POWER_DONE PASS",
            "PAPERCOLOR_RTC 2026-10-22 07:08:09",
            "PAPERCOLOR_KEY 1",
            "PAPERCOLOR_PWR 1",
        ],
        "post_input_wait": 5.0,
        "min_unique_colors": 1,
        "allow_static_frame": True,
    },
    {
        "id": "papercolor-sd",
        "expected_status": "PASS",
        "reason": (
            "The documented PaperColor SPI SD pins are used with "
            "machine.SDCard; a 512-byte block write/readback and raw image "
            "sector contents both match."
        ),
        "checks": [
            {"name": "sdspi_init", "status": "PASS"},
            {"name": "sdspi_write_block", "status": "PASS"},
            {"name": "sdspi_readback", "status": "PASS"},
            {"name": "sd_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/papercolor_sd",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "22",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "sd_image": True,
        "env": {
            "M5SW_SPI_SD_IMAGE": "{out_dir}/sd.img",
        },
        "disk": {
            "image": "{out_dir}/sd.img",
            "sector": 100,
        },
        "frame_color": {
            "x": 4, "y": 4, "label": "PaperColor SD", "dark": True,
        },
    },
    {
        "id": "papercolor-audio",
        "expected_status": "PASS",
        "reason": (
            "The official Speaker API drives ES8311/AW8737A through I2S TX "
            "and cyclic GDMA; host PCM capture contains the generated tone."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "i2s_gdma_capture", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/papercolor_audio",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "11",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {
            "x": 4, "y": 4, "label": "PaperColor audio", "dark": True,
        },
    },
    {
        "id": "papercolor-sht4x",
        "expected_status": "PASS",
        "reason": (
            "The onboard SHT4X sensor responds to the official hardware."
            "SHT4X API through I2C; temperature/humidity decoding and CRCs pass."
        ),
        "checks": [
            {"name": "sht4x_measure", "status": "PASS"},
            {"name": "sht4x_crc", "status": "PASS"},
            {"name": "sht4x_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/papercolor_sht4x",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {
            "x": 4, "y": 4, "label": "PaperColor SHT4X", "dark": True,
        },
    },
    {
        "id": "papercolor-mic",
        "expected_status": "PASS",
        "reason": (
            "The official Mic API records through ES7210, I2S RX and cyclic "
            "GDMA; deterministic host PCM injection reaches the buffer."
        ),
        "checks": [
            {"name": "es7210_configure", "status": "PASS"},
            {"name": "mic_record", "status": "PASS"},
            {"name": "i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/papercolor_mic",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "11",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {
            "x": 4, "y": 4, "label": "PaperColor mic", "dark": True,
        },
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
        "id": "stackchan-audio",
        "expected_status": "PASS",
        "reason": (
            "The official Speaker API drives AW88298 and I2S TX through "
            "cyclic GDMA; host PCM capture contains the generated tone."
        ),
        "checks": [
            {"name": "aw88298_configure", "status": "PASS"},
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "i2s_gdma_capture", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_audio",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "4",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "StackChan audio"},
    },
    {
        "id": "stackchan-mic",
        "expected_status": "PASS",
        "reason": (
            "The official Mic API records through ES7210, I2S RX and cyclic "
            "GDMA; host PCM injection reaches the UIFlow2 buffer."
        ),
        "checks": [
            {"name": "es7210_configure", "status": "PASS"},
            {"name": "mic_record", "status": "PASS"},
            {"name": "i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_mic",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "6",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {"x": 4, "y": 4, "label": "StackChan mic"},
    },
    {
        "id": "stackchan-peripherals",
        "expected_status": "PASS",
        "reason": (
            "BMI270 and BMM150 samples, AXP2101 power telemetry, display "
            "touch, AW9523 output/input registers, INA226 battery telemetry, "
            "LTR553 ambient light, the BM8563-compatible PCF8563 RTC and NEC "
            "IR TX/RX all pass through the StackChan board controllers."
        ),
        "checks": [
            {"name": "stackchan_imu", "status": "PASS"},
            {"name": "stackchan_magnetometer", "status": "PASS"},
            {"name": "stackchan_axp2101_power", "status": "PASS"},
            {"name": "stackchan_display_touch", "status": "PASS"},
            {"name": "stackchan_aw9523", "status": "PASS"},
            {"name": "stackchan_ina226", "status": "PASS"},
            {"name": "stackchan_ltr553_als", "status": "PASS"},
            {"name": "stackchan_rtc_bm8563", "status": "PASS"},
            {"name": "stackchan_ir_tx_rx", "status": "PASS"},
            {"name": "stackchan_peripheral_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_peripherals",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "3",
        "inputs": ["touch:160,120"],
        "post_input_wait": 8,
        "qom_set_boot": [
            ("/machine/aw9523", "input-bits", "61439"),
            ("/machine/ina226", "bus-voltage-mv", "4000"),
            ("/machine/ina226", "current-ma", "250"),
            ("/machine/ina226", "shunt-ohms", "0.08"),
            ("/machine/pcf8563", "unix-time", "1792630923"),
            ("/machine/ltr553", "light-level", "640"),
            ("/machine/ltr553", "proximity-level", "321"),
            ("/machine/axp2101", "vbat-mv", "4000"),
            ("/machine/axp2101", "vin-mv", "5000"),
            ("/machine/axp2101", "charging", "true"),
            ("/machine/bmm150", "mag-x", "30"),
            ("/machine/bmm150", "mag-y", "-20"),
            ("/machine/bmm150", "mag-z", "45"),
        ],
        "qom": [
            ("/machine/bmi270", "accel-x", "0.25"),
            ("/machine/bmi270", "accel-y", "-0.50"),
            ("/machine/bmi270", "accel-z", "0.75"),
            ("/machine/bmi270", "gyro-x", "10"),
            ("/machine/bmi270", "gyro-y", "-20"),
            ("/machine/bmi270", "gyro-z", "30"),
        ],
        "qom_settle": 0.5,
        "allow_static_frame": True,
        "env": {
            "M5SW_RMT_TX_FILE": "{out_dir}/ir.rmt",
            "M5SW_RMT_RX_FILE": "{out_dir}/nec-56-a3.rmt",
            "M5SW_RMT_TRACE": "1",
        },
        "rmt_nec_source": {
            "output": "{out_dir}/nec-56-a3.rmt",
            "address": 0x56,
            "command": 0xA3,
        },
        "rmt_nec": {
            "capture": "{out_dir}/ir.rmt",
            "address": 0x56,
            "command": 0xA3,
        },
        "serial_expect": [
            "STACKCHAN_IMU_TYPE 6",
            "STACKCHAN_IMU_ACCEL 0.25 -0.50 0.75",
            "STACKCHAN_IMU_GYRO 10.0 -20.0 30.0",
            "STACKCHAN_MAG 118.9 77.3 -356.8",
            "STACKCHAN_PMIC_POWER 87 4000 1",
            "STACKCHAN_TOUCH",
            "STACKCHAN_AW9523 1 0",
            "STACKCHAN_POWER 4.00 0.25 1.00",
            "STACKCHAN_ALS 640 321",
            "STACKCHAN_RTC 2026 10 22 6 7 8",
            "STACKCHAN_IR_RX 86 163",
            "STACKCHAN_CHECKS 1 1 1 1 1 1 1 1 1",
            "STACKCHAN_PERIPHERAL_DONE PASS",
        ],
        "frame_color": {
            "x": 4, "y": 4, "label": "StackChan peripherals",
        },
    },
    {
        "id": "stackchan-servo",
        "expected_status": "PASS",
        "reason": (
            "The official SCS servo driver uses UART1 to ping, enable torque "
            "and write/read back both StackChan servo positions through the "
            "SCSCL protocol model."
        ),
        "checks": [
            {"name": "servo_ping", "status": "PASS"},
            {"name": "servo_torque", "status": "PASS"},
            {"name": "servo_write", "status": "PASS"},
            {"name": "servo_readback", "status": "PASS"},
            {"name": "servo_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stackchan",
        "base": "platform/.cache/firmware/stackchan/uiflow2.bin",
        "files_dir": "tests/uiflow2/stackchan_servo",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "12",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "StackChan servo"},
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
        "id": "stopwatch-audio",
        "expected_status": "PASS",
        "reason": (
            "The official Speaker API drives ES8311/AW8737A through I2S TX "
            "and cyclic GDMA; host PCM capture contains the generated tone."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "i2s_gdma_capture", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stopwatch",
        "base": "platform/.cache/firmware/stopwatch/uiflow2.bin",
        "files_dir": "tests/uiflow2/stopwatch_audio",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "466x466",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "min_unique_colors": 1,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 233, "y": 5, "label": "StopWatch audio"},
    },
    {
        "id": "stopwatch-mic",
        "expected_status": "PASS",
        "reason": (
            "The official Mic API records through ES8311, I2S RX and cyclic "
            "GDMA; deterministic host PCM injection reaches the buffer."
        ),
        "checks": [
            {"name": "es8311_configure", "status": "PASS"},
            {"name": "mic_record", "status": "PASS"},
            {"name": "i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stopwatch",
        "base": "platform/.cache/firmware/stopwatch/uiflow2.bin",
        "files_dir": "tests/uiflow2/stopwatch_mic",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "466x466",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "min_unique_colors": 1,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {"x": 233, "y": 5, "label": "StopWatch mic"},
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
    {
        "id": "atoms3r-ir",
        "expected_status": "PASS",
        "reason": (
            "AtomS3R hardware.IR sends NEC through ESP32-S3 RMT0 and the "
            "captured symbols decode to address 0x56/command 0xA3."
        ),
        "checks": [{"name": "atoms3r_rmt_nec_tx", "status": "PASS"}],
        "machine": "m5atoms3r",
        "base": "platform/.cache/firmware/atoms3r/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_ir",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "128x128",
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
            "address": 86,
            "command": 163,
        },
    },
    {
        "id": "cardputer-adv-ir",
        "expected_status": "PASS",
        "reason": (
            "Cardputer-ADV hardware.IR sends NEC through ESP32-S3 RMT0 and "
            "the captured symbols decode to address 0x56/command 0xA3."
        ),
        "checks": [{"name": "cardputer_adv_rmt_nec_tx", "status": "PASS"}],
        "machine": "m5cardputeradv",
        "base": "platform/.cache/firmware/cardputer-adv/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_ir",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
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
            "address": 86,
            "command": 163,
        },
    },
    {
        "id": "papercolor-ir",
        "expected_status": "PASS",
        "reason": (
            "PaperColor hardware.IR sends NEC through ESP32-S3 RMT0 and the "
            "captured symbols decode to address 0x56/command 0xA3."
        ),
        "checks": [{"name": "papercolor_rmt_nec_tx", "status": "PASS"}],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/sticks3_ir",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_RMT_TX_FILE": "{out_dir}/ir.rmt",
            "M5SW_RMT_TRACE": "1",
        },
        "rmt_nec": {
            "capture": "{out_dir}/ir.rmt",
            "address": 86,
            "command": 163,
        },
    },
    {
        "id": "core2-peripherals",
        "expected_status": "PASS",
        "reason": (
            "Core2 FT6336-compatible touch, PCF8563-compatible RTC and the "
            "power key are exercised through the official UIFlow2 APIs."
        ),
        "checks": [
            {"name": "ft6336_touch", "status": "PASS"},
            {"name": "pcf8563_rtc_write_read", "status": "PASS"},
            {"name": "power_key", "status": "PASS"},
            {"name": "core2_peripheral_ui_marker", "status": "PASS"},
        ],
        "machine": "m5core2",
        "base": "platform/.cache/firmware/core2/uiflow2.bin",
        "files_dir": "tests/uiflow2/core2_peripherals",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "wait": "18",
        "inputs": ["longpress:220,190,1.5", "key:p"],
        "post_input_wait": 3.0,
        "pre_input_marker": "CORE2_PERIPHERAL_INPUT_READY",
        "post_input_marker": "CORE2_PERIPHERAL_DRAW_COMPLETE",
        "qom": [],
        "efuse_driver": "none",
        "memory": "0",
        "deterministic": True,
        "serial_expect": [
            "CORE2_PERIPHERAL_MAIN",
            "CORE2_RTC 2026-10-22 06:07:08",
            "CORE2_TOUCH",
            "CORE2_PWR",
        ],
        "post_frame_color": "310,230,00FF00",
        "frame_color": {"x": 310, "y": 230, "label": "Core2 peripherals"},
    },
    {
        "id": "core2-audio",
        "expected_status": "PASS",
        "reason": (
            "Core2 v1.1 Speaker drives ESP32 I2S1 and NS4168 through real "
            "IDF DMA descriptors, with AXP2101 ALDO3 enabled and host PCM "
            "containing the generated tone."
        ),
        "checks": [
            {"name": "speaker_tone", "status": "PASS"},
            {"name": "esp32_i2s_dma_capture", "status": "PASS"},
            {"name": "axp2101_ns4168_enable", "status": "PASS"},
            {"name": "speaker_ui_marker", "status": "PASS"},
        ],
        "machine": "m5core2",
        "base": "platform/.cache/firmware/core2/uiflow2.bin",
        "files_dir": "tests/uiflow2/core2_audio",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "wait": "10",
        "inputs": ["touch:160,183"],
        "qom": [],
        "allow_static_frame": True,
        "efuse_driver": "none",
        "memory": "0",
        "deterministic": True,
        "env": {
            "M5SW_I2S_PCM_FILE": "{out_dir}/speaker.pcm",
        },
        "qom_expect": [
            ("/machine/axp2101", "speaker-enabled", "true"),
        ],
        "pcm": {
            "capture": "{out_dir}/speaker.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "Core2 audio"},
    },
    {
        "id": "core2-mic",
        "expected_status": "PASS",
        "reason": (
            "Core2 v1.1 Mic uses ESP32 I2S0 PDM RX and the legacy I2S "
            "linked-list DMA engine; deterministic host PCM reaches the "
            "official UIFlow2 microphone buffer."
        ),
        "checks": [
            {"name": "mic_record", "status": "PASS"},
            {"name": "esp32_i2s_rx_pcm_injection", "status": "PASS"},
            {"name": "mic_ui_marker", "status": "PASS"},
        ],
        "machine": "m5core2",
        "base": "platform/.cache/firmware/core2/uiflow2.bin",
        "files_dir": "tests/uiflow2/core2_mic",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "wait": "10",
        "inputs": [],
        "qom": [],
        "allow_static_frame": True,
        "efuse_driver": "none",
        "memory": "0",
        "deterministic": True,
        "pcm_tone_source": {
            "output": "{out_dir}/microphone.pcm",
            "frequency": "440",
            "sample_rate": "16000",
            "seconds": "1",
            "amplitude": "12000",
        },
        "env": {
            "M5SW_I2S_RX_PCM_FILE": "{out_dir}/microphone.pcm",
        },
        "frame_color": {"x": 4, "y": 4, "label": "Core2 mic"},
    },
    {
        "id": "core2-power-monitor",
        "expected_status": "PASS",
        "reason": (
            "Core2 v1.1 INA3221 is read over ESP32 I2C0; QOM-injected "
            "physical channel values are converted through the documented "
            "INA3221 bus-voltage and shunt-voltage register encodings."
        ),
        "checks": [
            {"name": "ina3221_device_id", "status": "PASS"},
            {"name": "ina3221_bus_voltage", "status": "PASS"},
            {"name": "ina3221_shunt_voltage", "status": "PASS"},
            {"name": "ina3221_ui_marker", "status": "PASS"},
        ],
        "machine": "m5core2",
        "base": "platform/.cache/firmware/core2/uiflow2.bin",
        "files_dir": "tests/uiflow2/core2_power_monitor",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "wait": "8",
        "inputs": ["touch:160,183"],
        "qom_set_boot": [
            ("/machine/ina3221-40", "bus1-mv", "4800"),
            ("/machine/ina3221-40", "current1-ma", "240"),
        ],
        "allow_static_frame": True,
        "efuse_driver": "none",
        "memory": "0",
        "deterministic": True,
        "frame_color": {"x": 4, "y": 4, "label": "Core2 INA3221"},
    },
    {
        "id": "stamplc-can",
        "expected_status": "PASS",
        "reason": (
            "StamPLC CAN uses G42/G43 with the ESP32-S3 TWAI controller and a "
            "virtual CAN peer; the official UIFlow2 CAN API transmits and "
            "receives the same frame through the SJA1000-compatible path."
        ),
        "checks": [
            {"name": "twai_init", "status": "PASS"},
            {"name": "can_tx_rx", "status": "PASS"},
            {"name": "can_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stamplc",
        "base": "platform/.cache/firmware/stamplc/uiflow2.bin",
        "files_dir": "tests/uiflow2/stamplc_can",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_CAN_ECHO": "1",
        },
        "frame_color": {"x": 4, "y": 4, "label": "StamPLC CAN"},
    },
    {
        "id": "stamplc-rs485",
        "expected_status": "PASS",
        "reason": (
            "StamPLC PWR485 uses UART2 with G0/G39/G46 and the official "
            "half-duplex API; a byte-level peer verifies TX and RX through "
            "the UART controller."
        ),
        "checks": [
            {"name": "uart2_rs485_init", "status": "PASS"},
            {"name": "rs485_tx_rx", "status": "PASS"},
            {"name": "rs485_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stamplc",
        "base": "platform/.cache/firmware/stamplc/uiflow2.bin",
        "files_dir": "tests/uiflow2/stamplc_rs485",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_RS485_ECHO": "1",
        },
        "frame_color": {"x": 4, "y": 4, "label": "StamPLC RS485"},
    },
    {
        "id": "stamplc-buzzer",
        "expected_status": "PASS",
        "reason": (
            "StamPLC buzzer output is generated by the official Speaker path "
            "as a 1-bit delta-sigma I2S stream on G44; host capture verifies "
            "non-silent firmware output."
        ),
        "checks": [
            {"name": "speaker_buzzer_init", "status": "PASS"},
            {"name": "i2s_delta_sigma_capture", "status": "PASS"},
            {"name": "buzzer_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stamplc",
        "base": "platform/.cache/firmware/stamplc/uiflow2.bin",
        "files_dir": "tests/uiflow2/stamplc_buzzer",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "8",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": "{out_dir}/buzzer.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/buzzer.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "StamPLC buzzer"},
    },
    {
        "id": "core2-imu",
        "expected_status": "PASS",
        "reason": (
            "Core2 MPU6886 accel/gyro values are injected through QOM and read "
            "through the official UIFlow2 Imu API and ESP32 I2C0 path."
        ),
        "checks": [
            {"name": "mpu6886_identity", "status": "PASS"},
            {"name": "mpu6886_accel", "status": "PASS"},
            {"name": "mpu6886_gyro", "status": "PASS"},
            {"name": "imu_ui_marker", "status": "PASS"},
        ],
        "machine": "m5core2",
        "base": "platform/.cache/firmware/core2/uiflow2.bin",
        "files_dir": "tests/uiflow2/core2_imu",
        "pre_input_marker": "CORE2_IMU_SAMPLE_READY",
        "post_input_marker": "CORE2_IMU_DRAW_COMPLETE ok",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "wait": "13",
        "inputs": ["touch:160,183"],
        "qom": [
            ("/machine/mpu6886", "accel-x", "0.25"),
            ("/machine/mpu6886", "accel-y", "-0.50"),
            ("/machine/mpu6886", "accel-z", "0.75"),
            ("/machine/mpu6886", "gyro-x", "10"),
            ("/machine/mpu6886", "gyro-y", "-20"),
            ("/machine/mpu6886", "gyro-z", "30"),
        ],
        "allow_static_frame": True,
        "efuse_driver": "none",
        "memory": "0",
        "deterministic": True,
        "frame_color": {"x": 4, "y": 4, "label": "Core2 IMU"},
    },
    {
        "id": "core2-axp192",
        "expected_status": "PASS",
        "reason": (
            "Core2 UIFlow2 auto-detects the legacy AXP192 model and reads "
            "battery voltage, level, current and charging state through Power."
        ),
        "checks": [
            {"name": "core2_axp192_detect", "status": "PASS"},
            {"name": "core2_axp192_voltage", "status": "PASS"},
            {"name": "core2_axp192_current", "status": "PASS"},
            {"name": "core2_axp192_charging", "status": "PASS"},
            {"name": "core2_axp192_ui_marker", "status": "PASS"},
        ],
        "machine": "m5core2",
        "base": "platform/.cache/firmware/core2/uiflow2.bin",
        "files_dir": "tests/uiflow2/core2_axp192",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "wait": "13",
        "inputs": ["touch:160,183"],
        "qom": [
            ("/machine/axp192", "vbat-mv", "3900"),
            ("/machine/axp192", "vin-mv", "5000"),
            ("/machine/axp192", "battery-current-ma", "300"),
            ("/machine/axp192", "charging", "true"),
        ],
        "env": {
            "M5SW_CORE2_PMIC": "axp192",
        },
        "deterministic": True,
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "Core2 AXP192"},
    },
    {
        "id": "stamplc-lm75",
        "expected_status": "PASS",
        "reason": (
            "StamPLC LM75BDP is read over I2C0 G15/G13 at 0x48; QOM "
            "temperature injection is encoded in the chip-native register."
        ),
        "checks": [
            {"name": "lm75_i2c_read", "status": "PASS"},
            {"name": "lm75_temperature_encoding", "status": "PASS"},
            {"name": "lm75_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stamplc",
        "base": "platform/.cache/firmware/stamplc/uiflow2.bin",
        "files_dir": "tests/uiflow2/stamplc_lm75",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "8",
        "inputs": ["key:a"],
        "qom_set_boot": [
            ("/machine/lm75-48", "temperature-c", "37.5"),
        ],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "StamPLC LM75"},
    },
    {
        "id": "papercolor-rgb",
        "expected_status": "PASS",
        "reason": (
            "PaperColor M5.Led drives two GRB LEDs through ESP32-S3 RMT; "
            "captured RMT symbols decode to the expected red and green "
            "WS2812 wire bytes."
        ),
        "checks": [
            {"name": "rmt_led_init", "status": "PASS"},
            {"name": "ws2812_wire_decode", "status": "PASS"},
            {"name": "rgb_ui_marker", "status": "PASS"},
        ],
        "machine": "m5papercolor",
        "base": "platform/.cache/firmware/papercolor/uiflow2.bin",
        "files_dir": "tests/uiflow2/papercolor_rgb",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "400x600",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_RMT_TX_FILE": "{out_dir}/rgb.rmt",
            "M5SW_RMT_TRACE": "1",
        },
        "rmt_ws2812": {
            "capture": "{out_dir}/rgb.rmt",
            "leds": ["0,255,0", "255,0,0"],
        },
        "frame_color": {"x": 4, "y": 4, "label": "PaperColor RGB"},
    },
    {
        "id": "stamplc-onboard-io",
        "expected_status": "PASS",
        "reason": (
            "StamPLC AW9523B controls relay/input banks at 0x59 while "
            "PI4IOE5V6408 controls front-panel keys/RGB at 0x43; both are "
            "validated through their register paths."
        ),
        "checks": [
            {"name": "aw9523_relay_readback", "status": "PASS"},
            {"name": "aw9523_input_injection", "status": "PASS"},
            {"name": "pi4ioe_rgb_readback", "status": "PASS"},
            {"name": "onboard_io_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stamplc",
        "base": "platform/.cache/firmware/stamplc/uiflow2.bin",
        "files_dir": "tests/uiflow2/stamplc_onboard_io",
        "vfs_offset": "0x641000",
        "vfs_size": "0x1BE000",
        "flash_size": "0x800000",
        "expected_size": "240x135",
        "efuse_pkg_version": "0",
        "wait": "5",
        "inputs": ["key:a"],
        "qom": [
            ("/machine/aw9523-59", "input-bits", "61680"),
        ],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "StamPLC onboard IO"},
    },
    {
        "id": "cores3-aw9523-full",
        "expected_status": "PASS",
        "reason": (
            "The official AW9523 driver exercises output direction and "
            "readback plus a QOM-injected input on the CoreS3 system bus."
        ),
        "checks": [
            {"name": "aw9523_output_readback", "status": "PASS"},
            {"name": "aw9523_input_injection", "status": "PASS"},
            {"name": "aw9523_ui_marker", "status": "PASS"},
        ],
        "machine": "m5cores3",
        "base": "platform/.cache/firmware/cores3/uiflow2.bin",
        "files_dir": "tests/uiflow2/cores3_aw9523_full",
        "vfs_offset": "0xAA0000",
        "vfs_size": "0x4C0000",
        "flash_size": "0x1000000",
        "expected_size": "320x240",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["touch:160,183"],
        "qom": [
            ("/machine/aw9523", "input-bits", "61439"),
        ],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "CoreS3 AW9523"},
    },
    {
        "id": "stopwatch-m5ioe1-full",
        "expected_status": "PASS",
        "reason": (
            "The official M5IOE1 driver exercises GPIO, ADC and PWM registers "
            "on the StopWatch system bus, including QOM input injection."
        ),
        "checks": [
            {"name": "m5ioe1_gpio_output_readback", "status": "PASS"},
            {"name": "m5ioe1_input_injection", "status": "PASS"},
            {"name": "m5ioe1_adc_conversion", "status": "PASS"},
            {"name": "m5ioe1_pwm_readback", "status": "PASS"},
            {"name": "m5ioe1_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stopwatch",
        "base": "platform/.cache/firmware/stopwatch/uiflow2.bin",
        "files_dir": "tests/uiflow2/stopwatch_m5ioe1_full",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "466x466",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a"],
        "qom": [
            ("/machine/m5ioe1", "input-bits", "16382"),
            ("/machine/m5ioe1", "adc1-mv", "1650"),
        ],
        "allow_static_frame": True,
        "frame_color": {"x": 233, "y": 4, "label": "StopWatch M5IOE1"},
    },
    {
        "id": "stopwatch-m5pm1-full",
        "expected_status": "PASS",
        "reason": (
            "The official M5PM1 driver exercises power, GPIO, ADC, PWM, "
            "NeoPixel RAM, IRQ, wake, watchdog, timer and RTC RAM registers."
        ),
        "checks": [
            {"name": "m5pm1_device_info_uid", "status": "PASS"},
            {"name": "m5pm1_power_and_hold", "status": "PASS"},
            {"name": "m5pm1_gpio_input_irq", "status": "PASS"},
            {"name": "m5pm1_adc_and_temperature", "status": "PASS"},
            {"name": "m5pm1_pwm", "status": "PASS"},
            {"name": "m5pm1_neopixel_ram", "status": "PASS"},
            {"name": "m5pm1_wake_watchdog_timer_rtc", "status": "PASS"},
            {"name": "m5pm1_button_irq", "status": "PASS"},
            {"name": "m5pm1_ui_marker", "status": "PASS"},
        ],
        "machine": "m5stopwatch",
        "base": "platform/.cache/firmware/stopwatch/uiflow2.bin",
        "files_dir": "tests/uiflow2/stopwatch_m5pm1_full",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "466x466",
        "efuse_pkg_version": "0",
        "wait": "10",
        "inputs": ["key:a", "key:p"],
        "qom": [
            ("/machine/m5pm1", "gpio-input-bits", "29"),
            ("/machine/m5pm1", "adc1-mv", "1650"),
            ("/machine/m5pm1", "adc2-mv", "1200"),
            ("/machine/m5pm1", "temperature-c", "30"),
            ("/machine/m5pm1", "wake-source", "4"),
        ],
        "allow_static_frame": True,
        "frame_color": {"x": 233, "y": 4, "label": "StopWatch M5PM1"},
    },
    {
        "id": "nesso-peripherals",
        "expected_status": "PASS",
        "reason": (
            "Both PI4IOE expanders, a button input, the BQ27220 battery "
            "gauge and AW32001 charger status are visible through the Nesso "
            "UIFlow2 firmware."
        ),
        "checks": [
            {"name": "nesso_pi4ioe_e0", "status": "PASS"},
            {"name": "nesso_pi4ioe_e1", "status": "PASS"},
            {"name": "nesso_button_input", "status": "PASS"},
            {"name": "nesso_battery_voltage", "status": "PASS"},
            {"name": "nesso_charging_status", "status": "PASS"},
            {"name": "bq27220_runtime_transition", "status": "PASS"},
            {"name": "aw32001_runtime_transition", "status": "PASS"},
            {"name": "nesso_ui_marker", "status": "PASS"},
        ],
        "machine": "esp32c6",
        "backend": "qemu-esp32c6",
        "base": "platform/.cache/firmware/nesso-n1/uiflow2.bin",
        "files_dir": "tests/uiflow2/nesso_peripherals",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "135x240",
        "wait": "15",
        "inputs": ["touch:67,160", "key:a"],
        "qom": [
            ("/machine/nesso-bq27220", "battery-mv", "4000"),
            ("/machine/nesso-bq27220", "current-ma", "250"),
            ("/machine/nesso-bq27220", "battery-level", "87"),
            ("/machine/nesso-aw32001", "charging", "true"),
        ],
        "qom_steps": [
            (0.8, "/machine/nesso-bq27220", "battery-level", "64"),
            (0, "/machine/nesso-bq27220", "battery-mv", "3300"),
            (0, "/machine/nesso-aw32001", "charging", "false"),
            (1.5, "/machine/nesso-bq27220", "battery-level", "96"),
            (0, "/machine/nesso-bq27220", "battery-mv", "4300"),
            (0, "/machine/nesso-aw32001", "charging", "true"),
        ],
        "qom_sequence_settle": 2.0,
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "Nesso peripherals"},
    },
    {
        "id": "nesso-imu",
        "expected_status": "PASS",
        "reason": (
            "The Nesso N1 BMI270 at I2C 0x68 is initialized by M5Unified; "
            "QOM values are encoded in the chip sample registers and read "
            "through the official Imu API."
        ),
        "checks": [
            {"name": "nesso_bmi270_init", "status": "PASS"},
            {"name": "nesso_bmi270_accel", "status": "PASS"},
            {"name": "nesso_bmi270_gyro", "status": "PASS"},
            {"name": "nesso_imu_ui_marker", "status": "PASS"},
        ],
        "machine": "esp32c6",
        "backend": "qemu-esp32c6",
        "base": "platform/.cache/firmware/nesso-n1/uiflow2.bin",
        "files_dir": "tests/uiflow2/nesso_imu",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "135x240",
        "wait": "15",
        "inputs": ["touch:67,160"],
        "qom": [
            ("/machine/nesso-bmi270", "accel-x", "0.25"),
            ("/machine/nesso-bmi270", "accel-y", "-0.50"),
            ("/machine/nesso-bmi270", "accel-z", "0.75"),
            ("/machine/nesso-bmi270", "gyro-x", "10"),
            ("/machine/nesso-bmi270", "gyro-y", "-20"),
            ("/machine/nesso-bmi270", "gyro-z", "30"),
        ],
        "allow_static_frame": True,
        "frame_color": {"x": 4, "y": 4, "label": "Nesso BMI270"},
    },
    {
        "id": "nesso-ir",
        "expected_status": "PASS",
        "reason": (
            "Nesso N1 hardware.IR sends NEC through ESP32-C6 RMT0 GPIO9 and "
            "the captured symbols decode to address 0x56/command 0xA3."
        ),
        "checks": [
            {"name": "nesso_c6_rmt_nec_tx", "status": "PASS"},
            {"name": "nesso_ir_ui_marker", "status": "PASS"},
        ],
        "machine": "esp32c6",
        "backend": "qemu-esp32c6",
        "base": "platform/.cache/firmware/nesso-n1/uiflow2.bin",
        "files_dir": "tests/uiflow2/nesso_ir",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "135x240",
        "wait": "15",
        "inputs": ["touch:67,160"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_RMT_TX_FILE": "{out_dir}/ir.rmt",
            "M5SW_RMT_TRACE": "1",
        },
        "rmt_nec": {
            "capture": "{out_dir}/ir.rmt",
            "address": 86,
            "command": 163,
        },
        "frame_color": {"x": 4, "y": 4, "label": "Nesso IR"},
    },
    {
        "id": "nesso-lora",
        "expected_status": "PASS",
        "reason": (
            "The Nesso SX1262 shares ESP32-C6 SPI2 with the display; the "
            "hardware.LoRa driver configures the modem and receives the "
            "packet sent through the chip packet FIFO."
        ),
        "checks": [
            {"name": "nesso_pi4ioe_radio_rails", "status": "PASS"},
            {"name": "sx1262_spi2_configure", "status": "PASS"},
            {"name": "sx1262_tx_rx_loopback", "status": "PASS"},
            {"name": "nesso_lora_ui_marker", "status": "PASS"},
        ],
        "machine": "esp32c6",
        "backend": "qemu-esp32c6",
        "base": "platform/.cache/firmware/nesso-n1/uiflow2.bin",
        "files_dir": "tests/uiflow2/nesso_lora",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "135x240",
        "wait": "15",
        "inputs": ["touch:67,160"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_SX1262_TRACE": "1",
        },
        "frame_color": {"x": 4, "y": 4, "label": "Nesso SX1262"},
    },
    {
        "id": "nesso-buzzer",
        "expected_status": "PASS",
        "reason": (
            "The Nesso N1 GPIO11 buzzer is driven through the official "
            "Speaker API, ESP32-C6 I2S TX and cyclic AHB GDMA OUT "
            "descriptors; host PCM contains the firmware-generated "
            "1-bit delta-sigma tone."
        ),
        "checks": [
            {"name": "speaker_begin", "status": "PASS"},
            {"name": "speaker_is_playing", "status": "PASS"},
            {"name": "c6_i2s_gdma_out_eof", "status": "PASS"},
            {"name": "c6_buzzer_pcm_capture", "status": "PASS"},
            {"name": "nesso_buzzer_ui_marker", "status": "PASS"},
        ],
        "machine": "esp32c6",
        "backend": "qemu-esp32c6",
        "base": "platform/.cache/firmware/nesso-n1/uiflow2.bin",
        "files_dir": "tests/uiflow2/nesso_buzzer",
        "vfs_offset": "0x820000",
        "vfs_size": "0x7DF000",
        "flash_size": "0x1000000",
        "expected_size": "135x240",
        "wait": "10",
        "inputs": ["touch:67,160"],
        "qom": [],
        "allow_static_frame": True,
        "env": {
            "M5SW_I2S_PCM_FILE": "{out_dir}/buzzer.pcm",
        },
        "pcm": {
            "capture": "{out_dir}/buzzer.pcm",
            "min_nonzero": 1000,
            "min_peak_to_peak": 1000,
        },
        "frame_color": {"x": 4, "y": 4, "label": "Nesso buzzer"},
    },
]


def reference_layout(case: dict) -> dict:
    """Resolve the refreshed reference's VFS before composing a probe image."""
    tools_path = str(ROOT / "platform/tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    from firmware_analysis import parse_partition_table

    raw = (ROOT / case["base"]).read_bytes()
    flash_size = int(case["flash_size"], 0)
    table = parse_partition_table(raw, image_size=flash_size)
    if len(raw) > flash_size or not table["valid"]:
        raise ValueError(f"{case['id']}: invalid reference partition table")
    candidates = [part for part in table["partitions"] if (
        part["label"] == "vfs" and part["type"] == 1 and part["subtype"] == 0x81
    )]
    if len(candidates) != 1:
        raise ValueError(f"{case['id']}: expected exactly one LittleFS vfs partition")
    vfs = candidates[0]
    start, end = vfs["offset"], vfs["offset"] + vfs["size"]
    if not vfs["size"] or start % 4096 or vfs["size"] % 4096 or any(
        part is not vfs and start < part["offset"] + part["size"] and part["offset"] < end
        for part in table["partitions"]
    ):
        raise ValueError(f"{case['id']}: overlapping or unaligned vfs partition")
    return {
        "source": "reference-partition-table",
        "base_firmware_sha256": hashlib.sha256(raw).hexdigest(),
        "declared": {"offset": int(case["vfs_offset"], 0), "size": int(case["vfs_size"], 0)},
        "effective": {"offset": start, "size": vfs["size"]},
    }


def command_for(case: dict, out_dir: Path,
                sd_image: Path | None = None, *, reference: dict | None = None) -> list[str]:
    backend = case.get("backend", "qemu-esp32s3")
    qemu = QEMU_C6 if backend == "qemu-esp32c6" else QEMU
    rom_dir = ROM_DIR_C6 if backend == "qemu-esp32c6" else ROM_DIR
    efuse_driver = case.get(
        "efuse_driver",
        "none" if backend == "qemu-esp32c6" else "nvram.esp32s3.efuse",
    )
    command = [
        sys.executable,
        str(RUNNER),
        "--base", str(ROOT / case["base"]),
        "--machine", case["machine"],
        "--files-dir", str(ROOT / case["files_dir"]),
        "--vfs-offset", hex(reference["effective"]["offset"]) if reference else case["vfs_offset"],
        "--vfs-size", hex(reference["effective"]["size"]) if reference else case["vfs_size"],
        "--flash-size", case["flash_size"],
        "--expected-size", case["expected_size"],
        "--wait", case["wait"],
        "--post-input-wait", str(case.get("post_input_wait", 1)),
        "--efuse-driver", efuse_driver,
        "--qemu", str(qemu),
        "--rom-dir", str(rom_dir),
        "--out-dir", str(out_dir),
    ]
    if "efuse_pkg_version" in case:
        command.extend(["--efuse-pkg-version", case["efuse_pkg_version"]])
    if "memory" in case:
        command.extend(["--memory", case["memory"]])
    for name in ("pre_input_marker", "post_input_marker"):
        if case.get(name):
            command.extend(["--" + name.replace("_", "-"), case[name]])
    if case.get("deterministic"):
        command.append("--deterministic")
    for input_spec in case["inputs"]:
        command.extend(["--input", input_spec])
    for path, prop, value in case.get("qom", []):
        command.extend(["--qom-set", path, prop, value])
    for path, prop, value in case.get("qom_set_boot", []):
        command.extend(["--qom-set-boot", path, prop, value])
    for step in case.get("qom_steps", []):
        command.extend([
            "--qom-step", *(str(value) for value in step),
        ])
    for path, prop, value in case.get("qom_expect", []):
        command.extend(["--qom-expect", path, prop, value])
    for marker in case.get("serial_expect", []):
        command.extend(["--serial-expect", marker])
    for marker in case.get("serial1_expect", []):
        command.extend(["--serial1-expect", marker])
    if case.get("qom_settle"):
        command.extend(["--qom-settle", str(case["qom_settle"])])
    if case.get("qom_sequence_settle"):
        command.extend([
            "--qom-sequence-settle", str(case["qom_sequence_settle"]),
        ])
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
    parser.add_argument(
        "--device",
        action="append",
        default=[],
        help="run the runtime case group for a device; repeat as needed",
    )
    parser.add_argument(
        "--list-json",
        action="store_true",
        help="print the selected cases as JSON without executing them",
    )
    parser.add_argument(
        "--allow-retries",
        action="store_true",
        help=(
            "allow cases that explicitly configure retries; disabled by "
            "default so a retry success cannot be reported as a clean PASS"
        ),
    )
    args = parser.parse_args()
    filter_requested = bool(args.case or args.device)
    selected = set(args.case)
    if args.device:
        groups = json.loads(COVERAGE.read_text()).get(
            "device_case_groups", {}
        )
        for device_id in args.device:
            group = groups.get(device_id)
            if group is None:
                raise SystemExit(f"unknown device runtime group: {device_id}")
            selected.update(group.get("matrix", []))
    if args.case or args.device:
        unknown = selected - {case["id"] for case in CASES}
        if unknown:
            raise SystemExit(
                "unknown matrix cases: " + ", ".join(sorted(unknown))
            )
    if args.list_json:
        payload = [
            {
                "id": case["id"],
                "machine": case["machine"],
                "files_dir": case.get("files_dir"),
            }
            for case in CASES
            if not filter_requested or case["id"] in selected
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if filter_requested and not selected:
        raise SystemExit(
            "selected device has no matrix cases; run its external probes "
            "from runtime_cases"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(os.environ.get("M5_PYTHON_DEPS") or ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )

    results = {}
    for case in CASES:
        if filter_requested and case["id"] not in selected:
            continue
        if int(case.get("retries", 0)) and not args.allow_retries:
            raise SystemExit(
                f"{case['id']}: retries are configured; remove them for "
                "clean regression evidence or pass --allow-retries for "
                "diagnostic-only runs"
            )
        if not any(case.get(key) for key in (
            "serial_expect", "serial1_expect", "qom_expect", "pcm",
            "rmt_nec", "rmt_ws2812", "disk", "frame_color",
        )):
            raise SystemExit(
                f"{case['id']}: no runtime evidence source configured"
            )
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
        pcm_tone_source = case.get("pcm_tone_source")
        if pcm_tone_source:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/make_pcm_tone.py"),
                    str(pcm_tone_source["output"]).format(out_dir=case_out),
                    "--frequency", pcm_tone_source["frequency"],
                    "--sample-rate", pcm_tone_source["sample_rate"],
                    "--seconds", pcm_tone_source["seconds"],
                    "--amplitude", pcm_tone_source["amplitude"],
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        reference = reference_layout(case)
        command = command_for(case, case_out, sd_image, reference=reference)
        case_env = env.copy()
        for key, value in case.get("env", {}).items():
            case_env[key] = value.format(out_dir=case_out)
        stdout_path = args.out_dir / f"{case['id']}.stdout"
        stderr_path = args.out_dir / f"{case['id']}.stderr"
        attempts_run = 0
        for attempt in range(case.get("retries", 0) + 1):
            attempts_run = attempt + 1
            mode = "wb" if attempt == 0 else "ab"
            with stdout_path.open(mode) as stdout, \
                    stderr_path.open(mode) as stderr:
                if attempt:
                    stdout.write(
                        f"\n--- retry {attempt} ---\n".encode()
                    )
                    stderr.write(
                        f"\n--- retry {attempt} ---\n".encode()
                    )
                    stdout.flush()
                    stderr.flush()
                process = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=case_env,
                    stdout=stdout,
                    stderr=stderr,
                    check=False,
                )
            if process.returncode == 0:
                serial_path = case_out / "serial.log"
                serial_text = stdout_path.read_text(errors="replace")
                if serial_path.exists():
                    serial_text += "\n" + serial_path.read_text(errors="replace")
                forbidden = DEFAULT_SERIAL_FAILURES + tuple(
                    case.get("serial_forbid", ())
                )
                found = [marker for marker in forbidden if marker in serial_text]
                if found:
                    if serial_path.exists():
                        shutil.copyfile(
                            serial_path,
                            case_out / f"serial.attempt-{attempt + 1}.log",
                        )
                    continue
            if process.returncode == 0:
                break
        validation_output = ""
        validation_ok = True
        if process.returncode == 0 and case.get("serial_expect"):
            validation_output += (
                "PASS serial markers: "
                + ", ".join(case["serial_expect"]) + "\n"
            )
        if process.returncode == 0 and case.get("serial1_expect"):
            validation_output += (
                "PASS UART1 markers: "
                + ", ".join(case["serial1_expect"]) + "\n"
            )
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
        pcm = case.get("pcm")
        if pcm and process.returncode == 0:
            validation = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/check_pcm.py"),
                    str(pcm["capture"]).format(out_dir=case_out),
                    "--min-nonzero", str(pcm.get("min_nonzero", 1000)),
                    "--min-peak-to-peak",
                    str(pcm.get("min_peak_to_peak", 1000)),
                ],
                cwd=ROOT,
                env=case_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            validation_output += validation.stdout
            validation_ok = validation_ok and validation.returncode == 0
        rmt_ws2812 = case.get("rmt_ws2812")
        if rmt_ws2812 and process.returncode == 0:
            validation_command = [
                sys.executable,
                str(ROOT / "tests/uiflow2/check_rmt_ws2812.py"),
                str(rmt_ws2812["capture"]).format(out_dir=case_out),
            ]
            for led in rmt_ws2812["leds"]:
                validation_command.extend(["--led", led])
            validation = subprocess.run(
                validation_command,
                cwd=ROOT,
                env=case_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            validation_output += validation.stdout
            validation_ok = validation_ok and validation.returncode == 0
        disk = case.get("disk")
        if disk and process.returncode == 0:
            validation = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/check_disk_sector.py"),
                    str(disk["image"]).format(out_dir=case_out),
                    "--sector", str(disk["sector"]),
                ],
                cwd=ROOT,
                env=case_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            validation_output += validation.stdout
            validation_ok = validation_ok and validation.returncode == 0
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
        serial_text = stdout_path.read_text(errors="replace")
        if process.returncode == 0:
            serial_path = case_out / "serial.log"
            if serial_path.exists():
                serial_text += "\n" + serial_path.read_text(errors="replace")
            forbidden = DEFAULT_SERIAL_FAILURES + tuple(
                case.get("serial_forbid", ())
            )
            found = [marker for marker in forbidden if marker in serial_text]
            if found:
                validation_output += (
                    "forbidden serial text: " + ", ".join(found) + "\n"
                )
                executed = False

        evidence = []
        if case.get("serial_expect"):
            evidence.append("serial.log")
        if case.get("serial1_expect"):
            evidence.append("serial1.log")
        if case.get("qom_expect") or case.get("qom_steps"):
            evidence.append("qom")
        if case.get("pcm"):
            evidence.append("pcm")
        if case.get("rmt_nec"):
            evidence.append("rmt-nec")
        if case.get("rmt_ws2812"):
            evidence.append("rmt-ws2812")
        if case.get("disk"):
            evidence.append("disk")
        if case.get("frame_color"):
            evidence.append("frame-marker")

        status = case["expected_status"] if executed else "FAIL"
        checks = [
            {
                **check,
                "status": status,
                "evidence": evidence,
            }
            for check in case["checks"]
        ]
        results[case["id"]] = {
            "status": status,
            "reference_layout": reference,
            "exit_code": process.returncode,
            "command": command,
            "output": str(case_out),
            "before": str(case_out / "before.png"),
            "after": str(case_out / "after.png"),
            "attempts": attempts_run,
            "retry_used": attempts_run > 1,
            "checks": checks,
            "evidence_sources": evidence,
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
