#!/usr/bin/env python3
from __future__ import annotations

import json

from _docs_contract_support import DocsContractBase, ROOT

EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-manifest-policy-fail-closed.json"
)


class ManifestPolicyEvidenceTests(DocsContractBase):
    def test_manifest_policy_fail_closed_evidence(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(
            evidence["kind"],
            "m5stack-firmware-manifest-policy-fail-closed",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["date"], "2026-10-26")
        self.assertTrue(evidence["input_assets_unchanged"])
        self.assertTrue(all(evidence["checks"].values()))
        cases = evidence["cases"]
        self.assertEqual(cases["baseline"]["status"], "PASS")
        self.assertEqual(
            cases["missing_capabilities"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            cases["missing_capability_arrays"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            cases["signed_image_status_understatement"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            cases["invalid_efuse"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            cases["secure_version_below_efuse"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            evidence["boundary"]["physical_hardware"],
            "NOT RUN",
        )

    def test_manifest_policy_contract_is_documented(self) -> None:
        manifest = (ROOT / "platform/tools/firmware_manifest.py").read_text()
        for code in (
            "capabilities_required",
            "invalid_capability_declarations",
            "secure_boot_image_status_understated",
            "invalid_efuse_security_evidence",
            "secure_boot_efuse_key_mismatch",
            "firmware_secure_version_below_efuse",
        ):
            self.assertIn(code, manifest)
        schema = json.loads(
            (
                ROOT / "platform/tools/firmware_manifest.schema.json"
            ).read_text()
        )
        self.assertIn("capabilities", schema["required"])
        self.assertEqual(
            set(schema["properties"]["capabilities"]["required"]),
            {"required", "optional"},
        )
        efuse = schema["properties"]["security"]["properties"][
            "efuse_summary"
        ]
        self.assertEqual(
            set(efuse["required"]),
            {"secure_boot", "flash_encryption"},
        )
        self.assertNotIn(
            "enabled",
            efuse["properties"]["secure_boot"]["enum"],
        )
        self.assertNotIn(
            "enabled-active",
            efuse["properties"]["flash_encryption"]["enum"],
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
