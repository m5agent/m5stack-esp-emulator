"""Static contracts for the 0136 Unit batch-4 C data planes.

These checks never launch QEMU or firmware. They pin the patch content that
the offline QOM smoke and the planned catalog/profile inventory depend on, and
they keep the AC-mains/RF/HX711/driver-boundary unresolved items visible.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0136-unit-batch4c.patch"
UNITS = ("weight", "bldc-driver", "ac-measure", "dds", "gps", "uhf-rfid")


class UnitBatch4cPatchTests(unittest.TestCase):
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
        for token in ("US_ACMEASURE", "CONTROL_BLDC", "CONTROL_DDS",
                      "hx_pad_event", "gps_timer_cb", "uhf_inject_response"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_0129_plus_0131_plus_0134_tree(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0136-unit-batch4c.patch", readme)
        self.assertIn("0134", readme)
        self.assertIn("0131", readme)
        self.assertIn("0130", readme)
        self.assertIn("0138-unit-batch4-evidence-fixes.patch", readme)

    def test_weight_hx711_and_page_faq_conflict(self):
        weight = json.dumps(self.units["weight"], ensure_ascii=False)
        for token in ("HX711", "24-bit", "FAQ", "I2C", "weight-i2c", "NOT RUN"):
            self.assertIn(token, weight, token)

    def test_bldc_motor_boundary_and_pid_size(self):
        bldc = json.dumps(self.units["bldc-driver"], ensure_ascii=False)
        for token in ("0x65", "DRV11873", "PID", "12B", "失速", "NOT RUN"):
            self.assertIn(token, bldc, token)

    def test_ac_measure_is_measurement_input_not_a_switch(self):
        ac = json.dumps(self.units["ac-measure"], ensure_ascii=False)
        for token in ("100-240V", "测量输入", "绝不是可切换负载", "NOT RUN", "STM32G030"):
            self.assertIn(token, ac, token)

    def test_dds_and_uart_units_keep_their_boundaries(self):
        dds = json.dumps(self.units["dds"], ensure_ascii=False)
        for token in ("AD9833", "28-bit", "11-bit", "0x31"):
            self.assertIn(token, dds, token)
        gps = json.dumps(self.units["gps"], ensure_ascii=False)
        for token in ("NMEA", "checksum", "EOL"):
            self.assertIn(token, gps, token)
        uhf = json.dumps(self.units["uhf-rfid"], ensure_ascii=False)
        for token in ("JRD4035", "Gen2", "kill/lock", "绝不宣称真实标签"):
            self.assertIn(token, uhf, token)

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
            for patch in ("0136-unit-batch4c.patch", "0138-unit-batch4-evidence-fixes.patch"):
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

    def test_evidence_fix_and_measurement_boundaries_are_visible(self):
        weight = json.dumps(self.units["weight"], ensure_ascii=False)
        self.assertIn("0138", weight)
        self.assertIn("deferred", weight)
        ac = json.dumps(self.units["ac-measure"], ensure_ascii=False)
        self.assertIn("MEASUREMENT INPUT", ac)
        self.assertIn("0138", ac)
        self.assertIn("ASCII", ac)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
