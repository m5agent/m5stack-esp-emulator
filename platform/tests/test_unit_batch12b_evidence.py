"""Static contracts for the batch-12b seven-Unit I2C guest evidence batch.

No QEMU/firmware is launched here. Pins the seven PASS Units (raw machine.I2C
driver-gap probes), report hashes, the mutual-exclusion sessions for the
0x41/0x64 addresses, and the absence of a fabricated model-fix patch (no 0160).
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVID = ROOT / "docs/evidence/2026-11-03-unit-batch12b-evidence"
PASSED = ("bmm350", "ina226-10a", "ina226-1a", "roller485", "roller485-lite",
          "rollercan", "rollercan-lite")


class UnitBatch12bEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_seven_evidence_units_are_implemented(self):
        for unit_id in PASSED:
            unit, profile = self.units[unit_id], self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial", unit_id)
            self.assertEqual(unit["runtime"]["status"], "implemented", unit_id)
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(evidence["report_sha256"],
                             hashlib.sha256(report.read_bytes()).hexdigest(), unit_id)
            self.assertEqual(evidence["validation_scope"], "virtual-device validation")
            self.assertEqual(evidence["hardware"], "NOT RUN")
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "PASS", unit_id)
            # Driver-gap caveat must be explicit in the current contract.
            joined = json.dumps(unit, ensure_ascii=False)
            self.assertIn("machine.I2C", joined, unit_id)
            self.assertIn("driver-gap", joined, unit_id)
            self.assertIn("NOT RUN", joined, unit_id)

    def test_evidence_reports_and_summary_cover_seven(self):
        summary = json.loads((EVID / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual({case["unit_id"] for case in summary["cases"]}, set(PASSED))
        self.assertEqual(sum(1 for case in summary["cases"] if case["status"] == "PASS"), 7)
        self.assertEqual(summary["blocked_cases"], [])
        self.assertIn("no batch12b model bug found", summary["qemu_builds"]["A"]["source_state"])
        self.assertIn("raw machine.I2C", summary["driver_gap_caveat"])
        for unit_id in PASSED:
            report = EVID / f"report-{unit_id}.json"
            self.assertTrue(report.is_file(), unit_id)
            self.assertLess(len(report.read_bytes()), 64 * 1024, unit_id)
            self.assertTrue(json.loads(report.read_text(encoding="utf-8"))["checks"], unit_id)

    def test_mutually_exclusive_addresses_use_independent_sessions(self):
        reports = {unit_id: json.loads((EVID / f"report-{unit_id}.json").read_text(encoding="utf-8"))
                   for unit_id in PASSED}
        sessions = {reports[unit_id]["session_id_sha256"] for unit_id in PASSED}
        self.assertEqual(len(sessions), 7)
        for unit_id in PASSED:
            self.assertIn("session_id_sha256", reports[unit_id])
            self.assertNotIn("session_id", reports[unit_id])
        for unit_id in ("ina226-10a", "ina226-1a"):
            self.assertEqual(reports[unit_id]["port"]["id"], "port-a")
        for unit_id in ("roller485", "roller485-lite", "rollercan", "rollercan-lite"):
            self.assertEqual(reports[unit_id]["observations"][unit_id]["guest"]["product"],
                             1 if unit_id.startswith("roller485") else 2)

    def test_bmm350_dummy_bytes_are_pinned(self):
        report = json.loads((EVID / "report-bmm350.json").read_text(encoding="utf-8"))
        obs = report["observations"]["bmm350"]
        self.assertEqual(obs["guest"]["chip"], 0x33)
        self.assertEqual(obs["guest"]["otp_status"], 1)
        for axis in ("x", "y", "z", "temp"):
            self.assertEqual(obs["guest"][axis], obs["expected_from_qom"][axis], axis)
        self.assertIn("dummy", report["observations"]["bmm350"]["boundary"])

    def test_no_fabricated_model_fix(self):
        for name in ("0160-unit-batch12b-evidence-fixes.patch",
                     "0161-unit-batch12b-evidence-fixes.patch"):
            self.assertFalse((ROOT / "patches/qemu-m5stack-peripherals" / name).exists(), name)
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("39 layers", readme)
        self.assertNotIn("0160-unit-batch12b", readme)

    def test_probe_runner_present(self):
        self.assertTrue((ROOT / "tests/units/batch12b_probe/main.py").is_file())
        self.assertTrue((ROOT / "tests/units/run_batch12b_cases.py").is_file())
        probe = (ROOT / "tests/units/batch12b_probe/main.py").read_text(encoding="utf-8")
        self.assertIn("BATCH12B_PROBE_READY", probe)
        for token in ("readfrom_mem", "s24le", "s32le", "u16be", "s16be"):
            self.assertIn(token, probe)
        runner = (ROOT / "tests/units/run_batch12b_cases.py").read_text(encoding="utf-8")
        self.assertIn("raw machine.I2C register probe", runner)
        self.assertIn("purge=0", runner)

    def test_visual_mappings_and_ledger(self):
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(mappings.count("guest raw machine.I2C probe PASS"), 7)
        ledger = (ROOT / "docs/validation-ledger.md").read_text(encoding="utf-8")
        self.assertIn("batch12b", ledger.lower())
        readme = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        self.assertIn("2026-11-03-unit-batch12b-evidence", readme)

    def test_inventory_counts(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)
        self.assertEqual(sum(1 for p in self.profiles.values() if p["status"] == "implemented"), 158)
        self.assertEqual(sum(1 for p in self.profiles.values() if p["status"] != "implemented"), 2)


if __name__ == "__main__":
    unittest.main()
