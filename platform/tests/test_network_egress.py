#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from network_egress import (
    EgressEndpoint,
    EgressError,
    EgressGateway,
    build_egress_ruleset,
    parse_endpoints,
    requires_external_gateway,
    translated_address,
)


class NetworkEgressTests(unittest.TestCase):
    def test_endpoint_validation_sorts_and_canonicalizes(self):
        endpoints = parse_endpoints(
            [
                {
                    "protocol": "tcp",
                    "address": "1.1.1.1",
                    "port": 443,
                },
                {
                    "protocol": "udp",
                    "address": "10.0.2.2",
                    "port": 53,
                },
            ]
        )
        self.assertEqual(
            endpoints,
            (
                EgressEndpoint("tcp", "1.1.1.1", 443),
                EgressEndpoint("udp", "10.0.2.2", 53),
            ),
        )
        self.assertEqual(
            str(translated_address(endpoints[1])),
            "127.0.0.1",
        )
        self.assertTrue(requires_external_gateway(endpoints))
        self.assertFalse(
            requires_external_gateway(
                (EgressEndpoint("tcp", "10.0.2.2", 18443),)
            )
        )

    def test_rejects_unsafe_or_unsupported_endpoints(self):
        for value in (
            [{"protocol": "icmp", "address": "1.1.1.1", "port": 1}],
            [{"protocol": "tcp", "address": "example.com", "port": 443}],
            [{"protocol": "tcp", "address": "0.0.0.0", "port": 443}],
            [{"protocol": "tcp", "address": "224.0.0.1", "port": 443}],
            [{"protocol": "tcp", "address": "2606:4700:4700::1111", "port": 443}],
            [{"protocol": "tcp", "address": "1.1.1.1", "port": 0}],
            [{"protocol": "tcp", "address": "1.1.1.1", "port": True}],
            [{"protocol": "tcp", "address": "1.1.1.1", "port": 443, "x": 1}],
        ):
            with self.subTest(value=value), self.assertRaises(EgressError):
                parse_endpoints(value)

    def test_ruleset_defaults_to_drop_and_allows_exact_endpoints(self):
        rules = build_egress_ruleset(
            (
                EgressEndpoint("tcp", "10.0.2.2", 18443),
                EgressEndpoint("tcp", "1.1.1.1", 80),
                EgressEndpoint("udp", "8.8.8.8", 53),
            ),
            loopback_tcp_ports={19090},
            loopback_udp_ports={5353},
        )
        self.assertIn("policy drop;", rules)
        self.assertIn("ct state established,related accept", rules)
        self.assertIn('oifname "lo" tcp dport { 18443, 19090 } accept', rules)
        self.assertIn('oifname "lo" udp dport { 5353 } accept', rules)
        self.assertIn("ip daddr 1.1.1.1 tcp dport 80 accept", rules)
        self.assertIn("ip daddr 8.8.8.8 udp dport 53 accept", rules)
        self.assertNotIn("1.1.1.1 tcp dport 443", rules)

    def test_gateway_names_and_private_address_are_bounded(self):
        gateway = EgressGateway.allocate()
        metadata = gateway.metadata()
        self.assertLessEqual(len(gateway.namespace), 15)
        self.assertLessEqual(len(gateway.host_interface), 15)
        self.assertLessEqual(len(gateway.guest_interface), 15)
        self.assertEqual(gateway.prefix_length, 30)
        self.assertEqual(metadata["mode"], "veth-nat")
        self.assertTrue(gateway.host_address.startswith("10.213."))
        self.assertTrue(gateway.guest_address.startswith("10.213."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
