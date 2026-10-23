#!/usr/bin/env python3
from __future__ import annotations

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
    import_package,
    load_device_profile,
    validate_capabilities,
    validate_manifest_structure,
)
from test_firmware_analysis import (  # noqa: E402
    build_flash,
    build_flash_with_fat,
    build_flash_with_littlefs,
)


class FirmwareManifestTests(unittest.TestCase):
    def test_schema_file_is_valid_json(self):
        schema = json.loads(
            (ROOT / "platform/tools/firmware_manifest.schema.json").read_text()
        )
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)

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
            self.assertEqual(manifest["validation"]["status"], "PASS")

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
                required_capabilities=["wifi", "camera"],
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
