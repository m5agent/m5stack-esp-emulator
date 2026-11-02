"""Static contracts for the 0142 Unit batch-6 remaining six data planes."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0142-unit-batch6b.patch"
UNITS = ("unit-id", "thermal2", "qrcode", "uwb", "dmx", "finger")


class UnitBatch6bPatchTests(unittest.TestCase):
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
        for token in ("US_ATECC608B", "US_THERMAL2", "US_QRCODE"):
            self.assertIn(token, self.text)

    def test_patch_base_is_the_canonical_chain_through_0141(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0142-unit-batch6b.patch", readme)
        self.assertIn("0141", readme)

    def test_unit_id_uses_only_fixed_test_vectors(self):
        entry = json.dumps(self.units["unit-id"], ensure_ascii=False)
        for token in ("0x35", "ATECC608B", "test vectors", "NO real keys", "NOT RUN"):
            self.assertIn(token, entry, token)
        self.assertIn("test vectors", self.text.lower())

    def test_thermal2_address_ambiguity_and_array(self):
        entry = json.dumps(self.units["thermal2"], ensure_ascii=False)
        for token in ("0x32", "0x33", "768", "MLX90640", "ambiguity"):
            self.assertIn(token, entry, token)

    def test_qrcode_16bit_window_and_uart_responders(self):
        qr = json.dumps(self.units["qrcode"], ensure_ascii=False)
        for token in ("0x21", "0x1000", "16-bit", "I2C/UART"):
            self.assertIn(token, qr, token)
        for unit_id in ("uwb", "dmx", "finger"):
            entry = json.dumps(self.units[unit_id], ensure_ascii=False)
            for token in ("PORT.C", "NOT RUN", "UART"):
                self.assertIn(token, entry, token)

    def test_inventory_evidence_status_matches_validation(self):
        for unit_id in UNITS:
            entry = self.units[unit_id]
            profile = self.profiles[unit_id]
            if unit_id == "unit-id":
                # Blocked by the ATECC wake-to-address-0 harness requirement.
                self.assertEqual(entry["model_status"], "planned", unit_id)
                self.assertEqual(entry["runtime"]["status"], "planned", unit_id)
                self.assertEqual(profile["status"], "planned", unit_id)
                self.assertEqual(profile["hosts"], [], unit_id)
            else:
                self.assertEqual(entry["model_status"], "partial", unit_id)
                self.assertEqual(entry["runtime"]["status"], "implemented", unit_id)
                self.assertEqual(profile["status"], "implemented", unit_id)
                self.assertEqual(profile["hosts"], ["cores3"], unit_id)
                evidence = profile["virtual_device_evidence"]
                report = ROOT / evidence["report"]
                self.assertTrue(report.is_file(), unit_id)
                self.assertEqual(
                    hashlib.sha256(report.read_bytes()).hexdigest(),
                    evidence["report_sha256"], unit_id)
                self.assertIn("0142-unit-batch6b.patch", evidence["patches"], unit_id)
                self.assertIn("0147-unit-batch6b-evidence-fixes.patch", evidence["patches"], unit_id)
            self.assertTrue(profile["blocker"], unit_id)

    def test_patch_has_no_guest_claim(self):
        self.assertIn("Offline QOM smoke", self.text)
        self.assertNotIn("guest PASS", self.text)


if __name__ == "__main__":
    unittest.main()
