"""Static contracts for the 0158/0160 Unit batch-12a driver-gap data planes + evidence."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0158-unit-batch12a.patch"
UNITS = ("byteswitch", "bytebutton", "step16", "timerpwr", "mq",
         "8servos2-i2c", "cardkb2")


class UnitBatch12aPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_seven_register_file_kinds(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CONTROL_BYTEUNIT", "CONTROL_STEP16", "CONTROL_TIMERPWR",
                      "CONTROL_MQ", "CONTROL_SERVOS8V2", "CONTROL_CARDKB2"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_37_layer_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0158-unit-batch12a.patch", readme)
        self.assertIn("0156", readme)

    def test_byteunit_register_layout_is_shared_and_addresses_explicit(self):
        for unit_id, addr in (("byteswitch", 0x46), ("bytebutton", 0x47)):
            unit = self.units[unit_id]
            self.assertEqual(unit["interface"]["address_7bit"], [addr])
            props = set(unit["runtime"]["properties"])
            for name in ("state-bitmap", "brightness", "led-mode", "rgb-hex",
                         "irq-enable", "irq-count", "save-count", "firmware-version"):
                self.assertIn(name, props, unit_id)
            self.assertEqual(self.profiles[unit_id]["status"], "implemented")

    def test_register_maps_are_documented_evidence_contracts(self):
        expected = {
            "step16": {"position", "led-config", "led-brightness", "direction",
                       "rgb", "rgb-power", "rgb-brightness"},
            "timerpwr": {"schedule-on", "schedule-off", "usb-v", "usb-i",
                         "grove-v", "grove-i", "battery-mv", "battery-i-ma",
                         "charging", "grove-output", "backlight", "trigger-bits",
                         "cycle", "power-state"},
            "mq": {"sensor-mv", "ref-mv", "ntc-mv", "ntc-ohm", "valid-tags",
                   "mq-mode", "led", "heat-high", "heat-low", "adc8", "adc12",
                   "valid-raw"},
            "8servos2-i2c": {"rotary", "channel-modes-hex", "servo-angles-hex",
                             "adc-values-hex", "rgb-hex", "pwm-hex",
                             "timer-freq-hex", "uid-hex", "input-levels-hex",
                             "sys-ref-mv", "sys-grove-mv", "sys-dc-mv", "sys-ma"},
            "cardkb2": {"key-code", "mode", "key-events"},
        }
        for unit_id, names in expected.items():
            props = set(self.units[unit_id]["runtime"]["properties"])
            self.assertTrue(names <= props, unit_id)
            self.assertEqual(self.profiles[unit_id]["status"], "implemented", unit_id)

    def test_explicit_conflicts_and_boundaries(self):
        self.assertEqual(self.units["8servos2-i2c"]["interface"]["address_7bit"],
                         list(range(0x25, 0x35)))
        self.assertEqual(self.units["cardkb2"]["interface"]["address_7bit"], [0x5F])
        for unit_id, token in (("mq", "get_valid_tags"),
                               ("8servos2-i2c", "0x26"),
                               ("cardkb2", "PORT.CUSTOM"),
                               ("step16", "0x48"),
                               ("timerpwr", "0x56")):
            entry = json.dumps(self.units[unit_id], ensure_ascii=False)
            self.assertIn(token, entry, (unit_id, token))
            self.assertIn("NOT RUN", entry, unit_id)

    def test_all_seven_have_raw_i2c_guest_evidence(self):
        import hashlib
        for unit_id in UNITS:
            unit = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial", unit_id)
            self.assertEqual(unit["runtime"]["status"], "implemented", unit_id)
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            self.assertTrue(unit["blocker"], unit_id)
            self.assertIn("driver-gap", unit["blocker"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(),
                             evidence["report_sha256"], unit_id)
            self.assertIn("0158-unit-batch12a.patch", evidence["patches"], unit_id)
            self.assertIn("0160-unit-batch12a-evidence-fixes.patch", evidence["patches"], unit_id)
            self.assertIn("driver-gap", evidence["firmware_flavor"], unit_id)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
