"""Static contracts for the 0140 Unit batch-6 first-six data planes."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0140-unit-batch6a.patch"
UNITS = ("mini-scales", "rgb-led-strip-50cm", "op180", "synth", "mini-imu", "env-pro")


class UnitBatch6aPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_six_data_planes(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CONTROL_MINISCALE", "US_MPU6886", "US_BME68X",
                      "rgb-led-strip-50cm", "op180", "synth"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_canonical_chain_through_0139(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0140-unit-batch6a.patch", readme)
        self.assertIn("0139", readme)

    def test_mini_scales_register_map_and_four_way_conflict(self):
        entry = json.dumps(self.units["mini-scales"], ensure_ascii=False)
        for token in ("0x26", "0x10", "0x40", "0x80", "四方", "I2C OR UART"):
            self.assertIn(token, entry, token)

    def test_rmt_and_gpio_products_keep_sku_boundaries(self):
        strip = json.dumps(self.units["rgb-led-strip-50cm"], ensure_ascii=False)
        for token in ("A093", "30", "SK6812", "PORT.B", "unresolved"):
            self.assertIn(token, strip, token)
        op = json.dumps(self.units["op180"], ensure_ascii=False)
        for token in ("U058", "180", "不可", "PORT.B", "NOT RUN"):
            self.assertIn(token, op, token)

    def test_synth_is_tx_only(self):
        synth = json.dumps(self.units["synth"], ensure_ascii=False)
        for token in ("TX-only", "31250", "white=NC", "NOT RUN"):
            self.assertIn(token, synth, token)

    def test_mini_imu_and_env_pro_physical_boundaries(self):
        imu = json.dumps(self.units["mini-imu"], ensure_ascii=False)
        for token in ("0x68", "MPU6886", "0x19", "NOT RUN"):
            self.assertIn(token, imu, token)
        env = json.dumps(self.units["env-pro"], ensure_ascii=False)
        for token in ("0x77", "BME688", "0x61", "补偿", "NOT RUN"):
            self.assertIn(token, env, token)

    def test_inventory_stays_planned_and_does_not_claim_simulated(self):
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "planned", unit_id)
            self.assertEqual(entry["runtime"]["status"], "planned", unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertTrue(profile["blocker"], unit_id)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
