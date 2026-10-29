"""Small stateless parsers shared by Device Service request handling."""
from __future__ import annotations

from typing import Any

from device_service_errors import ServiceError


def parse_int(value: Any, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise ServiceError(
        "invalid_request",
        f"{field} must be an integer",
        400,
    )


def parse_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return None


def parse_capture_pcap(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ServiceError(
            "invalid_network",
            "network.capture_pcap must be a boolean",
            400,
        )
    return value


def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        char in "0123456789abcdef"
        for char in value
    )


_is_sha256 = is_sha256
