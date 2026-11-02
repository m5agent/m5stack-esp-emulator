"""Static contracts for the 0130 Unit batch-3 A+B data planes.

These checks never launch QEMU or firmware. They pin the patch content that the
offline QOM smoke and the planned catalog/profile inventory depend on, and they
keep the documented address conflicts and unresolved boundaries visible.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0130-unit-batch3ab.patch"
UNITS = ("rfid", "tube-pressure", "laser-rx", "extio", "dac2", "scales", "vmeter", "adc")


class UnitBatch3abPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]
        cls.visual = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")

    def test_patch_registers_all_eight_data_planes(self):
        for unit_id in ("rfid", "tube-pressure", "laser-rx", "extio", "dac2", "scales", "vmeter", "adc"):
            self.assertIn(unit_id, self.text)
        for token in ("CONTROL_PCA9554", "CONTROL_DAC2", "CONTROL_SCALES",
                      "US_ADS1100", "US_ADS1115_VMETER"):
            self.assertIn(token, self.text)
        for token in ("0x28", "0x27", "0x59", "0x26", "0x49", "0x53", "0x48"):
            self.assertIn(token, self.text)

    def test_guest_evidence_backed_upgrade_stays_partial(self):
        hosts = {"rfid": "cores3", "tube-pressure": "atoms3r", "laser-rx": "atoms3r",
                 "extio": "sticks3", "dac2": "cores3", "scales": "sticks3",
                 "vmeter": "cores3", "adc": "stopwatch"}
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "partial", unit_id)
            self.assertEqual(entry["runtime"]["status"], "implemented", unit_id)
            self.assertNotEqual(entry["model_status"], "simulated", unit_id)
            self.assertTrue(entry["blocker"], unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], [hosts[unit_id]], unit_id)
            self.assertTrue(profile["blocker"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(evidence["report_sha256"],
                             hashlib.sha256(report.read_bytes()).hexdigest(), unit_id)
            for patch in ("0130-unit-batch3ab.patch", "0133-unit-vmeter-default-config.patch",
                          "0135-unit-batch3ab-fixes.patch"):
                self.assertIn(patch, evidence["patches"], unit_id)
            for field in entry["inputs"]:
                self.assertIn(field, profile["inputs"], f"{unit_id}.{field}")
            for field in entry["outputs"]:
                self.assertIn(field, profile["state"], f"{unit_id}.{field}")

    def test_address_conflicts_and_unresolved_tokens_survive(self):
        rfid = json.dumps(self.units["rfid"], ensure_ascii=False)
        self.assertIn("rfid2", rfid)
        vmeter = json.dumps(self.units["vmeter"], ensure_ascii=False)
        self.assertIn("accel", vmeter)
        dac2 = json.dumps(self.units["dac2"], ensure_ascii=False)
        self.assertIn("extencoder", dac2)
        adc = json.dumps(self.units["adc"], ensure_ascii=False)
        self.assertIn("adc-v11", adc)
        self.assertIn("ADS1100", adc)
        scales = json.dumps(self.units["scales"], ensure_ascii=False)
        self.assertIn("4relay", scales)
        self.assertIn("weight-i2c", scales)
        self.assertIn("15-bit", dac2)
        self.assertIn("UART", json.dumps(self.units["laser-rx"], ensure_ascii=False))
        self.assertIn("±1.5kPa", json.dumps(self.units["tube-pressure"], ensure_ascii=False))

    def test_visual_audit_registers_all_eight_units(self):
        for unit_id in UNITS:
            self.assertTrue(f"'{unit_id}':" in self.visual or f"{unit_id}:" in self.visual, unit_id)
        self.assertIn("all-130-products", (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text())

    def test_patch_is_numbered_on_documented_base_and_has_no_guest_claim(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0130-unit-batch3ab.patch", readme)
        self.assertIn("0131", readme)
        for patch in ("0132-unit-batch3c-fixes.patch", "0133-unit-vmeter-default-config.patch",
                      "0135-unit-batch3ab-fixes.patch"):
            self.assertIn(patch, readme)
            self.assertTrue((ROOT / "patches/qemu-m5stack-peripherals" / patch).is_file(), patch)
        self.assertEqual(self.text.count("guest PASS"), 1)
        self.assertIn("No guest PASS", self.text)
        self.assertIn("planned", readme)
        research = (ROOT / "docs/unit-research/2026-11-02-batch3-protocols.md").read_text(encoding="utf-8")
        self.assertIn("0130-unit-batch3ab.patch", research)


if __name__ == "__main__":
    unittest.main()
