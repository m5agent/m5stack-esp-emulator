#!/usr/bin/env python3
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from pcap_summary import PcapError, summarize_pcap  # noqa: E402


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f">{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def ipv4_udp(
    payload: bytes,
    *,
    source: str = "10.0.2.15",
    destination: str = "10.0.2.3",
    source_port: int = 53000,
    destination_port: int = 53,
) -> bytes:
    udp = struct.pack(">HHHH", source_port, destination_port, 8 + len(payload), 0)
    udp += payload
    source_bytes = bytes(map(int, source.split(".")))
    destination_bytes = bytes(map(int, destination.split(".")))
    header = bytearray(
        struct.pack(
            ">BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(udp),
            1,
            0,
            64,
            17,
            0,
            source_bytes,
            destination_bytes,
        )
    )
    struct.pack_into(">H", header, 10, _checksum(bytes(header)))
    return bytes(header) + udp


def ipv4_tcp(
    payload: bytes,
    *,
    source: str = "10.0.2.15",
    destination: str = "8.8.8.8",
) -> bytes:
    tcp = bytearray(
        struct.pack(
            ">HHIIBBHHH",
            53001,
            80,
            1,
            0,
            5 << 4,
            0x18,
            65535,
            0,
            0,
        )
    )
    header = bytearray(
        struct.pack(
            ">BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(tcp) + len(payload),
            2,
            0,
            64,
            6,
            0,
            bytes(map(int, source.split("."))),
            bytes(map(int, destination.split("."))),
        )
    )
    struct.pack_into(">H", header, 10, _checksum(bytes(header)))
    return bytes(header) + bytes(tcp) + payload


def ethernet(packet: bytes, ether_type: int = 0x0800) -> bytes:
    return (
        b"\x02\x00\x00\x00\x00\x01"
        b"\x02\x00\x00\x00\x00\x02"
        + struct.pack(">H", ether_type)
        + packet
    )


def pcap(frames: list[bytes]) -> bytes:
    output = bytearray(
        b"\xd4\xc3\xb2\xa1"
        + struct.pack("<HHiIII", 2, 4, 0, 0, 262144, 1)
    )
    for index, frame in enumerate(frames):
        output.extend(
            struct.pack(
                "<IIII",
                100 + index,
                index * 1000,
                len(frame),
                len(frame),
            )
        )
        output.extend(frame)
    return bytes(output)


def dns_query(name: str = "example.com") -> bytes:
    labels = b"".join(
        bytes([len(label)]) + label.encode()
        for label in name.split(".")
    )
    return (
        struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
        + labels
        + b"\0"
        + struct.pack(">HH", 1, 1)
    )


class PcapSummaryTests(unittest.TestCase):
    def test_summarizes_dns_tcp_dhcp_without_payloads(self):
        dhcp = ethernet(
            ipv4_udp(
                b"DHCP-SECRET-OPTION",
                source="0.0.0.0",
                destination="255.255.255.255",
                source_port=68,
                destination_port=67,
            )
        )
        dns = ethernet(ipv4_udp(dns_query()))
        http = ethernet(ipv4_tcp(b"Authorization: Bearer secret"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "network.pcap"
            path.write_bytes(pcap([dhcp, dns, http]))
            summary = summarize_pcap(path)
        self.assertEqual(summary["packets"], 3)
        self.assertEqual(summary["dhcp"]["packets"], 1)
        self.assertEqual(summary["dns"]["queries"], ["example.com."])
        self.assertEqual(summary["protocols"]["TCP"], 1)
        self.assertEqual(summary["protocols"]["UDP"], 2)
        self.assertNotIn("secret", repr(summary).lower())
        self.assertTrue(
            any(
                row["destination"] == "8.8.8.8:80"
                for row in summary["flows"]
            )
        )
        self.assertTrue(
            any(
                row["address"] == "8.8.8.8"
                and row["scope"] == "global"
                for row in summary["egress_destinations"]
            )
        )

    def test_dhcp_reply_identifies_guest_and_excludes_reply_from_egress(self):
        bootp = bytearray(244)
        bootp[0] = 2
        bootp[16:20] = bytes((10, 0, 2, 15))
        reply = ethernet(
            ipv4_udp(
                bytes(bootp),
                source="10.0.2.2",
                destination="255.255.255.255",
                source_port=67,
                destination_port=68,
            )
        )
        dns = ethernet(
            ipv4_udp(
                dns_query(),
                destination="10.0.2.3",
            )
        )
        response = ethernet(
            ipv4_udp(
                dns_query(),
                source="10.0.2.3",
                destination="10.0.2.15",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "network.pcap"
            path.write_bytes(pcap([reply, dns, response]))
            summary = summarize_pcap(path)
        self.assertEqual(summary["dhcp"]["guest_addresses"], ["10.0.2.15"])
        addresses = {
            row["address"]: row["packets"]
            for row in summary["egress_destinations"]
        }
        self.assertEqual(addresses["10.0.2.3"], 1)
        self.assertNotIn("10.0.2.15", addresses)

    def test_can_omit_dns_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "network.pcap"
            path.write_bytes(pcap([ethernet(ipv4_udp(dns_query()))]))
            summary = summarize_pcap(path, include_dns_names=False)
        self.assertEqual(summary["dns"]["queries"], [])
        self.assertFalse(summary["dns"]["names_included"])

    def test_rejects_pcapng_and_other_linktypes(self):
        with tempfile.TemporaryDirectory() as tmp:
            pcapng = Path(tmp) / "capture.pcapng"
            pcapng.write_bytes(b"\x0a\x0d\x0d\x0a" + b"\0" * 32)
            with self.assertRaisesRegex(PcapError, "pcapng"):
                summarize_pcap(pcapng)
            raw = Path(tmp) / "raw.pcap"
            raw.write_bytes(
                b"\xd4\xc3\xb2\xa1"
                + struct.pack("<HHiIII", 2, 4, 0, 0, 65535, 101)
            )
            with self.assertRaisesRegex(PcapError, "unsupported linktype"):
                summarize_pcap(raw)

    def test_tolerates_truncated_packet_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "truncated.pcap"
            path.write_bytes(
                pcap([ethernet(dns_query())])[:-8]
            )
            summary = summarize_pcap(path)
        self.assertEqual(summary["packets"], 0)
        self.assertGreaterEqual(summary["truncated_records"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
