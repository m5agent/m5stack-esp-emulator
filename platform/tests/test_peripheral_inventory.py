#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
from peripheral_inventory import build_inventory


class PeripheralInventoryTests(unittest.TestCase):
    def test_every_hardware_requirement_maps_to_a_component(self):
        inventory = build_inventory()
        self.assertEqual(inventory["device_count"], 14)
        self.assertEqual(
            inventory["runtime_coverage"]["covered_models"],
            inventory["runtime_coverage"]["simulated_models"],
        )
        for device in inventory["devices"]:
            self.assertEqual(
                device["coverage_gaps"],
                [],
                f"{device['id']} has uncovered hardware",
            )

    def test_inventory_preserves_blocked_models(self):
        inventory = build_inventory()
        devices = {row["id"]: row for row in inventory["devices"]}
        self.assertTrue(devices["cardputer-zero"]["complete"])
        self.assertTrue(devices["stackchan"]["complete"])
        self.assertFalse(devices["tab5"]["complete"])
        self.assertEqual(
            {
                row["id"]
                for row in devices.values()
                if not row["complete"]
            },
            {"tab5"},
        )
        self.assertIn("sc2356", devices["tab5"]["blocked_models"])
        self.assertIn("es8388", devices["tab5"]["blocked_models"])
        self.assertNotIn("rs485", devices["tab5"]["blocked_models"])

    def test_inventory_exposes_device_local_model_cases(self):
        inventory = build_inventory()
        devices = {row["id"]: row for row in inventory["devices"]}
        stackchan = devices["stackchan"]
        magnetometer = next(
            row for row in stackchan["components"]
            if row["model"] == "bmm150"
        )
        self.assertIn(
            "stackchan-peripherals",
            magnetometer["runtime_cases"],
        )
        self.assertIn(
            "bmm150",
            stackchan["runtime_cases"]["measured_models"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
