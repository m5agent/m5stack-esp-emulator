"""Lab-station presets for review-sta sessions (#238 follow-up).

Many community applications only join networks they have saved themselves,
and some cannot reach their network code without a mounted SD card. A review
session can ask the Device Service to (a) write the review SSID into the NVS
namespaces that known application families read, and (b) attach a blank FAT32
card. Both are session-local fixtures applied to the isolated Flash/SD copy;
the source firmware is never modified.

A namespace is written only when the application image contains that
namespace name, so unrelated firmware keeps a pristine NVS partition.
"""
from __future__ import annotations

from nvs_image import NvsU8, build_nvs_image

# Saved-network layouts verified against the application source. A layout is
# added only after its exact namespace and key schema are confirmed; generic
# names such as "wifi" or "config" are not guessed.
_LAYOUTS = (
    # CardRadio (fengzeest-cpu/Cardradio src/Net.cpp): Preferences "mp3net",
    # u8 "cnt" plus string pairs "s<i>"/"p<i>", slot 0 most recent.
    ("mp3net", lambda ssid, pw: {"cnt": NvsU8(1), "s0": ssid, "p0": pw}),
)
MAX_SSID = 32


def matching_namespaces(image: bytes) -> list[str]:
    """Namespaces from the known layouts whose name appears as a C string."""
    found = []
    for name, _ in _LAYOUTS:
        if b"\x00" + name.encode() + b"\x00" in image:
            found.append(name)
    return found


def build_station_nvs(partition_size: int, image: bytes, *, ssid: str, password: str) -> tuple[bytes, list[str]] | None:
    if not 1 <= len(ssid.encode()) <= MAX_SSID:
        raise ValueError("preset SSID must be 1-32 bytes")
    namespaces = {}
    for name, builder in _LAYOUTS:
        if name in matching_namespaces(image):
            namespaces[name] = builder(ssid, password)
    if not namespaces:
        return None
    return build_nvs_image(partition_size, namespaces), sorted(namespaces)
