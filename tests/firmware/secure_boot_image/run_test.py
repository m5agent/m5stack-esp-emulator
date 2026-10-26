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
from datetime import datetime
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
    efuse_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = root / name
    case.mkdir()
    image = case / f"{name}.bin"
    image.write_bytes(image_bytes)
    (case / "sdkconfig").write_text(
        "CONFIG_SECURE_BOOT=y\n"
        f"CONFIG_SECURE_BOOT_{secure_boot_config.upper()}_ENABLED=y\n"
    )
    if efuse_summary is not None:
        (case / "efuse-summary.json").write_text(
            json.dumps(efuse_summary)
        )
    return import_package(
        image,
        case / "out",
        flash_size=8 << 20,
    )["manifest"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--date",
        default=datetime.now().astimezone().date().isoformat(),
    )
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
        signed_key_digest = signed["security"]["secure_boot_image"][
            "images"
        ][0]["blocks"][0]["public_key_digest_sha256"]
        efuse_digest_match = import_case(
            build_flash_with_secure_boot_v2(),
            root,
            "efuse-digest-match",
            efuse_summary={
                "ABS_DONE_1": {"value": "True", "readable": True},
                "KEY_PURPOSE_0": {
                    "value": "SECURE_BOOT_DIGEST0",
                    "readable": True,
                },
                "BLOCK_KEY0": {
                    "value": signed_key_digest,
                    "readable": True,
                },
            },
        )
        efuse_digest_mismatch = import_case(
            build_flash_with_secure_boot_v2(),
            root,
            "efuse-digest-mismatch",
            efuse_summary={
                "ABS_DONE_1": {"value": "True", "readable": True},
                "KEY_PURPOSE_0": {
                    "value": "SECURE_BOOT_DIGEST0",
                    "readable": True,
                },
                "BLOCK_KEY0": {
                    "value": "0" * 64,
                    "readable": True,
                },
            },
        )
        efuse_digest_unavailable = import_case(
            build_flash_with_secure_boot_v2(),
            root,
            "efuse-digest-unavailable",
            efuse_summary={
                "ABS_DONE_1": {"value": "True", "readable": True},
                "KEY_PURPOSE_0": {
                    "value": "SECURE_BOOT_DIGEST0",
                    "readable": True,
                },
            },
        )
        efuse_anti_rollback_below = import_case(
            build_flash(secure_version=2),
            root,
            "efuse-anti-rollback-below",
            efuse_summary={
                "ABS_DONE_1": {"value": "True", "readable": True},
                "SECURE_VERSION": {"value": 3, "readable": True},
            },
        )
        efuse_anti_rollback_satisfied = import_case(
            build_flash(secure_version=3),
            root,
            "efuse-anti-rollback-satisfied",
            efuse_summary={
                "ABS_DONE_1": {"value": "True", "readable": True},
                "SECURE_VERSION": {"value": 2, "readable": True},
            },
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
        ecdsa_p192 = import_case(
            build_flash_with_secure_boot_v2(
                scheme="ecdsa",
                curve_id=1,
            ),
            root,
            "ecdsa-p192",
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
    ecdsa_p192_image = ecdsa_p192["security"]["secure_boot_image"]
    efuse_match_trust = efuse_digest_match["security"]["trust_root"]
    efuse_mismatch_trust = efuse_digest_mismatch["security"]["trust_root"]
    efuse_unavailable_trust = efuse_digest_unavailable["security"][
        "trust_root"
    ]
    anti_rollback_below = efuse_anti_rollback_below["security"][
        "anti_rollback"
    ]
    anti_rollback_satisfied = efuse_anti_rollback_satisfied["security"][
        "anti_rollback"
    ]
    anti_rollback_unavailable = efuse_digest_unavailable["security"][
        "anti_rollback"
    ]
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
            and signed["security"]["trust_root"].get("status")
            == "not-verified"
        ),
        "efuse_digest_match_compared": (
            efuse_match_trust.get("comparison")
            == "match-unverified-source"
            and efuse_match_trust.get("status") == "not-verified"
            and len(efuse_match_trust.get("matching_pairs", [])) == 2
        ),
        "efuse_digest_mismatch_compared": (
            efuse_mismatch_trust.get("comparison")
            == "mismatch-unverified-source"
            and efuse_mismatch_trust.get("status") == "not-verified"
            and efuse_mismatch_trust.get("matching_pairs") == []
        ),
        "efuse_digest_mismatch_warning_recorded": (
            "secure_boot_v2_image_public_key_digest_mismatch"
            in warning_codes(efuse_digest_mismatch)
        ),
        "efuse_digest_unavailable": (
            efuse_unavailable_trust.get("comparison")
            == "efuse-key-digest-unavailable"
            and efuse_unavailable_trust.get("status") == "not-verified"
        ),
        "anti_rollback_image_version_recorded": (
            efuse_anti_rollback_below["security"].get("secure_version")
            == 2
            and anti_rollback_below.get("image_secure_version") == 2
        ),
        "anti_rollback_below_compared": (
            anti_rollback_below.get("comparison")
            == "image-below-efuse-unverified-source"
            and anti_rollback_below.get("status") == "not-verified"
            and anti_rollback_below.get("efuse_secure_version") == 3
        ),
        "anti_rollback_below_warning_recorded": (
            "secure_boot_image_secure_version_below_efuse"
            in warning_codes(efuse_anti_rollback_below)
        ),
        "anti_rollback_satisfied_compared": (
            anti_rollback_satisfied.get("comparison")
            == "image-satisfies-efuse-unverified-source"
            and anti_rollback_satisfied.get("status") == "not-verified"
        ),
        "anti_rollback_version_unavailable": (
            anti_rollback_unavailable.get("comparison")
            == "efuse-secure-version-unavailable"
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
        "ecdsa_p192_observed": (
            ecdsa_p192_image.get("status")
            == "signed-image-observed"
            and all(
                block.get("scheme") == "ecdsa-p192-sha256"
                and block.get("signature_math") == "valid"
                for image in ecdsa_p192_image["images"]
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
            for manifest in (
                signed,
                tampered,
                unsigned,
                efuse_digest_match,
                efuse_digest_mismatch,
                efuse_digest_unavailable,
                efuse_anti_rollback_below,
                efuse_anti_rollback_satisfied,
            )
        ),
    }
    hashes_after = {
        name: sha256_file(path) for name, path in TOOL_PATHS.items()
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-secure-boot-v2-image-evidence",
        "date": args.date,
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
            "ecdsa_p192": ecdsa_p192_image,
            "ecdsa_p384": ecdsa_p384_image,
            "bad_signature": bad_signature_image,
            "bad_ecdsa_signature": bad_ecdsa_signature_image,
        },
        "efuse_trust_comparisons": {
            "match": efuse_match_trust,
            "mismatch": efuse_mismatch_trust,
            "digest_unavailable": efuse_unavailable_trust,
        },
        "anti_rollback_comparisons": {
            "below": anti_rollback_below,
            "satisfied": anti_rollback_satisfied,
            "secure_version_unavailable": anti_rollback_unavailable,
        },
        "not_claimed": [
            "embedded public key authenticity",
            "package-provided eFuse summary authenticity",
            "embedded public key trust against live eFuse",
            "bootloader anti-rollback enforcement",
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
