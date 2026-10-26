#!/usr/bin/env python3
"""Validate that every simulated peripheral has a live runtime case."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "platform/peripherals/catalog.json"
COVERAGE = ROOT / "platform/peripherals/runtime-coverage.json"
MATRIX = ROOT / "tests/uiflow2/run_peripheral_matrix.py"
PROFILES = ROOT / "platform/qemu/profiles.json"
EVIDENCE_KEYS = (
    "serial_expect",
    "serial1_expect",
    "qom_expect",
    "qom_steps",
    "pcm",
    "rmt_nec",
    "rmt_ws2812",
    "disk",
    "frame_color",
)


def load_matrix_cases() -> dict[str, dict]:
    tree = ast.parse(MATRIX.read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "CASES"
            for target in node.targets
        ):
            continue
        return {
            case["id"]: case
            for case in ast.literal_eval(node.value)
        }
    raise RuntimeError("CASES assignment not found")


def validate() -> tuple[list[str], dict]:
    catalog = json.loads(CATALOG.read_text())
    coverage = json.loads(COVERAGE.read_text())
    profiles = json.loads(PROFILES.read_text())["devices"]
    cases = load_matrix_cases()
    external = coverage.get("external_cases", {})
    models = coverage.get("models", {})
    device_groups = coverage.get("device_case_groups", {})
    case_models = coverage.get("case_models", {})
    manifest_devices = catalog["devices"]
    errors: list[str] = []
    machine_devices = {
        profile.get("board_model"): profile["id"]
        for profile in profiles
        if profile.get("board_model")
    }
    machine_devices.update(coverage.get("machine_devices", {}))
    profile_devices = {profile["id"] for profile in profiles}
    for machine, device_id in coverage.get("machine_devices", {}).items():
        if device_id not in profile_devices:
            errors.append(
                f"machine alias {machine}: unknown device {device_id!r}"
            )

    known_cases = set(cases) | set(external)
    missing_case_models = sorted(known_cases - set(case_models))
    extra_case_models = sorted(set(case_models) - known_cases)
    if missing_case_models:
        errors.append(
            f"runtime cases without model coverage metadata: "
            f"{missing_case_models}"
        )
    if extra_case_models:
        errors.append(
            f"model coverage metadata references unknown cases: "
            f"{extra_case_models}"
        )

    simulated = {
        model_id
        for model_id, model in catalog["models"].items()
        if model["status"] == "simulated"
    }
    covered = set(models)
    missing = sorted(simulated - covered)
    extra = sorted(covered - simulated)
    if missing:
        errors.append(f"simulated models without runtime coverage: {missing}")
    if extra:
        errors.append(f"runtime coverage references non-simulated models: {extra}")

    for case_id, covered_models in case_models.items():
        if case_id not in known_cases:
            continue
        if not isinstance(covered_models, list):
            errors.append(f"{case_id}: case model coverage must be a list")
            continue
        if len(covered_models) != len(set(covered_models)):
            errors.append(f"{case_id}: duplicate model coverage entries")
        case = cases.get(case_id) or external.get(case_id)
        if case_id in cases:
            device_id = machine_devices.get(case.get("machine"))
        else:
            device_id = case.get("device")
        device_models = {
            component["model"]
            for component in manifest_devices.get(device_id, {}).get(
                "components", []
            )
        }
        for model_id in covered_models:
            if model_id not in catalog["models"]:
                errors.append(f"{case_id}: unknown covered model {model_id!r}")
                continue
            if model_id not in simulated:
                errors.append(
                    f"{case_id}: covered model {model_id!r} is not simulated"
                )
            if model_id not in device_models:
                errors.append(
                    f"{case_id}: covered model {model_id!r} is not a component "
                    f"of device {device_id!r}"
                )

    for model_id, sources in models.items():
        matrix_ids = sources.get("matrix", [])
        external_ids = sources.get("external", [])
        if not matrix_ids and not external_ids:
            errors.append(f"{model_id}: no runtime case")
        cited_cases = set(matrix_ids) | set(external_ids)
        declared_cases = {
            case_id
            for case_id, covered_models in case_models.items()
            if model_id in covered_models
        }
        if not (cited_cases & declared_cases):
            errors.append(
                f"{model_id}: no cited runtime case declares this model"
            )
        for case_id in matrix_ids:
            case = cases.get(case_id)
            if case is None:
                errors.append(f"{model_id}: unknown matrix case {case_id}")
                continue
            if not any(case.get(key) for key in EVIDENCE_KEYS):
                errors.append(
                    f"{model_id}: matrix case {case_id} has no runtime evidence"
                )
            device_id = machine_devices.get(case.get("machine"))
            if device_id is None:
                errors.append(
                    f"{model_id}: matrix case {case_id} has unknown machine "
                    f"{case.get('machine')!r}"
                )
            elif device_id not in catalog["models"][model_id].get(
                "tested_devices", []
            ):
                errors.append(
                    f"{model_id}: matrix case {case_id} runs on {device_id}, "
                    "not in tested_devices"
                )
        for case_id in external_ids:
            case = external.get(case_id)
            if case is None:
                errors.append(f"{model_id}: unknown external case {case_id}")
                continue
            device_id = case.get("device")
            if device_id not in profile_devices:
                errors.append(
                    f"{model_id}: external case {case_id} has unknown device "
                    f"{device_id!r}"
                )
            elif device_id not in catalog["models"][model_id].get(
                "tested_devices", []
            ):
                errors.append(
                    f"{model_id}: external case {case_id} runs on {device_id}, "
                    "not in tested_devices"
                )
            for key in ("test", "evidence"):
                path = ROOT / case.get(key, "")
                if not path.is_file():
                    errors.append(
                        f"{model_id}: external case {case_id} missing {key} "
                        f"file {case.get(key)!r}"
                    )

    assigned_matrix_cases: list[str] = []
    assigned_external_cases: list[str] = []
    for device_id, manifest in manifest_devices.items():
        group = device_groups.get(device_id)
        if group is None:
            errors.append(
                f"device {device_id}: no runtime case group for its peripheral "
                "components"
            )
            continue
        matrix_ids = group.get("matrix", [])
        external_ids = group.get("external", [])
        assigned_matrix_cases.extend(matrix_ids)
        assigned_external_cases.extend(external_ids)
        if not matrix_ids and not external_ids:
            errors.append(f"device {device_id}: runtime case group is empty")
        group_models = set(group.get("models", []))
        simulated_models = {
            component["model"]
            for component in manifest.get("components", [])
            if component.get(
                "status",
                catalog["models"][component["model"]]["status"],
            ) == "simulated"
        }
        measured_models: set[str] = set()
        for case_id in matrix_ids + external_ids:
            measured_models.update(case_models.get(case_id, []))
        missing_models = sorted(simulated_models - group_models)
        extra_models = sorted(group_models - simulated_models)
        if missing_models:
            errors.append(
                f"device {device_id}: runtime case group misses simulated "
                f"models {missing_models}"
            )
        if extra_models:
            errors.append(
                f"device {device_id}: runtime case group lists non-simulated "
                f"models {extra_models}"
            )
        unmeasured_models = sorted(simulated_models - measured_models)
        if unmeasured_models:
            errors.append(
                f"device {device_id}: no device-local case covers models "
                f"{unmeasured_models}"
            )
        for case_id in matrix_ids:
            case = cases.get(case_id)
            if case is None:
                errors.append(
                    f"device {device_id}: unknown matrix case {case_id}"
                )
                continue
            case_device = machine_devices.get(case.get("machine"))
            if case_device != device_id:
                errors.append(
                    f"device {device_id}: matrix case {case_id} runs on "
                    f"{case_device!r}"
                )
            if not any(case.get(key) for key in EVIDENCE_KEYS):
                errors.append(
                    f"device {device_id}: matrix case {case_id} has no "
                    "runtime evidence"
                )
        for case_id in external_ids:
            case = external.get(case_id)
            if case is None:
                errors.append(
                    f"device {device_id}: unknown external case {case_id}"
                )
                continue
            if case.get("device") != device_id:
                errors.append(
                    f"device {device_id}: external case {case_id} runs on "
                    f"{case.get('device')!r}"
                )
            for key in ("test", "evidence"):
                path = ROOT / case.get(key, "")
                if not path.is_file():
                    errors.append(
                        f"device {device_id}: external case {case_id} missing "
                        f"{key} file {case.get(key)!r}"
                    )

    for device_id in sorted(set(device_groups) - set(manifest_devices)):
        errors.append(
            f"runtime case group references unknown device {device_id!r}"
        )

    for kind, assigned, known in (
        ("matrix", assigned_matrix_cases, set(cases)),
        ("external", assigned_external_cases, set(external)),
    ):
        duplicates = sorted(
            case_id
            for case_id in set(assigned)
            if assigned.count(case_id) > 1
        )
        if duplicates:
            errors.append(
                f"{kind} cases assigned to multiple devices: {duplicates}"
            )
        unassigned = sorted(known - set(assigned))
        if unassigned:
            errors.append(
                f"{kind} cases not assigned to a device: {unassigned}"
            )

    report = {
        "simulated_models": len(simulated),
        "covered_models": len(simulated & covered),
        "matrix_cases": len(cases),
        "external_cases": len(external),
        "device_case_groups": len(device_groups),
        "assigned_matrix_cases": len(set(assigned_matrix_cases)),
        "assigned_external_cases": len(set(assigned_external_cases)),
        "machine_device_aliases": len(coverage.get("machine_devices", {})),
        "case_model_groups": len(case_models),
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
        print("RUNTIME_COVERAGE_OK")


if __name__ == "__main__":
    main()
