"""Bounded, read-only UIFlow cloud observations from guest Ethernet PCAP bytes.

This reports captured protocol evidence, never account binding or remote REPL
execution. No address, identity, credential, topic or arbitrary peer text leaves
this module. A failed observation must not fail the Device Service session.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import struct
from urllib.parse import parse_qs, urlsplit

MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_TCP_STREAMS = 64  # Directional streams, across connection generations.
MAX_STREAM_BYTES = 64 * 1024
MAX_PACKETS = 65536
MAX_HTTP_BYTES = 8192
_MAGIC = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",
          b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">"}
_ERRORS = {"mac has not been bound to a deviceId": "mac_not_bound",
           "mac does not exist": "mac_not_found"}


class _Unavailable(Exception):
    """Only constant, implementation-owned reason enums may be supplied."""


@dataclass
class _Stream:
    segments: list[tuple[int, bytes, int]] = field(default_factory=list)
    size: int = 0
    expected_start: int | None = None
    expected_end: int | None = None

    def append(self, seq: int, data: bytes, order: int) -> None:
        # Bound retained retransmissions as well as the reassembled byte range.
        self.size += len(data)
        if self.size > MAX_STREAM_BYTES:
            raise _Unavailable("stream_bytes_limit")
        self.segments.append((seq, data, order))

    def assemble(self) -> tuple[bytes, list[int]]:
        if not self.segments:
            if self.expected_start is not None and self.expected_end is not None and self.expected_start != self.expected_end:
                raise _Unavailable("stream_gap")
            return b"", []
        base = min(seq for seq, _, _ in self.segments)
        end = max(seq + len(data) for seq, data, _ in self.segments)
        if ((self.expected_start is not None and base != self.expected_start)
                or (self.expected_end is not None and end != self.expected_end)):
            raise _Unavailable("stream_gap")
        if end - base > MAX_STREAM_BYTES:
            raise _Unavailable("stream_bytes_limit")
        result = bytearray(end - base)
        seen = bytearray(end - base)
        orders = [0] * (end - base)
        for seq, data, order in self.segments:
            offset = seq - base
            for index, value in enumerate(data, offset):
                if seen[index] and result[index] != value:
                    raise _Unavailable("stream_conflict")
                if not seen[index]:
                    result[index], seen[index], orders[index] = value, 1, order
        if 0 in seen:
            raise _Unavailable("stream_gap")
        # A parsed unit is complete only after all its preceding bytes arrived.
        latest = 0
        for index, order in enumerate(orders):
            latest = max(latest, order)
            orders[index] = latest
        return bytes(result), orders


@dataclass
class _Connection:
    port: int
    order: int
    syn: int | None = None
    client: _Stream = field(default_factory=_Stream)
    server: _Stream = field(default_factory=_Stream)
    closed: bool = False
    close_order: int | None = None


def _blank(size: int = 0) -> dict:
    return {
        "source": "guest-pcap", "state": "not_observed",
        "pairing": {"state": "not_observed"},
        "webrepl": {"state": "not_observed", "reason": None,
                    "handshakes": 0, "disconnects": 0, "device_registered": False,
                    "heartbeat_roundtrips": 0, "protocol_ping_sent": 0,
                    "protocol_pong_received": 0, "protocol_ping_without_pong_count": 0},
        "observation": {"status": "complete", "reason": None,
                        "capture_bytes": size, "packets": 0, "tcp_streams": 0,
                        "partial_tail": False, "partial_stream": False,
                        "protocol_unknown": False, "unsupported_packets": 0},
    }


def _partial(observation: dict, reason: str) -> None:
    observation["status"] = "partial"
    if observation["reason"] is None:
        observation["reason"] = reason


def _packet(frame: bytes, observation: dict):
    if len(frame) < 14:
        raise _Unavailable("malformed_packet")
    kind = struct.unpack_from("!H", frame, 12)[0]
    offset = 14
    while kind in (0x8100, 0x88A8, 0x9100):
        if len(frame) < offset + 4:
            raise _Unavailable("malformed_packet")
        kind = struct.unpack_from("!H", frame, offset + 2)[0]
        offset += 4
    if kind != 0x0800:
        if kind == 0x86DD:
            observation["unsupported_packets"] += 1
        return None
    ip = frame[offset:]
    if len(ip) < 20 or ip[0] >> 4 != 4:
        raise _Unavailable("malformed_packet")
    header = (ip[0] & 15) * 4
    total = struct.unpack_from("!H", ip, 2)[0]
    if header < 20 or total < header or len(ip) < total:
        raise _Unavailable("malformed_packet")
    if ip[9] != 6:
        return None
    if struct.unpack_from("!H", ip, 6)[0] & 0x3FFF:
        raise _Unavailable("fragmented_ip")
    ip = ip[:total]
    if len(ip) < header + 20:
        raise _Unavailable("malformed_packet")
    tcp = ip[header:]
    tcp_header = (tcp[12] >> 4) * 4
    if tcp_header < 20 or len(tcp) < tcp_header:
        raise _Unavailable("malformed_packet")
    source_port, target_port, seq = struct.unpack_from("!HHI", tcp)
    return (ip[12:16], ip[16:20], source_port, target_port,
            seq, tcp[13], tcp[tcp_header:])


def _connections(data: bytes, observation: dict) -> list[_Connection]:
    if len(data) < 24:
        raise _Unavailable("malformed_pcap")
    endian = _MAGIC.get(data[:4])
    if endian is None or struct.unpack_from(endian + "HH", data, 4) != (2, 4):
        raise _Unavailable("unsupported_pcap")
    if struct.unpack_from(endian + "I", data, 20)[0] != 1:
        raise _Unavailable("unsupported_pcap")
    active, connections = {}, []
    directions = set()
    offset = 24
    while offset < len(data):
        if len(data) - offset < 16:
            observation["partial_tail"] = True
            _partial(observation, "capture_partial_tail")
            break
        _, _, size, original = struct.unpack_from(endian + "IIII", data, offset)
        offset += 16
        if size > MAX_CAPTURE_BYTES or original < size:
            raise _Unavailable("malformed_pcap")
        if size > len(data) - offset:
            observation["partial_tail"] = True
            _partial(observation, "capture_partial_tail")
            break
        frame = data[offset:offset + size]
        offset += size
        observation["packets"] += 1
        if observation["packets"] > MAX_PACKETS:
            raise _Unavailable("packet_limit")
        packet = _packet(frame, observation)
        if packet is None:
            continue
        source, target, source_port, target_port, seq, flags, payload = packet
        if target_port in (80, 1883):
            key, client, port = (source, target, source_port, target_port), True, target_port
        elif source_port in (80, 1883):
            key, client, port = (target, source, target_port, source_port), False, source_port
        else:
            continue
        order = observation["packets"]
        connection = active.get(key)
        new_syn = client and flags & 2 and not flags & 16
        if connection is None or (new_syn and connection.syn is not None and connection.syn != seq):
            connection = _Connection(port, order)
            connections.append(connection)
            active[key] = connection
        if new_syn:
            connection.syn = seq
        direction_key = (id(connection), client)
        directions.add(direction_key)
        observation["tcp_streams"] = len(directions)
        if len(directions) > MAX_TCP_STREAMS:
            raise _Unavailable("stream_limit")
        stream = connection.client if client else connection.server
        if flags & 2:
            stream.expected_start = (seq + 1) & 0xFFFFFFFF
        if flags & 1:
            stream.expected_end = (seq + bool(flags & 2) + len(payload)) & 0xFFFFFFFF
        if payload:
            stream.append((seq + bool(flags & 2)) & 0xFFFFFFFF, payload, order)
        if flags & 5:
            connection.closed = True
            if connection.close_order is None:
                connection.close_order = order
    return connections


def _http(data: bytes):
    end = data.find(b"\r\n\r\n")
    if end < 0:
        if len(data) > MAX_HTTP_BYTES:
            raise _Unavailable("http_bytes_limit")
        return None
    if end + 4 > MAX_HTTP_BYTES:
        raise _Unavailable("http_bytes_limit")
    lines = data[:end].split(b"\r\n")
    headers = {}
    for line in lines[1:]:
        if b":" not in line:
            raise _Unavailable("malformed_http")
        key, value = line.split(b":", 1)
        if not re.fullmatch(rb"[A-Za-z0-9-]+", key) or key.lower() in headers:
            raise _Unavailable("malformed_http")
        headers[key.lower()] = value.strip()
    return lines[0], headers, end + 4


def _upgrade(headers: dict) -> bool:
    return (headers.get(b"upgrade", b"").lower() == b"websocket"
            and b"upgrade" in [v.strip().lower() for v in headers.get(b"connection", b"").split(b",")])


def _ws_messages(data: bytes, orders: list[int], masked: bool, observation: dict):
    offset, fragmented, message, messages = 0, None, bytearray(), []
    while offset < len(data):
        start = offset
        if len(data) - offset < 2:
            break
        first, second = data[offset:offset + 2]
        offset += 2
        opcode, final, size = first & 15, bool(first & 128), second & 127
        if first & 0x70 or opcode not in (0, 1, 2, 8, 9, 10) or bool(second & 128) != masked:
            raise _Unavailable("malformed_websocket")
        width = 2 if size == 126 else 8 if size == 127 else 0
        if width:
            if len(data) - offset < width:
                offset = start
                break
            size = int.from_bytes(data[offset:offset + width], "big")
            offset += width
            if size < (126 if width == 2 else 65536):
                raise _Unavailable("malformed_websocket")
        if size > MAX_STREAM_BYTES:
            raise _Unavailable("message_bytes_limit")
        if opcode >= 8 and (not final or size > 125):
            raise _Unavailable("malformed_websocket")
        if len(data) - offset < size + (4 if masked else 0):
            offset = start
            break
        mask = data[offset:offset + 4] if masked else None
        offset += 4 if masked else 0
        payload = data[offset:offset + size]
        offset += size
        if mask is not None:
            payload = bytes(value ^ mask[i % 4] for i, value in enumerate(payload))
        order = orders[offset - 1]
        if opcode >= 8:
            if opcode == 8 and size == 1:
                raise _Unavailable("malformed_websocket")
            messages.append((opcode, payload, order))
            continue
        if opcode == 0:
            if fragmented is None:
                raise _Unavailable("malformed_websocket")
            message.extend(payload)
        else:
            if fragmented is not None:
                raise _Unavailable("malformed_websocket")
            fragmented, message = opcode, bytearray(payload)
        if len(message) > MAX_STREAM_BYTES:
            raise _Unavailable("message_bytes_limit")
        if final:
            if fragmented == 1:
                try:
                    bytes(message).decode("utf-8")
                except UnicodeDecodeError:
                    raise _Unavailable("malformed_websocket") from None
            messages.append((fragmented, bytes(message), order))
            fragmented, message = None, bytearray()
    if offset < len(data) or fragmented is not None:
        observation["partial_stream"] = True
        _partial(observation, "protocol_partial")
    return messages


def _websocket(connection: _Connection, observation: dict):
    client, client_orders = connection.client.assemble()
    server, server_orders = connection.server.assemble()
    if not client.startswith(b"GET /ws/realtime?"):
        return None
    request = _http(client)
    if request is None:
        observation["partial_stream"] = True
        _partial(observation, "protocol_partial")
        return None
    start, headers, request_end = request
    try:
        method, raw_url, version = start.decode("ascii").split(" ")
        url = urlsplit(raw_url)
        query = parse_qs(url.query, keep_blank_values=True, max_num_fields=32)
    except ValueError:
        raise _Unavailable("malformed_http") from None
    if (method != "GET" or version != "HTTP/1.1" or url.scheme or url.netloc or url.fragment
            or url.path != "/ws/realtime" or query.get("role") != ["device"]
            or headers.get(b"host", b"").lower() not in (b"uiflow2.m5stack.com", b"uiflow2.m5stack.com:80")
            or not _upgrade(headers) or headers.get(b"sec-websocket-version") != b"13"):
        return None
    try:
        key = headers.get(b"sec-websocket-key", b"")
        if len(base64.b64decode(key, validate=True)) != 16:
            return None
    except ValueError:
        return None
    response = _http(server)
    if response is None:
        observation["partial_stream"] = True
        _partial(observation, "protocol_partial")
        return None
    status, reply, response_end = response
    if not re.fullmatch(rb"HTTP/1\.1 101(?: [^\r\n]*)?", status) or not _upgrade(reply):
        return None
    accept = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
    if reply.get(b"sec-websocket-accept") != accept:
        return None
    if reply.get(b"sec-websocket-extensions"):
        raise _Unavailable("unsupported_websocket")
    outgoing = _ws_messages(client[request_end:], client_orders[request_end:], True, observation)
    incoming = _ws_messages(server[response_end:], server_orders[response_end:], False, observation)
    reason, heartbeat, closed, registered = None, False, connection.closed, False
    mac = query.get("mac", [])
    query_mac = mac[0].lower() if len(mac) == 1 and re.fullmatch("[0-9a-fA-F]{12}", mac[0]) else None
    for opcode, payload, _ in incoming:
        if opcode != 1 or payload in (b"PING", b"PONG"):
            continue
        try:
            message = json.loads(payload)
        except (ValueError, RecursionError):
            observation["protocol_unknown"] = True
            _partial(observation, "unrecognized_message")
            continue
        if not isinstance(message, dict) or message.get("type") not in ("deviceConnected", "clientMessage", "error"):
            observation["protocol_unknown"] = True
            _partial(observation, "unrecognized_message")
        if (isinstance(message, dict) and message.get("type") == "deviceConnected"
                and query_mac is not None and message.get("mac") == query_mac
                and isinstance(message.get("deviceId"), str) and message["deviceId"]):
            registered = True
        if isinstance(message, dict) and message.get("type") == "error":
            value = message.get("payload")
            reason = _ERRORS.get(value, "server_error") if isinstance(value, str) else "server_error"
    pending: dict[tuple[bool, int, bytes], list[int]] = {}
    roundtrips = 0
    events = [(order, True, opcode, payload) for opcode, payload, order in outgoing]
    events += [(order, False, opcode, payload) for opcode, payload, order in incoming]
    close_orders = [order for order, _, opcode, _ in events if opcode == 8]
    if connection.close_order is not None:
        close_orders.append(connection.close_order)
    close_order = min(close_orders) if close_orders else None
    ping_sent = pong_received = 0
    for order, direction, opcode, payload in sorted(events, key=lambda event: event[0]):
        if close_order is not None and order >= close_order:
            continue
        ping_sent += int(direction and opcode == 9)
        pong_received += int(not direction and opcode == 10)
        if opcode == 9 or (opcode == 1 and payload == b"PING"):
            key = (direction, opcode, payload if opcode == 9 else b"")
            pending.setdefault(key, []).append(order)
        elif opcode == 10 or (opcode == 1 and payload == b"PONG"):
            key = (not direction, 9 if opcode == 10 else 1,
                   payload if opcode == 10 else b"")
            waiting = pending.get(key, [])
            if waiting:
                waiting.pop(0)
                roundtrips += 1
    heartbeat = roundtrips > 0
    closed |= any(opcode == 8 for opcode, _, _ in outgoing + incoming)
    state = ("identity_rejected" if reason in ("mac_not_bound", "mac_not_found") else
             "server_error" if reason else "disconnected" if closed else
             "heartbeat_observed" if heartbeat else "handshake_observed")
    return {"state": state, "reason": reason, "closed": closed, "device_registered": registered,
            "heartbeat_roundtrips": roundtrips, "protocol_ping_sent": ping_sent,
            "protocol_pong_received": pong_received,
            "protocol_ping_without_pong_count": sum(len(waiting) for (direction, opcode, _), waiting in pending.items()
                                                   if direction and opcode == 9)}


def _mqtt_packets(data: bytes, observation: dict):
    offset = 0
    while offset < len(data):
        header = data[offset]
        offset += 1
        size, scale, complete = 0, 1, False
        for _ in range(4):
            if offset == len(data):
                break
            digit = data[offset]
            offset += 1
            size += (digit & 127) * scale
            scale *= 128
            if not digit & 128:
                complete = True
                break
        if not complete:
            if scale == 128 ** 4:
                raise _Unavailable("malformed_mqtt")
            observation["partial_stream"] = True
            _partial(observation, "protocol_partial")
            return
        if size > MAX_STREAM_BYTES:
            raise _Unavailable("message_bytes_limit")
        if offset + size > len(data):
            observation["partial_stream"] = True
            _partial(observation, "protocol_partial")
            return
        yield header >> 4, header & 15, data[offset:offset + size]
        offset += size


def _mqtt_string(body: bytes, offset: int):
    if offset + 2 > len(body):
        raise _Unavailable("malformed_mqtt")
    size = int.from_bytes(body[offset:offset + 2], "big")
    offset += 2
    if offset + size > len(body):
        raise _Unavailable("malformed_mqtt")
    try:
        value = body[offset:offset + size].decode("utf-8")
    except UnicodeDecodeError:
        raise _Unavailable("malformed_mqtt") from None
    return value, offset + size


def _pairing(connection: _Connection, observation: dict) -> bool:
    client, _ = connection.client.assemble()
    server, _ = connection.server.assemble()
    topics, connected = set(), False
    for kind, flags, body in _mqtt_packets(client, observation):
        if kind == 1:
            name, at = _mqtt_string(body, 0)
            if name != "MQTT" or len(body) < at + 4 or body[at] != 4 or flags:
                continue
            if body[at + 1] & 1:
                raise _Unavailable("malformed_mqtt")
            _mqtt_string(body, at + 4)
            connected = True
        elif kind == 8:
            if flags != 2 or len(body) < 2:
                raise _Unavailable("malformed_mqtt")
            at = 2
            while at < len(body):
                topic, at = _mqtt_string(body, at)
                if at == len(body) or body[at] > 2:
                    raise _Unavailable("malformed_mqtt")
                at += 1
                topics.add(topic)
    accepted, received = False, False
    for kind, flags, body in _mqtt_packets(server, observation):
        if kind == 2:
            accepted = len(body) == 2 and body[1] == 0 and flags == 0
        elif kind == 3:
            topic, at = _mqtt_string(body, 0)
            qos = (flags >> 1) & 3
            if qos == 3 or (qos and at + 2 > len(body)):
                raise _Unavailable("malformed_mqtt")
            at += 2 if qos else 0
            parts = topic.split("/")
            if (not connected or not accepted or topic not in topics or len(parts) != 6
                    or parts[:4] != ["$m5", "uiflow", "v2", "down"]
                    or not parts[4] or parts[5] != "syscmd"):
                continue
            try:
                message = json.loads(body[at:])
            except (ValueError, RecursionError):
                observation["protocol_unknown"] = True
                _partial(observation, "unrecognized_message")
                continue
            if isinstance(message, dict) and isinstance(message.get("data"), dict):
                code = message["data"].get("code")
                received |= isinstance(code, str) and bool(code)
    return received


def observe_uiflow_cloud_pcap(data: bytes) -> dict:
    """Return only bounded enum/count/boolean evidence; never raise on peer data."""
    result = _blank(len(data))
    observation = result["observation"]
    try:
        if len(data) > MAX_CAPTURE_BYTES:
            raise _Unavailable("capture_bytes_limit")
        connections = _connections(data, observation)
        for connection in connections:
            if connection.port == 1883:
                if _pairing(connection, observation):
                    result["pairing"]["state"] = "code_received"
            else:
                websocket = _websocket(connection, observation)
                if websocket is not None:
                    result["webrepl"].update(state=websocket["state"], reason=websocket["reason"],
                                              device_registered=websocket["device_registered"],
                                              heartbeat_roundtrips=websocket["heartbeat_roundtrips"],
                                              protocol_ping_sent=websocket["protocol_ping_sent"],
                                              protocol_pong_received=websocket["protocol_pong_received"],
                                              protocol_ping_without_pong_count=websocket["protocol_ping_without_pong_count"])
                    result["webrepl"]["handshakes"] += 1
                    result["webrepl"]["disconnects"] += int(websocket["closed"])
        if result["pairing"]["state"] == "code_received" or result["webrepl"]["handshakes"]:
            result["state"] = "observed"
    except (_Unavailable, ValueError, IndexError, struct.error, RecursionError) as error:
        reason = str(error) if isinstance(error, _Unavailable) else "malformed_protocol"
        safe = _blank(len(data))
        safe["state"] = "unavailable"
        safe["observation"].update(observation)
        safe["observation"].update(status="unavailable", reason=reason)
        return safe
    return result


def read_uiflow_cloud_status(path: str | Path) -> dict:
    """Read at most the capture limit plus one byte, including a live PCAP tail."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_CAPTURE_BYTES + 1)
    except OSError:
        result = _blank()
        result["state"] = "unavailable"
        result["observation"].update(status="unavailable", reason="capture_unavailable")
        return result
    return observe_uiflow_cloud_pcap(data)
