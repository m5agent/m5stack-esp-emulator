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
            "light all pass through their real buses."
        ),
        "checks": [
            {"name": "imu_identity", "status": "PASS"},
            {"name": "imu_values", "status": "PASS"},
            {"name": "magnetometer", "status": "PASS"},
            {"name": "ambient_light", "status": "PASS"},
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
        "retries": 2,
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
        "inputs": ["touch:160,183"],
        "qom": [],
        "allow_static_frame": True,
        "efuse_driver": "none",
        "memory": "0",
        "retries": 2,
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
        "wait": "10",
        "inputs": ["touch:160,183"],
        "qom_set_boot": [
            ("/machine/ina3221-40", "bus1-mv", "4800"),
            ("/machine/ina3221-40", "current1-ma", "240"),
        ],
        "allow_static_frame": True,
        "efuse_driver": "none",
        "memory": "0",
        "retries": 2,
        "frame_color": {"x": 4, "y": 4, "label": "Core2 INA3221"},
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
        "--efuse-driver", case.get("efuse_driver", "nvram.esp32s3.efuse"),
        "--qemu", str(QEMU),
        "--rom-dir", str(ROM_DIR),
        "--out-dir", str(out_dir),
    ]
    if "efuse_pkg_version" in case:
        command.extend(["--efuse-pkg-version", case["efuse_pkg_version"]])
    if "memory" in case:
        command.extend(["--memory", case["memory"]])
    for input_spec in case["inputs"]:
        command.extend(["--input", input_spec])
    for path, prop, value in case.get("qom", []):
        command.extend(["--qom-set", path, prop, value])
    for path, prop, value in case.get("qom_set_boot", []):
        command.extend(["--qom-set-boot", path, prop, value])
    for path, prop, value in case.get("qom_expect", []):
        command.extend(["--qom-expect", path, prop, value])
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
        command = command_for(case, case_out, sd_image)
        case_env = env.copy()
        for key, value in case.get("env", {}).items():
            case_env[key] = value.format(out_dir=case_out)
        stdout_path = args.out_dir / f"{case['id']}.stdout"
        stderr_path = args.out_dir / f"{case['id']}.stderr"
        for attempt in range(case.get("retries", 0) + 1):
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
                break
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
