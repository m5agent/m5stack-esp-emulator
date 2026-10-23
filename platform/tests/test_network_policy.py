#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from network_egress import EgressEndpoint  # noqa: E402
from network_policy import (  # noqa: E402
    NetworkPolicy,
    NetworkPolicyError,
    build_sandbox_command,
    namespace_capability,
    qemu_user_netdev,
)


class NetworkPolicyTests(unittest.TestCase):
    def test_default_policy_preserves_trusted_host_behavior(self):
        policy = NetworkPolicy.from_mapping(None)
        self.assertEqual(policy.isolation, "trusted-host")
        self.assertEqual(policy.egress, "native")
        self.assertEqual(
            qemu_user_netdev(nic="misc.esp32s3.wifi", policy=policy),
            "user,model=misc.esp32s3.wifi,id=wifi0",
        )
        self.assertIn(
            "malware safety",
            policy.evidence()["not_claimed"],
        )

    def test_isolated_lab_only_reaches_loopback_fixture_without_restrict(self):
        policy = NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "lab-only",
                "dns": "deny",
            }
        )
        self.assertEqual(policy.isolation, "namespace")
        self.assertEqual(policy.egress, "lab-only")
        self.assertEqual(
            qemu_user_netdev(nic="misc.esp32c6.wifi", policy=policy),
            "user,model=misc.esp32c6.wifi,id=wifi0",
        )
        deny = NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "deny-all",
                "dns": "deny",
            }
        )
        self.assertEqual(
            qemu_user_netdev(nic="misc.esp32c6.wifi", policy=deny),
            "user,restrict=yes,model=misc.esp32c6.wifi,id=wifi0",
        )

    def test_rejects_unsafe_or_incomplete_policies(self):
        for value in (
            {"isolation": "container"},
            {"isolation": "trusted-host", "egress": "deny-all"},
            {"isolation": "namespace", "egress": "deny-all", "dns": "slirp"},
            {"isolation": "namespace", "egress": "allowlist"},
        ):
            with self.subTest(value=value):
                with self.assertRaises(NetworkPolicyError):
                    NetworkPolicy.from_mapping(value)

    def test_allowlist_policy_requires_explicit_targets(self):
        policy = NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "deny",
                "allowed_hosts": [
                    "Allowed.Lab.Test",
                    "10.0.2.2",
                ],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "10.0.2.2",
                        "port": 18443,
                    }
                ],
            }
        )
        self.assertEqual(
            policy.allowed_hosts,
            ("10.0.2.2", "allowed.lab.test"),
        )
        self.assertEqual(
            policy.evidence()["allowed_hosts"],
            ["10.0.2.2", "allowed.lab.test"],
        )
        self.assertEqual(
            policy.evidence()["allowed_endpoints"],
            [
                {
                    "protocol": "tcp",
                    "address": "10.0.2.2",
                    "port": 18443,
                }
            ],
        )
        controlled = NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "controlled",
                "allowed_hosts": ["allowed.lab.test"],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "10.0.2.2",
                        "port": 18443,
                    }
                ],
            }
        )
        self.assertTrue(
            controlled.evidence()["controlled_resolver"]
        )
        endpoint_only = NetworkPolicy.from_mapping(
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "deny",
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "1.1.1.1",
                        "port": 80,
                    }
                ],
            }
        )
        self.assertEqual(
            endpoint_only.allowed_endpoints,
            (EgressEndpoint("tcp", "1.1.1.1", 80),),
        )
        for value in (
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "deny",
            },
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "deny",
                "allowed_hosts": ["bad host"],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "1.1.1.1",
                        "port": 80,
                    }
                ],
            },
            {
                "isolation": "namespace",
                "egress": "deny-all",
                "dns": "deny",
                "allowed_hosts": ["allowed.lab.test"],
            },
            {
                "isolation": "trusted-host",
                "egress": "native",
                "dns": "controlled",
            },
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "controlled",
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "1.1.1.1",
                        "port": 80,
                    }
                ],
            },
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "slirp",
                "allowed_hosts": ["allowed.lab.test"],
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "1.1.1.1",
                        "port": 80,
                    }
                ],
            },
            {
                "isolation": "namespace",
                "egress": "allowlist",
                "dns": "deny",
                "allowed_endpoints": [
                    {
                        "protocol": "tcp",
                        "address": "1.1.1.1",
                        "port": 0,
                    }
                ],
            },
        ):
            with self.subTest(value=value):
                with self.assertRaises(NetworkPolicyError):
                    NetworkPolicy.from_mapping(value)

    def test_namespace_builder_fails_closed(self):
        with mock.patch(
            "network_policy.namespace_capability",
            return_value={
                "status": "UNAVAILABLE",
                "checks": {},
                "errors": ["network namespace isolation requires Linux"],
            },
        ):
            with self.assertRaisesRegex(
                NetworkPolicyError,
                "requires Linux",
            ):
                build_sandbox_command(
                    ["qemu-system-xtensa"],
                    config_path=Path("/tmp/sandbox.json"),
                )
        self.assertIn("linux", namespace_capability()["checks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
