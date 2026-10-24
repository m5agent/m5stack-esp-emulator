#!/usr/bin/env python3
"""Select hot public M5Burner firmware and test it through Device Service.

The tool deliberately performs functional execution through /api/v1 instead of
starting a QEMU or esp-emu process directly. Downloaded binaries and session
evidence stay in ignored cache directories. This produces virtual-device
validation evidence; it must not be labeled as a physical-hardware measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from fetch_firmware import (  # noqa: E402
    DEFAULT_API_BASE,
    resolve_community_firmware,
)
from firmware_analysis import analyze_firmware, expected_chip_id  # noqa: E402


DEFAULT_SERVICE = os.environ.get(
    "M5_DEVICE_SERVICE_URL", "http://device-service:8787"
)
DEFAULT_CACHE = ROOT / "platform" / ".cache" / "user-firmware"
DEFAULT_RESULTS = ROOT / "platform" / ".cache" / "user-firmware-matrix"

# M5Burner models do not map one-to-one to simulator device IDs. StamPLC is
# distributed under Stamp-S3 because the actual controller is the StampS3 core.
BURNER_TARGETS = {
    "atoms3r": ("AtomS3R", "atoms3r"),
    "cardputer-adv": ("Cardputer ADV", "cardputer-adv"),
    "core2": ("Core2", "core2"),
    "cores3": ("CoreS3", "cores3"),
    "nanoc6": ("NanoC6", "nanoc6"),
    "nesso-n1": ("Arduino Nesso N1", "arduino-nesso-n1"),
    "papercolor": ("PaperColor", "paper-color"),
    "papermono": ("PaperMono", "paper-mono"),
    "stackchan": ("StackChan", "stackchan"),
    "stamplc": ("Stamp-S3", "stamp-s3"),
    "sticks3": ("StickS3", "sticks3"),
    "stopwatch": ("StopWatch", "stopwatch"),
    "tab5": ("Tab5", "tab5"),
}

BASELINE_RE = re.compile(r"^\s*UIFlow(?:2(?:\.0)?)?(?:\s|$)", re.IGNORECASE)
ERROR_PATTERNS = (
    re.compile(r"assert failed:", re.IGNORECASE),
    re.compile(r"Guru Meditation", re.IGNORECASE),
    re.compile(r"uru Meditation", re.IGNORECASE),
    re.compile(r"abort\(\) was called", re.IGNORECASE),
    re.compile(r"integer divide by zero", re.IGNORECASE),
    re.compile(r"LoadProhibited|StoreProhibited", re.IGNORECASE),
    re.compile(r"panic'ed", re.IGNORECASE),
    re.compile(r"Rebooting\.\.\.", re.IGNORECASE),
    re.compile(r"invalid header: 0x", re.IGNORECASE),
    re.compile(r"Invalid chip id", re.IGNORECASE),
    re.compile(r"LittleFS is Full", re.IGNORECASE),
    re.compile(r"Task watchdog got triggered", re.IGNORECASE),
    re.compile(r"task_wdt: Task watchdog", re.IGNORECASE),
    re.compile(r"Using PSRAM must when cache is enabled", re.IGNORECASE),
    re.compile(r"xTaskPriorityDisinherit", re.IGNORECASE),
)
EXPECTATION_MODES = {"ui-interactive", "headless-serial", "network-first"}
EXPECTATION_RUNTIMES = {"qemu", "qemu-wifi", "qemu-unified"}
EXPECTATION_NETWORK_KEYS = {
    "profile",
    "net_mode",
    "wifi_ssid",
    "wifi_auth",
    "wifi_password_env",
    "attempts",
    "capture_pcap",
    "expected_markers",
    "policy",
}
EXPECTATION_KEYS = {
    "device_id",
    "firmware_id",
    "sha256",
    "mode",
    "runtime",
    "description",
    "ready_marker",
    "required_markers",
    "forbidden_markers",
    "require_frame",
    "require_input_response",
    "require_network",
    "network",
    "network_observe_seconds",
    "nvs",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


class MatrixError(RuntimeError):
    pass


class HttpError(MatrixError):
    def __init__(self, message: str, *, status: int, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def normalize(value: Any) -> str:
    return " ".join(
        str(value or "").replace("_", " ").replace("-", " ").split()
    ).casefold()


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_string_list(
    value: Any,
    *,
    field: str,
    limit: int = 16,
    allow_empty: bool = True,
) -> list[str]:
    if value is None:
        value = []
    if not isinstance(value, list) or len(value) > limit:
        raise MatrixError(f"{field} must be a list with at most {limit} entries")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not 1 <= len(item) <= 200:
            raise MatrixError(f"{field} entries must be 1-200 character strings")
        if item in result:
            raise MatrixError(f"{field} contains duplicate marker {item!r}")
        result.append(item)
    if not allow_empty and not result:
        raise MatrixError(f"{field} must not be empty")
    return result


def _expectation_key(device_id: str, firmware_id: str, sha256: str) -> str:
    return f"{device_id}:{firmware_id}:{sha256}"


def _expectation_pair(device_id: str, firmware_id: str) -> str:
    return f"{device_id}:{firmware_id}"


def load_execution_expectations(path: Path | None) -> dict[str, Any] | None:
    """Load SHA-bound review intent without putting it into FirmwareManifest."""

    if path is None:
        return None
    path = path.resolve()
    if not path.is_file():
        raise MatrixError(f"expectation file does not exist: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatrixError(f"invalid expectation JSON: {error}") from error
    if not isinstance(document, Mapping):
        raise MatrixError("expectation document must be an object")
    unknown_top = sorted(set(document) - {"schema_version", "expectations"})
    if unknown_top:
        raise MatrixError(
            "unsupported expectation document fields: "
            + ", ".join(unknown_top)
        )
    if document.get("schema_version") != 1:
        raise MatrixError("expectation schema_version must be 1")
    raw_expectations = document.get("expectations")
    if not isinstance(raw_expectations, list) or not 1 <= len(raw_expectations) <= 512:
        raise MatrixError(
            "expectations must contain 1-512 entries"
        )

    by_key: dict[str, dict[str, Any]] = {}
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for index, raw in enumerate(raw_expectations):
        prefix = f"expectations[{index}]"
        if not isinstance(raw, Mapping):
            raise MatrixError(f"{prefix} must be an object")
        unknown = sorted(set(raw) - EXPECTATION_KEYS)
        if unknown:
            raise MatrixError(
                f"{prefix} has unsupported fields: {', '.join(unknown)}"
            )
        device_id = raw.get("device_id")
        firmware_id = raw.get("firmware_id")
        sha256 = str(raw.get("sha256") or "").lower()
        if not isinstance(device_id, str) or not device_id:
            raise MatrixError(f"{prefix}.device_id is invalid")
        if not isinstance(firmware_id, str) or not firmware_id:
            raise MatrixError(f"{prefix}.firmware_id is invalid")
        if not SHA256_RE.fullmatch(sha256):
            raise MatrixError(f"{prefix}.sha256 is invalid")
        mode = str(raw.get("mode") or "ui-interactive")
        if mode not in EXPECTATION_MODES:
            raise MatrixError(f"{prefix}.mode is unsupported: {mode!r}")
        runtime = str(raw.get("runtime") or "qemu")
        if runtime not in EXPECTATION_RUNTIMES:
            raise MatrixError(f"{prefix}.runtime is unsupported: {runtime!r}")
        if mode == "network-first" and runtime not in {
            "qemu-wifi",
            "qemu-unified",
        }:
            raise MatrixError(
                f"{prefix}.runtime must be qemu-wifi or qemu-unified "
                "for network-first"
            )

        required_markers = bounded_string_list(
            raw.get("required_markers"),
            field=f"{prefix}.required_markers",
            allow_empty=mode == "ui-interactive",
        )
        forbidden_markers = bounded_string_list(
            raw.get("forbidden_markers"),
            field=f"{prefix}.forbidden_markers",
        )
        overlap = sorted(set(required_markers) & set(forbidden_markers))
        if overlap:
            raise MatrixError(
                f"{prefix} markers are both required and forbidden: "
                + ", ".join(overlap)
            )
        ready_marker = raw.get("ready_marker")
        if ready_marker is not None and (
            not isinstance(ready_marker, str) or not 1 <= len(ready_marker) <= 200
        ):
            raise MatrixError(f"{prefix}.ready_marker is invalid")
        require_frame_default = mode == "ui-interactive"
        require_input_default = mode == "ui-interactive"
        require_network_default = mode == "network-first"
        require_frame = raw.get("require_frame", require_frame_default)
        require_input = raw.get(
            "require_input_response",
            require_input_default,
        )
        require_network = raw.get("require_network", require_network_default)
        if not all(
            isinstance(value, bool)
            for value in (require_frame, require_input, require_network)
        ):
            raise MatrixError(
                f"{prefix} require_frame/require_input_response/"
                "require_network must be booleans"
            )
        if mode == "ui-interactive" and (
            not require_frame or not require_input
        ):
            raise MatrixError(
                f"{prefix} ui-interactive requires frame and input response"
            )
        if mode == "network-first" and not require_network:
            raise MatrixError(
                f"{prefix} network-first requires network status validation"
            )
        observe_seconds = raw.get("network_observe_seconds", 8)
        if (
            not isinstance(observe_seconds, int)
            or not 0 <= observe_seconds <= 120
        ):
            raise MatrixError(
                f"{prefix}.network_observe_seconds must be 0-120"
            )

        network = raw.get("network")
        password_env: str | None = None
        if network is not None and not isinstance(network, Mapping):
            raise MatrixError(f"{prefix}.network must be an object")
        if mode == "network-first" and not isinstance(network, Mapping):
            raise MatrixError(f"{prefix}.network is required for network-first")
        if isinstance(network, Mapping):
            network = dict(network)
            if "wifi_password" in network:
                raise MatrixError(
                    f"{prefix}.network.wifi_password is not allowed; "
                    "use wifi_password_env"
                )
            unknown_network = sorted(set(network) - EXPECTATION_NETWORK_KEYS)
            if unknown_network:
                raise MatrixError(
                    f"{prefix}.network has unsupported fields: "
                    + ", ".join(unknown_network)
                )
            password_env = network.pop("wifi_password_env", None)
            if password_env is not None and (
                not isinstance(password_env, str)
                or not ENV_NAME_RE.fullmatch(password_env)
            ):
                raise MatrixError(
                    f"{prefix}.network.wifi_password_env is invalid"
                )
            if "expected_markers" not in network and required_markers:
                network["expected_markers"] = required_markers
            elif "expected_markers" in network:
                network["expected_markers"] = bounded_string_list(
                    network["expected_markers"],
                    field=f"{prefix}.network.expected_markers",
                )
            if "capture_pcap" not in network:
                network["capture_pcap"] = True
            elif not isinstance(network["capture_pcap"], bool):
                raise MatrixError(
                    f"{prefix}.network.capture_pcap must be a boolean"
                )
            if "profile" in network and (
                not isinstance(network["profile"], str)
                or not 1 <= len(network["profile"]) <= 64
            ):
                raise MatrixError(f"{prefix}.network.profile is invalid")
            if "net_mode" in network and network["net_mode"] not in {
                "user",
                "user,restrict=yes",
            }:
                raise MatrixError(f"{prefix}.network.net_mode is invalid")
            if "wifi_ssid" in network and (
                not isinstance(network["wifi_ssid"], str)
                or not 1 <= len(network["wifi_ssid"]) <= 32
            ):
                raise MatrixError(f"{prefix}.network.wifi_ssid is invalid")
            if "wifi_auth" in network and network["wifi_auth"] not in {
                "open",
                "wpa2-psk",
                "wpa2-wpa3",
                "wpa3-sae",
            }:
                raise MatrixError(f"{prefix}.network.wifi_auth is invalid")
            if "attempts" in network and (
                not isinstance(network["attempts"], int)
                or not 1 <= network["attempts"] <= 10
            ):
                raise MatrixError(
                    f"{prefix}.network.attempts must be 1-10"
                )
            if "policy" in network and not isinstance(
                network["policy"],
                Mapping,
            ):
                raise MatrixError(f"{prefix}.network.policy must be an object")
            network_bytes = json.dumps(
                network,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(network_bytes) > 16 * 1024:
                raise MatrixError(f"{prefix}.network is too large")
        elif mode != "network-first":
            network = None

        nvs = raw.get("nvs")
        nvs_private: dict[str, Any] | None = None
        if nvs is not None:
            if not isinstance(nvs, Mapping):
                raise MatrixError(f"{prefix}.nvs must be an object")
            unknown_nvs = sorted(set(nvs) - {"partition_label", "image_path"})
            if unknown_nvs:
                raise MatrixError(
                    f"{prefix}.nvs has unsupported fields: "
                    + ", ".join(unknown_nvs)
                )
            partition_label = nvs.get("partition_label", "nvs")
            image_path = nvs.get("image_path")
            if (
                not isinstance(partition_label, str)
                or not 1 <= len(partition_label) <= 16
            ):
                raise MatrixError(f"{prefix}.nvs.partition_label is invalid")
            if not isinstance(image_path, str) or not image_path:
                raise MatrixError(f"{prefix}.nvs.image_path is invalid")
            resolved_image = Path(image_path)
            if not resolved_image.is_absolute():
                resolved_image = path.parent / resolved_image
            resolved_image = resolved_image.resolve()
            if not resolved_image.is_file():
                raise MatrixError(
                    f"{prefix}.nvs image does not exist: {resolved_image}"
                )
            size = resolved_image.stat().st_size
            if size <= 0 or size > 32 * 1024 * 1024:
                raise MatrixError(
                    f"{prefix}.nvs image must be 1 byte to 32 MiB"
                )
            nvs_private = {
                "partition_label": partition_label,
                "image_path": str(resolved_image),
                "sha256": file_sha256(resolved_image),
                "bytes": size,
            }

        normalized = {
            "device_id": device_id,
            "firmware_id": firmware_id,
            "sha256": sha256,
            "mode": mode,
            "runtime": runtime,
            "required_markers": required_markers,
            "forbidden_markers": forbidden_markers,
            "ready_marker": ready_marker,
            "require_frame": require_frame,
            "require_input_response": require_input,
            "require_network": require_network,
            "network_observe_seconds": observe_seconds,
            "network": network,
            "network_public": (
                {
                    key: value
                    for key, value in network.items()
                    if key != "wifi_password"
                }
                if isinstance(network, Mapping)
                else None
            ),
            "nvs": (
                {
                    "partition_label": nvs_private["partition_label"],
                    "sha256": nvs_private["sha256"],
                    "bytes": nvs_private["bytes"],
                }
                if nvs_private
                else None
            ),
        }
        if raw.get("description") is not None:
            description = raw["description"]
            if not isinstance(description, str) or len(description) > 1000:
                raise MatrixError(f"{prefix}.description is invalid")
            normalized["description"] = description
        normalized["expectation_sha256"] = canonical_json_sha256(normalized)
        if nvs_private:
            normalized["_nvs"] = nvs_private
        if password_env:
            normalized["_wifi_password_env"] = password_env
        key = _expectation_key(device_id, firmware_id, sha256)
        if key in by_key:
            raise MatrixError(f"duplicate expectation for {key}")
        by_key[key] = normalized
        by_pair.setdefault(
            _expectation_pair(device_id, firmware_id),
            [],
        ).append(normalized)
    return {
        "schema_version": 1,
        "source_sha256": file_sha256(path),
        "by_key": by_key,
        "by_pair": by_pair,
    }


def apply_execution_expectations(
    samples: list[dict[str, Any]],
    expectations: dict[str, Any] | None,
) -> None:
    if expectations is None:
        return
    by_key = expectations["by_key"]
    by_pair = expectations["by_pair"]
    for sample in samples:
        device_id = str(sample.get("device_id") or "")
        firmware_id = str(sample.get("firmware_id") or "")
        sha256 = str(sample.get("sha256") or "").lower()
        key = _expectation_key(device_id, firmware_id, sha256)
        expectation = by_key.get(key)
        if expectation is None and by_pair.get(
            _expectation_pair(device_id, firmware_id)
        ):
            raise MatrixError(
                "expectation firmware SHA mismatch for "
                f"{device_id}/{firmware_id}: selected={sha256}"
            )
        if expectation is None:
            continue
        sample["review_expectation"] = {
            key: value
            for key, value in expectation.items()
            if not key.startswith("_") and key != "network_public"
        }
        sample["_review_expectation_private"] = expectation
        sample["expectation_file_sha256"] = expectations["source_sha256"]


def public_review_expectation(expectation: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if expectation is None:
        return None
    public = {
        key: value
        for key, value in expectation.items()
        if not key.startswith("_") and key != "network_public"
    }
    public["network"] = expectation.get("network_public")
    return public


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 90,
) -> tuple[bytes, Mapping[str, str]]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "m5stack-user-firmware-matrix/1",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = raw.decode("utf-8", errors="replace")[:2000]
        message = f"HTTP {error.code} for {url}"
        if isinstance(payload, Mapping):
            detail = payload.get("error", payload)
            if isinstance(detail, Mapping):
                message = str(detail.get("message") or detail.get("msg") or message)
        raise HttpError(message, status=error.code, payload=payload) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise MatrixError(f"request failed for {url}: {error}") from error


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Any = None,
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 90,
) -> Any:
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    raw, _ = request_bytes(
        url,
        method=method,
        body=body,
        headers=request_headers,
        timeout=timeout,
    )
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MatrixError(f"invalid JSON from {url}") from error


def burner_devices(base_url: str) -> list[Mapping[str, Any]]:
    payload = request_json(f"{base_url.rstrip('/')}/api/v1/devices")
    if not isinstance(payload, Mapping) or payload.get("code") != 200:
        raise MatrixError(f"M5Burner device query failed: {payload!r}")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MatrixError("M5Burner device response has no data list")
    return [row for row in rows if isinstance(row, Mapping)]


def burner_search(
    base_url: str,
    *,
    device_id: str,
    page_size: int,
) -> list[Mapping[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "deviceId": device_id,
            "sort": "MOST_DOWNLOADED",
            "pageNum": 1,
            "pageSize": page_size,
        }
    )
    payload = request_json(
        f"{base_url.rstrip('/')}/api/v1/firmwares?{query}"
    )
    if not isinstance(payload, Mapping) or payload.get("code") != 200:
        raise MatrixError(f"M5Burner firmware query failed: {payload!r}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise MatrixError("M5Burner firmware response has no rows list")
    return [row for row in rows if isinstance(row, Mapping)]


def baseline_name(name: str) -> bool:
    return bool(BASELINE_RE.match(name))


def png_metrics(data: bytes) -> dict[str, int]:
    """Decode common non-interlaced RGB/RGBA PNGs using the stdlib."""

    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise MatrixError("frame is not a PNG")
    offset = 8
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if interlace:
                raise MatrixError("interlaced PNG is unsupported")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None or bit_depth != 8:
        raise MatrixError("unsupported PNG header")
    channels = {2: 3, 6: 4}.get(color_type)
    if channels is None:
        raise MatrixError("unsupported PNG color type")
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    if len(raw) != (stride + 1) * height:
        raise MatrixError("unexpected PNG data length")
    previous = bytearray(stride)
    nonblack = 0
    unique: set[bytes] = set()
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                estimate = left + up - upper_left
                pa = abs(estimate - left)
                pb = abs(estimate - up)
                pc = abs(estimate - upper_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                row[index] = (row[index] + predictor) & 0xFF
            elif filter_type != 0:
                raise MatrixError(f"unsupported PNG filter {filter_type}")
        for pixel in range(0, stride, channels):
            rgb = bytes(row[pixel : pixel + 3])
            if any(rgb):
                nonblack += 1
                if len(unique) < 512:
                    unique.add(rgb)
        previous = row
    return {
        "width": int(width),
        "height": int(height),
        "nonblack_pixels": nonblack,
        "unique_colors": len(unique),
    }


def download_candidates(
    *,
    device_id: str,
    target_name: str,
    target_slug: str,
    base_url: str,
    cache_dir: Path,
    candidate_limit: int,
    sample_limit: int,
    device_soc: str,
) -> dict[str, Any]:
    devices = burner_devices(base_url)
    target = next(
        (row for row in devices if normalize(row.get("deviceName")) == normalize(target_name)),
        None,
    )
    if target is None:
        raise MatrixError(f"M5Burner device not found: {target_name}")
    target_id = str(target.get("deviceId") or "")
    if not target_id:
        raise MatrixError(f"M5Burner device has no ID: {target_name}")
    rows = burner_search(base_url, device_id=target_id, page_size=candidate_limit)
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    baseline_rows: list[Mapping[str, Any]] = []

    def consider(row: Mapping[str, Any], *, fill: bool = False) -> None:
        if len(selected) >= sample_limit:
            return
        firmware_id = str(row.get("firmwareId") or "")
        name = str(row.get("firmwareName") or firmware_id)
        version = row.get("currentVersion")
        version_name = (
            str(version.get("versionName") or "")
            if isinstance(version, Mapping)
            else ""
        )
        if not firmware_id:
            skipped.append({"firmware_id": firmware_id, "name": name, "reason": "missing ID"})
            return
        if not fill and baseline_name(name):
            baseline_rows.append(row)
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": "baseline UIFlow2 excluded while alternatives remain",
                }
            )
            return
        if device_id == "stamplc" and "stamplc" not in normalize(name):
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": "generic Stamp-S3 image is not StamPLC-specific",
                }
            )
            return
        destination = cache_dir / device_id / f"{firmware_id}.bin"
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = resolve_community_firmware(
                firmware_id,
                destination,
                api_base=base_url,
                device_slug=target_slug or None,
                # Public CDN objects may change under one firmware/version ID.
                # A review matrix must bind the artifact fetched for this run.
                force=True,
                analyze=False,
                expected_chip_id_value=None,
            )
            analysis = analyze_firmware(
                destination,
                expected_chip_id_value=expected_chip_id(device_soc),
            )
        except Exception as error:
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": f"download/static analysis failed: {error}",
                }
            )
            return
        if not analysis.get("valid"):
            skipped.append(
                {
                    "firmware_id": firmware_id,
                    "name": name,
                    "reason": "static image incompatible",
                    "errors": analysis.get("errors", []),
                    "warnings": analysis.get("warnings", []),
                }
            )
            return
        selected.append(
            {
                "device_id": device_id,
                "device_soc": device_soc,
                "burner_device_name": target_name,
                "burner_device_slug": target_slug,
                "firmware_id": firmware_id,
                "name": name,
                "version": version_name,
                "source": row.get("sourceType"),
                "developer": (
                    row.get("developer", {}).get("nickname")
                    if isinstance(row.get("developer"), Mapping)
                    else None
                ),
                "downloads": (
                    row.get("statistics", {}).get("downloadCount")
                    if isinstance(row.get("statistics"), Mapping)
                    else None
                ),
                "published": (
                    version.get("publishTime")
                    if isinstance(version, Mapping)
                    else None
                ),
                "path": str(destination),
                "bytes": result["bytes"],
                "sha256": result["sha256"],
                "url": result["url"],
                "metadata": result,
                "static_analysis": analysis,
                "rank": len(selected) + 1,
            }
        )

    for row in rows:
        consider(row)
        if len(selected) >= sample_limit:
            break
    if len(selected) < sample_limit:
        for row in baseline_rows:
            consider(row, fill=True)
            if len(selected) >= sample_limit:
                break
    return {
        "device_id": device_id,
        "target_name": target_name,
        "target_slug": target_slug,
        "target_id": target_id,
        "selected": selected,
        "skipped": skipped,
        "coverage": "complete" if len(selected) >= sample_limit else "shortfall",
    }


def refresh_selected_sample(
    sample: Mapping[str, Any],
    *,
    base_url: str,
    cache_dir: Path,
    device_soc: str,
) -> dict[str, Any]:
    device_id = str(sample.get("device_id") or "")
    firmware_id = str(sample.get("firmware_id") or "")
    target_slug = str(sample.get("burner_device_slug") or "")
    if not device_id or not firmware_id or not target_slug:
        raise MatrixError("resume sample lacks device, firmware or target slug")
    destination = cache_dir / device_id / f"{firmware_id}.bin"
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = resolve_community_firmware(
        firmware_id,
        destination,
        api_base=base_url,
        device_slug=target_slug,
        force=True,
        analyze=False,
        expected_chip_id_value=None,
    )
    analysis = analyze_firmware(
        destination,
        expected_chip_id_value=expected_chip_id(device_soc),
    )
    if not analysis.get("valid"):
        raise MatrixError(
            "refreshed static image is incompatible: "
            + ", ".join(analysis.get("errors", []))
        )
    refreshed = dict(sample)
    refreshed.update(
        {
            "path": str(destination),
            "bytes": result["bytes"],
            "sha256": result["sha256"],
            "url": result["url"],
            "metadata": result,
            "static_analysis": analysis,
            "refreshed_at": utc_now(),
        }
    )
    return refreshed


def sample_result_key(sample: Mapping[str, Any]) -> str:
    parts = [
        str(sample.get("device_id") or ""),
        str(sample.get("firmware_id") or ""),
        str(sample.get("sha256") or ""),
    ]
    storage = sample.get("storage_fixture")
    if isinstance(storage, Mapping) and storage.get("sha256"):
        parts.append(f"sd={storage['sha256']}")
    expectation = sample.get("review_expectation")
    if isinstance(expectation, Mapping) and expectation.get("expectation_sha256"):
        parts.append(f"expectation={expectation['expectation_sha256']}")
    return ":".join(parts)


class ServiceClient:
    def __init__(self, base_url: str, timeout: float = 90):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/{path.lstrip('/')}"

    def get(self, path: str) -> Any:
        return request_json(self.url(path), timeout=self.timeout)

    def post(
        self,
        path: str,
        payload: Any = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return request_json(
            self.url(path),
            method="POST",
            payload={} if payload is None else payload,
            timeout=self.timeout if timeout is None else timeout,
        )

    def delete(self, path: str) -> Any:
        return request_json(
            self.url(path),
            method="DELETE",
            timeout=self.timeout,
        )

    def upload(self, path: Path, name: str) -> Any:
        return request_json(
            self.url("artifacts"),
            method="POST",
            body=path.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": name,
            },
            timeout=180,
        )

    def frame(self, session_id: str, destination: Path) -> tuple[bytes, Mapping[str, str]]:
        data, headers = request_bytes(
            self.url(f"sessions/{session_id}/frame.png"),
            headers={"Accept": "image/png"},
            timeout=max(self.timeout, 60),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return data, headers


def error_lines(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in ERROR_PATTERNS):
            compact = " ".join(line.replace("\x00", "").split())
            if compact and compact not in found:
                found.append(compact[:500])
            if len(found) >= 20:
                break
    return found


def inputs_for_device(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    display = device.get("display")
    if isinstance(display, Mapping) and display.get("touch"):
        width = int(display.get("width") or 320)
        height = int(display.get("height") or 240)
        return [
            {
                "kind": "touch",
                "x": max(1, width // 2),
                "y": max(1, height // 2),
                "settle_seconds": 0.8,
            },
            {
                "kind": "touch",
                "x": max(1, width // 4),
                "y": max(1, height // 2),
                "settle_seconds": 0.8,
            },
            {
                "kind": "touch",
                "x": max(1, (width * 3) // 4),
                "y": max(1, height // 2),
                "settle_seconds": 0.8,
            },
            {"kind": "key", "key": "a", "settle_seconds": 0.8},
            {"kind": "key", "key": "ret", "settle_seconds": 0.8},
        ]
    return [
        {"kind": "key", "key": "a", "settle_seconds": 0.8},
        {"kind": "key", "key": "ret", "settle_seconds": 0.8},
    ]


def detect_runtime_model_gaps(
    serial: str,
    device_id: str | None = None,
) -> list[dict[str, str]]:
    """Identify stable runtime signatures caused by unmodeled device features."""

    gaps: list[dict[str, str]] = []
    if "Zigbee_main" in serial and re.search(
        r"task_wdt: Task watchdog got triggered",
        serial,
        re.IGNORECASE,
    ):
        gaps.append(
            {
                "code": "zigbee_runtime_not_modeled",
                "detail": (
                    "Zigbee_main repeatedly blocked while the current C6 "
                    "profile has no Zigbee radio/controller model"
                ),
            }
        )
    if "LP_SW_HPSYS" in serial and re.search(
        r"Invalid chip id\. Expected 13 read 12",
        serial,
    ):
        gaps.append(
            {
                "code": "c6_chip_id_lost_after_software_reset",
                "detail": (
                    "the first boot entered the ESP32-C6 ROM, but a later "
                    "LP_SW_HPSYS reset reported chip id 12 instead of 13"
                ),
            }
        )
    if device_id == "core2":
        if (
            (
                "pmic_axp" in serial
                or "M5Core2 initializing" in serial
            )
            and (
                "i2cRead returned Error -1" in serial
                or "OSError: I2C bus error (19)" in serial
            )
        ):
            gaps.append(
                {
                    "code": "core2_pmic_i2c_model_gap",
                    "detail": (
                        "official Core2 firmware reached PMIC discovery but "
                        "failed an AXP192/AXP2101 register transaction"
                    ),
                }
            )
        if (
            "ATECC608" in serial
            and "Core2forAWS" in serial
            and "abort() was called" in serial
        ):
            gaps.append(
                {
                    "code": "core2_aws_atecc608_model_gap",
                    "detail": (
                        "Core2 for AWS firmware aborted after the unmodeled "
                        "ATECC608 secure element failed initialization"
                    ),
                }
            )
    if device_id == "papermono":
        sd_init_failures = re.findall(
            r"sdmmc_init_ocr: send_op_cond \(1\) returned 0x107",
            serial,
            re.IGNORECASE,
        )
        if len(sd_init_failures) >= 3:
            gaps.append(
                {
                    "code": "papermono_sd_fixture_unavailable",
                    "category": "fixture",
                    "detail": (
                        "the generic Device Service session has no attached "
                        "initialized SD-card fixture; repeated SDMMC OCR "
                        "initialization failed and the firmware rendered an "
                        "SD card error page"
                    ),
                }
            )
    return gaps


def classify_result(
    *,
    has_screenshot: bool,
    nonblack: int,
    running: bool,
    crash: bool,
    serial_bytes: int,
    boot_error: str | None,
    input_observed: bool,
    runtime_model_gaps: list[dict[str, str]] | None = None,
    review_expectation: Mapping[str, Any] | None = None,
    required_markers_observed: bool = True,
    forbidden_markers_observed: bool = False,
    network_observed: bool | None = None,
) -> tuple[str, str, list[str]]:
    """Classify runtime evidence without conflating firmware and model gaps."""

    if boot_error:
        return (
            "PARTIAL",
            "device_service_startup_failed",
            [f"runtime_startup: {boot_error}"],
        )
    if runtime_model_gaps:
        fixture_gap = any(
            gap.get("category") == "fixture"
            for gap in runtime_model_gaps
        )
        return (
            "PARTIAL",
            "runtime_fixture_gap" if fixture_gap else "runtime_model_gap",
            [
                (
                    "device_fixture: "
                    if gap.get("category") == "fixture"
                    else "device_model: "
                )
                + f"{gap['code']}: {gap['detail']}"
                for gap in runtime_model_gaps
            ],
        )
    mode = str((review_expectation or {}).get("mode") or "ui-interactive")
    if mode != "ui-interactive":
        if not required_markers_observed:
            return (
                "PARTIAL",
                "expected_runtime_marker_missing",
                ["expectation: one or more required serial markers were absent"],
            )
        if forbidden_markers_observed:
            return (
                "FAIL",
                "forbidden_runtime_marker_observed",
                ["expectation: a forbidden serial marker was observed"],
            )
        if (
            review_expectation
            and review_expectation.get("require_network")
            and network_observed is not True
        ):
            return (
                "PARTIAL",
                "network_expectation_not_met",
                ["network: expected network status PASS was not observed"],
            )
        if serial_bytes <= 0:
            return (
                "FAIL",
                "expected_runtime_serial_missing",
                ["serial: no boot or application output"],
            )
        if crash:
            return (
                "PARTIAL",
                "fatal_expected_runtime",
                ["runtime: fatal serial signature"],
            )
        if not running:
            return (
                "FAIL",
                "expected_runtime_not_running",
                ["runtime: session did not remain running"],
            )
        return "PASS", f"{mode}_expectation_ok", []
    if has_screenshot:
        if nonblack < 16:
            if crash or not running:
                return (
                    "FAIL",
                    "fatal_before_application_frame",
                    [
                        "application_frame: no non-blank frame",
                        "runtime:" + (" fatal serial signature" if crash else " not running"),
                    ],
                )
            return (
                "PARTIAL",
                "application_frame_not_ready",
                ["application_frame: no non-blank frame"],
            )
        if crash:
            return (
                "PARTIAL",
                "fatal_after_application_frame",
                ["runtime: fatal serial signature after frame capture"],
            )
        if not running:
            return (
                "PARTIAL",
                "session_not_running_after_frame",
                ["runtime: session did not remain running"],
            )
        if not input_observed:
            return (
                "PARTIAL",
                "no_observable_input_response",
                ["input: no frame change or serial response after probes"],
            )
        return "PASS", "application_frame_and_runtime_ok", []
    if serial_bytes <= 0:
        return "FAIL", "serial_not_ready", ["serial: no boot or application output"]
    if crash or not running:
        return (
            "FAIL",
            "fatal_without_display",
            [
                "runtime:" + (" fatal serial signature" if crash else " not running"),
                "display: device profile has no display",
            ],
        )
    return (
        "PARTIAL",
        "serial_only_device",
        ["display: device profile has no display; frame validation is not applicable"],
    )


def evaluate_network_expectation(
    network: Mapping[str, Any] | None,
    *,
    require_capture: bool,
) -> dict[str, Any]:
    document = network if isinstance(network, Mapping) else {}
    capture = document.get("packet_capture")
    capture = capture if isinstance(capture, Mapping) else {}
    capture_input = capture.get("input")
    capture_input = (
        capture_input if isinstance(capture_input, Mapping) else {}
    )
    pcap_observed = bool(
        capture.get("status") == "PASS"
        and capture_input.get("sha256")
    )
    status_observed = document.get("status") == "PASS"
    return {
        "network_status": document.get("status"),
        "pcap_required": require_capture,
        "pcap_observed": pcap_observed,
        "observed": status_observed
        and (not require_capture or pcap_observed),
    }


def wait_until_running(
    client: ServiceClient,
    session_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = client.get(f"sessions/{session_id}")
        if last.get("state") == "running":
            return last
        if last.get("state") in {"failed", "stopped"}:
            return last
        time.sleep(0.3)
    return last


def prepare_review_runtime(
    client: ServiceClient,
    sample: Mapping[str, Any],
) -> dict[str, Any]:
    private = sample.get("_review_expectation_private")
    if not isinstance(private, Mapping):
        return {}
    runtime = str(private.get("runtime") or "qemu")
    required_markers = list(private.get("required_markers") or [])
    ready_marker = private.get("ready_marker")
    network = private.get("network")
    if isinstance(network, Mapping):
        network = dict(network)
    else:
        network = None
    if network and not isinstance(ready_marker, str):
        expected = network.get("expected_markers")
        if isinstance(expected, list) and expected:
            ready_marker = expected[0]
    if network and not isinstance(ready_marker, str) and required_markers:
        ready_marker = required_markers[0]
    password_env = private.get("_wifi_password_env")
    if password_env:
        password = os.environ.get(str(password_env))
        if password is None:
            raise MatrixError(
                f"WiFi password environment variable is missing: {password_env}"
            )
        if network is None:
            raise MatrixError("wifi_password_env requires a network object")
        network["wifi_password"] = password
    nvs = private.get("_nvs")
    nvs_fixture = None
    if isinstance(nvs, Mapping):
        path = Path(str(nvs["image_path"]))
        artifact = client.upload(
            path,
            f"{sample['device_id']}-{sample['firmware_id']}-{path.name}",
        )
        if artifact.get("sha256") != nvs.get("sha256"):
            raise MatrixError("uploaded NVS fixture SHA-256 changed")
        nvs_fixture = {
            "partition_label": nvs["partition_label"],
            "artifact_id": artifact["artifact_id"],
            "sha256": artifact["sha256"],
            "bytes": artifact["size"],
        }
    return {
        "runtime": runtime,
        "ready_marker": ready_marker,
        "network": network,
        "network_public": private.get("network_public"),
        "nvs": nvs_fixture,
        "network_observe_seconds": int(
            private.get("network_observe_seconds") or 0
        ),
    }


def execute_sample(
    sample: Mapping[str, Any],
    *,
    client: ServiceClient,
    device: Mapping[str, Any],
    out_dir: Path,
    observe_seconds: float,
    settle_seconds: float,
    storage_fixture: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    firmware_path = Path(str(sample["path"]))
    has_screenshot = bool(device.get("features", {}).get("screenshot"))
    review_expectation = sample.get("review_expectation")
    review_expectation = (
        dict(review_expectation)
        if isinstance(review_expectation, Mapping)
        else None
    )
    expectation_mode = str(
        (review_expectation or {}).get("mode") or "ui-interactive"
    )
    capture_frame = has_screenshot and bool(
        (review_expectation or {}).get("require_frame", True)
    )
    capture_input = bool(
        (review_expectation or {}).get("require_input_response", True)
    )
    result: dict[str, Any] = {
        **{
            key: value
            for key, value in sample.items()
            if key not in {"metadata", "static_analysis"}
            and not key.startswith("_")
        },
        "started_at": utc_now(),
        "scope": "simulation-only-not-hardware-validation",
        "session_id": None,
        "review_expectation": public_review_expectation(
            sample.get("_review_expectation_private")
        ),
    }
    session_id: str | None = None
    try:
        artifact = client.upload(
            firmware_path,
            f"{sample['device_id']}-{sample['firmware_id']}.bin",
        )
        result["artifact"] = artifact
        firmware = client.post(
            "firmware",
            {
                "device_id": sample["device_id"],
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            },
        )
        result["firmware"] = firmware
        analysis = client.post(
            "firmware/analyze",
            {"firmware_id": firmware["firmware_id"]},
        )
        result["service_static_analysis"] = analysis
        prepared = prepare_review_runtime(client, sample)
        session_payload = {
            "device_id": sample["device_id"],
            "firmware_id": firmware["firmware_id"],
            "ttl_seconds": max(600, int(observe_seconds) + 300),
            "ready_timeout_seconds": observe_seconds,
        }
        if prepared:
            session_payload["runtime"] = prepared["runtime"]
            if prepared.get("ready_marker"):
                session_payload["ready_marker"] = prepared["ready_marker"]
            if prepared.get("network"):
                session_payload["network"] = prepared["network"]
            if prepared.get("nvs"):
                session_payload["nvs"] = {
                    "partition_label": prepared["nvs"]["partition_label"],
                    "image_artifact_id": prepared["nvs"]["artifact_id"],
                }
                result["nvs_fixture"] = prepared["nvs"]
        if storage_fixture:
            session_payload["storage"] = {
                "sd_image_artifact_id": storage_fixture["artifact_id"],
            }
        session = client.post("sessions", session_payload)
        session_id = str(session["session_id"])
        result["session_id"] = session_id
        snapshot = wait_until_running(
            client,
            session_id,
            timeout=(
                420
                if sample["device_id"] == "tab5"
                else max(120, observe_seconds + 60)
            ),
        )
        result["boot_snapshot"] = snapshot
        if (
            snapshot.get("state") == "running"
            and expectation_mode == "network-first"
        ):
            time.sleep(
                max(
                    0,
                    min(
                        120,
                        int(
                            (sample.get("_review_expectation_private") or {}).get(
                                "network_observe_seconds"
                            )
                            or 0
                        ),
                    ),
                )
            )
        if snapshot.get("state") == "running" and capture_frame:
            try:
                ready = client.post(
                    f"sessions/{session_id}/wait",
                    {
                        "timeout_seconds": observe_seconds,
                        "ready": {
                            "frame_nonblank": True,
                            "frame_min_bytes": 1024,
                            "frame_min_nonblack_pixels": 16,
                            "require_all": True,
                        },
                    },
                    timeout=max(client.timeout, observe_seconds + 15),
                )
                result["frame_ready"] = True
                result["ready_snapshot"] = ready
                result["frame_metrics"] = ready.get("frame")
            except HttpError as error:
                result["frame_ready"] = False
                result["frame_wait_error"] = {
                    "status": error.status,
                    "message": str(error),
                }
        elif expectation_mode != "network-first":
            time.sleep(min(observe_seconds, 12))

        snapshot = client.get(f"sessions/{session_id}")
        result["pre_input_snapshot"] = snapshot
        before_path = out_dir / f"{sample['device_id']}-{sample['firmware_id']}-before.png"
        before_sha = None
        if capture_frame:
            try:
                before, before_headers = client.frame(session_id, before_path)
                before_sha = hashlib.sha256(before).hexdigest()
                result["before_frame"] = {
                    "path": str(before_path),
                    "sha256": before_sha,
                    "width": before_headers.get("X-Frame-Width"),
                    "height": before_headers.get("X-Frame-Height"),
                    **png_metrics(before),
                }
            except (HttpError, MatrixError) as error:
                result["before_frame_error"] = str(error)

        pre_input_serial_sha = None
        try:
            pre_input_logs = client.get(
                f"sessions/{session_id}/logs?offset=0&limit=262144"
            )
            pre_input_serial = str(pre_input_logs.get("data") or "")
            pre_input_serial_sha = hashlib.sha256(
                pre_input_serial.encode("utf-8", errors="replace")
            ).hexdigest()
        except HttpError:
            pre_input_serial = ""

        input_attempts: list[dict[str, Any]] = []
        if snapshot.get("state") == "running" and capture_input:
            for index, payload in enumerate(inputs_for_device(device)):
                input_result: dict[str, Any] = {"request": payload}
                try:
                    response = client.post(
                        f"sessions/{session_id}/input",
                        payload,
                    )
                    input_result["response"] = response
                    time.sleep(settle_seconds)
                    if capture_frame:
                        probe_path = out_dir / (
                            f"{sample['device_id']}-{sample['firmware_id']}"
                            f"-input-{index}.png"
                        )
                        probe, probe_headers = client.frame(
                            session_id, probe_path
                        )
                        probe_sha = hashlib.sha256(probe).hexdigest()
                        input_result["frame"] = {
                            "path": str(probe_path),
                            "sha256": probe_sha,
                            "width": probe_headers.get("X-Frame-Width"),
                            "height": probe_headers.get("X-Frame-Height"),
                            **png_metrics(probe),
                        }
                        input_result["frame_changed_from_before"] = bool(
                            before_sha and before_sha != probe_sha
                        )
                except HttpError as error:
                    input_result["error"] = {
                        "status": error.status,
                        "message": str(error),
                    }
                input_attempts.append(input_result)
        result["inputs"] = input_attempts

        after_path = out_dir / f"{sample['device_id']}-{sample['firmware_id']}-after.png"
        if capture_frame:
            try:
                after, after_headers = client.frame(session_id, after_path)
                after_metrics = png_metrics(after)
                after_sha = hashlib.sha256(after).hexdigest()
                result["after_frame"] = {
                    "path": str(after_path),
                    "sha256": after_sha,
                    "width": after_headers.get("X-Frame-Width"),
                    "height": after_headers.get("X-Frame-Height"),
                    **after_metrics,
                }
                result["input_changed_frame"] = bool(
                    before_sha and before_sha != after_sha
                )
            except (HttpError, MatrixError) as error:
                result["after_frame_error"] = str(error)

        logs = client.get(f"sessions/{session_id}/logs?offset=0&limit=262144")
        serial = str(logs.get("data") or "")
        stderr = str(logs.get("stderr") or logs.get("qemu_stderr") or "")
        result["serial_bytes"] = len(serial.encode("utf-8", errors="replace"))
        result["serial_sha256"] = hashlib.sha256(serial.encode("utf-8")).hexdigest()
        result["errors"] = error_lines(serial + "\n" + stderr)
        runtime_model_gaps = detect_runtime_model_gaps(
            serial + "\n" + stderr,
            device_id=sample["device_id"],
        )
        result["runtime_model_gaps"] = runtime_model_gaps
        log_path = out_dir / f"{sample['device_id']}-{sample['firmware_id']}-serial.log"
        log_path.write_text(serial, encoding="utf-8", errors="replace")
        result["serial_log"] = str(log_path)

        final_snapshot = client.get(f"sessions/{session_id}")
        result["final_snapshot"] = final_snapshot
        pre_stop_state = final_snapshot.get("state")
        network_document: Mapping[str, Any] = {}
        if isinstance(
            (sample.get("_review_expectation_private") or {}).get("network"),
            Mapping,
        ):
            try:
                result["stop"] = client.delete(
                    f"sessions/{session_id}?purge=0",
                )
                stopped_snapshot = client.get(f"sessions/{session_id}")
                result["stopped_snapshot"] = stopped_snapshot
                network_document = client.get(
                    f"sessions/{session_id}/network"
                )
                if not isinstance(network_document, Mapping):
                    raise MatrixError("network evidence is not an object")
                result["network"] = dict(network_document)
            except (HttpError, MatrixError) as error:
                result["network_error"] = str(error)
                network_document = {}
        if not network_document:
            snapshot_network = final_snapshot.get("network")
            network_document = (
                snapshot_network
                if isinstance(snapshot_network, Mapping)
                else {}
            )
        network_status = network_document.get("status")
        marker_text = serial + "\n" + stderr
        required_results = {
            marker: marker in marker_text
            for marker in (
                (review_expectation or {}).get("required_markers") or []
            )
        }
        forbidden_results = {
            marker: marker in marker_text
            for marker in (
                (review_expectation or {}).get("forbidden_markers") or []
            )
        }
        required_markers_observed = all(required_results.values())
        forbidden_markers_observed = any(forbidden_results.values())
        require_network = bool(
            (review_expectation or {}).get("require_network")
        )
        expectation_network = (review_expectation or {}).get("network")
        expectation_network = (
            expectation_network
            if isinstance(expectation_network, Mapping)
            else {}
        )
        require_pcap = bool(
            expectation_network.get("capture_pcap", False)
        )
        network_evaluation = evaluate_network_expectation(
            network_document,
            require_capture=require_pcap,
        )
        network_observed = (
            bool(network_evaluation["observed"])
            if require_network
            else None
        )
        result["expectation_evidence"] = {
            "required_markers": required_results,
            "forbidden_markers": forbidden_results,
            "network_status": network_status,
            "pcap_required": require_pcap,
            "pcap_observed": network_evaluation["pcap_observed"],
            "network_observed": network_observed,
        }
        if network_document:
            result["network"] = dict(network_document)
        frame_info = result.get("after_frame") or result.get("before_frame")
        nonblack = int((frame_info or {}).get("nonblack_pixels") or 0)
        running = pre_stop_state == "running"
        crash = bool(result["errors"])
        frame_changed = any(
            bool(item.get("frame_changed_from_before"))
            for item in input_attempts
        )
        serial_changed = bool(
            pre_input_serial_sha
            and result["serial_sha256"] != pre_input_serial_sha
        )
        input_observed = frame_changed or serial_changed
        result["observable_input_response"] = {
            "frame_changed": frame_changed,
            "serial_changed": serial_changed,
            "observed": input_observed,
        }
        boot_error = (
            str(final_snapshot["error"])
            if final_snapshot.get("state") == "failed"
            and final_snapshot.get("error")
            else None
        )
        status, status_reason, unmet_requirements = classify_result(
            has_screenshot=has_screenshot,
            nonblack=nonblack,
            running=running,
            crash=crash,
            serial_bytes=int(result["serial_bytes"]),
            boot_error=boot_error,
            input_observed=input_observed,
            runtime_model_gaps=runtime_model_gaps,
            review_expectation=review_expectation,
            required_markers_observed=required_markers_observed,
            forbidden_markers_observed=forbidden_markers_observed,
            network_observed=network_observed,
        )
        result["status"] = status
        result["status_reason"] = status_reason
        result["unmet_requirements"] = unmet_requirements
        if expectation_mode == "ui-interactive":
            result["application_ready"] = nonblack >= 16
        else:
            result["application_ready"] = (
                required_markers_observed
                and not forbidden_markers_observed
                and (not require_network or network_observed is True)
                and result["serial_bytes"] > 0
                and running
                and not crash
            )
        result["error"] = None
    except Exception as error:
        result["status"] = "FAIL"
        result["error"] = str(error)
        result["finished_at"] = utc_now()
    finally:
        if session_id and not result.get("stop"):
            try:
                result["stop"] = client.delete(
                    f"sessions/{session_id}?purge=0",
                )
            except Exception as error:
                result["stop_error"] = str(error)
        result["finished_at"] = utc_now()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--service-url",
        default=os.environ.get("M5_DEVICE_SERVICE_URL", DEFAULT_SERVICE),
    )
    parser.add_argument(
        "--burner-url",
        default=os.environ.get("M5BURNER_API_BASE_URL", DEFAULT_API_BASE),
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--devices", default="")
    parser.add_argument("--per-device", type=int, default=3)
    parser.add_argument("--candidate-limit", type=int, default=30)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--observe-seconds", type=float, default=35)
    parser.add_argument("--settle-seconds", type=float, default=1.2)
    parser.add_argument("--sd-image", type=Path)
    parser.add_argument(
        "--expectation-file",
        type=Path,
        help=(
            "SHA-bound review intent JSON; supports UI, headless-serial "
            "and network-first execution expectations"
        ),
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    selected_devices = [
        item.strip()
        for item in args.devices.split(",")
        if item.strip()
    ]
    if selected_devices:
        unknown = sorted(set(selected_devices) - set(BURNER_TARGETS))
        if unknown:
            raise SystemExit(f"unsupported devices: {', '.join(unknown)}")
    else:
        selected_devices = list(BURNER_TARGETS)

    client = ServiceClient(args.service_url)
    expectations = load_execution_expectations(args.expectation_file)
    devices_payload = client.get("devices")
    devices = {
        str(row["device_id"]): row
        for row in devices_payload.get("devices", [])
        if isinstance(row, Mapping) and row.get("device_id")
    }
    missing = sorted(set(selected_devices) - set(devices))
    if missing:
        raise SystemExit(f"Device Service does not expose: {', '.join(missing)}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.out_dir / "plan.json"
    results_path = args.out_dir / "results.json"
    previous_results: dict[str, Any] = {}
    if args.resume and results_path.is_file():
        payload = json.loads(results_path.read_text())
        previous_results = {
            str(row.get("sample_key")): row
            for row in payload.get("samples", [])
            if isinstance(row, Mapping) and row.get("sample_key")
        }

    selections: list[dict[str, Any]] = []
    if args.resume and plan_path.is_file():
        plan = json.loads(plan_path.read_text())
        existing = {
            str(row.get("device_id")): row
            for row in plan.get("devices", [])
            if isinstance(row, Mapping) and row.get("device_id")
        }
        for device_id in selected_devices:
            if device_id not in existing:
                raise SystemExit(
                    f"resume plan is missing {device_id}; remove --resume or rerun"
                )
            selection = dict(existing[device_id])
            _, target_slug = BURNER_TARGETS[device_id]
            samples = selection.get("selected")
            if not isinstance(samples, list) or not samples:
                raise SystemExit(f"resume plan has no samples for {device_id}")
            refreshed_samples = []
            for index, sample in enumerate(samples, start=1):
                if not isinstance(sample, Mapping):
                    raise SystemExit(
                        f"resume plan has invalid sample {device_id}[{index}]"
                    )
                try:
                    refreshed_samples.append(
                        refresh_selected_sample(
                            sample,
                            base_url=args.burner_url,
                            cache_dir=args.cache_dir,
                            device_soc=str(
                                devices[device_id].get("soc") or ""
                            ),
                        )
                    )
                except Exception as error:
                    raise SystemExit(
                        f"resume refresh failed for {device_id} "
                        f"sample {index}: {error}"
                    ) from error
            selection["selected"] = refreshed_samples
            selection["refreshed_at"] = utc_now()
            if target_slug != selection.get("target_slug"):
                raise SystemExit(f"resume target slug changed for {device_id}")
            selections.append(selection)
        plan = {
            **(plan if isinstance(plan, dict) else {}),
            "retrieved_at": utc_now(),
            "device_service_url": args.service_url,
            "devices": selections,
        }
        atomic_write_json(plan_path, plan)
    else:
        for device_id in selected_devices:
            target_name, target_slug = BURNER_TARGETS[device_id]
            device = devices[device_id]
            print(
                f"PLAN {device_id}: {target_name} / {target_slug}",
                file=sys.stderr,
                flush=True,
            )
            selection = download_candidates(
                device_id=device_id,
                target_name=target_name,
                target_slug=target_slug,
                base_url=args.burner_url,
                cache_dir=args.cache_dir,
                candidate_limit=args.candidate_limit,
                sample_limit=args.per_device,
                device_soc=str(device.get("soc") or ""),
            )
            selections.append(selection)
            print(
                f"  selected {len(selection['selected'])}/{args.per_device}; "
                f"coverage={selection['coverage']}",
                file=sys.stderr,
                flush=True,
            )
            for sample in selection["selected"]:
                print(
                    f"  {sample['rank']}. {sample['name']} "
                    f"({sample['firmware_id']}, {sample['source']}, "
                    f"{sample['downloads']} downloads)",
                    file=sys.stderr,
                    flush=True,
                )
        plan = {
            "schema_version": 1,
            "retrieved_at": utc_now(),
            "burner_url": args.burner_url,
            "device_service_url": args.service_url,
            "selection_policy": (
                "M5Burner MOST_DOWNLOADED; exclude baseline UIFlow2 while "
                "sufficient chip/format-compatible alternatives remain"
            ),
            "devices": selections,
        }
        atomic_write_json(plan_path, plan)
        print(f"PLAN {plan_path}", file=sys.stderr, flush=True)
    expectation_preview: list[dict[str, Any]] = []
    for selection in selections:
        for sample in selection.get("selected", []):
            if isinstance(sample, Mapping):
                expectation_preview.append(dict(sample))
    apply_execution_expectations(expectation_preview, expectations)
    matched_expectations = sum(
        isinstance(sample.get("review_expectation"), Mapping)
        for sample in expectation_preview
    )
    if expectations is not None:
        print(
            "EXPECTATIONS "
            f"matched={matched_expectations} "
            f"source_sha256={expectations['source_sha256']}",
            file=sys.stderr,
            flush=True,
        )
    if args.plan_only:
        return

    sd_fixture: dict[str, Any] | None = None
    if args.sd_image is not None:
        if not args.sd_image.is_file():
            raise SystemExit(f"SD image does not exist: {args.sd_image}")
        sd_bytes = args.sd_image.stat().st_size
        if sd_bytes <= 0 or sd_bytes % 512:
            raise SystemExit(
                "SD image must be non-empty and a multiple of 512 bytes"
            )
        sd_sha = hashlib.sha256(args.sd_image.read_bytes()).hexdigest()
        artifact = client.upload(args.sd_image, args.sd_image.name)
        if artifact["sha256"] != sd_sha:
            raise SystemExit("uploaded SD image SHA-256 changed")
        sd_fixture = {
            "kind": "raw-sd",
            "artifact_id": artifact["artifact_id"],
            "sha256": sd_sha,
            "bytes": sd_bytes,
        }
        print(
            f"SD fixture sha256={sd_sha} bytes={sd_bytes}",
            file=sys.stderr,
            flush=True,
        )

    samples_by_rank: list[list[dict[str, Any]]] = []
    for selection in selections:
        for index, sample in enumerate(selection["selected"]):
            while len(samples_by_rank) <= index:
                samples_by_rank.append([])
            sample = dict(sample)
            if sample["device_id"] == "papermono" and sd_fixture:
                sample["storage_fixture"] = dict(sd_fixture)
            apply_execution_expectations([sample], expectations)
            sample["sample_key"] = sample_result_key(sample)
            samples_by_rank[index].append(sample)

    all_results = list(previous_results.values())
    for wave in samples_by_rank:
        pending = [
            sample
            for sample in wave
            if sample["sample_key"] not in previous_results
        ]
        if not pending:
            continue
        print(
            f"RUN wave rank={pending[0]['rank']} samples={len(pending)}",
            file=sys.stderr,
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            futures = {
                executor.submit(
                    execute_sample,
                    sample,
                    client=client,
                    device=devices[sample["device_id"]],
                    out_dir=args.out_dir,
                    observe_seconds=args.observe_seconds,
                    settle_seconds=args.settle_seconds,
                    storage_fixture=(
                        sample.get("storage_fixture")
                        if isinstance(sample.get("storage_fixture"), dict)
                        else None
                    ),
                ): sample
                for sample in pending
            }
            for future in as_completed(futures):
                sample = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = {
                        **sample,
                        "status": "FAIL",
                        "error": str(error),
                        "finished_at": utc_now(),
                    }
                result["sample_key"] = sample["sample_key"]
                all_results = [
                    row
                    for row in all_results
                    if row.get("sample_key") != sample["sample_key"]
                ]
                all_results.append(result)
                atomic_write_json(
                    results_path,
                    {
                        "schema_version": 1,
                        "scope": "simulation-only-not-hardware-validation",
                        "updated_at": utc_now(),
                        "plan": str(plan_path),
                        "samples": sorted(
                            all_results,
                            key=lambda row: (
                                str(row.get("device_id")),
                                int(row.get("rank") or 0),
                            ),
                        ),
                    },
                )
                print(
                    f"RESULT {sample['device_id']} rank={sample['rank']} "
                    f"status={result.get('status')} "
                    f"session={result.get('session_id')} "
                    f"error={result.get('error')}",
                    file=sys.stderr,
                    flush=True,
                )

    final = json.loads(results_path.read_text())
    counts: dict[str, int] = {}
    for row in final.get("samples", []):
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    print(
        "SUMMARY "
        + " ".join(f"{key}={counts[key]}" for key in sorted(counts)),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
