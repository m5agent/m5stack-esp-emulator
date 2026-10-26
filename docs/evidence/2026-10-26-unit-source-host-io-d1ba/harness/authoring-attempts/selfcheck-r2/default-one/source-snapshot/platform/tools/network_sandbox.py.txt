#!/usr/bin/env python3
"""Run a command inside a fail-closed Linux network namespace."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import ipaddress
import json
import os
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from network_egress import (
    EgressEndpoint,
    EgressError,
    EgressGateway,
    endpoint_contains_address,
    install_egress_rules,
    parse_endpoints,
    requires_external_gateway,
    requires_external_ipv6,
)
from network_egress import (
    capability as egress_capability,
)

SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
IFNAMSIZ = 16
IFREQ_SIZE = 40
MS_BIND = 4096
MS_REC = 16384
MS_PRIVATE = 1 << 18


class SandboxError(RuntimeError):
    pass


class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def normalize_host_name(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise SandboxError(f"{field} must contain host name strings")
    host = value.strip().lower()
    if not host:
        raise SandboxError(f"{field} contains an empty host name")
    if host.endswith("."):
        host = host[:-1]
        if not host or host.endswith("."):
            raise SandboxError(f"{field} contains an invalid trailing dot")
    if len(host) > 253 or any(
        not character.isascii()
        or not (character.isalnum() or character in {"-", "."})
        for character in host
    ):
        raise SandboxError(f"{field} contains an invalid host name")
    labels = host.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        for label in labels
    ):
        raise SandboxError(f"{field} contains an invalid host name")
    return host


def _normalize_authority_port(value: str) -> None:
    if not value or not value.isascii() or not value.isdigit():
        raise SandboxError("HTTP Host port is invalid")
    port = int(value)
    if not 1 <= port <= 65535:
        raise SandboxError("HTTP Host port is out of range")


def normalize_http_authority(value: str) -> str:
    """Parse the Host authority, including its optional numeric port."""
    if not isinstance(value, str):
        raise SandboxError("HTTP Host must be a string")
    raw = value.strip()
    if (
        not raw
        or value != raw
        or any(character.isspace() for character in raw)
        or any(character in raw for character in ",/@\\")
    ):
        raise SandboxError("HTTP Host authority is malformed")
    if raw.startswith("["):
        closing = raw.find("]")
        if closing <= 1:
            raise SandboxError("HTTP Host IPv6 literal is malformed")
        literal = raw[1:closing]
        remainder = raw[closing + 1 :]
        try:
            host = str(ipaddress.IPv6Address(literal))
        except ValueError as error:
            raise SandboxError("HTTP Host IPv6 literal is invalid") from error
        if remainder:
            if not remainder.startswith(":"):
                raise SandboxError("HTTP Host authority is malformed")
            _normalize_authority_port(remainder[1:])
        return host
    if raw.count(":") > 1:
        raise SandboxError(
            "HTTP Host IPv6 literals must use square brackets"
        )
    if ":" in raw:
        host_value, port_value = raw.rsplit(":", 1)
        _normalize_authority_port(port_value)
    else:
        host_value = raw
    return normalize_host_name(host_value, field="HTTP Host")


def domain_matches_suffix(host: str, suffix: str) -> bool:
    normalized_host = host.strip().lower().rstrip(".")
    normalized_suffix = suffix.strip().lower().rstrip(".")
    return bool(
        normalized_suffix
        and (
            normalized_host == normalized_suffix
            or normalized_host.endswith("." + normalized_suffix)
        )
    )


def normalize_domain_suffixes(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str)
        for item in value
    ):
        raise SandboxError("sandbox allowed_domains must be a string list")
    normalized = tuple(
        sorted(
            {
                item.strip().lower().rstrip(".")
                for item in value
            }
        )
    )
    for suffix in normalized:
        labels = suffix.split(".")
        if (
            "." not in suffix
            or len(suffix) > 253
            or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or not all(
                    character.isascii()
                    and (character.isalnum() or character == "-")
                    for character in label
                )
                for label in labels
            )
        ):
            raise SandboxError("sandbox allowed_domains contains an invalid suffix")
    return normalized


def normalize_allowed_hosts(
    value: object,
    *,
    field: str,
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str)
        for item in value
    ):
        raise SandboxError(f"{field} must be a string list")
    return tuple(
        sorted(
            {
                normalize_host_name(item, field=field)
                for item in value
            }
        )
    )


def install_controlled_resolv_conf(
    nameserver: str = "127.0.0.1",
) -> Path:
    try:
        address = ipaddress.ip_address(nameserver)
    except ValueError as error:
        raise SandboxError("controlled DNS nameserver is not an IP address") from error
    if address.is_unspecified or address.is_multicast:
        raise SandboxError("controlled DNS nameserver must be unicast")
    try:
        os.unshare(os.CLONE_NEWNS)
    except (AttributeError, OSError) as error:
        raise SandboxError(
            f"controlled DNS requires a private mount namespace: {error}"
        ) from error

    descriptor, raw_path = tempfile.mkstemp(
        prefix="m5-resolv-",
        suffix=".conf",
    )
    path = Path(raw_path)
    try:
        os.write(
            descriptor,
            (
                f"nameserver {address}\n"
                "options timeout:1 attempts:1\n"
            ).encode(),
        )
    finally:
        os.close(descriptor)

    libc = ctypes.CDLL(None, use_errno=True)
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    libc.mount.restype = ctypes.c_int
    if libc.mount(
        None,
        b"/",
        None,
        MS_REC | MS_PRIVATE,
        None,
    ) != 0:
        error = ctypes.get_errno()
        path.unlink(missing_ok=True)
        raise SandboxError(
            "cannot make mount namespace private: "
            f"{os.strerror(error)}"
        )
    target = Path("/etc/resolv.conf").resolve()
    if libc.mount(
        str(path).encode(),
        str(target).encode(),
        None,
        MS_BIND,
        None,
    ) != 0:
        error = ctypes.get_errno()
        path.unlink(missing_ok=True)
        raise SandboxError(
            "cannot bind controlled resolv.conf: "
            f"{os.strerror(error)}"
        )
    return path


def bring_loopback_up(interface: str = "lo") -> None:
    encoded = interface.encode("ascii")
    if not encoded or len(encoded) >= IFNAMSIZ:
        raise SandboxError(f"invalid interface name: {interface!r}")
    request = bytearray(IFREQ_SIZE)
    request[: len(encoded)] = encoded
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        response = fcntl.ioctl(sock.fileno(), SIOCGIFFLAGS, bytes(request))
        flags = struct.unpack_from("H", response, IFNAMSIZ)[0]
        struct.pack_into("H", request, IFNAMSIZ, flags | IFF_UP)
        fcntl.ioctl(sock.fileno(), SIOCSIFFLAGS, bytes(request))


def route_table_has_external_route(
    *,
    expected_interface: str | None = None,
    expected_gateway: str | None = None,
    expected_network: str | None = None,
    expected_ipv6_gateway: str | None = None,
    expected_ipv6_network: str | None = None,
) -> bool:
    path = Path("/proc/net/route")
    if not path.is_file():
        return True
    gateway_value = (
        int.from_bytes(socket.inet_aton(expected_gateway), "little")
        if expected_gateway
        else None
    )
    network_value = (
        int.from_bytes(socket.inet_aton(expected_network), "little")
        if expected_network
        else None
    )
    for line in path.read_text(errors="replace").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8:
            continue
        flags = int(fields[3], 16)
        if fields[0] == "lo" or not flags & 0x1:
            continue
        destination = int(fields[1], 16)
        gateway = int(fields[2], 16)
        if (
            expected_interface
            and fields[0] == expected_interface
            and (
                (
                    destination == 0
                    and gateway == gateway_value
                )
                or (
                    expected_network is not None
                    and destination == network_value
                    and gateway == 0
                )
            )
        ):
            continue
        return True
    ipv6 = Path("/proc/net/ipv6_route")
    if ipv6.is_file():
        ipv6_gateway_value = (
            ipaddress.IPv6Address(expected_ipv6_gateway).packed.hex()
            if expected_ipv6_gateway
            else None
        )
        ipv6_network = (
            ipaddress.ip_network(expected_ipv6_network, strict=False)
            if expected_ipv6_network
            else None
        )
        for line in ipv6.read_text(errors="replace").splitlines():
            fields = line.split()
            if not fields or fields[-1] == "lo":
                continue
            destination = fields[0] if fields else ""
            prefix_length = (
                int(fields[1], 16)
                if len(fields) > 1
                else -1
            )
            gateway = fields[4] if len(fields) > 4 else ""
            destination_network = None
            if destination and prefix_length >= 0:
                try:
                    destination_network = ipaddress.IPv6Network(
                        (
                            str(ipaddress.IPv6Address(int(destination, 16))),
                            prefix_length,
                        ),
                        strict=False,
                    )
                except ValueError:
                    destination_network = None
            if (
                expected_interface
                and fields[-1] == expected_interface
                and (
                    (
                        destination.startswith("fe8")
                        and prefix_length == 64
                    )
                    or (
                        destination.startswith("ff")
                        and prefix_length == 8
                    )
                    or (
                        destination == "0" * 32
                        and prefix_length == 0
                        and ipv6_gateway_value is not None
                        and gateway == ipv6_gateway_value
                    )
                    or (
                        ipv6_network is not None
                        and destination_network is not None
                        and destination_network.subnet_of(ipv6_network)
                        and gateway == "0" * 32
                    )
                )
            ):
                continue
            return True
    return False


def write_isolation_evidence(
    path: Path,
    config: dict[str, Any] | None = None,
    *,
    gateway: dict[str, Any] | None = None,
    external_route: bool = False,
) -> None:
    interfaces = sorted(name for _, name in socket.if_nameindex())
    policy = (config or {}).get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    http = (config or {}).get("http", {})
    if not isinstance(http, dict):
        http = {}
    dns = (config or {}).get("dns", {})
    if not isinstance(dns, dict):
        dns = {}
    control = (config or {}).get("control", {})
    if not isinstance(control, dict):
        control = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": sys.platform,
                "private_network_namespace": True,
                "interfaces": interfaces,
                "external_route": external_route,
                "egress": policy.get("egress", "deny-all"),
                "dns": policy.get("dns", "deny"),
                "allowed_hosts": policy.get("allowed_hosts", []),
                "allowed_domains": policy.get("allowed_domains", []),
                "allowed_endpoints": policy.get("allowed_endpoints", []),
                "control_tcp_ports": control.get("tcp_ports", []),
                "control_udp_ports": control.get("udp_ports", []),
                "egress_enforcement": (
                    "nftables-input-output-default-drop"
                    if policy.get("egress") == "allowlist"
                    else "namespace-no-external-route"
                ),
                "gateway": gateway,
                "tls_gateway": bool(http.get("tls")),
                "controlled_dns": dns.get("mode") == "controlled",
                "dns_records": dns.get("hosts", {}),
                "dns_domain_records": dns.get("domain_records", {}),
                "dns_cname_records": dns.get("cname_records", {}),
                "cleanup_completed": False,
            },
            indent=2,
        )
        + "\n"
    )


def update_isolation_evidence(
    path: Path,
    fields: dict[str, Any],
) -> None:
    try:
        evidence = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SandboxError(
            f"cannot update isolation evidence: {error}"
        ) from error
    if not isinstance(evidence, dict):
        raise SandboxError("isolation evidence must be an object")
    evidence.update(fields)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    temporary.replace(path)


class ControlledHttp:
    def __init__(
        self,
        *,
        port: int,
        body: bytes,
        log_path: Path | None,
        host: str = "127.0.0.1",
        allowed_hosts: tuple[str, ...] | None = None,
        allowed_domains: tuple[str, ...] | None = None,
        tls: dict[str, Any] | None = None,
    ):
        self.requests: list[dict[str, str]] = []
        self.lock = threading.Lock()
        self.allowed_hosts = (
            {
                host.strip().lower().rstrip(".")
                for host in allowed_hosts or ()
                if host.strip()
            }
            if allowed_hosts is not None
            else None
        )
        self.allowed_domains = (
            normalize_domain_suffixes(allowed_domains)
            if allowed_domains is not None
            else None
        )
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                host_values = self.headers.get_all("Host", [])
                host_header = host_values[0] if len(host_values) == 1 else ""
                enforce_host_policy = not (
                    owner.allowed_hosts is None
                    and owner.allowed_domains is None
                )
                host = ""
                if enforce_host_policy:
                    try:
                        host = normalize_http_authority(host_header)
                    except SandboxError:
                        host = ""
                allowed = not enforce_host_policy or (
                    len(host_values) == 1
                    and self.path.startswith("/")
                    and bool(
                        (
                            owner.allowed_hosts is not None
                            and host in owner.allowed_hosts
                        )
                        or (
                            owner.allowed_domains is not None
                            and host
                            and any(
                                domain_matches_suffix(host, suffix)
                                for suffix in owner.allowed_domains
                            )
                        )
                    )
                )
                status = 200 if allowed else 403
                request = {
                    "path": self.path,
                    "host": self.headers.get("Host", ""),
                }
                if (
                    owner.allowed_hosts is not None
                    or owner.allowed_domains is not None
                ):
                    request.update(
                        {
                            "decision": "allow" if allowed else "deny",
                            "status": str(status),
                        }
                    )
                with owner.lock:
                    owner.requests.append(request)
                    owner.persist()
                self.send_response(status)
                self.send_header("Content-Type", "text/plain")
                response_body = body if allowed else b"host not allowed\n"
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.log_path = log_path
        family = ipaddress.ip_address(host).version
        bind_address = (
            (host, port, 0, 0)
            if family == 6
            else (host, port)
        )
        server_class = (
            IPv6ThreadingHTTPServer
            if family == 6
            else ThreadingHTTPServer
        )
        self.server = server_class(bind_address, Handler)
        if tls is not None:
            certfile = tls.get("certfile")
            keyfile = tls.get("keyfile")
            if not isinstance(certfile, str) or not isinstance(keyfile, str):
                raise SandboxError("sandbox TLS certfile/keyfile are required")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile, keyfile)
            self.server.socket = context.wrap_socket(
                self.server.socket,
                server_side=True,
            )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="m5-sandbox-http",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def persist(self) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.log_path.with_name(
            f".{self.log_path.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(self.requests, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(self.log_path)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        with self.lock:
            self.persist()


class ControlledDns:
    MAX_CNAME_CHAIN = 8

    def __init__(
        self,
        *,
        host: str,
        port: int,
        records: dict[str, Any],
        log_path: Path | None,
        domain_records: dict[str, Any] | None = None,
        cname_records: dict[str, Any] | None = None,
    ):
        self.records = self.normalize_records(records)
        self.domain_records = self.normalize_domain_records(
            domain_records or {}
        )
        self.cname_records = self.normalize_cname_records(
            cname_records or {}
        )
        for alias in self.cname_records:
            if alias in self.records:
                raise SandboxError(
                    f"sandbox DNS CNAME {alias} conflicts with an exact A/AAAA record"
                )
            if alias in self.domain_records:
                raise SandboxError(
                    f"sandbox DNS CNAME {alias} conflicts with a domain suffix answer"
                )
            _, terminal = self.resolve_cname(alias)
            if not self.has_record_data(terminal):
                raise SandboxError(
                    f"sandbox DNS CNAME {alias} terminates at uncontrolled name "
                    f"{terminal}"
                )
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.log_path = log_path
        self.stop_event = threading.Event()
        family = ipaddress.ip_address(host).version
        self.socket = socket.socket(
            socket.AF_INET6 if family == 6 else socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_address = (host, port, 0, 0) if family == 6 else (host, port)
        self.socket.bind(bind_address)
        self.socket.settimeout(0.2)
        self.thread = threading.Thread(
            target=self.serve,
            name="m5-sandbox-dns",
            daemon=True,
        )

    @staticmethod
    def normalize_records(
        records: dict[str, Any],
    ) -> dict[str, tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]]:
        normalized = {}
        for raw_name, raw_addresses in records.items():
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise SandboxError("sandbox DNS record names must be strings")
            name = normalize_host_name(
                raw_name,
                field="sandbox DNS record names",
            )
            values = (
                [raw_addresses]
                if isinstance(raw_addresses, str)
                else list(raw_addresses)
                if isinstance(raw_addresses, tuple)
                else raw_addresses
            )
            if (
                not isinstance(values, list)
                or not values
                or len(values) > 8
                or any(
                    not isinstance(
                        value,
                        (
                            str,
                            ipaddress.IPv4Address,
                            ipaddress.IPv6Address,
                        ),
                    )
                    for value in values
                )
            ):
                raise SandboxError(
                    "sandbox DNS record addresses must be a string or "
                    "a non-empty list/tuple of at most 8 addresses"
                )
            addresses = []
            seen = set()
            for value in values:
                if isinstance(
                    value,
                    (ipaddress.IPv4Address, ipaddress.IPv6Address),
                ):
                    address = value
                else:
                    try:
                        address = ipaddress.ip_address(value.strip())
                    except ValueError as error:
                        raise SandboxError(
                            f"sandbox DNS record for {name} is not an IP address"
                        ) from error
                if (
                    isinstance(address, ipaddress.IPv6Address)
                    and address.ipv4_mapped is not None
                ):
                    raise SandboxError(
                        f"sandbox DNS record for {name} must use IPv4 "
                        "instead of an IPv4-mapped IPv6 address"
                    )
                if address.is_unspecified or address.is_multicast:
                    raise SandboxError(
                        f"sandbox DNS record for {name} is not a unicast address"
                    )
                if address in seen:
                    continue
                seen.add(address)
                addresses.append(address)
            normalized[name] = tuple(addresses)
        return normalized

    @classmethod
    def normalize_domain_records(
        cls,
        records: dict[str, Any],
    ) -> dict[
        str,
        tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...],
    ]:
        normalized = cls.normalize_records(records)
        normalize_domain_suffixes(tuple(normalized))
        return normalized

    @staticmethod
    def normalize_cname_records(records: dict[str, Any]) -> dict[str, str]:
        if not isinstance(records, dict):
            raise SandboxError(
                "sandbox DNS cname_records must be a record map"
            )
        if len(records) > 64:
            raise SandboxError(
                "sandbox DNS cname_records exceeds the 64-entry limit"
            )
        normalized: dict[str, str] = {}
        for raw_alias, raw_target in records.items():
            if not isinstance(raw_alias, str) or not isinstance(raw_target, str):
                raise SandboxError(
                    "sandbox DNS CNAME aliases and targets must be strings"
                )
            aliases = normalize_domain_suffixes((raw_alias,))
            targets = normalize_domain_suffixes((raw_target,))
            if not aliases or not targets:
                raise SandboxError(
                    "sandbox DNS CNAME aliases and targets must be "
                    "non-empty domain names"
                )
            alias = aliases[0]
            target = targets[0]
            if alias == target:
                raise SandboxError(
                    f"sandbox DNS CNAME {alias} cannot target itself"
                )
            if alias in normalized:
                raise SandboxError(
                    f"sandbox DNS CNAME {alias} appears more than once"
                )
            normalized[alias] = target
        return normalized

    def has_record_data(self, name: str) -> bool:
        if name in self.records:
            return True
        return any(
            domain_matches_suffix(name, suffix)
            for suffix in self.domain_records
        )

    def resolve_cname(self, name: str) -> tuple[list[tuple[str, str]], str]:
        chain: list[tuple[str, str]] = []
        seen: set[str] = set()
        current = name
        while current in self.cname_records:
            if current in seen:
                raise SandboxError(
                    f"sandbox DNS CNAME cycle detected at {current}"
                )
            if len(chain) >= self.MAX_CNAME_CHAIN:
                raise SandboxError(
                    "sandbox DNS CNAME chain exceeds 8 records"
                )
            seen.add(current)
            target = self.cname_records[current]
            chain.append((current, target))
            current = target
        if chain and not self.has_record_data(current):
            raise SandboxError(
                f"sandbox DNS CNAME {name} terminates at uncontrolled name "
                f"{current}"
            )
        return chain, current

    @staticmethod
    def encode_name(name: str) -> bytes:
        return (
            b"".join(
                bytes([len(label)]) + label.encode("ascii")
                for label in name.rstrip(".").split(".")
            )
            + b"\0"
        )

    @staticmethod
    def parse_question(query: bytes) -> tuple[str, int, int, int] | None:
        if len(query) < 17:
            return None
        offset = 12
        labels: list[str] = []
        while offset < len(query):
            length = query[offset]
            offset += 1
            if length == 0:
                break
            if length & 0xC0 or offset + length > len(query):
                return None
            label = query[offset : offset + length].decode(
                "ascii",
                errors="ignore",
            )
            if not label:
                return None
            labels.append(label)
            offset += length
        else:
            return None
        if not labels or offset + 4 > len(query):
            return None
        qtype, qclass = struct.unpack_from("!HH", query, offset)
        return ".".join(labels).lower(), qtype, qclass, offset + 4

    def response(self, query: bytes) -> bytes:
        question = self.parse_question(query)
        if question is None:
            return b""
        name, qtype, qclass, question_end = question
        cname_chain, terminal = self.resolve_cname(name)
        addresses = self.records.get(terminal)
        matched_rule = (
            f"exact:{terminal}" if addresses is not None else "none"
        )
        if addresses is None:
            for suffix in sorted(
                self.domain_records,
                key=len,
                reverse=True,
            ):
                if domain_matches_suffix(terminal, suffix):
                    addresses = self.domain_records[suffix]
                    matched_rule = f"suffix:{suffix}"
                    break
        allowed = addresses is not None
        answers: list[bytes] = []
        if allowed and qclass == 1:
            for owner, target in cname_chain:
                target_wire = self.encode_name(target)
                owner_wire = (
                    b"\xc0\x0c"
                    if owner == name
                    else self.encode_name(owner)
                )
                answers.append(
                    owner_wire
                    + struct.pack("!HHIH", 5, 1, 60, len(target_wire))
                    + target_wire
                )
        address = None
        if allowed and qclass == 1 and qtype in {1, 28}:
            address = next(
                (
                    item
                    for item in addresses or ()
                    if (
                        qtype == 1
                        and isinstance(item, ipaddress.IPv4Address)
                    )
                    or (
                        qtype == 28
                        and isinstance(item, ipaddress.IPv6Address)
                    )
                ),
                None,
            )
        answer_type = None
        if address is not None:
            record_type = 1 if qtype == 1 else 28
            owner_wire = (
                b"\xc0\x0c"
                if not cname_chain
                else self.encode_name(terminal)
            )
            answers.append(
                owner_wire
                + struct.pack("!HHIH", record_type, 1, 60, len(address.packed))
                + address.packed
            )
            answer_type = "A" if qtype == 1 else "AAAA"
        elif cname_chain and qclass == 1 and qtype == 5:
            answer_type = "CNAME"
        flags = 0x8180 if allowed else 0x8183
        response = (
            query[:2]
            + struct.pack("!HHHHH", flags, 1, len(answers), 0, 0)
            + query[12:question_end]
            + b"".join(answers)
        )
        status = (
            answer_type
            if answer_type is not None
            else "NOERROR_NO_A"
            if allowed and qtype == 1
            else "NOERROR_NO_AAAA"
            if allowed and qtype == 28
            else "NOERROR_NO_ANSWER"
            if allowed
            else "NXDOMAIN"
        )
        with self.lock:
            request = {
                "name": name,
                "qtype": str(qtype),
                "decision": "allow" if allowed else "deny",
                "status": status,
                "rule": matched_rule,
            }
            if cname_chain:
                request["cname_chain"] = [
                    {"owner": owner, "target": target}
                    for owner, target in cname_chain
                ]
                request["cname_terminal"] = terminal
            self.requests.append(request)
            self.persist()
        return response

    def serve(self) -> None:
        while not self.stop_event.is_set():
            try:
                query, peer = self.socket.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            response = self.response(query)
            if response:
                try:
                    self.socket.sendto(response, peer)
                except OSError:
                    break

    def persist(self) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.log_path.with_name(
            f".{self.log_path.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(self.requests, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(self.log_path)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        self.socket.close()
        self.thread.join(timeout=5)
        with self.lock:
            self.persist()


def start_logged_process(
    command: list[str],
    *,
    log_path: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w")
    environment = os.environ.copy()
    environment.update(env_overrides or {})
    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    setattr(process, "_m5_log", log)
    return process


def wait_for_text(
    path: Path,
    marker: str,
    *,
    timeout: float,
    process: subprocess.Popen,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and marker in path.read_text(errors="replace"):
            return
        if process.poll() is not None:
            raise SandboxError(
                f"process exited before log marker {marker!r}: "
                f"{process.returncode}"
            )
        time.sleep(0.1)
    raise SandboxError(f"timed out waiting for log marker {marker!r}")


def terminate_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SandboxError(f"invalid sandbox config: {error}") from error
    if not isinstance(value, dict):
        raise SandboxError("sandbox config must be an object")
    return value


def _port_values(value: object, *, field: str) -> set[int]:
    if value is None:
        return set()
    if not isinstance(value, list) or any(
        not isinstance(port, int)
        or isinstance(port, bool)
        or not 1 <= port <= 65535
        for port in value
    ):
        raise SandboxError(f"{field} must be a list of TCP/UDP ports")
    return set(value)


def _egress_endpoints(config: dict[str, Any]) -> tuple[EgressEndpoint, ...]:
    policy = config.get("policy")
    if not isinstance(policy, dict):
        raise SandboxError("sandbox policy config must be an object")
    try:
        return parse_endpoints(policy.get("allowed_endpoints", []))
    except EgressError as error:
        raise SandboxError(str(error)) from error


def validate_exact_record_bindings(
    records: dict[str, Any],
    endpoints: tuple[EgressEndpoint, ...],
) -> dict[
    str,
    tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...],
]:
    exact_records = ControlledDns.normalize_records(records)
    for name, addresses in exact_records.items():
        for address in addresses:
            if not any(
                endpoint_contains_address(endpoint, address)
                for endpoint in endpoints
            ):
                raise SandboxError(
                    f"sandbox DNS exact record {name} resolves to "
                    f"{address}, which is not covered by an allowed endpoint"
                )
    return exact_records


def validate_domain_record_bindings(
    records: dict[str, Any],
    allowed_domains: tuple[str, ...],
    endpoints: tuple[EgressEndpoint, ...],
) -> dict[
    str,
    tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...],
]:
    domain_records = ControlledDns.normalize_domain_records(records)
    if set(domain_records) != set(allowed_domains):
        raise SandboxError(
            "sandbox DNS domain_records must exactly match "
            "policy.allowed_domains"
        )
    for suffix, addresses in domain_records.items():
        for address in addresses:
            if not any(
                endpoint_contains_address(endpoint, address)
                for endpoint in endpoints
            ):
                raise SandboxError(
                    f"sandbox DNS suffix {suffix} resolves to "
                    f"{address}, which is not covered by an allowed endpoint"
                )
    return domain_records


def validate_cname_record_bindings(
    records: dict[str, Any],
    exact_hosts: tuple[str, ...],
    allowed_hosts: tuple[str, ...],
    allowed_domains: tuple[str, ...],
) -> dict[str, str]:
    cname_records = ControlledDns.normalize_cname_records(records)
    unauthorized_aliases = [
        alias
        for alias in cname_records
        if alias not in allowed_hosts
        and not any(
            domain_matches_suffix(alias, suffix)
            for suffix in allowed_domains
        )
    ]
    if unauthorized_aliases:
        raise SandboxError(
            "sandbox DNS CNAME aliases must be covered by "
            "policy.allowed_hosts or policy.allowed_domains: "
            + ", ".join(unauthorized_aliases)
        )
    expected_hosts = set(exact_hosts) | {
        alias for alias in cname_records if alias in allowed_hosts
    }
    if expected_hosts != set(allowed_hosts):
        raise SandboxError(
            "sandbox DNS hosts/CNAME aliases must exactly match "
            "policy.allowed_hosts"
        )
    return validate_cname_graph(
        cname_records,
        tuple(set(exact_hosts) - set(cname_records)),
        allowed_domains,
    )


def validate_cname_graph(
    records: dict[str, Any],
    exact_hosts: tuple[str, ...],
    domain_suffixes: tuple[str, ...],
) -> dict[str, str]:
    cname_records = ControlledDns.normalize_cname_records(records)
    for alias in cname_records:
        if alias in exact_hosts:
            raise SandboxError(
                f"sandbox DNS CNAME {alias} conflicts with an exact A/AAAA record"
            )
        if alias in domain_suffixes:
            raise SandboxError(
                f"sandbox DNS CNAME {alias} conflicts with a domain suffix answer"
            )
        seen: set[str] = set()
        current = alias
        hops = 0
        while current in cname_records:
            if current in seen:
                raise SandboxError(
                    f"sandbox DNS CNAME cycle detected at {current}"
                )
            if hops >= ControlledDns.MAX_CNAME_CHAIN:
                raise SandboxError(
                    "sandbox DNS CNAME chain exceeds 8 records"
                )
            seen.add(current)
            current = cname_records[current]
            hops += 1
        if current not in exact_hosts and not any(
            domain_matches_suffix(current, suffix)
            for suffix in domain_suffixes
        ):
            raise SandboxError(
                f"sandbox DNS CNAME {alias} terminates at uncontrolled name "
                f"{current}"
            )
    return cname_records


def _loopback_ports(config: dict[str, Any]) -> tuple[set[int], set[int]]:
    control = config.get("control", {})
    if not isinstance(control, dict):
        raise SandboxError("sandbox control config must be an object")
    tcp_ports = _port_values(
        control.get("tcp_ports"),
        field="sandbox control.tcp_ports",
    )
    udp_ports = _port_values(
        control.get("udp_ports"),
        field="sandbox control.udp_ports",
    )
    http = config.get("http")
    if isinstance(http, dict) and http.get("port") is not None:
        port = int(http["port"])
        if 1 <= port <= 65535:
            tcp_ports.add(port)
    dns = config.get("dns")
    if isinstance(dns, dict):
        port = int(dns.get("port", 53))
        if not 1 <= port <= 65535:
            raise SandboxError("sandbox DNS port is out of range")
        udp_ports.add(port)
    return tcp_ports, udp_ports


def run(
    config: dict[str, Any],
    command: list[str],
    *,
    create_namespace: bool = True,
    gateway: dict[str, Any] | None = None,
) -> int:
    if sys.platform != "linux":
        raise SandboxError("network namespace isolation requires Linux")
    if not command:
        raise SandboxError("a command is required after --")
    if create_namespace:
        try:
            os.unshare(os.CLONE_NEWNET)
        except (AttributeError, OSError) as error:
            raise SandboxError(
                f"cannot create network namespace: {error}"
            ) from error
    dns_config = config.get("dns")
    resolv_path: Path | None = None
    if dns_config is not None:
        if not isinstance(dns_config, dict):
            raise SandboxError("sandbox DNS config must be an object")
        resolv_path = install_controlled_resolv_conf(
            str(dns_config.get("host", "127.0.0.1"))
        )
    bring_loopback_up()
    if gateway is None and route_table_has_external_route():
        raise SandboxError(
            "network namespace still has an external route; refusing to run"
        )
    if gateway is not None:
        guest_address = str(gateway.get("guest_address", ""))
        try:
            network = str(
                ipaddress.ip_network(
                    f"{guest_address}/{gateway.get('prefix_length', 30)}",
                    strict=False,
                ).network_address
            )
        except ValueError as error:
            raise SandboxError("sandbox gateway metadata is invalid") from error
        expected_ipv6_gateway = None
        expected_ipv6_network = None
        if bool(gateway.get("ipv6_required")):
            guest_ipv6_address = str(gateway.get("guest_ipv6_address", ""))
            try:
                expected_ipv6_network = str(
                    ipaddress.ip_network(
                        (
                            f"{guest_ipv6_address}/"
                            f"{gateway.get('ipv6_prefix_length', 126)}"
                        ),
                        strict=False,
                    )
                )
                expected_ipv6_gateway = str(
                    ipaddress.IPv6Address(
                        str(gateway.get("host_ipv6_address", ""))
                    )
                )
            except ValueError as error:
                raise SandboxError(
                    "sandbox IPv6 gateway metadata is invalid"
                ) from error
        if route_table_has_external_route(
            expected_interface=str(gateway.get("guest_interface", "")),
            expected_gateway=str(gateway.get("host_address", "")),
            expected_network=network,
            expected_ipv6_gateway=expected_ipv6_gateway,
            expected_ipv6_network=expected_ipv6_network,
        ):
            raise SandboxError(
                "gateway namespace has an unexpected external route"
            )
    policy = config.get("policy")
    policy_egress = (
        policy.get("egress")
        if isinstance(policy, dict)
        else None
    )
    allowed_domains = (
        normalize_domain_suffixes(policy.get("allowed_domains"))
        if isinstance(policy, dict)
        else ()
    )
    endpoints: tuple[EgressEndpoint, ...] = ()
    loopback_tcp_ports: set[int] = set()
    loopback_udp_ports: set[int] = set()
    if policy_egress == "allowlist":
        endpoints = _egress_endpoints(config)
        loopback_tcp_ports, loopback_udp_ports = _loopback_ports(config)
        try:
            install_egress_rules(
                endpoints,
                loopback_tcp_ports=loopback_tcp_ports,
                loopback_udp_ports=loopback_udp_ports,
            )
        except EgressError as error:
            raise SandboxError(str(error)) from error
    evidence_path = config.get("isolation_evidence")
    if evidence_path:
        write_isolation_evidence(
            Path(str(evidence_path)),
            config,
            gateway=gateway,
            external_route=gateway is not None,
        )

    http_config = config.get("http")
    http: ControlledHttp | None = None
    dns: ControlledDns | None = None
    ble_process: subprocess.Popen[str] | None = None
    qemu_process: subprocess.Popen | None = None
    previous: dict[int, Any] = {}
    terminating = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal terminating
        if terminating:
            return
        terminating = True
        terminate_process(qemu_process)
        terminate_process(ble_process)
        raise SystemExit(143)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, stop)
    try:
        if dns_config is not None:
            if not isinstance(dns_config, dict):
                raise SandboxError("sandbox DNS config must be an object")
            records = dns_config.get("hosts", {})
            raw_domain_records = dns_config.get("domain_records", {})
            raw_cname_records = dns_config.get("cname_records", {})
            if not isinstance(records, dict):
                raise SandboxError("sandbox DNS hosts must be a record map")
            if not isinstance(raw_domain_records, dict):
                raise SandboxError(
                    "sandbox DNS domain_records must be a record map"
                )
            if not isinstance(raw_cname_records, dict):
                raise SandboxError(
                    "sandbox DNS cname_records must be a record map"
                )
            if not records and not raw_domain_records and not raw_cname_records:
                raise SandboxError(
                    "sandbox DNS requires hosts, domain_records or cname_records"
                )
            normalized_records = validate_exact_record_bindings(
                records,
                endpoints,
            )
            domain_records = validate_domain_record_bindings(
                raw_domain_records,
                allowed_domains,
                endpoints,
            )
            if isinstance(policy, dict):
                policy_hosts = normalize_allowed_hosts(
                    policy.get("allowed_hosts", []),
                    field="sandbox policy allowed_hosts",
                ) or ()
                policy_domains = normalize_domain_suffixes(
                    policy.get("allowed_domains", [])
                )
            else:
                policy_hosts = ()
                policy_domains = ()
            cname_records = validate_cname_record_bindings(
                raw_cname_records,
                tuple(normalized_records),
                policy_hosts,
                policy_domains,
            )
            raw_log = dns_config.get("log")
            dns = ControlledDns(
                host=str(dns_config.get("host", "127.0.0.1")),
                port=int(dns_config.get("port", 53)),
                records=normalized_records,
                log_path=Path(str(raw_log)) if raw_log else None,
                domain_records=domain_records,
                cname_records=cname_records,
            )
            dns.start()

        if http_config is not None:
            if not isinstance(http_config, dict):
                raise SandboxError("sandbox http config must be an object")
            port = int(http_config.get("port", 0))
            body = http_config.get("body", "M5_SANDBOX_OK\n")
            if not isinstance(body, str):
                raise SandboxError("sandbox HTTP body must be a string")
            raw_log = http_config.get("log")
            host = str(http_config.get("host", "127.0.0.1"))
            http_allowed_hosts = normalize_allowed_hosts(
                http_config.get("allowed_hosts"),
                field="sandbox http allowed_hosts",
            )
            policy_hosts = normalize_allowed_hosts(
                (
                    policy.get("allowed_hosts", [])
                    if isinstance(policy, dict)
                    else []
                ),
                field="sandbox policy allowed_hosts",
            ) or ()
            if http_allowed_hosts is None and policy_hosts:
                http_allowed_hosts = policy_hosts
            if not set(http_allowed_hosts or ()).issubset(policy_hosts):
                raise SandboxError(
                    "sandbox http allowed_hosts must be a subset of "
                    "policy.allowed_hosts"
                )
            raw_allowed_domains = http_config.get("allowed_domains")
            if raw_allowed_domains is None and allowed_domains:
                raw_allowed_domains = list(allowed_domains)
            http_allowed_domains = normalize_domain_suffixes(
                raw_allowed_domains
            )
            if not set(http_allowed_domains).issubset(allowed_domains):
                raise SandboxError(
                    "sandbox http allowed_domains must be a subset of "
                    "policy.allowed_domains"
                )
            tls_config = http_config.get("tls")
            if tls_config is not None and not isinstance(tls_config, dict):
                raise SandboxError("sandbox TLS config must be an object")
            http = ControlledHttp(
                port=port,
                body=body.encode(),
                log_path=Path(str(raw_log)) if raw_log else None,
                host=host,
                allowed_hosts=(
                    http_allowed_hosts
                    if http_allowed_hosts is not None
                    else None
                ),
                allowed_domains=(
                    http_allowed_domains
                    if raw_allowed_domains is not None
                    else None
                ),
                tls=tls_config,
            )
            http.start()

        ble_config = config.get("ble_probe")
        if ble_config is not None:
            if not isinstance(ble_config, dict):
                raise SandboxError("sandbox ble_probe config must be an object")
            ble_command = ble_config.get("command")
            ble_log = ble_config.get("log")
            if (
                not isinstance(ble_command, list)
                or not ble_command
                or any(not isinstance(item, str) for item in ble_command)
                or not isinstance(ble_log, str)
            ):
                raise SandboxError("sandbox ble_probe config is invalid")
            ble_env = ble_config.get("env", {})
            if not isinstance(ble_env, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in ble_env.items()
            ):
                raise SandboxError("sandbox ble_probe env is invalid")
            ble_process = start_logged_process(
                ble_command,
                log_path=Path(ble_log),
                env_overrides=ble_env,
            )
            wait_for_text(
                Path(ble_log),
                str(ble_config.get("ready_marker", "BLE_PROBE_READY")),
                timeout=float(ble_config.get("ready_timeout_seconds", 10)),
                process=ble_process,
            )

        qemu_process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return qemu_process.wait()
    finally:
        terminate_process(qemu_process)
        terminate_process(ble_process)
        if ble_process is not None:
            log = getattr(ble_process, "_m5_log", None)
            if log is not None:
                log.close()
        if http is not None:
            http.close()
        if dns is not None:
            dns.close()
        if resolv_path is not None:
            resolv_path.unlink(missing_ok=True)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if evidence_path:
            qemu_process_reaped = (
                qemu_process is None or qemu_process.poll() is not None
            )
            dns_closed = dns is None or not dns.thread.is_alive()
            http_closed = http is None or not http.thread.is_alive()
            update_isolation_evidence(
                Path(str(evidence_path)),
                {
                    "cleanup_completed": (
                        qemu_process_reaped
                        and dns_closed
                        and http_closed
                    ),
                    "qemu_process_reaped": qemu_process_reaped,
                    "dns_closed": dns_closed,
                    "http_closed": http_closed,
                },
            )


def run_with_gateway(
    config: dict[str, Any],
    command: list[str],
    *,
    config_path: Path,
) -> int:
    endpoints = _egress_endpoints(config)
    ipv6_required = requires_external_ipv6(endpoints)
    capability = egress_capability(
        require_gateway=True,
        require_ipv6=ipv6_required,
    )
    if capability["status"] != "PASS":
        raise SandboxError("; ".join(capability["errors"]))
    gateway = EgressGateway.allocate(ipv6_required=ipv6_required)
    process: subprocess.Popen | None = None
    previous: dict[int, Any] = {}
    terminating = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal terminating
        if terminating:
            return
        terminating = True
        terminate_process(process)
        raise SystemExit(143)

    try:
        gateway.start()
        inner_environment = os.environ.copy()
        inner_environment["M5_EGRESS_GATEWAY"] = json.dumps(
            gateway.metadata()
        )
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, stop)
        inner_command = [
            "ip",
            "netns",
            "exec",
            gateway.namespace,
            sys.executable,
            str(Path(__file__).resolve()),
            "--inner",
            "--config",
            str(config_path),
            "--",
            *command,
        ]
        process = subprocess.Popen(
            inner_command,
            cwd=Path.cwd(),
            env=inner_environment,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return process.wait()
    finally:
        terminate_process(process)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        gateway.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a QEMU command inside a no-egress network namespace"
    )
    parser.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    try:
        config = load_config(args.config)
        if args.inner:
            raw_gateway = os.environ.get("M5_EGRESS_GATEWAY")
            gateway = json.loads(raw_gateway) if raw_gateway else None
            if gateway is not None and not isinstance(gateway, dict):
                raise SandboxError("gateway metadata must be an object")
            return run(
                config,
                command,
                create_namespace=False,
                gateway=gateway,
            )
        policy = config.get("policy")
        if isinstance(policy, dict) and policy.get("egress") == "allowlist":
            endpoints = _egress_endpoints(config)
            if requires_external_gateway(endpoints):
                return run_with_gateway(
                    config,
                    command,
                    config_path=args.config,
                )
        return run(config, command)
    except (json.JSONDecodeError, OSError, EgressError, SandboxError) as error:
        print(f"network sandbox failed: {error}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
