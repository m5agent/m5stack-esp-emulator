"""Fixed open SoftAP peers using QEMU's local Ethernet stream."""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from device_service_errors import ServiceError
from network_fabric import (
    DHCP_MAGIC, LabDhcp, _dhcp_options, _internet_checksum,
    build_dhcp_ethernet_reply, parse_dhcp_request,
)

PROFILE = "cardputer-open-softap-fixture"
STICKS3_PROFILE = "sticks3-open-softap-fixture"
STICKS3_PORTAL_PROFILE = "sticks3-open-softap-portal"
STICKS3_PROVISION_PROFILE = "sticks3-open-softap-provisioning"
PROFILE_BOARDS = {
    PROFILE: frozenset({"cardputer", "cardputer-adv"}),
    STICKS3_PROFILE: frozenset({"sticks3"}),
    STICKS3_PORTAL_PROFILE: frozenset({"sticks3"}),
    STICKS3_PROVISION_PROFILE: frozenset({"sticks3"}),
}
ACL_OPERATION = "network.softap.probe"
PROVISION_ACL_OPERATION = "network.softap.provision"
QOM_PROPERTY = "open-softap-peer"
PORTAL_QOM_PROPERTY = "open-softap-sticks3-portal"
STATION_QOM_PROPERTY = "open-softap-sticks3-station"
NIC = "misc.esp32s3.wifi"
HTTP_REQUEST = b"GET /proof HTTP/1.0\r\n\r\n"
HTTP_BODY = b"AP_FIXTURE_OK"
HTTP_RESPONSE = b"HTTP/1.0 200 OK\r\nContent-Length: 13\r\n\r\n" + HTTP_BODY
PORTAL_REQUEST = b"GET / HTTP/1.0\r\nHost: 192.168.4.1\r\nConnection: close\r\n\r\n"
PROVISION_SSID = "fixturetest"
_FORM = f"s={PROVISION_SSID}&p=".encode()
_SAVE_REQUEST = (
    b"POST /wifisave HTTP/1.0\r\nHost: 192.168.4.1\r\nConnection: close\r\n"
    b"Content-Type: application/x-www-form-urlencoded\r\nContent-Length: "
    + str(len(_FORM)).encode() + b"\r\n\r\n" + _FORM
)
_ROOT_MARKERS = (b"<h3>StickS3-Setup</h3>", b"<form action='/wifi'")
_SAVE_MARKERS = (b"Saving Credentials", b"Trying to connect ESP to network")
PROVISION_STATION_GATEWAY = ipaddress.IPv4Address("10.0.2.2")
PROVISION_STATION_LEASE = ipaddress.IPv4Address("10.0.2.15")
_STATION_GATEWAY_MAC = bytes.fromhex("02f100000001")
_ARP_HEADER = b"\x08\x06\0\x01\x08\0\x06\x04"
_PORTAL_MAX_HEADER = 2048
_PORTAL_MAX_BODY = 8192
_BROADCAST = b"\xff" * 6
_ZERO_IP = b"\0" * 4
_BROADCAST_IP = b"\xff" * 4
_MAX_ETHERNET = 1514


def require_softap_backend(qemu: Path, *, portal: bool = False, station: bool = False) -> None:
    try:
        result = subprocess.run(
            [str(qemu), "-device", f"{NIC},help"],
            check=True, capture_output=True, text=True, timeout=3,
        )
        required = [QOM_PROPERTY]
        if portal or station:
            required.append(PORTAL_QOM_PROPERTY)
        if station:
            required.append(STATION_QOM_PROPERTY)
        options = result.stdout.splitlines()
        if all(any(line.strip().startswith(f"{prop}=<bool>") for line in options)
               for prop in required):
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


class _StationDiscovered(Exception):
    def __init__(self, frame: bytes):
        super().__init__("guest sent a station DHCP DISCOVER during AP discovery")
        self.frame = frame


