#!/usr/bin/env python3
"""Validate peripheral coverage for current and future device profiles."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERIPHERALS = ROOT / "platform/peripherals/catalog.json"
DEVICES = ROOT / "devices/catalog.source.json"
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
    "charger": ("charging",),
    "io-expander": ("io-expander",),
    "temperature": ("temperature",),
    "power-monitor": ("power-monitor",),
    "light-proximity": ("ambient-light", "proximity"),
    "buzzer": ("buzzer",),
    "can": ("can",),
    "rs485": ("rs485",),
    "digital-input": ("digital-input",),
    "relay-output": ("relay-output",),
    "servo": ("servo",),
    "nfc": ("nfc",),
    "lora": ("lora",),
    "subghz": ("subghz",),
    "wireless": ("wifi", "ble"),
    "usb-host": ("usb-host",),
    "storage": ("sd",),
    "sht40": ("temperature", "humidity"),
    "temperature-humidity": ("temperature", "humidity"),
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
    "audio-codec",
    "ethernet",
    "rs485",
}

COMPONENT_STATUS_VALUES = {"simulated", "partial", "planned", "not-applicable"}
DISPLAY_ONLY_CAPABILITIES = {
    "display-output",
    "framebuffer-capture",
    "input-event",
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
    completion_policy = peripheral.get("completion_policy", {})
    if not isinstance(completion_policy, dict):
        errors.append("completion_policy must be an object")
        completion_policy = {}
    allowlist = completion_policy.get("incomplete_device_allowlist", {})
    if not isinstance(allowlist, dict):
        errors.append("incomplete_device_allowlist must be an object")
        allowlist = {}

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
    tested_model_counts = Counter()
    requirements_total = 0
    requirements_covered = 0
    completed_device_ids: set[str] = set()

    for model_id, model in models.items():
        status = model.get("status")
        injection = model.get("injection")
        if status not in COMPONENT_STATUS_VALUES:
            errors.append(f"model {model_id}: invalid status {status!r}")
        if not isinstance(injection, list) or not injection:
            errors.append(f"model {model_id}: no injection/data source")
        if status == "simulated":
            if not model.get("data_plane"):
                errors.append(
                    f"model {model_id}: simulated model has no data-plane contract"
                )
            tested_devices = model.get("tested_devices", [])
            if not tested_devices:
                errors.append(
                    f"model {model_id}: simulated model has no tested_devices"
                )
            for device_id in tested_devices:
                entry = manifest_devices.get(device_id, {})
                models_for_device = {
                    component.get("model")
                    for component in entry.get("components", [])
                }
                if model_id not in models_for_device:
                    errors.append(
                        f"model {model_id}: tested device {device_id} does not "
                        "reference this model"
                    )
            if tested_devices:
                tested_model_counts["simulated"] += 1
        elif status in {"partial", "planned"} and not model.get("blocker"):
            errors.append(
                f"model {model_id}: {status} model has no concrete blocker"
            )

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
        blocked_models = set()
        simulated_components = False
        for component in components:
            model_id = component.get("model")
            model = models.get(model_id)
            if model is None:
                errors.append(f"{device_id}: unknown model {model_id}")
                continue
            if (
                model["interface"].startswith("i2c")
                and not (component.get("address") or model.get("address"))
            ):
                errors.append(
                    f"{device_id}/{component.get('id')}: I2C model {model_id} "
                    "has no address at model or component level"
                )
            component_status = component.get("status", model["status"])
            if component_status not in COMPONENT_STATUS_VALUES:
                errors.append(
                    f"{device_id}/{component.get('id')}: invalid component "
                    f"status {component_status!r}"
                )
            if model["status"] == "not-applicable" and component_status == "simulated":
                errors.append(
                    f"{device_id}/{component.get('id')}: not-applicable model "
                    f"{model_id} cannot be marked simulated"
                )
            if component_status != "simulated" or model["status"] != "simulated":
                blocked_models.add(model_id)
            else:
                simulated_components = True
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

        declared_blockers = entry.get("peripheral_blockers", [])
        blocker_models = [row.get("model") for row in declared_blockers]
        if len(blocker_models) != len(set(blocker_models)):
            errors.append(f"{device_id}: duplicate peripheral blocker models")
        if set(blocker_models) != blocked_models:
            errors.append(
                f"{device_id}: peripheral blocker mismatch: "
                f"missing={sorted(blocked_models - set(blocker_models))}, "
                f"extra={sorted(set(blocker_models) - blocked_models)}"
            )
        for blocker in declared_blockers:
            if not blocker.get("reason"):
                errors.append(
                    f"{device_id}: blocker for {blocker.get('model')} "
                    "has no reason"
                )
        expected_peripheral_status = (
            "simulated" if not blocked_models
            else "planned"
            if entry.get("status") == "not-applicable" and not simulated_components
            else "partial"
        )
        peripheral_status = entry.get(
            "peripheral_status", "simulated" if not blocked_models else None
        )
        if peripheral_status != expected_peripheral_status:
            errors.append(
                f"{device_id}: peripheral_status={peripheral_status!r}, "
                f"expected {expected_peripheral_status!r}"
            )
        if not blocked_models:
            completed_device_ids.add(device_id)

        required = set()
        for sensor in device.get("hardware", {}).get("sensors", []):
            required.update(sensor_capabilities(sensor))
        for control in device.get("hardware", {}).get("controls", []):
            required.update(control_capabilities(control))
        missing = sorted(required - available)
        requirements_total += len(required)
        requirements_covered += len(required & available)
        if missing:
            errors.append(f"{device_id}: missing capabilities {missing}")
        for component in components:
            model = models.get(component.get("model"))
            if model is None:
                continue
            capabilities = set(model.get("capabilities", []))
            if (
                capabilities
                and not capabilities.intersection(required)
                and not capabilities <= DISPLAY_ONLY_CAPABILITIES
            ):
                errors.append(
                    f"{device_id}/{component.get('id')}: component "
                    f"{component.get('model')} is not represented by the "
                    "device hardware inventory"
                )

    for device_id, entry in allowlist.items():
        if device_id not in manifest_devices:
            errors.append(
                f"incomplete-device allowlist references unknown device "
                f"{device_id!r}"
            )
            continue
        if not isinstance(entry, dict):
            errors.append(
                f"incomplete-device allowlist {device_id}: entry must be object"
            )
            continue
        if not entry.get("reason"):
            errors.append(
                f"incomplete-device allowlist {device_id}: no reason"
            )
        try:
            review_by = date.fromisoformat(entry.get("review_by", ""))
        except ValueError:
            errors.append(
                f"incomplete-device allowlist {device_id}: invalid review_by"
            )
        else:
            if review_by < date.today():
                errors.append(
                    f"incomplete-device allowlist {device_id}: review expired "
                    f"on {review_by.isoformat()}"
                )
        if device_id in completed_device_ids:
            errors.append(
                f"incomplete-device allowlist {device_id}: device is complete; "
                "remove the stale exemption"
            )

    for device_id in sorted(set(manifest_devices) - completed_device_ids):
        if device_id not in allowlist:
            errors.append(
                f"incomplete device {device_id}: no allowlist exemption; "
                "complete every peripheral before registering the device"
            )

    report = {
        "models": len(models),
        "model_status": dict(sorted(status_counts.items())),
        "models_with_test_evidence": dict(sorted(tested_model_counts.items())),
        "devices": len(manifest_devices),
        "device_status": dict(sorted(device_status_counts.items())),
        "requirements_total": requirements_total,
        "requirements_covered": requirements_covered,
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
