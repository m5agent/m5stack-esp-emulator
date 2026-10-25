#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

from firmware_manifest import (  # noqa: E402
    ManifestError,
    detect_image_capabilities,
    evaluate_license_policy,
    import_package,
    load_device_profile,
    normalize_capability_declarations,
    validate_capabilities,
    validate_manifest_structure,
)
from test_firmware_analysis import (  # noqa: E402
    build_flash,
    build_flash_with_secure_boot_v2,
    build_flash_with_fat,
    build_flash_with_littlefs,
    build_flash_with_spiffs,
)


class FirmwareManifestTests(unittest.TestCase):
    @staticmethod
    def license_manifest(*licenses: str) -> dict:
        return {
            "target": {
                "filesystems": [
                    {
                        "partition": "storage",
                        "declared_licenses": list(licenses),
                    }
                ]
            },
            "provenance": {"license": None},
            "review": {"sbom": {"licenses": []}},
        }

    def test_schema_file_is_valid_json(self):
        schema = json.loads(
            (ROOT / "platform/tools/firmware_manifest.schema.json").read_text()
        )
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertIn("license_policy", schema["properties"])
        capability_properties = schema["properties"]["capabilities"]["properties"]
        self.assertIn("detected", capability_properties)
        self.assertIn("observed", capability_properties)
        self.assertIn("observation", capability_properties)
        self.assertIn(
            "secure_boot_image",
            schema["properties"]["security"]["properties"],
        )
        trust_root_schema = schema["properties"]["security"]["properties"][
            "trust_root"
        ]
        self.assertEqual(
            trust_root_schema["properties"]["status"]["const"],
            "not-verified",
        )
        self.assertIn(
            "mismatch-unverified-source",
            trust_root_schema["properties"]["comparison"]["enum"],
        )
        anti_rollback_schema = schema["properties"]["security"]["properties"][
            "anti_rollback"
        ]
        self.assertEqual(
            anti_rollback_schema["properties"]["status"]["const"],
            "not-verified",
        )
        self.assertIn(
            "image-below-efuse-unverified-source",
            anti_rollback_schema["properties"]["comparison"]["enum"],
        )
        segment_properties = (
            schema["properties"]["artifact"]["properties"]["segments"]["items"][
                "properties"
            ]
        )
        self.assertIn("declared_integrity", segment_properties)

    def test_license_policy_accepts_allowlisted_declarations(self):
        policy = evaluate_license_policy(
            self.license_manifest("MIT", "Apache-2.0"),
            allowed_licenses=["MIT", "Apache-2.0"],
        )
        self.assertEqual(policy["status"], "PASS")
        self.assertEqual(policy["decision"], "allowlisted")
        self.assertEqual(
            policy["discovered_licenses"],
            ["Apache-2.0", "MIT"],
        )
        self.assertFalse(policy["findings"])

    def test_license_policy_rejects_denied_license(self):
        policy = evaluate_license_policy(
            self.license_manifest("GPL-3.0-only"),
            allowed_licenses=["MIT", "GPL-3.0-only"],
            denied_licenses=["GPL-3.0-only"],
        )
        self.assertEqual(policy["status"], "REJECTED")
        self.assertEqual(
            [finding["code"] for finding in policy["findings"]],
            ["license_denied"],
        )

    def test_license_policy_requires_review_without_allowlist(self):
        policy = evaluate_license_policy(
            self.license_manifest("MIT"),
        )
        self.assertEqual(policy["status"], "REVIEW_REQUIRED")
        self.assertIn(
            "license_allowlist_not_configured",
            {finding["code"] for finding in policy["findings"]},
        )

    def test_license_policy_requires_declarations(self):
        policy = evaluate_license_policy(
            self.license_manifest(),
            allowed_licenses=["MIT"],
        )
        self.assertEqual(policy["status"], "REVIEW_REQUIRED")
        self.assertIn(
            "license_not_declared",
            {finding["code"] for finding in policy["findings"]},
        )

    def test_imports_spiffs_inventory_without_sensitive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "spiffs.bin"
            image.write_bytes(build_flash_with_spiffs())
            manifest = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]

        filesystem = manifest["target"]["filesystems"][0]
        self.assertEqual(filesystem["type"], "spiffs")
        self.assertEqual(filesystem["status"], "PASS")
        self.assertEqual(filesystem["declared_licenses"], ["BSD-3-Clause"])
        self.assertEqual(filesystem["file_count"], 4)
        self.assertNotIn("device.key", json.dumps(manifest))
        self.assertEqual(validate_manifest_structure(manifest), [])

    def test_import_persists_allowlisted_license_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "spiffs.bin"
            image.write_bytes(build_flash_with_spiffs())
            manifest = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
                allowed_licenses=["BSD-3-Clause"],
            )["manifest"]

        self.assertEqual(manifest["license_policy"]["status"], "PASS")
        self.assertEqual(
            manifest["license_policy"]["discovered_licenses"],
            ["BSD-3-Clause"],
        )
        self.assertEqual(manifest["validation"]["status"], "PASS")
        self.assertNotIn(
            "license_policy_review_required",
            {
                issue["code"]
                for issue in manifest["validation"]["warnings"]
            },
        )
        self.assertEqual(validate_manifest_structure(manifest), [])
        inconsistent = json.loads(json.dumps(manifest))
        inconsistent["license_policy"]["status"] = "REJECTED"
        self.assertIn(
            "license_policy.status is REJECTED",
            "\n".join(validate_manifest_structure(inconsistent)),
        )

    def test_imports_sparse_merged_image_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "community.bin"
            image.write_bytes(build_flash())
            image.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "firmware_id": "123",
                        "firmware_name": "Community Probe",
                        "source_url": "https://example.invalid/firmware",
                        "source_type": "COMMUNITY",
                        "resolved_version": "1.2.3",
                        "supported_devices": [
                            {"device_slug": "sticks3"}
                        ],
                    }
                )
            )
            result = import_package(
                image,
                root / "out",
                flash_size=8 << 20,
            )
            manifest = result["manifest"]
            output_image = Path(result["image_path"])
            self.assertEqual(manifest["validation"]["status"], "PASS")
            self.assertEqual(manifest["device_id"], "sticks3")
            self.assertEqual(manifest["target"]["soc"], "esp32s3")
            self.assertEqual(manifest["target"]["flash_size"], 8 << 20)
            self.assertEqual(output_image.stat().st_size, 8 << 20)
            self.assertEqual(
                manifest["artifact"]["sha256"],
                manifest["artifact"]["artifact_id"],
            )
            self.assertNotEqual(
                manifest["artifact"]["source_sha256"],
                manifest["artifact"]["sha256"],
            )
            self.assertEqual(
                manifest["provenance"]["firmware_id"],
                "123",
            )
            self.assertEqual(validate_manifest_structure(manifest), [])

    def test_efuse_summary_adds_redacted_security_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "probe.bin"
            firmware.write_bytes(build_flash())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
                "CONFIG_SECURE_FLASH_ENC_ENABLED=y\n"
            )
            (root / "efuse-summary.json").write_text(
                "espefuse v5.6.0\n\n"
                "=== Run \"summary\" command ===\n"
                + json.dumps(
                    {
                        "ABS_DONE_1": {
                            "value": "True",
                            "readable": True,
                        },
                        "SPI_BOOT_CRYPT_CNT": {
                            "value": "Enable",
                            "readable": True,
                        },
                        "SECURE_VERSION": {
                            "value": 7,
                            "readable": True,
                        },
                        "KEY_PURPOSE_0": {
                            "value": "SECURE_BOOT_DIGEST0",
                            "readable": True,
                        },
                        "WR_DIS_SECURE_BOOT_EN": {
                            "value": "True",
                            "readable": True,
                        },
                        "BLOCK_KEY0": {
                            "value": "EFUSE_SECRET_SENTINEL",
                            "raw_value": "EFUSE_SECRET_SENTINEL",
                            "readable": True,
                        },
                    }
                )
            )
            result = import_package(
                firmware,
                root / "out",
                flash_size=8 << 20,
            )
            manifest = result["manifest"]
            output_text = "\n".join(
                path.read_text(errors="ignore")
                for path in (root / "out").rglob("*")
                if path.is_file()
            )
        self.assertEqual(manifest["security"]["secure_boot"], "v2")
        self.assertEqual(
            manifest["security"]["flash_encryption"],
            "enabled",
        )
        self.assertEqual(
            manifest["security"]["secure_boot_config"],
            "v2",
        )
        self.assertEqual(
            manifest["security"]["efuse"],
            "summary-included",
        )
        summary = manifest["security"]["efuse_summary"]
        self.assertEqual(summary["secure_version"], 7)
        self.assertEqual(
            summary["key_purposes"],
            [{"block": 0, "purpose": "SECURE_BOOT_DIGEST0"}],
        )
        self.assertTrue(summary["write_protected"]["secure_boot"])
        self.assertIn(
            "efuse_summary_unverified",
            {
                row["code"]
                for row in manifest["validation"]["warnings"]
            },
        )
        self.assertNotIn("EFUSE_SECRET_SENTINEL", json.dumps(manifest))
        self.assertNotIn("EFUSE_SECRET_SENTINEL", output_text)
        self.assertFalse((root / "out" / "efuse-summary.json").exists())
        self.assertEqual(validate_manifest_structure(manifest), [])

    def test_efuse_summary_keeps_config_and_runtime_state_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "probe.bin"
            firmware.write_bytes(build_flash())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
                "CONFIG_SECURE_FLASH_ENC_ENABLED=y\n"
            )
            (root / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {
                            "value": "False",
                            "readable": True,
                        },
                        "SPI_BOOT_CRYPT_CNT": {
                            "value": "Disable",
                            "readable": True,
                        },
                    }
                )
            )
            manifest = import_package(
                firmware,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]
        security = manifest["security"]
        self.assertEqual(security["secure_boot"], "disabled")
        self.assertEqual(security["secure_boot_config"], "v2")
        self.assertEqual(security["flash_encryption"], "disabled")
        self.assertEqual(security["flash_encryption_config"], "enabled")
        codes = {
            row["code"]
            for row in manifest["validation"]["warnings"]
        }
        self.assertIn("secure_boot_config_not_enabled", codes)
        self.assertIn("flash_encryption_config_not_enabled", codes)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "probe.bin"
            firmware.write_bytes(build_flash())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=n\n"
                "CONFIG_SECURE_FLASH_ENC_ENABLED=n\n"
            )
            (root / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {"value": "True", "readable": True},
                        "SPI_BOOT_CRYPT_CNT": {
                            "value": "Enable",
                            "readable": True,
                        },
                    }
                )
            )
            reverse_manifest = import_package(
                firmware,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]
        reverse_codes = {
            row["code"]
            for row in reverse_manifest["validation"]["warnings"]
        }
        self.assertIn(
            "secure_boot_config_disabled_but_runtime_enabled",
            reverse_codes,
        )
        self.assertIn(
            "flash_encryption_config_disabled_but_runtime_enabled",
            reverse_codes,
        )
        self.assertIn("secure_boot_key_purpose_not_observed", reverse_codes)
        self.assertIn(
            "flash_encryption_key_purpose_not_observed",
            reverse_codes,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "probe.bin"
            firmware.write_bytes(build_flash())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V1_ENABLED=y\n"
            )
            (root / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {"value": "True", "readable": True},
                        "KEY_PURPOSE_0": {
                            "value": "SECURE_BOOT_DIGEST0",
                            "readable": True,
                        },
                    }
                )
            )
            mode_manifest = import_package(
                firmware,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]
        self.assertIn(
            "secure_boot_mode_mismatch",
            {
                row["code"]
                for row in mode_manifest["validation"]["warnings"]
            },
        )

    def test_secure_boot_v2_image_evidence_does_not_claim_trust(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "signed.bin"
            image.write_bytes(build_flash_with_secure_boot_v2())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            manifest = import_package(
                image,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]

        evidence = manifest["security"]["secure_boot_image"]
        self.assertEqual(evidence["status"], "signed-image-observed")
        self.assertEqual(evidence["signature_authenticity"], "not-verified")
        self.assertEqual(evidence["trust_root"], "not-verified")
        self.assertEqual(
            {row["label"] for row in evidence["images"]},
            {"bootloader", "factory"},
        )
        self.assertTrue(
            all(
                block["signature_math"] == "valid"
                and block["signature_math_valid"] is True
                for image in evidence["images"]
                for block in image["blocks"]
            )
        )
        warning_codes = {
            row["code"]
            for row in manifest["validation"]["warnings"]
        }
        self.assertIn(
            "secure_boot_v2_image_signature_authenticity_unverified",
            warning_codes,
        )
        self.assertNotIn(
            "secure_boot_v2_image_signature_not_observed",
            warning_codes,
        )
        self.assertEqual(validate_manifest_structure(manifest), [])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "ecdsa-signed.bin"
            image.write_bytes(
                build_flash_with_secure_boot_v2(
                    scheme="ecdsa",
                    curve_id=2,
                )
            )
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            ecdsa_manifest = import_package(
                image,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]

        ecdsa_evidence = ecdsa_manifest["security"][
            "secure_boot_image"
        ]
        self.assertTrue(
            all(
                block["signature_math"] == "valid"
                and block["signature_math_valid"] is True
                for image in ecdsa_evidence["images"]
                for block in image["blocks"]
            )
        )
        self.assertNotIn(
            "secure_boot_v2_image_signature_math_not_verified",
            {
                row["code"]
                for row in ecdsa_manifest["validation"]["warnings"]
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = bytearray(build_flash_with_secure_boot_v2())
            image[0x10500] ^= 0xFF
            path = root / "tampered.bin"
            path.write_bytes(image)
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            tampered = import_package(
                path,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]

        self.assertEqual(
            tampered["security"]["secure_boot_image"]["status"],
            "invalid",
        )
        self.assertIn(
            "secure_boot_v2_image_signature_invalid",
            {
                row["code"]
                for row in tampered["validation"]["warnings"]
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "unsigned.bin"
            image.write_bytes(build_flash())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            unsigned = import_package(
                image,
                root / "out",
                flash_size=8 << 20,
            )["manifest"]

        self.assertEqual(
            unsigned["security"]["secure_boot_image"]["status"],
            "not-found",
        )
        self.assertIn(
            "secure_boot_v2_image_signature_not_observed",
            {
                row["code"]
                for row in unsigned["validation"]["warnings"]
            },
        )
        self.assertEqual(
            unsigned["security"]["trust_root"]["comparison"],
            "not-applicable",
        )

    def test_secure_boot_image_compares_efuse_key_digest_without_trust(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "signed.bin"
            image.write_bytes(build_flash_with_secure_boot_v2())
            (root / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            baseline = import_package(
                image,
                root / "out-baseline",
                flash_size=8 << 20,
            )["manifest"]
            digest = {
                block["public_key_digest_sha256"]
                for evidence_image in baseline["security"][
                    "secure_boot_image"
                ]["images"]
                for block in evidence_image["blocks"]
            }
            self.assertEqual(len(digest), 1)
            matching_digest = digest.pop()
            self.assertEqual(
                baseline["security"]["trust_root"]["comparison"],
                "efuse-summary-not-included",
            )
            self.assertEqual(
                baseline["security"]["anti_rollback"]["comparison"],
                "efuse-summary-not-included",
            )

            matching = root / "matching"
            matching_image = matching / "signed.bin"
            matching.mkdir()
            matching_image.write_bytes(build_flash_with_secure_boot_v2())
            (matching / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            (matching / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {
                            "value": "True",
                            "readable": True,
                        },
                        "KEY_PURPOSE_0": {
                            "value": "SECURE_BOOT_DIGEST0",
                            "readable": True,
                        },
                        "BLOCK_KEY0": {
                            "value": matching_digest.upper(),
                            "readable": True,
                        },
                    }
                )
            )
            matched_manifest = import_package(
                matching_image,
                matching / "out",
                flash_size=8 << 20,
            )["manifest"]
            matched_trust = matched_manifest["security"]["trust_root"]
            self.assertEqual(matched_trust["status"], "not-verified")
            self.assertEqual(
                matched_trust["comparison"],
                "match-unverified-source",
            )
            self.assertEqual(
                matched_trust["source"],
                "package-espefuse-json-unverified",
            )
            self.assertEqual(
                {
                    (row["image"], row["public_key_digest_sha256"])
                    for row in matched_trust["matching_pairs"]
                },
                {
                    ("bootloader", matching_digest),
                    ("factory", matching_digest),
                },
            )
            self.assertEqual(
                matched_manifest["security"]["efuse_summary"][
                    "secure_boot_key_digests"
                ],
                [
                    {
                        "block": 0,
                        "purpose": "SECURE_BOOT_DIGEST0",
                        "digest_sha256": matching_digest,
                    }
                ],
            )
            self.assertEqual(
                validate_manifest_structure(matched_manifest),
                [],
            )

            mismatched = root / "mismatched"
            mismatched_image = mismatched / "signed.bin"
            mismatched.mkdir()
            mismatched_image.write_bytes(
                build_flash_with_secure_boot_v2()
            )
            (mismatched / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            (mismatched / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {
                            "value": "True",
                            "readable": True,
                        },
                        "KEY_PURPOSE_0": {
                            "value": "SECURE_BOOT_DIGEST0",
                            "readable": True,
                        },
                        "BLOCK_KEY0": {
                            "value": "0" * 64,
                            "readable": True,
                        },
                    }
                )
            )
            mismatched_manifest = import_package(
                mismatched_image,
                mismatched / "out",
                flash_size=8 << 20,
            )["manifest"]
            self.assertEqual(
                mismatched_manifest["security"]["trust_root"][
                    "comparison"
                ],
                "mismatch-unverified-source",
            )
            self.assertEqual(
                mismatched_manifest["security"]["trust_root"][
                    "matching_pairs"
                ],
                [],
            )
            self.assertIn(
                "secure_boot_v2_image_public_key_digest_mismatch",
                {
                    row["code"]
                    for row in mismatched_manifest["validation"][
                        "warnings"
                    ]
                },
            )

            unavailable = root / "unavailable"
            unavailable_image = unavailable / "signed.bin"
            unavailable.mkdir()
            unavailable_image.write_bytes(
                build_flash_with_secure_boot_v2()
            )
            (unavailable / "sdkconfig").write_text(
                "CONFIG_SECURE_BOOT=y\n"
                "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
            )
            (unavailable / "efuse-summary.json").write_text(
                json.dumps(
                    {
                        "ABS_DONE_1": {
                            "value": "True",
                            "readable": True,
                        },
                        "KEY_PURPOSE_0": {
                            "value": "SECURE_BOOT_DIGEST0",
                            "readable": True,
                        },
                    }
                )
            )
            unavailable_manifest = import_package(
                unavailable_image,
                unavailable / "out",
                flash_size=8 << 20,
            )["manifest"]
            self.assertEqual(
                unavailable_manifest["security"]["trust_root"][
                    "comparison"
                ],
                "efuse-key-digest-unavailable",
            )

        claimed = json.loads(json.dumps(matched_manifest))
        claimed["security"]["trust_root"]["status"] = "verified"
        self.assertIn(
            "must not claim a verified trust root",
            "\n".join(validate_manifest_structure(claimed)),
        )
        invalid_comparison = json.loads(json.dumps(matched_manifest))
        invalid_comparison["security"]["trust_root"][
            "comparison"
        ] = "trusted"
        self.assertIn(
            "manifest.security.trust_root.comparison is invalid",
            "\n".join(validate_manifest_structure(invalid_comparison)),
        )

    def test_secure_boot_anti_rollback_does_not_claim_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def import_with_efuse(
                name: str,
                *,
                image_version: int,
                efuse_version: int | None,
                secure_boot_enabled: bool = True,
            ) -> dict:
                case = root / name
                case.mkdir()
                image = case / "signed.bin"
                image.write_bytes(
                    build_flash(secure_version=image_version)
                )
                (case / "sdkconfig").write_text(
                    "CONFIG_SECURE_BOOT=y\n"
                    "CONFIG_SECURE_BOOT_V2_ENABLED=y\n"
                )
                summary = {
                    "ABS_DONE_1": {
                        "value": (
                            "True" if secure_boot_enabled else "False"
                        ),
                        "readable": True,
                    }
                }
                if efuse_version is not None:
                    summary["SECURE_VERSION"] = {
                        "value": efuse_version,
                        "readable": True,
                    }
                (case / "efuse-summary.json").write_text(
                    json.dumps(summary)
                )
                return import_package(
                    image,
                    case / "out",
                    flash_size=8 << 20,
                )["manifest"]

            below = import_with_efuse(
                "below",
                image_version=2,
                efuse_version=3,
            )
            satisfied = import_with_efuse(
                "satisfied",
                image_version=3,
                efuse_version=2,
            )
            unavailable = import_with_efuse(
                "unavailable",
                image_version=3,
                efuse_version=None,
            )
            disabled = import_with_efuse(
                "secure-boot-disabled",
                image_version=2,
                efuse_version=3,
                secure_boot_enabled=False,
            )

        below_policy = below["security"]["anti_rollback"]
        self.assertEqual(below_policy["status"], "not-verified")
        self.assertEqual(
            below_policy["comparison"],
            "image-below-efuse-unverified-source",
        )
        self.assertEqual(below_policy["image_secure_version"], 2)
        self.assertEqual(below_policy["efuse_secure_version"], 3)
        self.assertIn(
            "secure_boot_image_secure_version_below_efuse",
            {
                row["code"]
                for row in below["validation"]["warnings"]
            },
        )
        self.assertEqual(validate_manifest_structure(below), [])

        satisfied_policy = satisfied["security"]["anti_rollback"]
        self.assertEqual(
            satisfied_policy["comparison"],
            "image-satisfies-efuse-unverified-source",
        )
        self.assertNotIn(
            "secure_boot_image_secure_version_below_efuse",
            {
                row["code"]
                for row in satisfied["validation"]["warnings"]
            },
        )
        self.assertEqual(
            unavailable["security"]["anti_rollback"]["comparison"],
            "efuse-secure-version-unavailable",
        )
        self.assertEqual(disabled["security"]["secure_boot"], "disabled")
        self.assertEqual(
            disabled["security"]["anti_rollback"]["comparison"],
            "image-below-efuse-unverified-source",
        )
        self.assertNotIn(
            "secure_boot_image_secure_version_below_efuse",
            {
                row["code"]
                for row in disabled["validation"]["warnings"]
            },
        )

        claimed = json.loads(json.dumps(below))
        claimed["security"]["anti_rollback"]["status"] = "verified"
        self.assertIn(
            "must not claim verified runtime enforcement",
            "\n".join(validate_manifest_structure(claimed)),
        )
        invalid_comparison = json.loads(json.dumps(below))
        invalid_comparison["security"]["anti_rollback"][
            "comparison"
        ] = "runtime-enforced"
        self.assertIn(
            "manifest.security.anti_rollback.comparison is invalid",
            "\n".join(validate_manifest_structure(invalid_comparison)),
        )

    def test_manifest_id_is_content_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "probe.bin"
            image.write_bytes(build_flash())
            first = import_package(
                image,
                root / "out-a",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]
            second = import_package(
                image,
                root / "out-b",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]
        self.assertNotEqual(first["created_at"], second["created_at"])
        self.assertEqual(first["manifest_id"], second["manifest_id"])

    def test_webburner_manifest_id_ignores_output_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = build_flash()
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
            manifests = []
            for package_name in ("package-a", "package-b"):
                package = root / package_name
                package.mkdir()
                for name, data in parts.items():
                    (package / name).write_bytes(data)
                (package / "manifest.json").write_text(
                    json.dumps(
                        {
                            "name": "Identity Probe",
                            "version": "1.0.0",
                            "builds": [
                                {
                                    "chipFamily": "ESP32-S3",
                                    "parts": [
                                        {
                                            "path": name,
                                            "offset": offsets[name],
                                        }
                                        for name in parts
                                    ],
                                }
                            ],
                        }
                    )
                )
                manifests.append(
                    import_package(
                        package,
                        root / f"out-{package_name}",
                        device_id="sticks3",
                        flash_size=8 << 20,
                    )["manifest"]
                )
        self.assertNotEqual(
            manifests[0]["artifact"]["file"],
            manifests[1]["artifact"]["file"],
        )
        self.assertEqual(
            manifests[0]["artifact"]["sha256"],
            manifests[1]["artifact"]["sha256"],
        )
        self.assertEqual(
            manifests[0]["manifest_id"],
            manifests[1]["manifest_id"],
        )

    def test_imports_webburner_segmented_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = build_flash()
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
            for name, data in parts.items():
                (root / name).write_bytes(data)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "name": "Web Probe",
                        "version": "2.0.0",
                        "builds": [
                            {
                                "chipFamily": "ESP32-S3",
                                "parts": [
                                    {
                                        "path": name,
                                        "offset": offsets[name],
                                        "size": len(parts[name]),
                                        "sha256": hashlib.sha256(
                                            parts[name]
                                        ).hexdigest(),
                                        "sha1": hashlib.sha1(
                                            parts[name],
                                            usedforsecurity=False,
                                        ).hexdigest(),
                                        "md5": hashlib.md5(
                                            parts[name],
                                            usedforsecurity=False,
                                        ).hexdigest(),
                                    }
                                    for name in parts
                                ],
                            }
                        ],
                    }
                )
            )
            result = import_package(
                root,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )
            manifest = result["manifest"]
            self.assertEqual(
                manifest["provenance"]["source_format"],
                "web-manifest",
            )
            self.assertEqual(manifest["artifact"]["kind"], "segmented-flash")
            self.assertEqual(len(manifest["artifact"]["segments"]), 3)
            for segment in manifest["artifact"]["segments"]:
                self.assertTrue(
                    (root / "out" / segment["file"]).is_file()
                )
                self.assertEqual(
                    segment["declared_integrity"],
                    {
                        "status": "verified",
                        "algorithms": [
                            "size",
                            "sha256",
                            "sha1",
                            "md5",
                        ],
                        "weak_digest": True,
                    },
                )
            self.assertEqual(manifest["validation"]["status"], "PASS")
            self.assertEqual(validate_manifest_structure(manifest), [])
            tampered = json.loads(json.dumps(manifest))
            tampered["artifact"]["segments"][0]["declared_integrity"][
                "status"
            ] = "unverified"
            self.assertIn(
                "declared_integrity is invalid",
                "\n".join(validate_manifest_structure(tampered)),
            )

    def test_webburner_part_integrity_mismatch_is_rejected(self):
        image = build_flash()
        digest = hashlib.sha256(image).hexdigest()
        cases = (
            (
                "sha256",
                {"sha256": "0" * 64},
                "sha256 mismatch",
            ),
            (
                "size",
                {"size": len(image) + 1},
                "size mismatch",
            ),
            (
                "invalid",
                {"sha256": "not-a-digest"},
                "invalid sha256",
            ),
            (
                "conflict",
                {
                    "sha256": digest,
                    "integrity": {"sha256": "0" * 64},
                },
                "conflicting sha256",
            ),
            (
                "unknown-integrity",
                {
                    "integrity": {"crc32": "not-supported"},
                },
                "unsupported integrity fields",
            ),
        )
        for label, declared, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "firmware.bin").write_bytes(image)
                part = {
                    "path": "firmware.bin",
                    "offset": 0,
                    **declared,
                }
                (root / "manifest.json").write_text(
                    json.dumps(
                        {
                            "name": "Integrity Probe",
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
                with self.assertRaisesRegex(ManifestError, expected):
                    import_package(
                        root,
                        root / "out",
                        device_id="sticks3",
                        flash_size=8 << 20,
                    )

    def test_imports_flasher_args_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = build_flash()
            for name, start, end in (
                ("bootloader.bin", 0, 0x8000),
                ("partition-table.bin", 0x8000, 0x10000),
                ("app.bin", 0x10000, len(image)),
            ):
                (root / name).write_bytes(image[start:end])
            (root / "flasher_args.json").write_text(
                json.dumps(
                    {
                        "flash_settings": {"flash_size": "8MB"},
                        "flash_files": {
                            "0x0": "bootloader.bin",
                            "0x8000": "partition-table.bin",
                            "0x10000": "app.bin",
                        },
                        "extra_esptool_args": {"chip": "esp32s3"},
                    }
                )
            )
            result = import_package(
                root,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )
            manifest = result["manifest"]
            self.assertEqual(
                manifest["provenance"]["source_format"],
                "flasher-args",
            )
            self.assertEqual(manifest["target"]["soc"], "esp32s3")
            self.assertTrue(manifest["artifact"]["padded"])

    def test_capability_mismatch_is_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "probe.bin"
            image.write_bytes(build_flash())
            result = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
                required_capabilities=["wifi", "camera", "custom-input"],
                optional_capabilities=["lora", "custom-sensor"],
            )
        manifest = result["manifest"]
        self.assertEqual(manifest["validation"]["status"], "REJECTED")
        errors = manifest["validation"]["errors"]
        self.assertTrue(
            any(
                issue["code"] == "unsupported_capability"
                and issue["requirement"] == "camera"
                for issue in errors
            )
        )
        self.assertFalse(
            any(
                issue.get("requirement") == "wifi"
                for issue in errors
            )
        )
        self.assertIn(
            "unsupported_optional_capability",
            {
                warning["code"]
                for warning in manifest["validation"]["warnings"]
            },
        )
        self.assertIn(
            "unknown_optional_capability",
            {
                warning["code"]
                for warning in manifest["validation"]["warnings"]
            },
        )
        self.assertIn(
            "unknown_required_capability",
            {
                error["code"]
                for error in manifest["validation"]["errors"]
            },
        )
        self.assertEqual(manifest["validation"]["status"], "REJECTED")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "probe.bin"
            image.write_bytes(build_flash())
            unknown_result = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
                required_capabilities=["vendor-private-sensor"],
            )
        unknown_manifest = unknown_result["manifest"]
        self.assertEqual(unknown_manifest["validation"]["status"], "REJECTED")
        self.assertEqual(
            [
                error["code"]
                for error in unknown_manifest["validation"]["errors"]
            ],
            ["unknown_required_capability"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "probe.bin"
            image.write_bytes(build_flash())
            optional_result = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
                required_capabilities=["wifi"],
                optional_capabilities=["camera"],
            )
        optional_manifest = optional_result["manifest"]
        self.assertEqual(optional_manifest["validation"]["status"], "PASS")
        self.assertIn(
            "unsupported_optional_capability",
            {
                warning["code"]
                for warning in optional_manifest["validation"]["warnings"]
            },
        )

        manifest["capabilities"]["optional"] = ["WIFI"]
        self.assertIn(
            "manifest.capabilities.required and optional overlap",
            validate_manifest_structure(manifest),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "probe.bin"
            image.write_bytes(build_flash())
            with self.assertRaisesRegex(
                ManifestError,
                "both required and optional",
            ):
                import_package(
                    image,
                    root / "out",
                    device_id="sticks3",
                    flash_size=8 << 20,
                    required_capabilities=["wifi"],
                    optional_capabilities=["WIFI"],
                )

    def test_capability_declarations_are_bounded_and_canonical(self):
        self.assertEqual(
            normalize_capability_declarations(
                ["WIFI", "screen", "wifi"],
                field="required_capabilities",
            ),
            ["display", "wifi"],
        )
        self.assertEqual(
            normalize_capability_declarations(
                ["zigbee", "thread", "Classic Bluetooth"],
                field="required_capabilities",
            ),
            ["classic-bluetooth", "ieee802154"],
        )
        for value in (
            "wifi",
            [""],
            [1],
            ["x" * 65],
            ["wifi"] * 65,
        ):
            with self.subTest(value=value), self.assertRaises(ManifestError):
                normalize_capability_declarations(
                    value,
                    field="required_capabilities",
                )

    def test_sdkconfig_capabilities_are_detected_without_hard_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "probe.bin"
            firmware.write_bytes(build_flash())
            (root / "sdkconfig").write_text(
                "CONFIG_ESP_WIFI_ENABLED=y\n"
                "CONFIG_BT_ENABLED=y\n"
                "CONFIG_BT_CLASSIC_ENABLED=y\n"
                "CONFIG_ZB_ENABLED=y\n"
                "CONFIG_SPIRAM=y\n"
            )
            result = import_package(
                firmware,
                root / "out",
                device_id="cardputer-adv",
                flash_size=8 << 20,
            )
        manifest = result["manifest"]
        self.assertEqual(manifest["validation"]["status"], "PASS")
        self.assertEqual(
            manifest["capabilities"]["detected"],
            [
                {
                    "capability": "wifi",
                    "source": "sdkconfig",
                    "flag": "CONFIG_ESP_WIFI_ENABLED",
                },
                {
                    "capability": "ble",
                    "source": "sdkconfig",
                    "flag": "CONFIG_BT_ENABLED",
                },
                {
                    "capability": "classic-bluetooth",
                    "source": "sdkconfig",
                    "flag": "CONFIG_BT_CLASSIC_ENABLED",
                },
                {
                    "capability": "ieee802154",
                    "source": "sdkconfig",
                    "flag": "CONFIG_ZB_ENABLED",
                },
                {
                    "capability": "psram",
                    "source": "sdkconfig",
                    "flag": "CONFIG_SPIRAM",
                },
            ],
        )
        self.assertIn(
            "detected_capability_unavailable",
            {
                warning["code"]
                for warning in manifest["validation"]["warnings"]
            },
        )
        self.assertFalse(manifest["validation"]["errors"])
        self.assertEqual(validate_manifest_structure(manifest), [])

    def test_image_signatures_are_low_confidence_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "signatures.bin"
            image = bytearray(build_flash())
            image.extend(
                b"\x00esp_wifi_init\x00OV2640\x00esp_lcd_touch\x00"
            )
            firmware.write_bytes(image)
            observed, observation = detect_image_capabilities(firmware)
            result = import_package(
                firmware,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
                required_capabilities=["wifi"],
            )
            rejected = import_package(
                firmware,
                root / "out-camera",
                device_id="sticks3",
                flash_size=8 << 20,
                required_capabilities=["camera"],
            )["manifest"]
        self.assertEqual(
            observed,
            [
                {
                    "capability": "wifi",
                    "source": "image-signature",
                    "confidence": "low",
                    "signatures": ["esp_wifi_init"],
                },
                {
                    "capability": "camera",
                    "source": "image-signature",
                    "confidence": "low",
                    "signatures": ["ov2640"],
                },
                {
                    "capability": "touch",
                    "source": "image-signature",
                    "confidence": "low",
                    "signatures": ["esp_lcd_touch"],
                },
            ],
        )
        self.assertEqual(observation["status"], "SCANNED")
        self.assertEqual(observation["bytes_total"], len(image))
        self.assertFalse(observation["truncated"])
        manifest = result["manifest"]
        self.assertEqual(manifest["validation"]["status"], "PASS")
        self.assertEqual(
            manifest["capabilities"]["observed"],
            observed,
        )
        warning_codes = {
            warning["code"]
            for warning in manifest["validation"]["warnings"]
        }
        self.assertIn("observed_capability_unavailable", warning_codes)
        self.assertIn("observed_capability_not_declared", warning_codes)
        self.assertNotIn("required_capability_not_observed", warning_codes)
        self.assertFalse(manifest["validation"]["errors"])
        self.assertEqual(validate_manifest_structure(manifest), [])
        self.assertEqual(rejected["validation"]["status"], "REJECTED")
        self.assertIn(
            "unsupported_capability",
            {error["code"] for error in rejected["validation"]["errors"]},
        )
        self.assertNotIn(
            "required_capability_not_observed",
            {
                warning["code"]
                for warning in rejected["validation"]["warnings"]
            },
        )

    def test_required_capability_without_image_signature_is_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firmware = root / "plain.bin"
            firmware.write_bytes(build_flash())
            result = import_package(
                firmware,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
                required_capabilities=["wifi"],
            )
        manifest = result["manifest"]
        self.assertEqual(manifest["validation"]["status"], "PASS")
        self.assertEqual(manifest["capabilities"]["observed"], [])
        warning_codes = {
            warning["code"]
            for warning in manifest["validation"]["warnings"]
        }
        self.assertIn("required_capability_not_observed", warning_codes)
        self.assertFalse(manifest["validation"]["errors"])

    def test_manifest_includes_redacted_review_and_sbom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = bytearray(build_flash())
            image.extend(b"\xff" * 0x1000)
            marker = b"api_key=MANIFEST_SECRET_VALUE_12345"
            image[0x12000:0x12000 + len(marker)] = marker
            firmware = root / "review.bin"
            firmware.write_bytes(image)
            (root / "sbom.spdx.json").write_text(
                json.dumps(
                    {
                        "spdxVersion": "SPDX-2.3",
                        "packages": [
                            {
                                "name": "M5GFX",
                                "licenseDeclared": "MIT",
                            }
                        ],
                    }
                )
            )
            manifest = import_package(
                firmware,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]
        rendered = json.dumps(manifest)
        self.assertNotIn("MANIFEST_SECRET_VALUE_12345", rendered)
        self.assertEqual(manifest["review"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(manifest["review"]["sbom"]["component_count"], 1)
        self.assertEqual(
            manifest["resources"]["sbom"]["file"],
            "sbom.spdx.json",
        )
        codes = {
            issue["code"]
            for issue in manifest["validation"]["warnings"]
        }
        self.assertIn("static_review_required", codes)
        self.assertEqual(validate_manifest_structure(manifest), [])
        legacy = dict(manifest)
        legacy.pop("review")
        self.assertEqual(validate_manifest_structure(legacy), [])

    def test_manifest_includes_littlefs_inventory_and_sensitive_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "littlefs.bin"
            image.write_bytes(build_flash_with_littlefs())
            manifest = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]

        filesystem = manifest["target"]["filesystems"][0]
        self.assertEqual(filesystem["status"], "PASS")
        self.assertEqual(filesystem["declared_licenses"], ["MIT"])
        self.assertTrue(filesystem["sensitive_files"])
        self.assertEqual(manifest["review"]["status"], "REVIEW_REQUIRED")
        self.assertTrue(
            any(
                issue["code"] == "filesystem_sensitive_file"
                for issue in manifest["validation"]["warnings"]
            )
        )
        self.assertNotIn(
            "certs/device.key",
            json.dumps(manifest, sort_keys=True),
        )

    def test_manifest_includes_fat_inventory_and_sensitive_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "fat.bin"
            image.write_bytes(build_flash_with_fat())
            manifest = import_package(
                image,
                root / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]

        filesystem = manifest["target"]["filesystems"][0]
        self.assertEqual(filesystem["type"], "fat")
        self.assertEqual(filesystem["fat_type"], "fat16")
        self.assertEqual(filesystem["status"], "PASS")
        self.assertEqual(filesystem["declared_licenses"], ["Apache-2.0"])
        self.assertEqual(
            filesystem["permission_model"]["kind"],
            "fat-attributes",
        )
        self.assertEqual(
            filesystem["permission_summary"]["files_with_policy"],
            filesystem["file_count"],
        )
        self.assertTrue(filesystem["directory_permissions"])
        self.assertTrue(
            all(
                row["permission_policy"]["source"] == "fat-directory-entry"
                for row in filesystem["files"]
            )
        )
        self.assertTrue(filesystem["sensitive_files"])
        self.assertEqual(
            filesystem["sensitive_files"][0]["path"],
            "<redacted-sensitive-path>",
        )
        self.assertTrue(
            any(
                issue["code"] == "filesystem_sensitive_file"
                for issue in manifest["validation"]["warnings"]
            )
        )
        self.assertNotIn(
            "device.key",
            json.dumps(manifest, sort_keys=True),
        )

    def test_soc_and_flash_mismatches_are_rejected(self):
        profile = load_device_profile("sticks3")
        manifest = {
            "target": {
                "soc": "esp32c6",
                "flash_size": 16 << 20,
                "psram_size": 16 << 20,
            },
            "security": {
                "secure_boot": "v2",
                "flash_encryption": "enabled",
            },
            "capabilities": {
                "required": ["wifi", "camera"],
            },
        }
        result = validate_capabilities(manifest, profile)
        codes = {issue["code"] for issue in result["errors"]}
        self.assertEqual(result["status"], "REJECTED")
        self.assertTrue(
            {
                "soc_mismatch",
                "flash_size_mismatch",
                "psram_mismatch",
                "secure_boot_not_modeled",
                "flash_encryption_not_modeled",
                "unsupported_capability",
            }
            <= codes
        )

    def test_source_spdx_scan_feeds_license_policy_and_redacts_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            source = root / "src"
            source.mkdir(parents=True)
            (root / "firmware.bin").write_bytes(build_flash())
            (source / "main.c").write_text(
                "// SPDX-License-Identifier: MIT\nint main(void) { return 0; }\n"
            )
            (source / "secret.config.py").write_text(
                "# SPDX-License-Identifier: Apache-2.0\nVALUE = 1\n"
            )
            manifest = import_package(
                root,
                Path(tmp) / "out",
                device_id="sticks3",
                flash_size=8 << 20,
            )["manifest"]

        scan = manifest["source_license_scan"]
        self.assertEqual(scan["status"], "PASS")
        self.assertEqual(scan["coverage"]["files_scanned"], 2)
        self.assertEqual(
            scan["coverage"]["declared_licenses"],
            ["Apache-2.0", "MIT"],
        )
        self.assertEqual(
            {row["path"] for row in scan["files"]},
            {"src/main.c", "<redacted-sensitive-path>"},
        )
        redacted = next(
            row for row in scan["files"] if row.get("redacted")
        )
        self.assertIn("path_sha256", redacted)
        self.assertEqual(
            manifest["license_policy"]["coverage"][
                "source_code_declarations"
            ],
            2,
        )
        self.assertEqual(
            manifest["license_policy"]["discovered_licenses"],
            ["Apache-2.0", "MIT"],
        )
        self.assertNotIn(
            "secret.config.py",
            json.dumps(manifest, sort_keys=True),
        )

    def test_zip_slip_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "firmware.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.bin", b"bad")
            with self.assertRaisesRegex(ManifestError, "escapes root"):
                import_package(archive_path, root / "out")


if __name__ == "__main__":
    unittest.main(verbosity=2)
