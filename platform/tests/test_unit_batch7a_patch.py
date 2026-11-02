"""Static contracts for the 0143 Unit batch-7 first-five data planes.

These checks never launch QEMU or firmware. They pin the patch content, the
planned catalog/profile inventory and the visual-mapping registration that the
offline QOM smoke depends on, and they keep the reused-model boundaries,
the QMP6988 address conflict and the DEFER decision visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0143-unit-batch7a.patch"
IMPLEMENTED = ("mini-tof-90", "hbridge-v11", "cardkb-original", "env-ii")
UNITS = IMPLEMENTED + ("mini-bps-v11",)


class UnitBatch7aPatchTests(unittest.TestCase):
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
        for token in ("US_SHT30", "sht30_measure_command", "sht30_build_response",
                      "sensor_attach_one(u, \"sht30\"", "CONTROL_HBRIDGE", "CONTROL_CARDKB"):
            self.assertIn(token, self.text)

    def test_deferred_mini_bps_v11_is_not_registered(self):
        self.assertNotIn('"mini-bps-v11"', self.text)
        self.assertEqual(self.units["mini-bps-v11"]["model_status"], "planned")

    def test_patch_base_is_the_22_layer_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0143-unit-batch7a.patch", readme)
        self.assertIn("23 layers", readme)
        for token in ("0140", "0141", "0142"):
            self.assertIn(token, readme)

    def test_mini_tof_90_reuses_vl53l0x_and_0x29_conflict(self):
        unit = json.dumps(self.units["mini-tof-90"], ensure_ascii=False)
        for token in ("VL53L0X", "0x29", "tof4m", "90°", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_hbridge_v11_adds_only_vin_current(self):
        unit = json.dumps(self.units["hbridge-v11"], ensure_ascii=False)
        for token in ("U160-V11", "0x30", "vin-current-a", "0x20", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_cardkb_original_version_boundary(self):
        unit = json.dumps(self.units["cardkb-original"], ensure_ascii=False)
        for token in ("MEGA8A", "MEGA328P", "0x5F", "cardkb", "unresolved"):
            self.assertIn(token, unit, token)

    def test_env_ii_dual_slave_sht30_and_bmp280(self):
        unit = json.dumps(self.units["env-ii"], ensure_ascii=False)
        for token in ("SHT30", "0x2C10", "0x44", "BMP280", "0x76", "双从机", "NOT RUN"):
            self.assertIn(token, unit, token)

    def test_mini_bps_v11_address_conflict_is_deferred(self):
        unit = json.dumps(self.units["mini-bps-v11"], ensure_ascii=False)
        for token in ("DEFER", "0x56", "0x70", "unresolved", "NOT RUN"):
            self.assertIn(token, unit, token)
        profile = self.profiles["mini-bps-v11"]
        self.assertEqual(profile["status"], "planned")
        self.assertEqual(profile["hosts"], [])

    def test_catalog_and_profiles_counts_and_visual_mappings(self):
        self.assertEqual(len(self.catalog["units"]), 111)
        self.assertEqual(len(self.profiles), 111)
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(f"'{unit_id}'", mappings)
        self.assertIn("all-111-products", (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8"))

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
