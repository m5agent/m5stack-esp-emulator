#!/usr/bin/env python3
"""HMAC-authenticated multicast discovery for worker control planes."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

DISCOVERY_SCHEMA_VERSION = 1
DISCOVERY_KIND = "m5stack-worker-discovery-v1"
DEFAULT_DISCOVERY_GROUP = "239.255.77.77"
DEFAULT_DISCOVERY_PORT = 8788
DEFAULT_DISCOVERY_INTERVAL = 2.0
DEFAULT_DISCOVERY_TTL = 8.0
MAX_DISCOVERY_PACKET_BYTES = 4096
DISCOVERY_CLOCK_SKEW_SECONDS = 30
MAX_DISCOVERY_TTL_SECONDS = 300
MAX_DISCOVERY_SEED_TIMEOUT_SECONDS = 60
DISCOVERY_FIELDS = {
    "schema_version",
    "kind",
    "service_url",
    "group",
    "port",
    "issued_at",
    "expires_at",
    "nonce",
    "signature",
}


class _RejectDiscoveryRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WorkerDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_group(group: str) -> None:
    try:
        address = ipaddress.IPv4Address(group)
    except ipaddress.AddressValueError as error:
        raise WorkerDiscoveryError(
            "invalid_discovery_group",
            "worker discovery group must be an IPv4 address",
        ) from error
    if not address.is_multicast:
        raise WorkerDiscoveryError(
            "invalid_discovery_group",
            "worker discovery group must be multicast",
        )


def _validate_port(port: int) -> None:
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise WorkerDiscoveryError(
            "invalid_discovery_port",
            "worker discovery port must be 1-65535",
        )


def normalize_service_url(service_url: str) -> str:
    if not isinstance(service_url, str):
        raise WorkerDiscoveryError(
            "invalid_discovery_service_url",
            "worker discovery service URL must be a string",
        )
    value = service_url.rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise WorkerDiscoveryError(
            "invalid_discovery_service_url",
            "worker discovery service URL must be an HTTP(S) base URL "
            "without credentials, query or fragment",
        )
    return value


def normalize_discovery_seed_url(seed_url: str) -> str:
    if not isinstance(seed_url, str):
        raise WorkerDiscoveryError(
            "invalid_discovery_seed_url",
            "worker discovery seed URL must be a string",
        )
    value = seed_url.rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise WorkerDiscoveryError(
            "invalid_discovery_seed_url",
            "worker discovery seed URL must be an HTTP(S) URL without "
            "credentials, query or fragment",
        )
    return value


def _canonical_beacon(fields: Mapping[str, Any]) -> bytes:
    payload = {
        key: fields[key]
        for key in DISCOVERY_FIELDS
        if key != "signature"
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _signature(master_token: str, fields: Mapping[str, Any]) -> str:
    if not master_token:
        raise WorkerDiscoveryError(
            "invalid_discovery_secret",
            "worker discovery requires a non-empty master token",
        )
    return hmac.new(
        master_token.encode("utf-8"),
        b"m5stack-worker-discovery-v1\0" + _canonical_beacon(fields),
        hashlib.sha256,
    ).hexdigest()


def build_discovery_beacon(
    master_token: str,
    service_url: str,
    *,
    group: str = DEFAULT_DISCOVERY_GROUP,
    port: int = DEFAULT_DISCOVERY_PORT,
    ttl_seconds: float = DEFAULT_DISCOVERY_TTL,
    now: float | None = None,
) -> dict[str, Any]:
    _validate_group(group)
    _validate_port(port)
    if not 1 <= ttl_seconds <= MAX_DISCOVERY_TTL_SECONDS:
        raise WorkerDiscoveryError(
            "invalid_discovery_ttl",
            f"worker discovery TTL must be 1-{MAX_DISCOVERY_TTL_SECONDS} seconds",
        )
    issued_at = float(time.time() if now is None else now)
    fields: dict[str, Any] = {
        "schema_version": DISCOVERY_SCHEMA_VERSION,
        "kind": DISCOVERY_KIND,
        "service_url": normalize_service_url(service_url),
        "group": group,
        "port": port,
        "issued_at": round(issued_at, 3),
        "expires_at": round(issued_at + ttl_seconds, 3),
        "nonce": secrets.token_hex(16),
    }
    fields["signature"] = _signature(master_token, fields)
    return fields


def verify_discovery_beacon(
    data: bytes,
    master_token: str,
    *,
    group: str = DEFAULT_DISCOVERY_GROUP,
    port: int = DEFAULT_DISCOVERY_PORT,
    now: float | None = None,
) -> dict[str, Any]:
    _validate_group(group)
    _validate_port(port)
    if not data or len(data) > MAX_DISCOVERY_PACKET_BYTES:
        raise WorkerDiscoveryError(
            "invalid_discovery_packet",
            "worker discovery packet is empty or too large",
        )
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerDiscoveryError(
            "invalid_discovery_packet",
            "worker discovery packet is not UTF-8 JSON",
        ) from error
    if not isinstance(payload, Mapping) or set(payload) != DISCOVERY_FIELDS:
        raise WorkerDiscoveryError(
            "invalid_discovery_packet",
            "worker discovery packet fields are invalid",
        )
    if (
        payload.get("schema_version") != DISCOVERY_SCHEMA_VERSION
        or payload.get("kind") != DISCOVERY_KIND
        or payload.get("group") != group
        or payload.get("port") != port
    ):
        raise WorkerDiscoveryError(
            "invalid_discovery_packet",
            "worker discovery packet identity does not match",
        )
    service_url = normalize_service_url(payload.get("service_url"))
    issued_at = payload.get("issued_at")
    expires_at = payload.get("expires_at")
    nonce = payload.get("nonce")
    signature = payload.get("signature")
    if (
        not isinstance(issued_at, (int, float))
        or isinstance(issued_at, bool)
        or not isinstance(expires_at, (int, float))
        or isinstance(expires_at, bool)
        or not isinstance(nonce, str)
        or len(nonce) != 32
        or not isinstance(signature, str)
        or len(signature) != 64
    ):
        raise WorkerDiscoveryError(
            "invalid_discovery_packet",
            "worker discovery timing, nonce or signature is invalid",
        )
    current = time.time() if now is None else now
    if issued_at > current + DISCOVERY_CLOCK_SKEW_SECONDS:
        raise WorkerDiscoveryError(
            "invalid_discovery_time",
            "worker discovery beacon is issued too far in the future",
        )
    if expires_at < issued_at or expires_at - issued_at > MAX_DISCOVERY_TTL_SECONDS:
        raise WorkerDiscoveryError(
            "invalid_discovery_time",
            "worker discovery beacon lifetime is invalid",
        )
    if expires_at <= current:
        raise WorkerDiscoveryError(
            "expired_discovery_beacon",
            "worker discovery beacon has expired",
        )
    expected = _signature(master_token, payload)
    if not hmac.compare_digest(signature, expected):
        raise WorkerDiscoveryError(
            "invalid_discovery_signature",
            "worker discovery beacon signature is invalid",
        )
    verified = dict(payload)
    verified["service_url"] = service_url
    return verified


def _announcer_socket(group: str) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    return sock


def send_discovery_beacon(
    sock: socket.socket,
    master_token: str,
    service_url: str,
    *,
    group: str = DEFAULT_DISCOVERY_GROUP,
    port: int = DEFAULT_DISCOVERY_PORT,
    ttl_seconds: float = DEFAULT_DISCOVERY_TTL,
) -> dict[str, Any]:
    beacon = build_discovery_beacon(
        master_token,
        service_url,
        group=group,
        port=port,
        ttl_seconds=ttl_seconds,
    )
    data = json.dumps(
        beacon,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    sock.sendto(data, (group, port))
    return beacon


def _discovery_socket(
    group: str,
    port: int,
    *,
    timeout: float,
) -> socket.socket:
    _validate_group(group)
    _validate_port(port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", port))
        membership = struct.pack(
            "4s4s",
            socket.inet_aton(group),
            socket.inet_aton("0.0.0.0"),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.settimeout(max(0.05, timeout))
    except OSError:
        sock.close()
        raise
    if hasattr(socket, "IP_MULTICAST_LOOP"):
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    return sock


def discover_service(
    master_token: str,
    *,
    group: str = DEFAULT_DISCOVERY_GROUP,
    port: int = DEFAULT_DISCOVERY_PORT,
    timeout: float = 15.0,
) -> dict[str, Any]:
    if timeout <= 0:
        raise WorkerDiscoveryError(
            "invalid_discovery_timeout",
            "worker discovery timeout must be positive",
        )
    deadline = time.monotonic() + timeout
    last_error: WorkerDiscoveryError | None = None
    with _discovery_socket(group, port, timeout=min(1.0, timeout)) as sock:
        while time.monotonic() < deadline:
            try:
                data, address = sock.recvfrom(MAX_DISCOVERY_PACKET_BYTES + 1)
            except socket.timeout:
                continue
            try:
                beacon = verify_discovery_beacon(
                    data,
                    master_token,
                    group=group,
                    port=port,
                )
            except WorkerDiscoveryError as error:
                last_error = error
                continue
            beacon["source"] = address[0]
            return beacon
    if last_error is not None:
        raise WorkerDiscoveryError(
            "no_valid_discovery_beacon",
            f"no valid worker discovery beacon found: {last_error.message}",
        )
    raise WorkerDiscoveryError(
        "discovery_timeout",
        "timed out waiting for an authenticated worker discovery beacon",
    )


def fetch_discovery_beacon(
    seed_url: str,
    master_token: str,
    *,
    group: str = DEFAULT_DISCOVERY_GROUP,
    port: int = DEFAULT_DISCOVERY_PORT,
    timeout: float = 10.0,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    """Fetch and verify a signed beacon from a routable unicast seed."""

    seed_url = normalize_discovery_seed_url(seed_url)
    if not master_token:
        raise WorkerDiscoveryError(
            "invalid_discovery_secret",
            "worker discovery requires a non-empty master token",
        )
    if (
        timeout <= 0
        or timeout > MAX_DISCOVERY_SEED_TIMEOUT_SECONDS
    ):
        raise WorkerDiscoveryError(
            "invalid_discovery_timeout",
            "worker discovery seed timeout must be positive and at most "
            f"{MAX_DISCOVERY_SEED_TIMEOUT_SECONDS} seconds",
        )
    handlers: list[urllib.request.BaseHandler] = [
        _RejectDiscoveryRedirect()
    ]
    if ssl_context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ssl_context))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        seed_url,
        headers={"Accept": "application/json"},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise WorkerDiscoveryError(
                    "discovery_seed_http_error",
                    "worker discovery seed returned an invalid HTTP status",
                )
            if response.headers.get_content_type() != "application/json":
                raise WorkerDiscoveryError(
                    "invalid_discovery_seed_response",
                    "worker discovery seed must return application/json",
                )
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError as error:
                    raise WorkerDiscoveryError(
                        "invalid_discovery_seed_response",
                        "worker discovery seed returned an invalid "
                        "Content-Length",
                    ) from error
                if declared_bytes > MAX_DISCOVERY_PACKET_BYTES:
                    raise WorkerDiscoveryError(
                        "invalid_discovery_seed_response",
                        "worker discovery seed response is too large",
                    )
            data = response.read(MAX_DISCOVERY_PACKET_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise WorkerDiscoveryError(
            "discovery_seed_http_error",
            f"worker discovery seed returned HTTP {error.code}",
        ) from error
    except WorkerDiscoveryError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise WorkerDiscoveryError(
            "discovery_seed_unreachable",
            "worker discovery seed is unreachable",
        ) from error
    if len(data) > MAX_DISCOVERY_PACKET_BYTES:
        raise WorkerDiscoveryError(
            "invalid_discovery_seed_response",
            "worker discovery seed response is too large",
        )
    beacon = verify_discovery_beacon(
        data,
        master_token,
        group=group,
        port=port,
    )
    seed_host = urlsplit(seed_url).hostname or ""
    beacon["source"] = seed_host
    beacon["transport"] = "unicast-seed"
    return beacon


class WorkerDiscoveryAnnouncer:
    def __init__(
        self,
        token_provider: Callable[[], str | None],
        service_url: str,
        *,
        group: str = DEFAULT_DISCOVERY_GROUP,
        port: int = DEFAULT_DISCOVERY_PORT,
        interval: float = DEFAULT_DISCOVERY_INTERVAL,
        ttl_seconds: float = DEFAULT_DISCOVERY_TTL,
    ):
        self.token_provider = token_provider
        self.service_url = normalize_service_url(service_url)
        _validate_group(group)
        _validate_port(port)
        if interval <= 0:
            raise WorkerDiscoveryError(
                "invalid_discovery_interval",
                "worker discovery interval must be positive",
            )
        if ttl_seconds <= interval:
            raise WorkerDiscoveryError(
                "invalid_discovery_ttl",
                "worker discovery TTL must be longer than the interval",
            )
        self.group = group
        self.port = port
        self.interval = interval
        self.ttl_seconds = ttl_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    def send_once(self) -> dict[str, Any]:
        token = self.token_provider()
        if not token:
            raise WorkerDiscoveryError(
                "invalid_discovery_secret",
                "worker discovery requires an active API token",
            )
        with _announcer_socket(self.group) as sock:
            beacon = send_discovery_beacon(
                sock,
                token,
                self.service_url,
                group=self.group,
                port=self.port,
                ttl_seconds=self.ttl_seconds,
            )
        self.last_error = None
        return beacon

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.send_once()
            except Exception as error:
                self.last_error = (
                    f"{type(error).__name__}: {str(error)[:500]}"
                )
            self._stop.wait(self.interval)

    def start(self) -> None:
        if self._thread is not None:
            raise WorkerDiscoveryError(
                "discovery_already_started",
                "worker discovery announcer is already running",
            )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="m5-worker-discovery",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval + 1.0))
            self._thread = None
