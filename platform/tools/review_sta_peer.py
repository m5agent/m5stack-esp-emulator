"""Userspace station fixture peer for the `review-sta` profile (#238).

The peer is the far end of QEMU's ``-nic socket,fd=`` Ethernet stream. It
answers ARP, DHCP, DNS, HTTP, raw TCP, UDP and MQTT for the fixed gateway
10.0.2.2 and records structured events. It never opens an IP socket, so the
guest cannot reach the host, LAN or Internet through it. Frames addressed to
any other destination are counted as dropped egress attempts.
"""
from __future__ import annotations

import hashlib
import secrets
import socket
import struct
import threading
import time
from collections.abc import Callable

from network_fabric import LabDhcp, _internet_checksum, build_dhcp_ethernet_reply, parse_dhcp_request
from network_sandbox import ControlledDns
from device_service_softap_peer import SoftAPPeer, _PeerStopped
from review_sta_config import GATEWAY, LEASE

PEER_MAC = bytes.fromhex("02f100000001")
MAX_EVENTS = 512
MAX_STREAM_BYTES = 64 * 1024
TCP_WINDOW = 8192
_FIN, _SYN, _RST, _PSH, _ACK = 0x01, 0x02, 0x04, 0x08, 0x10


class _Stream:
    """One guest-initiated TCP connection to the fixture gateway."""

    def __init__(self, kind: str, client: tuple[bytes, int], port: int, client_seq: int):
        self.kind = kind
        self.client = client
        self.port = port
        self.remote_next = (client_seq + 1) & 0xFFFFFFFF
        self.local_seq = secrets.randbits(32)
        self.local_next = (self.local_seq + 1) & 0xFFFFFFFF
        self.inbound = bytearray()
        self.closed = False
        self.state: dict = {}


