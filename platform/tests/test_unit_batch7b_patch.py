"""Static contracts for the 0145 Unit batch-7 remaining-seven data planes.

These checks never launch QEMU or firmware. They pin the patch content, the
planned catalog/profile inventory and the visual-mapping registration that the
offline QOM smoke depends on, and they keep the driver-gap/DEFER, UART fixture
boundary, CAN attachment limitation and BMI270 aux boundary visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0145-unit-batch7b.patch"
IMPLEMENTED = ("hex", "catm", "catm-gnss", "lorawan-cn470", "can", "mini-imu-pro")
UNITS = IMPLEMENTED + ("mini-pdm",)


class UnitBatch7bPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_the_six_implemented_data_planes(self):
        for unit_id in IMPLEMENTED:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CanBusClientState", "inject-hex", "US_BMI270", "bmi270_refresh",
                      "frames-observed", "catm-gnss", "lorawan-cn470"):
            self.assertIn(token, self.text)

    def test_deferred_mini_pdm_is_not_registered(self):
        self.assertNotIn('"mini-pdm"', self.text)
        self.assertEqual(self.units["mini-pdm"]["model_status"], "planned")
        self.assertIn("DEFER", self.units["mini-pdm"]["blocker"])

    def test_patch_base_is_the_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0145-unit-batch7b.patch", readme)
        self.assertIn("28 layers", readme)
        for token in ("0143", "0144"):
            self.assertIn(token, readme)

    def test_hex_driver_gap_and_rmt_boundary(self):
        unit = json.dumps(self.units["hex"], ensure_ascii=False)
        for token in ("A045", "37", "SK6812", "driver-gap", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_uart_fixture_boundaries(self):
        for unit_id, token in (
            ("catm", "SIM7080G"),
            ("catm-gnss", "CGNSINF"),
            ("lorawan-cn470", "STM32WLE5"),
        ):
            unit = json.dumps(self.units[unit_id], ensure_ascii=False)
            for word in (token, "UART", "NOT RUN"):
                self.assertIn(word, unit, word)
            self.assertIn("ASR650x", json.dumps(self.units["lorawan-cn470"], ensure_ascii=False))

    def test_can_attachment_and_frame_boundary(self):
        unit = json.dumps(self.units["can"], ensure_ascii=False)
        for token in ("m5-canbus", "inject-hex", "frames-observed", "NOT modeled", "PORT.C"):
            self.assertIn(token, unit, token)
        self.assertIn("CanBusClientState", self.text)

    def test_mini_imu_pro_bmi270_aux_boundary(self):
        unit = json.dumps(self.units["mini-imu-pro"], ensure_ascii=False)
        for token in ("BMI270", "0x68", "BMM150", "0x76", "init", "aux", "NOT RUN"):
            self.assertIn(token, unit, token)
        self.assertIn("US_BMI270", self.text)

    def test_catalog_and_profiles_counts_and_visual_mappings(self):
        self.assertEqual(len(self.catalog["units"]), 130)
        self.assertEqual(len(self.profiles), 130)
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(f"'{unit_id}'", mappings)
        self.assertIn("all-130-products", (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8"))

    def test_planned_contracts_keep_blockers_and_empty_hosts(self):
        for unit_id in UNITS:
            unit = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "planned")
            self.assertEqual(unit["runtime"]["status"], "planned")
            self.assertEqual(unit["blocker"], unit["runtime"]["blocker"])
            self.assertTrue(unit["blocker"])
            self.assertEqual(profile["status"], "planned")
            self.assertEqual(profile["hosts"], [])
            self.assertTrue(profile["blocker"])


if __name__ == "__main__":
    unittest.main()
