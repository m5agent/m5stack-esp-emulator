"""Static contracts for the 0151 Unit batch-9 remaining data planes/contracts.

These checks never launch QEMU or firmware. They pin the 0151 UART byte-layer
registrations, the planned-only contracts for the five driver-gap products,
catalog/profile/visual counts and the no-guest-evidence boundary.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0151-unit-batch9b.patch"
UART_IMPLEMENTED = ("lorawan-as923", "lorawan-eu868", "audioplayer", "fingerprint2")
PLANNED_ONLY = ("cardkb2", "8servos2-i2c", "bmm350", "ina226-10a", "rollercan")
UNITS = UART_IMPLEMENTED + PLANNED_ONLY


class UnitBatch9bPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_base_is_the_canonical_chain(self):
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0151-unit-batch9b.patch", readme)
        self.assertIn("31st layer", readme)
        self.assertIn("31 layers", readme)
        for token in ("0149", "0150", "0152"):
            self.assertIn(token, readme)

    def test_patch_registers_the_four_uart_byte_planes(self):
        for unit_id in UART_IMPLEMENTED:
            self.assertIn(f'"{unit_id}"', self.text)
        for token in ("m5_unit_gpio.c", "idle-time fixture", "responses-hex",
                      "frames-injected"):
            self.assertIn(token, self.text)
        added = [line for line in self.text.splitlines() if line.startswith("+")]
        for unit_id in PLANNED_ONLY:
            self.assertFalse(any(f'"{unit_id}"' in line for line in added),
                             f"{unit_id} must not be registered as a model")

    def test_catalog_and_profiles_counts(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)

    def test_all_nine_stay_planned_with_empty_hosts(self):
        for unit_id in UNITS:
            unit = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "planned", unit_id)
            self.assertEqual(unit["runtime"]["status"], "planned", unit_id)
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertTrue(unit["blocker"], unit_id)
            self.assertTrue(profile["blocker"], unit_id)

    def test_four_uart_contracts_expose_only_byte_layer_properties(self):
        for unit_id in UART_IMPLEMENTED:
            unit = self.units[unit_id]
            profile = self.profiles[unit_id]
            self.assertEqual(set(unit["runtime"]["properties"]),
                             {"responses-hex", "tx-hex", "frames-sent", "frames-injected"})
            for prop in ("tx-hex", "frames-sent", "frames-injected"):
                self.assertTrue(unit["outputs"][prop]["readOnly"], prop)
            self.assertFalse(unit["inputs"]["responses-hex"]["readOnly"])
            self.assertIn("responses-hex", unit["inputs"])
            self.assertIn("responses-hex", profile["inputs"])
            self.assertNotIn("virtual_device_evidence", profile)
            self.assertFalse((ROOT / "docs/evidence").exists() and any(
                unit_id in path.name for path in (ROOT / "docs/evidence").rglob("*")), unit_id)
            blocker = unit["blocker"]
            self.assertIn("planned", blocker)
            self.assertTrue(any(token in blocker for token in
                                ("NOT RUN", "unresolved", "不可读", "错配")))

    def test_planned_only_contracts_have_no_model_properties(self):
        for unit_id in PLANNED_ONLY:
            unit = self.units[unit_id]
            self.assertEqual(unit["runtime"]["properties"], {}, unit_id)
            self.assertIn("不建 QEMU 模型", unit["blocker"], unit_id)
            self.assertTrue(unit["interface"]["address_7bit"] or
                            unit["interface"]["bus"] in ("i2c", "uart", "gpio"), unit_id)
            self.assertIn(unit_id, self.profiles)

    def test_address_metadata_is_explicit_but_not_guessed(self):
        self.assertEqual(self.units["bmm350"]["interface"]["address_7bit"], [0x14])
        self.assertEqual(self.units["ina226-10a"]["interface"]["address_7bit"], [0x41])
        self.assertEqual(self.units["rollercan"]["interface"]["address_7bit"], [0x64])
        self.assertEqual(self.units["8servos2-i2c"]["interface"]["address_7bit"],
                         list(range(0x25, 0x35)))
        self.assertEqual(self.units["cardkb2"]["interface"]["address_7bit"], [])

    def test_visual_mappings_cover_all_nine(self):
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, mappings)
        test = (ROOT / "platform/tests/test_unit_visual_mappings.mjs").read_text(encoding="utf-8")
        self.assertIn("catalog.units.length, 160", test)
        self.assertIn("all-160-products", test)
        self.assertIn("all-160-products", (ROOT / "platform/tests/test_unit_batch3ab_patch.py").read_text())

    def test_implementation_status_doc_and_no_guest_evidence(self):
        doc = (ROOT / "docs/unit-research/2026-11-03-batch9-impl-status.md").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, doc)
        self.assertIn("不做 guest", doc)
        self.assertIn("planned", doc)
        self.assertFalse((ROOT / "docs/evidence/2026-11-03-unit-batch9").exists())


if __name__ == "__main__":
    unittest.main()
