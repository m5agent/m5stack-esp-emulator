#!/usr/bin/env python3
from __future__ import annotations

import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

import device_service
from device_service_errors import ServiceError
from device_service_qemu_wifi import (
    STICKS3_RAW_TX_WINDOW_PROPERTY,
    apply_qemu_wifi_environment,
    apply_sticks3_monitor_environment,
    configure_sticks3_monitor_radio,
    parse_qemu_wifi_security,
    parse_sticks3_raw_mpdu,
    parse_sticks3_wifi_monitor,
    require_sticks3_raw_backend,
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


    def test_monitor_is_opt_in_and_binds_the_radio_state(self) -> None:
        self.assertIsNone(parse_sticks3_wifi_monitor({"device_id": "sticks3"}))
        on = parse_sticks3_wifi_monitor({"device_id": "sticks3", "wifi_monitor_fixture": "beacon"})
        off = parse_sticks3_wifi_monitor({"device_id": "sticks3", "wifi_monitor_fixture": "no-beacon"})
        self.assertTrue(on["radio_enabled"])
        self.assertFalse(off["radio_enabled"])
        self.assertEqual(on["host_backends"], 0)
        self.assertNotEqual(on["fixture_sha256"], off["fixture_sha256"])

    def test_monitor_rejects_nonlocal_or_conflicting_configuration(self) -> None:
        payload = {"device_id": "sticks3", "wifi_monitor_fixture": "beacon"}
        for change, code in (
            ({"wifi_monitor_fixture": True}, "invalid_wifi_monitor_fixture"),
            ({"wifi_monitor_fixture": None}, "invalid_wifi_monitor_fixture"),
            ({"device_id": "cores3"}, "wifi_monitor_fixture_not_supported"),
            ({"runtime": "qemu-wifi"}, "wifi_monitor_fixture_not_supported"),
            ({"network": {"hostfwd": []}}, "wifi_monitor_fixture_conflict"),
            ({"runtime_env": {"M5SW_ESPNOW_LOOPBACK": "1"}}, "wifi_monitor_fixture_conflict"),
            ({"program_transport": "uart-repl"}, "wifi_monitor_fixture_conflict"),
        ):
            with self.subTest(change=change), self.assertRaises(ServiceError) as caught:
                parse_sticks3_wifi_monitor(payload | change)
            self.assertEqual(caught.exception.code, code)

    def test_monitor_environment_drops_inherited_wifi_and_peers(self) -> None:
        env = {"M5SW_WIFI_SSID": "inherited", "M5SW_WIFI_PASSWORD": "inherited",
               "M5SW_ESPNOW_LOOPBACK": "1", "M5SW_ESPNOW_PEER_LOCAL_PORT": "7001",
               "M5SW_ESPNOW_PEER_REMOTE_PORT": "7002", "M5SW_INPUT_TRACE": "1"}
        apply_sticks3_monitor_environment(env)
        self.assertEqual(env, {"M5SW_WIFI_SSID": "m5-monitor-lab", "M5SW_WIFI_AUTH": "open",
                               "M5SW_S3_WIFI_TRACE": "1", "M5SW_INPUT_TRACE": "1"})

    def test_monitor_rejects_a_host_backend_before_changing_radio(self) -> None:
        qmp = Mock(side_effect=[
            {"return": {"running": False}},
            {"return": "hub 0\n \\ hub0port0: misc.esp32s3.wifi.0: "
                       "index=0,type=nic,model=misc.esp32s3.wifi,macaddr=02:00:00:00:20:04\n"
                       " \\ hub0port1: user.0: type=user\n"},
        ])
        with self.assertRaises(ServiceError) as caught:
            configure_sticks3_monitor_radio(qmp, True)
        self.assertEqual(caught.exception.code, "wifi_monitor_fixture_isolation")
        self.assertEqual(qmp.call_count, 2)


    def test_raw_monitor_keeps_ap_and_forwarding_off(self) -> None:
        config = parse_sticks3_wifi_monitor({"device_id": "sticks3", "wifi_monitor_fixture": "raw"})
        self.assertTrue(config["radio_enabled"])
        self.assertFalse(config["forwarding"])
        self.assertFalse(config["ap_beacons"])
        self.assertIsNone(config["wifi_ssid"])

    def test_raw_monitor_backend_probe_rejects_old_qemu(self) -> None:
        with patch("device_service_qemu_wifi.subprocess.run", return_value=Mock(stdout="mac=<str>")):
            with self.assertRaises(ServiceError) as caught:
                require_sticks3_raw_backend(Path("/qemu-system-xtensa"))
        self.assertEqual(caught.exception.code, "wifi_monitor_raw_backend_unavailable")
        self.assertEqual(caught.exception.status, 503)

    def test_raw_monitor_request_requires_bounded_hex(self) -> None:
        self.assertEqual(parse_sticks3_raw_mpdu("AB" * 28), bytes([0xab] * 28))
        for value in (None, "00" * 27, "00" * 2317, "0" * 57, "z0" * 28, "00 " * 28):
            with self.subTest(value=value[:20] if isinstance(value, str) else value):
                with self.assertRaises(ServiceError) as caught:
                    parse_sticks3_raw_mpdu(value)
                self.assertEqual(caught.exception.code, "invalid_wifi_monitor_mpdu")


    def test_raw_window_uses_audited_read_permission(self) -> None:
        session = Mock()
        session._lock = nullcontext()
        session._qmp_call.return_value = {"return": "3:ab"}
        path = "/machine/unattached/device[0]"
        response = device_service.DeviceSession.qom_get(session, path, STICKS3_RAW_TX_WINDOW_PROPERTY)
        session._require_raw_monitor_qom.assert_called_once_with(path, "serial.read")
        self.assertEqual(response["value"], "3:ab")

    def test_old_raw_runtime_rejects_window_without_disconnect(self) -> None:
        session = Mock()
        session._lock = nullcontext()
        session._proc.poll.return_value = None
        session._qmp.cmd.side_effect = device_service.QMPCommandError("missing raw-tx-window")
        with self.assertRaises(ServiceError) as caught:
            device_service.DeviceSession._qmp_call(
                session, "qom-get", path="/machine/unattached/device[0]",
                property=STICKS3_RAW_TX_WINDOW_PROPERTY,
            )
        self.assertEqual(caught.exception.code, "wifi_monitor_raw_window_unavailable")
        self.assertEqual(caught.exception.status, 409)
        session._qmp.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
