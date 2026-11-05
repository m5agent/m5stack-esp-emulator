"""Narrow tokenless Preview access for an explicitly loopback-bound service.

This is not authentication for remote clients or a policy for other Device APIs.
Configured current/previous Bearer credentials are checked by serve.Handler
before this fallback is considered. Forwarded/proxy headers are never trusted.
"""
from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit


def _loopback_ip(value: object) -> bool:
    if not isinstance(value, str) or "%" in value:
        return False
    try:
        address = ip_address(value)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def _authority(value: object, default_port: int) -> tuple[str, int] | None:
    if not isinstance(value, str) or not value or not value.isascii():
        return None
    if any(ord(char) <= 32 or ord(char) == 127 or char in "/\\?#,@" for char in value):
        return None
    try:
        parsed = urlsplit("//" + value)
        host, port = parsed.hostname, parsed.port
    except ValueError:
        return None
    if (not host or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        return None
    if host != "localhost" and not _loopback_ip(host):
        return None
    return host, default_port if port is None else port


def tokenless_preview_local_control(*, server_address, client_address, headers,
                                   method: str, secure: bool) -> bool:
    """Check actual socket locality and browser request context, without DNS.

    Same-origin browser GETs often omit Origin. Non-browser local CLI requests
    can omit both Origin and Fetch Metadata. Missing Origin combined with
    browser metadata must positively identify same-origin, or a safe direct
    navigation. A browser Origin, when present, must always match exactly.
    """
    if (not isinstance(server_address, tuple) or len(server_address) < 2
            or not isinstance(client_address, tuple) or not client_address
            or not _loopback_ip(server_address[0])
            or not _loopback_ip(client_address[0])):
        return False
    hosts = headers.get_all("Host", [])
    origins = headers.get_all("Origin", [])
    sites = headers.get_all("Sec-Fetch-Site", [])
    if len(hosts) != 1 or len(origins) > 1 or len(sites) > 1:
        return False
    default_port = 443 if secure else 80
    authority = _authority(hosts[0], default_port)
    if authority is None or authority[1] != server_address[1]:
        return False
    site = sites[0] if sites else None
    safe = method in {"GET", "HEAD"}
    # same-site includes different ports/origins; it is not local same-origin.
    if site is not None and site != "same-origin" and not (safe and site == "none"):
        return False
    if origins:
        origin = origins[0]
        if (not isinstance(origin, str) or not origin.isascii()
                or any(ord(char) <= 32 or ord(char) == 127 for char in origin)
                or any(char in origin for char in "\\?#")):
            return False
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        if (parsed.scheme != ("https" if secure else "http") or parsed.path
                or parsed.query or parsed.fragment
                or _authority(parsed.netloc, default_port) != authority):
            return False
        return True
    if site == "same-origin" or safe and site == "none":
        return True
    # No browser Fetch Metadata is the explicit local CLI compatibility case.
    # Arbitrary DNS names remain rejected by _authority, including rebinding.
    return not any(name.lower().startswith("sec-fetch-") for name in headers.keys())
