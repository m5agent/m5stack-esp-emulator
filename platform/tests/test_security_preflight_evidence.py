#!/usr/bin/env python3
from __future__ import annotations

import json

from _docs_contract_support import DocsContractBase, ROOT

EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-firmware-security-preflight-fail-closed.json"
)


class SecurityPreflightEvidenceTests(DocsContractBase):
    def test_security_preflight_rejects_understated_claims(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(
            evidence["kind"],
            "m5stack-firmware-security-preflight",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["date"], "2026-10-26")
        self.assertTrue(evidence["input_assets_unchanged"])
        self.assertTrue(all(evidence["checks"].values()))
        cases = evidence["cases"]
        self.assertEqual(cases["baseline"]["status"], "PASS")
        for name in (
            "aggregate_secure_boot",
            "understated_secure_boot_config",
            "understated_signed_image",
            "invalid_signed_image",
            "understated_flash_encryption_config",
            "understated_efuse_summary",
        ):
            self.assertEqual(cases[name]["status"], "REJECTED", name)
        self.assertEqual(
            evidence["boundary"]["physical_hardware"],
            "NOT RUN",
        )

    def test_security_preflight_contract_is_documented(self) -> None:
        manifest = (ROOT / "platform/tools/firmware_manifest.py").read_text()
        self.assertIn("secure_boot_config_not_modeled", manifest)
        self.assertIn("secure_boot_image_not_modeled", manifest)
        self.assertIn("flash_encryption_efuse_not_modeled", manifest)
        schema = json.loads(
            (
                ROOT / "platform/tools/firmware_manifest.schema.json"
            ).read_text()
        )
        security = schema["properties"]["security"]["properties"]
        self.assertIn("disabled", security["secure_boot_config"]["enum"])
        self.assertIn(
            "disabled",
            security["flash_encryption_config"]["enum"],
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