def _portal_http_body(response: bytes, markers: tuple[bytes, ...] = _ROOT_MARKERS) -> bytes | None:
    header, separator, body = response.partition(b"\r\n\r\n")
    if len(header) > _PORTAL_MAX_HEADER:
        raise ValueError("portal HTTP header exceeded the limit")
    if not separator:
        return None
    status, *headers = header.split(b"\r\n")
    if status.split()[:2] not in ([b"HTTP/1.0", b"200"], [b"HTTP/1.1", b"200"]):
        raise ValueError("portal did not return HTTP 200")
    fields = {}
    for line in headers:
        name, colon, value = line.partition(b":")
        name = name.lower()
        if not colon or name in fields:
            raise ValueError("invalid portal HTTP header")
        fields[name] = value.strip()
    length = fields.get(b"content-length", b"")
    if (
        b"transfer-encoding" in fields or not length.isdigit()
        or len(length) > 4 or not 0 < int(length) <= _PORTAL_MAX_BODY
        or fields.get(b"content-type", b"").lower().split(b";", 1)[0] != b"text/html"
    ):
        raise ValueError("portal did not return bounded HTML")
    size = int(length)
    if len(body) < size:
        return None
    if len(body) != size or not all(marker in body for marker in markers):
        raise ValueError("portal HTML did not match the expected setup page")
    return body


class SoftAPPeer:
    """Per-lease peer. Neither endpoint can dial or listen on an IP socket."""

    def __init__(self, mac: str, persist: Callable[[dict], None], *, portal: bool = False):
        self.mac = bytes.fromhex(mac.replace(":", ""))
        if len(self.mac) != 6 or self.mac[0] & 3 != 2:
            raise ValueError("SoftAP peer requires a locally administered unicast address")
        self._peer, self.child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self._peer.settimeout(0.15)
        self._persist = persist
        self._portal = portal
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
        if self._generation:
            self._discard_pending_frames()
        self._stop.clear()
        self._generation += 1
        with self._lock:
            self._receipt = {}
        self._record(
            schema_version=1, transport="unix-socketpair", generation=self._generation,
            status="RUNNING", released=False, **self._initial_protocol_state(),
        )
        self._thread = threading.Thread(target=self._run, name="softap-fixture-peer", daemon=True)
        self._thread.start()

    @staticmethod
    def _initial_protocol_state() -> dict:
        return {"dhcp": False, "arp": False, "http": False}

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
            status="INTERRUPTED", stage="reset", **self._initial_protocol_state(),
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

    def _discard_pending_frames(self) -> None:
        previous_timeout = self._peer.gettimeout()
        self._peer.setblocking(False)
        try:
            for _ in range(64):
                if not self._peer.recv(2048):
                    break
            else:
                raise RuntimeError("old Wi-Fi fixture frames did not drain")
        except BlockingIOError:
            pass
        finally:
            self._peer.settimeout(previous_timeout)
        self._input.clear()

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

    def _dhcp_reply(
        self, xid: bytes, kind: int, deadline: float, *, on_frame: Callable[[bytes], None] | None = None,
    ) -> tuple[bytes, bytes]:
        while True:
            frame = self._next_frame(deadline)
            if on_frame is not None:
                on_frame(frame)
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

    def _lease(self, xid: bytes, *, on_frame: Callable[[bytes], None] | None = None) -> tuple[bytes, bytes]:
        deadline = time.monotonic() + 25
        while True:
            self._dhcp_request(xid, b"\x35\x01\x01")
            try:
                lease, server = self._dhcp_reply(xid, 2, min(deadline, time.monotonic() + 1), on_frame=on_frame)
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

    def _http(
        self, lease: bytes, server: bytes, mac: bytes, request: bytes,
        *, markers: tuple[bytes, ...] = _ROOT_MARKERS,
    ) -> bytes:
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
        while time.monotonic() < deadline:
            send(2, initial, 0)
            try:
                seq, ack, flags, _ = read(min(deadline, time.monotonic() + 0.65))
            except TimeoutError:
                continue
            if ack != initial + 1:
                continue
            if flags & 0x04:
                raise ConnectionRefusedError
            if flags & 0x12 == 0x12:
                break
        else:
            raise TimeoutError

        next_remote = (seq + 1) & 0xffffffff
        send(0x10, initial + 1, next_remote)
        send(0x18, initial + 1, next_remote, request)
        end_local = initial + 1 + len(request)
        response = bytearray()
        deadline = time.monotonic() + 5
        while True:
            seq, ack, flags, payload = read(deadline)
            if seq != next_remote or ack != end_local or not payload:
                continue
            response.extend(payload)
            if self._portal:
                body = _portal_http_body(bytes(response), markers)
            else:
                if not HTTP_RESPONSE.startswith(response):
                    raise ValueError("HTTP response differed from the fixed fixture")
                body = HTTP_BODY if len(response) == len(HTTP_RESPONSE) else None
            next_remote = (next_remote + len(payload) + bool(flags & 1)) & 0xffffffff
            if body is not None:
                send(0x11, end_local, next_remote)
                return body
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
            request = PORTAL_REQUEST if self._portal else HTTP_REQUEST
            attempts = 8 if self._portal else 1
            for attempt in range(attempts):
                try:
                    body = self._http(lease, server, mac, request)
                    break
                except ConnectionRefusedError:
                    # WiFiManager starts the guest AP before binding its HTTP server.
                    # Retry only a rejected connection, before emitting any request.
                    if attempt == attempts - 1:
                        raise
                    if self._stop.wait(0.5):
                        raise _PeerStopped
            self._complete_http(lease, server, mac, {
                "http": True, "http_body_sha256": hashlib.sha256(body).hexdigest(),
                "http_request_sha256": hashlib.sha256(request).hexdigest(),
            })
        except _PeerStopped:
            self._record(status="INTERRUPTED", stage=stage)
        except (EOFError, OSError, ValueError):
            self._record(status="PARTIAL", stage=stage)

    def _complete_http(self, lease: bytes, server: bytes, mac: bytes, evidence: dict) -> None:
        self._record(status="PASS", **evidence)


