#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from user_firmware_matrix import (  # noqa: E402
    baseline_name,
    error_lines,
    input_for_device,
)


class UserFirmwareMatrixTests(unittest.TestCase):
    def test_baseline_filter_keeps_user_firmware(self):
        self.assertTrue(baseline_name("UIFlow Core2"))
        self.assertTrue(baseline_name("UIFlow2.0 StamPLC"))
        self.assertFalse(baseline_name("M5Launcher"))
        self.assertFalse(baseline_name("Meshtastic For Cardputer-Adv"))

    def test_error_lines_deduplicates_and_orders_crash_evidence(self):
        lines = error_lines(
            "\n".join(
                (
                    "I (100) boot: ready",
                    "Guru Meditation Error: Core 1 panic'ed",
                    "Rebooting...",
                    "Guru Meditation Error: Core 1 panic'ed",
                )
            )
        )

        self.assertEqual(
            lines,
            [
                "Guru Meditation Error: Core 1 panic'ed",
                "Rebooting...",
            ],
        )

    def test_error_lines_detects_new_user_firmware_failures(self):
        lines = error_lines(
            "\n".join(
                (
                    "assert failed: xTaskPriorityDisinherit tasks.c:5156",
                    "Invalid chip id. Expected 13 read 12.",
                    "E task_wdt: Task watchdog got triggered.",
                )
            )
        )

        self.assertEqual(len(lines), 3)

    def test_input_routes_touch_and_key_devices(self):
        touch = input_for_device(
            {"display": {"width": 320, "height": 240, "touch": True}}
        )
        key = input_for_device({"display": {"width": 128, "height": 128}})

        self.assertEqual(touch["kind"], "touch")
        self.assertEqual((touch["x"], touch["y"]), (160, 120))
        self.assertEqual(key, {"kind": "key", "key": "a", "settle_seconds": 0.8})


if __name__ == "__main__":
    unittest.main()
