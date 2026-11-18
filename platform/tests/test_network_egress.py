#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class GatewayOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.gateway = EgressGateway.allocate(ipv6_required=True)
        self.netns_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.binding = self.netns_dir / self.gateway.namespace
        self.host_link = None
        self.nat_table = None
        self.commands = []
        self.fail_command = None
        self.keep_nat_after_delete = False
        self.enterContext(patch("network_egress.NETNS_DIRECTORY", self.netns_dir))
        self.enterContext(patch("network_egress._require_binary"))
        self.enterContext(patch("network_egress._require_forwarding"))
        self.enterContext(patch("network_egress._default_interface", return_value="eth2"))
        self.enterContext(patch("network_egress._run", side_effect=self.kernel_command))

    def kernel_command(self, argv, *, body=None):
        gateway = self.gateway
        self.commands.append((argv, body))
        if argv == self.fail_command:
            raise EgressError("forced kernel command failure")
        if argv == ["ip", "netns", "add", gateway.namespace]:
            if self.binding.exists():
                raise EgressError("namespace already exists")
            self.binding.touch()
        elif argv == ["ip", "netns", "delete", gateway.namespace]:
            self.binding.unlink()
        elif argv[:3] == ["ip", "link", "add"]:
            self.host_link = {"ifname": gateway.host_interface, "ifindex": 20}
        elif argv == ["ip", "link", "delete", "dev", gateway.host_interface]:
            self.host_link = None
        elif argv == ["ip", "-j", "link", "show"]:
            return json.dumps([self.host_link] if self.host_link is not None else [])
        elif argv == ["nft", "-f", "-"]:
            if self.nat_table is not None:
                raise EgressError("table already exists")
            self.nat_table = {"family": "inet", "name": gateway.nat_table, "handle": 51,
                              "comment": "m5-gateway:" + gateway.ownership()["token"]}
        elif argv == ["nft", "-j", "-a", "list", "ruleset"]:
            return json.dumps({"nftables": [{"metainfo": {}}, *([{"table": self.nat_table}] if self.nat_table else [])]})
        elif argv == ["nft", "delete", "table", "inet", "handle", "51"] and not self.keep_nat_after_delete:
            self.nat_table = None
        return ""

    def test_start_receipts_bind_exact_objects_and_cleanup_checks_readback(self):
        states = []
        gateway = self.gateway
        gateway.start(on_ownership_change=states.append)
        self.assertEqual([list(key for key in row if row[key] is not None) for row in states],
                         [["token", "namespace"], ["token", "namespace", "host_link"],
                          ["token", "namespace", "host_link", "nat_table"]])
        binding = self.binding.stat()
        self.assertEqual(states[-1]["namespace"], {"device": binding.st_dev, "inode": binding.st_ino})
        self.assertEqual(states[-1]["host_link"], {"ifindex": 20})
        self.assertEqual(states[-1]["nat_table"], {"family": "inet", "handle": 51})
        script, = (body for argv, body in self.commands if argv == ["nft", "-f", "-"])
        self.assertIn(f'create table inet {gateway.nat_table} {{ comment "m5-gateway:{states[-1]["token"]}"; }}', script)
        self.assertIn(f'ip saddr {gateway.guest_address} oifname "eth2" masquerade', script)
        self.assertIn(f'ip6 saddr {gateway.guest_ipv6_address} oifname "eth2" masquerade', script)
        expected = {"host_link_removed": True, "nat_table_removed": True, "namespace_removed": True}
        self.assertEqual(gateway.cleanup(), expected)
        self.assertEqual(gateway.cleanup(), expected)
        self.assertIn((["nft", "delete", "table", "inet", "handle", "51"], None), self.commands)
        self.assertFalse(self.binding.exists())

    def test_failure_before_peer_move_removes_owned_host_link(self):
        gateway = self.gateway
        self.fail_command = ["ip", "addr", "add", f"{gateway.host_address}/{gateway.prefix_length}",
                             "dev", gateway.host_interface]
        with self.assertRaisesRegex(EgressError, "forced kernel command failure"):
            gateway.start()
        self.assertIsNone(self.host_link)
        self.assertFalse(self.binding.exists())
        self.assertIn((["ip", "link", "delete", "dev", gateway.host_interface], None), self.commands)

    def test_colliding_names_cannot_be_removed(self):
        gateway = self.gateway
        self.nat_table = {"family": "inet", "name": gateway.nat_table, "handle": 51, "comment": "other"}
        self.binding.touch()
        with self.assertRaisesRegex(EgressError, "namespace already exists"):
            gateway.start()
        self.assertTrue(self.binding.exists())
        self.binding.unlink()
        with self.assertRaisesRegex(EgressError, "table already exists"):
            gateway.start()
        self.assertEqual(self.nat_table["comment"], "other")
        self.assertFalse(any(argv[:2] == ["nft", "delete"] for argv, _ in self.commands))
        self.assertFalse(self.binding.exists())
        self.assertIsNone(self.host_link)

    def test_replaced_objects_and_unreadable_state_are_not_removed(self):
        gateway = self.gateway
        gateway.start()
        self.binding.rename(self.binding.with_suffix(".old"))
        self.binding.touch()
        self.host_link["ifindex"] = 21
        self.fail_command = ["nft", "-j", "-a", "list", "ruleset"]
        self.commands.clear()
        self.assertEqual(gateway.cleanup(), {"host_link_removed": False, "nat_table_removed": False,
                                             "namespace_removed": False})
        self.assertFalse(any("delete" in argv for argv, _ in self.commands))

    def test_successful_delete_without_absence_observation_stays_pending(self):
        gateway = self.gateway
        gateway.start()
        self.keep_nat_after_delete = True
        self.assertEqual(gateway.cleanup(), {"host_link_removed": True, "nat_table_removed": False,
                                             "namespace_removed": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
