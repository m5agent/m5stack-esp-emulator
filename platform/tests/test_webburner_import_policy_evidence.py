#!/usr/bin/env python3
from __future__ import annotations

import json

from _docs_contract_support import DocsContractBase, ROOT

EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-webburner-import-policy.json"
)


class WebBurnerImportPolicyEvidenceTests(DocsContractBase):
    def test_webburner_import_policy_evidence(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(
            evidence["kind"],
            "m5stack-webburner-import-policy",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["date"], "2026-10-26")
        self.assertTrue(evidence["input_assets_unchanged"])
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(
            evidence["boundary"]["physical_hardware"],
            "NOT RUN",
        )

    def test_webburner_import_policy_contract(self) -> None:
        manifest = (ROOT / "platform/tools/firmware_manifest.py").read_text()
        for token in (
            "_safe_archive_path",
            "collide after normalization",
            "reserved name",
            "multi-build WebBurner package requires a target device",
            "package contains multiple {kind} resources",
            "multiple eFuse summaries",
            "multiple WebBurner manifests found",
        ):
            self.assertIn(token, manifest)


if __name__ == "__main__":
    import unittest

    unittest.main()
