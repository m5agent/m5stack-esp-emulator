#!/usr/bin/env python3
"""Create a fail-closed Linux L2 fabric for multiple QEMU guests."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IP = "ip"
NFT = "nft"
BRIDGE_ADDRESS = "10.230.0.1"
GUEST_ADDRESSES = ("10.230.0.2", "10.230.0.3")
GUEST_MACS = (
    "02:4d:35:00:00:01",
    "02:4d:35:00:00:02",
)
DHCP_MAGIC = b"\x63\x82\x53\x63"
ETH_P_ALL = 0x0003
ETH_P_IP = 0x0800
IPPROTO_UDP = 17
MAX_PENDING_SWITCH_FRAMES = 256


class LabFabricError(RuntimeError):
    pass


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise LabFabricError(f"required fabric helper is unavailable: {name}")
    return path


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise LabFabricError(
            f"fabric command failed ({' '.join(command)}): {detail}"
        )
    return completed


def build_fabric_ruleset(
    *,
    bridge: str,
    taps: tuple[str, ...],
) -> str:
    if len(taps) != 2:
        raise LabFabricError("the lab fabric requires exactly two TAP endpoints")
    first, second = taps
    return (
        "table inet m5_lab {\n"
        "  chain input {\n"
        "    type filter hook input priority 0; policy drop;\n"
        "    ct state established,related accept\n"
        '    iifname "lo" accept\n'
        f'    iifname "{bridge}" udp dport 67 accept\n'
        "  }\n"
        "  chain output {\n"
        "    type filter hook output priority 0; policy drop;\n"
        "    ct state established,related accept\n"
        '    oifname "lo" accept\n'
        f'    oifname "{bridge}" udp sport 67 accept\n'
        "  }\n"
        "  chain forward {\n"
        "    type filter hook forward priority 0; policy drop;\n"
        f'    iifname "{first}" oifname "{second}" accept\n'
        f'    iifname "{second}" oifname "{first}" accept\n'
        "  }\n"
        "}\n"
    )


@dataclass(frozen=True)
class FabricEndpoint:
    index: int
    tap: str
    mac: str
    address: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tap": self.tap,
            "mac": self.mac,
            "address": self.address,
        }


@dataclass
class LabFabric:
    namespace: str
    bridge: str
    bridge_address: str
    prefix_length: int
    endpoints: tuple[FabricEndpoint, FabricEndpoint]
    nft_table: str = "m5_lab"
    started: bool = False

    @classmethod
    def allocate(cls) -> LabFabric:
        suffix = secrets.token_hex(4)
        tap_prefix = f"m5t{suffix[:1]}-{suffix}"
        return cls(
            namespace=f"m5lab-{suffix}",
            bridge=f"m5b-{suffix}",
            bridge_address=BRIDGE_ADDRESS,
            prefix_length=24,
            endpoints=(
                FabricEndpoint(
                    index=0,
                    tap=f"{tap_prefix}0"[:15],
                    mac=GUEST_MACS[0],
                    address=GUEST_ADDRESSES[0],
                ),
                FabricEndpoint(
                    index=1,
                    tap=f"{tap_prefix}1"[:15],
                    mac=GUEST_MACS[1],
                    address=GUEST_ADDRESSES[1],
                ),
            ),
        )

    def _exec(self, *command: str) -> subprocess.CompletedProcess[str]:
        return _run([IP, "netns", "exec", self.namespace, *command])

    def _nft(self, *command: str) -> subprocess.CompletedProcess[str]:
        return self._exec(_require_binary(NFT), *command)

    def start(self) -> None:
        if sys.platform != "linux":
            raise LabFabricError("the lab fabric requires Linux")
        _require_binary(IP)
        _require_binary(NFT)
        if self.started:
            raise LabFabricError("lab fabric is already started")
        _run([IP, "netns", "add", self.namespace])
        try:
            self._nft("delete", "table", "inet", self.nft_table)
        except LabFabricError:
            # A fresh namespace has no table; deletion is only defensive.
            pass
        try:
            self._exec(IP, "link", "set", "lo", "up")
            self._exec(IP, "link", "add", self.bridge, "type", "bridge")
            self._exec(
                IP,
                "addr",
                "add",
                f"{self.bridge_address}/{self.prefix_length}",
                "dev",
                self.bridge,
            )
            self._exec(IP, "link", "set", self.bridge, "up")
            for endpoint in self.endpoints:
                self._exec(
                    IP,
                    "tuntap",
                    "add",
                    "dev",
                    endpoint.tap,
                    "mode",
                    "tap",
                )
                self._exec(
                    IP,
                    "link",
                    "set",
                    endpoint.tap,
                    "master",
                    self.bridge,
                    "up",
                )
            rules = build_fabric_ruleset(
                bridge=self.bridge,
                taps=tuple(endpoint.tap for endpoint in self.endpoints),
            )
            completed = subprocess.run(
                [
                    IP,
                    "netns",
                    "exec",
                    self.namespace,
                    _require_binary(NFT),
                    "-f",
                    "-",
                ],
                input=rules,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise LabFabricError(
                    f"cannot install lab fabric nftables rules: {detail}"
                )
            self.started = True
            self.assert_isolated()
        except Exception:
            self.cleanup()
            raise

    def metadata(self) -> dict[str, Any]:
        return {
            "mode": "linux-private-bridge-tap",
            "namespace": self.namespace,
            "bridge": self.bridge,
            "bridge_address": self.bridge_address,
            "prefix_length": self.prefix_length,
            "nft_table": self.nft_table,
            "endpoints": [
                endpoint.as_dict() for endpoint in self.endpoints
            ],
        }

    def command(self, command: list[str]) -> list[str]:
        if not command:
            raise LabFabricError("fabric command must not be empty")
        return [IP, "netns", "exec", self.namespace, *command]

    def run(
        self,
        command: list[str],
        *,
        log_path: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("w")
        environment = os.environ.copy()
        environment.update(env or {})
        process = subprocess.Popen(
            self.command(command),
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

    def run_checked(
        self,
        command: list[str],
        *,
        timeout: float = 10,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(command),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def namespace_exists(self) -> bool:
        completed = subprocess.run(
            [IP, "netns", "list"],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return True
        return any(
            line.split(maxsplit=1)[0] == self.namespace
            for line in completed.stdout.splitlines()
            if line.strip()
        )

    def assert_isolated(self) -> None:
        routes = self._exec(IP, "-json", "-4", "route", "show")
        links = self._exec(IP, "-json", "link", "show")
        try:
            route_rows = json.loads(routes.stdout)
            link_rows = json.loads(links.stdout)
        except json.JSONDecodeError as error:
            raise LabFabricError(
                f"cannot parse fabric network state: {error}"
            ) from error
        expected_network = ipaddress.ip_network(
            f"{self.bridge_address}/{self.prefix_length}",
            strict=False,
        )
        external_routes = []
        for route in route_rows:
            if route.get("dst") == "default":
                external_routes.append(route)
                continue
            destination = route.get("dst")
            if not isinstance(destination, str):
                continue
            try:
                network = ipaddress.ip_network(destination, strict=False)
            except ValueError:
                external_routes.append(route)
                continue
            if network != expected_network:
                external_routes.append(route)
        links_by_name = {
            row.get("ifname"): row
            for row in link_rows
            if isinstance(row, dict)
        }
        expected_links = {
            "lo",
            self.bridge,
            *(endpoint.tap for endpoint in self.endpoints),
            # Linux creates these disabled tunnel stubs in every netns.
            "tunl0",
            "gre0",
            "gretap0",
            "erspan0",
            "ip_vti0",
            "ip6_vti0",
            "sit0",
            "ip6tnl0",
            "ip6gre0",
        }
        unexpected_links = sorted(set(links_by_name) - expected_links)
        if external_routes or unexpected_links:
            raise LabFabricError(
                "lab fabric has unexpected routes or interfaces"
            )

    def cleanup(self) -> None:
        namespace_existed = False
        try:
            namespace_existed = self.namespace_exists()
        except OSError:
            pass
        if namespace_existed:
            subprocess.run(
                [IP, "netns", "delete", self.namespace],
                text=True,
                capture_output=True,
                check=False,
            )
        self.started = False


@dataclass
class LabSocketFabric:
    namespace: str
    listen_host: str
    listen_port: int
    nft_table: str
    endpoints: tuple[FabricEndpoint, FabricEndpoint]
    started: bool = False

    @classmethod
    def allocate(cls) -> LabSocketFabric:
        suffix = secrets.token_hex(4)
        return cls(
            namespace=f"m5sock-{suffix}",
            listen_host="127.0.0.1",
            listen_port=20000 + (int(suffix, 16) % 20000),
            nft_table="m5_socket_lab",
            endpoints=(
                FabricEndpoint(
                    index=0,
                    tap="",
                    mac=GUEST_MACS[0],
                    address=GUEST_ADDRESSES[0],
                ),
                FabricEndpoint(
                    index=1,
                    tap="",
                    mac=GUEST_MACS[1],
                    address=GUEST_ADDRESSES[1],
                ),
            ),
        )

    def start(self) -> None:
        if sys.platform != "linux":
            raise LabFabricError("the socket lab fabric requires Linux")
        _require_binary(IP)
        _require_binary(NFT)
        _run([IP, "netns", "add", self.namespace])
        try:
            self._exec(IP, "link", "set", "lo", "up")
            rules = (
                "table inet m5_socket_lab {\n"
                "  chain input {\n"
                "    type filter hook input priority 0; policy drop;\n"
                '    iifname "lo" accept\n'
                "  }\n"
                "  chain output {\n"
                "    type filter hook output priority 0; policy drop;\n"
                '    oifname "lo" accept\n'
                "  }\n"
                "}\n"
            )
            completed = subprocess.run(
                [
                    IP,
                    "netns",
                    "exec",
                    self.namespace,
                    _require_binary(NFT),
                    "-f",
                    "-",
                ],
                input=rules,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise LabFabricError(
                    f"cannot install socket fabric rules: {detail}"
                )
            self.started = True
            self.assert_isolated()
        except Exception:
            self.cleanup()
            raise

    def _exec(self, *command: str) -> subprocess.CompletedProcess[str]:
        return _run([IP, "netns", "exec", self.namespace, *command])

    def metadata(self) -> dict[str, Any]:
        return {
            "mode": "linux-private-qemu-socket-switch",
            "namespace": self.namespace,
            "listen_host": self.listen_host,
            "listen_port": self.listen_port,
            "nft_table": self.nft_table,
            "endpoints": [
                {
                    "index": endpoint.index,
                    "mac": endpoint.mac,
                    "address": endpoint.address,
                }
                for endpoint in self.endpoints
            ],
        }

    def command(self, command: list[str]) -> list[str]:
        if not command:
            raise LabFabricError("fabric command must not be empty")
        return [IP, "netns", "exec", self.namespace, *command]

    def run(
        self,
        command: list[str],
        *,
        log_path: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open("w")
        environment = os.environ.copy()
        environment.update(env or {})
        process = subprocess.Popen(
            self.command(command),
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

    def run_checked(
        self,
        command: list[str],
        *,
        timeout: float = 10,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(command),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def namespace_exists(self) -> bool:
        completed = subprocess.run(
            [IP, "netns", "list"],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return True
        return any(
            line.split(maxsplit=1)[0] == self.namespace
            for line in completed.stdout.splitlines()
            if line.strip()
        )

    def assert_isolated(self) -> None:
        routes = self._exec(IP, "-json", "-4", "route", "show")
        links = self._exec(IP, "-json", "link", "show")
        try:
            route_rows = json.loads(routes.stdout)
            link_rows = json.loads(links.stdout)
        except json.JSONDecodeError as error:
            raise LabFabricError(
                f"cannot parse socket fabric state: {error}"
            ) from error
        if route_rows:
            raise LabFabricError("socket fabric has an unexpected route")
        expected_links = {
            "lo",
            "tunl0",
            "gre0",
            "gretap0",
            "erspan0",
            "ip_vti0",
            "ip6_vti0",
            "sit0",
            "ip6tnl0",
            "ip6gre0",
        }
        unexpected = sorted(
            row.get("ifname")
            for row in link_rows
            if row.get("ifname") not in expected_links
        )
        if unexpected:
            raise LabFabricError(
                f"socket fabric has unexpected links: {unexpected}"
            )

    def cleanup(self) -> None:
        namespace_existed = False
        try:
            namespace_existed = self.namespace_exists()
        except OSError:
            pass
        if namespace_existed:
            subprocess.run(
                [IP, "netns", "delete", self.namespace],
                text=True,
                capture_output=True,
                check=False,
            )
        self.started = False


def normalize_mac(value: str) -> str:
    parts = value.lower().split(":")
    if len(parts) != 6:
        raise LabFabricError(f"invalid MAC address: {value!r}")
    try:
        octets = [int(part, 16) for part in parts]
    except ValueError as error:
        raise LabFabricError(f"invalid MAC address: {value!r}") from error
    if any(not 0 <= octet <= 255 for octet in octets):
        raise LabFabricError(f"invalid MAC address: {value!r}")
    return ":".join(f"{octet:02x}" for octet in octets)


def _dhcp_options(packet: bytes) -> dict[int, bytes]:
    if len(packet) < 240 or packet[236:240] != DHCP_MAGIC:
        return {}
    result: dict[int, bytes] = {}
    offset = 240
    while offset < len(packet):
        option = packet[offset]
        offset += 1
        if option == 0:
            continue
        if option == 255:
            break
        if offset >= len(packet):
            break
        length = packet[offset]
        offset += 1
        end = offset + length
        if end > len(packet):
            break
        result[option] = packet[offset:end]
        offset = end
    return result


def parse_dhcp_request(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 240 or packet[0] != 1:
        return None
    if packet[1] != 1 or packet[2] != 6:
        return None
    options = _dhcp_options(packet)
    raw_type = options.get(53)
    if not raw_type or len(raw_type) != 1:
        return None
    requested = options.get(50)
    return {
        "xid": packet[4:8],
        "flags": struct.unpack_from("!H", packet, 10)[0],
        "mac": normalize_mac(packet[28:34].hex(":")),
        "message_type": raw_type[0],
        "requested_ip": (
            str(ipaddress.IPv4Address(requested))
            if requested and len(requested) == 4
            else None
        ),
    }


def build_dhcp_reply(
    request: bytes,
    parsed: dict[str, Any],
    *,
    message_type: int,
    address: str,
    server_address: str,
    prefix_length: int,
    lease_seconds: int,
) -> bytes:
    packet = bytearray(request[:240])
    packet[0] = 2
    packet[1] = 1
    packet[2] = 6
    packet[3] = 0
    packet[4:8] = parsed["xid"]
    struct.pack_into("!H", packet, 10, int(parsed.get("flags", 0)))
    packet[12:16] = b"\0\0\0\0"
    packet[16:20] = socket.inet_aton(address)
    packet[20:24] = socket.inet_aton(server_address)
    packet[24:28] = b"\0\0\0\0"
    packet[236:240] = DHCP_MAGIC
    netmask = str(
        ipaddress.ip_network(
            f"0.0.0.0/{prefix_length}",
            strict=False,
        ).netmask
    )
    options = bytearray()

    def option(code: int, value: bytes) -> None:
        options.extend((code, len(value)))
        options.extend(value)

    option(1, socket.inet_aton(netmask))
    option(3, socket.inet_aton(server_address))
    option(6, socket.inet_aton(server_address))
    option(51, struct.pack("!I", lease_seconds))
    option(53, bytes([message_type]))
    option(54, socket.inet_aton(server_address))
    options.append(255)
    packet.extend(options)
    if len(packet) < 548:
        packet.extend(b"\0" * (548 - len(packet)))
    return bytes(packet)


def _internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_dhcp_ethernet_reply(
    dhcp_payload: bytes,
    *,
    source_mac: bytes,
    server_mac: bytes,
    server_address: str,
) -> bytes:
    if len(source_mac) != 6 or len(server_mac) != 6:
        raise LabFabricError("DHCP Ethernet MAC addresses must be six bytes")
    destination_address = "255.255.255.255"
    udp_length = 8 + len(dhcp_payload)
    udp_base = struct.pack(
        "!HHHH",
        67,
        68,
        udp_length,
        0,
    )
    pseudo_header = (
        socket.inet_aton(server_address)
        + socket.inet_aton(destination_address)
        + struct.pack("!BBH", 0, IPPROTO_UDP, udp_length)
    )
    udp_checksum = _internet_checksum(
        pseudo_header + udp_base + dhcp_payload
    )
    if udp_checksum == 0:
        udp_checksum = 0xFFFF
    udp = (
        struct.pack("!HHHH", 67, 68, udp_length, udp_checksum)
        + dhcp_payload
    )
    total_length = 20 + len(udp)
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        0,
        0,
        64,
        IPPROTO_UDP,
        0,
        socket.inet_aton(server_address),
        socket.inet_aton(destination_address),
    )
    checksum = _internet_checksum(header)
    header = header[:10] + struct.pack("!H", checksum) + header[12:]
    ethernet = (
        b"\xff" * 6
        + server_mac
        + struct.pack("!H", ETH_P_IP)
        + header
        + udp
    )
    minimum = 60
    if len(ethernet) < minimum:
        ethernet += b"\0" * (minimum - len(ethernet))
    return ethernet


class LabDhcp:
    def __init__(self, config: dict[str, Any]):
        self.interface = str(config.get("interface", ""))
        self.server_address = str(config.get("server_address", ""))
        self.prefix_length = int(config.get("prefix_length", 24))
        self.lease_seconds = int(config.get("lease_seconds", 3600))
        reservations = config.get("reservations")
        if (
            not self.interface
            or not self.server_address
            or not isinstance(reservations, dict)
            or not reservations
        ):
            raise LabFabricError("invalid lab DHCP configuration")
        self.reservations = {
            normalize_mac(mac): str(ipaddress.IPv4Address(address))
            for mac, address in reservations.items()
        }
        self.lease_path = (
            Path(str(config["lease_file"]))
            if config.get("lease_file")
            else None
        )
        self.ready_path = (
            Path(str(config["ready_file"]))
            if config.get("ready_file")
            else None
        )
        self.leases: dict[str, str] = {}
        self.requests: list[dict[str, Any]] = []
        raw_endpoints = config.get("endpoints", [])
        self.tap_by_mac: dict[str, str] = {}
        if isinstance(raw_endpoints, list):
            for row in raw_endpoints:
                if not isinstance(row, dict):
                    raise LabFabricError("DHCP endpoints must be objects")
                mac = row.get("mac")
                tap = row.get("tap", "")
                if not isinstance(mac, str) or not isinstance(tap, str):
                    raise LabFabricError(
                        "DHCP endpoint requires a MAC and optional TAP"
                    )
                if tap:
                    self.tap_by_mac[normalize_mac(mac)] = tap

    def address_for(self, mac: str) -> str:
        address = self.reservations.get(normalize_mac(mac))
        if address is None:
            raise LabFabricError(f"no DHCP reservation for MAC {mac}")
        return address

    def persist(self) -> None:
        if self.lease_path is None:
            return
        self.lease_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.lease_path.with_suffix(
            f"{self.lease_path.suffix}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(
                {
                    "reservations": self.reservations,
                    "leases": self.leases,
                    "requests": self.requests,
                },
                indent=2,
            )
            + "\n"
        )
        temporary.replace(self.lease_path)

    def handle(
        self,
        packet: bytes,
        *,
        source_mac: str | None = None,
    ) -> bytes | None:
        parsed = parse_dhcp_request(packet)
        if parsed is None:
            return None
        if source_mac is not None:
            parsed["mac"] = normalize_mac(source_mac)
        message_type = parsed["message_type"]
        if message_type not in {1, 3}:
            return None
        try:
            address = self.address_for(parsed["mac"])
        except LabFabricError:
            self.requests.append(
                {
                    "mac": parsed["mac"],
                    "message_type": message_type,
                    "decision": "deny",
                }
            )
            self.persist()
            raise
        if message_type == 3:
            requested = parsed["requested_ip"]
            if requested and requested != address:
                self.requests.append(
                    {
                        "mac": parsed["mac"],
                        "message_type": message_type,
                        "requested_ip": requested,
                        "decision": "deny",
                    }
                )
                self.persist()
                return None
            reply_type = 5
            self.leases[parsed["mac"]] = address
        else:
            reply_type = 2
        self.requests.append(
            {
                "mac": parsed["mac"],
                "message_type": message_type,
                "requested_ip": parsed.get("requested_ip"),
                "address": address,
                "decision": "allow",
            }
        )
        self.persist()
        return build_dhcp_reply(
            packet,
            parsed,
            message_type=reply_type,
            address=address,
            server_address=self.server_address,
            prefix_length=self.prefix_length,
            lease_seconds=self.lease_seconds,
        )

    def serve(self) -> int:
        if sys.platform != "linux":
            raise LabFabricError("lab DHCP requires Linux")
        stop = False

        def terminate(_signum: int, _frame: object) -> None:
            nonlocal stop
            stop = True

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        server_mac_text = Path(
            f"/sys/class/net/{self.interface}/address"
        ).read_text().strip()
        server_mac = bytes.fromhex(server_mac_text.replace(":", ""))
        sock = socket.socket(
            socket.AF_PACKET,
            socket.SOCK_RAW,
            socket.htons(ETH_P_ALL),
        )
        sock.bind((self.interface, 0))
        sock.setblocking(False)
        if self.ready_path is not None:
            self.ready_path.parent.mkdir(parents=True, exist_ok=True)
            self.ready_path.write_text(
                json.dumps(
                    {
                        "status": "READY",
                        "interface": self.interface,
                        "server_address": self.server_address,
                        "reservations": self.reservations,
                    },
                    indent=2,
                )
                + "\n"
            )
        try:
            while not stop:
                try:
                    ready, _, _ = select.select([sock], [], [], 0.2)
                except InterruptedError:
                    continue
                for ready_socket in ready:
                    tap = self.interface
                    frame, _peer = ready_socket.recvfrom(4096)
                    if len(frame) < 42:
                        continue
                    if struct.unpack_from("!H", frame, 12)[0] != ETH_P_IP:
                        continue
                    ip_offset = 14
                    header_length = (frame[ip_offset] & 0x0F) * 4
                    total_length = struct.unpack_from(
                        "!H",
                        frame,
                        ip_offset + 2,
                    )[0]
                    if (
                        header_length < 20
                        or frame[ip_offset + 9] != IPPROTO_UDP
                        or ip_offset + total_length > len(frame)
                    ):
                        continue
                    udp_offset = ip_offset + header_length
                    (
                        source_port,
                        destination_port,
                        udp_length,
                    ) = struct.unpack_from(
                        "!HHH",
                        frame,
                        udp_offset,
                    )
                    if (
                        source_port != 68
                        or destination_port != 67
                        or udp_length < 8
                        or udp_offset + udp_length > len(frame)
                    ):
                        continue
                    payload = frame[
                        udp_offset + 8 : udp_offset + udp_length
                    ]
                    source_mac = frame[6:12].hex(":")
                    try:
                        reply = self.handle(
                            payload,
                            source_mac=source_mac,
                        )
                    except LabFabricError:
                        continue
                    if reply is None:
                        continue
                    ready_socket.send(
                        build_dhcp_ethernet_reply(
                            reply,
                            source_mac=frame[6:12],
                            server_mac=server_mac,
                            server_address=self.server_address,
                        )
                    )
        finally:
            sock.close()
            self.persist()
        return 0


class LabSocketSwitch:
    def __init__(self, config: dict[str, Any]):
        self.listen_host = str(config.get("listen_host", "127.0.0.1"))
        self.listen_port = int(config.get("listen_port", 0))
        self.expected_clients = int(config.get("expected_clients", 2))
        if (
            not self.listen_host
            or not 1 <= self.listen_port <= 65535
            or self.expected_clients != 2
        ):
            raise LabFabricError("invalid socket switch configuration")
        raw_endpoints = config.get("endpoints")
        if not isinstance(raw_endpoints, list) or len(raw_endpoints) != 2:
            raise LabFabricError("socket switch requires two endpoints")
        self.mac_by_index: dict[int, str] = {}
        for row in raw_endpoints:
            if not isinstance(row, dict):
                raise LabFabricError("socket switch endpoints must be objects")
            index = row.get("index")
            mac = row.get("mac")
            if not isinstance(index, int) or not isinstance(mac, str):
                raise LabFabricError("socket switch endpoint is invalid")
            self.mac_by_index[index] = normalize_mac(mac)
        self.ready_path = (
            Path(str(config["ready_file"]))
            if config.get("ready_file")
            else None
        )
        self.state_path = (
            Path(str(config["state_file"]))
            if config.get("state_file")
            else None
        )
        self.trace = config.get("trace") is True
        self.dhcp = LabDhcp(
            {
                **config,
                "interface": "lo",
                "lease_file": config.get("lease_file"),
            }
        )
        self.clients: dict[int, socket.socket | None] = {
            index: None for index in self.mac_by_index
        }
        self.client_slot_by_endpoint: dict[int, int | None] = {
            index: None for index in self.mac_by_index
        }
        self.endpoint_by_client_slot: dict[int, int] = {}
        self.mac_by_client_slot: dict[int, str] = {}
        self.pending_frames: dict[int, list[bytes]] = {
            index: [] for index in self.mac_by_index
        }
        self.current_client = 0
        self.frames = 0
        self.client_frames: dict[int, int] = {
            index: 0 for index in self.mac_by_index
        }

    def persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "status": "READY",
                    "listen_host": self.listen_host,
                    "listen_port": self.listen_port,
                    "frames": self.frames,
                    "client_frames": self.client_frames,
                    "pending_frames": {
                        index: len(frames)
                        for index, frames in self.pending_frames.items()
                    },
                    "client_slot_by_endpoint": {
                        index: slot
                        for index, slot in self.client_slot_by_endpoint.items()
                        if slot is not None
                    },
                    "mac_by_client_slot": self.mac_by_client_slot,
                },
                indent=2,
            )
            + "\n"
        )

    @staticmethod
    def encode_frame(frame: bytes) -> bytes:
        return struct.pack("!I", len(frame)) + frame

    @staticmethod
    def extract_frames(
        buffer: bytearray,
    ) -> list[bytes]:
        frames: list[bytes] = []
        while len(buffer) >= 4:
            length = struct.unpack_from("!I", buffer)[0]
            if not 14 <= length <= 262144:
                raise LabFabricError(
                    f"socket switch received invalid frame length {length}"
                )
            if len(buffer) < 4 + length:
                break
            frames.append(bytes(buffer[4 : 4 + length]))
            del buffer[: 4 + length]
        return frames

    def accept_clients(self, listener: socket.socket) -> None:
        deadline = time.monotonic() + 20
        while (
            time.monotonic() < deadline
            and any(client is None for client in self.clients.values())
        ):
            ready, _, _ = select.select([listener], [], [], 0.2)
            if not ready:
                continue
            client, _peer = listener.accept()
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.setblocking(False)
            self.clients[self.current_client] = client
            self.current_client += 1
        if any(client is None for client in self.clients.values()):
            raise LabFabricError("socket switch did not receive both guests")

    def bind_client(
        self,
        client_slot: int,
        source_mac: str,
    ) -> int:
        normalized = normalize_mac(source_mac)
        existing_slot = next(
            (
                slot
                for slot, mac in self.mac_by_client_slot.items()
                if mac == normalized
            ),
            None,
        )
        if existing_slot is not None and existing_slot != client_slot:
            raise LabFabricError(
                f"socket switch MAC {normalized} moved between clients"
            )
        existing_mac = self.mac_by_client_slot.get(client_slot)
        if existing_mac is not None and existing_mac != normalized:
            raise LabFabricError(
                f"socket switch client {client_slot} changed MAC"
            )
        endpoint_index = next(
            (
                index
                for index, mac in self.mac_by_index.items()
                if mac == normalized
            ),
            None,
        )
        if endpoint_index is None:
            raise LabFabricError(
                f"socket switch rejected unconfigured MAC {normalized}"
            )
        assigned_slot = self.client_slot_by_endpoint[endpoint_index]
        if assigned_slot is not None and assigned_slot != client_slot:
            raise LabFabricError(
                f"socket switch endpoint {endpoint_index} connected twice"
            )
        self.client_slot_by_endpoint[endpoint_index] = client_slot
        self.endpoint_by_client_slot[client_slot] = endpoint_index
        self.mac_by_client_slot[client_slot] = normalized
        return endpoint_index

    def send_to(self, endpoint_index: int, frame: bytes) -> None:
        client_slot = self.client_slot_by_endpoint[endpoint_index]
        if client_slot is None:
            raise LabFabricError(
                f"socket switch endpoint {endpoint_index} is not identified"
            )
        client = self.clients[client_slot]
        if client is None:
            raise LabFabricError("socket switch endpoint is disconnected")
        try:
            client.setblocking(True)
            client.sendall(self.encode_frame(frame))
            client.setblocking(False)
            if self.trace:
                print(
                    f"socket-switch tx client={endpoint_index} "
                    f"bytes={len(frame)}",
                    flush=True,
                )
        except OSError as error:
            raise LabFabricError(
                f"socket switch send failed: {error}"
            ) from error

    def forward(self, source_index: int, frame: bytes) -> None:
        destination_index = 1 - source_index
        if self.client_slot_by_endpoint[destination_index] is None:
            pending = self.pending_frames[destination_index]
            if len(pending) >= MAX_PENDING_SWITCH_FRAMES:
                raise LabFabricError(
                    f"socket switch endpoint {destination_index} "
                    "accumulated too many unidentified frames"
                )
            pending.append(frame)
        else:
            self.send_to(destination_index, frame)

    def flush_pending(self) -> None:
        for endpoint_index, pending in self.pending_frames.items():
            if self.client_slot_by_endpoint[endpoint_index] is None:
                continue
            for frame in pending:
                self.send_to(endpoint_index, frame)
            pending.clear()

    def handle_frame(self, client_slot: int, frame: bytes) -> None:
        if len(frame) < 14:
            raise LabFabricError("socket switch received a short Ethernet frame")
        source_mac = normalize_mac(frame[6:12].hex(":"))
        source_index = self.bind_client(client_slot, source_mac)
        self.frames += 1
        self.client_frames[source_index] += 1
        if len(frame) < 42 or frame[12:14] != b"\x08\x00":
            self.forward(source_index, frame)
            return
        ip_header = (frame[14] & 0x0F) * 4
        udp_offset = 14 + ip_header
        if (
            ip_header < 20
            or frame[23] != IPPROTO_UDP
            or udp_offset + 8 > len(frame)
        ):
            self.forward(source_index, frame)
            return
        source_port, destination_port, udp_length = struct.unpack_from(
            "!HHH",
            frame,
            udp_offset,
        )
        if (
            source_port == 68
            and destination_port == 67
            and udp_length >= 8
            and udp_offset + udp_length <= len(frame)
        ):
            payload = frame[
                udp_offset + 8 : udp_offset + udp_length
            ]
            parsed = parse_dhcp_request(payload)
            if self.trace:
                print(
                    f"socket-switch dhcp client={source_index} "
                    f"mac={source_mac} "
                    f"type="
                    f"{parsed['message_type'] if parsed else 'unknown'}",
                    flush=True,
                )
            try:
                reply = self.dhcp.handle(
                    payload,
                    source_mac=source_mac,
                )
            except LabFabricError:
                reply = None
            if reply is not None:
                self.send_to(
                    source_index,
                    build_dhcp_ethernet_reply(
                        reply,
                        source_mac=frame[6:12],
                        server_mac=bytes.fromhex("024d35fffffe"),
                        server_address=BRIDGE_ADDRESS,
                    ),
                )
            return
        self.forward(source_index, frame)

    def serve(self) -> int:
        if sys.platform != "linux":
            raise LabFabricError("socket switch requires Linux")
        stop = False

        def terminate(_signum: int, _frame: object) -> None:
            nonlocal stop
            stop = True

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.listen_host, self.listen_port))
        listener.listen(2)
        listener.settimeout(0.2)
        self.listen_port = int(listener.getsockname()[1])
        if self.ready_path is not None:
            self.ready_path.parent.mkdir(parents=True, exist_ok=True)
            self.ready_path.write_text(
                json.dumps(
                    {
                        "status": "LISTENING",
                        "listen_host": self.listen_host,
                        "listen_port": self.listen_port,
                    },
                    indent=2,
                )
                + "\n"
            )
        self.persist()
        listener.setblocking(False)
        self.accept_clients(listener)
        buffers = {
            index: bytearray() for index in self.clients
        }
        try:
            while not stop:
                active = [
                    client
                    for client in self.clients.values()
                    if client is not None
                ]
                ready, _, _ = select.select(active, [], [], 0.2)
                for client in ready:
                    index = next(
                        key
                        for key, value in self.clients.items()
                        if value is client
                    )
                    data = client.recv(65536)
                    if not data:
                        raise LabFabricError(
                            f"socket switch guest {index} disconnected"
                        )
                    buffers[index].extend(data)
                    for frame in self.extract_frames(buffers[index]):
                        self.handle_frame(index, frame)
                self.flush_pending()
                self.persist()
        finally:
            for client in self.clients.values():
                if client is not None:
                    client.close()
            listener.close()
            self.dhcp.persist()
        return 0


def _load_dhcp_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise LabFabricError(f"invalid DHCP config: {error}") from error
    if not isinstance(value, dict):
        raise LabFabricError("DHCP config must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage a private Linux L2 fabric for QEMU guests"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    dhcp_parser = subparsers.add_parser("dhcp")
    dhcp_parser.add_argument("--config", type=Path, required=True)
    switch_parser = subparsers.add_parser("switch")
    switch_parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "dhcp":
            return LabDhcp(_load_dhcp_config(args.config)).serve()
        if args.command == "switch":
            return LabSocketSwitch(
                _load_dhcp_config(args.config)
            ).serve()
        parser.error(f"unsupported command: {args.command}")
    except (LabFabricError, OSError) as error:
        print(f"lab fabric failed: {error}", file=sys.stderr)
        return 126
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
