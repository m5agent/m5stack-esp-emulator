"""Static contracts for batch-12c Chain/Cat1/mini-imu-pro guest evidence."""
from __future__ import annotations
import hashlib, json, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "docs/evidence/2026-11-03-unit-batch12c-evidence"
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0161-unit-batch12c-chain-frames.patch"
UNITS = ("8servos2-chain", "chainbus", "cat1-cn", "mini-imu-pro")

class UnitBatch12cEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text())
        cls.units = {u["id"]: u for u in cls.catalog["units"]}
        cls.profiles = json.loads((ROOT / "platform/units/runtime-profiles.json").read_text())["units"]

    def test_chain_frame_patch(self):
        text = PATCH.read_text()
        self.assertIn("length < 3", text)
        self.assertIn("length < 4", text)
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text()
        self.assertIn("0161-unit-batch12c-chain-frames.patch", readme)
        self.assertIn("41 layers", readme)

    def test_four_units_evidence_backed(self):
        for unit_id in UNITS:
            unit, profile = self.units[unit_id], self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial", unit_id)
            self.assertEqual(unit["runtime"]["status"], "implemented", unit_id)
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            ev = profile["virtual_device_evidence"]
            report = ROOT / ev["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), ev["report_sha256"], unit_id)
            self.assertEqual(json.loads(report.read_text())["status"], "PASS", unit_id)
            self.assertIn("0161-unit-batch12c-chain-frames.patch", ev["patches"], unit_id)

    def test_counts_and_chain_contracts(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)
        self.assertEqual(sum(1 for p in self.profiles.values() if p["status"] == "implemented"), 158)
        self.assertEqual(sum(1 for p in self.profiles.values() if p["status"] != "implemented"), 2)
        self.assertIn("adc-values", self.units["8servos2-chain"]["inputs"])
        self.assertIn("current-ma", self.units["8servos2-chain"]["inputs"])
        self.assertIn("gpio-levels", self.units["chainbus"]["inputs"])
        self.assertIn("adc-values", self.units["chainbus"]["inputs"])

    def test_reports_and_summary(self):
        summary = json.loads((EVID / "summary.json").read_text())
        self.assertEqual({c["unit_id"] for c in summary["cases"]}, set(UNITS))
        self.assertEqual(summary["optional_mini_bps"]["status"], "NOT TESTED / MODEL MISSING")
        for unit_id in UNITS:
            self.assertTrue((EVID / f"report-{unit_id}.json").is_file(), unit_id)

if __name__ == "__main__":
    unittest.main()
