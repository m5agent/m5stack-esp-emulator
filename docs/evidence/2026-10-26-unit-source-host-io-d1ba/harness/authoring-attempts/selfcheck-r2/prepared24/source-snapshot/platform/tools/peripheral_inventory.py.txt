#!/usr/bin/env python3
"""Build a device-center-friendly inventory from hardware and model manifests."""
from __future__ import annotations

import argparse
import json

from peripheral_catalog import (
    DEVICES,
    PERIPHERALS,
    PROFILES,
    control_capabilities,
    sensor_capabilities,
)
from runtime_coverage import (
    COVERAGE,
    validate as validate_runtime_coverage,
)


def load_inputs() -> tuple[list[dict], dict, list[dict]]:
    devices = json.loads(DEVICES.read_text())["devices"]
    peripheral = json.loads(PERIPHERALS.read_text())
    profiles = json.loads(PROFILES.read_text())["devices"]
    return devices, peripheral, profiles


def requirement_rows(
    hardware: dict, models: dict, components: list[dict]
) -> list[dict]:
    requirements = []
    for sensor in hardware.get("sensors", []):
        capabilities = sensor_capabilities(sensor)
        requirements.append(
            {
                "source": "sensor",
                "hardware": sensor,
                "hardware_part": sensor.split(":", 1)[1]
                if ":" in sensor
                else None,
                "capabilities": list(capabilities),
            }
        )
    for control in hardware.get("controls", []):
        capabilities = control_capabilities(control)
        requirements.append(
            {
                "source": "control",
                "hardware": control.get("id", control.get("type", "unknown")),
                "hardware_part": None,
                "capabilities": list(capabilities),
            }
        )

    for requirement in requirements:
        matches = []
        for component in components:
            model = models.get(component.get("model"), {})
            capabilities = set(model.get("capabilities", []))
            if capabilities.intersection(requirement["capabilities"]):
                matches.append(component.get("id"))
        requirement["components"] = matches
        requirement["covered"] = bool(matches)
    return requirements


def build_inventory() -> dict:
    devices, peripheral, profiles = load_inputs()
    coverage_errors, coverage_report = validate_runtime_coverage()
    if coverage_errors:
        raise RuntimeError(
            "invalid runtime coverage: " + "; ".join(coverage_errors)
        )
    models = peripheral["models"]
    manifests = peripheral["devices"]
    coverage = json.loads(COVERAGE.read_text())
    device_case_groups = coverage.get("device_case_groups", {})
    case_models = coverage.get("case_models", {})
    completion_allowlist = peripheral.get(
        "completion_policy", {}
    ).get("incomplete_device_allowlist", {})
    profiles_by_id = {profile["id"]: profile for profile in profiles}
    rows = []

    for device in devices:
        device_id = device["id"]
        manifest = manifests[device_id]
        components = manifest.get("components", [])
        blocker_reasons = {
            row.get("model"): row.get("reason")
            for row in manifest.get("peripheral_blockers", [])
        }
        requirements = requirement_rows(
            device.get("hardware", {}), models, components
        )
        runtime_group = device_case_groups.get(device_id, {})
        device_cases = (
            runtime_group.get("matrix", [])
            + runtime_group.get("external", [])
        )
        model_cases = {}
        for case_id in device_cases:
            for model_id in case_models.get(case_id, []):
                model_cases.setdefault(model_id, []).append(case_id)
        component_rows = []
        for component in components:
            model_id = component["model"]
            model = models[model_id]
            component_rows.append(
                {
                    "id": component.get("id"),
                    "model": model_id,
                    "kind": model.get("kind"),
                    "interface": component.get(
                        "bus", component.get("interface", model.get("interface"))
                    ),
                    "address": component.get(
                        "address", model.get("address")
                    ),
                    "qom_path": component.get("qom_path"),
                    "model_status": model.get("status"),
                    "device_status": component.get(
                        "status", model.get("status")
                    ),
                    "capabilities": model.get("capabilities", []),
                    "injection": model.get("injection", []),
                    "data_plane": model.get("data_plane"),
                    "evidence": model.get("evidence", []),
                    "blocker": (
                        component.get("blocker")
                        or model.get("blocker")
                        or blocker_reasons.get(model_id)
                    ),
                    "runtime_cases": model_cases.get(model_id, []),
                }
            )

        blocked = [
            row["model"]
            for row in component_rows
            if row["device_status"] != "simulated"
        ]
        gaps = [
            requirement
            for requirement in requirements
            if not requirement["covered"]
        ]
        complete = not blocked and not gaps
        declared_status = (
            manifest.get("peripheral_status")
            or manifest.get("status")
        )
        profile = profiles_by_id.get(device_id, {})
        rows.append(
            {
                "id": device_id,
                "name": device.get("name"),
                "group": device.get("group"),
                "runtime_status": device.get("runtime", {}).get("status"),
                "backend": profile.get("backend"),
                "machine": profile.get("machine"),
                "display": device.get("hardware", {}).get("display"),
                "peripheral_status": declared_status
                or ("simulated" if complete else "partial"),
                "complete": complete,
                "requirements": requirements,
                "components": component_rows,
                "blocked_models": blocked,
                "coverage_gaps": gaps,
                "evidence": manifest.get("evidence", []),
                "completion_exemption": completion_allowlist.get(device_id),
                "runtime_cases": {
                    **runtime_group,
                    "measured_models": sorted(
                        set(model_cases)
                    ),
                    "case_models": {
                        case_id: case_models.get(case_id, [])
                        for case_id in device_cases
                    },
                },
            }
        )
    return {
        "schema_version": 1,
        "device_count": len(rows),
        "complete_devices": sum(row["complete"] for row in rows),
        "incomplete_devices": sum(not row["complete"] for row in rows),
        "runtime_coverage": {
            key: value
            for key, value in coverage_report.items()
            if key != "errors"
        },
        "incomplete_device_allowlist": completion_allowlist,
        "devices": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    inventory = build_inventory()
    devices = inventory["devices"]
    if args.device:
        devices = [row for row in devices if row["id"] == args.device]
        if not devices:
            raise SystemExit(f"unknown device: {args.device}")

    incomplete = [row for row in devices if not row["complete"]]
    if args.json:
        payload = {
            key: value
            for key, value in inventory.items()
            if key != "devices"
        }
        payload["devices"] = devices
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for row in devices:
            blocked = ",".join(row["blocked_models"]) or "none"
            runtime_cases = row.get("runtime_cases") or {}
            case_ids = (
                runtime_cases.get("matrix", [])
                + runtime_cases.get("external", [])
            )
            print(
                f"{row['id']:18} {row['peripheral_status']:12} "
                f"requirements={len(row['requirements']):2} "
                f"components={len(row['components']):2} "
                f"cases={len(case_ids):2} blocked={blocked}"
            )
    if args.require_complete and incomplete:
        raise SystemExit(
            "incomplete devices: "
            + ", ".join(row["id"] for row in incomplete)
        )


if __name__ == "__main__":
    main()
