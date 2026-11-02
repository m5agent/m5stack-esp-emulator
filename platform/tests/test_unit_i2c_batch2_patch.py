"""Static contracts for the 0119 B-class external Unit I2C data planes.

These checks never launch QEMU or firmware. They pin the patch content that the
offline QOM smoke and the catalog/profile inventory depend on, and they keep
the documented protocol conflicts visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0119-unit-i2c-batch2.patch"
UNITS = ("dlight", "accel", "4relay", "weight-i2c")


class UnitI2cBatch2PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_four_transaction_models(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("0x23", "0x53", "0x26"):
            self.assertIn(token, self.text)
        self.assertIn("m5_unit_i2c_sensors.c", self.text)
        self.assertIn("m5_unit_i2c_controls.c", self.text)

    def test_dlight_conversion_happens_inside_the_model_only(self):
        self.assertIn("dlight_complete", self.text)
        self.assertIn("s->values[0] * 1.2 * s->dlight_sensitivity", self.text)
        self.assertIn("be16(s->response", self.text)
        self.assertIn("MTreg", self.text)
        self.assertNotIn("return 400", self.text)
        self.assertFalse(any("illuminance-lx" in key for key in self.units["dlight"]["outputs"]))

    def test_accel_does_not_guess_devid_and_keeps_pointer_semantics(self):
        self.assertIn("DEVID", self.text)
        self.assertIn("never reads", self.text)
        self.assertIn("0xff", self.text.lower())
        self.assertNotIn("0xe5", self.text.lower())
        self.assertIn("read-to-clear", self.text.lower())
        self.assertIn("accel-x-g", self.text)
        self.assertIn("int-source", self.text)

    def test_4relay_uses_driver_bit_order_and_documents_page_conflict(self):
        self.assertIn("RELAY1..4=bit0..3", self.text)
        self.assertIn("LED1..4=bit4..7", self.text)
        entry = self.units["4relay"]
        text = json.dumps(entry, ensure_ascii=False)
        self.assertIn("product-page", text)
        self.assertIn("reverse", text)
        self.assertIn("driver-compatible bit order", text)
        for channel in range(1, 5):
            self.assertIn(f"relay-{channel}-level", self.profiles["4relay"]["state"])
            self.assertIn(f"led-{channel}-level", self.profiles["4relay"]["state"])
        self.assertIn("mode", self.profiles["4relay"]["state"])

    def test_weight_i2c_address_and_semantic_conflicts_are_explicit(self):
        self.assertIn("weight*100", self.text)
        self.assertIn("0x60", self.text)
        for unit_id in ("4relay", "weight-i2c"):
            entry = self.units[unit_id]
            text = json.dumps(entry, ensure_ascii=False)
            self.assertIn("0x26", text)
            self.assertIn("weight-i2c", text)
            self.assertIn("4relay", text)
        for token in ("calibration", "unresolved", "NOT RUN"):
            self.assertIn(token, json.dumps(self.units["weight-i2c"], ensure_ascii=False))

    def test_no_premature_runtime_upgrade(self):
        allowed = {"planned", "partial", "unsupported"}
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "planned", unit_id)
            self.assertIn(entry["runtime"]["status"], allowed, unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertTrue(profile["blocker"])

    def test_patch_is_numbered_on_the_documented_base_and_has_no_guest_claim(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0119-unit-i2c-batch2.patch", readme)
        self.assertRegex(self.text, r"(?m)^Subject: .*B-class external Unit I2C models")
        self.assertNotIn("PASS", self.text.replace("PASS on", ""))


if __name__ == "__main__":
    unittest.main()
