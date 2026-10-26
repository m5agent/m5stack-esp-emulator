#!/usr/bin/env python3
"""Summarize QEMU Ethernet captures without retaining packet payloads."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PCAP_MAGIC = {
    b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
    b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
    b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
    b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
}
ETHERNET_LINKTYPE = 1
VLAN_ETHERTYPES = {0x8100, 0x88A8, 0x9100}
SLIRP_REDIRECT_NETWORK = ipaddress.IPv4Network("198.18.0.0/15")
SITE_LOCAL_NETWORK = ipaddress.IPv6Network("fec0::/10")
MAX_RECORDED_DNS_NAMES = 256
MAX_RECORDED_FLOWS = 512
MAX_RECORDED_PAYLOAD_HASHES = 16
MAX_RECORDED_DHCP_TRANSACTIONS = 64
MAX_CAPTURE_BYTES = 512 * 1024 * 1024
DHCP_MESSAGE_TYPES = {
    1: "DISCOVER",
    2: "OFFER",
    3: "REQUEST",
    4: "DECLINE",
    5: "ACK",
    6: "NAK",
    7: "RELEASE",
    8: "INFORM",
}


class PcapError(ValueError):
    """Raised when a capture is malformed or unsupported."""


@dataclass
class Flow:
    protocol: str
    source: str
    destination: str
    packets: int = 0
    payload_bytes: int = 0
    first_timestamp: float | None = None
    last_timestamp: float | None = None
    payload_hashes: list[str] = field(default_factory=list)

    def observe(
        self,
        *,
        timestamp: float,
        payload: bytes,
    ) -> None:
        self.packets += 1
        self.payload_bytes += len(payload)
        if self.first_timestamp is None:
            self.first_timestamp = timestamp
        self.last_timestamp = timestamp
        if (
            payload
            and len(self.payload_hashes) < MAX_RECORDED_PAYLOAD_HASHES
        ):
            self.payload_hashes.append(hashlib.sha256(payload).hexdigest())

    def evidence(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "source": self.source,
            "destination": self.destination,
            "packets": self.packets,
            "payload_bytes": self.payload_bytes,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "payload_sha256": self.payload_hashes,
        }


def _scope(address: str) -> str:
    if address == "255.255.255.255":
        return "broadcast"
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return "unknown"
    if value.is_loopback:
        return "loopback"
    if value.is_link_local:
        return "link-local"
    if value.is_multicast:
        return "multicast"
    if value.is_unspecified:
        return "unspecified"
    if value.version == 6 and value in SITE_LOCAL_NETWORK:
        return "site-local"
    if value.version == 4 and value in SLIRP_REDIRECT_NETWORK:
        return "slirp-redirect"
    if value.is_private:
        return "private"
    return "global"


def _dns_name(data: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    cursor = offset
    highest = offset
    jumped = False
    visited: set[int] = set()
    while cursor < len(data):
        if cursor in visited:
            raise PcapError("DNS compression pointer loop")
        visited.add(cursor)
        length = data[cursor]
        if length == 0:
            cursor += 1
            if not jumped:
                highest = cursor
            break
        if length & 0xC0 == 0xC0:
            if cursor + 1 >= len(data):
                raise PcapError("truncated DNS compression pointer")
            pointer = ((length & 0x3F) << 8) | data[cursor + 1]
            if pointer >= len(data):
                raise PcapError("DNS compression pointer is out of range")
            if not jumped:
                highest = cursor + 2
            cursor = pointer
            jumped = True
            continue
        if length & 0xC0:
            raise PcapError("unsupported DNS label encoding")
        start = cursor + 1
        end = start + length
        if end > len(data):
            raise PcapError("truncated DNS label")
        labels.append(data[start:end].decode("ascii", errors="replace"))
        cursor = end
        if not jumped:
            highest = cursor
    else:
        raise PcapError("truncated DNS name")
    return ".".join(labels) + ".", highest


def dns_names(payload: bytes) -> tuple[list[str], str | None]:
    if len(payload) < 12:
        return [], None
    flags = struct.unpack_from(">H", payload, 2)[0]
    question_count = struct.unpack_from(">H", payload, 4)[0]
    if question_count == 0:
        return [], "response" if flags & 0x8000 else "query"
    names: list[str] = []
    cursor = 12
    try:
        for _ in range(min(question_count, 32)):
            name, cursor = _dns_name(payload, cursor)
            if cursor + 4 > len(payload):
                raise PcapError("truncated DNS question")
            cursor += 4
            if name not in names:
                names.append(name)
    except PcapError:
        return names, None
    return names, "response" if flags & 0x8000 else "query"


def _network_packet(
    frame: bytes,
) -> tuple[int, bytes] | None:
    if len(frame) < 14:
        return None
    ether_type = struct.unpack_from(">H", frame, 12)[0]
    offset = 14
    while ether_type in VLAN_ETHERTYPES:
        if offset + 4 > len(frame):
            return None
        ether_type = struct.unpack_from(">H", frame, offset + 2)[0]
        offset += 4
    return ether_type, frame[offset:]


def _ipv4(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 20 or packet[0] >> 4 != 4:
        return None
    header_length = (packet[0] & 0x0F) * 4
    if header_length < 20 or header_length > len(packet):
        return None
    total_length = struct.unpack_from(">H", packet, 2)[0]
    if total_length < header_length or total_length > len(packet):
        return None
    fragment = struct.unpack_from(">H", packet, 6)[0]
    source = str(ipaddress.IPv4Address(packet[12:16]))
    destination = str(ipaddress.IPv4Address(packet[16:20]))
    protocol_number = packet[9]
    return {
        "version": 4,
        "source": source,
        "destination": destination,
        "protocol_number": protocol_number,
        "payload_offset": header_length,
        "payload_end": total_length,
        "fragment": fragment,
    }


def _ipv6(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 40 or packet[0] >> 4 != 6:
        return None
    payload_length = struct.unpack_from(">H", packet, 4)[0]
    end = 40 + payload_length
    if end > len(packet):
        return None
    source = str(ipaddress.IPv6Address(packet[8:24]))
    destination = str(ipaddress.IPv6Address(packet[24:40]))
    return {
        "version": 6,
        "source": source,
        "destination": destination,
        "protocol_number": packet[6],
        "payload_offset": 40,
        "payload_end": end,
        "fragment": 0,
    }


def _ipv4_text(payload: bytes, offset: int) -> str | None:
    if offset + 4 > len(payload):
        return None
    address = str(ipaddress.IPv4Address(payload[offset : offset + 4]))
    return None if address == "0.0.0.0" else address


def _dhcp_options(payload: bytes) -> dict[str, int | str]:
    if len(payload) < 240 or payload[236:240] != b"\x63\x82\x53\x63":
        return {}
    result: dict[str, int | str] = {}
    cursor = 240
    while cursor < len(payload):
        option = payload[cursor]
        cursor += 1
        if option == 0:
            continue
        if option == 255:
            break
        if cursor >= len(payload):
            break
        length = payload[cursor]
        cursor += 1
        if cursor + length > len(payload):
            break
        value = payload[cursor : cursor + length]
        cursor += length
        if option == 53 and length == 1:
            message_type = DHCP_MESSAGE_TYPES.get(value[0])
            if message_type is not None:
                result["message_type"] = message_type
        elif option == 50 and length == 4:
            requested = _ipv4_text(value, 0)
            if requested:
                result["requested_ip"] = requested
        elif option == 54 and length == 4:
            server = _ipv4_text(value, 0)
            if server:
                result["server_id"] = server
        elif option in {51, 58, 59} and length == 4:
            name = {
                51: "lease_seconds",
                58: "t1_seconds",
                59: "t2_seconds",
            }[option]
            result[name] = struct.unpack(">I", value)[0]
    return result


def _dhcp(
    payload: bytes,
    *,
    source_port: int,
    destination_port: int,
) -> dict[str, Any] | None:
    if not ({source_port, destination_port} & {67, 68}):
        return None
    if len(payload) < 236:
        direction = (
            "reply"
            if source_port == 67 or destination_port == 68
            else "request"
        )
        return {
            "direction": direction,
            "xid": None,
            "message_type": None,
            "client_address": None,
            "requested_ip": None,
            "server_id": None,
        }
    operation = payload[0]
    if operation not in {1, 2}:
        direction = (
            "reply"
            if source_port == 67 or destination_port == 68
            else "request"
        )
        return {
            "direction": direction,
            "xid": None,
            "message_type": None,
            "client_address": None,
            "requested_ip": None,
            "server_id": None,
        }
    direction = "reply" if operation == 2 else "request"
    assigned = _ipv4_text(payload, 16)
    current = _ipv4_text(payload, 12)
    options = _dhcp_options(payload)
    return {
        "direction": direction,
        "xid": payload[4:8].hex(),
        "message_type": options.get("message_type"),
        "client_address": assigned or current,
        "requested_ip": options.get("requested_ip"),
        "server_id": options.get("server_id"),
        **{
            key: options[key]
            for key in ("lease_seconds", "t1_seconds", "t2_seconds")
            if key in options
        },
    }


def summarize_pcap(
    path: Path,
    *,
    include_dns_names: bool = True,
    max_flows: int = MAX_RECORDED_FLOWS,
) -> dict[str, Any]:
    capture_size = path.stat().st_size
    if capture_size > MAX_CAPTURE_BYTES:
        raise PcapError(
            f"capture is {capture_size} bytes; maximum is {MAX_CAPTURE_BYTES}"
        )
    data = path.read_bytes()
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "m5stack-pcap-summary",
        "status": "PASS",
        "scope": "capture-summary-not-rf-validation",
        "input": {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "format": "pcap",
        "linktype": None,
        "packets": 0,
        "truncated_records": 0,
        "malformed_records": 0,
        "protocols": {},
        "flows": [],
        "flows_truncated": False,
        "dns": {
            "queries": [],
            "responses": [],
            "malformed": 0,
            "names_included": include_dns_names,
        },
        "dhcp": {
            "packets": 0,
            "requests": 0,
            "replies": 0,
            "guest_addresses": [],
            "message_types": {},
            "selecting_requests": 0,
            "renewal_requests": 0,
            "renewal_acks": 0,
            "transactions": [],
            "transactions_truncated": False,
        },
        "arp_packets": 0,
        "egress_destinations": [],
        "not_claimed": [
            "packet payload contents",
            "TLS plaintext",
            "real-hardware RF behavior",
            "malware safety",
        ],
    }
    if len(data) < 24:
        raise PcapError("capture is shorter than the pcap global header")
    magic = data[:4]
    if magic not in PCAP_MAGIC:
        if magic == b"\x0a\x0d\x0d\x0a":
            raise PcapError("pcapng is not supported; use libpcap output")
        raise PcapError(f"unrecognized capture magic {magic.hex()}")
    byte_order, fraction_scale = PCAP_MAGIC[magic]
    (
        version_major,
        version_minor,
        _thiszone,
        _sigfigs,
        _snaplen,
        linktype,
    ) = struct.unpack_from(f"{byte_order}HHiIII", data, 4)
    result["pcap_version"] = f"{version_major}.{version_minor}"
    result["linktype"] = linktype
    if linktype != ETHERNET_LINKTYPE:
        raise PcapError(
            f"unsupported linktype {linktype}; Ethernet is required"
        )

    flows: dict[tuple[str, str, str], Flow] = {}
    dns_queries: list[str] = []
    dns_responses: list[str] = []
    destinations: dict[tuple[str, int, str], dict[str, Any]] = {}
    guest_addresses: set[str] = set()
    dhcp_transactions: dict[str, dict[str, Any]] = {}
    protocols = result["protocols"]
    offset = 24
    while offset < len(data):
        if offset + 16 > len(data):
            result["truncated_records"] += 1
            break
        seconds, fraction, captured_length, _original_length = struct.unpack_from(
            f"{byte_order}IIII", data, offset
        )
        offset += 16
        end = offset + captured_length
        if end > len(data):
            result["truncated_records"] += 1
            break
        frame = data[offset:end]
        offset = end
        result["packets"] += 1
        timestamp = seconds + (fraction / fraction_scale)
        network = _network_packet(frame)
        if network is None:
            result["malformed_records"] += 1
            continue
        ether_type, packet = network
        if ether_type == 0x0806:
            result["arp_packets"] += 1
            protocols["ARP"] = protocols.get("ARP", 0) + 1
            continue
        if ether_type == 0x86DD:
            parsed = _ipv6(packet)
        elif ether_type == 0x0800:
            parsed = _ipv4(packet)
        else:
            protocols[f"ethertype-0x{ether_type:04x}"] = (
                protocols.get(f"ethertype-0x{ether_type:04x}", 0) + 1
            )
            continue
        if parsed is None:
            result["malformed_records"] += 1
            continue
        if parsed["fragment"] & 0x1FFF:
            protocols["IP-fragment"] = protocols.get("IP-fragment", 0) + 1
            continue
        transport = packet[
            parsed["payload_offset"] : parsed["payload_end"]
        ]
        protocol_number = parsed["protocol_number"]
        if protocol_number == 1:
            protocol = "ICMP" if parsed["version"] == 4 else "ICMPv6"
            source_port = destination_port = 0
            transport_payload = b""
        elif protocol_number == 2:
            protocol = "IGMP"
            source_port = destination_port = 0
            transport_payload = transport
        elif protocol_number in {6, 17}:
            if len(transport) < 8:
                result["malformed_records"] += 1
                continue
            source_port, destination_port = struct.unpack_from(">HH", transport)
            protocol = "TCP" if protocol_number == 6 else "UDP"
            if protocol_number == 6 and len(transport) >= 20:
                data_offset = (transport[12] >> 4) * 4
                if data_offset < 20 or data_offset > len(transport):
                    result["malformed_records"] += 1
                    continue
                transport_payload = transport[data_offset:]
            else:
                udp_length = struct.unpack_from(">H", transport, 4)[0]
                if udp_length < 8 or udp_length > len(transport):
                    result["malformed_records"] += 1
                    continue
                transport_payload = transport[8:udp_length]
        else:
            protocol = f"IP-{protocol_number}"
            source_port = destination_port = 0
            transport_payload = transport
        protocols[protocol] = protocols.get(protocol, 0) + 1

        source = (
            f"{parsed['source']}:{source_port}"
            if source_port
            else parsed["source"]
        )
        destination = (
            f"{parsed['destination']}:{destination_port}"
            if destination_port
            else parsed["destination"]
        )
        key = (protocol, source, destination)
        flow = flows.get(key)
        if flow is None and len(flows) < max_flows:
            flow = Flow(protocol, source, destination)
            flows[key] = flow
        if flow is not None:
            flow.observe(timestamp=timestamp, payload=transport_payload)
        else:
            result["flows_truncated"] = True

        inbound = parsed["destination"] in guest_addresses
        if not inbound:
            destination_key = (
                parsed["destination"],
                destination_port,
                _scope(parsed["destination"]),
            )
            row = destinations.setdefault(
                destination_key,
                {
                    "address": parsed["destination"],
                    "port": destination_port or None,
                    "scope": destination_key[2],
                    "protocols": [],
                    "packets": 0,
                },
            )
            row["packets"] += 1
            if protocol not in row["protocols"]:
                row["protocols"].append(protocol)

        if protocol == "UDP":
            dhcp = _dhcp(
                transport_payload,
                source_port=source_port,
                destination_port=destination_port,
            )
            if dhcp is not None:
                direction = dhcp["direction"]
                client_address = dhcp["client_address"]
                result["dhcp"]["packets"] += 1
                result["dhcp"][
                    "replies" if direction == "reply" else "requests"
                ] += 1
                if client_address:
                    guest_addresses.add(client_address)
                message_type = dhcp["message_type"]
                if message_type:
                    key = message_type.lower()
                    result["dhcp"]["message_types"][key] = (
                        result["dhcp"]["message_types"].get(key, 0) + 1
                    )
                request_kind = None
                if direction == "request" and message_type == "REQUEST":
                    if client_address:
                        request_kind = "renewal"
                        result["dhcp"]["renewal_requests"] += 1
                    elif dhcp["requested_ip"]:
                        request_kind = "selecting"
                        result["dhcp"]["selecting_requests"] += 1
                xid = dhcp["xid"]
                if xid:
                    transaction = dhcp_transactions.get(xid)
                    if (
                        transaction is None
                        and len(dhcp_transactions)
                        < MAX_RECORDED_DHCP_TRANSACTIONS
                    ):
                        transaction = {
                            "xid": xid,
                            "message_sequence": [],
                            "renewal": False,
                            "client_address": None,
                            "requested_ip": None,
                            "server_id": None,
                            "lease_seconds": None,
                            "t1_seconds": None,
                            "t2_seconds": None,
                        }
                        dhcp_transactions[xid] = transaction
                    elif transaction is None:
                        result["dhcp"]["transactions_truncated"] = True
                    if transaction is not None:
                        if message_type and len(
                            transaction["message_sequence"]
                        ) < 32:
                            transaction["message_sequence"].append(
                                message_type
                            )
                        if request_kind == "renewal":
                            transaction["renewal"] = True
                        for key in (
                            "client_address",
                            "requested_ip",
                            "server_id",
                            "lease_seconds",
                            "t1_seconds",
                            "t2_seconds",
                        ):
                            if dhcp.get(key) is not None:
                                transaction[key] = dhcp[key]
                        if (
                            direction == "reply"
                            and message_type == "ACK"
                            and transaction["renewal"]
                        ):
                            result["dhcp"]["renewal_acks"] += 1
        if protocol == "UDP" and {source_port, destination_port} & {53, 5353}:
            names, direction = dns_names(transport_payload)
            if direction is None:
                result["dns"]["malformed"] += 1
            else:
                target = (
                    dns_responses if direction == "response" else dns_queries
                )
                for name in names:
                    if (
                        include_dns_names
                        and name not in target
                        and len(target) < MAX_RECORDED_DNS_NAMES
                    ):
                        target.append(name)
    result["flows"] = sorted(
        (flow.evidence() for flow in flows.values()),
        key=lambda row: (
            row["protocol"],
            row["source"],
            row["destination"],
        ),
    )
    result["dns"]["queries"] = dns_queries
    result["dns"]["responses"] = dns_responses
    result["dhcp"]["guest_addresses"] = sorted(guest_addresses)
    result["dhcp"]["transactions"] = sorted(
        dhcp_transactions.values(),
        key=lambda row: row["xid"],
    )
    result["dhcp"]["message_types"] = dict(
        sorted(result["dhcp"]["message_types"].items())
    )
    result["egress_destinations"] = sorted(
        destinations.values(),
        key=lambda row: (
            row["scope"],
            row["address"],
            row["port"] or 0,
        ),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize a QEMU Ethernet pcap for review evidence"
    )
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--include-dns-names",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--max-flows", type=int, default=MAX_RECORDED_FLOWS)
    args = parser.parse_args()
    if args.max_flows < 1:
        parser.error("--max-flows must be positive")
    try:
        evidence = summarize_pcap(
            args.capture,
            include_dns_names=args.include_dns_names,
            max_flows=args.max_flows,
        )
    except (OSError, PcapError) as error:
        parser.error(str(error))
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
