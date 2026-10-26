#!/usr/bin/env python3
"""Prove manifest capability and security evidence fail closed."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

from firmware_manifest import (  # noqa: E402
    import_package,
    load_device_profile,
    validate_capabilities,
    validate_manifest_structure,
)
from test_firmware_analysis import (  # noqa: E402
    build_flash,
    build_flash_with_secure_boot_v2,
)

OUTPUT = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-manifest-policy-fail-closed.json"
)
TOOL_PATHS = {
    "runner": Path(__file__).resolve(),
    "firmware_manifest": ROOT / "platform/tools/firmware_manifest.py",
    "manifest_schema": (
        ROOT / "platform/tools/firmware_manifest.schema.json"
    ),
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def issue_codes(result: dict) -> list[str]:
    return sorted(issue["code"] for issue in result["errors"])


def main() -> int:
    tool_hashes_before = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    device = load_device_profile("sticks3")
    with tempfile.TemporaryDirectory(prefix="m5-manifest-policy-") as tmp:
        root = Path(tmp)
        baseline_image = root / "baseline.bin"
        baseline_image.write_bytes(build_flash())
        baseline = import_package(
            baseline_image,
            root / "baseline-out",
            device_id="sticks3",
            flash_size=8 << 20,
        )["manifest"]

        signed_image = root / "signed.bin"
        signed_image.write_bytes(build_flash_with_secure_boot_v2())
        signed = import_package(
            signed_image,
            root / "signed-out",
            device_id="sticks3",
            flash_size=8 << 20,
        )["manifest"]

    baseline_result = validate_capabilities(baseline, device)

    missing_capabilities = copy.deepcopy(baseline)
    missing_capabilities.pop("capabilities")
    missing_capability_structure = validate_manifest_structure(
        missing_capabilities
    )
    missing_capability_result = validate_capabilities(
        missing_capabilities,
        device,
    )

    missing_capability_arrays = copy.deepcopy(baseline)
    missing_capability_arrays["capabilities"].pop("required")
    missing_capability_arrays["capabilities"].pop("optional")
    missing_array_structure = validate_manifest_structure(
        missing_capability_arrays
    )
    missing_array_result = validate_capabilities(
        missing_capability_arrays,
        device,
    )

    oversized_capabilities = copy.deepcopy(baseline)
    oversized_capabilities["capabilities"]["required"] = ["wifi"] * 65
    oversized_structure = validate_manifest_structure(
        oversized_capabilities
    )
    oversized_result = validate_capabilities(
        oversized_capabilities,
        device,
    )

    understated_image = copy.deepcopy(signed)
    understated_image["security"]["secure_boot"] = "unknown"
    understated_image["security"]["secure_boot_config"] = "unknown"
    understated_image["security"]["secure_boot_image"]["status"] = "not-found"
    status_result = validate_capabilities(understated_image, device)

    invalid_efuse = copy.deepcopy(baseline)
    invalid_efuse["security"]["secure_boot"] = "unknown"
    invalid_efuse["security"]["flash_encryption"] = "unknown"
    invalid_efuse["security"]["efuse_summary"] = {
        "secure_boot": "enabled",
        "flash_encryption": "enabled-active",
    }
    invalid_efuse_structure = validate_manifest_structure(invalid_efuse)
    invalid_efuse_result = validate_capabilities(invalid_efuse, device)

    key_mismatch = copy.deepcopy(understated_image)
    key_mismatch["security"]["trust_root"]["comparison"] = (
        "mismatch-unverified-source"
    )
    key_mismatch_result = validate_capabilities(key_mismatch, device)

    rollback = copy.deepcopy(understated_image)
    rollback["security"]["anti_rollback"]["comparison"] = (
        "image-below-efuse-unverified-source"
    )
    rollback["security"]["anti_rollback"]["image_secure_version"] = 1
    rollback["security"]["anti_rollback"]["efuse_secure_version"] = 2
    rollback_result = validate_capabilities(rollback, device)

    schema = json.loads(TOOL_PATHS["manifest_schema"].read_text())
    schema_capabilities = schema["properties"]["capabilities"]
    schema_security = schema["properties"]["security"]["properties"]
    efuse_schema = schema_security["efuse_summary"]

    checks = {
        "baseline_pass": baseline_result["status"] == "PASS",
        "capabilities_required_in_schema": (
            "capabilities" in schema["required"]
        ),
        "capability_arrays_required_in_schema": (
            set(schema_capabilities["required"])
            == {"required", "optional"}
        ),
        "capabilities_omitted_structure_rejected": (
            "manifest.capabilities is required"
            in missing_capability_structure
        ),
        "capabilities_omitted_validation_rejected": (
            missing_capability_result["status"] == "REJECTED"
            and "capabilities_required"
            in issue_codes(missing_capability_result)
        ),
        "capability_arrays_omitted_structure_rejected": (
            "manifest.capabilities.required is required"
            in missing_array_structure
            and "manifest.capabilities.optional is required"
            in missing_array_structure
        ),
        "capability_arrays_omitted_validation_rejected": (
            missing_array_result["status"] == "REJECTED"
            and "invalid_capability_declarations"
            in issue_codes(missing_array_result)
        ),
        "oversized_capability_array_rejected": (
            "manifest.capabilities.required exceeds 64 entries"
            in oversized_structure
            and oversized_result["status"] == "REJECTED"
            and "invalid_capability_declarations"
            in issue_codes(oversized_result)
        ),
        "signed_image_status_understatement_rejected": (
            status_result["status"] == "REJECTED"
            and "secure_boot_image_status_understated"
            in issue_codes(status_result)
        ),
        "invalid_efuse_structure_rejected": (
            "manifest.security.efuse_summary.secure_boot is invalid"
            in invalid_efuse_structure
            and "manifest.security.efuse_summary.flash_encryption is invalid"
            in invalid_efuse_structure
        ),
        "invalid_efuse_validation_rejected": (
            invalid_efuse_result["status"] == "REJECTED"
            and "invalid_efuse_security_evidence"
            in issue_codes(invalid_efuse_result)
        ),
        "efuse_summary_enums_bounded": (
            "v2"
            in efuse_schema["properties"]["secure_boot"]["enum"]
            and "enabled-active"
            not in efuse_schema["properties"]["flash_encryption"]["enum"]
        ),
        "secure_boot_key_mismatch_rejected": (
            key_mismatch_result["status"] == "REJECTED"
            and "secure_boot_efuse_key_mismatch"
            in issue_codes(key_mismatch_result)
        ),
        "secure_version_rollback_rejected": (
            rollback_result["status"] == "REJECTED"
            and "firmware_secure_version_below_efuse"
            in issue_codes(rollback_result)
        ),
    }
    tool_hashes_after = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-firmware-manifest-policy-fail-closed",
        "date": "2026-10-26",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation": "static manifest capability and security policy",
        "tool_hashes": tool_hashes_before,
        "input_assets_unchanged": tool_hashes_before == tool_hashes_after,
        "checks": checks,
        "cases": {
            "baseline": baseline_result,
            "missing_capabilities_structure": missing_capability_structure,
            "missing_capabilities": missing_capability_result,
            "missing_capability_arrays_structure": missing_array_structure,
            "missing_capability_arrays": missing_array_result,
            "oversized_capabilities_structure": oversized_structure,
            "oversized_capabilities": oversized_result,
            "signed_image_status_understatement": status_result,
            "invalid_efuse_structure": invalid_efuse_structure,
            "invalid_efuse": invalid_efuse_result,
            "secure_boot_key_mismatch": key_mismatch_result,
            "secure_version_below_efuse": rollback_result,
        },
        "boundary": {
            "boot": "NOT RUN",
            "network": "NOT RUN",
            "live_efuse": "NOT RUN",
            "secure_boot_runtime": "NOT RUN",
            "flash_encryption_runtime": "NOT RUN",
            "physical_hardware": "NOT RUN",
        },
        "not_claimed": [
            "package-provided eFuse summary authenticity",
            "live eFuse state",
            "bootloader trust-chain or anti-rollback execution",
            "Flash Encryption runtime state",
            "physical hardware validation",
        ],
    }
    OUTPUT.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
