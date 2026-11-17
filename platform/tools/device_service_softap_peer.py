"""One fixed open SoftAP fixture using QEMU's local Ethernet stream."""

from __future__ import annotations

import hashlib
import secrets
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from device_service_errors import ServiceError
from network_fabric import DHCP_MAGIC, _dhcp_options, _internet_checksum

PROFILE = "cardputer-open-softap-fixture"
STICKS3_PROFILE = "sticks3-open-softap-fixture"
PROFILE_BOARDS = {
    PROFILE: frozenset({"cardputer", "cardputer-adv"}),
    STICKS3_PROFILE: frozenset({"sticks3"}),
}
ACL_OPERATION = "network.softap.probe"
QOM_PROPERTY = "open-softap-peer"
NIC = "misc.esp32s3.wifi"
HTTP_REQUEST = b"GET /proof HTTP/1.0\r\n\r\n"
HTTP_BODY = b"AP_FIXTURE_OK"
HTTP_RESPONSE = b"HTTP/1.0 200 OK\r\nContent-Length: 13\r\n\r\n" + HTTP_BODY
_BROADCAST = b"\xff" * 6
_ZERO_IP = b"\0" * 4
_BROADCAST_IP = b"\xff" * 4
_MAX_ETHERNET = 1514


def require_softap_backend(qemu: Path) -> None:
    try:
        result = subprocess.run(
            [str(qemu), "-device", f"{NIC},help"],
            check=True, capture_output=True, text=True, timeout=3,
        )
        if any(line.strip().startswith(f"{QOM_PROPERTY}=<bool>")
               for line in result.stdout.splitlines()):
            return
    except (OSError, subprocess.SubprocessError):
        pass
    raise ServiceError(
        "softap_fixture_backend_unavailable",
        "native QEMU lacks the open SoftAP peer capability",
        503,
    )


class _PeerStopped(Exception):
    pass


