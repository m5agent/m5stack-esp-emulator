"""Stateless Device Service parsers for network request data."""
from __future__ import annotations

from typing import Any

from device_service_errors import ServiceError
from network_egress import EgressEndpoint
from network_policy import NetworkPolicy, NetworkPolicyError
from network_sandbox import (
    STA_STREAM_PORTS, SandboxError, validate_cname_record_bindings,
    validate_exact_record_bindings, validate_sta_stream_fixture, validate_udp_fixture,
)


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


def parse_dns_host_records(
    value: Any,
    policy: NetworkPolicy,
    cname_records: dict[str, str],
) -> dict[str, str]:
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict) or len(value) > 32 or any(
        not isinstance(address, str) or "%" in address for address in value.values()
    ):
        raise ServiceError(
            "invalid_network",
            "network.dns_host_records requires at most 32 names mapped to IP addresses",
            400,
        )
    if policy.dns != "controlled":
        raise ServiceError("invalid_network", "network.dns_host_records requires controlled DNS", 400)
    try:
        records = validate_exact_record_bindings(value, policy.allowed_endpoints)
    except SandboxError as error:
        raise ServiceError("invalid_network", str(error), 400) from error
    names = set(records)
    if len(records) != len(value) or names.difference(policy.allowed_hosts) or names.intersection(cname_records):
        raise ServiceError(
            "invalid_network",
            "network.dns_host_records requires unique allowed hosts without CNAME aliases",
            400,
        )
    return {name: str(addresses[0]) for name, addresses in records.items()}


def parse_udp_fixture(value: Any) -> dict[str, int | str] | None:
    if value is None:
        return None
    try:
        return validate_udp_fixture(value)
    except SandboxError as error:
        raise ServiceError("invalid_network", str(error), 400) from error


def parse_sta_stream_fixtures(network: dict) -> dict[str, dict[str, str]]:
    try:
        return {key: validate_sta_stream_fixture(key, network[key])
                for key in STA_STREAM_PORTS if key in network}
    except SandboxError as error:
        raise ServiceError("invalid_network", str(error), 400) from error
