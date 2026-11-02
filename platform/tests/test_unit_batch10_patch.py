"""Static contracts for the 0152 Unit batch-10 a/b registration.

These checks never launch QEMU or firmware. They pin the six minimum model
subsets, the 18 planned catalog/profile entries, the 12 planned-only units with
no model, the visual-audit inventory (160) and the no-guest-evidence boundary.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0152-unit-batch10ab.patch"
MODELED = ("dcssr", "puzzle", "dof6", "dof9", "dof10", "asr")
PLANNED_ONLY = ("ina226-1a", "roller485", "roller485-lite", "rollercan-lite",
                 "8servos2-chain", "cat1-cn", "chainbus")
# byteswitch/bytebutton/step16/timerpwr/mq got register-file models in 0157;
# their modeled planned contract is pinned by test_unit_batch12a_patch.py.
UNITS = MODELED + PLANNED_ONLY


class UnitBatch10PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_base_is_the_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0152-unit-batch10ab.patch", readme)
        self.assertIn("0154-unit-batch10-evidence-fixes.patch", readme)
        self.assertIn("38th layer", readme)
        self.assertIn("39 layers", readme)
        for token in ("0150", "0151", "0152", "0153", "0154", "0156", "0157", "0158"):
            self.assertIn(token, readme)

    def test_patch_registers_only_the_six_model_units(self):
        for unit_id in MODELED:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CONTROL_ACSSR", "asr_command_id", "puzzle", "US_BMI270",
                      "dof6", "dof9", "dof10"):
            self.assertIn(token, self.text)
        added = [line for line in self.text.splitlines() if line.startswith("+")]
        for unit_id in PLANNED_ONLY:
            self.assertFalse(any(f'"{unit_id}"' in line for line in added),
                             f"{unit_id} must not be registered as a model")

    def test_catalog_and_profiles_counts(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)

    def test_six_modeled_units_are_evidence_backed_and_twelve_stay_planned(self):
        import hashlib
        evidence_dir = ROOT / "docs/evidence/2026-11-03-unit-batch10"
        for unit_id in MODELED:
            unit, profile = self.units[unit_id], self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial", unit_id)
            self.assertEqual(unit["runtime"]["status"], "implemented", unit_id)
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(evidence["report_sha256"], hashlib.sha256(report.read_bytes()).hexdigest(), unit_id)
            self.assertIn("0154-unit-batch10-evidence-fixes.patch", evidence["patches"], unit_id)
        for unit_id in PLANNED_ONLY:
            unit, profile = self.units[unit_id], self.profiles[unit_id]
            self.assertIn(unit["model_status"], ("planned", "partial"), unit_id)
            self.assertIn(unit["runtime"]["status"], ("planned", "implemented"), unit_id)
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertTrue(unit["blocker"], unit_id)
            self.assertTrue(profile["blocker"], unit_id)
            self.assertNotIn("virtual_device_evidence", profile, unit_id)

    def test_six_models_expose_only_reusable_subset_properties(self):
        expected = {
            "dcssr": {"relay-level", "relay-transitions", "led-rgb", "fw-version"},
            "puzzle": {"led-rgb", "led-frames", "incomplete-frames", "output-transitions"},
            "dof6": {"acceleration-x", "acceleration-y", "acceleration-z",
                     "gyroscope-x", "gyroscope-y", "gyroscope-z",
                     "temperature-c", "whoami"},
            "dof9": {"acceleration-x", "acceleration-y", "acceleration-z",
                     "gyroscope-x", "gyroscope-y", "gyroscope-z",
                     "temperature-c", "whoami"},
            "dof10": {"acceleration-x", "acceleration-y", "acceleration-z",
                      "gyroscope-x", "gyroscope-y", "gyroscope-z",
                      "temperature-c", "whoami"},
            "asr": {"responses-hex", "tx-hex", "frames-sent", "frames-injected",
                    "command-id"},
        }
        for unit_id in MODELED:
            self.assertEqual(set(self.units[unit_id]["runtime"]["properties"]),
                             expected[unit_id], unit_id)

    def test_planned_only_units_keep_planned_profiles_with_models(self):
        # batch12b added register-file models for the remaining planned units (0159);
        # they still have no guest evidence, so their profiles must stay planned.
        for unit_id in PLANNED_ONLY:
            unit = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertIn(unit["model_status"], ("planned", "partial"), unit_id)
            self.assertIn(unit["runtime"]["status"], ("planned", "implemented"), unit_id)
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertIn(unit_id, self.profiles)

    def test_datasheet_gaps_are_explicit(self):
        for unit_id, token in (("dof9", "BMM350"), ("dof10", "SPA06"),
                               ("ina226-1a", "TI SBOS547C")):
            self.assertIn(token, json.dumps(self.units[unit_id], ensure_ascii=False), unit_id)
        self.assertEqual(self.units["dcssr"]["interface"]["address_7bit"], [0x50])
        self.assertEqual(self.units["ina226-1a"]["interface"]["address_7bit"], [0x41])
        self.assertEqual(self.units["byteswitch"]["interface"]["address_7bit"], [0x46])
        self.assertEqual(self.units["bytebutton"]["interface"]["address_7bit"], [0x47])
        self.assertEqual(self.units["step16"]["interface"]["address_7bit"], [0x48])
        self.assertEqual(self.units["timerpwr"]["interface"]["address_7bit"], [0x56])
        self.assertEqual(self.units["mq"]["interface"]["address_7bit"], [0x11])

    def test_visual_mappings_cover_all_eighteen(self):
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, mappings)
        test = (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8")
        self.assertIn("catalog.units.length, 160", test)
        self.assertIn("all-160-products", test)
        self.assertIn("all-160-products", (ROOT / "platform/tests/test_unit_batch3ab_patch.py").read_text())

    def test_implementation_status_doc_and_guest_evidence(self):
        doc = (ROOT / "docs/unit-research/2026-11-03-batch10-impl-status.md").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, doc)
        evidence = (ROOT / "docs/evidence/2026-11-03-unit-batch10/README.md").read_text(encoding="utf-8")
        self.assertIn("0154-unit-batch10-evidence-fixes.patch", evidence)
        self.assertIn("BLOCKED", evidence)
        for unit_id in MODELED:
            self.assertTrue((ROOT / f"docs/evidence/2026-11-03-unit-batch10/report-{unit_id}.json").is_file(), unit_id)


if __name__ == "__main__":
    unittest.main()
