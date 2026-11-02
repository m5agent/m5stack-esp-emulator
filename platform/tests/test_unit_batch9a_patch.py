"""Static contracts for the 0149 Unit batch-9 first-three data planes.

These checks never launch QEMU or firmware. They pin the patch content, the
planned catalog/profile inventory and the visual-mapping registration that the
offline QOM smoke depends on, and they keep the Glass internal-firmware
unresolved items and the RF433T/RF433R driver-gap boundaries visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0149-unit-batch9a.patch"
UNITS = ("glass", "rf433t", "rf433r")


class UnitBatch9aPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_three_data_planes(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CONTROL_UNIT_GLASS", "glass_stream_command", "glass_fb_crc",
                      "rf433_tx_output_changed", "rf433_rx_level_set"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_28_layer_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0149-unit-batch9a.patch", readme)
        self.assertIn("39 layers", readme)
        self.assertIn("0148", readme)

    def test_glass_m5gfx_protocol_and_fixtures(self):
        unit = json.dumps(self.units["glass"], ensure_ascii=False)
        for token in ("M5UnitGLASS", "0x3D", "REG_INDEX", "NOT RUN"):
            self.assertIn(token, unit, token)
        self.assertIn("buzzer-hex", self.units["glass"]["inputs"])
        self.assertIn("button-states", self.units["glass"]["inputs"])

    def test_rf433t_has_driver_gap_and_gpio_observation(self):
        unit = json.dumps(self.units["rf433t"], ensure_ascii=False)
        for token in ("SYN115", "driver-gap", "edge-count", "bit-count", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_rf433r_has_driver_gap_and_input_fixture(self):
        unit = json.dumps(self.units["rf433r"], ensure_ascii=False)
        for token in ("SYN531R", "driver-gap", "input-level", "sample-rate", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_catalog_and_profiles_counts_and_visual_mappings(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(f"'{unit_id}'", mappings)
        self.assertIn("all-160-products", (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8"))

    def test_glass_is_unblocked_and_rf_pair_is_implemented(self):
        g = self.units["glass"]; gp = self.profiles["glass"]
        self.assertEqual(g["model_status"], "partial")
        self.assertEqual(g["runtime"]["status"], "implemented")
        self.assertEqual(gp["status"], "implemented")
        self.assertEqual(gp["hosts"], ["cores3"])
        self.assertIn("virtual_device_evidence", gp)
        for unit_id in ("rf433t", "rf433r"):
            unit = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial")
            self.assertEqual(unit["runtime"]["status"], "implemented")
            self.assertTrue(unit["blocker"])
            self.assertEqual(profile["status"], "implemented")
            self.assertEqual(profile["hosts"], ["cores3"])
            self.assertIn("virtual_device_evidence", profile)


if __name__ == "__main__":
    unittest.main()
