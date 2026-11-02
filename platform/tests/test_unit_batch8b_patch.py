"""Static contracts for the 0148 Unit batch-8 remaining-seven data planes."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0148-unit-batch8b.patch"
UNITS = ("oled", "mini-oled", "glass2", "nbiot-cn", "lora-e220-920", "lorawan-us915", "mic")


class UnitBatch8bPatchTests(unittest.TestCase):
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
        for token in ("CONTROL_UNIT_DISPLAY", "DISP_SH1107", "DISP_SSD1315",
                      "DISP_SSD1309", "lora-e220-920", "comparator-level"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_28_layer_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0148-unit-batch8b.patch", readme)
        self.assertIn("0147", readme)

    def test_display_units_keep_address_ambiguity(self):
        for unit_id, addr in (("oled", "0x3D"), ("mini-oled", "0x3D"), ("glass2", "0x3C")):
            entry = json.dumps(self.units[unit_id], ensure_ascii=False)
            for token in ("0x3C", "0x3D", "UNRESOLVED", "NOT RUN"):
                self.assertIn(token, entry, (unit_id, token))
            self.assertEqual(self.profiles[unit_id]["status"], "implemented")
            self.assertIn(addr.lower(), entry.lower())
        self.assertIn("display-controller", json.dumps(self.units["oled"]))

    def test_mic_is_driver_gap(self):
        entry = json.dumps(self.units["mic"], ensure_ascii=False)
        for token in ("U096", "no public Unit MIC driver", "machine.ADC", "comparator-level", "NOT RUN"):
            self.assertIn(token, entry, token)

    def test_uart_units_only_claim_byte_layer(self):
        for unit_id in ("nbiot-cn", "lora-e220-920", "lorawan-us915"):
            entry = json.dumps(self.units[unit_id], ensure_ascii=False)
            for token in ("responses-hex", "NOT RUN", "PORT.C"):
                self.assertIn(token, entry, (unit_id, token))
        lorawan = json.dumps(self.units["lorawan-us915"], ensure_ascii=False)
        self.assertIn("ASR650x", lorawan)
        lora920 = json.dumps(self.units["lora-e220-920"], ensure_ascii=False)
        self.assertIn("920MHz", lora920)
        self.assertIn("NOT transferable", lora920)

    def test_evidence_status_matches_validation(self):
        for unit_id in UNITS:
            entry = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertEqual(entry["model_status"], "partial", unit_id)
            self.assertEqual(entry["runtime"]["status"], "implemented", unit_id)
            self.assertEqual(profile["status"], "implemented", unit_id)
            self.assertEqual(profile["hosts"], ["cores3"], unit_id)
            evidence = profile["virtual_device_evidence"]
            report = ROOT / evidence["report"]
            self.assertTrue(report.is_file(), unit_id)
            self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(),
                             evidence["report_sha256"], unit_id)
            self.assertIn("0153-unit-batch8-evidence-lcd-read.patch",
                          evidence["patches"], unit_id)
            if unit_id == "lorawan-us915":
                self.assertIn("byte layer", entry["blocker"], unit_id)
                self.assertIn("NOT RUN", entry["blocker"], unit_id)
            self.assertTrue(profile["blocker"], unit_id)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
