#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from network_lane import (  # noqa: E402
    LaneConfig,
    LaneError,
    build_emulator_command,
    check_generic_evidence,
    check_dns_udp_evidence,
    check_http_evidence,
    check_smoke_evidence,
    check_uiflow2_evidence,
    execute,
    redact_command,
)


def config(tmp: Path, **changes) -> LaneConfig:
    values = {
        "profile": "uiflow2-sticks3",
        "chip": "esp32s3",
        "firmware": tmp / "firmware.bin",
        "elf": tmp / "firmware.elf",
        "emulator": tmp / "esp-emu",
        "out_dir": tmp / "out",
        "timeout": 30,
        "ssid": "myssid",
        "password": "mypassword",
        "wifi_auth": "wpa2-wpa3",
        "psram_size": "8M",
        "net_mode": "user",
        "wifi": True,
        "ble": True,
        "ble_port": 9544,
        "ble_name": "M5-NETWORK-LANE",
        "tcp": True,
        "expected_markers": [],
    }
    values.update(changes)
    return LaneConfig(**values)


class NetworkLaneTests(unittest.TestCase):
    def test_builds_uiflow2_command_with_ble_and_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            row = config(tmp)
            command, injection = build_emulator_command(
                row,
                firmware_copy=tmp / "runtime.bin",
            )
        self.assertIn("--net", command)
        self.assertIn("user", command)
        self.assertIn("--ble-hci", command)
        self.assertIn("tcp:127.0.0.1:9544", command)
        self.assertNotIn("--exit-on", command)
        stages = injection["stages"]
        self.assertEqual(stages[0]["payload"], "\x03")
        self.assertIn("machine.reset()", stages[1]["payload"])
        self.assertIn("w.connect(\"myssid\",\"mypassword\")", stages[2]["payload"])
        self.assertIn("BLEUARTServer", stages[2]["payload"])

    def test_http_profile_exits_on_machine_readable_result(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            row = config(tmp, profile="esp-idf-http", ble=False)
            command, injection = build_emulator_command(
                row,
                firmware_copy=tmp / "runtime.bin",
            )
        self.assertEqual(injection, {})
        self.assertIn("--exit-on", command)
        self.assertIn("HTTP_TPUT_RESULT", command)

    def test_c6_without_psram_omits_psram_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            row = config(
                tmp,
                chip="esp32c6",
                profile="esp-idf-http",
                psram_size="0",
                ble=False,
            )
            command, _ = build_emulator_command(
                row,
                firmware_copy=tmp / "runtime.bin",
            )
        self.assertNotIn("--psram-size", command)

    def test_dns_udp_profile_exits_on_final_result(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            row = config(
                tmp,
                profile="idf-dns-udp",
                ble=False,
                tcp=False,
            )
            command, _ = build_emulator_command(
                row,
                firmware_copy=tmp / "runtime.bin",
            )
        self.assertIn("--exit-on", command)
        self.assertIn("DNS_UDP_RESULT", command)

    def test_command_and_injection_redact_password(self):
        with tempfile.TemporaryDirectory() as directory:
            row = config(Path(directory))
            command, injection = build_emulator_command(
                row,
                firmware_copy=Path(directory) / "runtime.bin",
            )
        rendered = redact_command(command, "mypassword")
        self.assertNotIn("mypassword", rendered)
        self.assertIn("<redacted>", rendered)
        self.assertIn("myssid", rendered)

    def test_uiflow2_parser_requires_wifi_and_ble_data_planes(self):
        serial = """
LANE_WIFI_SCAN 1
LANE_WIFI_CONNECTED True
LANE_WIFI_STATUS 1010
LANE_WIFI_IP 192.168.4.2
M5_NETWORK_LANE_OK
LANE_BLE_RX b'M5_LANE'
LANE_DONE
"""
        ble = """
BLE_BUMBLE_FOUND name='M5-NETWORK-LANE'
BLE_BUMBLE_GATT_DISCOVERED 6e400001-b5a3-f393-e0a9-e50e24dcca9e
BLE_BUMBLE_SUBSCRIBED 6e400003-b5a3-f393-e0a9-e50e24dcca9e
BLE_BUMBLE_WRITE M5_LANE
BLE_BUMBLE_PASS
"""
        checks, values = check_uiflow2_evidence(
            serial,
            ble,
            wifi=True,
            ble=True,
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(values["wifi_ip"], "192.168.4.2")
        self.assertEqual(values["ble_payload"], "M5_LANE")

    def test_wifi_only_does_not_require_ble_probe(self):
        serial = """
LANE_WIFI_SCAN 1
LANE_WIFI_CONNECTED True
LANE_WIFI_STATUS 1010
LANE_WIFI_IP 192.168.4.2
LANE_DONE
"""
        checks, _ = check_uiflow2_evidence(
            serial,
            "",
            wifi=True,
            ble=False,
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertNotIn("ble_probe", checks)

    def test_ble_only_does_not_require_wifi(self):
        serial = """
LANE_BLE_RX b'M5_LANE'
LANE_DONE
"""
        ble = """
BLE_BUMBLE_GATT_DISCOVERED 6e400001-b5a3-f393-e0a9-e50e24dcca9e
BLE_BUMBLE_SUBSCRIBED 6e400003-b5a3-f393-e0a9-e50e24dcca9e
BLE_BUMBLE_WRITE M5_LANE
BLE_BUMBLE_PASS
"""
        checks, _ = check_uiflow2_evidence(
            serial,
            ble,
            wifi=False,
            ble=True,
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertNotIn("wifi_scan", checks)

    def test_http_parser_requires_full_tcp_download(self):
        serial = """
I (1598) http_tput: GOT_IP 192.168.4.2
I (1598) http_tput: HTTP 200, content-length=1048576
I (1878) http_tput: downloaded 1048576 bytes in 280081 us (complete=1)
HTTP_TPUT: bytes=1048576 us=280081 mbit_s=29.95 target=esp32s3 link=wifi
HTTP_TPUT_RESULT: PASSED
"""
        checks = check_http_evidence(serial, ["/bigfile"])
        self.assertTrue(all(checks.values()), checks)

    def test_dns_udp_parser_requires_host_datagram_and_guest_reply(self):
        serial = """
GOT_IP 192.168.4.2
DNS_OK: 198.18.0.86
UDP_REPLY: UDP_REPLY:M5_DNS_UDP_PROBE
UDP_RESULT: PASSED
DNS_UDP_RESULT: PASSED
"""
        checks, values = check_dns_udp_evidence(
            serial,
            [b"M5_DNS_UDP_PROBE"],
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(values["dns_address"], "198.18.0.86")

    def test_smoke_parser_keeps_ble_separate(self):
        serial = """
WiFi: GOT_IP 192.168.4.2
TEST wifi: PASSED
RESULT_SUMMARY: passed=34 failed=0 target=esp32s3
"""
        checks = check_smoke_evidence(serial, require_ble=True)
        self.assertTrue(checks["wifi_dhcp"])
        self.assertFalse(checks["ble_advertising"])

    def test_generic_observations_are_partial_without_assertions(self):
        checks = check_generic_evidence("firmware booted\n", [])
        self.assertEqual(checks, {"runtime_output": True})
        asserted = check_generic_evidence(
            "APP_READY\n",
            ["APP_READY", "NETWORK_READY"],
        )
        self.assertTrue(asserted["marker:1"])
        self.assertFalse(asserted["marker:2"])

    def test_rejects_classic_esp32_before_process_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            (tmp / "firmware.bin").write_bytes(b"\xe9")
            (tmp / "esp-emu").write_bytes(b"")
            row = config(tmp, chip="esp32")
            with self.assertRaises(LaneError) as caught:
                execute(row)
        self.assertIn("separate network/PHY path", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
