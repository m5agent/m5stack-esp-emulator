"""Static contracts for the 0134 Unit batch-4 A+B data planes.

These checks never launch QEMU or firmware. They pin the patch content that
the offline QOM smoke and the planned catalog/profile inventory depend on, and
they keep the laser/AC-mains/RF/driver-boundary unresolved items visible.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0134-unit-batch4ab.patch"
UNITS = ("rs485-iso", "laser-tx", "co2l", "neco", "midi", "tof4m")


class UnitBatch4abPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.lowered = cls.text.lower()
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_six_data_planes(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("US_VL53L1X", "rs485-iso", "laser-tx", "neco", "midi", "co2l"):
            self.assertIn(token, self.text)
        for token in ("0x29", "0x62", "0x010f", "rgb[128]", "128"):
            self.assertIn(token, self.lowered, token)

    def test_patch_base_is_0129_plus_0131(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0134-unit-batch4ab.patch", readme)
        self.assertIn("0131", readme)
        self.assertIn("0130", readme)
        entry = json.dumps(self.units["rs485-iso"], ensure_ascii=False)
        self.assertIn("0134", entry)
        self.assertIn("Virtual-device guest evidence", entry)

    def test_laser_eye_safety_and_co2l_conflict_are_blockers(self):
        laser = json.dumps(self.units["laser-tx"], ensure_ascii=False)
        for token in ("激光", "人眼", "NOT RUN", "不可"):
            self.assertIn(token, laser, token)
        co2l = json.dumps(self.units["co2l"], ensure_ascii=False)
        for token in ("SCD40", "SCD41", "0x62", "buf[1]", "chip-id"):
            self.assertIn(token, co2l, token)

    def test_neco_rgb_limit_and_led_count_conflict(self):
        self.assertIn("128", self.text)
        neco = json.dumps(self.units["neco"], ensure_ascii=False)
        for token in ("35", "70", "WS2812", "级联", "RMT"):
            self.assertIn(token, neco, token)

    def test_midi_baud_and_port_conflict(self):
        midi = json.dumps(self.units["midi"], ensure_ascii=False)
        for token in ("31250", "31520", "SAM2695", "PORT.C", "音频"):
            self.assertIn(token, midi, token)

    def test_tof4m_16bit_register_and_three_way_conflict(self):
        tof = json.dumps(self.units["tof4m"], ensure_ascii=False)
        for token in ("VL53L1", "16-bit", "0x29", "tof", "color"):
            self.assertIn(token, tof, token)
        self.assertIn("US_VL53L1X", self.text)
        self.assertIn("0x0096", self.text.lower())

    def test_guest_evidence_backed_upgrade_stays_partial(self):
        for unit_id in UNITS:
            entry = self.units[unit_id]
            self.assertEqual(entry["model_status"], "partial", unit_id)
            self.assertEqual(entry["runtime"]["status"], "implemented", unit_id)
            self.assertNotEqual(entry["model_status"], "simulated", unit_id)
            self.assertTrue(entry["runtime"]["blocker"], unit_id)
            profile = self.profiles[unit_id]
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            self.assertTrue(profile["blocker"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(evidence["report_sha256"],
                             hashlib.sha256(report.read_bytes()).hexdigest(), unit_id)
            for patch in ("0134-unit-batch4ab.patch", "0138-unit-batch4-evidence-fixes.patch"):
                self.assertIn(patch, evidence["patches"], unit_id)
            for field in entry["inputs"]:
                self.assertIn(field, profile["inputs"], f"{unit_id}.{field}")
            for field in entry["outputs"]:
                self.assertIn(field, profile["state"], f"{unit_id}.{field}")

    def test_0138_evidence_fixes_pin_ac_and_weight_bugs(self):
        fix = (ROOT / "patches/qemu-m5stack-peripherals/0138-unit-batch4-evidence-fixes.patch")
        self.assertTrue(fix.is_file())
        text = fix.read_text(encoding="utf-8")
        for token in ("ac_fixed_scaled", "esp32_gpio_set_input_deferred",
                      "hx_pad_event"):
            self.assertIn(token, text)
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0138-unit-batch4-evidence-fixes.patch", readme)
        evidence = (ROOT / "docs/evidence/2026-11-02-unit-batch4/README.md").read_text(encoding="utf-8")
        self.assertIn("0138-unit-batch4-evidence-fixes.patch", evidence)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