class ReviewStaPeer(SoftAPPeer):
    """Per-session peer. ``persist`` receives the full receipt on each change."""

    def __init__(self, station_mac: str, config: dict, persist: Callable[[dict], None]):
        super().__init__(station_mac, persist)
        self._config = config
        self._fixtures = config["fixtures"]
        self._events: list[dict] = []
        self._streams: dict[tuple, _Stream] = {}
        self._dhcp_server: LabDhcp | None = None
        self._leased = False
        self._started_at = 0.0
        self._fixture_log = hashlib.sha256()
        self._dropped = 0
        self._events_truncated = False

    @staticmethod
    def _initial_protocol_state() -> dict:
        return {"isolation": "userspace-fixture-only", "host_ip_backends": 0,
                "events": [], "events_truncated": False, "dropped_egress_frames": 0,
                "fixture_log_sha256": hashlib.sha256().hexdigest()}

    def start(self) -> None:
        self._events = []
        self._streams = {}
        self._leased = False
        self._dropped = 0
        self._events_truncated = False
        self._fixture_log = hashlib.sha256()
        self._started_at = time.monotonic()
        self._dhcp_server = LabDhcp({
            "interface": "unix", "server_address": str(GATEWAY),
            "reservations": {self.mac.hex(":"): str(LEASE)},
        })
        super().start()

    def invalidate_for_reset(self) -> None:
        self.pause()
        self._record(status="INTERRUPTED", stage="reset")

    def event(self, event_type: str, /, **fields) -> None:
        """Record one structured event. Also used by the session for wifi_auth/setup."""
        with self._lock:
            if len(self._events) >= MAX_EVENTS:
                self._events_truncated = True
            else:
                row = {"at": round(time.monotonic() - self._started_at, 3), **fields, "type": event_type}
                self._events.append(row)
                self._fixture_log.update(repr(sorted(row.items())).encode())
            snapshot = {"events": list(self._events), "events_truncated": self._events_truncated,
                        "dropped_egress_frames": self._dropped,
                        "fixture_log_sha256": self._fixture_log.hexdigest()}
        self._record(**snapshot)

    # ---- frame loop -------------------------------------------------------

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    frame = self._next_frame(time.monotonic() + 0.5)
                except TimeoutError:
                    continue
                for reply in self._dispatch(frame):
                    self._send(reply)
        except _PeerStopped:
            return
        except (EOFError, OSError, ValueError) as error:
            self._record(status="TRANSPORT_CLOSED", stage=type(error).__name__)

    def _dispatch(self, frame: bytes) -> list[bytes]:
        if frame[6:12] != self.mac or frame[:6] not in (PEER_MAC, b"\xff" * 6):
            return []
        ethertype = frame[12:14]
        if ethertype == b"\x08\x06":
            reply = self._arp(frame)
            return [reply] if reply else []
        if ethertype != b"\x08\x00" or len(frame) < 34:
            return []
        protocol = frame[23]
        destination = frame[30:34]
        if protocol == socket.IPPROTO_UDP:
            ip = self._ip_payload(frame, socket.IPPROTO_UDP)
            if ip is None or len(ip[2]) < 8:
                return []
            source, destination, udp = ip
            sport, dport, length = struct.unpack_from("!HHH", udp)
            if length != len(udp):
                return []
            if (sport, dport) == (68, 67):
                reply = self._dhcp(udp[8:])
                return [reply] if reply else []
            if not self._leased or source != LEASE.packed:
                return []
            if destination != GATEWAY.packed:
                return self._drop(destination, dport, "udp")
            payload = udp[8:]
            if dport == 53:
                response = self._dns(payload)
            elif "udp" in self._fixtures and dport == self._fixtures["udp"]["port"]:
                response = self._udp(payload)
            else:
                self.event("udp_unserved", dst=f"{GATEWAY}:{dport}", status="FAIL", code="fixture_rejected")
                return []
            return [self._udp_frame(dport, sport, response)] if response is not None else []
        if protocol == socket.IPPROTO_TCP:
            if not self._leased or frame[26:30] != LEASE.packed:
                return []
            if destination != GATEWAY.packed:
                port = struct.unpack_from("!H", frame, 14 + (frame[14] & 0xF) * 4 + 2)[0] if len(frame) > 40 else 0
                return self._drop(destination, port, "tcp")
            return self._tcp(frame)
        if destination != GATEWAY.packed and self._leased and frame[26:30] == LEASE.packed:
            return self._drop(destination, 0, f"ip{protocol}")
        return []

    def _drop(self, destination: bytes, port: int, transport: str) -> list[bytes]:
        if destination == b"\x00\x00\x00\x00":
            # An unresolved name leaves the unspecified address in the socket
            # (for example SNTP after NXDOMAIN). It names no host, so it is
            # recorded but is not an attempt to leave the fixture.
            self.event("unroutable_dropped", dst=f"0.0.0.0:{port}", transport=transport)
            return []
        self._dropped += 1
        if self._dropped <= 16:
            self.event("egress_denied", dst=f"{socket.inet_ntoa(destination)}:{port}",
                       transport=transport, status="FAIL", code="host_egress_denied")
        return []

    def _arp(self, frame: bytes) -> bytes | None:
        if (len(frame) >= 42 and frame[14:22] == bytes.fromhex("0001080006040001")
                and frame[22:28] == self.mac and frame[38:42] == GATEWAY.packed):
            return (self.mac + PEER_MAC + bytes.fromhex("08060001080006040002") + PEER_MAC
                    + GATEWAY.packed + self.mac + frame[28:32])
        return None

    def _dhcp(self, payload: bytes) -> bytes | None:
        parsed = parse_dhcp_request(payload)
        if parsed is None or parsed["mac"] != self.mac.hex(":") or parsed["message_type"] not in (1, 3):
            return None
        assert self._dhcp_server is not None
        reply = self._dhcp_server.handle(payload, source_mac=self.mac.hex(":"))
        if reply is None:
            self.event("dhcp_nak", status="FAIL", code="dhcp_rejected")
            return None
        if parsed["message_type"] == 1:
            self.event("dhcp_discover")
        else:
            if not self._leased:
                self.event("dhcp_lease", ipv4=str(LEASE), gateway=str(GATEWAY), status="PASS")
            self._leased = True
        return build_dhcp_ethernet_reply(reply, source_mac=self.mac, server_mac=PEER_MAC,
                                         server_address=str(GATEWAY))

    def _dns(self, request: bytes) -> bytes | None:
        question = ControlledDns.parse_question(request)
        if question is None:
            return None
        name, qtype, qclass, end = question
        name = name.lower().rstrip(".")
        answers = self._fixtures.get("dns", {}).get("A", {})
        known = qclass == 1 and name in answers
        if qtype == 1 and known:
            self.event("dns_query", name=name, qtype="A", answer=str(GATEWAY), status="PASS")
            return (request[:2] + struct.pack("!HHHHH", 0x8180, 1, 1, 0, 0) + request[12:end]
                    + bytes.fromhex("c00c000100010000003c0004") + GATEWAY.packed)
        if known:
            # Name exists but only A is served: NOERROR with no answers.
            self.event("dns_query", name=name, qtype=str(qtype), answer=None, status="PASS")
            return request[:2] + struct.pack("!HHHHH", 0x8180, 1, 0, 0, 0) + request[12:end]
        self.event("dns_query", name=name, qtype="A" if qtype == 1 else str(qtype),
                   answer=None, status="FAIL", code="dns_failed", rcode="NXDOMAIN")
        return request[:2] + struct.pack("!HHHHH", 0x8183, 1, 0, 0, 0) + request[12:end]

    def _udp(self, payload: bytes) -> bytes | None:
        fixture = self._fixtures["udp"]
        expected = bytes.fromhex(fixture["request_hex"])
        port = fixture["port"]
        if payload != expected:
            self.event("udp_exchange", dst=f"{GATEWAY}:{port}", status="FAIL", code="fixture_rejected",
                       request_sha256=hashlib.sha256(payload).hexdigest())
            return None
        self.event("udp_exchange", dst=f"{GATEWAY}:{port}", status="PASS")
        return bytes.fromhex(fixture["response_hex"])

    def _udp_frame(self, sport: int, dport: int, payload: bytes) -> bytes:
        udp = struct.pack("!HHHH", sport, dport, len(payload) + 8, 0) + payload
        return self.mac + PEER_MAC + b"\x08\x00" + self._ipv4(GATEWAY.packed, LEASE.packed,
                                                               socket.IPPROTO_UDP, udp)

    # ---- TCP ----------------------------------------------------------------

    def _tcp_kind(self, port: int) -> str | None:
        for kind in ("http", "tcp", "mqtt"):
            if kind in self._fixtures and self._fixtures[kind]["port"] == port:
                return kind
        return None

    def _segment(self, stream: _Stream, flags: int, payload: bytes = b"") -> bytes:
        client_ip, client_port = stream.client
        tcp = bytearray(struct.pack("!HHIIBBHHH", stream.port, client_port, stream.local_next,
                                    stream.remote_next, 0x50, flags, TCP_WINDOW, 0, 0) + payload)
        pseudo = GATEWAY.packed + client_ip + struct.pack("!BBH", 0, socket.IPPROTO_TCP, len(tcp))
        struct.pack_into("!H", tcp, 16, _internet_checksum(pseudo + bytes(tcp)))
        stream.local_next = (stream.local_next + len(payload) + (1 if flags & (_SYN | _FIN) else 0)) & 0xFFFFFFFF
        return self.mac + PEER_MAC + b"\x08\x00" + self._ipv4(GATEWAY.packed, client_ip,
                                                               socket.IPPROTO_TCP, bytes(tcp))

    def _rst(self, frame: bytes, tcp: bytes) -> bytes:
        sport, dport, seq, ack = struct.unpack_from("!HHII", tcp)
        flags = tcp[13]
        offset = (tcp[12] >> 4) * 4
        length = len(tcp) - offset + (1 if flags & _SYN else 0) + (1 if flags & _FIN else 0)
        seg = bytearray(struct.pack("!HHIIBBHHH", dport, sport, ack if flags & _ACK else 0,
                                    (seq + length) & 0xFFFFFFFF, 0x50, _RST | _ACK, 0, 0, 0))
        pseudo = GATEWAY.packed + frame[26:30] + struct.pack("!BBH", 0, socket.IPPROTO_TCP, len(seg))
        struct.pack_into("!H", seg, 16, _internet_checksum(pseudo + bytes(seg)))
        return self.mac + PEER_MAC + b"\x08\x00" + self._ipv4(GATEWAY.packed, frame[26:30],
                                                               socket.IPPROTO_TCP, bytes(seg))

    def _tcp(self, frame: bytes) -> list[bytes]:
        ip = self._ip_payload(frame, socket.IPPROTO_TCP)
        if ip is None or len(ip[2]) < 20:
            return []
        source, _, tcp = ip
        pseudo = source + GATEWAY.packed + struct.pack("!BBH", 0, socket.IPPROTO_TCP, len(tcp))
        offset = (tcp[12] >> 4) * 4
        if not 20 <= offset <= len(tcp) or _internet_checksum(pseudo + tcp):
            return []
        sport, dport, seq, _ack = struct.unpack_from("!HHII", tcp)
        flags = tcp[13]
        payload = tcp[offset:]
        key = (sport, dport)
        stream = self._streams.get(key)
        if flags & _RST:
            self._streams.pop(key, None)
            return []
        if flags & _SYN and not flags & _ACK:
            kind = self._tcp_kind(dport)
            if kind is None:
                self.event("tcp_connect", dst=f"{GATEWAY}:{dport}", status="FAIL", code="tcp_refused")
                return [self._rst(frame, tcp)]
            if stream is None or stream.remote_next != (seq + 1) & 0xFFFFFFFF:
                stream = _Stream(kind, (source, sport), dport, seq)
                self._streams[key] = stream
                self.event("tcp_connect", dst=f"{GATEWAY}:{dport}", service=kind, status="PASS")
            stream.local_next = stream.local_seq
            return [self._segment(stream, _SYN | _ACK)]
        if stream is None:
            return [] if flags & _FIN and not payload else [self._rst(frame, tcp)]
        replies: list[bytes] = []
        if payload:
            if seq != stream.remote_next:
                # Out-of-order or retransmission: re-acknowledge what we have.
                return [self._segment(stream, _ACK)]
            stream.remote_next = (stream.remote_next + len(payload)) & 0xFFFFFFFF
            if len(stream.inbound) + len(payload) > MAX_STREAM_BYTES:
                self.event(f"{stream.kind}_overflow", dst=f"{GATEWAY}:{dport}", status="FAIL",
                           code="fixture_rejected")
                self._streams.pop(key, None)
                return [self._rst(frame, tcp)]
            stream.inbound.extend(payload)
            output, close = getattr(self, f"_serve_{stream.kind}")(stream)
            replies.append(self._segment(stream, _ACK | (_PSH if output else 0), output))
            if close and not stream.closed:
                stream.closed = True
                replies.append(self._segment(stream, _FIN | _ACK))
        if flags & _FIN:
            stream.remote_next = (stream.remote_next + 1) & 0xFFFFFFFF
            if not stream.closed:
                stream.closed = True
                replies.append(self._segment(stream, _FIN | _ACK))
            else:
                replies.append(self._segment(stream, _ACK))
            self._streams.pop(key, None)
        return replies

    def _serve_tcp(self, stream: _Stream) -> tuple[bytes, bool]:
        fixture = self._fixtures["tcp"]
        expected = bytes.fromhex(fixture["request_hex"])
        if len(stream.inbound) < len(expected) and expected.startswith(bytes(stream.inbound)):
            return b"", False
        matched = bytes(stream.inbound[:len(expected)]) == expected
        self.event("tcp_exchange", dst=f"{GATEWAY}:{stream.port}",
                   status="PASS" if matched else "FAIL", **({} if matched else {"code": "fixture_rejected"}))
        stream.inbound.clear()
        return (bytes.fromhex(fixture["response_hex"]) if matched else b""), not matched

    def _serve_http(self, stream: _Stream) -> tuple[bytes, bool]:
        data = bytes(stream.inbound)
        head, separator, body = data.partition(b"\r\n\r\n")
        if not separator:
            if len(head) > 8192:
                self.event("http_request", status="FAIL", code="fixture_rejected", reason="header_too_large")
                return b"HTTP/1.1 431 Request Header Fields Too Large\r\nContent-Length: 0\r\n\r\n", True
            return b"", False
        lines = head.split(b"\r\n")
        parts = lines[0].split(b" ")
        if len(parts) != 3 or not parts[2].startswith(b"HTTP/1."):
            self.event("http_request", status="FAIL", code="fixture_rejected", reason="malformed")
            return b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n", True
        headers = {}
        for line in lines[1:]:
            name, colon, value = line.partition(b":")
            if colon:
                headers[name.strip().lower()] = value.strip()
        length = headers.get(b"content-length", b"0")
        if not length.isdigit() or int(length) > MAX_STREAM_BYTES:
            self.event("http_request", status="FAIL", code="fixture_rejected", reason="bad_length")
            return b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n", True
        if len(body) < int(length):
            return b"", False
        stream.inbound = bytearray(body[int(length):])
        method = parts[0].decode("ascii", "replace")
        path = parts[1].decode("ascii", "replace").split("?", 1)[0]
        host = headers.get(b"host", b"").decode("ascii", "replace")
        route = next((r for r in self._fixtures["http"]["routes"]
                      if r["method"] == method and r["path"] == path), None)
        status = route["status"] if route else 404
        content = route["body"].encode() if route else b"not a review fixture route\n"
        content_type = route["content_type"] if route else "text/plain"
        ok = route is not None and status < 400
        self.event("http_request", method=method, path=path, host=host, status=status,
                   request_body_bytes=int(length),
                   request_body_sha256=hashlib.sha256(body[:int(length)]).hexdigest(),
                   result="PASS" if ok else "FAIL",
                   **({} if ok else {"code": "http_status"}))
        keep_alive = headers.get(b"connection", b"").lower() != b"close" and parts[2] == b"HTTP/1.1"
        reason = {200: "OK", 201: "Created", 204: "No Content", 404: "Not Found"}.get(status, "Status")
        response = (f"HTTP/1.1 {status} {reason}\r\nContent-Type: {content_type}\r\n"
                    f"Content-Length: {len(content) if method != 'HEAD' else 0}\r\n"
                    f"Connection: {'keep-alive' if keep_alive else 'close'}\r\n\r\n").encode()
        return response + (content if method != "HEAD" else b""), not keep_alive

    def _serve_mqtt(self, stream: _Stream) -> tuple[bytes, bool]:
        output = bytearray()
        while True:
            packet = _mqtt_packet(stream.inbound)
            if packet is None:
                return bytes(output), False
            kind, flags, body, size = packet
            del stream.inbound[:size]
            if kind == 1:
                protocol_len = struct.unpack_from("!H", body)[0] if len(body) >= 2 else 0
                name = body[2:2 + protocol_len]
                level = body[2 + protocol_len] if len(body) > 2 + protocol_len else 0
                client = b""
                cursor = 2 + protocol_len + 4
                if len(body) >= cursor + 2:
                    size_id = struct.unpack_from("!H", body, cursor)[0]
                    client = body[cursor + 2:cursor + 2 + size_id]
                accepted = name == b"MQTT" and level == 4
                self.event("mqtt_connect", client_id=client.decode("utf-8", "replace")[:64],
                           status="PASS" if accepted else "FAIL",
                           **({} if accepted else {"code": "fixture_rejected", "protocol_level": level}))
                output += bytes([0x20, 2, 0, 0 if accepted else 1])
                if not accepted:
                    return bytes(output), True
                stream.state["connected"] = True
            elif not stream.state.get("connected"):
                self.event("mqtt_protocol", status="FAIL", code="fixture_rejected", packet_type=kind)
                return bytes(output), True
            elif kind == 3:
                topic_len = struct.unpack_from("!H", body)[0] if len(body) >= 2 else 0
                topic = body[2:2 + topic_len].decode("utf-8", "replace")
                qos = (flags >> 1) & 3
                cursor = 2 + topic_len + (2 if qos else 0)
                allowed = any(_topic_matches(f, topic) for f in self._fixtures["mqtt"]["topics"])
                self.event("mqtt_publish", topic=topic, qos=qos, payload_bytes=len(body) - cursor,
                           payload_sha256=hashlib.sha256(body[cursor:]).hexdigest(),
                           status="PASS" if allowed else "FAIL",
                           **({} if allowed else {"code": "fixture_rejected"}))
                if qos == 1:
                    output += b"\x40\x02" + body[2 + topic_len:4 + topic_len]
            elif kind == 8:
                packet_id = body[:2]
                filters, cursor = [], 2
                while cursor + 2 <= len(body):
                    size_f = struct.unpack_from("!H", body, cursor)[0]
                    filters.append(body[cursor + 2:cursor + 2 + size_f].decode("utf-8", "replace"))
                    cursor += 3 + size_f
                self.event("mqtt_subscribe", topics=filters[:8], status="PASS")
                output += bytes([0x90, 2 + len(filters)]) + packet_id + b"\x00" * len(filters)
            elif kind == 12:
                output += b"\xd0\x00"
            elif kind == 14:
                self.event("mqtt_disconnect", status="PASS")
                return bytes(output), True


def _mqtt_packet(buffer: bytearray) -> tuple[int, int, bytes, int] | None:
    if len(buffer) < 2:
        return None
    multiplier, length, cursor = 1, 0, 1
    while True:
        if cursor >= len(buffer) or cursor > 4:
            return None
        byte = buffer[cursor]
        length += (byte & 0x7F) * multiplier
        multiplier *= 128
        cursor += 1
        if not byte & 0x80:
            break
    if len(buffer) < cursor + length:
        return None
    return buffer[0] >> 4, buffer[0] & 0xF, bytes(buffer[cursor:cursor + length]), cursor + length


def _topic_matches(pattern: str, topic: str) -> bool:
    pattern_parts, topic_parts = pattern.split("/"), topic.split("/")
    for index, part in enumerate(pattern_parts):
        if part == "#":
            return True
        if index >= len(topic_parts) or (part != "+" and part != topic_parts[index]):
            return False
    return len(pattern_parts) == len(topic_parts)
