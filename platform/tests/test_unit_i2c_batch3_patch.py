"""Static contracts for the 0123 C-class external Unit I2C data planes.

These checks never launch QEMU or firmware. They pin the patch content that the
offline QOM smoke and the planned catalog/profile inventory depend on, and they
keep the documented address conflicts and protocol-unresolved items visible.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0123-unit-i2c-batch3.patch"
UNITS = ("ncir2", "extio2", "hbridge")


class UnitI2cBatch3PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_three_transaction_models(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("0x5a", "0x45", "0x20"):
            self.assertIn(token, self.text)
        self.assertIn("m5_unit_i2c_controls.c", self.text)

    def test_ncir2_encoding_and_alarm_boundaries_are_explicit(self):
        self.assertIn("ncir2_object_c", self.text)
        self.assertIn("ncir2_chip_c", self.text)
        self.assertIn("clamp_i16", self.text)
        self.assertIn("0x5a", self.text.lower())
        entry = json.dumps(self.units["ncir2"], ensure_ascii=False)
        for token in ("0x5A", "327.67", "alarm state machine", "NOT RUN"):
            self.assertIn(token, entry)
        self.assertIn("object-c", self.profiles["ncir2"]["inputs"])
        self.assertIn("rgb-led", self.profiles["ncir2"]["state"])
        self.assertIn("buzzer-on", self.profiles["ncir2"]["state"])

    def test_extio2_channels_and_unresolved_units_are_explicit(self):
        for token in ("extio2_inputs", "extio2_adc_mv", "extio_adc12", "extio_adc8"):
            self.assertIn(token, self.text)
        entry = json.dumps(self.units["extio2"], ensure_ascii=False)
        for token in ("Protocol v1/v3", "full-scale", "RGB", "IAP", "0x90/0xA0"):
            self.assertIn(token, entry)
        for field in ("input-levels", "adc-mv", "fw-version", "modes",
                      "output-levels", "servo-angles", "servo-pulses", "rgb-leds"):
            self.assertIn(field, self.units["extio2"]["runtime"]["properties"])

    def test_hbridge_registers_and_v11_boundary_are_explicit(self):
        for token in ("hbridge_pwm16", "hbridge_adc_mv", "hbridge_vin_a"):
            self.assertIn(token, self.text)
        self.assertIn("0x2f", self.text.lower())
        entry = json.dumps(self.units["hbridge"], ensure_ascii=False)
        for token in ("0x30", "v1.1", "RZ7899", "NOT RUN"):
            self.assertIn(token, entry)
        for field in ("direction", "pwm-duty-pct", "pwm-frequency-hz"):
            self.assertIn(field, self.units["hbridge"]["runtime"]["properties"])

    def test_inventory_stays_planned_and_does_not_claim_simulated(self):
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "planned", unit_id)
            self.assertEqual(entry["runtime"]["status"], "planned", unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertTrue(profile["blocker"], unit_id)
            self.assertNotEqual(entry["model_status"], "simulated", unit_id)

    def test_patch_has_no_guest_claim_and_numbering_is_documented(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0123-unit-i2c-batch3.patch", readme)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
