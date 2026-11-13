"""Synthetic protocol fixtures; no local evidence cache or cloud access required."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
import uiflow_cloud_status as cloud  # noqa: E402

KEY = b"dGhlIHNhbXBsZSBub25jZQ=="
ACCEPT = base64.b64encode(hashlib.sha1(KEY + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
IDENTITY = "020000000001"  # Synthetic locally administered fixture identity.
TOPIC = "$m5/uiflow/v2/down/" + IDENTITY + "/syscmd"


def request(host="uiflow2.m5stack.com", path="/ws/realtime", role="device"):
    return (f"GET {path}?role={role}&mac={IDENTITY} HTTP/1.1\r\nHost: {host}\r\n"
            "Connection: keep-alive, Upgrade\r\nUpgrade: websocket\r\n"
            "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ").encode() + KEY + b"\r\n\r\n"


def response():
    return b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: " + ACCEPT + b"\r\n\r\n"


def ws(payload, opcode=1, masked=False, final=True):
    if isinstance(payload, str):
        payload = payload.encode()
    size = len(payload)
    header = bytes([(128 if final else 0) | opcode, (128 if masked else 0) | (size if size < 126 else 126)])
    if size >= 126:
        header += struct.pack("!H", size)
    if masked:
        mask = b"TEST"
        return header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
    return header + payload


def packet(payload=b"", *, server=False, port=80, client_port=50000, seq=1000, flags=0x18):
    addresses = (b"\xc0\x00\x02\x01", b"\xc6\x33\x64\x01")
    source, target = addresses[::-1] if server else addresses
    source_port, target_port = (port, client_port) if server else (client_port, port)
    tcp = struct.pack("!HHIIBBHHH", source_port, target_port, seq, 0, 0x50, flags, 65535, 0, 0) + payload
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0, source, target)
    return b"\x00" * 12 + b"\x08\x00" + ip + tcp


class Flow:
    def __init__(self, port=80, client_port=50000):
        self.port, self.client_port = port, client_port
        self.sequences = [1000, 9000]

    def send(self, payload=b"", *, server=False, flags=0x18):
        seq = self.sequences[int(server)]
        self.sequences[int(server)] += len(payload) + bool(flags & 2) + bool(flags & 1)
        return packet(payload, server=server, port=self.port, client_port=self.client_port, seq=seq, flags=flags)


def pcap(*frames):
    data = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for i, frame in enumerate(frames):
        data += struct.pack("<IIII", i + 1, 0, len(frame), len(frame)) + frame
    return data


def mqtt_string(text):
    data = text.encode()
    return struct.pack("!H", len(data)) + data


def mqtt(header, body):
    remaining, encoded = len(body), bytearray()
    while True:
        digit = remaining % 128
        remaining //= 128
        encoded.append(digit | (128 if remaining else 0))
        if not remaining:
            return bytes([header]) + bytes(encoded) + body


def mqtt_fixture(*, topic=TOPIC, code="test-code-private", accepted=True, subscribe=True):
    client = mqtt(0x10, mqtt_string("MQTT") + b"\x04\x02\x00\x3c" + mqtt_string("fixture-" + IDENTITY))
    if subscribe:
        client += mqtt(0x82, b"\x00\x01" + mqtt_string(TOPIC) + b"\x00")
    server = mqtt(0x20, b"\x00" + bytes([0 if accepted else 5]))
    server += mqtt(0x30, mqtt_string(topic) + json.dumps({"data": {"code": code}}).encode())
    return client, server


class CloudStatusTests(unittest.TestCase):
    def observe(self, *frames):
        return cloud.observe_uiflow_cloud_pcap(pcap(*frames))

    def handshake(self, incoming=b"", outgoing=b"", **kwargs):
        flow = Flow()
        frames = [flow.send(request(**kwargs)), flow.send(response(), server=True)]
        if outgoing:
            frames.append(flow.send(outgoing))
        if incoming:
            frames.append(flow.send(incoming, server=True))
        return flow, frames

    def test_handshake_does_not_claim_heartbeat_or_binding(self):
        _, frames = self.handshake()
        result = self.observe(*frames)
        self.assertEqual(result["webrepl"]["state"], "handshake_observed")
        self.assertEqual(result["pairing"]["state"], "not_observed")
        self.assertFalse(result["webrepl"]["device_registered"])

    def test_business_errors_are_fixed_enums_even_after_fin(self):
        for payload, reason in [("mac has not been bound to a deviceId", "mac_not_bound"),
                                ("mac does not exist", "mac_not_found"),
                                ("private-server-detail", "server_error"), ({"secret": "hidden"}, "server_error")]:
            with self.subTest(reason=reason):
                body = json.dumps({"type": "error", "payload": payload, "mac": IDENTITY, "deviceId": "private-id"})
                flow, frames = self.handshake(ws(body))
                result = self.observe(*frames, flow.send(server=True, flags=0x11))
                self.assertEqual(result["webrepl"]["reason"], reason)
                self.assertEqual(result["webrepl"]["state"], "server_error" if reason == "server_error" else "identity_rejected")
                self.assertEqual(result["webrepl"]["disconnects"], 1)
                encoded = json.dumps(result)
                for private in (IDENTITY, "private-id", "private-server-detail", "hidden", "uiflow2.m5stack.com", "198.51.100.1"):
                    self.assertNotIn(private, encoded)

    def test_registered_requires_matching_mac_and_nonempty_device_id(self):
        for identity, device_id, expected in [(IDENTITY, "fixture", True), ("020000000002", "fixture", False), (IDENTITY, "", False)]:
            _, frames = self.handshake(ws(json.dumps({"type": "deviceConnected", "mac": identity, "deviceId": device_id})))
            result = self.observe(*frames)
            self.assertEqual(result["webrepl"]["device_registered"], expected)
            self.assertEqual(result["webrepl"]["state"], "handshake_observed")

    def test_text_heartbeat_requires_roundtrip_in_same_connection(self):
        _, frames = self.handshake(ws("PONG"), ws("PING", masked=True))
        result = self.observe(*frames)
        self.assertEqual(result["webrepl"]["state"], "heartbeat_observed")
        self.assertEqual(result["webrepl"]["heartbeat_roundtrips"], 1)
        _, one_way = self.handshake(ws("PONG"))
        self.assertEqual(self.observe(*one_way)["webrepl"]["state"], "handshake_observed")
        other = Flow(client_port=50001)
        _, first = self.handshake(outgoing=ws("PING", masked=True))
        first += [other.send(request()), other.send(response() + ws("PONG"), server=True)]
        self.assertEqual(self.observe(*first)["webrepl"]["heartbeat_roundtrips"], 0)

    def test_reverse_and_control_heartbeat_match_payload_once(self):
        flow, frames = self.handshake(ws("PING"))
        frames.append(flow.send(ws("PONG", masked=True)))
        self.assertEqual(self.observe(*frames)["webrepl"]["heartbeat_roundtrips"], 1)
        for reply, expected in [(b"same", 1), (b"wrong", 0)]:
            _, frames = self.handshake(ws(reply, opcode=10), ws(b"same", opcode=9, masked=True) * 2)
            self.assertEqual(self.observe(*frames)["webrepl"]["heartbeat_roundtrips"], expected)

    def test_fin_retains_observed_heartbeat_count(self):
        flow, frames = self.handshake(ws("PONG"), ws("PING", masked=True))
        result = self.observe(*frames, flow.send(flags=0x11))
        self.assertEqual(result["webrepl"]["state"], "disconnected")
        self.assertEqual(result["webrepl"]["heartbeat_roundtrips"], 1)

    def test_fragmented_json_with_interleaved_control_frame(self):
        message = b'{"type":"error","payload":"mac does not exist"}'
        incoming = ws(message[:17], final=False) + ws(b"probe", opcode=9) + ws(message[17:], opcode=0)
        _, frames = self.handshake(incoming)
        self.assertEqual(self.observe(*frames)["webrepl"]["reason"], "mac_not_found")

    def test_tcp_split_reordered_and_retransmitted(self):
        client = request()
        server = response() + ws('{"type":"error","payload":"mac does not exist"}')
        frames = [packet(client[20:], seq=1020), packet(client[:20], seq=1000),
                  packet(client[:20], seq=1000), packet(server[31:], server=True, seq=9031),
                  packet(server[:31], server=True, seq=9000)]
        result = self.observe(*frames)
        self.assertEqual(result["webrepl"]["reason"], "mac_not_found")
        self.assertEqual(result["observation"]["status"], "complete")

    def test_gap_and_conflicting_retransmission_are_unavailable(self):
        client = request()
        for frame, reason in [(packet(client[21:], seq=1021), "stream_gap"),
                              (packet(b"X" + client[19:], seq=1018), "stream_conflict")]:
            result = self.observe(packet(client[:20], seq=1000), frame, packet(response(), server=True, seq=9000))
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["observation"]["reason"], reason)
            self.assertEqual(result["webrepl"]["handshakes"], 0)

    def test_wrong_origin_path_role_and_accept_are_not_trusted(self):
        error = ws('{"type":"error","payload":"mac does not exist"}')
        for change in [{"host": "uiflow2.m5stack.com.example"}, {"host": "other.example"},
                       {"path": "/other"}, {"role": "client"}, {"role": "device&role=client"}]:
            _, frames = self.handshake(error, **change)
            self.assertEqual(self.observe(*frames)["webrepl"]["handshakes"], 0)
        for reply in [response().replace(ACCEPT, b"wrong"), response().replace(b"101", b"200")]:
            result = self.observe(packet(request()), packet(reply + error, server=True, seq=9000))
            self.assertEqual(result["webrepl"]["handshakes"], 0)

    def test_http_duplicate_headers_are_unavailable(self):
        duplicate = request().replace(b"Host:", b"Host: other.example\r\nHost:")
        result = self.observe(packet(duplicate), packet(response(), server=True, seq=9000))
        self.assertEqual(result["observation"]["reason"], "malformed_http")

    def test_partial_capture_and_frame_keep_only_completed_facts(self):
        _, frames = self.handshake()
        capture = pcap(*frames) + struct.pack("<IIII", 4, 0, 100, 100) + b"tail"
        result = cloud.observe_uiflow_cloud_pcap(capture)
        self.assertEqual(result["webrepl"]["state"], "handshake_observed")
        self.assertTrue(result["observation"]["partial_tail"])
        _, frames = self.handshake(ws("PONG")[:-1], ws("PING", masked=True))
        result = self.observe(*frames)
        self.assertTrue(result["observation"]["partial_stream"])
        self.assertEqual(result["webrepl"]["heartbeat_roundtrips"], 0)

    def test_huge_ws_length_mask_and_invalid_fragment_fail_closed(self):
        bad_frames = [b"\x81\x7f" + (1 << 63).to_bytes(8, "big"), ws("bad", masked=True),
                      ws("orphan", opcode=0), ws("bad", opcode=9, final=False), b"\x81\x7e\x00\x01X"]
        for incoming in bad_frames:
            _, frames = self.handshake(incoming)
            result = self.observe(*frames)
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["webrepl"]["handshakes"], 0)

    def test_unknown_or_deep_json_never_becomes_ready(self):
        for payload in [b"not-json-private", b"[" * 1500 + b"0" + b"]" * 1500]:
            _, frames = self.handshake(ws(payload))
            result = self.observe(*frames)
            self.assertTrue(result["observation"]["protocol_unknown"])
            self.assertEqual(result["webrepl"]["state"], "handshake_observed")
            self.assertNotIn("not-json-private", json.dumps(result))

    def test_mqtt_pairing_requires_same_flow_subscription_and_accept(self):
        for kwargs, expected in [({}, "code_received"), ({"accepted": False}, "not_observed"),
                                 ({"subscribe": False}, "not_observed"),
                                 ({"topic": TOPIC.replace(IDENTITY, "020000000002")}, "not_observed"),
                                 ({"code": ""}, "not_observed"), ({"code": 123456}, "not_observed")]:
            client, server = mqtt_fixture(**kwargs)
            result = self.observe(packet(client, port=1883), packet(server, port=1883, server=True, seq=9000))
            self.assertEqual(result["pairing"]["state"], expected)
            self.assertNotIn("test-code-private", json.dumps(result))
            self.assertNotIn(TOPIC, json.dumps(result))
            self.assertEqual(result["webrepl"]["state"], "not_observed")

    def test_mqtt_split_header_and_partial_last_packet(self):
        client, server = mqtt_fixture()
        result = self.observe(packet(client[:1], port=1883), packet(client[1:], port=1883, seq=1001),
                              packet(server, server=True, port=1883, seq=9000),
                              packet(b"\x30\x10", server=True, port=1883, seq=9000 + len(server)))
        self.assertEqual(result["pairing"]["state"], "code_received")
        self.assertTrue(result["observation"]["partial_stream"])

    def test_mqtt_huge_or_malformed_remaining_length_is_unavailable(self):
        for data in [b"\x30\xff\xff\xff\x7f", b"\x30\xff\xff\xff\xff"]:
            result = self.observe(packet(data, port=1883, server=True))
            self.assertEqual(result["state"], "unavailable")

    def test_pairing_and_webrepl_are_independent(self):
        client, server = mqtt_fixture()
        _, frames = self.handshake(ws('{"type":"error","payload":"mac does not exist"}'))
        result = self.observe(*frames, packet(client, port=1883), packet(server, port=1883, server=True, seq=9000))
        self.assertEqual(result["pairing"]["state"], "code_received")
        self.assertEqual(result["webrepl"]["state"], "identity_rejected")

    def test_same_tuple_new_syn_does_not_reuse_old_heartbeat(self):
        flow = Flow()
        frames = [flow.send(flags=2), flow.send(request()), flow.send(response(), server=True),
                  flow.send(ws("PING", masked=True)), flow.send(ws("PONG"), server=True), flow.send(flags=0x11)]
        second = Flow()
        second.sequences = [20000, 30000]
        frames += [second.send(flags=2), second.send(request()), second.send(response(), server=True)]
        result = self.observe(*frames)
        self.assertEqual(result["webrepl"]["handshakes"], 2)
        self.assertEqual(result["webrepl"]["state"], "handshake_observed")
        self.assertEqual(result["webrepl"]["heartbeat_roundtrips"], 0)

    def test_control_ping_absence_is_only_an_observation(self):
        _, frames = self.handshake(outgoing=ws(b"", opcode=9, masked=True))
        result = self.observe(*frames)
        self.assertEqual(result["webrepl"]["state"], "handshake_observed")
        self.assertIsNone(result["webrepl"]["reason"])
        self.assertEqual(result["webrepl"]["protocol_ping_sent"], 1)
        self.assertEqual(result["webrepl"]["protocol_pong_received"], 0)
        self.assertEqual(result["webrepl"]["protocol_ping_without_pong_count"], 1)

    def test_pong_after_fin_does_not_count_as_live_roundtrip(self):
        flow, frames = self.handshake(outgoing=ws("PING", masked=True))
        frames += [flow.send(flags=0x11), flow.send(ws("PONG"), server=True)]
        result = self.observe(*frames)
        self.assertEqual(result["webrepl"]["state"], "disconnected")
        self.assertEqual(result["webrepl"]["heartbeat_roundtrips"], 0)

    def test_syn_and_fin_sequences_detect_missing_edges(self):
        flow = Flow()
        syn = flow.send(flags=2)
        client = request()
        lost_prefix = packet(client[4:], seq=1005)
        result = self.observe(syn, lost_prefix, flow.send(response(), server=True))
        self.assertEqual(result["observation"]["reason"], "stream_gap")
        _, frames = self.handshake()
        frames.append(packet(server=True, seq=9000 + len(response()) + 5, flags=0x11))
        self.assertEqual(self.observe(*frames)["observation"]["reason"], "stream_gap")

    def test_capture_stream_and_packet_limits(self):
        self.assertEqual(cloud.observe_uiflow_cloud_pcap(b"x" * (cloud.MAX_CAPTURE_BYTES + 1))["observation"]["reason"], "capture_bytes_limit")
        frames = [packet(flags=2, client_port=40000 + i) for i in range(cloud.MAX_TCP_STREAMS + 1)]
        self.assertEqual(self.observe(*frames)["observation"]["reason"], "stream_limit")
        with patch.object(cloud, "MAX_STREAM_BYTES", 100):
            self.assertEqual(self.observe(packet(b"x" * 101))["observation"]["reason"], "stream_bytes_limit")
        with patch.object(cloud, "MAX_PACKETS", 1):
            self.assertEqual(self.observe(packet(), packet())["observation"]["reason"], "packet_limit")

    def test_invalid_capture_and_missing_file_never_raise(self):
        for content in [b"", b"bad", b"x" * 24, pcap(b"short")]:
            self.assertEqual(cloud.observe_uiflow_cloud_pcap(content)["state"], "unavailable")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.pcap"
            self.assertEqual(cloud.read_uiflow_cloud_status(path)["observation"]["reason"], "capture_unavailable")
            path.write_bytes(pcap())
            self.assertEqual(cloud.read_uiflow_cloud_status(path)["state"], "not_observed")


if __name__ == "__main__":
    unittest.main()
