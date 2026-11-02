"""Static contracts for the batch-11 guest evidence batch.

No QEMU/firmware is launched here. Pins the six evidence-backed Units, the
glass BLOCKED boundary, report hashes and the absence of a fabricated 0155
model-fix patch.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "docs/evidence/2026-11-03-unit-batch11"
PASSED = ("lorawan-as923", "lorawan-eu868", "rf433t", "rf433r", "audioplayer", "fingerprint2")
UNITS = PASSED + ("glass",)


class UnitBatch11EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_six_evidence_units_are_implemented(self):
        for unit_id in PASSED:
            unit, profile = self.units[unit_id], self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial", unit_id)
            self.assertEqual(unit["runtime"]["status"], "implemented", unit_id)
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(evidence["report_sha256"], hashlib.sha256(report.read_bytes()).hexdigest(), unit_id)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "PASS", unit_id)

    def test_glass_history_is_superseded_by_unblock_evidence(self):
        # batch11 recorded glass BLOCKED; the later glass-unblock evidence supersedes it.
        unit, profile = self.units["glass"], self.profiles["glass"]
        self.assertEqual(unit["model_status"], "partial")
        self.assertEqual(unit["runtime"]["status"], "implemented")
        self.assertEqual(profile["status"], "implemented")
        self.assertEqual(profile["hosts"], ["cores3"])
        self.assertIn("virtual_device_evidence", profile)
        self.assertIn("BLOCKED", unit["blocker"])
        report = EVID / "report-glass.json"
        self.assertTrue(report.is_file())
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "BLOCKED")
        self.assertIn("commands=0", report.read_text(encoding="utf-8"))

    def test_inventory_counts(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)
        # 140 batch11-era implemented + 7 batch-12a + 4 batch-12c + 7 batch-12b raw-I2C evidence promotions.
        self.assertEqual(sum(1 for p in self.profiles.values() if p["status"] == "implemented"), 158)
        self.assertEqual(sum(1 for p in self.profiles.values() if p["status"] != "implemented"), 2)

    def test_evidence_reports_and_summary_cover_seven(self):
        summary = json.loads((EVID / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual({case["unit_id"] for case in summary["cases"]}, set(UNITS))
        self.assertEqual(sum(1 for case in summary["cases"] if case["status"] == "PASS"), 6)
        self.assertEqual(summary["blocked_cases"][0]["unit_id"], "glass")
        self.assertIn("no 0155 model fix was needed", summary["qemu_builds"]["A"]["source_state"])
        for unit_id in UNITS:
            self.assertTrue((EVID / f"report-{unit_id}.json").is_file(), unit_id)

    def test_no_fabricated_0155_patch_or_guest_fix(self):
        self.assertFalse((ROOT / "patches/qemu-m5stack-peripherals/0155-unit-batch11-evidence-fixes.patch").exists())
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("39 layers", readme)
        self.assertNotIn("0155-unit-batch11", readme)

    def test_visual_mappings_cover_all_seven(self):
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, mappings)
        self.assertIn("BLOCKED", mappings)
        test = (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8")
        self.assertIn("catalog.units.length, 142", test) if False else self.assertIn("catalog.units.length, 160", test)

    def test_probe_runner_present(self):
        self.assertTrue((ROOT / "tests/units/batch11_probe/main.py").is_file())
        self.assertTrue((ROOT / "tests/units/run_batch11_cases.py").is_file())
        self.assertIn("BATCH11_PROBE_READY", (ROOT / "tests/units/batch11_probe/main.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
