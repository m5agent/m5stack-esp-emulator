#!/usr/bin/env python3
"""Verify optional WebBurner part size and digest declarations."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

from firmware_manifest import ManifestError, import_package  # noqa: E402
from test_firmware_analysis import build_flash  # noqa: E402


def write_package(
    root: Path,
    image: bytes,
    *,
    size: int | None,
    sha256: str | None,
    md5: str | None,
    integrity: dict | None = None,
) -> None:
    (root / "firmware.bin").write_bytes(image)
    part = {
        "path": "firmware.bin",
        "offset": 0,
    }
    if size is not None:
        part["size"] = size
    if sha256 is not None:
        part["sha256"] = sha256
    if md5 is not None:
        part["md5"] = md5
    if integrity is not None:
        part["integrity"] = integrity
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": "WebBurner Integrity Probe",
                "version": "1.0.0",
                "builds": [
                    {
                        "chipFamily": "ESP32-S3",
                        "parts": [part],
                    }
                ],
            }
        )
    )


def write_segmented_package(root: Path, image: bytes) -> None:
    parts = {
        "bootloader.bin": image[:0x8000],
        "partition-table.bin": image[0x8000:0x10000],
        "application.bin": image[0x10000:],
    }
    offsets = {
        "bootloader.bin": 0,
        "partition-table.bin": 0x8000,
        "application.bin": 0x10000,
    }
    declared_parts = []
    for name, data in parts.items():
        (root / name).write_bytes(data)
        declared_parts.append(
            {
                "path": name,
                "offset": offsets[name],
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "sha1": hashlib.sha1(
                    data,
                    usedforsecurity=False,
                ).hexdigest(),
                "md5": hashlib.md5(
                    data,
                    usedforsecurity=False,
                ).hexdigest(),
            }
        )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": "WebBurner Integrity Probe",
                "version": "1.0.0",
                "builds": [
                    {
                        "chipFamily": "ESP32-S3",
                        "parts": declared_parts,
                    }
                ],
            }
        )
    )


def reject_case(
    label: str,
    image: bytes,
    declared: dict,
    expected_error: str,
) -> dict:
    with tempfile.TemporaryDirectory(prefix=f"m5-web-integrity-{label}-") as tmp:
        root = Path(tmp)
        write_package(root, image, **declared)
        try:
            import_package(
                root,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )
        except ManifestError as error:
            message = str(error)
            return {
                "label": label,
                "status": "REJECTED",
                "error_type": type(error).__name__,
                "expected_error": expected_error,
                "error_match": expected_error in message,
                "error": message,
            }
        return {
            "label": label,
            "status": "UNEXPECTED_PASS",
            "expected_error": expected_error,
            "error_match": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    image = build_flash()
    image_sha256 = hashlib.sha256(image).hexdigest()
    image_md5 = hashlib.md5(
        image,
        usedforsecurity=False,
    ).hexdigest()
    with tempfile.TemporaryDirectory(prefix="m5-web-integrity-pass-") as tmp:
        root = Path(tmp)
        write_segmented_package(root, image)
        result = import_package(
            root,
            root / "out",
            device_id="sticks3",
            flash_size=8 << 20,
        )
        manifest = result["manifest"]
        segments = manifest["artifact"]["segments"]
        verified_segments = [
            segment
            for segment in segments
            if segment.get("declared_integrity")
            == {
                "status": "verified",
                "algorithms": ["size", "sha256", "sha1", "md5"],
                "weak_digest": True,
            }
        ]

    rejects = [
        reject_case(
            "sha256-mismatch",
            image,
            {
                "size": None,
                "sha256": "0" * 64,
                "md5": None,
            },
            "sha256 mismatch",
        ),
        reject_case(
            "size-mismatch",
            image,
            {
                "size": len(image) + 1,
                "sha256": None,
                "md5": None,
            },
            "size mismatch",
        ),
        reject_case(
            "invalid-sha256",
            image,
            {
                "size": None,
                "sha256": "not-a-digest",
                "md5": None,
            },
            "invalid sha256",
        ),
        reject_case(
            "conflicting-sha256",
            image,
            {
                "size": None,
                "sha256": image_sha256,
                "md5": None,
                "integrity": {"sha256": "0" * 64},
            },
            "conflicting sha256",
        ),
        reject_case(
            "unknown-integrity-field",
            image,
            {
                "size": None,
                "sha256": None,
                "md5": None,
                "integrity": {"crc32": "not-supported"},
            },
            "unsupported integrity fields",
        ),
    ]
    checks = {
        "valid_declarations_import": manifest["validation"]["status"] == "PASS",
        "declared_integrity_recorded": len(verified_segments) == len(segments),
        "sha256_mismatch_rejected": rejects[0]["error_match"],
        "size_mismatch_rejected": rejects[1]["error_match"],
        "invalid_digest_rejected": rejects[2]["error_match"],
        "conflicting_declarations_rejected": rejects[3]["error_match"],
        "unknown_integrity_rejected": rejects[4]["error_match"],
    }
    evidence = {
        "schema_version": 1,
        "kind": "webburner-part-integrity",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "validation": "static-manifest validation",
        "device_id": "sticks3",
        "input": {
            "synthetic_image_bytes": len(image),
            "synthetic_image_sha256": image_sha256,
            "synthetic_image_md5": image_md5,
        },
        "positive": {
            "status": manifest["validation"]["status"],
            "segments": len(segments),
            "verified_segments": len(verified_segments),
            "declared_integrity": (
                verified_segments[0]["declared_integrity"]
                if verified_segments
                else None
            ),
        },
        "negative_cases": rejects,
        "checks": checks,
        "not_claimed": [
            "source authenticity or publisher identity",
            "cryptographic signature verification",
            "boot, runtime behavior or network access",
            "secure boot or Flash Encryption execution",
            "physical hardware validation",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
