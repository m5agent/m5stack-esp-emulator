from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "platform/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import device_service
import device_service_errors
import device_service_network
from network_egress import EgressEndpoint


class DeviceServiceNetworkBoundaryTests(unittest.TestCase):
    def policy_value(self) -> dict:
        return {
            "isolation": "namespace",
            "egress": "allowlist",
            "dns": "controlled",
            "allowed_hosts": [
                "api.fixture.test",
                "origin.fixture.test",
            ],
            "allowed_domains": ["service.fixture.test"],
        }

    def test_network_policy_preserves_implicit_endpoint_merge(self):
        endpoint = EgressEndpoint("tcp", "10.0.2.2", 18443)
        policy = device_service_network.parse_network_policy(
            self.policy_value(),
            implicit_endpoints=(endpoint,),
        )
        self.assertEqual(policy.allowed_endpoints, (endpoint,))

    def test_network_policy_preserves_error_contract(self):
        with self.assertRaises(device_service_errors.ServiceError) as caught:
            device_service_network.parse_network_policy(
                {
                    "isolation": "trusted-host",
                    "egress": "allowlist",
                    "dns": "controlled",
                }
            )
        self.assertEqual(caught.exception.code, "invalid_network_policy")
        self.assertEqual(caught.exception.status, 400)

    def test_cname_records_are_bound_to_the_same_policy(self):
        policy = device_service_network.parse_network_policy(
            self.policy_value(),
            implicit_endpoints=(
                EgressEndpoint("tcp", "10.0.2.2", 18443),
            ),
        )
        records = {
            "api.fixture.test": "edge.service.fixture.test",
            "edge.service.fixture.test": "origin.fixture.test",
        }
        self.assertEqual(
            device_service_network.parse_dns_cname_records(records, policy),
            records,
        )

    def test_cname_records_fail_closed_without_controlled_policy(self):
        native = device_service_network.parse_network_policy(None)
        with self.assertRaises(device_service_errors.ServiceError) as caught:
            device_service_network.parse_dns_cname_records(
                {
                    "api.fixture.test": "origin.fixture.test",
                },
                native,
            )
        self.assertEqual(caught.exception.code, "invalid_network")
        self.assertEqual(caught.exception.status, 400)

    def test_invalid_cname_target_is_rejected(self):
        policy = device_service_network.parse_network_policy(
            self.policy_value(),
            implicit_endpoints=(
                EgressEndpoint("tcp", "10.0.2.2", 18443),
            ),
        )
        with self.assertRaises(device_service_errors.ServiceError) as caught:
            device_service_network.parse_dns_cname_records(
                {
                    "api.fixture.test": "outside.test",
                },
                policy,
            )
        self.assertEqual(caught.exception.code, "invalid_network")
        self.assertEqual(caught.exception.status, 400)

    def test_reexported_network_parsers_keep_identity(self):
        self.assertIs(
            device_service.parse_network_policy,
            device_service_network.parse_network_policy,
        )
        self.assertIs(
            device_service.parse_dns_cname_records,
            device_service_network.parse_dns_cname_records,
        )


if __name__ == "__main__":
    unittest.main()
