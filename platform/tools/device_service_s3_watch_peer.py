"""Exact-original S3-watch WPA2 SoftAP application peer over Unix Ethernet."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

from device_service_errors import ServiceError
from device_service_softap_peer import SoftAPPeer, _PeerStopped

PROFILE = "sticks3-s3-watch-wpa2"
QOM_PROPERTY = "wpa2-softap-peer"
STATE_PROPERTY = "wpa2-softap-state"
FIRMWARE_SHA256 = "eb7f9425c07cffd972d0de479fc6c82d86af2aa51dc807d9829d5ee55add163b"
SSID_SHA256 = "972cbf88eea8e23832a3537ec184994f61abac2385a309004d849ad85a26aabe"
REQUEST = b"GET /api/state HTTP/1.0\r\nHost: 192.168.4.1\r\nConnection: close\r\n\r\n"


def parse_config(value: dict) -> dict:
    if (value.get("profile") != PROFILE
            or set(value) - {"profile", "capture_pcap", "wifi_ssid", "wifi_password"}
            or value.get("capture_pcap", True) is not True):
        raise ServiceError("invalid_network", "S3-watch accepts only its fixed peer and private Wi-Fi credentials", 400)
    ssid, password = value.get("wifi_ssid"), value.get("wifi_password")
    try:
        valid = (isinstance(ssid, str) and len(ssid.encode()) <= 32
                 and hashlib.sha256(ssid.encode()).hexdigest() == SSID_SHA256
                 and isinstance(password, str) and "\0" not in password and 8 <= len(password.encode()) <= 63)
    except UnicodeError:
        valid = False
    if not valid:
        raise ServiceError("invalid_network", "S3-watch requires its original SSID and an 8-63 byte WPA2 passphrase", 400)
    return {"profile": PROFILE, "net_mode": "unix-socketpair", "nic": "misc.esp32s3.wifi",
            "capture_pcap": True, "http_fixture": False, "wifi_auth": "wpa2-psk",
            "wifi_ssid": ssid, "wifi_password": password}


def require_backend(qemu: Path) -> None:
    try:
        output = subprocess.run([str(qemu), "-device", "misc.esp32s3.wifi,help"],
                                check=True, capture_output=True, text=True, timeout=3).stdout
        if any(line.strip().startswith(QOM_PROPERTY + "=<bool>") for line in output.splitlines()):
            return
    except (OSError, subprocess.SubprocessError):
        pass
    raise ServiceError("softap_fixture_backend_unavailable", "native QEMU lacks the WPA2 supplicant peer", 503)


def _json_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def state_body(response: bytes) -> bytes | None:
    header, separator, body = response.partition(b"\r\n\r\n")
    if len(header) > 2048:
        raise ValueError("S3-watch HTTP header exceeds its bound")
    if not separator:
        return None
    status, *lines = header.split(b"\r\n")
    if status.split()[:2] not in ([b"HTTP/1.0", b"200"], [b"HTTP/1.1", b"200"]):
        raise ValueError("S3-watch did not return HTTP 200")
    fields = {}
    for line in lines:
        name, colon, value = line.partition(b":")
        name = name.lower()
        if not colon or name in fields:
            raise ValueError("S3-watch returned an invalid header")
        fields[name] = value.strip()
    length = fields.get(b"content-length", b"")
    if (b"transfer-encoding" in fields or not length.isdigit() or len(length) > 4
            or not 0 < int(length) <= 4096
            or fields.get(b"content-type", b"").lower().split(b";", 1)[0] != b"application/json"):
        raise ValueError("S3-watch did not return bounded JSON")
    if len(body) < int(length):
        return None
    if len(body) != int(length):
        raise ValueError("S3-watch returned trailing bytes")
    value = json.loads(body, object_pairs_hook=_json_object)
    if (not isinstance(value, dict) or set(value) != {
            "t", "bt", "n", "name", "theme", "h24", "secs", "scan", "brt", "net", "ssid", "ble", "sleep", "web"}
            or not isinstance(value["t"], str) or not re.fullmatch(r"(?:\d{2}:\d{2}(?::\d{2})?|--:--(?::--)?)", value["t"])
            or not isinstance(value["bt"], str) or value["bt"] not in {"LINK", "ADV", "N/A"} or value["web"] != "1"
            or any(type(value[key]) is not int for key in ("n", "theme", "brt", "sleep"))
            or value["n"] < 0
            or any(not isinstance(value[key], str) for key in ("name", "h24", "secs", "scan", "net", "ssid", "ble"))):
        raise ValueError("S3-watch state did not match the original schema")
    return body


class S3WatchPeer(SoftAPPeer):
    _lease_timeout_seconds = 120

    def _lease(self, xid: bytes) -> tuple[bytes, bytes]:
        # AP credentials are applied by the original application's B toggle.
        # Bound discovery traffic while QEMU waits for that real association.
        deadline = time.monotonic() + self._lease_timeout_seconds
        while True:
            self._dhcp_request(xid, b"\x35\x01\x01")
            try:
                lease, server = self._dhcp_reply(xid, 2, min(deadline, time.monotonic() + 5))
                break
            except TimeoutError:
                if time.monotonic() >= deadline:
                    raise
        self._dhcp_request(xid, b"\x35\x01\x03\x32\x04" + lease + b"\x36\x04" + server)
        if self._dhcp_reply(xid, 5, time.monotonic() + 3) != (lease, server):
            raise ValueError("DHCP ACK did not match the selected offer")
        return lease, server

    def _run(self) -> None:
        stage = "dhcp"
        try:
            lease, server = self._lease(secrets.token_bytes(4))
            self._record(dhcp=True)
            stage = "arp"
            mac = self._arp(lease, server)
            self._record(arp=True)
            stage = "http"
            body = self._http(lease, server, mac, REQUEST, body_parser=state_body)
            self._record(status="PASS", http=True, http_body_sha256=hashlib.sha256(body).hexdigest(),
                         http_request_sha256=hashlib.sha256(REQUEST).hexdigest(),
                         http_status=200, state_schema=True, web_listener_reported=True)
        except _PeerStopped:
            self._record(status="INTERRUPTED", stage=stage)
        except (EOFError, OSError, ValueError):
            self._record(status="PARTIAL", stage=stage)


CONTROLLER_COUNTERS = frozenset({
    'beacons', 'auth', 'assoc', 'm1', 'm2', 'm3', 'm4', 'rejected',
    'deauth', 'data_seen', 'protected_tx', 'protected_rx',
})


def controller_state(value: object) -> dict:
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('invalid WPA2 controller observation')
    state = json.loads(value, object_pairs_hook=_json_object)
    if (not isinstance(state, dict) or set(state) != {'ready', *CONTROLLER_COUNTERS}
            or type(state['ready']) is not bool
            or any(type(state[k]) is not int or not 0 <= state[k] < 2**64 for k in CONTROLLER_COUNTERS)):
        raise ValueError('invalid WPA2 controller fields')
    return state


def controller_checks(receipt: dict) -> dict:
    state = receipt.get('state', {}) if receipt.get('status') == 'OBSERVED' else {}
    return {
        'wpa2_current_association': state.get('ready') is True,
        'wpa2_guest_handshake': all(type(state.get(k)) is int and state[k] > 0
                                    for k in ('beacons', 'auth', 'assoc', 'm1', 'm2', 'm3', 'm4')),
        'wpa2_protected_guest_tx': type(state.get('protected_tx')) is int and state['protected_tx'] > 0,
        'wpa2_protected_guest_rx': type(state.get('protected_rx')) is int and state['protected_rx'] > 0,
    }
