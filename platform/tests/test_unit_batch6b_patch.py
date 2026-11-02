"""Static contracts for the 0142 Unit batch-6 remaining six data planes."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0142-unit-batch6b.patch"
UNITS = ("unit-id", "thermal2", "qrcode", "uwb", "dmx", "finger")


class UnitBatch6bPatchTests(unittest.TestCase):
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
        for token in ("US_ATECC608B", "US_THERMAL2", "US_QRCODE"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_canonical_chain_through_0141(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0142-unit-batch6b.patch", readme)
        self.assertIn("0141", readme)

    def test_unit_id_uses_only_fixed_test_vectors(self):
        entry = json.dumps(self.units["unit-id"], ensure_ascii=False)
        for token in ("0x35", "ATECC608B", "测试向量", "私钥", "NOT RUN"):
            self.assertIn(token, entry, token)
        self.assertIn("test vectors", self.text.lower())

    def test_thermal2_address_ambiguity_and_array(self):
        entry = json.dumps(self.units["thermal2"], ensure_ascii=False)
        for token in ("0x32", "0x33", "768", "MLX90640", "二义"):
            self.assertIn(token, entry, token)

    def test_qrcode_16bit_window_and_uart_responders(self):
        qr = json.dumps(self.units["qrcode"], ensure_ascii=False)
        for token in ("0x21", "0x1000", "16-bit", "I2C/UART"):
            self.assertIn(token, qr, token)
        for unit_id in ("uwb", "dmx", "finger"):
            entry = json.dumps(self.units[unit_id], ensure_ascii=False)
            for token in ("PORT.C", "NOT RUN", "UART"):
                self.assertIn(token, entry, token)

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
