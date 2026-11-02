"""Static contracts for the 0146 Unit batch-8 first-five data planes.

These checks never launch QEMU or firmware. They pin the patch content, the
planned catalog/profile inventory and the visual-mapping registration that the
offline QOM smoke depends on, and they keep the reused-model boundaries, the
LCD address conflict, the GPS baud conflict and the blocked Mini CAN visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0146-unit-batch8a.patch"
IMPLEMENTED = ("pahub-v21", "gps-v11", "gps-sma", "lcd")
UNITS = IMPLEMENTED + ("mini-can",)


class UnitBatch8aPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_the_four_implemented_data_planes(self):
        for unit_id in IMPLEMENTED:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CONTROL_UNIT_LCD", "lcd_parse_command", "lcd_fb_store",
                      "gpio_gps_unit", "gps_baud", "pahub_dip", "dip-address"):
            self.assertIn(token, self.text)

    def test_blocked_mini_can_is_not_registered(self):
        # The 0145 layer already registers the batch-7 can/mini-can binding, so a
        # plain assertNotIn would trip on context lines; this batch-8 layer must not
        # ADD another registration path for mini-can.
        added = [line for line in self.text.splitlines() if line.startswith('+')]
        self.assertFalse(any('"mini-can"' in line for line in added))
        self.assertEqual(self.units["mini-can"]["model_status"], "planned")

    def test_patch_base_is_the_25_layer_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0146-unit-batch8a.patch", readme)
        self.assertIn("28 layers", readme)
        self.assertIn("0145", readme)

    def test_pahub_v21_reuses_mask_only_with_dip_fixture(self):
        unit = json.dumps(self.units["pahub-v21"], ensure_ascii=False)
        for token in ("PCA9548A", "0x70-0x77", "dip-address", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_gps_baud_conflict_stays_unresolved(self):
        for unit_id in ("gps-v11", "gps-sma"):
            unit = json.dumps(self.units[unit_id], ensure_ascii=False)
            for token in ("115200", "9600", "unresolved", "NOT RUN"):
                self.assertIn(token, unit, token)
            self.assertIn("baud", self.units[unit_id]["inputs"])

    def test_lcd_command_and_address_conflict(self):
        unit = json.dumps(self.units["lcd"], ensure_ascii=False)
        for token in ("ST7789V2", "0x3D", "0x3E", "READ_ID", "framebuffer", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_mini_can_is_blocked_not_fabricated(self):
        unit = json.dumps(self.units["mini-can"], ensure_ascii=False)
        for token in ("blocked", "TWAI", "attachment", "NOT RUN"):
            self.assertIn(token, unit, token)
        profile = self.profiles["mini-can"]
        self.assertEqual(profile["status"], "planned")
        self.assertEqual(profile["hosts"], [])

    def test_catalog_and_profiles_counts_and_visual_mappings(self):
        self.assertEqual(len(self.catalog["units"]), 123)
        self.assertEqual(len(self.profiles), 123)
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(f"'{unit_id}'", mappings)
        self.assertIn("all-123-products", (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8"))

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
