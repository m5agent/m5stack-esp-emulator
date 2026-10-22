#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/network/core2_openmac_wifi"))

from run_test import parse_probe  # noqa: E402


class Core2OpenMacWifiTests(unittest.TestCase):
    def test_parses_stock_wifi_scan_markers(self):
        parsed = parse_probe(
            "CORE2_WIFI_BOOT_FLAG\n"
            "CORE2_WIFI_MAIN_START\n"
            "CORE2_WIFI_ACTIVE True\n"
            "CORE2_WIFI_SCAN_OK 3\n"
            "CORE2_WIFI_SCAN_RESULTS [(b'myssid',)]\n"
            "CORE2_WIFI_RESULT: PASSED\n"
        )
        self.assertTrue(parsed["boot"])
        self.assertTrue(parsed["main"])
        self.assertTrue(parsed["active"])
        self.assertEqual(parsed["scan_count"], 3)
        self.assertTrue(parsed["known_ssid"])
        self.assertEqual(parsed["terminal_result"], "PASSED")

    def test_missing_scan_does_not_pass(self):
        parsed = parse_probe("CORE2_WIFI_RESULT: FAILED\n")
        self.assertFalse(parsed["boot"])
        self.assertEqual(parsed["scan_count"], 0)
        self.assertEqual(parsed["terminal_result"], "FAILED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
