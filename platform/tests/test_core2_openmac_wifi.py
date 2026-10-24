#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/network/core2_openmac_wifi"))

from run_test import DETERMINISTIC_QEMU_ARGS, parse_probe


class Core2OpenMacWifiTests(unittest.TestCase):
    def test_parses_stock_wifi_scan_markers(self):
        parsed = parse_probe(
            "CORE2_WIFI_BOOT_FLAG\n"
            "CORE2_WIFI_MAIN_START\n"
            "CORE2_WIFI_ACTIVE True\n"
            "CORE2_WIFI_SCAN_OK 3\n"
            "CORE2_WIFI_SCAN_RESULTS [(b'myssid',)]\n"
            "CORE2_WIFI_CONNECT_RETURNED None\n"
            "CORE2_WIFI_CONNECTED True\n"
            "CORE2_WIFI_IP 10.0.2.15\n"
            "CORE2_HTTP_RX b'HTTP/1.0 200 OK\\r\\nServer: SimpleH'\n"
            "CORE2_HTTP_OK\n"
            "CORE2_WIFI_RESULT: PASSED\n"
        )
        self.assertTrue(parsed["boot"])
        self.assertTrue(parsed["main"])
        self.assertTrue(parsed["active"])
        self.assertEqual(parsed["scan_count"], 3)
        self.assertTrue(parsed["known_ssid"])
        self.assertTrue(parsed["connect_returned"])
        self.assertTrue(parsed["connected"])
        self.assertEqual(parsed["ip"], "10.0.2.15")
        self.assertTrue(parsed["http_200"])
        self.assertIn("200 OK", parsed["http_response"])
        self.assertEqual(parsed["terminal_result"], "PASSED")
        self.assertEqual(
            DETERMINISTIC_QEMU_ARGS,
            (
                "-accel",
                "tcg,thread=single,tb-size=128",
                "-icount",
                "shift=auto,align=off,sleep=off",
            ),
        )

    def test_missing_scan_does_not_pass(self):
        parsed = parse_probe("CORE2_WIFI_RESULT: FAILED\n")
        self.assertFalse(parsed["boot"])
        self.assertEqual(parsed["scan_count"], 0)
        self.assertFalse(parsed["connected"])
        self.assertIsNone(parsed["ip"])
        self.assertFalse(parsed["http_200"])
        self.assertIsNone(parsed["http_response"])
        self.assertEqual(parsed["terminal_result"], "FAILED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
