#!/usr/bin/env python3
"""Verify that Device Service security preflight cannot be bypassed."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime
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
    "evidence-2026-10-26-firmware-security-preflight-fail-closed.json"
)
TOOL_PATHS = {
    "runner": Path(__file__).resolve(),
    "firmware_manifest": ROOT / "platform/tools/firmware_manifest.py",
    "manifest_schema": (
        ROOT / "platform/tools/firmware_manifest.schema.json"
    ),
    "test_image_builder": (
        ROOT / "platform/tests/test_firmware_analysis.py"
    ),
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def codes(result: dict) -> list[str]:
    return sorted(issue["code"] for issue in result["errors"])


def import_manifest(
    root: Path,
    name: str,
    image: bytes,
    *,
    sdkconfig: str | None = None,
) -> dict:
    case = root / name
    case.mkdir()
    path = case / "firmware.bin"
    path.write_bytes(image)
    if sdkconfig is not None:
        (case / "sdkconfig").write_text(sdkconfig)
    return import_package(
        path,
        case / "out",
        flash_size=8 << 20,
    )["manifest"]


def main() -> int:
    tool_hashes_before = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    device = load_device_profile("sticks3")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        baseline = import_manifest(root, "baseline", build_flash())
        secure_config = import_manifest(
            root,
            "secure-config",
            build_flash_with_secure_boot_v2(),
            sdkconfig=(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            ),
        )
        signed_image = import_manifest(
            root,
            "signed-image",
            build_flash_with_secure_boot_v2(),
        )

    baseline_result = validate_capabilities(baseline, device)
    aggregate = json.loads(json.dumps(secure_config))
    aggregate["security"]["secure_boot_config"] = "unknown"
    aggregate["security"]["secure_boot_image"]["status"] = "not-found"
    aggregate_result = validate_capabilities(aggregate, device)

    understated_config = json.loads(json.dumps(secure_config))
    understated_config["security"]["secure_boot"] = "unknown"
    understated_config["security"]["secure_boot_image"]["status"] = "not-found"
    config_result = validate_capabilities(understated_config, device)

    understated_image = json.loads(json.dumps(signed_image))
    understated_image["security"]["secure_boot"] = "unknown"
    understated_image["security"]["secure_boot_config"] = "unknown"
    image_result = validate_capabilities(understated_image, device)

    invalid_image = json.loads(json.dumps(understated_image))
    invalid_image["security"]["secure_boot_image"]["status"] = "invalid"
    invalid_image_result = validate_capabilities(invalid_image, device)

    understated_flash = json.loads(json.dumps(baseline))
    understated_flash["security"]["flash_encryption"] = "unknown"
    understated_flash["security"]["flash_encryption_config"] = "enabled"
    flash_result = validate_capabilities(understated_flash, device)

    understated_efuse = json.loads(json.dumps(baseline))
    understated_efuse["security"]["efuse"] = "summary-included"
    understated_efuse["security"]["efuse_summary"] = {
        "secure_boot": "v2",
        "flash_encryption": "enabled",
    }
    efuse_result = validate_capabilities(understated_efuse, device)

    missing_field = json.loads(json.dumps(baseline))
    missing_field["security"].pop("secure_boot")
    missing_errors = validate_manifest_structure(missing_field)
    invalid_enum = json.loads(json.dumps(baseline))
    invalid_enum["security"]["flash_encryption"] = "enabled-elsewhere"
    invalid_enum_errors = validate_manifest_structure(invalid_enum)
    schema = json.loads(TOOL_PATHS["manifest_schema"].read_text())
    config_enums = schema["properties"]["security"]["properties"]

    checks = {
        "baseline_pass": baseline_result["status"] == "PASS",
        "aggregate_secure_boot_rejected": (
            aggregate_result["status"] == "REJECTED"
            and "secure_boot_not_modeled" in codes(aggregate_result)
        ),
        "config_secure_boot_rejected": (
            config_result["status"] == "REJECTED"
            and "secure_boot_config_not_modeled" in codes(config_result)
        ),
        "signed_image_rejected": (
            image_result["status"] == "REJECTED"
            and "secure_boot_image_not_modeled" in codes(image_result)
        ),
        "invalid_image_rejected": (
            invalid_image_result["status"] == "REJECTED"
            and "secure_boot_image_invalid"
            in codes(invalid_image_result)
        ),
        "config_flash_encryption_rejected": (
            flash_result["status"] == "REJECTED"
            and "flash_encryption_config_not_modeled"
            in codes(flash_result)
        ),
        "efuse_secure_boot_rejected": (
            efuse_result["status"] == "REJECTED"
            and "secure_boot_efuse_not_modeled"
            in codes(efuse_result)
        ),
        "efuse_flash_encryption_rejected": (
            efuse_result["status"] == "REJECTED"
            and "flash_encryption_efuse_not_modeled"
            in codes(efuse_result)
        ),
        "missing_security_field_rejected": (
            "manifest.security.secure_boot is required"
            in missing_errors
        ),
        "invalid_security_enum_rejected": (
            "manifest.security.flash_encryption is invalid"
            in invalid_enum_errors
        ),
        "schema_allows_explicit_disabled_config": (
            "disabled"
            in config_enums["secure_boot_config"]["enum"]
            and "disabled"
            in config_enums["flash_encryption_config"]["enum"]
        ),
    }
    tool_hashes_after = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-firmware-security-preflight",
        "date": datetime.now().astimezone().date().isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation": "static manifest security compatibility",
        "tool_hashes": tool_hashes_before,
        "input_assets_unchanged": tool_hashes_before == tool_hashes_after,
        "checks": checks,
        "cases": {
            "baseline": baseline_result,
            "aggregate_secure_boot": aggregate_result,
            "understated_secure_boot_config": config_result,
            "understated_signed_image": image_result,
            "invalid_signed_image": invalid_image_result,
            "understated_flash_encryption_config": flash_result,
            "understated_efuse_summary": efuse_result,
            "missing_security_field_errors": missing_errors,
            "invalid_security_enum_errors": invalid_enum_errors,
        },
        "boundary": {
            "boot": "NOT RUN",
            "network": "NOT RUN",
            "secure_boot_runtime": "NOT RUN",
            "live_efuse": "NOT RUN",
            "flash_encryption_runtime": "NOT RUN",
            "physical_hardware": "NOT RUN",
        },
        "not_claimed": [
            "package-provided eFuse summary authenticity",
            "live eFuse state",
            "ROM or bootloader trust-chain execution",
            "Flash Encryption key or runtime state",
            "physical hardware validation",
        ],
    }
    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
