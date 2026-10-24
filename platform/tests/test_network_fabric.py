#!/usr/bin/env python3
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import network_fabric  # noqa: E402


def dhcp_request(
    message_type: int,
    *,
    mac: str = "02:4d:35:00:00:01",
    requested_ip: str | None = None,
) -> bytes:
    packet = bytearray(240)
    packet[0] = 1
    packet[1] = 1
    packet[2] = 6
    packet[4:8] = b"\x12\x34\x56\x78"
    packet[28:34] = bytes.fromhex(mac.replace(":", ""))
    packet[236:240] = network_fabric.DHCP_MAGIC
    options = bytearray((53, 1, message_type))
    if requested_ip is not None:
        options.extend((50, 4))
        options.extend(socket.inet_aton(requested_ip))
    options.append(255)
    packet.extend(options)
    return bytes(packet)


class NetworkFabricTests(unittest.TestCase):
    def test_allocation_is_bounded_private_and_unique(self):
        first = network_fabric.LabFabric.allocate()
        second = network_fabric.LabFabric.allocate()
        self.assertNotEqual(first.namespace, second.namespace)
        for fabric in (first, second):
            self.assertLessEqual(len(fabric.namespace), 15)
            self.assertLessEqual(len(fabric.bridge), 15)
            for endpoint in fabric.endpoints:
                self.assertLessEqual(len(endpoint.tap), 15)
            self.assertEqual(
                [endpoint.address for endpoint in fabric.endpoints],
                ["10.230.0.2", "10.230.0.3"],
            )
            self.assertEqual(
                [endpoint.mac for endpoint in fabric.endpoints],
                [
                    "02:4d:35:00:00:01",
                    "02:4d:35:00:00:02",
                ],
            )
            self.assertEqual(
                fabric.metadata()["mode"],
                "linux-private-bridge-tap",
            )
        socket_fabric = network_fabric.LabSocketFabric.allocate()
        self.assertLessEqual(len(socket_fabric.namespace), 15)
        self.assertEqual(
            socket_fabric.metadata()["mode"],
            "linux-private-qemu-socket-switch",
        )
        frame = b"frame" + b"\0" * 9
        encoded = network_fabric.LabSocketSwitch.encode_frame(frame)
        buffer = bytearray(encoded)
        self.assertEqual(
            network_fabric.LabSocketSwitch.extract_frames(buffer),
            [frame],
        )
        self.assertEqual(buffer, b"")

    def test_ruleset_allows_only_dhcp_host_services_and_peer_forwarding(self):
        rules = network_fabric.build_fabric_ruleset(
            bridge="br0",
            taps=("tap0", "tap1"),
        )
        self.assertIn("policy drop;", rules)
        self.assertIn('iifname "br0" udp dport 67 accept', rules)
        self.assertIn('oifname "br0" udp sport 67 accept', rules)
        self.assertIn(
            'iifname "tap0" oifname "tap1" accept',
            rules,
        )
        self.assertIn(
            'iifname "tap1" oifname "tap0" accept',
            rules,
        )

    def test_socket_switch_binds_reversed_clients_by_mac(self):
        switch = network_fabric.LabSocketSwitch(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 25000,
                "expected_clients": 2,
                "server_address": "10.230.0.1",
                "prefix_length": 24,
                "reservations": {
                    "02:4d:35:00:00:01": "10.230.0.2",
                    "02:4d:35:00:00:02": "10.230.0.3",
                },
                "endpoints": [
                    {
                        "index": 0,
                        "mac": "02:4d:35:00:00:01",
                    },
                    {
                        "index": 1,
                        "mac": "02:4d:35:00:00:02",
                    },
                ],
            }
        )
        switch.forward(0, b"pending-for-b")
        self.assertEqual(
            switch.pending_frames[1],
            [b"pending-for-b"],
        )
        self.assertEqual(
            switch.bind_client(0, "02:4d:35:00:00:02"),
            1,
        )
        self.assertEqual(
            switch.bind_client(1, "02:4d:35:00:00:01"),
            0,
        )
        self.assertEqual(
            switch.client_slot_by_endpoint,
            {0: 1, 1: 0},
        )
        with self.assertRaisesRegex(
            network_fabric.LabFabricError,
            "unconfigured MAC",
        ):
            switch.bind_client(2, "02:4d:35:00:00:09")

    def test_dhcp_reservations_build_offer_and_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dhcp = network_fabric.LabDhcp(
                {
                    "interface": "br0",
                    "server_address": "10.230.0.1",
                    "prefix_length": 24,
                    "lease_seconds": 3600,
                    "reservations": {
                        "02:4d:35:00:00:01": "10.230.0.2",
                        "02:4d:35:00:00:02": "10.230.0.3",
                    },
                    "lease_file": str(root / "leases.json"),
                }
            )
            offer = dhcp.handle(dhcp_request(1))
            self.assertIsNotNone(offer)
            parsed_offer = network_fabric.parse_dhcp_request(offer or b"")
            self.assertIsNone(parsed_offer)
            options = network_fabric._dhcp_options(offer or b"")
            self.assertEqual(options[53], b"\x02")
            self.assertEqual(
                str(network_fabric.ipaddress.IPv4Address(options[54])),
                "10.230.0.1",
            )
            self.assertEqual(offer[16:20], socket.inet_aton("10.230.0.2"))

            ack = dhcp.handle(
                dhcp_request(3, requested_ip="10.230.0.2")
            )
            self.assertIsNotNone(ack)
            self.assertEqual(
                network_fabric._dhcp_options(ack or b"")[53],
                b"\x05",
            )
            leases = (root / "leases.json").read_text()
            self.assertIn("02:4d:35:00:00:01", leases)
            self.assertIn("10.230.0.2", leases)

    def test_dhcp_rejects_unreserved_and_wrong_requested_address(self):
        dhcp = network_fabric.LabDhcp(
            {
                "interface": "br0",
                "server_address": "10.230.0.1",
                "reservations": {
                    "02:4d:35:00:00:01": "10.230.0.2",
                },
            }
        )
        with self.assertRaisesRegex(
            network_fabric.LabFabricError,
            "no DHCP reservation",
        ):
            dhcp.handle(
                dhcp_request(1, mac="02:4d:35:00:00:09")
            )
        self.assertIsNone(
            dhcp.handle(
                dhcp_request(3, requested_ip="10.230.0.9")
            )
        )

    def test_dhcp_falls_back_to_ethernet_source_and_builds_frame(self):
        dhcp = network_fabric.LabDhcp(
            {
                "interface": "br0",
                "server_address": "10.230.0.1",
                "reservations": {
                    "02:4d:35:00:00:02": "10.230.0.3",
                },
            }
        )
        request = dhcp_request(1, mac="00:00:00:00:00:00")
        offer = dhcp.handle(
            request,
            source_mac="02:4d:35:00:00:02",
        )
        self.assertIsNotNone(offer)
        frame = network_fabric.build_dhcp_ethernet_reply(
            offer or b"",
            source_mac=bytes.fromhex("024d35000002"),
            server_mac=bytes.fromhex("024d35fffffe"),
            server_address="10.230.0.1",
        )
        self.assertEqual(frame[:6], b"\xff" * 6)
        self.assertEqual(
            network_fabric.struct.unpack_from("!H", frame, 12)[0],
            network_fabric.ETH_P_IP,
        )
        ip_header = frame[14:34]
        self.assertEqual(network_fabric._internet_checksum(ip_header), 0)
        self.assertEqual(frame[34:36], b"\x00\x43")
        self.assertEqual(frame[36:38], b"\x00\x44")
        udp_length = network_fabric.struct.unpack_from(
            "!H",
            frame,
            38,
        )[0]
        udp = frame[34 : 34 + udp_length]
        pseudo = (
            frame[26:30]
            + frame[30:34]
            + network_fabric.struct.pack(
                "!BBH",
                0,
                network_fabric.IPPROTO_UDP,
                udp_length,
            )
        )
        self.assertEqual(
            network_fabric._internet_checksum(pseudo + udp),
            0,
        )

    def test_cleanup_is_safe_before_start(self):
        fabric = network_fabric.LabFabric.allocate()
        fabric.cleanup()
        self.assertFalse(fabric.started)


if __name__ == "__main__":
    unittest.main(verbosity=2)
