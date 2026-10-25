#!/usr/bin/env python3
from __future__ import annotations

import json

from _docs_contract_support import DocsContractBase, ROOT

EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-26-unknown-required-capability-fail-closed.json"
)


class UnknownRequiredCapabilityEvidenceTests(DocsContractBase):
    def test_unknown_required_capability_fails_closed(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(
            evidence["kind"],
            "m5stack-firmware-capability-fail-closed",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["sample"]["source_sha256"],
            "8b7b47c8d601e1821817f8d0e6b55568829913e50333dbcc15de6ffdbad1997c",
        )
        self.assertEqual(
            evidence["sample"]["normalized_flash_sha256"],
            "d291e77f782399e37fd5b464f9b206a00654b2c10556d730d1c45667156c603f",
        )

        runs = evidence["runs"]
        self.assertEqual(runs["merged_baseline"]["status"], "PASS")
        self.assertEqual(runs["merged_baseline"]["exit_code"], 0)
        self.assertEqual(
            runs["merged_unknown_required"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            runs["merged_unknown_required"]["exit_code"],
            1,
        )
        self.assertEqual(
            [
                issue["code"]
                for issue in runs["merged_unknown_required"]["errors"]
            ],
            ["unknown_required_capability"],
        )
        self.assertEqual(
            runs["merged_unknown_optional"]["status"],
            "PASS",
        )
        self.assertIn(
            "unknown_optional_capability",
            {
                issue["code"]
                for issue in runs["merged_unknown_optional"]["warnings"]
            },
        )
        self.assertEqual(
            runs["webburner_baseline"]["source_format"],
            "web-manifest",
        )
        self.assertEqual(
            runs["webburner_baseline"]["artifact_sha256"],
            runs["merged_baseline"]["artifact_sha256"],
        )
        self.assertEqual(
            runs["webburner_repeat"]["manifest_id"],
            runs["webburner_baseline"]["manifest_id"],
        )
        self.assertEqual(
            runs["webburner_unknown_required"]["status"],
            "REJECTED",
        )
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["boundary"]["physical_hardware"], "NOT RUN")

    def test_manifest_and_runner_describe_the_same_policy(self) -> None:
        source = (
            ROOT / "platform/tools/firmware_manifest.py"
        ).read_text()
        self.assertIn(
            "unknown required capabilities fail closed",
            source,
        )
        docs = (ROOT / "docs/firmware-manifest.md").read_text()
        self.assertIn("未知 **required** capability", docs)
        self.assertIn("`REJECTED`", docs)


if __name__ == "__main__":
    import unittest

    unittest.main()
