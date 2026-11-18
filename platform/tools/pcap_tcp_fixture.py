"""Fold bounded fixed-peer TCP connections into payload-free capture evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
import struct


GATEWAY = "10.0.2.2"
POST_PORT = 18193
POST_AUTHORITY = "post.native-sta.test"
POST_PATH = "/native-sta-post"
TCP_PORT = 19193
MAX_BODY = 512
MAX_WIRE_BYTES = 4096
MAX_CONNECTIONS = 16
_SEQ_MASK = 0xFFFFFFFF
_PORT_KIND = {POST_PORT: "http_post", TCP_PORT: "tcp_length_prefixed"}
_SYN, _ACK, _FIN_OR_RST = 0x02, 0x10, 0x05


@dataclass
class _Direction:
    start: int | None = None
    seen: dict[int, int] = field(default_factory=dict)

    def open(self, sequence: int) -> bool:
        first = (sequence + 1) & _SEQ_MASK
        if self.start not in (None, first):
            return False
        self.start = first
        return True

    def observe(self, sequence: int, payload: bytes) -> bool:
        if self.start is None:
            return False
        offset = (sequence - self.start) & _SEQ_MASK
        if offset + len(payload) > MAX_WIRE_BYTES:
            return False
        for position, value in enumerate(payload, offset):
            if self.seen.setdefault(position, value) != value:
                return False
        return True

    def data(self) -> bytes | None:
        if not self.seen or max(self.seen) + 1 != len(self.seen):
            return None
        return bytes(self.seen[index] for index in range(len(self.seen)))


@dataclass
class _Connection:
    request: _Direction = field(default_factory=_Direction)
    reply: _Direction = field(default_factory=_Direction)
    established: bool = False
    invalid: bool = False

    def observe(self, *, incoming: bool, header: bytes, payload: bytes) -> None:
        if self.invalid:
            return
        sequence, acknowledgement = struct.unpack_from(">II", header, 4)
        flags = header[13]
        half = self.reply if incoming else self.request
        if flags & _SYN:
            if (self.established or payload or flags & _FIN_OR_RST or bool(flags & _ACK) != incoming
                    or (incoming and acknowledgement != self.request.start)
                    or not half.open(sequence)):
                self.invalid = True
            return
        if not incoming and flags & _ACK and self.reply.start is not None and acknowledgement == self.reply.start:
            self.established = True
        if payload and (not self.established or not flags & _ACK or not half.observe(sequence, payload)):
            self.invalid = True


def _digests(wire: bytes, body: bytes) -> dict:
    return {"wire_bytes": len(wire), "wire_sha256": sha256(wire).hexdigest(),
            "body_bytes": len(body), "body_sha256": sha256(body).hexdigest()}


def _http(wire: bytes, *, incoming: bool) -> dict | None:
    head, delimiter, body = wire.partition(b"\r\n\r\n")
    if not delimiter or not 1 <= len(body) <= MAX_BODY:
        return None
    lines = head.split(b"\r\n")
    fields = {}
    for header in lines[1:]:
        name, separator, value = header.partition(b":")
        if not separator or not re.fullmatch(rb"[A-Za-z0-9-]+", name):
            return None
        name = name.lower()
        if name in (b"host", b"content-length", b"transfer-encoding"):
            if name in fields:
                return None
            fields[name] = value.strip(b" \t")
    length = fields.get(b"content-length", b"")
    if b"transfer-encoding" in fields or not re.fullmatch(rb"[0-9]{1,3}", length) or int(length) != len(body):
        return None
    if incoming:
        status = re.fullmatch(rb"HTTP/1\.[01] ([1-5][0-9]{2})(?: [ -~]*)?", lines[0])
        return {**_digests(wire, body), "status_code": int(status[1])} if status else None
    expected = {b"POST /native-sta-post HTTP/1.0", b"POST /native-sta-post HTTP/1.1"}
    host = fields.get(b"host", b"").lower()
    if lines[0] not in expected or host not in (POST_AUTHORITY.encode(), f"{POST_AUTHORITY}:{POST_PORT}".encode()):
        return None
    return {**_digests(wire, body), "method": "POST", "authority": POST_AUTHORITY, "path": POST_PATH}


def _length_frame(wire: bytes) -> dict | None:
    body = wire[2:]
    if not 1 <= len(body) <= MAX_BODY or int.from_bytes(wire[:2], "big") != len(body):
        return None
    return _digests(wire, body)


class TcpFixtureStreams:
    """Track only opted-in TCP fixture ports on the controlled guest gateway."""

    def __init__(self, ports: set[int]):
        if not ports or not ports <= _PORT_KIND.keys():
            raise ValueError("expected controlled TCP fixture ports")
        self.ports = ports
        self.connections: dict[tuple[str, int, int], _Connection] = {}
        self.complete = True

    def observe(self, source: str, destination: str, header: bytes, payload: bytes, *, fragment: bool) -> None:
        src_port, dst_port = struct.unpack_from(">HH", header)
        if source == GATEWAY and src_port in self.ports:
            client_address, client_port, port, incoming = destination, dst_port, src_port, True
        elif destination == GATEWAY and dst_port in self.ports:
            client_address, client_port, port, incoming = source, src_port, dst_port, False
        else:
            return
        key = (client_address, client_port, port)
        if fragment or not client_port or (key not in self.connections and len(self.connections) == MAX_CONNECTIONS):
            self.complete = False
            return
        if key not in self.connections:
            self.connections[key] = _Connection()
        self.connections[key].observe(incoming=incoming, header=header, payload=payload)

    def evidence(self) -> dict:
        complete = self.complete
        streams = []
        for (address, client_port, port), connection in sorted(self.connections.items()):
            request = connection.request.data()
            reply = connection.reply.data()
            if connection.invalid or not connection.established or request is None or reply is None:
                complete = False
                continue
            if port == POST_PORT:
                request, reply = _http(request, incoming=False), _http(reply, incoming=True)
            else:
                request, reply = _length_frame(request), _length_frame(reply)
            if request is None or reply is None:
                complete = False
                continue
            streams.append({"kind": _PORT_KIND[port], "client": f"{address}:{client_port}",
                            "peer": f"{GATEWAY}:{port}", "request": request, "reply": reply})
        return {"tcp_fixture_streams_complete": complete, "tcp_fixture_streams": streams}
