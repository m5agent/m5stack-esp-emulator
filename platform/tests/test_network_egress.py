#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
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
    endpoint_contains_address,
    parse_endpoints,
    requires_external_gateway,
    requires_external_ipv6,
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
                {
                    "protocol": "tcp",
                    "address": "2001:db8:6d35::1",
                    "port": 443,
                },
                {
                    "protocol": "tcp",
                    "address": "fec0::2",
                    "port": 18443,
                },
            ]
        )
        self.assertEqual(
            endpoints,
            (
                EgressEndpoint("tcp", "1.1.1.1", 443),
                EgressEndpoint("tcp", "2001:db8:6d35::1", 443),
                EgressEndpoint("tcp", "fec0::2", 18443),
                EgressEndpoint("udp", "10.0.2.2", 53),
            ),
        )
        self.assertEqual(
            str(translated_address(endpoints[2])),
            "::1",
        )
        self.assertEqual(
            str(translated_address(endpoints[3])),
            "127.0.0.1",
        )
        self.assertTrue(requires_external_gateway(endpoints))
        self.assertTrue(requires_external_ipv6(endpoints))
        self.assertFalse(
            requires_external_gateway(
                (EgressEndpoint("tcp", "10.0.2.2", 18443),)
            )
        )
        self.assertFalse(
            requires_external_gateway(
                (
                    EgressEndpoint("tcp", "10.0.2.2", 18443),
                    EgressEndpoint("tcp", "fec0::2", 18443),
                )
            )
        )
        self.assertFalse(
            requires_external_ipv6(
                (EgressEndpoint("tcp", "10.0.2.2", 18443),)
            )
        )
        self.assertFalse(
            requires_external_ipv6(
                (EgressEndpoint("tcp", "fec0::2", 18443),)
            )
        )

    def test_rejects_unsafe_or_unsupported_endpoints(self):
        for value in (
            [{"protocol": "icmp", "address": "1.1.1.1", "port": 1}],
            [{"protocol": "tcp", "address": "example.com", "port": 443}],
            [{"protocol": "tcp", "address": "0.0.0.0", "port": 443}],
            [{"protocol": "tcp", "address": "224.0.0.1", "port": 443}],
            [{"protocol": "tcp", "address": "127.0.0.1", "port": 443}],
            [{"protocol": "tcp", "address": "169.254.1.1", "port": 443}],
            [{"protocol": "tcp", "address": "::", "port": 443}],
            [{"protocol": "tcp", "address": "ff02::1", "port": 443}],
            [{"protocol": "tcp", "address": "::1", "port": 443}],
            [{"protocol": "tcp", "address": "fe80::1", "port": 443}],
            [{"protocol": "tcp", "address": "::ffff:127.0.0.1", "port": 443}],
            [{"protocol": "tcp", "address": "1.1.1.1", "port": 0}],
            [{"protocol": "tcp", "address": "1.1.1.1", "port": True}],
            [{"protocol": "tcp", "address": "1.1.1.1", "port": 443, "x": 1}],
        ):
            with self.subTest(value=value), self.assertRaises(EgressError):
                parse_endpoints(value)

    def test_ipv4_mapped_ipv6_is_canonicalized_to_ipv4(self):
        endpoints = parse_endpoints(
            [
                {
                    "protocol": "tcp",
                    "address": "::ffff:1.1.1.1",
                    "port": 443,
                }
            ]
        )
        self.assertEqual(
            endpoints,
            (EgressEndpoint("tcp", "1.1.1.1", 443),),
        )
        self.assertFalse(requires_external_ipv6(endpoints))

    def test_cidr_endpoints_are_canonicalized_and_bounded(self):
        endpoints = parse_endpoints(
            [
                {
                    "protocol": "tcp",
                    "address": "10.203.0.7/30",
                    "port": 8443,
                },
                {
                    "protocol": "udp",
                    "address": "2001:db8:6d35:1::abcd/64",
                    "port": 5353,
                },
            ]
        )
        self.assertEqual(
            endpoints,
            (
                EgressEndpoint("tcp", "10.203.0.4/30", 8443),
                EgressEndpoint("udp", "2001:db8:6d35:1::/64", 5353),
            ),
        )
        self.assertEqual(
            str(translated_address(endpoints[0])),
            "10.203.0.4/30",
        )
        self.assertTrue(
            endpoint_contains_address(
                endpoints[0],
                ipaddress.ip_address("10.203.0.6"),
            )
        )
        self.assertFalse(
            endpoint_contains_address(
                endpoints[0],
                ipaddress.ip_address("10.203.0.8"),
            )
        )
        self.assertTrue(requires_external_gateway(endpoints))
        self.assertTrue(requires_external_ipv6(endpoints))
        rules = build_egress_ruleset(
            endpoints,
            loopback_tcp_ports=set(),
            loopback_udp_ports=set(),
        )
        self.assertIn(
            "ip daddr 10.203.0.4/30 tcp dport 8443 accept",
            rules,
        )
        self.assertIn(
            "ip6 daddr 2001:db8:6d35:1::/64 udp dport 5353 accept",
            rules,
        )

    def test_cidr_endpoints_reject_broad_special_mapped_and_slirp_space(self):
        for address in (
            "1.1.0.0/15",
            "2001:db8::/47",
            "0.0.0.0/16",
            "127.0.0.0/16",
            "169.254.0.0/24",
            "224.0.0.0/24",
            "::/48",
            "::1/128",
            "fe80::/64",
            "ff00::/64",
            "::ffff:0:0/95",
            "10.0.2.0/24",
            "fec0::/64",
        ):
            with self.subTest(address=address), self.assertRaises(EgressError):
                parse_endpoints(
                    [
                        {
                            "protocol": "tcp",
                            "address": address,
                            "port": 443,
                        }
                    ]
                )

    def test_ruleset_defaults_to_drop_and_allows_exact_endpoints(self):
        rules = build_egress_ruleset(
            (
                EgressEndpoint("tcp", "10.0.2.2", 18443),
                EgressEndpoint("tcp", "1.1.1.1", 80),
                EgressEndpoint("udp", "8.8.8.8", 53),
                EgressEndpoint("tcp", "2001:db8:6d35::1", 443),
            ),
            loopback_tcp_ports={19090},
            loopback_udp_ports={5353},
        )
        self.assertIn("policy drop;", rules)
        self.assertIn("ct state established,related accept", rules)
        self.assertIn(
            "icmpv6 type { nd-neighbor-solicit, nd-neighbor-advert } accept",
            rules,
        )
        self.assertIn('oifname "lo" tcp dport { 18443, 19090 } accept', rules)
        self.assertIn('oifname "lo" udp dport { 5353 } accept', rules)
        self.assertIn("ip daddr 1.1.1.1 tcp dport 80 accept", rules)
        self.assertIn("ip daddr 8.8.8.8 udp dport 53 accept", rules)
        self.assertIn(
            "ip6 daddr 2001:db8:6d35::1 tcp dport 443 accept",
            rules,
        )
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
        self.assertFalse(gateway.ipv6_required)
        self.assertEqual(metadata["ipv6_prefix_length"], 126)

    def test_gateway_allocates_private_ipv6_when_required(self):
        gateway = EgressGateway.allocate(ipv6_required=True)
        metadata = gateway.metadata()
        self.assertTrue(gateway.ipv6_required)
        self.assertTrue(metadata["host_ipv6_address"].startswith("fd6d:"))
        self.assertTrue(metadata["guest_ipv6_address"].startswith("fd6d:"))
        self.assertEqual(
            metadata["host_ipv6_address"].rsplit(":", 1)[1],
            "1",
        )
        self.assertEqual(
            metadata["guest_ipv6_address"].rsplit(":", 1)[1],
            "2",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
