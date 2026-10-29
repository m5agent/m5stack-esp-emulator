"""Legacy M5Stack deviceCfg partition support.

Classic UIFlow stores the selected WiFi credentials in the ``config``
partition as a length-prefixed JSON document.  This helper only mutates a
partition that has the legacy deviceCfg schema; unrelated firmware layouts
are left byte-for-byte unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from firmware_analysis import (
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    parse_partition_table,
)


LEGACY_DEVICE_CONFIG_KEYS = frozenset(
    {"apikey", "wifi", "wifi-list", "board-name"}
)


class LegacyDeviceConfigError(ValueError):
    """A recognized legacy config cannot be safely updated."""


def _wifi_entry(value: Any) -> list[str] | None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, str) for item in value)
    ):
        return None
    return [value[0], value[1]]


def decode_legacy_device_config(raw: bytes) -> dict[str, Any] | None:
    if len(raw) < 4 or raw[:2] == b"\xff\xff":
        return None
    length = int.from_bytes(raw[:2], "big")
    if length < 2 or length + 3 > len(raw):
        return None
    encoded = raw[: length + 2]
    if sum(encoded) & 0xFF != raw[length + 2]:
        return None
    try:
        value = json.loads(raw[2 : length + 2].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if (
        not isinstance(value, dict)
        or not LEGACY_DEVICE_CONFIG_KEYS.issubset(value)
        or (
            _wifi_entry(value.get("wifi")) is None
            and value.get("wifi") != []
        )
        or not isinstance(value.get("wifi-list"), list)
    ):
        return None
    entries = []
    for item in value["wifi-list"]:
        entry = _wifi_entry(item)
        if entry is None:
            return None
        entries.append(entry)
    return value


def encode_legacy_device_config(
    value: dict[str, Any],
    *,
    size: int,
) -> bytes:
    if size < 4:
        raise LegacyDeviceConfigError("legacy config partition is too small")
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(", ", ": "),
    ).encode("utf-8")
    if len(payload) + 3 > size:
        raise LegacyDeviceConfigError(
            f"legacy config requires {len(payload) + 3} bytes; "
            f"partition has {size}"
        )
    encoded = len(payload).to_bytes(2, "big") + payload
    encoded += bytes([sum(encoded) & 0xFF])
    return encoded + b"\x00" * (size - len(encoded))


def _config_partition(image_path: Path, flash_size: int) -> dict | None:
    with image_path.open("rb") as image:
        image.seek(PARTITION_TABLE_OFFSET)
        table = image.read(PARTITION_TABLE_SIZE)
    if len(table) != PARTITION_TABLE_SIZE:
        return None
    parsed = parse_partition_table(
        table,
        offset=0,
        image_size=flash_size,
    )
    if not parsed["valid"]:
        return None
    matches = [
        partition
        for partition in parsed["partitions"]
        if partition["type"] == 64
        and partition["subtype"] == 64
        and partition["label"] == "config"
    ]
    return dict(matches[0]) if matches else None


def apply_legacy_wifi_config(
    image_path: Path,
    *,
    flash_size: int,
    ssid: str,
    password: str,
) -> dict[str, Any] | None:
    """Select a WiFi network in a recognized legacy deviceCfg partition."""
    partition = _config_partition(image_path, flash_size)
    if partition is None:
        return None
    offset = int(partition["offset"])
    size = int(partition["size"])
    with image_path.open("r+b") as image:
        image.seek(offset)
        original = image.read(size)
        if len(original) != size:
            return None
        value = decode_legacy_device_config(original)
        if value is None:
            return None
        entries = [
            _wifi_entry(item)
            for item in value["wifi-list"]
        ]
        changed = False
        for entry in entries:
            if entry[0] == ssid and entry[1] != password:
                entry[1] = password
                changed = True
        if not any(entry[0] == ssid for entry in entries):
            entries.append([ssid, password])
            changed = True
        selected = _wifi_entry(value.get("wifi"))
        if selected != [ssid, password]:
            changed = True
        value["wifi"] = [ssid, password]
        value["wifi-list"] = entries
        if not changed:
            return {
                "partition_label": "config",
                "offset": offset,
                "size": size,
                "changed": False,
                "wifi_ssid_sha256": hashlib.sha256(
                    ssid.encode("utf-8")
                ).hexdigest(),
                "password_provided": bool(password),
                "wifi_entries": len(entries),
            }
        encoded = encode_legacy_device_config(value, size=size)
        image.seek(offset)
        image.write(encoded)
    return {
        "partition_label": "config",
        "offset": offset,
        "size": size,
        "changed": True,
        "config_sha256": hashlib.sha256(encoded).hexdigest(),
        "wifi_ssid_sha256": hashlib.sha256(
            ssid.encode("utf-8")
        ).hexdigest(),
        "password_provided": bool(password),
        "wifi_entries": len(entries),
    }
