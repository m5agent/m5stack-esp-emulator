#!/usr/bin/env python3
"""Record low-confidence capability observations from a public firmware image."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from firmware_manifest import import_package, sha256_file  # noqa: E402


def issue_codes(manifest: dict[str, Any]) -> dict[str, list[str]]:
    validation = manifest.get("validation", {})
    return {
        "errors": [
            str(issue.get("code"))
            for issue in validation.get("errors", [])
            if isinstance(issue, dict)
        ],
        "warnings": [
            str(issue.get("code"))
            for issue in validation.get("warnings", [])
            if isinstance(issue, dict)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--flash-size", required=True, type=int)
    parser.add_argument("--require-capability", action="append", default=[])
    parser.add_argument("--optional-capability", action="append", default=[])
    parser.add_argument("--expect-observed", action="append", default=[])
    parser.add_argument("--mismatch-required", default="camera")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"image does not exist: {args.image}")
    if args.flash_size <= 0:
        parser.error("--flash-size must be positive")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    source_sha256 = sha256_file(args.image)
    source_bytes = args.image.stat().st_size
    normal = import_package(
        args.image,
        args.out_dir / "normal",
        device_id=args.device_id,
        flash_size=args.flash_size,
        required_capabilities=args.require_capability,
        optional_capabilities=args.optional_capability,
    )["manifest"]
    rejected = import_package(
        args.image,
        args.out_dir / "mismatch",
        device_id=args.device_id,
        flash_size=args.flash_size,
        required_capabilities=[args.mismatch_required],
    )["manifest"]

    capabilities = normal.get("capabilities", {})
    observed = capabilities.get("observed", [])
    observed_capabilities = {
        item.get("capability")
        for item in observed
        if isinstance(item, dict)
    }
    normal_codes = issue_codes(normal)
    rejected_codes = issue_codes(rejected)
    checks = {
        "normal_manifest_pass": normal.get("validation", {}).get("status")
        == "PASS",
        "observation_scanned": (
            capabilities.get("observation", {}).get("status") == "SCANNED"
        ),
        "observation_complete": (
            capabilities.get("observation", {}).get("truncated") is False
        ),
        "expected_capabilities_observed": set(
            args.expect_observed
        ).issubset(observed_capabilities),
        "observed_entries_are_low_confidence": all(
            isinstance(item, dict)
            and item.get("source") == "image-signature"
            and item.get("confidence") == "low"
            for item in observed
        ),
        "mismatch_rejected": rejected.get("validation", {}).get("status")
        == "REJECTED",
        "mismatch_issue_structured": (
            "unsupported_capability" in rejected_codes["errors"]
        ),
        "artifact_hash_equal": (
            normal.get("artifact", {}).get("sha256")
            == rejected.get("artifact", {}).get("sha256")
        ),
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-firmware-image-capability-observation",
        "date": "2026-10-25",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation": "static-manifest validation",
        "source": {
            "name": args.image.name,
            "bytes": source_bytes,
            "sha256": source_sha256,
            "device_id": args.device_id,
            "flash_size": args.flash_size,
        },
        "normal_import": {
            "status": normal.get("validation", {}).get("status"),
            "artifact_sha256": normal.get("artifact", {}).get("sha256"),
            "manifest_id": normal.get("manifest_id"),
            "required": capabilities.get("required", []),
            "optional": capabilities.get("optional", []),
            "detected": capabilities.get("detected", []),
            "observed": observed,
            "observation": capabilities.get("observation"),
            "issues": normal_codes,
        },
        "mismatch_import": {
            "status": rejected.get("validation", {}).get("status"),
            "required": rejected.get("capabilities", {}).get("required", []),
            "issues": rejected_codes,
        },
        "checks": checks,
        "not_claimed": [
            "runtime capability use",
            "boot or application behavior",
            "network or RF behavior",
            "secure-boot or eFuse execution",
            "license or legal approval",
            "physical hardware validation",
        ],
    }
    output = args.out_dir / "evidence.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