class PortalStationPeer(SoftAPPeer):
    """Submit the owned lab SSID, then observe its lease on the same socketpair."""

    def __init__(self, mac: str, station_mac: str, persist: Callable[[dict], None]):
        super().__init__(mac, persist, portal=True)
        self._station_mac = bytes.fromhex(station_mac.replace(":", ""))
        self._station_proven = False
        self._capture_start_offset = None

    def start(self, *, capture_start_offset: int | None = None) -> None:
        self._capture_start_offset = capture_start_offset
        super().start()

    @staticmethod
    def _initial_protocol_state() -> dict:
        return {
            **SoftAPPeer._initial_protocol_state(),
            "save_http": False, "save_body_sha256": None,
            "station_dhcp": False, "station_arp": False,
            "station_reconnect": False, "station_on_start": False,
            "station_dhcp_xid": None, "capture_start_offset": None,
        }

    def _observe_station_discover(self, frame: bytes) -> None:
        packet = self._station_dhcp_packet(frame)
        if packet is not None and _dhcp_options(packet).get(53) == b"\x01":
            raise _StationDiscovered(frame)

    def _lease(self, xid: bytes, *, on_frame: Callable[[bytes], None] | None = None) -> tuple[bytes, bytes]:
        if self._generation == 1:
            on_frame = self._observe_station_discover
        return super()._lease(xid, on_frame=on_frame)

    def _run(self) -> None:
        stage = "station-reconnect"
        try:
            if self._station_proven:
                self._record(stage=stage, station_reconnect=True, capture_start_offset=self._capture_start_offset)
                self._await_station()
                return
            try:
                super()._run()
            except _StationDiscovered as discover:
                stage = "station-on-start"
                self._record(stage=stage, station_on_start=True)
                self._await_station(first_frame=discover.frame)
        except _PeerStopped:
            self._record(status="INTERRUPTED", stage=stage)
        except (EOFError, OSError, ValueError):
            self._record(status="PARTIAL", stage=stage)

    def _complete_http(self, lease: bytes, server: bytes, mac: bytes, evidence: dict) -> None:
        stage = "submit"
        self._record(stage=stage, **evidence)
        try:
            # This is the ordinary WiFiManager form with the fixed, open lab SSID.
            # It is sent at most once per peer run.
            body = self._http(lease, server, mac, _SAVE_REQUEST, markers=_SAVE_MARKERS)
            stage = "station"
            self._record(stage=stage, save_http=True, save_body_sha256=hashlib.sha256(body).hexdigest())
            self._await_station()
        except _PeerStopped:
            self._record(status="INTERRUPTED", stage=stage)
        except (EOFError, OSError, ValueError):
            self._record(status="PARTIAL", stage=stage)

    def _await_station(self, *, first_frame: bytes | None = None) -> None:
        station = self._station_mac
        mac = station.hex(":")
        gateway = PROVISION_STATION_GATEWAY.packed
        lease = PROVISION_STATION_LEASE.packed
        router = _STATION_GATEWAY_MAC
        dhcp = LabDhcp({
            "interface": "unix", "server_address": str(PROVISION_STATION_GATEWAY),
            "reservations": {mac: str(PROVISION_STATION_LEASE)},
        })
        arp_request = (
            _BROADCAST + router + _ARP_HEADER + b"\0\x01"
            + router + gateway + b"\0" * 6 + lease
        )
        arp_reply = router + station + _ARP_HEADER + b"\0\x02" + station + lease + router + gateway
        deadline = time.monotonic() + 28
        probe_at = None
        offered_xid = None
        acknowledged_xid = None
        while time.monotonic() < deadline:
            if probe_at is not None and time.monotonic() >= probe_at:
                self._send(arp_request)
                probe_at = time.monotonic() + 0.5
            if first_frame is not None:
                frame, first_frame = first_frame, None
            else:
                try:
                    frame = self._next_frame(min(deadline, probe_at or deadline))
                except TimeoutError:
                    continue
            if frame[6:12] != station:
                continue
            if acknowledged_xid is not None and frame[:42] == arp_reply:
                self._station_proven = True
                self._record(station_arp=True, status="PASS")
                return
            packet = self._station_dhcp_packet(frame)
            if packet is None:
                continue
            reply = dhcp.handle(packet, source_mac=mac)
            if reply is None:
                continue
            xid = reply[4:8].hex()
            message_type = _dhcp_options(reply).get(53)
            if message_type == b"\x02":
                offered_xid = xid
            elif xid != offered_xid:
                continue
            self._send(build_dhcp_ethernet_reply(
                reply, source_mac=station, server_mac=router,
                server_address=str(PROVISION_STATION_GATEWAY),
            ))
            if message_type == b"\x05":
                acknowledged_xid = xid
                self._record(station_dhcp=True, station_dhcp_xid=xid)
                probe_at = time.monotonic()
        raise TimeoutError

    def _station_dhcp_packet(self, frame: bytes) -> bytes | None:
        if frame[6:12] != self._station_mac:
            return None
        ip = self._ip_payload(frame, socket.IPPROTO_UDP)
        if ip is None or len(ip[2]) < 8:
            return None
        _, _, udp = ip
        if struct.unpack_from("!HHH", udp) != (68, 67, len(udp)):
            return None
        packet = udp[8:]
        parsed = parse_dhcp_request(packet)
        if parsed is None or parsed["mac"] != self._station_mac.hex(":") or parsed["message_type"] not in (1, 3):
            return None
        return packet