class SoftAPPeer:
    """Per-lease peer. Neither endpoint can dial or listen on an IP socket."""

    def __init__(self, mac: str, persist: Callable[[dict], None]):
        self.mac = bytes.fromhex(mac.replace(":", ""))
        if len(self.mac) != 6 or self.mac[0] & 3 != 2:
            raise ValueError("SoftAP peer requires a locally administered unicast address")
        self._peer, self.child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self._peer.settimeout(0.15)
        self._persist = persist
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._input = bytearray()
        self._generation = 0
        self._closed = False
        self._receipt = {}

    def _record(self, **fields) -> None:
        with self._lock:
            self._receipt = {**self._receipt, **fields}
            self._persist(dict(self._receipt))

    def start(self) -> None:
        if self._closed or self._thread is not None:
            raise RuntimeError("SoftAP peer cannot start in its current state")
        self._stop.clear()
        self._generation += 1
        with self._lock:
            self._receipt = {}
        self._record(
            schema_version=1, transport="unix-socketpair", generation=self._generation,
            status="RUNNING", released=False, dhcp=False, arp=False, http=False,
        )
        self._thread = threading.Thread(target=self._run, name="softap-fixture-peer", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                raise RuntimeError("SoftAP peer did not stop")
            self._thread = None

    def invalidate_for_reset(self) -> None:
        self.pause()
        self._record(
            status="INTERRUPTED", stage="reset", dhcp=False, arp=False, http=False,
            http_body_sha256=None, http_request_sha256=None,
        )

    def close(self) -> None:
        if self._closed:
            return
        self.pause()
        self._peer.close()
        self.child.close()
        if self._receipt:
            self._record(released=True)
        self._closed = True

    def _send(self, data: bytes) -> None:
        if self._stop.is_set():
            raise _PeerStopped
        self._peer.sendall(struct.pack("!I", len(data)) + data)

    def _next_frame(self, deadline: float) -> bytes:
        while time.monotonic() < deadline:
            if self._stop.is_set():
                raise _PeerStopped
            if len(self._input) >= 4:
                length = int.from_bytes(self._input[:4], "big")
                if not 14 <= length <= _MAX_ETHERNET + 4:
                    raise ValueError("invalid Ethernet frame length")
                if len(self._input) >= length + 4:
                    frame = bytes(self._input[4 : length + 4])
                    del self._input[: length + 4]
                    return frame
            try:
                data = self._peer.recv(2048)
            except TimeoutError:
                continue
            if not data:
                raise EOFError("QEMU peer disconnected")
            self._input.extend(data)
        raise TimeoutError

    @staticmethod
    def _ipv4(source: bytes, target: bytes, protocol: int, payload: bytes) -> bytes:
        header = bytearray(struct.pack(
            "!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), 0, 0, 64, protocol, 0, source, target
        ))
        struct.pack_into("!H", header, 10, _internet_checksum(header))
        return bytes(header) + payload

    @staticmethod
    def _ip_payload(frame: bytes, protocol: int) -> tuple[bytes, bytes, bytes] | None:
        if len(frame) < 34 or frame[12:14] != b"\x08\0" or frame[14] != 0x45:
            return None
        size, fragments = struct.unpack_from("!H2xH", frame, 16)
        if (
            size < 20 or size + 14 > len(frame) or fragments & 0x3fff
            or frame[23] != protocol or _internet_checksum(frame[14:34])
        ):
            return None
        return frame[26:30], frame[30:34], frame[34 : 14 + size]

    def _dhcp_request(self, xid: bytes, options: bytes) -> None:
        packet = bytearray(240)
        packet[:4] = b"\x01\x01\x06\0"
        packet[4:8] = xid
        packet[10:12] = b"\x80\0"
        packet[28:34] = self.mac
        packet[236:240] = DHCP_MAGIC
        bootp = (bytes(packet) + options + b"\xff").ljust(300, b"\0")
        udp = struct.pack("!HHHH", 68, 67, 8 + len(bootp), 0) + bootp
        self._send(_BROADCAST + self.mac + b"\x08\0" + self._ipv4(_ZERO_IP, _BROADCAST_IP, 17, udp))

    def _dhcp_reply(self, xid: bytes, kind: int, deadline: float) -> tuple[bytes, bytes]:
        while True:
            frame = self._next_frame(deadline)
            if frame[:6] not in (self.mac, _BROADCAST):
                continue
            ip = self._ip_payload(frame, 17)
            if ip is None:
                continue
            source, _, udp = ip
            if len(udp) < 248 or struct.unpack_from("!HHH", udp) != (67, 68, len(udp)):
                continue
            reply = udp[8:]
            if reply[:4] != b"\x02\x01\x06\0" or reply[4:8] != xid or reply[28:34] != self.mac:
                continue
            options = _dhcp_options(reply)
            lease = reply[16:20]
            if (
                options.get(53) == bytes([kind]) and options.get(54) == source
                and source == b"\xc0\xa8\x04\x01"
                and lease[:3] == source[:3] and 1 < lease[3] < 255
            ):
                return lease, source

    def _lease(self, xid: bytes) -> tuple[bytes, bytes]:
        deadline = time.monotonic() + 25
        while True:
            self._dhcp_request(xid, b"\x35\x01\x01")
            try:
                lease, server = self._dhcp_reply(xid, 2, min(deadline, time.monotonic() + 1))
                break
            except TimeoutError:
                if time.monotonic() >= deadline:
                    raise
        self._dhcp_request(xid, b"\x35\x01\x03\x32\x04" + lease + b"\x36\x04" + server)
        if self._dhcp_reply(xid, 5, time.monotonic() + 3) != (lease, server):
            raise ValueError("DHCP ACK did not match the selected offer")
        return lease, server

    def _arp(self, lease: bytes, server: bytes) -> bytes:
        header = b"\0\x01\x08\0\x06\x04"
        self._send(
            _BROADCAST + self.mac + b"\x08\x06" + header + b"\0\x01"
            + self.mac + lease + b"\0" * 6 + server
        )
        deadline = time.monotonic() + 3
        while True:
            frame = self._next_frame(deadline)
            if len(frame) < 42 or frame[12:20] != b"\x08\x06" + header:
                continue
            mac, source, target = frame[22:28], frame[28:32], frame[38:42]
            if mac != frame[6:12] or mac[0] & 1 or source != server or target != lease:
                continue
            if frame[20:22] == b"\0\x01":
                self._send(
                    mac + self.mac + b"\x08\x06" + header + b"\0\x02"
                    + self.mac + lease + mac + server
                )
            elif frame[20:22] == b"\0\x02" and frame[:6] == self.mac and frame[32:38] == self.mac:
                return mac

    def _http(self, lease: bytes, server: bytes, mac: bytes) -> None:
        port = 49152 + secrets.randbelow(16384)
        initial = secrets.randbits(31)

        def send(flags: int, seq: int, ack: int, body: bytes = b"") -> None:
            tcp = bytearray(struct.pack("!HHIIBBHHH", port, 80, seq, ack, 0x50, flags, 8192, 0, 0) + body)
            pseudo = lease + server + struct.pack("!BBH", 0, 6, len(tcp))
            struct.pack_into("!H", tcp, 16, _internet_checksum(pseudo + tcp))
            self._send(mac + self.mac + b"\x08\0" + self._ipv4(lease, server, 6, bytes(tcp)))

        def read(deadline: float) -> tuple[int, int, int, bytes]:
            while True:
                frame = self._next_frame(deadline)
                ip = self._ip_payload(frame, 6)
                if frame[:12] != self.mac + mac or ip is None or ip[:2] != (server, lease):
                    continue
                tcp = ip[2]
                if len(tcp) < 20 or struct.unpack_from("!HH", tcp) != (80, port):
                    continue
                offset = (tcp[12] >> 4) * 4
                pseudo = server + lease + struct.pack("!BBH", 0, 6, len(tcp))
                if 20 <= offset <= len(tcp) and not _internet_checksum(pseudo + tcp):
                    seq, ack = struct.unpack_from("!II", tcp, 4)
                    return seq, ack, tcp[13], tcp[offset:]

        deadline = time.monotonic() + 5
        send(2, initial, 0)
        while True:
            seq, ack, flags, _ = read(deadline)
            if ack == initial + 1 and flags & 0x12 == 0x12:
                break
        next_remote = (seq + 1) & 0xffffffff
        send(0x10, initial + 1, next_remote)
        send(0x18, initial + 1, next_remote, HTTP_REQUEST)
        end_local = initial + 1 + len(HTTP_REQUEST)
        response = bytearray()
        while len(response) < len(HTTP_RESPONSE):
            seq, ack, flags, payload = read(deadline)
            if seq != next_remote or ack != end_local or not payload:
                continue
            response.extend(payload)
            if not HTTP_RESPONSE.startswith(response):
                raise ValueError("HTTP response differed from the fixed fixture")
            next_remote = (next_remote + len(payload) + bool(flags & 1)) & 0xffffffff
            send(0x10, end_local, next_remote)

    def _run(self) -> None:
        stage = "dhcp"
        try:
            lease, server = self._lease(secrets.token_bytes(4))
            self._record(dhcp=True)
            stage = "arp"
            mac = self._arp(lease, server)
            self._record(arp=True)
            stage = "http"
            self._http(lease, server, mac)
            self._record(
                http=True, status="PASS",
                http_body_sha256=hashlib.sha256(HTTP_BODY).hexdigest(),
                http_request_sha256=hashlib.sha256(HTTP_REQUEST).hexdigest(),
            )
        except _PeerStopped:
            self._record(status="INTERRUPTED", stage=stage)
        except (EOFError, OSError, ValueError):
            self._record(status="PARTIAL", stage=stage)
