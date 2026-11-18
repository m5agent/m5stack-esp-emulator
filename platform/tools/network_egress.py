#!/usr/bin/env python3
"""Kernel-enforced destination policy for isolated QEMU networking."""
from __future__ import annotations

from collections.abc import Callable
import ipaddress
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

IP = "ip"
NFT = "nft"
NETNS_DIRECTORY = Path("/run/netns")
GATEWAY_COMMAND_TIMEOUT = 5
SLIRP_HOST_ADDRESS = ipaddress.ip_address("10.0.2.2")
SLIRP_HOST_ADDRESS_V6 = ipaddress.ip_address("fec0::2")
IPAddress: TypeAlias = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork: TypeAlias = ipaddress.IPv4Network | ipaddress.IPv6Network
EgressTarget: TypeAlias = IPAddress | IPNetwork
MIN_IPV4_PREFIX_LENGTH = 16
MIN_IPV6_PREFIX_LENGTH = 48
SPECIAL_IPV4_NETWORKS = (
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("224.0.0.0/4"),
)
SPECIAL_IPV6_NETWORKS = (
    ipaddress.IPv6Network("::/128"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("ff00::/8"),
)
IPV4_MAPPED_IPV6_NETWORK = ipaddress.IPv6Network("::ffff:0:0/96")
SLIRP_IPV4_NETWORK = ipaddress.IPv4Network("10.0.2.0/24")
SLIRP_IPV6_NETWORK = ipaddress.IPv6Network("fec0::/64")


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
            "network.policy.allowed_endpoints.address must be an IP or CIDR"
        )
    raw_address = address_value.strip()
    try:
        if "/" in raw_address:
            network = ipaddress.ip_network(raw_address, strict=False)
            if (
                isinstance(network, ipaddress.IPv6Network)
                and network.overlaps(IPV4_MAPPED_IPV6_NETWORK)
            ):
                raise EgressError(
                    "IPv4-mapped IPv6 CIDRs must use an IPv4 network"
                )
            minimum_prefix = (
                MIN_IPV4_PREFIX_LENGTH
                if network.version == 4
                else MIN_IPV6_PREFIX_LENGTH
            )
            if network.prefixlen < minimum_prefix:
                raise EgressError(
                    "network.policy.allowed_endpoints CIDR is too broad; "
                    f"IPv{network.version} requires /{minimum_prefix} "
                    "or narrower"
                )
            special_networks = (
                SPECIAL_IPV4_NETWORKS
                if isinstance(network, ipaddress.IPv4Network)
                else SPECIAL_IPV6_NETWORKS
            )
            if any(network.overlaps(item) for item in special_networks):
                raise EgressError(
                    "network.policy.allowed_endpoints CIDR cannot cover "
                    "unspecified, multicast, link-local or loopback space"
                )
            slirp_network = (
                SLIRP_IPV4_NETWORK
                if isinstance(network, ipaddress.IPv4Network)
                else SLIRP_IPV6_NETWORK
            )
            if network.overlaps(slirp_network):
                raise EgressError(
                    "network.policy.allowed_endpoints CIDR cannot cover "
                    "a QEMU SLiRP synthetic network; declare an exact "
                    "10.0.2.2 or fec0::2 endpoint instead"
                )
            address = str(network)
        else:
            parsed = ipaddress.ip_address(raw_address)
            if isinstance(parsed, ipaddress.IPv6Address):
                mapped = parsed.ipv4_mapped
                if mapped is not None:
                    parsed = mapped
            if (
                parsed.is_unspecified
                or parsed.is_multicast
                or parsed.is_loopback
                or parsed.is_link_local
            ):
                raise EgressError(
                    "network.policy.allowed_endpoints.address cannot be "
                    "unspecified, multicast, loopback or link-local; "
                    "use the QEMU SLiRP 10.0.2.2 or fec0::2 host address"
                )
            address = str(parsed)
    except EgressError:
        raise
    except ValueError as error:
        raise EgressError(
            "network.policy.allowed_endpoints.address must be an IP or CIDR"
        ) from error
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise EgressError(
            "network.policy.allowed_endpoints.port must be from 1 to 65535"
        )
    return EgressEndpoint(
        protocol=protocol,
        address=address,
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


def translated_address(endpoint: EgressEndpoint) -> EgressTarget:
    if "/" in endpoint.address:
        return ipaddress.ip_network(endpoint.address, strict=False)
    address = ipaddress.ip_address(endpoint.address)
    if address == SLIRP_HOST_ADDRESS:
        return ipaddress.ip_address("127.0.0.1")
    if address == SLIRP_HOST_ADDRESS_V6:
        return ipaddress.ip_address("::1")
    return address


def endpoint_contains_address(
    endpoint: EgressEndpoint,
    address: IPAddress,
) -> bool:
    target: EgressTarget = (
        ipaddress.ip_network(endpoint.address, strict=False)
        if "/" in endpoint.address
        else ipaddress.ip_address(endpoint.address)
    )
    if isinstance(target, IPNetwork):
        return address.version == target.version and address in target
    return address == target


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


def _run(command: list[str], *, body: str | None = None) -> str:
    try:
        completed = subprocess.run(
            command, input=body, text=True, capture_output=True, check=False,
            timeout=GATEWAY_COMMAND_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EgressError(f"egress gateway command unavailable ({' '.join(command)})") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise EgressError(
            f"egress gateway command failed ({' '.join(command)}): {detail}"
        )
    return completed.stdout


def _objects(command: list[str], *, key: str | None = None) -> list[dict]:
    try:
        result = json.loads(_run(command))
    except ValueError as error:
        raise EgressError("gateway kernel inspection returned invalid JSON") from error
    if key is not None:
        result = result.get(key) if isinstance(result, dict) else None
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        raise EgressError("gateway kernel inspection returned invalid objects")
    return result


def _remove_owned(probe, expected, delete: list[str]) -> bool:
    try:
        actual = probe()
        if actual is None:
            return True
        if actual != expected:
            return False
        _run(delete)
        return probe() is None
    except EgressError:
        return False


def _default_interface(family: int, *, required: bool = True) -> str:
    try:
        output = _run([IP, f"-{family}", "route", "show", "default"])
    except EgressError as error:
        if not required:
            return ""
        raise EgressError(
            f"cannot inspect the worker IPv{family} default route"
        ) from error
    for line in output.splitlines():
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
    _token: str = field(default_factory=lambda: secrets.token_hex(16), repr=False)
    _namespace_id: tuple[int, int] | None = field(default=None, init=False)
    _host_ifindex: int | None = field(default=None, init=False)
    _nat_handle: int | None = field(default=None, init=False)

    @classmethod
    def allocate(cls, *, ipv6_required: bool = False) -> EgressGateway:
        token = secrets.token_hex(16)
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
            _token=token,
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

    @property
    def _nat_owner(self) -> str:
        return "m5-gateway:" + self._token

    def ownership(self) -> dict:
        """Return the observed identities of this launch's kernel objects."""
        return {
            "token": self._token,
            "namespace": (dict(zip(("device", "inode"), self._namespace_id)) if self._namespace_id is not None else None),
            "host_link": {"ifindex": self._host_ifindex} if self._host_ifindex is not None else None,
            "nat_table": {"family": "inet", "handle": self._nat_handle} if self._nat_handle is not None else None,
        }

    def _inspect_namespace(self) -> tuple[int, int] | None:
        binding = NETNS_DIRECTORY / self.namespace
        try:
            info = binding.lstat()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise EgressError("cannot inspect gateway namespace binding") from error
        if not stat.S_ISREG(info.st_mode):
            raise EgressError("gateway namespace binding is not a regular namespace handle")
        return info.st_dev, info.st_ino

    def _inspect_host_link(self) -> int | None:
        links = _objects([IP, "-j", "link", "show"])
        if any(not isinstance(link.get("ifname"), str) or type(link.get("ifindex")) is not int for link in links):
            raise EgressError("cannot inspect gateway host link identity")
        return next((link["ifindex"] for link in links if link["ifname"] == self.host_interface), None)

    def _inspect_nat_table(self) -> tuple[int, str | None] | None:
        objects = _objects([NFT, "-j", "-a", "list", "ruleset"], key="nftables")
        for entry in objects:
            if "table" not in entry:
                continue
            table = entry["table"]
            if not isinstance(table, dict) or not isinstance(table.get("family"), str) or not isinstance(table.get("name"), str):
                raise EgressError("cannot inspect gateway NAT table identity")
            if table["family"] == "inet" and table["name"] == self.nat_table:
                handle, owner = table.get("handle"), table.get("comment")
                if type(handle) is not int or handle <= 0 or owner is not None and not isinstance(owner, str):
                    raise EgressError("cannot inspect gateway NAT table ownership")
                return handle, owner
        return None

    def start(self, *, on_ownership_change: Callable[[dict], None] | None = None) -> None:
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
            self._namespace_id = self._inspect_namespace()
            if self._namespace_id is None:
                raise EgressError("gateway namespace binding disappeared after creation")
            if on_ownership_change is not None:
                on_ownership_change(self.ownership())
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
            self._host_ifindex = self._inspect_host_link()
            if self._host_ifindex is None:
                raise EgressError("gateway host link disappeared after creation")
            if on_ownership_change is not None:
                on_ownership_change(self.ownership())
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
                    f"ip saddr {self.guest_address} "
                    f"oifname {json.dumps(self.default_interface)} masquerade"
                )
            ]
            if (
                self.ipv6_required
                and self.default_ipv6_interface
            ):
                nat_rules.append(
                    (
                        f"ip6 saddr {self.guest_ipv6_address} "
                        f"oifname {json.dumps(self.default_ipv6_interface)} "
                        "masquerade"
                    )
                )
            nat_script = "\n".join(
                [
                    f'create table inet {self.nat_table} {{ comment "{self._nat_owner}"; }}',
                    f"add chain inet {self.nat_table} postrouting {{ type nat hook postrouting priority srcnat; policy accept; }}",
                    *(f"add rule inet {self.nat_table} postrouting {rule}" for rule in nat_rules),
                    "",
                ]
            )
            _run([NFT, "-f", "-"], body=nat_script)
            table = self._inspect_nat_table()
            if table is None or table[1] != self._nat_owner:
                raise EgressError("gateway NAT table owner did not match after creation")
            self._nat_handle = table[0]
            if on_ownership_change is not None:
                on_ownership_change(self.ownership())
            self.started = True
        except (EgressError, OSError):
            self.cleanup()
            raise

    def cleanup(self) -> dict[str, bool]:
        """Close only positively matched objects and recheck their absence."""
        closed = {
            "host_link_removed": _remove_owned(
                self._inspect_host_link, self._host_ifindex, [IP, "link", "delete", "dev", self.host_interface],
            ),
            "nat_table_removed": _remove_owned(
                self._inspect_nat_table, (self._nat_handle, self._nat_owner),
                [NFT, "delete", "table", "inet", "handle", str(self._nat_handle)],
            ),
            "namespace_removed": _remove_owned(
                self._inspect_namespace, self._namespace_id, [IP, "netns", "delete", self.namespace],
            ),
        }
        if all(closed.values()):
            self.started = False
        return closed


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
