#!/usr/bin/env python3
"""Kernel-enforced destination policy for isolated QEMU networking."""
from __future__ import annotations

import ipaddress
import json
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

IP = "ip"
NFT = "nft"
SLIRP_HOST_ADDRESS = ipaddress.ip_address("10.0.2.2")
IPAddress: TypeAlias = ipaddress.IPv4Address | ipaddress.IPv6Address


class EgressError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class EgressEndpoint:
    protocol: str
    address: str
    port: int

    def as_dict(self) -> dict:
        return {
            "protocol": self.protocol,
            "address": self.address,
            "port": self.port,
        }


def parse_endpoint(value: object) -> EgressEndpoint:
    if not isinstance(value, dict):
        raise EgressError("network.policy.allowed_endpoints entries must be objects")
    unknown = set(value) - {"protocol", "address", "port"}
    if unknown:
        raise EgressError(
            "network.policy.allowed_endpoints contains unknown fields"
        )
    protocol = value.get("protocol")
    address_value = value.get("address")
    port = value.get("port")
    if protocol not in {"tcp", "udp"}:
        raise EgressError(
            "network.policy.allowed_endpoints.protocol must be tcp or udp"
        )
    if not isinstance(address_value, str) or not address_value.strip():
        raise EgressError(
            "network.policy.allowed_endpoints.address must be an IP address"
        )
    try:
        address = ipaddress.ip_address(address_value.strip())
    except ValueError as error:
        raise EgressError(
            "network.policy.allowed_endpoints.address must be an IP address"
        ) from error
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            address = mapped
    if address.is_unspecified or address.is_multicast:
        raise EgressError(
            "network.policy.allowed_endpoints.address cannot be unspecified "
            "or multicast"
        )
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise EgressError(
            "network.policy.allowed_endpoints.port must be from 1 to 65535"
        )
    return EgressEndpoint(
        protocol=protocol,
        address=str(address),
        port=port,
    )


