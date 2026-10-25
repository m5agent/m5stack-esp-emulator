#!/usr/bin/env python3
"""Exercise Secure Boot v2 signature-sector manifest evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import struct
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

from firmware_manifest import (  # noqa: E402
    import_package,
    validate_manifest_structure,
)
from test_firmware_analysis import (  # noqa: E402
    build_flash,
    build_flash_with_secure_boot_v2,
)

TOOL_PATHS = {
    "runner": Path(__file__).resolve(),
    "test_image_builder": (
        ROOT / "platform/tests/test_firmware_analysis.py"
    ),
    "firmware_analysis": ROOT / "platform/tools/firmware_analysis.py",
    "firmware_manifest": ROOT / "platform/tools/firmware_manifest.py",
    "manifest_schema": (
        ROOT / "platform/tools/firmware_manifest.schema.json"
    ),
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def warning_codes(manifest: dict[str, Any]) -> set[str]:
    return {
        str(row.get("code") or "")
        for row in manifest.get("validation", {}).get("warnings", [])
        if isinstance(row, dict)
    }


def import_case(
    image_bytes: bytes,
    root: Path,
    name: str,
    *,
    secure_boot_config: str = "v2",
) -> dict[str, Any]:
    case = root / name
    case.mkdir()
    image = case / f"{name}.bin"
    image.write_bytes(image_bytes)
    (case / "sdkconfig").write_text(
        "CONFIG_SECURE_BOOT=y\n"
        f"CONFIG_SECURE_BOOT_{secure_boot_config.upper()}_ENABLED=y\n"
    )
    return import_package(
        image,
        case / "out",
        flash_size=8 << 20,
    )["manifest"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    hashes_before = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        signed = import_case(
            build_flash_with_secure_boot_v2(),
            root,
            "signed",
        )
        tampered_bytes = bytearray(build_flash_with_secure_boot_v2())
        tampered_bytes[0x10500] ^= 0xFF
        tampered = import_case(
            bytes(tampered_bytes),
            root,
            "tampered",
        )
        bad_signature_bytes = bytearray(
            build_flash_with_secure_boot_v2()
        )
        bad_sector = 0x11000
        bad_signature_bytes[bad_sector + 900] ^= 0x01
        struct.pack_into(
            "<I",
            bad_signature_bytes,
            bad_sector + 1196,
            zlib.crc32(
                bad_signature_bytes[
                    bad_sector : bad_sector + 1196
                ]
            ),
        )
        bad_signature = import_case(
            bytes(bad_signature_bytes),
            root,
            "bad-signature",
        )
        bad_ecdsa_bytes = bytearray(
            build_flash_with_secure_boot_v2(
                scheme="ecdsa",
                curve_id=2,
            )
        )
        bad_ecdsa_bytes[bad_sector + 115] ^= 0x01
        struct.pack_into(
            "<I",
            bad_ecdsa_bytes,
            bad_sector + 1196,
            zlib.crc32(
                bad_ecdsa_bytes[bad_sector : bad_sector + 1196]
            ),
        )
        bad_ecdsa_signature = import_case(
            bytes(bad_ecdsa_bytes),
            root,
            "bad-ecdsa-signature",
        )
        unsigned = import_case(
            build_flash(),
            root,
            "unsigned",
        )
        ecdsa_p256 = import_case(
            build_flash_with_secure_boot_v2(
                scheme="ecdsa",
                curve_id=2,
            ),
            root,
            "ecdsa-p256",
        )
        ecdsa_p384 = import_case(
            build_flash_with_secure_boot_v2(
                scheme="ecdsa",
                curve_id=3,
            ),
            root,
            "ecdsa-p384",
        )

    signed_image = signed["security"]["secure_boot_image"]
    tampered_image = tampered["security"]["secure_boot_image"]
    unsigned_image = unsigned["security"]["secure_boot_image"]
    bad_signature_image = bad_signature["security"][
        "secure_boot_image"
    ]
    bad_ecdsa_signature_image = bad_ecdsa_signature["security"][
        "secure_boot_image"
    ]
    ecdsa_p256_image = ecdsa_p256["security"]["secure_boot_image"]
    ecdsa_p384_image = ecdsa_p384["security"]["secure_boot_image"]
    signed_by_label = {
        row["label"]: row for row in signed_image["images"]
    }
    checks = {
        "signed_image_observed": (
            signed_image.get("status") == "signed-image-observed"
        ),
        "bootloader_digest_match": (
            signed_by_label.get("bootloader", {}).get(
                "image_digest_match"
            )
            is True
        ),
        "application_digest_match": (
            signed_by_label.get("factory", {}).get(
                "image_digest_match"
            )
            is True
        ),
        "public_key_digest_recorded": all(
            isinstance(
                block.get("public_key_digest_sha256"), str
            )
            and len(block["public_key_digest_sha256"]) == 64
            for image in signed_image["images"]
            for block in image.get("blocks", [])
        ),
        "rsa_signature_math_valid": all(
            block.get("signature_math") == "valid"
            and block.get("signature_math_valid") is True
            for image in signed_image["images"]
            for block in image.get("blocks", [])
        ),
        "authenticity_not_verified": (
            signed_image.get("signature_authenticity")
            == "not-verified"
            and signed_image.get("trust_root") == "not-verified"
        ),
        "tampered_digest_rejected": (
            tampered_image.get("status") == "invalid"
        ),
        "tampered_warning_recorded": (
            "secure_boot_v2_image_signature_invalid"
            in warning_codes(tampered)
        ),
        "unsigned_image_not_found": (
            unsigned_image.get("status") == "not-found"
        ),
        "ecdsa_p256_observed": (
            ecdsa_p256_image.get("status")
            == "signed-image-observed"
            and all(
                block.get("scheme") == "ecdsa-p256-sha256"
                and block.get("signature_math") == "valid"
                for image in ecdsa_p256_image["images"]
                for block in image.get("blocks", [])
            )
        ),
        "ecdsa_p384_observed": (
            ecdsa_p384_image.get("status")
            == "signed-image-observed"
            and all(
                block.get("scheme") == "ecdsa-p384-sha384"
                and block.get("signature_math") == "valid"
                for image in ecdsa_p384_image["images"]
                for block in image.get("blocks", [])
            )
        ),
        "bad_signature_math_rejected": (
            bad_signature_image.get("status") == "invalid"
            and any(
                image.get("status") == "signature-math-mismatch"
                for image in bad_signature_image["images"]
            )
        ),
        "bad_ecdsa_signature_math_rejected": (
            bad_ecdsa_signature_image.get("status") == "invalid"
            and any(
                image.get("status") == "signature-math-mismatch"
                for image in bad_ecdsa_signature_image["images"]
            )
        ),
        "missing_signature_warning_recorded": (
            "secure_boot_v2_image_signature_not_observed"
            in warning_codes(unsigned)
        ),
        "authenticity_warning_recorded": (
            "secure_boot_v2_image_signature_authenticity_unverified"
            in warning_codes(signed)
        ),
        "manifest_structure_valid": all(
            not validate_manifest_structure(manifest)
            for manifest in (signed, tampered, unsigned)
        ),
    }
    hashes_after = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-secure-boot-v2-image-evidence",
        "date": "2026-10-25",
        "validation": "static secure-boot image validation",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "schema_version_tested": 1,
        "tool_hashes": hashes_before,
        "input_assets_unchanged": hashes_before == hashes_after,
        "checks": checks,
        "security_images": {
            "signed": signed_image,
            "tampered": tampered_image,
            "unsigned": unsigned_image,
            "ecdsa_p256": ecdsa_p256_image,
            "ecdsa_p384": ecdsa_p384_image,
            "bad_signature": bad_signature_image,
            "bad_ecdsa_signature": bad_ecdsa_signature_image,
        },
        "not_claimed": [
            "embedded public key authenticity",
            "ECDSA P-192 mathematical verification",
            "embedded public key trust against live eFuse",
            "Secure Boot ROM/bootloader execution",
            "Secure Boot v1",
            "Flash Encryption key or runtime state",
            "physical hardware validation",
        ],
    }
    output = args.out_dir / "evidence.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
