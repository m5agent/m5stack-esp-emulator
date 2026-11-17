"""Offline DNS and SNTP for the native Cardputer ADV Wi-Fi station fixture."""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import struct
import time

from device_service_softap_peer import SoftAPPeer, _PeerStopped
from network_fabric import LabDhcp, build_dhcp_ethernet_reply, parse_dhcp_request
from network_sandbox import ControlledDns

PROFILE = "cardputer-adv-local-time-fixture"
DEVICE = "cardputer-adv"
ACL_OPERATION = "network.sta.time.probe"
SSID = "fixturetest"
NTP_SECONDS = 4004280000
PEER_MAC = bytes.fromhex("02f100000001")
PEER_IP = ipaddress.IPv4Address("10.0.2.2")
LEASE_IP = ipaddress.IPv4Address("10.0.2.15")
TIME_NAMES = frozenset(("pool.ntp.org", "time.nist.gov"))
MAX_REPLIES = 128


class StationTimePeer(SoftAPPeer):
    """Serves fixed packets on a per-session Unix socketpair."""

    def __init__(self, mac, persist, *, withhold_ntp=False):
        super().__init__(mac, persist)
        self.withhold_ntp = withhold_ntp
        self._leased = False
        self._counts = {}
        self._dhcp_server = None

    def start(self):
        if self._generation:
            previous_timeout = self._peer.gettimeout()
            self._peer.setblocking(False)
            try:
                for _ in range(64):
                    if not self._peer.recv(2048):
                        break
                else:
                    raise RuntimeError("old station fixture frames did not drain")
            except BlockingIOError:
                pass
            finally:
                self._peer.settimeout(previous_timeout)
            self._input.clear()
        self._leased = False
        self._counts = {}
        self._dhcp_server = LabDhcp({
            "interface": "unix", "server_address": str(PEER_IP),
            "reservations": {self.mac.hex(":"): str(LEASE_IP)},
        })
        super().start()

    def invalidate_for_reset(self):
        self.pause()
        self._record(status="INTERRUPTED", stage="reset", **self._initial_protocol_state())

    @staticmethod
    def _initial_protocol_state() -> dict:
        return {"dhcp": False, "arp": False, "dns_a_replies": 0, "dns_denials": 0,
                "ntp_requests": 0, "ntp_replies": 0, "last_ntp_response_sha256": None}

    def _count(self, kind):
        self._counts[kind] = self._counts.get(kind, 0) + 1
        return self._counts[kind]

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    packet = self._next_frame(time.monotonic() + 1)
                except TimeoutError:
                    continue
                if sum(self._counts.values()) >= MAX_REPLIES:
                    continue
                if reply := self._reply(packet):
                    self._send(reply)
        except _PeerStopped:
            return
        except (EOFError, OSError, ValueError):
            if not self._counts.get("ntp_replies"):
                self._record(status="PARTIAL", stage="transport")

    def _reply(self, frame):
        if frame[6:12] != self.mac:
            return None
        if frame[12:14] == b"\x08\x06":
            return self._reply_arp(frame)
        ip = self._ip_payload(frame, socket.IPPROTO_UDP)
        if ip is None:
            return None
        source, destination, udp = ip
        if len(udp) < 8:
            return None
        source_port, port, length = struct.unpack_from("!HHH", udp)
        if length != len(udp):
            return None
        payload = udp[8:]
        if (source_port, port) == (68, 67):
            return self._reply_dhcp(payload)
        if not self._leased or source != LEASE_IP.packed or destination != PEER_IP.packed:
            return None
        if port == 53:
            response = self._reply_dns(payload)
        elif port == 123:
            response = self._reply_ntp(payload)
        else:
            return None
        if not response:
            return None
        udp = struct.pack("!HHHH", port, source_port, len(response) + 8, 0) + response
        return self.mac + PEER_MAC + b"\x08\x00" + self._ipv4(
            PEER_IP.packed, LEASE_IP.packed, socket.IPPROTO_UDP, udp,
        )

    def _reply_dhcp(self, payload):
        parsed = parse_dhcp_request(payload)
        if (parsed is None or parsed["message_type"] not in (1, 3)
                or parsed["mac"] != self.mac.hex(":")):
            return None
        reply = self._dhcp_server.handle(payload, source_mac=self.mac.hex(":"))
        if reply is None:
            return None
        self._count("dhcp_replies")
        if parsed["message_type"] == 3:
            self._leased = True
            self._record(dhcp=True)
        return build_dhcp_ethernet_reply(reply, source_mac=self.mac, server_mac=PEER_MAC,
                                         server_address=str(PEER_IP))

    def _reply_arp(self, frame):
        if (self._leased and len(frame) >= 42 and frame[14:22] == bytes.fromhex("0001080006040001")
                and frame[22:28] == self.mac and frame[38:42] == PEER_IP.packed):
            self._count("arp_replies")
            self._record(arp=True)
            return self.mac + PEER_MAC + bytes.fromhex("08060001080006040002") + PEER_MAC + (
                PEER_IP.packed + self.mac + frame[28:32]
            )
        return None

    def _reply_dns(self, request):
        question = ControlledDns.parse_question(request)
        if question is None:
            return None
        name, qtype, qclass, end = question
        allowed = name in TIME_NAMES and qtype == 1 and qclass == 1
        counter = "dns_a_replies" if allowed else "dns_denials"
        self._record(**{counter: self._count(counter)})
        records = bytes.fromhex("c00c000100010000003c0004") + PEER_IP.packed if allowed else b""
        return request[:2] + struct.pack("!HHHHH", 0x8180 if allowed else 0x8183,
                                         1, int(allowed), 0, 0) + request[12:end] + records

    def _reply_ntp(self, request):
        if len(request) != 48 or request[0] & 7 != 3:
            return None
        self._record(ntp_requests=self._count("ntp_requests"))
        if self.withhold_ntp:
            return None
        response = bytearray(48)
        response[:4] = bytes([0x24, 1, request[2], 0xec])
        response[12:16] = b"LOCL"
        struct.pack_into("!II", response, 16, NTP_SECONDS - 1, 0)
        response[24:32] = request[40:48]
        struct.pack_into("!IIII", response, 32, NTP_SECONDS, 10000, NTP_SECONDS, 20000)
        self._record(
            status="REPLIED", ntp_replies=self._count("ntp_replies"),
            last_ntp_response_sha256=hashlib.sha256(response).hexdigest(),
        )
        return bytes(response)
