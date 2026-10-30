#!/usr/bin/env python3
from __future__ import annotations

from types import SimpleNamespace
import unittest

import device_service
from device_service_errors import ServiceError
from device_service_network_execution import parse_network_execution


def spec() -> SimpleNamespace:
    return SimpleNamespace(
        id="sticks3",
        network_chip="esp32s3",
        network_profiles=["esp-idf-http"],
        network_console="uart0",
    )


class DeviceServiceNetworkExecutionTests(unittest.TestCase):
    def test_device_service_reexports_the_same_parser_object(self) -> None:
        self.assertIs(
            device_service.parse_network_execution,
            parse_network_execution,
        )

    def test_network_parser_preserves_defaults(self) -> None:
        parsed = parse_network_execution(spec(), None)
        self.assertEqual(parsed["profile"], "esp-idf-http")
        self.assertEqual(parsed["chip"], "esp32s3")
        self.assertTrue(parsed["wifi"])
        self.assertFalse(parsed["ble"])
        self.assertTrue(parsed["tcp"])
        self.assertEqual(parsed["wifi_ssid"], "myssid")
        self.assertEqual(parsed["wifi_password"], "mypassword")
        self.assertEqual(parsed["wifi_auth"], "wpa2-wpa3")
        self.assertEqual(parsed["psram_size"], "8M")
        self.assertEqual(parsed["net_mode"], "user")
        self.assertEqual(parsed["console_mode"], "uart0")
        self.assertFalse(parsed["capture_pcap"])

    def test_network_parser_preserves_host_forwarding_contract(self) -> None:
        parsed = parse_network_execution(
            spec(),
            {
                "hostfwd": [
                    {
                        "protocol": "tcp",
                        "host_port": 18080,
                        "guest_port": 80,
                    }
                ]
            },
        )
        self.assertEqual(
            parsed["hostfwd"],
            ["tcp:127.0.0.1:18080-:80"],
        )

    def test_network_parser_fail_closed(self) -> None:
        cases = (
            (
                {"profile": "generic-observe"},
                "unsupported_network_profile",
                400,
            ),
            (
                {"capture_pcap": True},
                "pcap_not_supported",
                409,
            ),
            (
                {
                    "hostfwd": [
                        {
                            "protocol": "tcp",
                            "host_port": 18080,
                            "guest_port": 80,
                        },
                        {
                            "protocol": "tcp",
                            "host_port": 18080,
                            "guest_port": 81,
                        },
                    ]
                },
                "invalid_network",
                400,
            ),
            (
                {"wifi": "yes"},
                "invalid_network",
                400,
            ),
        )
        for value, code, status in cases:
            with self.subTest(value=value):
                with self.assertRaises(ServiceError) as caught:
                    parse_network_execution(spec(), value)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.status, status)


if __name__ == "__main__":
    unittest.main()
