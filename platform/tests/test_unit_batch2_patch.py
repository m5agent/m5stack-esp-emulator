"""Static contracts for the 0125 second-batch Unit data planes.

These checks never launch QEMU or firmware. They pin the patch content that the
offline QOM smoke and the planned catalog/profile inventory depend on, and they
keep the documented address/version conflicts and unresolved items visible.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0125-unit-batch2.patch"
UNITS = ("joystick", "watering", "fader", "dac", "bps", "adc-v11")


class UnitBatch2PatchTests(unittest.TestCase):
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
        for token in ("0x52", "0x60", "0x76", "0x48"):
            self.assertIn(token, self.text)
        for token in ("CONTROL_DAC", "US_ADS1110", "US_BMP280",
                      "watering_output_changed", "leds = 14"):
            self.assertIn(token, self.text)

    def test_joystick_reuses_existing_snapshot_and_documents_conflict(self):
        self.assertIn("CONTROL_JOYSTICK", self.text)
        entry = json.dumps(self.units["joystick"], ensure_ascii=False)
        for token in ("0x52", "joystick-v11", "polarity", "NOT RUN"):
            self.assertIn(token, entry)
        self.assertEqual(self.units["joystick"]["runtime"]["status"], "implemented")

    def test_watering_and_fader_dual_endpoint_boundaries(self):
        for token in ("pump-level", "pump-transitions", "adc-samples",
                      "led-rgb", "led-frames", "incomplete-frames"):
            self.assertIn(token, self.text)
        for unit_id in ("watering", "fader"):
            self.assertIn("analog-mv", self.units[unit_id]["runtime"]["properties"])
        fader = json.dumps(self.units["fader"], ensure_ascii=False)
        for token in ("set_brightness", "driver SHA", "NOT RUN"):
            self.assertIn(token, fader)
        watering = json.dumps(self.units["watering"], ensure_ascii=False)
        for token in ("PUMP_EN", "pump electrical", "NOT RUN", "unresolved"):
            self.assertIn(token, watering)

    def test_dac_bps_adc_v11_register_boundaries(self):
        dac = json.dumps(self.units["dac"], ensure_ascii=False)
        for token in ("0x60", "EEPROM", "vdd=5.0V", "UNRESOLVED"):
            self.assertIn(token, dac)
        bps = json.dumps(self.units["bps"], ensure_ascii=False)
        for token in ("0x76", "0x58", "QMP6988", "calibration", "NOT modeled"):
            self.assertIn(token, bps)
        adc = json.dumps(self.units["adc-v11"], ensure_ascii=False)
        for token in ("0x48", "ADS1110", "15/30/60/240 SPS",
                      "ADS1100 compatibility is NOT verified", "divider tolerance"):
            self.assertIn(token, adc)
        for unit_id in ("dac", "bps", "adc-v11"):
            self.assertEqual(self.units[unit_id]["runtime"]["status"], "implemented", unit_id)

    def test_guest_evidence_backed_upgrade_stays_partial(self):
        hosts = {"joystick": "cores3", "watering": "atoms3r", "fader": "atoms3r",
                 "dac": "cores3", "bps": "sticks3", "adc-v11": "stopwatch"}
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "partial", unit_id)
            self.assertEqual(entry["runtime"]["status"], "implemented", unit_id)
            self.assertNotEqual(entry["model_status"], "simulated", unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], [hosts[unit_id]], unit_id)
            self.assertTrue(profile["blocker"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(evidence["report_sha256"],
                             hashlib.sha256(report.read_bytes()).hexdigest(), unit_id)
            self.assertIn("0125-unit-batch2.patch", evidence["patches"], unit_id)
            if unit_id == "dac":
                self.assertIn("0127-unit-dac-fast-mode-write.patch", evidence["patches"], unit_id)

    def test_patch_is_numbered_on_the_documented_base_and_has_no_guest_claim(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0125-unit-batch2.patch", readme)
        self.assertIn("0124", readme)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
