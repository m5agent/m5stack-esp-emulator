"""Static contracts for the 0131 Unit batch-3 C data planes.

These checks never launch QEMU or firmware. They pin the patch content that the
offline QOM smoke and the planned catalog/profile inventory depend on, and they
keep the SHT4x/SCD4x/PbHub/Ultrasonic unresolved boundaries visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0131-unit-batch3c.patch"
UNITS = ("env-iv", "co2", "pbhub", "ultrasonic-io")


class UnitBatch3cPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_four_data_planes(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        lowered = self.text.lower()
        for token in ("0x44", "0x76", "0x62", "0x61", "0x40", "0x50", "0x60",
                      "0x70", "0x80", "0xa0"):
            self.assertIn(token, lowered, token)
        for token in ("US_SHT4X", "US_SCD40", "CONTROL_PBHUB",
                      "ultrasonic-io", "sensor_attach_one", "0xfa"):
            self.assertIn(token, self.text)

    def test_env_iv_is_a_dual_slave_unit(self):
        self.assertEqual(self.units["env-iv"]["interface"]["address_7bit"], [0x44, 0x76])
        for child in ("sht4x", "bmp280"):
            self.assertIn(f'"{child}"', self.text)
        entry = json.dumps(self.units["env-iv"], ensure_ascii=False)
        for token in ("master", "sht4x", "0x44", "env-iii", "type=4", "NOT RUN"):
            self.assertIn(token, entry, token)

    def test_co2_keeps_scd40_scd41_and_driver_rewrite_unresolved(self):
        entry = json.dumps(self.units["co2"], ensure_ascii=False)
        for token in ("SCD40", "SCD41", "asyncio", "buf[1]", "buf[4]", "5s"):
            self.assertIn(token, entry, token)
        for token in ("0xe4b8", "0xec05", "crc"):
            self.assertIn(token, self.text.lower())

    def test_pbhub_single_command_space_and_mcu_conflict(self):
        entry = json.dumps(self.units["pbhub"], ensure_ascii=False)
        for token in ("0x61", "channel_base|offset", "GRB", "MEGA328",
                      "STM32F030F4P6", "0xFA", "嵌套"):
            self.assertIn(token, entry, token)
        self.assertIn("256 字节命令空间", entry)
        self.assertEqual(self.units["pbhub"]["interface"]["address_7bit"], [0x61])

    def test_ultrasonic_timeout_and_pinmap_conflict(self):
        entry = json.dumps(self.units["ultrasonic-io"], ensure_ascii=False)
        for token in ("time_pulse_us", "SDA/SCL", "distance-mm", "超时",
                      "声学", "NOT RUN"):
            self.assertIn(token, entry, token)
        self.assertIn("echo-pulse-us", entry)
        self.assertIn("timeout", self.text)

    def test_inventory_stays_planned_and_does_not_claim_simulated(self):
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "planned", unit_id)
            self.assertEqual(entry["runtime"]["status"], "planned", unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertTrue(profile["blocker"], unit_id)

    def test_patch_is_numbered_on_the_documented_base_and_has_no_guest_claim(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0131-unit-batch3c.patch", readme)
        self.assertIn("0129", readme)
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
