"""Static contracts for the 0139 Unit batch-5 remaining seven data planes."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0139-unit-batch5b.patch"
UNITS = ("pahub-v20", "rtc", "tmos-pir", "neohex", "lora-e220-433", "zigbee", "nbiot2")


class UnitBatch5bPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_registers_all_seven_data_planes(self):
        for unit_id in UNITS:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("CONTROL_PAHUB", "US_RTC8563", "US_STHS34PF80",
                      "lora_respond", "at_idle_cb", "neohex"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_canonical_chain_through_0138(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0139-unit-batch5b.patch", readme)
        self.assertIn("0138", readme)
        self.assertIn("0137", readme)
        self.assertIn("0141-unit-batch5-evidence-fixes.patch", readme)

    def test_pahub_is_mask_only_with_single_bus_blocker(self):
        entry = json.dumps(self.units["pahub-v20"], ensure_ascii=False)
        for token in ("0x70", "PCA9548A", "mask", "0x70 与 env-iii 冲突", "NOT modeled"):
            self.assertIn(token, entry, token)

    def test_rtc_and_tmos_physical_boundaries(self):
        rtc = json.dumps(self.units["rtc"], ensure_ascii=False)
        for token in ("0x51", "BCD", "虚拟时钟", "alarm", "0x51 与 ameter"):
            self.assertIn(token, rtc, token)
        tmos = json.dumps(self.units["tmos-pir"], ensure_ascii=False)
        for token in ("0x5A", "STHS34PF80", "0xD3", "热", "ncir"):
            self.assertIn(token, tmos, token)

    def test_neohex_driver_gap_and_uart_modules_do_not_claim_rf(self):
        neo = json.dumps(self.units["neohex"], ensure_ascii=False)
        for token in ("A045-B", "37", "driver-gap", "WS2812"):
            self.assertIn(token, neo, token)
        for unit_id in ("lora-e220-433", "zigbee", "nbiot2"):
            entry = json.dumps(self.units[unit_id], ensure_ascii=False)
            for token in ("NOT RUN", "PORT.C"):
                self.assertIn(token, entry, token)
            self.assertIn("UART", entry)

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
            for patch in ("0139-unit-batch5b.patch", "0141-unit-batch5-evidence-fixes.patch"):
                self.assertIn(patch, evidence["patches"], unit_id)
            for field in entry["inputs"]:
                self.assertIn(field, profile["inputs"], f"{unit_id}.{field}")
            for field in entry["outputs"]:
                self.assertIn(field, profile["state"], f"{unit_id}.{field}")

    def test_0141_evidence_fixes_pin_rtc_and_tmos_bugs(self):
        fix = ROOT / "patches/qemu-m5stack-peripherals/0141-unit-batch5-evidence-fixes.patch"
        self.assertTrue(fix.is_file())
        text = fix.read_text(encoding="utf-8")
        for token in ("rtc_running", "tmos_presence", "reg == 0x09",
                      "kmeter_tc_c", "digital-level"):
            self.assertIn(token, text)
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0141-unit-batch5-evidence-fixes.patch", readme)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
