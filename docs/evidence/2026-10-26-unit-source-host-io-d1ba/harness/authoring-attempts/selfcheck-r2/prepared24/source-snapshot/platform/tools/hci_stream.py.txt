"""Utilities for parsing raw H4 HCI byte streams."""
from __future__ import annotations


def hci_packet_length(packet_type: int, header: bytes) -> int | None:
    if packet_type == 1:
        return header[3]
    if packet_type == 2:
        return int.from_bytes(header[3:5], "little")
    if packet_type == 3:
        return header[3]
    if packet_type == 4:
        return header[2]
    if packet_type == 5:
        return int.from_bytes(header[3:5], "little")
    return None


def hci_packet_header_size(packet_type: int) -> int | None:
    if packet_type == 1:
        return 4
    if packet_type in (2, 5):
        return 5
    if packet_type == 3:
        return 4
    if packet_type == 4:
        return 3
    return None


class HciStreamParser:
    """Split a raw H4 byte stream into complete HCI packets."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        packets: list[bytes] = []
        while self.buffer:
            packet_type = self.buffer[0]
            header_size = hci_packet_header_size(packet_type)
            if header_size is None:
                raise ValueError(f"unsupported HCI packet type {packet_type}")
            if len(self.buffer) < header_size:
                break
            payload_size = hci_packet_length(
                packet_type,
                bytes(self.buffer),
            )
            if payload_size is None:
                raise ValueError(f"unsupported HCI packet type {packet_type}")
            total_size = header_size + payload_size
            if len(self.buffer) < total_size:
                break
            packets.append(bytes(self.buffer[:total_size]))
            del self.buffer[:total_size]
        return packets
