#!/usr/bin/env python3
"""Validate peripheral coverage for current and future device profiles."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERIPHERALS = ROOT / "platform/peripherals/catalog.json"
DEVICES = ROOT / "devices/catalog.json"
PROFILES = ROOT / "platform/qemu/profiles.json"

SENSOR_CAPABILITIES = {
    "imu": ("accel", "gyro"),
    "magnetometer": ("magnetometer",),
    "camera": ("camera",),
    "microphone": ("microphone",),
    "speaker": ("speaker",),
    "ir": ("ir",),
    "rgb-led": ("rgb-led",),
    "rtc": ("rtc",),
    "audio": ("audio-codec",),
    "vibration": ("vibration",),
    "battery": ("battery",),
    "temperature": ("temperature",),
    "power-monitor": ("power-monitor",),
    "buzzer": ("buzzer",),
    "can": ("can",),
    "rs485": ("rs485",),
    "digital-input": ("digital-input",),
    "relay-output": ("relay-output",),
    "servo": ("servo",),
    "nfc": ("nfc",),
    "lora": ("lora",),
    "subghz": ("subghz",),
    "usb-host": ("usb-host",),
    "sht40": ("temperature", "humidity"),
}

CONTROL_CAPABILITIES = {
    "button": ("button",),
    "touch": ("touch",),
    "keyboard": ("keyboard",),
    "servo": ("servo",),
}

HIGH_BANDWIDTH_CAPABILITIES = {
    "camera",
    "microphone",
    "speaker",
    "ir",
    "can",
    "lora",
    "subghz",
    "usb-host",
    "sd",
}


def sensor_capabilities(value: str) -> tuple[str, ...]:
    category = value.split(":", 1)[0]
    return SENSOR_CAPABILITIES.get(category, (category,))


def control_capabilities(control: dict) -> tuple[str, ...]:
    kind = control.get("type", "")
    if kind == "button" and control.get("id") == "power":
        return ("power-key",)
    return CONTROL_CAPABILITIES.get(kind, (kind,))


def validate() -> tuple[list[str], dict]:
    peripheral = json.loads(PERIPHERALS.read_text())
    devices = json.loads(DEVICES.read_text())["devices"]
    profiles = json.loads(PROFILES.read_text())["devices"]
    models = peripheral["models"]
    manifest_devices = peripheral["devices"]
    errors: list[str] = []

    device_ids = {device["id"] for device in devices}
    profile_ids = {device["id"] for device in profiles}
    if device_ids != set(manifest_devices):
        errors.append(
            "peripheral manifest device mismatch: "
            f"missing={sorted(device_ids - set(manifest_devices))}, "
            f"extra={sorted(set(manifest_devices) - device_ids)}"
        )
    if device_ids != profile_ids:
        errors.append(
            "profile/device catalog mismatch: "
            f"missing={sorted(device_ids - profile_ids)}, "
            f"extra={sorted(profile_ids - device_ids)}"
        )

    status_counts = Counter(model["status"] for model in models.values())
    device_status_counts = Counter()
    for device in devices:
        device_id = device["id"]
        entry = manifest_devices.get(device_id, {})
        components = entry.get("components", [])
        device_status_counts[entry.get("status", "partial")] += 1
        if (device.get("runtime", {}).get("status") != "backend-required"
                and not entry.get("evidence")):
            errors.append(f"{device_id}: no official hardware evidence")
        if not components:
            if device.get("runtime", {}).get("status") != "backend-required":
                errors.append(f"{device_id}: no peripheral components")
            continue

        available = set()
        for component in components:
            model_id = component.get("model")
            model = models.get(model_id)
            if model is None:
                errors.append(f"{device_id}: unknown model {model_id}")
                continue
            available.update(model["capabilities"])
            high_bandwidth = HIGH_BANDWIDTH_CAPABILITIES.intersection(
                model["capabilities"]
            )
            if model["status"] == "simulated" and high_bandwidth and not model.get(
                "data_plane"
            ):
                errors.append(
                    f"{device_id}: simulated high-bandwidth model {model_id} "
                    "has no data-plane contract"
                )

        required = set()
        for sensor in device.get("hardware", {}).get("sensors", []):
            required.update(sensor_capabilities(sensor))
        for control in device.get("hardware", {}).get("controls", []):
            required.update(control_capabilities(control))
        missing = sorted(required - available)
        if missing:
            errors.append(f"{device_id}: missing capabilities {missing}")

    report = {
        "models": len(models),
        "model_status": dict(sorted(status_counts.items())),
        "devices": len(manifest_devices),
        "device_status": dict(sorted(device_status_counts.items())),
        "errors": errors,
    }
    return errors, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors, report = validate()
    if args.json or not args.check:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.check:
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            raise SystemExit(1)
        print("PERIPHERAL_CATALOG_OK")


if __name__ == "__main__":
    main()
