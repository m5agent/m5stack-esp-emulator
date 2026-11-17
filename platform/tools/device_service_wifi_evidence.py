"""Passive, same-session native STA transport observations."""

from __future__ import annotations

from ipaddress import IPv4Address
from typing import TYPE_CHECKING

from device_service_parsing import is_sha256
from device_service_sta_time_peer import DEVICE as STA_TIME_DEVICE, PROFILE as STA_TIME_PROFILE

if TYPE_CHECKING:
    from device_service_specs import DeviceSpec


_CARDPUTER_STA_MACHINES = {
    "cardputer": "m5cardputer",
    "cardputer-adv": "m5cardputeradv",
}


def native_sta_capability(spec: DeviceSpec, *, backend_ready: bool) -> dict:
    """Advertise only board/native-machine combinations with exercised STA."""
    machine = _CARDPUTER_STA_MACHINES.get(spec.id)
    if (
        not backend_ready or not spec.supported or machine is None
        or spec.machine != machine or spec.service_kind != "qemu"
        or spec.backend != "qemu-esp32s3"
    ):
        return {}
    capability = {"sta": {
        "runtime": "qemu-wifi",
        "profile": "generic-observe",
        "operation_assertions": False,
    }}
    if spec.id == STA_TIME_DEVICE:
        capability["sta_time_fixture"] = {
            "runtime": "qemu-wifi", "profile": STA_TIME_PROFILE,
            "host_ip_backends": 0, "scope": "local-dns-and-sntp",
        }
    return capability


def _ipv4(value: object) -> IPv4Address | None:
    if not isinstance(value, str):
        return None
    try:
        address = IPv4Address(value)
    except ValueError:
        return None
    if address.is_unspecified or address.is_multicast or address.is_loopback or address.is_reserved:
        return None
    return address


def _endpoint(value: object) -> tuple[IPv4Address, int] | None:
    if not isinstance(value, str):
        return None
    host, sep, port = value.rpartition(":")
    if not sep or not port.isascii() or not port.isdigit() or not 1 <= len(port) <= 5:
        return None
    address = _ipv4(host)
    if address is None or not 1 <= int(port) <= 65535:
        return None
    return address, int(port)


def _completed_dora(row: dict) -> IPv4Address | None:
    address = _ipv4(row.get("client_address"))
    if (
        address is None or address != _ipv4(row.get("requested_ip"))
        or _ipv4(row.get("server_id")) is None
        or type(row.get("lease_seconds")) is not int or row["lease_seconds"] <= 0
    ):
        return None
    sequence = row.get("message_sequence")
    if not isinstance(sequence, list):
        return None
    stages = ["DISCOVER", "OFFER", "REQUEST", "ACK"]
    current = 0
    for event in sequence:
        if event in ("NAK", "DECLINE"):
            current = 0
        elif event == stages[current]:
            current += 1
            if current == len(stages):
                return address
    return None


def _count_transport_pairs(rows: list, lease_addresses: set[IPv4Address]) -> dict[str, int]:
    observed = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        transport = row.get("protocol")
        if transport not in ("TCP", "UDP") or type(row.get("payload_bytes")) is not int or row["payload_bytes"] <= 0:
            continue
        source, destination = _endpoint(row.get("source")), _endpoint(row.get("destination"))
        if not source or not destination or source == destination:
            continue
        if transport == "UDP" and {source[1], destination[1]} == {67, 68}:
            continue
        observed.add((transport, source, destination))
    counts = {"TCP": 0, "UDP": 0}
    for transport, source, destination in observed:
        if (
            source[0] in lease_addresses and destination[0] not in lease_addresses
            and (transport, destination, source) in observed
        ):
            counts[transport] += 1
    return counts


def native_sta_data_plane(packet_capture: dict) -> dict:
    """Summarize observed transport. Application semantics require separate proof."""
    receipt = {
        "schema_version": 1,
        "scope": "same-session-native-ipv4-transport",
        "source": "ethernet-pcap",
        "capture_state": "unavailable",
        "capture_sha256": None,
        "dhcpv4": {"completed_dora_transactions": 0, "leased_address_count": 0},
        "tcp": {"bidirectional_payload_flows": 0},
        "udp": {"bidirectional_payload_flows": 0},
    }
    if packet_capture.get("status") == "CAPTURING":
        receipt["capture_state"] = "capturing"
        return receipt
    capture_input = packet_capture.get("input")
    capture_sha256 = capture_input.get("sha256") if isinstance(capture_input, dict) else None
    dhcp = packet_capture.get("dhcp")
    flows = packet_capture.get("flows")
    if (
        packet_capture.get("status") != "PASS" or packet_capture.get("format") != "pcap"
        or packet_capture.get("linktype") != 1
        or packet_capture.get("truncated_records") or packet_capture.get("malformed_records")
        or packet_capture.get("flows_truncated")
        or not isinstance(capture_sha256, str) or not is_sha256(capture_sha256)
        or not isinstance(dhcp, dict) or dhcp.get("transactions_truncated")
        or not isinstance(dhcp.get("transactions"), list) or not isinstance(flows, list)
    ):
        return receipt
    leases = {}
    for row in dhcp["transactions"]:
        if isinstance(row, dict) and isinstance(row.get("xid"), str) and row["xid"]:
            if address := _completed_dora(row):
                leases[row["xid"]] = address
    lease_addresses = set(leases.values())
    counts = _count_transport_pairs(flows, lease_addresses)
    receipt["capture_state"] = "finalized"
    receipt["capture_sha256"] = capture_sha256
    receipt["dhcpv4"] = {
        "completed_dora_transactions": len(leases),
        "leased_address_count": len(lease_addresses),
    }
    receipt["tcp"]["bidirectional_payload_flows"] = counts["TCP"]
    receipt["udp"]["bidirectional_payload_flows"] = counts["UDP"]
    return receipt
