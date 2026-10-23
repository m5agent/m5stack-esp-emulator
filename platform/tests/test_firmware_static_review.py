#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(ROOT / "platform/tests"))

from firmware_static_review import review_firmware, review_sbom  # noqa: E402
from test_firmware_analysis import build_flash  # noqa: E402


class FirmwareStaticReviewTests(unittest.TestCase):
    def test_redacts_credentials_and_sanitizes_urls(self):
        blob = base64.b64encode(
            hashlib.sha512(b"firmware-static-review").digest()
            + hashlib.sha512(b"second-block").digest()
        ).decode("ascii")
        strings = (
            "https://user:password@example.com:8443/device"
            "?token=SECRET_QUERY_VALUE"
            "\x00api_key=SUPER_SECRET_VALUE_1234567890"
            "\x00-----BEGIN PRIVATE KEY-----"
            "\x00http://format.example:%d/template"
            f"\x00{blob}"
        ).encode("ascii")
        image = bytearray(build_flash())
        image.extend(b"\xff" * 0x2000)
        image[0x12000 : 0x12000 + len(strings)] = strings

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.bin"
            path.write_bytes(image)
            review = review_firmware(path)

        rendered = json.dumps(review, sort_keys=True)
        for secret in (
            "user:password",
            "SECRET_QUERY_VALUE",
            "SUPER_SECRET_VALUE_1234567890",
            "PRIVATE KEY",
            blob,
        ):
            self.assertNotIn(secret, rendered)
        self.assertEqual(review["status"], "REVIEW_REQUIRED")
        self.assertEqual(review["urls"][0]["scheme"], "https")
        self.assertEqual(review["urls"][0]["host"], "example.com")
        self.assertEqual(review["urls"][0]["port"], 8443)
        self.assertTrue(
            any(
                row["host"] == "format.example" and "port" not in row
                for row in review["urls"]
            )
        )
        self.assertIn(
            "private-key",
            {
                finding["category"]
                for finding in review["findings"]
            },
        )
        self.assertIn(
            "credential-assignment",
            {
                finding["category"]
                for finding in review["findings"]
            },
        )
        self.assertTrue(review["encoded_blobs"])
        self.assertNotIn(str(Path(tmp)), rendered)

    def test_clean_image_has_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clean.bin"
            path.write_bytes(build_flash())
            review = review_firmware(path)
        self.assertEqual(review["status"], "CLEAN")
        self.assertEqual(review["findings"], [])
        self.assertEqual(review["sbom"]["status"], "NOT_PROVIDED")

    def test_spdx_and_cyclonedx_sbom_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spdx = root / "sbom.spdx.json"
            spdx.write_text(
                json.dumps(
                    {
                        "spdxVersion": "SPDX-2.3",
                        "packages": [
                            {"name": "m5gfx", "licenseDeclared": "MIT"},
                            {"name": "idf", "licenseDeclared": "Apache-2.0"},
                        ],
                    }
                )
            )
            cyclonedx = root / "bom.json"
            cyclonedx.write_text(
                json.dumps(
                    {
                        "bomFormat": "CycloneDX",
                        "specVersion": "1.6",
                        "components": [
                            {
                                "name": "lvgl",
                                "licenses": [{"license": {"id": "MIT"}}],
                            }
                        ],
                    }
                )
            )
            spdx_result = review_sbom(spdx)
            cyclonedx_result = review_sbom(cyclonedx)
        self.assertEqual(spdx_result["status"], "PASS")
        self.assertEqual(spdx_result["component_count"], 2)
        self.assertEqual(
            spdx_result["licenses"],
            ["Apache-2.0", "MIT"],
        )
        self.assertEqual(cyclonedx_result["status"], "PASS")
        self.assertEqual(cyclonedx_result["component_count"], 1)
        self.assertEqual(cyclonedx_result["licenses"], ["MIT"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