def parse_endpoints(value: object) -> tuple[EgressEndpoint, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EgressError(
            "network.policy.allowed_endpoints must be an array"
        )
    if len(value) > 64:
        raise EgressError(
            "network.policy.allowed_endpoints exceeds 64 entries"
        )
    endpoints = tuple(sorted({parse_endpoint(item) for item in value}))
    return endpoints


def translated_address(endpoint: EgressEndpoint) -> IPAddress:
    address = ipaddress.ip_address(endpoint.address)
    if address == SLIRP_HOST_ADDRESS:
        return ipaddress.ip_address("127.0.0.1")
    return address


def requires_external_gateway(endpoints: tuple[EgressEndpoint, ...]) -> bool:
    return any(
        not translated_address(endpoint).is_loopback
        for endpoint in endpoints
    )


def requires_external_ipv6(endpoints: tuple[EgressEndpoint, ...]) -> bool:
    return any(
        (address := translated_address(endpoint)).version == 6
        and not address.is_loopback
        for endpoint in endpoints
    )


def _port_set(ports: set[int]) -> str:
    return "{ " + ", ".join(str(port) for port in sorted(ports)) + " }"


def build_egress_ruleset(
    endpoints: tuple[EgressEndpoint, ...],
    *,
    loopback_tcp_ports: set[int],
    loopback_udp_ports: set[int],
) -> str:
    loopback_tcp = set(loopback_tcp_ports)
    loopback_udp = set(loopback_udp_ports)
    external_rules: list[str] = []
    for endpoint in endpoints:
        address = translated_address(endpoint)
        if address.is_loopback:
            target = loopback_tcp if endpoint.protocol == "tcp" else loopback_udp
            target.add(endpoint.port)
            continue
        family = "ip" if address.version == 4 else "ip6"
        external_rules.append(
            f"    {family} daddr {address} "
            f"{endpoint.protocol} dport {endpoint.port} accept"
        )

    input_rules: list[str] = [
        "    ct state established,related accept",
    ]
    output_rules: list[str] = [
        "    ct state established,related accept",
    ]
    ipv6_neighbor_control = (
        "    icmpv6 type { nd-neighbor-solicit, "
        "nd-neighbor-advert } accept"
    )
    input_rules.append(ipv6_neighbor_control)
    output_rules.append(ipv6_neighbor_control)
    if loopback_tcp:
        ports = _port_set(loopback_tcp)
        input_rules.append(
            f'    iifname "lo" tcp dport {ports} accept'
        )
        output_rules.append(
            f'    oifname "lo" tcp dport {ports} accept'
        )
    if loopback_udp:
        ports = _port_set(loopback_udp)
        input_rules.append(
            f'    iifname "lo" udp dport {ports} accept'
        )
        output_rules.append(
            f'    oifname "lo" udp dport {ports} accept'
        )

    lines = [
        "table inet m5_egress {",
        "  chain input {",
        "    type filter hook input priority 0; policy drop;",
        *input_rules,
        "  }",
        "  chain output {",
        "    type filter hook output priority 0; policy drop;",
        *output_rules,
        *external_rules,
        "  }",
        "}",
    ]
    return "\n".join(lines) + "\n"


def install_egress_rules(
    endpoints: tuple[EgressEndpoint, ...],
    *,
    loopback_tcp_ports: set[int],
    loopback_udp_ports: set[int],
) -> None:
    _require_binary(NFT)
    ruleset = build_egress_ruleset(
        endpoints,
        loopback_tcp_ports=loopback_tcp_ports,
        loopback_udp_ports=loopback_udp_ports,
    )
    completed = subprocess.run(
        [NFT, "-f", "-"],
        input=ruleset,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise EgressError(f"cannot install egress nftables rules: {detail}")


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise EgressError(f"required egress helper is unavailable: {name}")
    return path


def _run(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise EgressError(
            f"egress gateway command failed ({' '.join(command)}): {detail}"
        )


def _default_interface(family: int, *, required: bool = True) -> str:
    completed = subprocess.run(
        [IP, f"-{family}", "route", "show", "default"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        if not required:
            return ""
        raise EgressError(
            f"cannot inspect the worker IPv{family} default route"
        )
    for line in completed.stdout.splitlines():
        fields = line.split()
        if "dev" in fields:
            index = fields.index("dev")
            if index + 1 < len(fields):
                return fields[index + 1]
    if not required:
        return ""
    raise EgressError(
        f"external egress requires a worker IPv{family} default route"
    )


def _require_forwarding(*, ipv6_required: bool) -> None:
    paths = [Path("/proc/sys/net/ipv4/ip_forward")]
    if ipv6_required:
        paths.append(Path("/proc/sys/net/ipv6/conf/all/forwarding"))
    for path in paths:
        family = "IPv6" if "ipv6" in str(path) else "IPv4"
        try:
            enabled = path.read_text().strip()
        except OSError as error:
            raise EgressError(
                f"cannot inspect {family} forwarding: {error}"
            ) from error
        if enabled != "1":
            raise EgressError(
                f"external egress requires {family} forwarding"
            )


@dataclass
class EgressGateway:
    namespace: str
    host_interface: str
    guest_interface: str
    host_address: str
    guest_address: str
    prefix_length: int
    default_interface: str
    default_ipv6_interface: str
    nat_table: str
    ipv6_required: bool
    host_ipv6_address: str
    guest_ipv6_address: str
    ipv6_prefix_length: int
    started: bool = False

    @classmethod
    def allocate(cls, *, ipv6_required: bool = False) -> EgressGateway:
        token = secrets.token_hex(8)
        index = int(token[:8], 16) % 16384
        third = (index >> 6) & 0xFF
        fourth = (index & 0x3F) * 4
        suffix = token[:6]
        ipv6_prefix = (
            f"fd6d:{token[:4]}:{token[4:8]}:{token[8:12]}"
        )
        return cls(
            namespace=f"m5eg-{suffix}",
            host_interface=f"m5h-{suffix}",
            guest_interface=f"m5g-{suffix}",
            host_address=f"10.213.{third}.{fourth + 1}",
            guest_address=f"10.213.{third}.{fourth + 2}",
            prefix_length=30,
            default_interface="",
            default_ipv6_interface="",
            nat_table=f"m5nat_{suffix}",
            ipv6_required=ipv6_required,
            host_ipv6_address=f"{ipv6_prefix}::1",
            guest_ipv6_address=f"{ipv6_prefix}::2",
            ipv6_prefix_length=126,
        )

    def metadata(self) -> dict:
        return {
            "mode": "veth-nat",
            "namespace": self.namespace,
            "host_interface": self.host_interface,
            "guest_interface": self.guest_interface,
            "host_address": self.host_address,
            "guest_address": self.guest_address,
            "prefix_length": self.prefix_length,
            "default_interface": self.default_interface,
            "default_ipv6_interface": self.default_ipv6_interface,
            "nat_table": self.nat_table,
            "ipv6_required": self.ipv6_required,
            "host_ipv6_address": self.host_ipv6_address,
            "guest_ipv6_address": self.guest_ipv6_address,
            "ipv6_prefix_length": self.ipv6_prefix_length,
        }

    def start(self) -> None:
        _require_binary(IP)
        _require_binary(NFT)
        _require_forwarding(ipv6_required=self.ipv6_required)
        self.default_interface = _default_interface(4)
        if self.ipv6_required:
            self.default_ipv6_interface = _default_interface(
                6,
                required=False,
            )
        try:
            _run([IP, "netns", "add", self.namespace])
            _run(
                [
                    IP,
                    "link",
                    "add",
                    self.host_interface,
                    "type",
                    "veth",
                    "peer",
                    "name",
                    self.guest_interface,
                ]
            )
            _run(
                [
                    IP,
                    "addr",
                    "add",
                    f"{self.host_address}/{self.prefix_length}",
                    "dev",
                    self.host_interface,
                ]
            )
            if self.ipv6_required:
                _run(
                    [
                        IP,
                        "-6",
                        "addr",
                        "add",
                        (
                            f"{self.host_ipv6_address}/"
                            f"{self.ipv6_prefix_length}"
                        ),
                        "dev",
                        self.host_interface,
                        "nodad",
                    ]
                )
            _run([IP, "link", "set", self.host_interface, "up"])
            _run(
                [
                    IP,
                    "link",
                    "set",
                    self.guest_interface,
                    "netns",
                    self.namespace,
                ]
            )
            _run(
                [
                    IP,
                    "-n",
                    self.namespace,
                    "link",
                    "set",
                    "lo",
                    "up",
                ]
            )
            _run(
                [
                    IP,
                    "-n",
                    self.namespace,
                    "link",
                    "set",
                    self.guest_interface,
                    "up",
                ]
            )
            _run(
                [
                    IP,
                    "-n",
                    self.namespace,
                    "addr",
                    "add",
                    f"{self.guest_address}/{self.prefix_length}",
                    "dev",
                    self.guest_interface,
                ]
            )
            if self.ipv6_required:
                _run(
                    [
                        IP,
                        "-6",
                        "-n",
                        self.namespace,
                        "addr",
                        "add",
                        (
                            f"{self.guest_ipv6_address}/"
                            f"{self.ipv6_prefix_length}"
                        ),
                        "dev",
                        self.guest_interface,
                        "nodad",
                    ]
                )
            _run(
                [
                    IP,
                    "-n",
                    self.namespace,
                    "route",
                    "add",
                    "default",
                    "via",
                    self.host_address,
                ]
            )
            if self.ipv6_required:
                _run(
                    [
                        IP,
                        "-6",
                        "-n",
                        self.namespace,
                        "route",
                        "add",
                        "default",
                        "via",
                        self.host_ipv6_address,
                    ]
                )
            nat_rules = [
                (
                    f'    ip saddr {self.guest_address} '
                    f'oifname "{self.default_interface}" masquerade'
                )
            ]
            if (
                self.ipv6_required
                and self.default_ipv6_interface
            ):
                nat_rules.append(
                    (
                        f"    ip6 saddr {self.guest_ipv6_address} "
                        f'oifname "{self.default_ipv6_interface}" '
                        "masquerade"
                    )
                )
            nat_script = "\n".join(
                [
                    f"table inet {self.nat_table} {{",
                    "  chain postrouting {",
                    (
                        "    type nat hook postrouting priority srcnat; "
                        "policy accept;"
                    ),
                    *nat_rules,
                    "  }",
                    "}",
                    "",
                ]
            )
            completed = subprocess.run(
                [NFT, "-f", "-"],
                input=nat_script,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise EgressError(
                    f"cannot install worker NAT rules: {detail}"
                )
            self.started = True
        except (EgressError, OSError):
            self.cleanup()
            raise

    def cleanup(self) -> None:
        if self.nat_table:
            try:
                subprocess.run(
                    [NFT, "delete", "table", "inet", self.nat_table],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError:
                pass
        if self.namespace:
            try:
                subprocess.run(
                    [IP, "netns", "delete", self.namespace],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError:
                pass
        self.started = False


def capability(
    *,
    require_gateway: bool = False,
    require_ipv6: bool = False,
) -> dict:
    checks = {
        "linux": sys.platform == "linux",
        "root": os.geteuid() == 0 if hasattr(os, "geteuid") else False,
        "nft": shutil.which(NFT) is not None,
    }
    if require_gateway or require_ipv6:
        checks["ip"] = shutil.which(IP) is not None
    if require_gateway:
        checks["ipv4_forwarding"] = False
        path = Path("/proc/sys/net/ipv4/ip_forward")
        if path.is_file():
            checks["ipv4_forwarding"] = path.read_text().strip() == "1"
    if require_ipv6:
        checks["ipv6_forwarding"] = False
        path = Path("/proc/sys/net/ipv6/conf/all/forwarding")
        if path.is_file():
            checks["ipv6_forwarding"] = path.read_text().strip() == "1"
    errors = [
        f"missing egress capability: {name}"
        for name, value in checks.items()
        if not value
    ]
    return {
        "status": "PASS" if not errors else "UNAVAILABLE",
        "checks": checks,
        "errors": errors,
    }


def main() -> int:
    print(json.dumps(capability(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
