"""Bounded original StopWatch JSON provisioning on an Ethernet socketpair.

This peer is a client of the guest's ordinary portal and a private open lab AP
DHCP server concurrently. It never opens IP sockets or writes guest memory/NVS.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from device_service_softap_peer import (
    PORTAL_REQUEST, PROVISION_SSID, PROVISION_STATION_GATEWAY,
    PROVISION_STATION_LEASE, PortalStationPeer, SoftAPPeer, _ARP_HEADER,
    _BROADCAST, _PeerStopped, _STATION_GATEWAY_MAC,
)
from network_fabric import LabDhcp, _dhcp_options, build_dhcp_ethernet_reply

_SUBMIT = json.dumps({"ssid": PROVISION_SSID, "password": ""}, separators=(",", ":")).encode()
EXIT_REQUEST = (b"POST /exit HTTP/1.0\r\nHost: 192.168.4.1\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
DONE_REQUEST = PORTAL_REQUEST.replace(b"GET / ", b"GET /done.html ")
SUBMIT_REQUEST = (
    b"POST /submit HTTP/1.0\r\nHost: 192.168.4.1\r\nConnection: close\r\n"
    b"Content-Type: application/json\r\nContent-Length: "
    + str(len(_SUBMIT)).encode() + b"\r\n\r\n" + _SUBMIT
)


def _body(response: bytes, *, submit: bool = False, done: bool = False) -> bytes | None:
    header, separator, body = response.partition(b"\r\n\r\n")
    if len(header) > 2048:
        raise ValueError("StopWatch HTTP header exceeded its bound")
    if not separator:
        return None
    status, *lines = header.split(b"\r\n")
    if status.split()[:2] not in ([b"HTTP/1.0", b"200"], [b"HTTP/1.1", b"200"]):
        raise ValueError("StopWatch portal did not return HTTP 200")
    fields = {}
    for line in lines:
        name, colon, value = line.partition(b":")
        name = name.lower()
        if not colon or name in fields:
            raise ValueError("invalid StopWatch HTTP header")
        fields[name] = value.strip()
    length = fields.get(b"content-length", b"")
    expected_type = b"application/json" if submit else b"text/html"
    if (b"transfer-encoding" in fields or not length.isdigit() or len(length) > 5
            or not 0 < int(length) <= (1024 if submit else 65536)
            or fields.get(b"content-type", b"").lower().split(b";", 1)[0] != expected_type):
        raise ValueError("StopWatch portal response format exceeded the contract")
    if len(body) < int(length):
        return None
    if len(body) != int(length):
        raise ValueError("StopWatch response length differed")
    if submit:
        if body != b'{"success":true}':
            raise ValueError("StopWatch did not confirm successful provisioning")
    elif not all(marker in body for marker in ((b"/exit",) if done else (b"/submit", b"ssid", b"password"))):
        raise ValueError("StopWatch page did not contain its provisioning form")
    return body


class StopWatchProvisionPeer(PortalStationPeer):
    """Complete the association test, /done.html and /exit before observing STA.

    The exact original saves and disconnects after the /submit association test;
    its normal /exit then starts the station manager and DHCP. JSON success alone
    never proves that the final station acquired an address.
    """

    _lease_timeout_seconds = 90

    def __init__(self, mac: str, station_mac: str, persist):
        super().__init__(mac, station_mac, persist)
        self._offered_xid = None
        self._acknowledged_xid = None
        self._exit_response_received = False
        self._station_dhcp_after_exit = False
        self._station_arp_seen = False
        self._dhcp = LabDhcp({
            "interface": "unix", "server_address": str(PROVISION_STATION_GATEWAY),
            "reservations": {station_mac: str(PROVISION_STATION_LEASE)},
        })

    @staticmethod
    def _initial_protocol_state() -> dict:
        return {
            **PortalStationPeer._initial_protocol_state(),
            "submit_http": False, "submit_body_sha256": None,
            "exit_http": False, "done_http": False, "station_dhcp_after_exit_response": False,
        }

    def _next_frame(self, deadline: float) -> bytes:
        frame = SoftAPPeer._next_frame(self, deadline)
        self._station_frame(frame)
        return frame

    def _station_frame(self, frame: bytes) -> None:
        if frame[6:12] != self._station_mac:
            return
        packet = self._station_dhcp_packet(frame)
        if packet is not None:
            reply = self._dhcp.handle(packet, source_mac=self._station_mac.hex(":"))
            if reply is None:
                return
            xid = reply[4:8].hex()
            kind = _dhcp_options(reply).get(53)
            if kind == b"\x02":
                self._offered_xid = xid
            elif xid != self._offered_xid:
                return
            self._send(build_dhcp_ethernet_reply(
                reply, source_mac=self._station_mac, server_mac=_STATION_GATEWAY_MAC,
                server_address=str(PROVISION_STATION_GATEWAY),
            ))
            if kind == b"\x05":
                self._acknowledged_xid = xid
                self._station_dhcp_after_exit |= self._exit_response_received
                self._record(station_dhcp=True, station_dhcp_xid=xid)
                self._arp_probe()
            return
        if self._acknowledged_xid is None or len(frame) < 42 or frame[12:20] != _ARP_HEADER:
            return
        station, gateway = self._station_mac, _STATION_GATEWAY_MAC
        lease, server = PROVISION_STATION_LEASE.packed, PROVISION_STATION_GATEWAY.packed
        if frame[22:32] != station + lease or frame[38:42] != server:
            return
        if frame[20:22] == b"\0\x01":
            self._send(station + gateway + _ARP_HEADER + b"\0\x02"
                       + gateway + server + station + lease)
        elif frame[:6] == gateway and frame[20:22] == b"\0\x02" and frame[32:38] == gateway:
            self._station_arp_seen = True
            self._record(station_arp=True)

    def _arp_probe(self) -> None:
        router = _STATION_GATEWAY_MAC
        self._send(_BROADCAST + router + _ARP_HEADER + b"\0\x01"
                   + router + PROVISION_STATION_GATEWAY.packed + b"\0" * 6
                   + PROVISION_STATION_LEASE.packed)

    def _run(self) -> None:
        stage = "ap-dhcp"
        try:
            if self._station_proven:
                stage = "station-reconnect"
                self._offered_xid = self._acknowledged_xid = None
                self._station_arp_seen = False
                self._record(stage=stage, station_reconnect=True,
                             capture_start_offset=self._capture_start_offset)
                deadline = time.monotonic() + 35
                while not self._station_arp_seen:
                    try:
                        self._next_frame(min(deadline, time.monotonic() + 0.5))
                    except TimeoutError:
                        if time.monotonic() >= deadline:
                            raise
                    if self._acknowledged_xid is not None:
                        self._arp_probe()
                self._record(status="PASS", stage="complete")
                return
            # Cold proof must actually visit the AP. No NVS/on-start shortcut.
            ap_xid = secrets.token_bytes(4)
            self._record(ap_dhcp_xid=ap_xid.hex())
            lease, server = SoftAPPeer._lease(self, ap_xid)
            self._record(dhcp=True)
            stage = "ap-arp"
            mac = self._arp(lease, server)
            self._record(arp=True)
            stage = "portal"
            for attempt in range(8):
                try:
                    body = self._http(lease, server, mac, PORTAL_REQUEST, body_parser=_body)
                    break
                except ConnectionRefusedError:
                    if attempt == 7:
                        raise
                    if self._stop.wait(0.5):
                        raise _PeerStopped
            self._record(http=True, http_body_sha256=hashlib.sha256(body).hexdigest(),
                         http_request_sha256=hashlib.sha256(PORTAL_REQUEST).hexdigest())
            stage = "submit-and-station"
            body = self._http(lease, server, mac, SUBMIT_REQUEST,
                              body_parser=lambda response: _body(response, submit=True),
                              response_timeout=35)
            self._record(submit_http=True, submit_body_sha256=hashlib.sha256(body).hexdigest(),
                         submit_request_sha256=hashlib.sha256(SUBMIT_REQUEST).hexdigest(),
                         submit_confirmed=True)
            stage = "portal-done"
            body = self._http(lease, server, mac, DONE_REQUEST,
                              body_parser=lambda response: _body(response, done=True))
            self._record(done_http=True, done_body_sha256=hashlib.sha256(body).hexdigest(),
                         done_request_sha256=hashlib.sha256(DONE_REQUEST).hexdigest())
            stage = "portal-exit"
            body = self._http(lease, server, mac, EXIT_REQUEST,
                              body_parser=lambda response: _body(response, submit=True))
            self._exit_response_received = True
            self._record(exit_http=True, exit_body_sha256=hashlib.sha256(body).hexdigest(),
                         exit_request_sha256=hashlib.sha256(EXIT_REQUEST).hexdigest())
            stage = "station-dhcp-arp"
            deadline = time.monotonic() + 35
            while not self._station_arp_seen:
                if self._acknowledged_xid is not None:
                    self._arp_probe()
                try:
                    self._next_frame(min(deadline, time.monotonic() + 0.5))
                except TimeoutError:
                    if time.monotonic() >= deadline:
                        raise
            self._record(station_dhcp_after_exit_response=self._station_dhcp_after_exit)
            if not self._station_dhcp_after_exit:
                raise ValueError("STA lease did not follow the ordinary portal exit")
            self._station_proven = True
            self._record(status="PASS", stage="complete")
        except _PeerStopped:
            self._record(status="INTERRUPTED", stage=stage)
        except (EOFError, OSError, ValueError) as error:
            self._record(status="PARTIAL", stage=stage, error_type=type(error).__name__)
