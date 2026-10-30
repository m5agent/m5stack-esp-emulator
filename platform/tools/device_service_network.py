"""Stateless Device Service parsers for network request data."""
from __future__ import annotations

from typing import Any

from device_service_errors import ServiceError
from network_egress import EgressEndpoint
from network_policy import NetworkPolicy, NetworkPolicyError
from network_sandbox import SandboxError, validate_cname_record_bindings


def parse_network_policy(
    value: Any,
    *,
    implicit_endpoints: tuple[EgressEndpoint, ...] = (),
) -> NetworkPolicy:
    try:
        policy = NetworkPolicy.from_mapping(value)
        if policy.egress == "allowlist" and implicit_endpoints:
            policy = policy.with_allowed_endpoints(implicit_endpoints)
        if policy.dns == "controlled" and not policy.allowed_endpoints:
            raise NetworkPolicyError(
                "dns=controlled requires at least one allowed endpoint"
            )
        return policy
    except NetworkPolicyError as error:
        raise ServiceError(
            "invalid_network_policy",
            str(error),
            400,
        ) from error


def parse_dns_cname_records(
    value: Any,
    policy: NetworkPolicy,
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ServiceError(
            "invalid_network",
            "network.cname_records must be an object",
            400,
        )
    if value and (
        policy.egress != "allowlist"
        or policy.dns != "controlled"
    ):
        raise ServiceError(
            "invalid_network",
            "network.cname_records requires egress=allowlist and "
            "dns=controlled",
            400,
        )
    try:
        return validate_cname_record_bindings(
            value,
            policy.allowed_hosts,
            policy.allowed_hosts,
            policy.allowed_domains,
        )
    except SandboxError as error:
        raise ServiceError(
            "invalid_network",
            str(error),
            400,
        ) from error
