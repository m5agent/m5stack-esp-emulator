"""Bounded native STA DHCP, DNS, and fixed NTP fixture on one Unix stream."""
from __future__ import annotations

from pathlib import Path
import hashlib
import ipaddress
import json
import socket
import struct
import tempfile
import threading

from device_service_softap_peer import SoftAPPeer
from network_fabric import LabDhcp, build_dhcp_ethernet_reply, parse_dhcp_request
from network_sandbox import ControlledDns

PEER_MAC = bytes.fromhex("02f100000001")
PEER_IP = ipaddress.IPv4Address("10.0.2.2")
LEASE_IP = ipaddress.IPv4Address("10.0.2.15")
DNS_NAMES = frozenset(("pool.ntp.org", "time.nist.gov"))
NTP_SECONDS = 4004280000  # Fixed test time. Independent of host wall clock.
MAX_FRAME = 1518
MAX_EXCHANGES = 200


class UnixStaPeer:
    def __init__(self, evidence: Path, *, ntp_reply=True):
        self.directory = tempfile.TemporaryDirectory(prefix="m5staproof-", dir="/tmp")
        self.path = Path(self.directory.name) / "peer"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        self.listener.listen(1)
        self.listener.settimeout(.2)
        self.stop = threading.Event()
        self.events = []
        self.evidence = evidence
        self.ntp_reply = ntp_reply
        self.error = None
        self.client = None
        self.leased = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        assert not self.thread.is_alive()
        self.listener.close()
        self.directory.cleanup()
        self.evidence.write_text(json.dumps({"transport": "one Unix stream", "events": self.events,
                                             "error":self.error, "released":True},indent=2)+"\n")
        if self.error:
            raise RuntimeError(self.error)

    def run(self):
        try:
            while not self.stop.is_set():
                try:
                    with self.listener.accept()[0] as connection:
                        connection.settimeout(.15)
                        self.connection(connection)
                        return
                except TimeoutError:
                    continue
        except (OSError, ValueError) as error:
            if not self.stop.is_set():
                self.error = str(error)

    def connection(self, sock):
        buffered = bytearray()
        while not self.stop.is_set():
            try:
                chunk = sock.recv(2048)
            except TimeoutError:
                continue
            if not chunk:
                return
            buffered.extend(chunk)
            while len(buffered) >= 4:
                length = int.from_bytes(buffered[:4], "big")
                if not 14 <= length <= MAX_FRAME:
                    raise ValueError("invalid QEMU Ethernet frame")
                if len(buffered) < 4 + length:
                    break
                packet = bytes(buffered[4:4+length])
                del buffered[:4+length]
                response = self.reply(packet)
                if response:
                    sock.sendall(struct.pack("!I", len(response)) + response)

    def record(self, **fields):
        if len(self.events) < MAX_EXCHANGES:
            self.events.append(fields)

    def reply(self, frame):
        if self.client and frame[6:12] != self.client:
            return None
        if frame[12:14] == b"\x08\x06":
            return self.reply_arp(frame)
        ip = SoftAPPeer._ip_payload(frame, 17)
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
            return self.reply_dhcp(frame[6:12], payload)
        if not self.leased or source != LEASE_IP.packed or destination != PEER_IP.packed:
            return None
        if port == 53:
            response = self.reply_dns(payload)
        elif port == 123:
            response = self.reply_ntp(payload)
        else:
            return None
        if not response:
            return None
        udp = struct.pack("!HHHH", port, source_port, len(response)+8, 0) + response
        return self.client + PEER_MAC + b"\x08\x00" + SoftAPPeer._ipv4(
            PEER_IP.packed, LEASE_IP.packed, 17, udp)

    def reply_dhcp(self, client, payload):
        parsed = parse_dhcp_request(payload)
        if (parsed is None or parsed["message_type"] not in (1, 3)
                or parsed["mac"] != client.hex(":") or client[0] & 3 != 2):
            return None
        if self.client is None:
            self.client = client
            self.dhcp = LabDhcp({"interface":"unix", "server_address":str(PEER_IP),
                                "reservations":{client.hex(":"):str(LEASE_IP)}})
        reply = self.dhcp.handle(payload, source_mac=client.hex(":"))
        if reply:
            self.leased = self.leased or parsed["message_type"] == 3
            self.record(protocol="dhcp", message="offer" if parsed["message_type"] == 1 else "ack")
            return build_dhcp_ethernet_reply(reply, source_mac=client, server_mac=PEER_MAC,
                                             server_address=str(PEER_IP))
        return None

    def reply_arp(self, frame):
        if (self.client and len(frame) >= 42 and frame[14:22] == bytes.fromhex("0001080006040001")
                and frame[22:28] == self.client and frame[38:42] == PEER_IP.packed):
            self.record(protocol="arp", message="reply")
            return self.client + PEER_MAC + bytes.fromhex("08060001080006040002") + PEER_MAC + (
                PEER_IP.packed + self.client + frame[28:32])
        return None

    def reply_dns(self, request):
        question = ControlledDns.parse_question(request)
        if question is None:
            return None
        name, qtype, qclass, end = question
        allowed = name in DNS_NAMES and qtype == 1 and qclass == 1
        self.record(protocol="dns", message="A" if allowed else "NXDOMAIN",
                    name=name if allowed else "other")
        records = bytes.fromhex("c00c000100010000003c0004") + PEER_IP.packed if allowed else b""
        return request[:2] + struct.pack("!HHHHH", 0x8180 if allowed else 0x8183,
                                         1, int(allowed), 0, 0) + request[12:end] + records

    def reply_ntp(self, request):
        if len(request) != 48 or request[0] & 7 != 3:
            return None
        if not self.ntp_reply:
            self.record(protocol="ntp", message="withheld")
            return None
        response = bytearray(48)
        response[:4] = bytes([0x24, 1, request[2], 0xec])
        response[12:16] = b"LOCL"
        struct.pack_into("!II", response, 16, NTP_SECONDS-1, 0)
        response[24:32] = request[40:48]
        struct.pack_into("!IIII",response,32,NTP_SECONDS,10000,NTP_SECONDS,20000)
        self.record(protocol="ntp", message="server", response_sha256=hashlib.sha256(response).hexdigest())
        return bytes(response)
