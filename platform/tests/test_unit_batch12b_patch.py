"""Static contracts for the 0158 Unit batch-12b driver-gap model layer.

These checks never launch QEMU or firmware. They pin the three model areas
(BMM350/INA226 I2C sensors, Roller family I2C register file, Chain/Cat1 UART
responders), the ten partial-but-planned catalog/profile contracts, the
explicit address conflicts and the no-guest-evidence boundary.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0159-unit-batch12b.patch"
SENSOR_UNITS = ("bmm350", "ina226-10a", "ina226-1a")
ROLLER_UNITS = ("roller485", "roller485-lite", "rollercan", "rollercan-lite")
UART_UNITS = ("8servos2-chain", "chainbus", "cat1-cn")
UNITS = SENSOR_UNITS + ROLLER_UNITS + UART_UNITS


class UnitBatch12bPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding="utf-8")
        cls.catalog = json.loads((ROOT / "platform/units/catalog.json").read_text(encoding="utf-8"))
        cls.units = {unit["id"]: unit for unit in cls.catalog["units"]}
        cls.profiles = json.loads(
            (ROOT / "platform/units/runtime-profiles.json").read_text(encoding="utf-8")
        )["units"]

    def test_patch_exists_on_the_canonical_chain(self):
        self.assertTrue(PATCH.is_file())
        readme = (ROOT / "patches/qemu-m5stack-peripherals/README.md").read_text(encoding="utf-8")
        self.assertIn("0159-unit-batch12b.patch", readme)
        self.assertIn("0156", readme)
        self.assertIn("0157", readme)
        self.assertEqual(
            hashlib.sha256(PATCH.read_bytes()).hexdigest(),
            "096fed5de9041bace01d9ac7d74ccd61914858a7314cbe45ca54af6b7507295a",
        )

    def test_patch_touches_three_model_files(self):
        for path in (
            "hw/m5stopwatch/m5_unit_i2c_sensors.c",
            "hw/m5stopwatch/m5_unit_i2c_controls.c",
            "hw/m5stopwatch/m5_unit_gpio.c",
        ):
            self.assertIn(f"diff --git a/{path} b/{path}", self.text)

    def test_bmm350_and_ina226_register_semantics(self):
        # BMM350 must reproduce the datasheet two-dummy-byte read and Table 8
        # registers; INA226 must use the TI Table 7-1 big-endian register set.
        for token in ("US_BMM350", "US_INA226", "9.2.3", "bmm_mag_raw",
                      "bmm_temp_raw", "ina_bus_raw", "ina_current_raw",
                      "0x31", "0x7e", "0x5449", "0x2260"):
            self.assertIn(token, self.text, token)
        self.assertIn("bmm_chip_id", self.text)
        self.assertIn("ina_calibration", self.text)

    def test_roller_family_register_subset(self):
        for token in ("CONTROL_ROLLER", "roller_refresh", "roller_family",
                      "roller_target_speed_rpm", "roller_actual_position_deg",
                      "roller_save_writes"):
            self.assertIn(token, self.text, token)
        for unit_id in ROLLER_UNITS:
            self.assertIn(f'"{unit_id}"', self.text, unit_id)

    def test_chain_and_cat1_uart_responders(self):
        for token in ("chain_process", "chain_emit", "chain_handle_frame",
                      "chain_handle_servos", "chain_handle_bus",
                      "0xaa", "0x55", "cat1_respond", "MIPOPEN", "MDNSGIP",
                      "8servos2-chain", "chainbus", "cat1-cn"):
            self.assertIn(token, self.text, token)
        # Chain device types: U223 8Servos2 = 0x000C, U212 ChainBus = 0x0006.
        self.assertIn("0x000c", self.text)
        self.assertIn("0x0006", self.text)

    def test_catalog_partial_but_profiles_planned(self):
        self.assertEqual(len(self.catalog["units"]), 160)
        self.assertEqual(len(self.profiles), 160)
        for unit_id in UNITS:
            unit, profile = self.units[unit_id], self.profiles[unit_id]
            self.assertEqual(unit["model_status"], "partial", unit_id)
            self.assertEqual(unit["runtime"]["status"], "implemented", unit_id)
            self.assertTrue(unit["runtime"]["properties"], unit_id)
            self.assertIn("无 guest 证据", unit["blocker"], unit_id)
            # No guest/Device Service evidence means the host-facing profile
            # stays planned and host-less (never promoted to implemented).
            self.assertEqual(profile["status"], "planned", unit_id)
            self.assertEqual(profile["hosts"], [], unit_id)
            self.assertNotIn("virtual_device_evidence", profile, unit_id)
            self.assertEqual(profile["model_completeness"], "pending", unit_id)
            self.assertTrue(profile["blocker"], unit_id)

    def test_address_conflicts_and_blockers_are_explicit(self):
        self.assertEqual(self.units["bmm350"]["interface"]["address_7bit"], [0x14])
        self.assertEqual(self.units["ina226-10a"]["interface"]["address_7bit"], [0x41])
        self.assertEqual(self.units["ina226-1a"]["interface"]["address_7bit"], [0x41])
        for unit_id in ROLLER_UNITS:
            self.assertEqual(self.units[unit_id]["interface"]["address_7bit"], [0x64])
        for unit_id in ROLLER_UNITS:
            self.assertIn("0x64", self.units[unit_id]["blocker"])
        self.assertIn("0x41", self.units["ina226-1a"]["blocker"])
        self.assertIn("0x811", self.units["ina226-1a"]["blocker"])
        self.assertIn("0x14", self.units["bmm350"]["blocker"])
        # Physical/RF/motor semantics always stay NOT RUN in this layer.
        for unit_id in UNITS:
            joined = json.dumps(self.units[unit_id], ensure_ascii=False)
            self.assertIn("NOT RUN", joined, unit_id)

    def test_recognized_properties_match_patch_tokens(self):
        expected = {
            "bmm350": {"magnetic-x", "magnetic-y", "magnetic-z", "temperature-c",
                       "whoami", "i2c-address", "transactions", "read-bytes",
                       "written-bytes"},
            "ina226-10a": {"bus-voltage-v", "current-a", "power-w",
                           "manufacturer-id", "die-id", "i2c-address",
                           "transactions", "read-bytes", "written-bytes"},
            "8servos2-chain": {"channel-modes", "servo-angles", "adc-values",
                               "rgb-leds", "current-ma", "frames-sent",
                               "frames-injected"},
            "chainbus": {"chain-uid", "version", "link-devices", "heartbeat",
                         "i2c-address", "gpio-levels", "adc-values",
                         "frames-sent", "frames-injected"},
            "cat1-cn": {"responses-hex", "tx-hex", "frames-sent", "frames-injected"},
        }
        expected["ina226-1a"] = expected["ina226-10a"]
        for unit_id in ROLLER_UNITS:
            expected[unit_id] = {"motor-output", "mode", "system-state", "fault",
                                 "encoder-pos", "target-speed-rpm",
                                 "actual-speed-rpm", "target-position-deg",
                                 "actual-position-deg", "current-ma", "vin-v",
                                 "mcu-temp-c", "i2c-address", "save-count",
                                 "transactions", "read-bytes", "written-bytes"}
        for unit_id, names in expected.items():
            self.assertEqual(set(self.units[unit_id]["runtime"]["properties"]), names, unit_id)

    def test_visual_mappings_and_impl_status_doc(self):
        mappings = (ROOT / "platform/web/unit-visual-mappings.js").read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, mappings)
        self.assertEqual(mappings.count("0158"), 10)
        doc = ROOT / "docs/unit-research/2026-11-03-batch12b-impl-status.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text(encoding="utf-8")
        for unit_id in UNITS:
            self.assertIn(unit_id, text)
        self.assertIn("0158", text)
        self.assertIn("planned", text)
        # The QOM smoke is property/fixture-only, not an I2C/UART transaction
        # or guest PASS.
        self.assertIn("smoke", text.lower())
        self.assertIn("NOT RUN", text)


if __name__ == "__main__":
    unittest.main()
