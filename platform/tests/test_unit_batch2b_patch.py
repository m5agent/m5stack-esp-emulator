"""Static contracts for the 0126 Unit batch-2b data planes.

These checks never launch QEMU or firmware. They pin the patch content that the
offline QOM smoke and the planned catalog/profile inventory depend on, and they
keep the documented address, dual-slave and AC-mains-safety boundaries visible.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0126-unit-batch2b.patch"
UNITS = ("env", "ameter", "extencoder", "ain4-20ma", "acssr", "gesture")


class UnitBatch2bPatchTests(unittest.TestCase):
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
        for token in ("0x5c", "0x76", "0x48", "0x51", "0x59", "0x55", "0x50", "0x73"):
            self.assertIn(token, self.text)
        for token in ("m5_unit_i2c_attach", "US_DHT12", "US_ADS1115",
                      "US_AMETER_EEPROM", "US_AIN420", "US_PAJ7620",
                      "CONTROL_EXTENCODER", "CONTROL_ACSSR"):
            self.assertIn(token, self.text)

    def test_dual_slave_units_expose_two_addresses(self):
        self.assertIn("m5_unit_i2c_attach", self.text)
        for child in ("dht12", "bmp280", "ads1115", "eeprom"):
            self.assertIn(f'"{child}"', self.text)
        self.assertEqual(self.units["env"]["interface"]["address_7bit"], [0x5C, 0x76])
        self.assertEqual(self.units["ameter"]["interface"]["address_7bit"], [0x48, 0x51])
        for unit_id in ("env", "ameter"):
            self.assertIn("two device-local slaves", json.dumps(self.units[unit_id], ensure_ascii=False))

    def test_acssr_mains_safety_is_an_explicit_blocker(self):
        entry = json.dumps(self.units["acssr"], ensure_ascii=False)
        self.assertIn("24–480V", entry)
        self.assertIn("AC 市电", entry)
        self.assertIn("NOT RUN", entry)
        self.assertEqual(self.units["acssr"]["runtime"]["status"], "implemented")
        self.assertEqual(self.units["acssr"]["model_status"], "partial")
        self.assertIn("不是 AC 市电开关模型", entry)

    def test_documented_conflicts_and_unresolved_tokens_survive(self):
        env = json.dumps(self.units["env"], ensure_ascii=False)
        self.assertIn("ENV-II/III/IV", env)
        self.assertIn("0x5C", env)
        ameter = json.dumps(self.units["ameter"], ensure_ascii=False)
        for token in ("0x48", "0x51", "出厂校准", "adc-v11"):
            self.assertIn(token, ameter)
        extencoder = json.dumps(self.units["extencoder"], ensure_ascii=False)
        for token in ("0x59", "渲染损坏", "AB/ABZ"):
            self.assertIn(token, extencoder)
        ain = json.dumps(self.units["ain4-20ma"], ensure_ascii=False)
        for token in ("0x55", "0xF0", "raw16", "STM32G030"):
            self.assertIn(token, ain)
        gesture = json.dumps(self.units["gesture"], ensure_ascii=False)
        for token in ("0x73", "PAJ7620", "219"):
            self.assertIn(token, gesture)

    def test_guest_evidence_backed_upgrade_stays_partial(self):
        hosts = {"env": "atoms3r", "ameter": "sticks3", "extencoder": "cores3",
                 "ain4-20ma": "stopwatch", "acssr": "atoms3r", "gesture": "sticks3"}
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
            self.assertIn("0126-unit-batch2b.patch", evidence["patches"], unit_id)
            if unit_id == "ameter":
                self.assertIn("0128-unit-ameter-eeprom-layout.patch", evidence["patches"], unit_id)
            if unit_id in {"extencoder", "acssr"}:
                self.assertIn("0129-unit-batch2b-write-offset.patch", evidence["patches"], unit_id)

    def test_patch_is_numbered_on_the_documented_base_and_has_no_guest_claim(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0126-unit-batch2b.patch", readme)
        self.assertIn("0128-unit-ameter-eeprom-layout.patch", readme)
        self.assertIn("0129-unit-batch2b-write-offset.patch", readme)
        self.assertIn("0125", readme)
        for patch in ("0128-unit-ameter-eeprom-layout.patch", "0129-unit-batch2b-write-offset.patch"):
            self.assertTrue((ROOT / "patches/qemu-m5stack-peripherals" / patch).is_file(), patch)
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
