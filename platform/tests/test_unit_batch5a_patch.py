"""Static contracts for the 0137 Unit batch-5 first-five data planes.

These checks never launch QEMU or firmware. They pin the patch content that
the offline QOM smoke and the planned catalog/profile inventory depend on, and
they keep the PORT.B / polarity / firmware-version / thermocouple boundaries
visible.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0137-unit-batch5a.patch"
UNITS = ("pbhub-v11", "op90", "rgb-led-10cm", "8angle", "kmeter-iso-v11")


class UnitBatch5aPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_five_data_planes(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("US_ANGLE8", "US_KMETER", "angle8_any_get", "kmeter_ascii",
                      "pbhub-v11", "op90", "rgb-led-10cm"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_documented_through_0136_tree(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0137-unit-batch5a.patch", readme)
        self.assertIn("0136", readme)
        self.assertIn("0134", readme)
        self.assertIn("0141-unit-batch5-evidence-fixes.patch", readme)

    def test_pbhub_v11_reuses_single_0x61_command_space(self):
        entry = json.dumps(self.units["pbhub-v11"], ensure_ascii=False)
        for token in ("0x61", "0x40", "0x50", "0x60", "0x70", "0x80", "0xA0",
                      "STM32F030F4P6", "v2", "pbhub"):
            self.assertIn(token, entry, token)
        self.assertEqual(self.units["pbhub-v11"]["interface"]["address_7bit"], [0x61])

    def test_op90_and_rgb_led_port_b_boundaries(self):
        op90 = json.dumps(self.units["op90"], ensure_ascii=False)
        for token in ("PORT.B", "unresolved", "NOT RUN", "U057"):
            self.assertIn(token, op90, token)
        rgb = json.dumps(self.units["rgb-led-10cm"], ensure_ascii=False)
        for token in ("A035", "15", "SK6812", "RMT", "PORT.B"):
            self.assertIn(token, rgb, token)

    def test_8angle_register_map_and_kmeter_physical_boundary(self):
        angle = json.dumps(self.units["8angle"], ensure_ascii=False)
        for token in ("0x43", "8x ADC12", "ADC8", "9x", "SK6812", "U154"):
            self.assertIn(token, angle, token)
        kmeter = json.dumps(self.units["kmeter-iso-v11"], ensure_ascii=False)
        for token in ("0x66", "MAX31855", "-200", "1350", "NOT RUN", "隔离"):
            self.assertIn(token, kmeter, token)

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
            for patch in ("0137-unit-batch5a.patch", "0141-unit-batch5-evidence-fixes.patch"):
                self.assertIn(patch, evidence["patches"], unit_id)
            for field in entry["inputs"]:
                self.assertIn(field, profile["inputs"], f"{unit_id}.{field}")
            for field in entry["outputs"]:
                self.assertIn(field, profile["state"], f"{unit_id}.{field}")

    def test_0141_evidence_fixes_pin_batch5_bugs(self):
        fix = ROOT / "patches/qemu-m5stack-peripherals/0141-unit-batch5-evidence-fixes.patch"
        self.assertTrue(fix.is_file())
        text = fix.read_text(encoding="utf-8")
        for token in ("digital-level", "rtc_running", "kmeter_tc_c",
                      "tmos_presence", "tmos_shock"):
            self.assertIn(token, text)
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0141-unit-batch5-evidence-fixes.patch", readme)
        evidence = (ROOT / "docs/evidence/2026-11-02-unit-batch5/README.md").read_text(encoding="utf-8")
        self.assertIn("0141-unit-batch5-evidence-fixes.patch", evidence)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
