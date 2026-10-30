#!/usr/bin/env python3
from __future__ import annotations

import unittest

import device_service
from device_service_errors import ServiceError
from device_service_qemu_wifi import (
    apply_qemu_wifi_environment,
    parse_qemu_wifi_security,
)


class DeviceServiceQemuWifiTests(unittest.TestCase):
    def test_device_service_reexports_the_same_objects(self) -> None:
        self.assertIs(
            device_service.parse_qemu_wifi_security,
            parse_qemu_wifi_security,
        )
        self.assertIs(
            device_service.apply_qemu_wifi_environment,
            apply_qemu_wifi_environment,
        )

    def test_security_parser_normalizes_open_and_wpa2(self) -> None:
        self.assertEqual(
            parse_qemu_wifi_security(
                {
                    "wifi_ssid": "open-net",
                    "wifi_password": "ignored-secret",
                    "wifi_auth": "open",
                }
            ),
            {
                "wifi_ssid": "open-net",
                "wifi_password": "",
                "wifi_auth": "open",
            },
        )
        self.assertEqual(
            parse_qemu_wifi_security(
                {
                    "wifi_ssid": "secure-net",
                    "wifi_password": "12345678",
                    "wifi_auth": "wpa2-psk",
                }
            ),
            {
                "wifi_ssid": "secure-net",
                "wifi_password": "12345678",
                "wifi_auth": "wpa2-psk",
            },
        )

    def test_security_parser_fail_closed(self) -> None:
        for value, code, status in (
            (
                {"wifi_ssid": ""},
                "invalid_network",
                400,
            ),
            (
                {"wifi_password": "x" * 64},
                "invalid_network",
                400,
            ),
            (
                {"wifi_auth": "wpa3-sae"},
                "unsupported_wifi_security",
                409,
            ),
            (
                {"wifi_auth": "wpa2-psk", "wifi_password": "short"},
                "invalid_network",
                400,
            ),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ServiceError) as caught:
                    parse_qemu_wifi_security(value)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.status, status)

    def test_environment_projection_preserves_s3_trace_gate(self) -> None:
        network = {
            "wifi_ssid": "secure-net",
            "wifi_password": "12345678",
            "wifi_auth": "wpa2-psk",
        }
        s3_env: dict[str, str] = {}
        apply_qemu_wifi_environment(
            s3_env,
            "misc.esp32s3.wifi",
            network,
        )
        self.assertEqual(
            s3_env,
            {
                "M5SW_WIFI_SSID": "secure-net",
                "M5SW_WIFI_PASSWORD": "12345678",
                "M5SW_WIFI_AUTH": "wpa2-psk",
                "M5SW_S3_WIFI_TRACE": "1",
            },
        )

        classic_env: dict[str, str] = {}
        apply_qemu_wifi_environment(
            classic_env,
            "misc.esp32_wifi",
            network,
        )
        self.assertNotIn("M5SW_S3_WIFI_TRACE", classic_env)

        unrelated_env: dict[str, str] = {}
        apply_qemu_wifi_environment(
            unrelated_env,
            "misc.esp32c6.wifi",
            network,
        )
        self.assertEqual(unrelated_env, {})


if __name__ == "__main__":
    unittest.main()
