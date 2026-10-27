"""Radio acceptance rejects missing data planes; no firmware cache or QEMU."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from test_pcap_summary import dhcp_packet, ethernet, ipv4_tcp, ipv4_udp, pcap

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "core2_radio_service_runner",
    ROOT / "tests/firmware/core2_startup/run_radio_service_test.py",
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

SERIAL = """rst:0x1 (POWERON_RESET)
V2.5.3
CORE2_WIFI_BOOT_FLAG
CORE2_WIFI_MAIN_START
CORE2_WIFI_ACTIVE True
CORE2_WIFI_SCAN_OK 2
CORE2_WIFI_SCAN_RESULTS myssid
CORE2_WIFI_CONNECT_RETURNED None
CORE2_WIFI_CONNECTED True
CORE2_WIFI_IP 10.0.2.15
CORE2_HTTP_RX b'HTTP/1.0 200 OK'
CORE2_HTTP_OK
CORE2_WIFI_RESULT: PASSED
"""


def capture(*, ack=True, payload=True, http_port=18080):
    frames = []
    for message in ((1, 2, 3, 5) if ack else (1, 2, 3)):
        reply = message in (2, 5)
        bootp = dhcp_packet(operation=2 if reply else 1, xid=1,
                            message_type=message,
                            assigned_address="10.0.2.15" if reply else "0.0.0.0")
        frames.append(ethernet(ipv4_udp(
            bootp, source="10.0.2.2" if reply else "0.0.0.0",
            destination="10.0.2.15" if reply else "255.255.255.255",
            source_port=67 if reply else 68, destination_port=68 if reply else 67,
        )))
    for reply in (False, True):
        body = (b"HTTP/1.0 200 OK\r\n\r\nOK" if reply else b"GET / HTTP/1.0\r\n\r\n") if payload else b""
        packet = bytearray(ipv4_tcp(
            body, source="10.0.2.2" if reply else "10.0.2.15",
            destination="10.0.2.15" if reply else "10.0.2.2",
        ))
        struct.pack_into(">HH", packet, 20, http_port if reply else 53001,
                         53001 if reply else http_port)
        frames.append(ethernet(bytes(packet)))
    return pcap(frames)


class Core2RadioRunnerTests(unittest.TestCase):
    def test_serial_requires_scan_dhcp_and_success_not_only_http_text(self):
        self.assertTrue(all(runner.guest_checks(SERIAL)[0].values()))
        for old, new, check in (
            ("SCAN_OK 2", "SCAN_OK 0", "scan_nonempty"),
            ("10.0.2.15", "0.0.0.0", "dhcp_address"),
            ("CORE2_HTTP_OK", "missing", "http_200"),
            ("RESULT: PASSED", "RESULT: FAILED", "terminal_pass"),
        ):
            with self.subTest(check=check):
                self.assertFalse(runner.guest_checks(SERIAL.replace(old, new))[0][check])

    def test_done_cannot_hide_a_later_watchdog_or_second_boot(self):
        self.assertFalse(runner.guest_checks(SERIAL + "TG1WDT_SYS_RESET\n")[0]["no_guest_error_or_reset"])
        self.assertFalse(runner.guest_checks(SERIAL + "CORE2_WIFI_BOOT_FLAG\n")[0]["single_boot"])

    def test_capture_requires_complete_dhcp_and_bidirectional_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertTrue(all(runner.packet_checks(capture(), output, 18080)[0].values()))
            self.assertFalse(runner.packet_checks(capture(ack=False), output, 18080)[0]["pcap_dhcp_dora"])
            headers_only = runner.packet_checks(capture(payload=False), output, 18080)[0]
            self.assertFalse(headers_only["pcap_http_guest_payload"])
            self.assertFalse(headers_only["pcap_http_host_payload"])

    def test_unrelated_tcp_port_cannot_substitute_for_the_http_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            checks, _ = runner.packet_checks(capture(http_port=18081), Path(directory), 18080)
            self.assertTrue(checks["pcap_dhcp_dora"])
            self.assertFalse(checks["pcap_http_guest_payload"])
            self.assertFalse(checks["pcap_http_host_payload"])


if __name__ == "__main__":
    unittest.main()
