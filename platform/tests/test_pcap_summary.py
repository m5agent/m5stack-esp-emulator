#!/usr/bin/env python3
from __future__ import annotations

from hashlib import sha256
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from pcap_summary import PcapError, _scope, summarize_pcap  # noqa: E402
from device_service_wifi_evidence import native_sta_data_plane  # noqa: E402


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
    source_port: int = 53001,
    destination_port: int = 80,
    sequence: int = 1,
    acknowledgement: int = 0,
    flags: int = 0x18,
) -> bytes:
    tcp = bytearray(
        struct.pack(
            ">HHIIBBHHH",
            source_port,
            destination_port,
            sequence,
            acknowledgement,
            5 << 4,
            flags,
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


def dhcp_packet(
    *,
    operation: int,
    xid: int,
    message_type: int,
    client_address: str = "0.0.0.0",
    assigned_address: str = "0.0.0.0",
    requested_ip: str | None = None,
    server_id: str | None = None,
    lease_seconds: int | None = None,
) -> bytes:
    packet = bytearray(244)
    packet[0] = operation
    packet[1] = 1
    packet[2] = 6
    struct.pack_into(">I", packet, 4, xid)
    packet[12:16] = bytes(map(int, client_address.split(".")))
    packet[16:20] = bytes(map(int, assigned_address.split(".")))
    packet[28:34] = b"\x02\x00\x00\x00\x00\x01"
    packet[236:240] = b"\x63\x82\x53\x63"
    options = bytearray((53, 1, message_type))
    if requested_ip:
        options.extend((50, 4, *map(int, requested_ip.split("."))))
    if server_id:
        options.extend((54, 4, *map(int, server_id.split("."))))
    if lease_seconds is not None:
        options.extend((51, 4))
        options.extend(struct.pack(">I", lease_seconds))
    options.append(255)
    packet[240 : 240 + len(options)] = options
    return bytes(packet[: 240 + len(options)])


class PcapSummaryTests(unittest.TestCase):
    @staticmethod
    def dhcp_exchange_frame(kind, *, xid=0x11223344, renewal=False):
        reply = kind in (2, 5, 6)
        return ethernet(ipv4_udp(
            dhcp_packet(
                operation=2 if reply else 1, xid=xid, message_type=kind,
                client_address="10.0.2.15" if renewal else "0.0.0.0",
                assigned_address="10.0.2.15" if reply else "0.0.0.0",
                requested_ip="10.0.2.15" if kind == 3 and not renewal else None,
                server_id="10.0.2.2" if kind != 1 else None,
                lease_seconds=120 if reply else None,
            ),
            source="10.0.2.2" if reply else "10.0.2.15" if renewal else "0.0.0.0",
            destination="255.255.255.255",
            source_port=67 if reply else 68, destination_port=68 if reply else 67,
        ))

    def test_repeated_discover_does_not_hide_dora_and_transport(self):
        frames = [self.dhcp_exchange_frame(kind) for kind in [1] * 67 + [2, 3, 3, 5]]
        for port in (53001, 53002):
            frames.extend([
                ethernet(ipv4_tcp(b"request", source_port=port, destination="10.0.2.2")),
                ethernet(ipv4_tcp(b"reply", source="10.0.2.2", destination="10.0.2.15",
                                  source_port=80, destination_port=port)),
            ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retries.pcap"
            path.write_bytes(pcap(frames))
            summary = summarize_pcap(path)
        self.assertEqual(summary["dhcp"]["packets"], 71)
        self.assertEqual(summary["dhcp"]["message_types"], {
            "discover": 67, "offer": 1, "request": 2, "ack": 1,
        })
        self.assertEqual(summary["dhcp"]["transactions"][0]["message_sequence"],
                         ["DISCOVER", "OFFER", "REQUEST", "ACK"])
        self.assertFalse(summary["dhcp"]["transactions_truncated"])
        receipt = native_sta_data_plane(summary)
        self.assertEqual(receipt["dhcpv4"]["completed_dora_transactions"], 1)
        self.assertEqual(receipt["tcp"]["bidirectional_payload_flows"], 2)

    def test_repeated_renewal_keeps_packet_counts_without_becoming_dora(self):
        frames = [self.dhcp_exchange_frame(kind, renewal=True) for kind in [3] * 67 + [5, 5]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "renewal.pcap"
            path.write_bytes(pcap(frames))
            summary = summarize_pcap(path)
        self.assertEqual(summary["dhcp"]["renewal_requests"], 67)
        self.assertEqual(summary["dhcp"]["renewal_acks"], 2)
        self.assertEqual(summary["dhcp"]["transactions"][0]["message_sequence"], ["REQUEST", "ACK"])
        self.assertEqual(native_sta_data_plane(summary)["dhcpv4"]["completed_dora_transactions"], 0)

    def test_dhcp_retries_do_not_reorder_or_skip_negative_states(self):
        for sequence in ([5], [1, 3, 2, 5], [1, 2, 3, 6, 5], [1, 2, 3, 4, 5]):
            with self.subTest(sequence=sequence), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "incomplete.pcap"
                path.write_bytes(pcap([self.dhcp_exchange_frame(kind) for kind in sequence]))
                receipt = native_sta_data_plane(summarize_pcap(path))
                self.assertEqual(receipt["capture_state"], "finalized")
                self.assertEqual(receipt["dhcpv4"]["completed_dora_transactions"], 0)
                self.assertEqual(receipt["tcp"]["bidirectional_payload_flows"], 0)

    def test_dhcp_state_limit_keeps_incomplete_evidence_unknown(self):
        sequence = [1, 3] * 17 + [2, 3, 5]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "too-many-states.pcap"
            path.write_bytes(pcap([self.dhcp_exchange_frame(kind) for kind in sequence]))
            summary = summarize_pcap(path)
        transaction, = summary["dhcp"]["transactions"]
        self.assertEqual(len(transaction["message_sequence"]), 32)
        self.assertTrue(transaction["message_sequence_truncated"])
        self.assertTrue(summary["dhcp"]["transactions_truncated"])
        self.assertEqual(summary["dhcp"]["packets"], len(sequence))
        self.assertEqual(summary["dhcp"]["message_types"]["ack"], 1)
        self.assertEqual(native_sta_data_plane(summary)["capture_state"], "unavailable")

    def test_reset_cutoff_requires_a_new_exchange_even_when_xid_repeats(self):
        xid = 0x11223344
        frames = []
        for kind in (1, 2, 3, 5):
            reply = kind in (2, 5)
            frames.append(ethernet(ipv4_udp(
                dhcp_packet(
                    operation=2 if reply else 1,
                    xid=xid, message_type=kind,
                    assigned_address="10.0.2.15" if reply else "0.0.0.0",
                    requested_ip="10.0.2.15" if kind == 3 else None,
                    server_id="10.0.2.2" if kind != 1 else None,
                    lease_seconds=120 if reply else None,
                ),
                source="10.0.2.2" if reply else "0.0.0.0",
                destination="255.255.255.255",
                source_port=67 if reply else 68, destination_port=68 if reply else 67,
            )))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.pcap"
            cutoff = len(pcap(frames))
            path.write_bytes(pcap(frames + frames[:1]))
            cold = summarize_pcap(path)
            incomplete = summarize_pcap(path, record_start_offset=cutoff)
            self.assertEqual(incomplete["input"], cold["input"])
            self.assertEqual(incomplete["dhcp"]["transactions"][0]["message_sequence"], ["DISCOVER"])
            path.write_bytes(pcap(frames + frames))
            rejoin = summarize_pcap(path, record_start_offset=cutoff)
            transaction, = rejoin["dhcp"]["transactions"]
            self.assertEqual(transaction["xid"], "11223344")
            self.assertEqual(transaction["message_sequence"], ["DISCOVER", "OFFER", "REQUEST", "ACK"])
            self.assertEqual(rejoin["packets"], 4)
            with self.assertRaises(PcapError):
                summarize_pcap(path, record_start_offset=path.stat().st_size + 1)

    def test_ipv6_site_local_scope_is_not_global(self) -> None:
        self.assertEqual(_scope("fec0::2"), "site-local")

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

    def test_distinguishes_initial_and_renewal_dhcp_transactions(self):
        initial_xid = 0x11223344
        renewal_xid = 0x55667788
        frames = [
            ethernet(
                ipv4_udp(
                    dhcp_packet(
                        operation=1,
                        xid=initial_xid,
                        message_type=1,
                    ),
                    source="0.0.0.0",
                    destination="255.255.255.255",
                    source_port=68,
                    destination_port=67,
                )
            ),
            ethernet(
                ipv4_udp(
                    dhcp_packet(
                        operation=2,
                        xid=initial_xid,
                        message_type=2,
                        assigned_address="10.0.2.15",
                        server_id="10.0.2.2",
                        lease_seconds=120,
                    ),
                    source="10.0.2.2",
                    destination="255.255.255.255",
                    source_port=67,
                    destination_port=68,
                )
            ),
            ethernet(
                ipv4_udp(
                    dhcp_packet(
                        operation=1,
                        xid=initial_xid,
                        message_type=3,
                        requested_ip="10.0.2.15",
                        server_id="10.0.2.2",
                    ),
                    source="0.0.0.0",
                    destination="255.255.255.255",
                    source_port=68,
                    destination_port=67,
                )
            ),
            ethernet(
                ipv4_udp(
                    dhcp_packet(
                        operation=2,
                        xid=initial_xid,
                        message_type=5,
                        assigned_address="10.0.2.15",
                        server_id="10.0.2.2",
                        lease_seconds=120,
                    ),
                    source="10.0.2.2",
                    destination="255.255.255.255",
                    source_port=67,
                    destination_port=68,
                )
            ),
            ethernet(
                ipv4_udp(
                    dhcp_packet(
                        operation=1,
                        xid=renewal_xid,
                        message_type=3,
                        client_address="10.0.2.15",
                    ),
                    source="10.0.2.15",
                    destination="10.0.2.2",
                    source_port=68,
                    destination_port=67,
                )
            ),
            ethernet(
                ipv4_udp(
                    dhcp_packet(
                        operation=2,
                        xid=renewal_xid,
                        message_type=5,
                        client_address="10.0.2.15",
                        assigned_address="10.0.2.15",
                        server_id="10.0.2.2",
                        lease_seconds=120,
                    ),
                    source="10.0.2.2",
                    destination="10.0.2.15",
                    source_port=67,
                    destination_port=68,
                )
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dhcp.pcap"
            path.write_bytes(pcap(frames))
            summary = summarize_pcap(path)

        dhcp = summary["dhcp"]
        self.assertEqual(dhcp["selecting_requests"], 1)
        self.assertEqual(dhcp["renewal_requests"], 1)
        self.assertEqual(dhcp["renewal_acks"], 1)
        self.assertEqual(
            dhcp["message_types"],
            {
                "ack": 2,
                "discover": 1,
                "offer": 1,
                "request": 2,
            },
        )
        transactions = {
            row["xid"]: row for row in dhcp["transactions"]
        }
        self.assertFalse(transactions["11223344"]["renewal"])
        self.assertTrue(transactions["55667788"]["renewal"])
        self.assertEqual(
            transactions["55667788"]["message_sequence"],
            ["REQUEST", "ACK"],
        )
        self.assertEqual(
            transactions["55667788"]["lease_seconds"],
            120,
        )
        self.assertEqual(dhcp["guest_addresses"], ["10.0.2.15"])

    @staticmethod
    def fixture_tcp(port, request, reply, *, faults=()):
        client, peer = "10.0.2.15", "10.0.2.2"
        sequence, response = 0xffffffff, 700

        def segment(payload=b"", *, incoming=False, seq, ack, flags=0x18):
            return ethernet(ipv4_tcp(payload, source=peer if incoming else client, destination=client if incoming else peer,
                                     source_port=port if incoming else 53001, destination_port=53001 if incoming else port,
                                     sequence=seq, acknowledgement=ack, flags=flags))

        frames = [segment(seq=sequence, ack=0, flags=2),
                  segment(seq=response, ack=0, flags=0x12, incoming=True),
                  segment(seq=0, ack=response + 1, flags=0x10),
                  segment(request[3:], seq=3, ack=response + 1)]
        if "gap" not in faults:
            frames += [segment(request[:3], seq=0, ack=response + 1)]
        if "overlap" in faults:
            frames += [segment(b"invalid", seq=3, ack=response + 1)]
        else:
            frames += [segment(request[3:], seq=3, ack=response + 1)]
        frames += [segment(reply, seq=response + 1, ack=len(request), incoming=True)]
        if "reused" in faults:
            frames += [segment(seq=sequence, ack=0, flags=2)]
        return frames

    def fixture_summary(self, frames, ports, *, truncate=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.pcap"
            data = pcap(frames)
            path.write_bytes(data[:-1] if truncate else data)
            return summarize_pcap(path, fixture_tcp_ports=ports)

    def test_fixture_streams_bind_tcp_data_and_http_body_after_reassembly(self):
        sent, reply = b"\0\x03ab\x00", b"\0\x03cd\xff"
        body, answer = b"a\0b", b"c\x00d"
        http = b"POST /native-sta-post HTTP/1.1\r\nHost: post.native-sta.test:18193\r\nContent-Length: 3\r\n\r\n" + body
        response = b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\n" + answer
        frames = self.fixture_tcp(19193, sent, reply) + self.fixture_tcp(18193, http, response)
        result = self.fixture_summary(frames, {18193, 19193})
        self.assertIs(result["tcp_fixture_streams_complete"], True)
        self.assertEqual(len(result["tcp_fixture_streams"]), 2)
        post, tcp = result["tcp_fixture_streams"]
        self.assertEqual((post["kind"], post["request"]["authority"], post["reply"]["status_code"]),
                         ("http_post", "post.native-sta.test", 200))
        self.assertEqual(post["client"], "10.0.2.15:53001")
        self.assertEqual(post["peer"], "10.0.2.2:18193")
        self.assertEqual(post["request"]["body_sha256"], sha256(body).hexdigest())
        self.assertEqual(post["reply"]["body_sha256"], sha256(answer).hexdigest())
        self.assertEqual(tcp["request"]["wire_sha256"], sha256(sent).hexdigest())
        self.assertEqual(tcp["reply"]["body_sha256"], sha256(reply[2:]).hexdigest())
        legacy = self.fixture_summary(frames, set())
        self.assertNotIn("tcp_fixture_streams", legacy)

    def test_unconfirmed_streams_are_not_reported_complete(self):
        sent, reply = b"\0\x03abc", b"\0\x03def"
        for fault in ("gap", "overlap", "reused"):
            with self.subTest(fault=fault):
                result = self.fixture_summary(self.fixture_tcp(19193, sent, reply, faults=(fault,)), {19193})
                self.assertIs(result["tcp_fixture_streams_complete"], False)
                self.assertEqual(result["tcp_fixture_streams"], [])
        incomplete_http = b"POST /native-sta-post HTTP/1.1\r\nHost: post.native-sta.test\r\nContent-Length: 4\r\n\r\nabc"
        http_reply = b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\ndef"
        result = self.fixture_summary(self.fixture_tcp(18193, incomplete_http, http_reply), {18193})
        self.assertIs(result["tcp_fixture_streams_complete"], False)
        self.assertIs(self.fixture_summary(self.fixture_tcp(19193, sent, reply), {19193}, truncate=True)[
            "tcp_fixture_streams_complete"], False)

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
