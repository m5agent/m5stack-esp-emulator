#!/usr/bin/env python3
"""Normalize WebBurner/M5Burner packages into a validated flash manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from firmware_analysis import analyze_firmware
from firmware_static_review import review_firmware


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "platform/tools/firmware_manifest.schema.json"
CATALOG_PATH = ROOT / "devices/catalog.source.json"
DEVICE_MATRIX_PATH = ROOT / "tests/uiflow2/device_matrix.json"
SCHEMA_VERSION = 1
MAX_PACKAGE_FILES = 4096
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_SOURCE_FILES = 2048
MAX_SOURCE_SCAN_BYTES = 64 * 1024 * 1024
MAX_SOURCE_FILE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_HEADER_BYTES = 64 * 1024
WINDOWS_RESERVED_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".py",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
}
SOURCE_SPDX_RE = re.compile(
    r"SPDX-License-Identifier:\s*([A-Za-z0-9.+\-() ]+)"
)
SENSITIVE_SOURCE_PATH_RE = re.compile(
    r"(?:\.env(?:\..*)?|credentials?(?:\..*)?|"
    r"secrets?(?:\..*)?|private[^/]*|passwd|shadow|"
    r"[^/]+\.(?:key|p12|pfx))",
    re.IGNORECASE,
)
CHIP_FAMILIES = {
    "ESP32": "esp32",
    "ESP32-S2": "esp32s2",
    "ESP32-S3": "esp32s3",
    "ESP32-C2": "esp32c2",
    "ESP32-C3": "esp32c3",
    "ESP32-C5": "esp32c5",
    "ESP32-C6": "esp32c6",
    "ESP32-H2": "esp32h2",
    "ESP32-P4": "esp32p4",
}
SOC_ALIASES = {
    "esp32": "esp32",
    "esp32-lx6": "esp32",
    "esp32s3": "esp32s3",
    "esp32-s3": "esp32s3",
    "esp32c6": "esp32c6",
    "esp32-c6": "esp32c6",
    "esp32p4": "esp32p4",
    "esp32-p4": "esp32p4",
}
KNOWN_CAPABILITIES = {
    "adc",
    "audio",
    "ble",
    "button",
    "camera",
    "can",
    "classic-bluetooth",
    "display",
    "gpio",
    "imu",
    "ieee802154",
    "ir",
    "keyboard",
    "lora",
    "microphone",
    "nfc",
    "psram",
    "rs485",
    "sd",
    "speaker",
    "touch",
    "usb-host",
    "vibration",
    "wifi",
}
CAPABILITY_ALIASES = {
    "bluetooth": "ble",
    "bluetooth-low-energy": "ble",
    "classic bluetooth": "classic-bluetooth",
    "display-output": "display",
    "framebuffer": "display",
    "lcd": "display",
    "magnetometer": "imu",
    "screen": "display",
    "storage": "sd",
    "thread": "ieee802154",
    "openthread": "ieee802154",
    "ieee-802154": "ieee802154",
    "zigbee": "ieee802154",
}
SECURE_BOOT_VALUES = {
    "unknown",
    "disabled",
    "not-indicated",
    "v1",
    "v2",
    "enabled-unspecified",
}
FLASH_ENCRYPTION_VALUES = {
    "unknown",
    "disabled",
    "not-indicated",
    "partition-encryption-marked",
    "enabled",
}
SECURE_BOOT_CONFIG_VALUES = {
    "unknown",
    "disabled",
    "not-indicated",
    "v1",
    "v2",
    "enabled-unspecified",
}
FLASH_ENCRYPTION_CONFIG_VALUES = {
    "unknown",
    "disabled",
    "not-indicated",
    "enabled",
}
SECURE_BOOT_REQUIRED_VALUES = {
    "v1",
    "v2",
    "enabled-unspecified",
}
SDKCONFIG_CAPABILITY_FLAGS = (
    ("wifi", ("CONFIG_ESP_WIFI_ENABLED", "CONFIG_WIFI_ENABLED")),
    (
        "ble",
        (
            "CONFIG_BT_ENABLED",
            "CONFIG_BT_BLUEDROID_ENABLED",
            "CONFIG_BT_NIMBLE_ENABLED",
        ),
    ),
    (
        "classic-bluetooth",
        ("CONFIG_BT_CLASSIC_ENABLED",),
    ),
    (
        "ieee802154",
        (
            "CONFIG_IEEE802154_ENABLED",
            "CONFIG_OPENTHREAD_ENABLED",
            "CONFIG_ZB_ENABLED",
        ),
    ),
    ("psram", ("CONFIG_SPIRAM", "CONFIG_SPIRAM_BOOT_INIT")),
)
IMAGE_CAPABILITY_SIGNATURES = (
    (
        "wifi",
        (
            "esp_wifi_init",
            "esp_wifi_connect",
            "wifi:mode",
            "wifi:sta",
        ),
    ),
    (
        "ble",
        (
            "ble_hs_",
            "esp_ble_gap_",
            "esp_ble_gatts_",
            "nimble",
        ),
    ),
    (
        "classic-bluetooth",
        (
            "esp_bt_dev_",
            "esp_bt_gap_",
            "classic_bt",
        ),
    ),
    (
        "ieee802154",
        (
            "esp_ieee802154",
            "ieee802154",
            "zigbee",
        ),
    ),
    (
        "psram",
        (
            "malloc_cap_spiram",
            "spiram_boot_init",
        ),
    ),
    (
        "camera",
        (
            "esp_camera",
            "camera_init",
            "ov2640",
            "ov3660",
        ),
    ),
    (
        "display",
        (
            "lcd_panel_",
            "lv_disp_",
            "m5gfx",
        ),
    ),
    (
        "touch",
        (
            "esp_lcd_touch",
            "gt911",
            "ft5x06",
        ),
    ),
    (
        "audio",
        (
            "audio_element",
            "esp_codec_dev",
            "i2s_channel_",
        ),
    ),
    (
        "sd",
        (
            "esp_vfs_fat_sdmmc",
            "sdmmc_host_",
            "sdmmc_freq",
        ),
    ),
)
OBSERVABLE_CAPABILITIES = {
    capability for capability, _ in IMAGE_CAPABILITY_SIGNATURES
}
IMAGE_CAPABILITY_SCAN_BYTES = 64 << 20
EFUSE_SUMMARY_NAMES = (
    "efuse-summary.json",
    "espefuse-summary.json",
    "efuse_summary.json",
)


class ManifestError(ValueError):
    """Raised when a firmware package or manifest is invalid."""


def normalize_capability_declarations(
    values: object,
    *,
    field: str,
) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ManifestError(f"{field} must be an array")
    if len(values) > 64:
        raise ManifestError(f"{field} exceeds 64 entries")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"{field} must contain non-empty strings")
        token = value.strip().lower()
        if len(token) > 64:
            raise ManifestError(f"{field} contains an entry over 64 characters")
        normalized.append(CAPABILITY_ALIASES.get(token, token))
    return sorted(set(normalized))


def detect_sdkconfig_capabilities(flags: dict[str, str]) -> list[dict[str, str]]:
    detected = []
    for capability, candidate_flags in SDKCONFIG_CAPABILITY_FLAGS:
        enabled_flag = next(
            (
                flag
                for flag in candidate_flags
                if flags.get(flag, "").strip().lower() == "y"
            ),
            None,
        )
        if enabled_flag is not None:
            detected.append(
                {
                    "capability": capability,
                    "source": "sdkconfig",
                    "flag": enabled_flag,
                }
            )
    return detected


def detect_image_capabilities(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total_bytes = path.stat().st_size
    with path.open("rb") as source:
        data = source.read(IMAGE_CAPABILITY_SCAN_BYTES + 1)
    truncated = len(data) > IMAGE_CAPABILITY_SCAN_BYTES
    scanned = data[:IMAGE_CAPABILITY_SCAN_BYTES].lower()
    observed = []
    for capability, signatures in IMAGE_CAPABILITY_SIGNATURES:
        matched = [
            signature
            for signature in signatures
            if signature.encode("ascii") in scanned
        ]
        if matched:
            observed.append(
                {
                    "capability": capability,
                    "source": "image-signature",
                    "confidence": "low",
                    "signatures": matched,
                }
            )
    observation = {
        "status": "TRUNCATED" if truncated else "SCANNED",
        "source": "normalized-flash",
        "bytes_total": total_bytes,
        "bytes_scanned": min(total_bytes, IMAGE_CAPABILITY_SCAN_BYTES),
        "truncated": truncated,
    }
    return observed, observation


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm, usedforsecurity=False)
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    return file_digest(path, "sha256")


def canonical_json_sha256(value: Any) -> str:
    data = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256_bytes(data)


def manifest_identity_payload(manifest: dict) -> dict:
    """Return the content identity without output naming or timestamps."""
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_id", "created_at"}
    }
    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        payload["artifact"] = {
            key: value for key, value in artifact.items() if key != "file"
        }
    return payload


def normalize_soc(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower().replace("_", "-")
    exact = SOC_ALIASES.get(normalized)
    if exact is not None:
        return exact
    compact = normalized.replace("-", "")
    for prefix in ("esp32p4", "esp32c6", "esp32s3", "esp32"):
        if compact.startswith(prefix):
            return prefix
    return None


def load_device_profile(
    device_id: str,
    *,
    catalog_path: Path = CATALOG_PATH,
    matrix_path: Path = DEVICE_MATRIX_PATH,
) -> dict | None:
    catalog = _load_json(catalog_path)
    matrix = _load_json(matrix_path)
    catalog_rows = catalog.get("devices", []) if isinstance(catalog, dict) else []
    matrix_rows = matrix.get("devices", []) if isinstance(matrix, dict) else []
    base = next(
        (
            row
            for row in catalog_rows
            if isinstance(row, dict) and row.get("id") == device_id
        ),
        None,
    )
    if base is None:
        return None
    runtime = next(
        (
            row
            for row in matrix_rows
            if isinstance(row, dict) and row.get("id") == device_id
        ),
        {},
    )
    return {
        **base,
        **{
            key: value
            for key, value in runtime.items()
            if key not in {"id", "hardware"}
        },
    }


def _infer_device_id(sidecar: dict) -> str | None:
    supported = sidecar.get("supported_devices")
    if not isinstance(supported, list):
        return None
    catalog = _load_json(CATALOG_PATH)
    ids = {
        row.get("id")
        for row in catalog.get("devices", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    matches = {
        str(row.get("device_slug") or row.get("device_code") or "").lower()
        for row in supported
        if isinstance(row, dict)
    }
    valid = sorted(matches & ids)
    return valid[0] if len(valid) == 1 else None


def resource(path: Path, *, root: Path) -> dict:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise ManifestError(
            f"resource escapes package root: {path}"
        ) from error
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ManifestError(f"resource is missing or empty: {path}")
    return {
        "file": relative,
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _source_path(path: Path, root: Path) -> tuple[str, str | None]:
    relative = path.relative_to(root).as_posix()
    sensitive = any(
        part and SENSITIVE_SOURCE_PATH_RE.fullmatch(part)
        for part in relative.split("/")
    )
    if sensitive:
        return "<redacted-sensitive-path>", hashlib.sha256(
            relative.encode()
        ).hexdigest()
    return relative, None


def scan_source_licenses(root: Path) -> dict:
    candidates = []
    skipped_symlinks = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            skipped_symlinks += 1
            continue
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        candidates.append(path)
    files = []
    total_bytes = 0
    truncated = False
    declared: set[str] = set()
    for path in candidates:
        if len(files) >= MAX_SOURCE_FILES:
            truncated = True
            break
        size = path.stat().st_size
        if size > MAX_SOURCE_FILE_BYTES:
            truncated = True
            continue
        if total_bytes + size > MAX_SOURCE_SCAN_BYTES:
            truncated = True
            break
        with path.open("rb") as handle:
            header = handle.read(MAX_SOURCE_HEADER_BYTES)
        text = header.decode("utf-8", errors="ignore")
        licenses = sorted(
            {value.strip() for value in SOURCE_SPDX_RE.findall(text)}
        )
        declared.update(licenses)
        display_path, path_hash = _source_path(path, root)
        row = {
            "path": display_path,
            "size": size,
            "sha256": sha256_file(path),
            "declared_licenses": licenses,
        }
        if path_hash is not None:
            row["path_sha256"] = path_hash
            row["redacted"] = True
        files.append(row)
        total_bytes += size
    return {
        "schema_version": 1,
        "status": (
            "PARTIAL"
            if truncated
            else "PASS"
            if files
            else "NOT_PROVIDED"
        ),
        "method": "bounded-source-spdx-header-scan",
        "files": files,
        "limits": {
            "max_files": MAX_SOURCE_FILES,
            "max_total_bytes": MAX_SOURCE_SCAN_BYTES,
            "max_file_bytes": MAX_SOURCE_FILE_BYTES,
            "max_header_bytes": MAX_SOURCE_HEADER_BYTES,
            "files_truncated": truncated,
            "skipped_symlinks": skipped_symlinks,
        },
        "coverage": {
            "files_scanned": len(files),
            "bytes_scanned": total_bytes,
            "files_with_declaration": sum(
                bool(row["declared_licenses"]) for row in files
            ),
            "declared_licenses": sorted(declared),
        },
        "not_claimed": [
            "source contents beyond the SPDX header window",
            "generated or vendored source not present in the package",
            "legal review",
        ],
    }


def _safe_archive_path(value: str) -> str | None:
    if not value or "\x00" in value or "\\" in value:
        raise ManifestError(f"archive entry has invalid path: {value!r}")
    if any(ord(character) < 32 for character in value):
        raise ManifestError(f"archive entry has control characters: {value!r}")
    normalized = unicodedata.normalize("NFC", value)
    if normalized in {"", ".", "./"}:
        raise ManifestError(f"archive entry path is ambiguous: {value!r}")
    if normalized.startswith("/") or posixpath.isabs(normalized):
        raise ManifestError(f"archive entry escapes root: {value}")
    body = normalized[:-1] if normalized.endswith("/") else normalized
    parts = body.split("/")
    if any(not part or part == "." for part in parts):
        raise ManifestError(f"archive entry path is ambiguous: {value!r}")
    if any(part == ".." for part in parts):
        raise ManifestError(f"archive entry escapes root: {value}")
    if any(part != part.strip() for part in parts):
        raise ManifestError(f"archive entry path is not portable: {value!r}")
    for part in parts:
        if ":" in part or part.endswith((".", " ")):
            raise ManifestError(
                f"archive entry path is not portable: {value!r}"
            )
        reserved_stem = part.rstrip(" .").split(".", 1)[0].casefold()
        if reserved_stem in WINDOWS_RESERVED_NAMES:
            raise ManifestError(
                f"archive entry path uses a reserved name: {value!r}"
            )
    normalized = "/".join(parts)
    if normalized in {"", "."}:
        return None
    return normalized


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    files = archive.infolist()
    if len(files) > MAX_PACKAGE_FILES:
        raise ManifestError(
            f"archive contains {len(files)} entries; max is {MAX_PACKAGE_FILES}"
        )
    total = 0
    target_root = target.resolve()
    seen: dict[str, tuple[str, bool]] = {}
    directory_spellings: dict[str, str] = {}
    for entry in files:
        total += entry.file_size
        if total > MAX_PACKAGE_BYTES:
            raise ManifestError(
                f"archive expands above {MAX_PACKAGE_BYTES} bytes"
            )
        normalized = _safe_archive_path(entry.filename)
        if normalized is None:
            continue
        key = normalized.casefold()
        previous = seen.get(key)
        if previous is not None:
            raise ManifestError(
                "archive entries collide after normalization: "
                f"{previous[0]!r} and {entry.filename!r}"
            )
        path_parts = normalized.split("/")
        for index in range(1, len(path_parts)):
            prefix = "/".join(path_parts[:index])
            prefix_key = prefix.casefold()
            previous_spelling = directory_spellings.get(prefix_key)
            if previous_spelling is not None and previous_spelling != prefix:
                raise ManifestError(
                    "archive directory paths collide after normalization: "
                    f"{previous_spelling!r} and {prefix!r}"
                )
            directory_spellings[prefix_key] = prefix
            previous_parent = seen.get(prefix_key)
            if previous_parent is not None and not previous_parent[1]:
                raise ManifestError(
                    "archive path is nested below a file: "
                    f"{previous_parent[0]!r} and {entry.filename!r}"
                )
        for existing_key, (existing_name, _) in seen.items():
            if not entry.is_dir() and existing_key.startswith(key + "/"):
                raise ManifestError(
                    "archive file path is a parent of another entry: "
                    f"{entry.filename!r} and {existing_name!r}"
                )
        seen[key] = (entry.filename, entry.is_dir())
        mode = (entry.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise ManifestError(
                f"archive symlink entries are not supported: {entry.filename}"
            )
        destination = (target / normalized).resolve()
        try:
            destination.relative_to(target_root)
        except ValueError as error:
            raise ManifestError(
                f"archive entry escapes root: {entry.filename}"
            ) from error
        if entry.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with archive.open(entry) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
        except (OSError, RuntimeError) as error:
            raise ManifestError(
                f"cannot extract archive entry {entry.filename!r}: {error}"
            ) from error


def _package_root(path: Path, temporary: Path) -> Path:
    if path.is_dir():
        return path.resolve()
    if path.suffix.lower() in {".zip", ".m5burner", ".webburner"}:
        try:
            with zipfile.ZipFile(path) as archive:
                _safe_extract(archive, temporary)
        except zipfile.BadZipFile as error:
            raise ManifestError(f"invalid firmware archive: {path}") from error
        entries = [
            item for item in temporary.iterdir() if item.name != "__MACOSX"
        ]
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0].resolve()
        return temporary.resolve()
    return path.resolve().parent


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid JSON {path}: {error}") from error


def _sidecar_for(input_path: Path) -> dict:
    candidates = [
        input_path.with_suffix(".json"),
        input_path.with_name(input_path.name + ".json"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            value = _load_json(candidate)
            if isinstance(value, dict):
                return value
    return {}


def _choose_web_manifest(root: Path) -> Path | None:
    candidates = (
        "manifest.json",
        "web-manifest.json",
        "webburner.json",
        "web-burner.json",
    )
    found: list[Path] = []
    for name in candidates:
        path = root / name
        if not path.is_file():
            continue
        value = _load_json(path)
        if isinstance(value, dict) and (
            "builds" in value or "parts" in value
        ):
            found.append(path)
    if len(found) > 1:
        raise ManifestError(
            "multiple WebBurner manifests found: "
            + ", ".join(path.name for path in found)
        )
    return found[0] if found else None


def _resolve_package_file(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ManifestError("package file path must be a non-empty string")
    path = Path(value)
    candidate = path if path.is_absolute() else root / path
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ManifestError(
            f"package path escapes root: {value}"
        ) from error
    if not candidate.is_file():
        raise ManifestError(f"package file does not exist: {value}")
    return candidate


def _web_part_integrity(
    source: Path,
    index: int,
    part: dict,
) -> dict | None:
    declared: dict[str, Any] = {}
    for field in ("size", "sha256", "sha1", "md5"):
        if field in part:
            declared[field] = part[field]
    integrity = part.get("integrity")
    if integrity is not None:
        if not isinstance(integrity, dict):
            raise ManifestError(
                f"WebBurner part {index} integrity must be an object"
            )
        unsupported = sorted(
            set(integrity) - {"size", "sha256", "sha1", "md5"}
        )
        if unsupported:
            raise ManifestError(
                f"WebBurner part {index} has unsupported integrity fields: "
                + ", ".join(unsupported)
            )
        for field, value in integrity.items():
            if field in declared and declared[field] != value:
                raise ManifestError(
                    f"WebBurner part {index} has conflicting {field} values"
                )
            declared[field] = value
    if not declared:
        return None

    verified: list[str] = []
    if "size" in declared:
        raw_size = declared["size"]
        try:
            expected_size = (
                raw_size
                if isinstance(raw_size, int)
                and not isinstance(raw_size, bool)
                else int(str(raw_size), 0)
            )
        except (TypeError, ValueError) as error:
            raise ManifestError(
                f"WebBurner part {index} has invalid size"
            ) from error
        if expected_size < 0:
            raise ManifestError(
                f"WebBurner part {index} has negative size"
            )
        actual_size = source.stat().st_size
        if actual_size != expected_size:
            raise ManifestError(
                f"WebBurner part {index} size mismatch: "
                f"declared {expected_size}, actual {actual_size}"
            )
        verified.append("size")

    for algorithm in ("sha256", "sha1", "md5"):
        if algorithm not in declared:
            continue
        raw_digest = declared[algorithm]
        if not isinstance(raw_digest, str):
            raise ManifestError(
                f"WebBurner part {index} {algorithm} must be a string"
            )
        expected_digest = raw_digest.strip().lower()
        expected_length = hashlib.new(algorithm).digest_size * 2
        if (
            len(expected_digest) != expected_length
            or any(
                char not in "0123456789abcdef"
                for char in expected_digest
            )
        ):
            raise ManifestError(
                f"WebBurner part {index} has invalid {algorithm}"
            )
        actual_digest = file_digest(source, algorithm)
        if actual_digest != expected_digest:
            raise ManifestError(
                f"WebBurner part {index} {algorithm} mismatch"
            )
        verified.append(algorithm)

    return {
        "status": "verified",
        "algorithms": verified,
        "weak_digest": any(
            algorithm in {"sha1", "md5"} for algorithm in verified
        ),
    }


def _segments_from_web_manifest(
    root: Path,
    document: dict,
    *,
    expected_soc: str | None = None,
) -> tuple[list[dict], dict]:
    builds = document.get("builds")
    if isinstance(builds, list):
        if not builds or any(not isinstance(item, dict) for item in builds):
            raise ManifestError("WebBurner builds must be a non-empty object list")
        if len(builds) == 1:
            build = builds[0]
        else:
            if expected_soc is None:
                raise ManifestError(
                    "multi-build WebBurner package requires a target device"
                )
            matching = [
                item
                for item in builds
                if normalize_soc(item.get("chipFamily")) == expected_soc
            ]
            if len(matching) != 1:
                raise ManifestError(
                    "multi-build WebBurner package must have exactly one "
                    f"build for target SoC {expected_soc}"
                )
            build = matching[0]
        chip = normalize_soc(build.get("chipFamily"))
        version = document.get("version")
        name = document.get("name")
        parts = build.get("parts")
    else:
        build = document
        chip = normalize_soc(build.get("chip") or build.get("chipFamily"))
        version = document.get("version")
        name = document.get("name")
        parts = document.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ManifestError("WebBurner manifest has no flash parts")
    segments = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ManifestError(f"WebBurner part {index} must be an object")
        try:
            raw_offset = part.get("offset")
            offset = (
                raw_offset
                if isinstance(raw_offset, int)
                and not isinstance(raw_offset, bool)
                else int(str(raw_offset), 0)
            )
        except (TypeError, ValueError) as error:
            raise ManifestError(
                f"WebBurner part {index} has invalid offset"
            ) from error
        if offset < 0:
            raise ManifestError(f"WebBurner part {index} has negative offset")
        source = _resolve_package_file(root, part.get("path"))
        segment = {
            "offset": offset,
            "path": source,
            **resource(source, root=root),
        }
        integrity = _web_part_integrity(source, index, part)
        if integrity is not None:
            segment["declared_integrity"] = integrity
        segments.append(segment)
    return segments, {
        "source_format": "web-manifest",
        "name": name,
        "version": str(version) if version is not None else None,
        "chip": chip,
    }


def _segments_from_flasher_args(
    root: Path,
    path: Path,
) -> tuple[list[dict], dict]:
    document = _load_json(path)
    if not isinstance(document, dict):
        raise ManifestError("flasher_args.json must be an object")
    flash_files = document.get("flash_files")
    if not isinstance(flash_files, dict) or not flash_files:
        raise ManifestError("flasher_args.json has no flash_files")
    segments = []
    for raw_offset, raw_path in flash_files.items():
        try:
            offset = int(str(raw_offset), 0)
        except ValueError as error:
            raise ManifestError(
                f"invalid flasher_args offset: {raw_offset!r}"
            ) from error
        source = _resolve_package_file(root, raw_path)
        segments.append(
            {
                "offset": offset,
                "path": source,
                **resource(source, root=root),
            }
        )
    extra = document.get("extra_esptool_args")
    chip = normalize_soc(
        extra.get("chip") if isinstance(extra, dict) else None
    )
    return segments, {
        "source_format": "flasher-args",
        "chip": chip,
        "name": document.get("project_name"),
        "version": None,
    }


def _image_candidates(root: Path) -> list[Path]:
    excluded = {"bootloader.bin", "partition-table.bin", "partition_table.bin"}
    return sorted(
        (
            path
            for path in root.rglob("*.bin")
            if path.name.lower() not in excluded
        ),
        key=lambda path: (-path.stat().st_size, path.as_posix()),
    )


def _find_resources(root: Path) -> dict:
    resources: dict[str, dict] = {}
    patterns = {
        "elf": ("*.elf",),
        "map": ("*.map",),
        "sdkconfig": (
            "sdkconfig",
            "sdkconfig.defaults",
        ),
        "flasher_args": ("flasher_args.json",),
        "sbom": (
            "sbom.json",
            "bom.json",
            "*.spdx.json",
            "*.cdx.json",
            "cyclonedx*.json",
        ),
    }
    for kind, names in patterns.items():
        candidates = {
            path
            for pattern in names
            for path in root.rglob(pattern)
            if path.is_file()
        }
        if kind == "sdkconfig":
            exact = {
                path for path in candidates if path.name == "sdkconfig"
            }
            defaults = {
                path
                for path in candidates
                if path.name == "sdkconfig.defaults"
            }
            for label, paths in (
                ("sdkconfig", exact),
                ("sdkconfig.defaults", defaults),
            ):
                if len(paths) > 1:
                    raise ManifestError(
                        f"package contains multiple {label} resources: "
                        + ", ".join(
                            path.relative_to(root).as_posix()
                            for path in sorted(
                                paths,
                                key=lambda item: item.as_posix(),
                            )
                        )
                    )
            candidates = exact or defaults
        candidates = sorted(candidates, key=lambda item: item.as_posix())
        if not candidates:
            continue
        if len(candidates) > 1:
            raise ManifestError(
                f"package contains multiple {kind} resources: "
                + ", ".join(
                    path.relative_to(root).as_posix()
                    for path in candidates
                )
            )
        resources[kind] = resource(candidates[0], root=root)
    return resources


def _find_efuse_summary(root: Path) -> Path | None:
    candidates = [
        path
        for name in EFUSE_SUMMARY_NAMES
        for path in root.rglob(name)
        if path.is_file()
    ]
    if not candidates:
        return None
    candidates = sorted(candidates, key=lambda item: item.as_posix())
    if len(candidates) > 1:
        raise ManifestError(
            "package contains multiple eFuse summaries: "
            + ", ".join(
                path.relative_to(root).as_posix()
                for path in candidates
            )
        )
    return candidates[0]


def _load_efuse_summary(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text()
    except OSError as error:
        raise ManifestError(f"cannot read eFuse summary {path}: {error}") from error
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise ManifestError("eFuse summary contains no JSON object")
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as error:
            raise ManifestError(f"invalid eFuse summary JSON: {error}") from error
    if not isinstance(value, dict):
        raise ManifestError("eFuse summary must be a JSON object")
    return value


def _segment_intervals(segments: Iterable[dict]) -> list[tuple[int, int, dict]]:
    intervals = []
    for segment in segments:
        start = int(segment["offset"])
        size = int(segment["size"])
        if start < 0 or size <= 0:
            raise ManifestError("flash segment has invalid range")
        intervals.append((start, start + size, segment))
    intervals.sort(key=lambda row: row[0])
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise ManifestError("flash segments overlap")
    return intervals


def _compose_segments(
    segments: list[dict],
    *,
    flash_size: int,
    output: Path,
) -> None:
    intervals = _segment_intervals(segments)
    if intervals and intervals[-1][1] > flash_size:
        raise ManifestError(
            f"segments exceed flash size 0x{flash_size:x}"
        )
    image = bytearray(b"\xff" * flash_size)
    for start, end, segment in intervals:
        data = Path(segment["path"]).read_bytes()
        image[start:end] = data
    output.write_bytes(image)


def _code_issues(
    code: str,
    message: str,
    *,
    requirement: Any = None,
    available: Any = None,
    path: str | None = None,
) -> dict:
    issue = {
        "code": code,
        "message": message,
    }
    if requirement is not None:
        issue["requirement"] = requirement
    if available is not None:
        issue["available"] = available
    if path is not None:
        issue["path"] = path
    return issue


def _security_runtime_errors(security: dict) -> list[dict]:
    errors = []
    secure_boot = security.get("secure_boot")
    if secure_boot in SECURE_BOOT_REQUIRED_VALUES:
        errors.append(
            _code_issues(
                "secure_boot_not_modeled",
                "target profile does not model the required secure-boot chain",
                requirement=secure_boot,
                available="not modeled",
                path="security.secure_boot",
            )
        )
    secure_boot_config = security.get("secure_boot_config")
    if secure_boot_config in SECURE_BOOT_REQUIRED_VALUES:
        errors.append(
            _code_issues(
                "secure_boot_config_not_modeled",
                (
                    "sdkconfig enables a secure-boot chain that the target "
                    "profile does not model"
                ),
                requirement=secure_boot_config,
                available="not modeled",
                path="security.secure_boot_config",
            )
        )
    secure_boot_image = security.get("secure_boot_image")
    if isinstance(secure_boot_image, dict):
        status = secure_boot_image.get("status")
        images = secure_boot_image.get("images")
        signed_images = (
            [
                image
                for image in images
                if isinstance(image, dict)
                and (
                    image.get("status") != "not-found"
                    or image.get("block_count")
                    or image.get("blocks")
                )
            ]
            if isinstance(images, list)
            else []
        )
        if (
            status == "not-found"
            and signed_images
        ):
            errors.append(
                _code_issues(
                    "secure_boot_image_status_understated",
                    (
                        "Secure Boot image evidence is present while status "
                        "is not-found; the manifest is internally inconsistent"
                    ),
                    requirement=len(signed_images),
                    available=status,
                    path="security.secure_boot_image.status",
                )
            )
        if status == "signed-image-observed":
            errors.append(
                _code_issues(
                    "secure_boot_image_not_modeled",
                    (
                        "a Secure Boot v2 signed image was observed, but the "
                        "target profile does not model the boot trust chain"
                    ),
                    requirement=status,
                    available="not modeled",
                    path="security.secure_boot_image.status",
                )
            )
        elif status == "invalid":
            errors.append(
                _code_issues(
                    "secure_boot_image_invalid",
                    (
                        "Secure Boot v2 signature evidence is invalid; "
                        "the image cannot be accepted as boot-compatible"
                    ),
                    requirement=status,
                    available="invalid",
                    path="security.secure_boot_image.status",
                )
            )
    trust_root = security.get("trust_root")
    if isinstance(trust_root, dict):
        comparison = trust_root.get("comparison")
        if comparison == "mismatch-unverified-source":
            errors.append(
                _code_issues(
                    "secure_boot_efuse_key_mismatch",
                    (
                        "Secure Boot image key digest does not match the "
                        "package-provided eFuse summary"
                    ),
                    requirement="matching key digest",
                    available="mismatch",
                    path="security.trust_root.comparison",
                )
            )
        elif (
            comparison == "match-unverified-source"
            and isinstance(secure_boot_image, dict)
            and secure_boot_image.get("status") != "signed-image-observed"
        ):
            errors.append(
                _code_issues(
                    "secure_boot_trust_evidence_inconsistent",
                    (
                        "trust-root evidence claims a key comparison while "
                        "image status is not signed-image-observed"
                    ),
                    requirement=comparison,
                    available=secure_boot_image.get("status"),
                    path="security.trust_root.comparison",
                )
            )
    anti_rollback = security.get("anti_rollback")
    if (
        isinstance(anti_rollback, dict)
        and anti_rollback.get("comparison")
        == "image-below-efuse-unverified-source"
    ):
        errors.append(
            _code_issues(
                "firmware_secure_version_below_efuse",
                (
                    "image secure version is below the package-provided "
                    "eFuse anti-rollback version"
                ),
                requirement=anti_rollback.get("efuse_secure_version"),
                available=anti_rollback.get("image_secure_version"),
                path="security.anti_rollback.comparison",
            )
        )
    efuse_summary = security.get("efuse_summary")
    if isinstance(efuse_summary, dict):
        secure_boot = efuse_summary.get("secure_boot")
        if secure_boot not in SECURE_BOOT_VALUES:
            errors.append(
                _code_issues(
                    "invalid_efuse_security_evidence",
                    "eFuse summary secure_boot state is invalid",
                    requirement=secure_boot,
                    available=sorted(SECURE_BOOT_VALUES),
                    path="security.efuse_summary.secure_boot",
                )
            )
        if secure_boot in SECURE_BOOT_REQUIRED_VALUES:
            errors.append(
                _code_issues(
                    "secure_boot_efuse_not_modeled",
                    (
                        "package-provided eFuse summary indicates secure boot, "
                        "which the target profile does not model"
                    ),
                    requirement=secure_boot,
                    available="not modeled",
                    path="security.efuse_summary.secure_boot",
                )
            )
    flash_encryption = security.get("flash_encryption")
    if flash_encryption == "enabled":
        errors.append(
            _code_issues(
                "flash_encryption_not_modeled",
                "target profile does not model this flash-encryption mode",
                requirement="enabled",
                available="not modeled",
                path="security.flash_encryption",
            )
        )
    flash_encryption_config = security.get("flash_encryption_config")
    if flash_encryption_config == "enabled":
        errors.append(
            _code_issues(
                "flash_encryption_config_not_modeled",
                (
                    "sdkconfig enables Flash Encryption, which the target "
                    "profile does not model"
                ),
                requirement="enabled",
                available="not modeled",
                path="security.flash_encryption_config",
            )
        )
    if isinstance(efuse_summary, dict):
        flash_encryption = efuse_summary.get("flash_encryption")
        if flash_encryption not in FLASH_ENCRYPTION_VALUES:
            errors.append(
                _code_issues(
                    "invalid_efuse_security_evidence",
                    "eFuse summary Flash Encryption state is invalid",
                    requirement=flash_encryption,
                    available=sorted(FLASH_ENCRYPTION_VALUES),
                    path="security.efuse_summary.flash_encryption",
                )
            )
        if flash_encryption == "enabled":
            errors.append(
                _code_issues(
                    "flash_encryption_efuse_not_modeled",
                    (
                        "package-provided eFuse summary indicates Flash "
                        "Encryption, which the target profile does not model"
                    ),
                    requirement="enabled",
                    available="not modeled",
                    path="security.efuse_summary.flash_encryption",
                )
            )
    return errors


def validate_capabilities(
    manifest: dict,
    device: dict,
) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append(
            _code_issues(
                "capabilities_required",
                "manifest must include a capabilities object",
                path="capabilities",
            )
        )
        capabilities = {}
    for field in ("required", "optional"):
        value = capabilities.get(field)
        if (
            not isinstance(value, list)
            or len(value) > 64
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item.strip()) > 64
                for item in value
            )
        ):
            errors.append(
                _code_issues(
                    "invalid_capability_declarations",
                    (
                        f"manifest.capabilities.{field} must be a string "
                        "array"
                    ),
                    path=f"capabilities.{field}",
                )
            )
    hardware = device.get("hardware")
    if not isinstance(hardware, dict):
        raise ManifestError("device profile has no hardware object")
    expected_soc = normalize_soc(hardware.get("soc"))
    actual_soc = normalize_soc(manifest.get("target", {}).get("soc"))
    if expected_soc and actual_soc and expected_soc != actual_soc:
        errors.append(
            _code_issues(
                "soc_mismatch",
                f"firmware targets {actual_soc}; device is {expected_soc}",
                requirement=expected_soc,
                available=actual_soc,
                path="target.soc",
            )
        )
    device_flash = hardware.get("flash_bytes")
    manifest_flash = manifest.get("target", {}).get("flash_size")
    if isinstance(device_flash, int) and isinstance(manifest_flash, int):
        if manifest_flash > device_flash:
            errors.append(
                _code_issues(
                    "flash_size_mismatch",
                    (
                        f"firmware requires {manifest_flash} bytes of flash; "
                        f"device provides {device_flash}"
                    ),
                    requirement=device_flash,
                    available=manifest_flash,
                    path="target.flash_size",
                )
            )
    manifest_psram = manifest.get("target", {}).get("psram_size")
    device_psram = hardware.get("psram_bytes")
    if isinstance(manifest_psram, int) and manifest_psram > 0:
        if not isinstance(device_psram, int) or device_psram < manifest_psram:
            errors.append(
                _code_issues(
                    "psram_mismatch",
                    (
                        f"firmware requires {manifest_psram} bytes of PSRAM; "
                        f"device profile reports {device_psram or 0}"
                    ),
                    requirement=manifest_psram,
                    available=device_psram or 0,
                    path="target.psram_size",
                )
            )
    security = manifest.get("security", {})
    if not isinstance(security, dict):
        security = {}
    errors.extend(_security_runtime_errors(security))
    if security.get("flash_encryption") == "partition-encryption-marked":
        warnings.append(
            _code_issues(
                "partition_encryption_not_modeled",
                (
                    "partition table marks encrypted partitions; boot may "
                    "require a matching eFuse and key state"
                ),
                path="security.flash_encryption",
            )
        )
    required = capabilities.get("required", [])
    optional = capabilities.get("optional", [])
    if not isinstance(required, list):
        required = []
    if not isinstance(optional, list):
        optional = []
    required_set = {
        CAPABILITY_ALIASES.get(
            str(value).strip().lower(),
            str(value).strip().lower(),
        )
        for value in required
    }
    optional_set = {
        CAPABILITY_ALIASES.get(
            str(value).strip().lower(),
            str(value).strip().lower(),
        )
        for value in optional
    }
    declared_set = required_set | optional_set
    device_capabilities = _device_capability_set(device)
    for requirement in required:
        normalized = CAPABILITY_ALIASES.get(
            str(requirement).strip().lower(),
            str(requirement).strip().lower(),
        )
        if normalized not in KNOWN_CAPABILITIES:
            errors.append(
                _code_issues(
                    "unknown_required_capability",
                    (
                        f"firmware requires {requirement!r}, but the "
                        "compatibility checker does not recognize it; "
                        "unknown required capabilities fail closed"
                    ),
                    requirement=requirement,
                    path="capabilities.required",
                )
            )
        elif normalized not in device_capabilities:
            errors.append(
                _code_issues(
                    "unsupported_capability",
                    (
                        f"firmware requires {normalized}, but device "
                        f"{device.get('id')} does not expose it"
                    ),
                    requirement=normalized,
                    available=sorted(device_capabilities),
                    path="capabilities.required",
                )
            )
    for requirement in optional:
        normalized = CAPABILITY_ALIASES.get(
            str(requirement).strip().lower(),
            str(requirement).strip().lower(),
        )
        if normalized not in KNOWN_CAPABILITIES:
            warnings.append(
                _code_issues(
                    "unknown_optional_capability",
                    (
                        f"optional capability {requirement!r} is not "
                        "recognized by the compatibility checker"
                    ),
                    requirement=requirement,
                    path="capabilities.optional",
                )
            )
        elif normalized not in device_capabilities:
            warnings.append(
                _code_issues(
                    "unsupported_optional_capability",
                    (
                        f"firmware optionally supports {normalized}, but "
                        f"device {device.get('id')} does not expose it; "
                        "the firmware remains a candidate"
                    ),
                    requirement=normalized,
                    available=sorted(device_capabilities),
                    path="capabilities.optional",
                )
            )
    detected_capabilities = capabilities.get("detected", [])
    if not isinstance(detected_capabilities, list):
        detected_capabilities = []
    for detection in detected_capabilities:
        if not isinstance(detection, dict):
            continue
        requirement = str(detection.get("capability") or "").strip().lower()
        normalized = CAPABILITY_ALIASES.get(requirement, requirement)
        if (
            normalized in KNOWN_CAPABILITIES
            and normalized not in device_capabilities
        ):
            warnings.append(
                _code_issues(
                    "detected_capability_unavailable",
                    (
                        f"sdkconfig enables {normalized}, but device "
                        f"{device.get('id')} profile does not expose it; "
                        "this is a review warning, not a code-path proof"
                    ),
                    requirement=normalized,
                    available=sorted(device_capabilities),
                    path="capabilities.detected",
                )
            )
    observed_set: set[str] = set()
    observed_capabilities = capabilities.get("observed", [])
    if not isinstance(observed_capabilities, list):
        observed_capabilities = []
    for detection in observed_capabilities:
        if not isinstance(detection, dict):
            continue
        requirement = str(detection.get("capability") or "").strip().lower()
        normalized = CAPABILITY_ALIASES.get(requirement, requirement)
        if normalized not in KNOWN_CAPABILITIES:
            continue
        observed_set.add(normalized)
        signatures = [
            str(signature)
            for signature in detection.get("signatures", [])
            if isinstance(signature, str) and signature
        ][:8]
        if normalized not in device_capabilities:
            warnings.append(
                _code_issues(
                    "observed_capability_unavailable",
                    (
                        f"image contains low-confidence {normalized} "
                        f"signature(s) ({', '.join(signatures)}), but device "
                        f"{device.get('id')} "
                        "profile does not expose it"
                    ),
                    requirement=normalized,
                    available=sorted(device_capabilities),
                    path="capabilities.observed",
                )
            )
        if normalized not in declared_set:
            warnings.append(
                _code_issues(
                    "observed_capability_not_declared",
                    (
                        f"image contains low-confidence {normalized} "
                        f"signature(s) ({', '.join(signatures)}), but neither "
                        "required nor optional capabilities name it; this is "
                        "not runtime proof"
                    ),
                    requirement=normalized,
                    available=sorted(declared_set),
                    path="capabilities.observed",
                )
            )
    for requirement in sorted(
        required_set
        & OBSERVABLE_CAPABILITIES
        & device_capabilities
    ):
        if requirement in observed_set:
            continue
        warnings.append(
            _code_issues(
                "required_capability_not_observed",
                (
                    f"required capability {requirement} is supported by the "
                    "target, but its low-confidence image signature was not "
                    "observed; verify the declaration or runtime path"
                ),
                requirement=requirement,
                path="capabilities.required",
            )
        )
    return {
        "status": "REJECTED" if errors else "PASS",
        "device_id": device.get("id"),
        "errors": errors,
        "warnings": warnings,
    }


def _device_capability_set(device: dict) -> set[str]:
    hardware = device.get("hardware", {})
    capabilities: set[str] = set()
    display = hardware.get("display")
    if isinstance(display, dict):
        capabilities.add("display")
        if display.get("touch"):
            capabilities.add("touch")
    for control in hardware.get("controls", []):
        if isinstance(control, dict) and isinstance(control.get("type"), str):
            capabilities.add(control["type"].lower())
    for sensor in hardware.get("sensors", []):
        if isinstance(sensor, str) and sensor:
            kind = sensor.split(":", 1)[0].lower()
            capabilities.add(kind)
            if kind in {"audio", "audio-codec"}:
                capabilities.update({"audio", "speaker", "microphone"})
            if kind == "camera":
                capabilities.add("camera")
            if kind == "imu":
                capabilities.add("imu")
    psram = hardware.get("psram_bytes")
    if isinstance(psram, int) and psram > 0:
        capabilities.add("psram")
    if device.get("network_status") == "validated":
        capabilities.update({"wifi", "ble"})
    # WiFi/BLE-capable SoCs may expose one radio without the other in a
    # validated profile; the matrix advertises profiles rather than radio
    # types, so only mark them present when the profile family provides them.
    if "core2" in str(device.get("id", "")):
        capabilities.update({"wifi", "ble"})
    return capabilities


def _license_key(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _normalize_license_list(values: Iterable[str] | None) -> list[str]:
    normalized: dict[str, str] = {}
    for value in values or []:
        if not isinstance(value, str) or not value.strip():
            continue
        rendered = " ".join(value.strip().split())
        normalized.setdefault(_license_key(rendered), rendered)
    return sorted(normalized.values(), key=_license_key)


def evaluate_license_policy(
    manifest: dict,
    *,
    allowed_licenses: Iterable[str] | None = None,
    denied_licenses: Iterable[str] | None = None,
) -> dict:
    allowed = _normalize_license_list(allowed_licenses)
    denied = _normalize_license_list(denied_licenses)
    allowed_keys = {_license_key(value) for value in allowed}
    denied_keys = {_license_key(value) for value in denied}
    sources: list[dict] = []

    provenance_license = manifest.get("provenance", {}).get("license")
    if isinstance(provenance_license, str) and provenance_license.strip():
        sources.append(
            {
                "source": "provenance",
                "license": " ".join(provenance_license.split()),
            }
        )
    for index, filesystem in enumerate(
        manifest.get("target", {}).get("filesystems", [])
    ):
        if not isinstance(filesystem, dict):
            continue
        partition = filesystem.get("partition")
        source = (
            f"filesystem:{partition}"
            if isinstance(partition, str) and partition
            else f"filesystem[{index}]"
        )
        for license_value in filesystem.get("declared_licenses", []):
            if isinstance(license_value, str) and license_value.strip():
                sources.append(
                    {
                        "source": source,
                        "license": " ".join(license_value.split()),
                    }
                )
    sbom = manifest.get("review", {}).get("sbom", {})
    for license_value in sbom.get("licenses", []):
        if isinstance(license_value, str) and license_value.strip():
            sources.append(
                {
                    "source": "sbom",
                    "license": " ".join(license_value.split()),
                }
            )
    source_scan = manifest.get("source_license_scan", {})
    for source_file in source_scan.get("files", []):
        if not isinstance(source_file, dict):
            continue
        for license_value in source_file.get("declared_licenses", []):
            if isinstance(license_value, str) and license_value.strip():
                sources.append(
                    {
                        "source": "source-code",
                        "license": " ".join(license_value.split()),
                    }
                )

    unique_sources = []
    seen_sources: set[tuple[str, str]] = set()
    for row in sources:
        key = (row["source"], _license_key(row["license"]))
        if key in seen_sources:
            continue
        seen_sources.add(key)
        unique_sources.append(row)
    unique_sources.sort(
        key=lambda row: (row["source"], _license_key(row["license"]))
    )
    discovered = sorted(
        {row["license"] for row in unique_sources},
        key=_license_key,
    )
    unknown = sorted(
        {
            value
            for value in discovered
            if _license_key(value) in {"none", "noassertion", "unknown"}
        },
        key=_license_key,
    )
    findings: list[dict] = []
    rejected = False
    for value in discovered:
        key = _license_key(value)
        if key in denied_keys:
            rejected = True
            findings.append(
                {
                    "code": "license_denied",
                    "severity": "error",
                    "license": value,
                    "message": "declared license is denied by policy",
                }
            )
        elif allowed_keys and key not in allowed_keys:
            rejected = True
            findings.append(
                {
                    "code": "license_not_allowed",
                    "severity": "error",
                    "license": value,
                    "message": (
                        "declared license is not present in the allowlist"
                    ),
                }
            )
    if not discovered:
        findings.append(
            {
                "code": "license_not_declared",
                "severity": "warning",
                "message": (
                    "no SPDX license declaration was found in provenance, "
                    "filesystem metadata or SBOM"
                ),
            }
        )
    if not allowed_keys:
        findings.append(
            {
                "code": "license_allowlist_not_configured",
                "severity": "warning",
                "message": (
                    "no allowlist was supplied; declarations require review"
                ),
            }
        )
    if unknown:
        findings.append(
            {
                "code": "license_unknown_expression",
                "severity": "warning",
                "message": (
                    "one or more declarations are not concrete license IDs"
                ),
                "licenses": unknown,
            }
        )
    if rejected:
        status = "REJECTED"
        decision = "rejected"
    elif not discovered or not allowed_keys or unknown:
        status = "REVIEW_REQUIRED"
        decision = "review"
    else:
        status = "PASS"
        decision = "allowlisted"
    return {
        "schema_version": 1,
        "status": status,
        "decision": decision,
        "allowed_licenses": allowed,
        "denied_licenses": denied,
        "discovered_licenses": discovered,
        "sources": unique_sources,
        "findings": findings,
        "coverage": {
            "provenance_declared": bool(
                provenance_license
                and isinstance(provenance_license, str)
                and provenance_license.strip()
            ),
            "filesystem_declarations": sum(
                1
                for row in unique_sources
                if row["source"].startswith("filesystem")
            ),
            "sbom_declarations": sum(
                1 for row in unique_sources if row["source"] == "sbom"
            ),
            "source_code_declarations": sum(
                1 for row in unique_sources if row["source"] == "source-code"
            ),
        },
        "limits": [
            (
                "Policy evaluates declarations and a bounded SPDX source-"
                "header scan; it is not a legal opinion and does not inspect "
                "generated or absent source"
            )
        ],
    }


def _security_metadata(
    analysis: dict,
    sdkconfig: Path | None,
    efuse_summary: dict[str, Any] | None = None,
    efuse_summary_path: Path | None = None,
) -> dict:
    partitions = analysis.get("partition_table", {}).get("partitions", [])
    encrypted = any(
        isinstance(part, dict) and int(part.get("flags", 0)) & 1
        for part in partitions
    )
    descriptor = analysis.get("app_descriptor") or {}
    config = ""
    if sdkconfig is not None and sdkconfig.is_file():
        config = sdkconfig.read_text(errors="replace")
    config_flags = _sdkconfig_flags(config)
    configured_secure_boot = _configured_secure_boot(config_flags)
    configured_flash_encryption = (
        "enabled"
        if config_flags.get("CONFIG_SECURE_FLASH_ENC_ENABLED") == "y"
        else "disabled"
        if config_flags.get("CONFIG_SECURE_FLASH_ENC_ENABLED") == "n"
        else "not-indicated"
        if config_flags
        else "unknown"
    )
    efuse = _parse_efuse_security(efuse_summary, efuse_summary_path)
    secure_boot = (
        efuse["secure_boot"]
        if efuse is not None and efuse["secure_boot"] != "unknown"
        else configured_secure_boot
    )
    if efuse is not None and efuse["flash_encryption"] != "unknown":
        flash_encryption = efuse["flash_encryption"]
    elif encrypted:
        flash_encryption = "partition-encryption-marked"
    else:
        flash_encryption = configured_flash_encryption
    secure_boot_image = analysis.get(
        "secure_boot_v2",
        {
            "status": "not-found",
            "signature_authenticity": "not-verified",
            "trust_root": "not-verified",
            "images": [],
        },
    )
    image_key_digests = {
        (image.get("label"), block.get("public_key_digest_sha256"))
        for image in secure_boot_image.get("images", [])
        if isinstance(image, dict)
        for block in image.get("blocks", [])
        if isinstance(block, dict)
        and isinstance(block.get("public_key_digest_sha256"), str)
    }
    efuse_key_digests = (
        {
            row.get("digest_sha256")
            for row in efuse.get("secure_boot_key_digests", [])
            if isinstance(row, dict)
            and isinstance(row.get("digest_sha256"), str)
        }
        if efuse is not None
        else set()
    )
    matching_pairs = [
        {
            "image": label,
            "public_key_digest_sha256": digest,
        }
        for label, digest in sorted(image_key_digests)
        if digest in efuse_key_digests
    ]
    if secure_boot_image.get("status") != "signed-image-observed":
        trust_comparison = "not-applicable"
    elif efuse is None:
        trust_comparison = "efuse-summary-not-included"
    elif not efuse_key_digests:
        trust_comparison = "efuse-key-digest-unavailable"
    elif matching_pairs:
        trust_comparison = "match-unverified-source"
    else:
        trust_comparison = "mismatch-unverified-source"
    trust_root = {
        "status": "not-verified",
        "comparison": trust_comparison,
        "source": (
            "package-espefuse-json-unverified"
            if efuse is not None
            else "not-included"
        ),
        "matching_pairs": matching_pairs,
        "not_claimed": [
            "package-provided eFuse summary authenticity",
            "live eFuse read from the target device",
            "hardware secure-boot execution",
        ],
    }
    image_secure_version = descriptor.get("secure_version")
    efuse_secure_version = (
        efuse.get("secure_version") if efuse is not None else None
    )
    if not isinstance(image_secure_version, int):
        rollback_comparison = "image-secure-version-unavailable"
    elif efuse is None:
        rollback_comparison = "efuse-summary-not-included"
    elif not isinstance(efuse_secure_version, int):
        rollback_comparison = "efuse-secure-version-unavailable"
    elif image_secure_version < efuse_secure_version:
        rollback_comparison = "image-below-efuse-unverified-source"
    else:
        rollback_comparison = "image-satisfies-efuse-unverified-source"
    anti_rollback = {
        "status": "not-verified",
        "comparison": rollback_comparison,
        "source": (
            "package-espefuse-json-unverified"
            if efuse is not None
            else "not-included"
        ),
        "image_secure_version": (
            image_secure_version
            if isinstance(image_secure_version, int)
            else None
        ),
        "efuse_secure_version": (
            efuse_secure_version
            if isinstance(efuse_secure_version, int)
            else None
        ),
        "not_claimed": [
            "package-provided eFuse summary authenticity",
            "live eFuse read from the target device",
            "bootloader anti-rollback enforcement",
        ],
    }
    return {
        "secure_boot": secure_boot,
        "secure_boot_image": secure_boot_image,
        "trust_root": trust_root,
        "anti_rollback": anti_rollback,
        "flash_encryption": flash_encryption,
        "secure_boot_config": configured_secure_boot,
        "flash_encryption_config": configured_flash_encryption,
        "efuse": "summary-included" if efuse is not None else "not-included",
        "efuse_summary": efuse,
        "secure_version": (
            image_secure_version
            if isinstance(image_secure_version, int)
            else None
        ),
        "sdkconfig_available": bool(config),
    }


def _sdkconfig_flags(config: str) -> dict[str, str]:
    flags = {}
    for raw_line in config.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.startswith("CONFIG_"):
            flags[key] = value.strip().strip('"')
    return flags


def _configured_secure_boot(flags: dict[str, str]) -> str:
    if flags.get("CONFIG_SECURE_BOOT_V2_ENABLED") == "y":
        return "v2"
    if flags.get("CONFIG_SECURE_BOOT_V1_ENABLED") == "y":
        return "v1"
    if flags.get("CONFIG_SECURE_BOOT") == "y":
        return "enabled-unspecified"
    if flags.get("CONFIG_SECURE_BOOT") == "n":
        return "disabled"
    return "not-indicated" if flags else "unknown"


def _efuse_field(
    document: dict[str, Any],
    name: str,
) -> dict[str, Any] | None:
    value = document.get(name)
    if not isinstance(value, dict) or value.get("readable") is False:
        return None
    return value


def _efuse_bool(
    document: dict[str, Any],
    name: str,
) -> bool | None:
    field = _efuse_field(document, name)
    if field is None:
        return None
    value = field.get("value")
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "enable", "enabled", "1"}:
            return True
        if normalized in {"false", "disable", "disabled", "0"}:
            return False
    return None


def _efuse_int(
    document: dict[str, Any],
    name: str,
) -> int | None:
    field = _efuse_field(document, name)
    if field is None:
        return None
    value = field.get("value")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def _efuse_text(
    document: dict[str, Any],
    name: str,
) -> str | None:
    field = _efuse_field(document, name)
    if field is None:
        return None
    value = field.get("value")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _efuse_sha256(
    document: dict[str, Any],
    name: str,
) -> str | None:
    field = _efuse_field(document, name)
    if field is None:
        return None
    value = field.get("value")
    if not isinstance(value, str):
        value = field.get("raw_value")
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[\s:_-]", "", value.strip().lower())
    normalized = normalized.removeprefix("0x")
    if len(normalized) != 64 or any(
        char not in "0123456789abcdef" for char in normalized
    ):
        return None
    return normalized


def _parse_efuse_security(
    document: dict[str, Any] | None,
    source: Path | None,
) -> dict[str, Any] | None:
    if document is None:
        return None
    secure_boot_v1 = _efuse_bool(document, "ABS_DONE_0")
    secure_boot_v2 = _efuse_bool(document, "ABS_DONE_1")
    secure_boot_en = _efuse_bool(document, "SECURE_BOOT_EN")
    if secure_boot_v2 is True:
        secure_boot = "v2"
    elif secure_boot_v1 is True:
        secure_boot = "v1"
    elif secure_boot_en is True:
        secure_boot = "enabled-unspecified"
    elif any(
        value is False
        for value in (
            secure_boot_v1,
            secure_boot_v2,
            secure_boot_en,
        )
    ):
        secure_boot = "disabled"
    else:
        secure_boot = "unknown"

    flash_crypt = _efuse_text(document, "SPI_BOOT_CRYPT_CNT")
    if flash_crypt is None:
        flash_encryption = "unknown"
    elif flash_crypt.lower() in {"enable", "enabled"}:
        flash_encryption = "enabled"
    elif flash_crypt.lower() in {"disable", "disabled"}:
        flash_encryption = "disabled"
    else:
        flash_encryption = "unknown"

    purposes = []
    secure_boot_key_digests = []
    for index in range(8):
        purpose = _efuse_text(document, f"KEY_PURPOSE_{index}")
        if purpose is not None:
            purposes.append(
                {
                    "block": index,
                    "purpose": purpose,
                }
            )
            if purpose.upper().startswith("SECURE_BOOT_DIGEST"):
                digest = _efuse_sha256(
                    document,
                    f"BLOCK_KEY{index}",
                )
                if digest is not None:
                    secure_boot_key_digests.append(
                        {
                            "block": index,
                            "purpose": purpose,
                            "digest_sha256": digest,
                        }
                    )
    return {
        "source": "espefuse-json",
        "summary_sha256": (
            sha256_file(source)
            if source is not None and source.is_file()
            else None
        ),
        "field_count": len(document),
        "secure_boot": secure_boot,
        "flash_encryption": flash_encryption,
        "secure_version": _efuse_int(document, "SECURE_VERSION"),
        "write_protected": {
            "secure_boot": _efuse_bool(
                document,
                "WR_DIS_SECURE_BOOT_EN",
            ),
            "flash_encryption": _efuse_bool(
                document,
                "WR_DIS_SPI_BOOT_CRYPT_CNT",
            ),
        },
        "key_purposes": purposes,
        "secure_boot_key_digests": secure_boot_key_digests,
    }


def _copy_resource(
    resource_row: dict | None,
    *,
    source_root: Path,
    output_dir: Path,
) -> dict | None:
    if not resource_row:
        return None
    source = _resolve_package_file(source_root, resource_row["file"])
    destination = output_dir / source.name
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)
    return {
        "file": destination.name,
        "size": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }


def import_package(
    input_path: Path,
    output_dir: Path,
    *,
    device_id: str | None = None,
    flash_size: int | None = None,
    required_capabilities: list[str] | None = None,
    optional_capabilities: list[str] | None = None,
    allowed_licenses: list[str] | None = None,
    denied_licenses: list[str] | None = None,
) -> dict:
    input_path = input_path.resolve()
    required_capabilities = normalize_capability_declarations(
        required_capabilities,
        field="required_capabilities",
    )
    optional_capabilities = normalize_capability_declarations(
        optional_capabilities,
        field="optional_capabilities",
    )
    capability_overlap = sorted(
        set(required_capabilities) & set(optional_capabilities)
    )
    if capability_overlap:
        raise ManifestError(
            "capabilities cannot be both required and optional: "
            + ", ".join(capability_overlap)
        )
    if not input_path.exists():
        raise ManifestError(f"input does not exist: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar = _sidecar_for(input_path)
    resolved_device_id = device_id or _infer_device_id(sidecar)
    device_profile = (
        load_device_profile(resolved_device_id)
        if resolved_device_id
        else None
    )
    if resolved_device_id and device_profile is None:
        raise ManifestError(f"unknown device_id: {resolved_device_id}")
    expected_soc = (
        normalize_soc(device_profile.get("hardware", {}).get("soc"))
        if isinstance(device_profile, dict)
        else None
    )
    temporary = Path(tempfile.mkdtemp(prefix="m5-firmware-package-"))
    try:
        root = _package_root(input_path, temporary)
        web_manifest = _choose_web_manifest(root)
        flasher_args_candidates = sorted(
            path for path in root.rglob("flasher_args.json") if path.is_file()
        )
        if len(flasher_args_candidates) > 1:
            raise ManifestError(
                "package contains multiple flasher_args.json files"
            )
        flasher_args = (
            flasher_args_candidates[0]
            if flasher_args_candidates
            else None
        )
        if web_manifest is not None:
            segments, package_meta = _segments_from_web_manifest(
                root,
                _load_json(web_manifest),
                expected_soc=expected_soc,
            )
            source_format = package_meta["source_format"]
        elif flasher_args is not None:
            segments, package_meta = _segments_from_flasher_args(
                root,
                flasher_args,
            )
            source_format = package_meta["source_format"]
        else:
            candidates = (
                [input_path]
                if input_path.is_file()
                and input_path.suffix.lower() == ".bin"
                else _image_candidates(root)
            )
            if not candidates:
                raise ManifestError("package contains no firmware .bin")
            segments = [
                {
                    "offset": 0,
                    "path": candidates[0],
                    **resource(candidates[0], root=candidates[0].parent),
                }
            ]
            package_meta = {
                "source_format": "merged-bin",
                "chip": None,
                "name": sidecar.get("firmware_name"),
                "version": sidecar.get("resolved_version"),
            }
            source_format = "merged-bin"
        _segment_intervals(segments)
        source_size = max(end for _, end, _ in _segment_intervals(segments))
        # The header and partition table live in the first segment. Analysis is
        # done after composition so sparse public images are handled uniformly.
        declared_flash = max(
            [
                flash_size or 0,
                source_size,
            ]
        )
        if declared_flash < source_size:
            raise ManifestError("declared flash size is smaller than image")
        cap = max(declared_flash, 1 << 20)
        while cap < source_size:
            cap *= 2
        preliminary_path = temporary / "analyze.bin"
        _compose_segments(
            segments,
            flash_size=cap,
            output=preliminary_path,
        )
        preliminary_analysis = analyze_firmware(preliminary_path)
        inferred_flash = (
            flash_size
            or preliminary_analysis.get("declared_flash_size")
            or source_size
        )
        if inferred_flash < source_size:
            inferred_flash = source_size
        source_basename = (
            input_path.stem
            if input_path.is_file()
            else root.name
        )
        safe_stem = "".join(
            char if char.isalnum() or char in "._-" else "-"
            for char in source_basename
        ).strip("-") or "firmware"
        destination = output_dir / f"{safe_stem}-flash.bin"
        _compose_segments(
            segments,
            flash_size=inferred_flash,
            output=destination,
        )
        analysis = analyze_firmware(destination)
        if not analysis.get("valid"):
            raise ManifestError(
                "normalized flash image failed structural validation: "
                + "; ".join(analysis.get("errors", []))
            )
        resources = _find_resources(root)
        sdkconfig_path = (
            _resolve_package_file(root, resources["sdkconfig"]["file"])
            if "sdkconfig" in resources
            else None
        )
        efuse_summary_path = _find_efuse_summary(root)
        efuse_summary = (
            _load_efuse_summary(efuse_summary_path)
            if efuse_summary_path is not None
            else None
        )
        sdkconfig_flags = (
            _sdkconfig_flags(sdkconfig_path.read_text(errors="replace"))
            if sdkconfig_path is not None and sdkconfig_path.is_file()
            else {}
        )
        detected_capabilities = detect_sdkconfig_capabilities(sdkconfig_flags)
        observed_capabilities, capability_observation = (
            detect_image_capabilities(destination)
        )
        copied_resources = {
            key: _copy_resource(
                row,
                source_root=root,
                output_dir=output_dir,
            )
            for key, row in resources.items()
        }
        sbom_path = (
            _resolve_package_file(root, resources["sbom"]["file"])
            if "sbom" in resources
            else None
        )
        review = review_firmware(destination, sbom_path=sbom_path)
        source_license_scan = scan_source_licenses(root)
        source_digest = sha256_file(destination)
        artifact = {
            "kind": (
                "segmented-flash"
                if len(segments) > 1
                else "merged-flash"
            ),
            "file": destination.name,
            "artifact_id": source_digest,
            "size": destination.stat().st_size,
            "sha256": source_digest,
            "source_size": source_size,
            "source_sha256": (
                sha256_file(segments[0]["path"])
                if len(segments) == 1
                else canonical_json_sha256(
                    [
                        {
                            "offset": row["offset"],
                            "sha256": row["sha256"],
                            "size": row["size"],
                        }
                        for row in segments
                    ]
                )
            ),
            "padded": destination.stat().st_size != source_size,
        }
        if len(segments) > 1:
            normalized_segments = []
            for index, row in enumerate(segments):
                source = Path(row["path"])
                segment_path = output_dir / (
                    f"segment-{index:02d}-{source.name}"
                )
                if source.resolve() != segment_path.resolve():
                    shutil.copyfile(source, segment_path)
                normalized_segments.append(
                    {
                        "offset": row["offset"],
                        "file": segment_path.name,
                        "size": segment_path.stat().st_size,
                        "sha256": sha256_file(segment_path),
                        "artifact_id": row["sha256"],
                        **(
                            {
                                "declared_integrity": row[
                                    "declared_integrity"
                                ],
                            }
                            if "declared_integrity" in row
                            else {}
                        ),
                    }
                )
            artifact["segments"] = normalized_segments
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": "m5stack-firmware-manifest",
            "created_at": utc_now(),
            "device_id": resolved_device_id,
            "artifact": artifact,
            "target": {
                "soc": (
                    normalize_soc(package_meta.get("chip"))
                    or analysis.get("bootloader", {}).get("chip")
                ),
                "chip_id": analysis.get("bootloader", {}).get("chip_id"),
                "flash_size": inferred_flash,
                "psram_size": None,
                "partition_table": analysis.get("partition_table"),
                "application": analysis.get("app_descriptor"),
                "filesystems": analysis.get("filesystems", []),
            },
            "security": _security_metadata(
                analysis,
                sdkconfig_path,
                efuse_summary,
                efuse_summary_path,
            ),
            "provenance": {
                "importer": "m5stack-firmware-manifest/1",
                "source_format": source_format,
                "source_url": sidecar.get("source_url") or sidecar.get("url"),
                "source_type": sidecar.get("source_type"),
                "firmware_id": sidecar.get("firmware_id"),
                "name": (
                    sidecar.get("firmware_name")
                    or package_meta.get("name")
                ),
                "version": (
                    sidecar.get("resolved_version")
                    or package_meta.get("version")
                ),
                "license": sidecar.get("license"),
                "source_sha256": artifact["source_sha256"],
            },
            "resources": {
                key: value
                for key, value in copied_resources.items()
                if value is not None
            },
            "capabilities": {
                "required": required_capabilities,
                "optional": optional_capabilities,
                "detected": detected_capabilities,
                "observed": observed_capabilities,
                "observation": capability_observation,
            },
            "review": review,
            "source_license_scan": source_license_scan,
            "license_policy": evaluate_license_policy(
                {
                    "target": {
                        "filesystems": analysis.get("filesystems", []),
                    },
                    "provenance": {
                        "license": sidecar.get("license"),
                    },
                    "review": review,
                    "source_license_scan": source_license_scan,
                },
                allowed_licenses=allowed_licenses,
                denied_licenses=denied_licenses,
            ),
            "validation": {
                "status": "PASS",
                "errors": [],
                "warnings": [],
            },
        }
        license_policy = manifest["license_policy"]
        if license_policy["status"] == "REJECTED":
            manifest["validation"]["status"] = "REJECTED"
            manifest["validation"]["errors"].append(
                _code_issues(
                    "license_policy_rejected",
                    "one or more declared licenses violate the policy",
                    path="license_policy",
                )
            )
        elif license_policy["status"] == "REVIEW_REQUIRED":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "license_policy_review_required",
                    (
                        "license declarations require policy review; "
                        "no legal conclusion was inferred"
                    ),
                    path="license_policy",
                )
            )
        if manifest["security"]["efuse"] == "summary-included":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "efuse_summary_unverified",
                    (
                        "package-provided eFuse summary is self-asserted and "
                        "was not independently read from hardware"
                    ),
                    path="security.efuse_summary",
                )
            )
        else:
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "security_metadata_incomplete",
                    (
                        "eFuse and runtime security state are not embedded "
                        "in a flash image"
                    ),
                    path="security",
                )
            )
        security = manifest["security"]
        if (
            security["secure_boot_config"]
            in {"v1", "v2", "enabled-unspecified"}
            and security["secure_boot"] in {"disabled", "not-indicated"}
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_config_not_enabled",
                    (
                        "sdkconfig enables secure boot but the supplied "
                        "security evidence does not indicate an enabled "
                        "boot chain"
                    ),
                    path="security.secure_boot",
                )
            )
        if (
            security["secure_boot_config"] == "disabled"
            and security["secure_boot"]
            in {"v1", "v2", "enabled-unspecified"}
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_config_disabled_but_runtime_enabled",
                    (
                        "sdkconfig disables secure boot but the supplied "
                        "eFuse evidence indicates an enabled boot chain"
                    ),
                    path="security.secure_boot",
                )
            )
        if (
            security["secure_boot_config"] in {"v1", "v2"}
            and security["secure_boot"] in {"v1", "v2"}
            and security["secure_boot_config"] != security["secure_boot"]
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_mode_mismatch",
                    (
                        "sdkconfig and the supplied eFuse evidence name "
                        "different secure-boot modes"
                    ),
                    requirement=security["secure_boot_config"],
                    available=security["secure_boot"],
                    path="security.secure_boot",
                )
            )
        if (
            security["flash_encryption_config"] == "enabled"
            and security["flash_encryption"] in {"disabled", "not-indicated"}
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "flash_encryption_config_not_enabled",
                    (
                        "sdkconfig enables Flash Encryption but the supplied "
                        "security evidence does not indicate it is active"
                    ),
                    path="security.flash_encryption",
                )
            )
        if (
            security["flash_encryption_config"] == "disabled"
            and security["flash_encryption"] == "enabled"
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "flash_encryption_config_disabled_but_runtime_enabled",
                    (
                        "sdkconfig disables Flash Encryption but the supplied "
                        "eFuse evidence indicates it is active"
                    ),
                    path="security.flash_encryption",
                )
            )
        efuse_summary = security.get("efuse_summary")
        if isinstance(efuse_summary, dict):
            key_purposes = {
                str(row.get("purpose") or "").upper()
                for row in efuse_summary.get("key_purposes", [])
                if isinstance(row, dict)
            }
            if (
                security["secure_boot"] in {"v1", "v2"}
                and not any(
                    purpose.startswith("SECURE_BOOT_DIGEST")
                    for purpose in key_purposes
                )
            ):
                manifest["validation"]["warnings"].append(
                    _code_issues(
                        "secure_boot_key_purpose_not_observed",
                        (
                            "secure boot is indicated, but no readable "
                            "SECURE_BOOT_DIGEST key purpose was recorded"
                        ),
                        path="security.efuse_summary.key_purposes",
                    )
                )
            if (
                security["flash_encryption"] == "enabled"
                and not any(
                    "XTS_AES" in purpose or purpose == "XTS_AES"
                    for purpose in key_purposes
                )
            ):
                manifest["validation"]["warnings"].append(
                    _code_issues(
                        "flash_encryption_key_purpose_not_observed",
                        (
                            "Flash Encryption is indicated, but no readable "
                            "XTS AES key purpose was recorded"
                        ),
                        path="security.efuse_summary.key_purposes",
                    )
                )
        secure_boot_image = security.get("secure_boot_image") or {}
        secure_boot_image_status = secure_boot_image.get("status")
        if secure_boot_image_status == "invalid":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_v2_image_signature_invalid",
                    (
                        "a Secure Boot v2 signature sector was observed but "
                        "its block CRC, image digest or supported RSA-PSS "
                        "signature did not validate"
                    ),
                    path="security.secure_boot_image",
                )
            )
        elif secure_boot_image_status == "signed-image-observed":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_v2_image_signature_authenticity_unverified",
                    (
                        "signature-sector structure and image digest match; "
                        "any public-key digest match is against a "
                        "self-asserted package eFuse summary, not a live "
                        "hardware trust root"
                    ),
                    path="security.secure_boot_image",
                )
            )
            if any(
                block.get("signature_math") == "not-implemented"
                for image in secure_boot_image.get("images", [])
                if isinstance(image, dict)
                for block in image.get("blocks", [])
                if isinstance(block, dict)
            ):
                manifest["validation"]["warnings"].append(
                    _code_issues(
                        "secure_boot_v2_image_signature_math_not_verified",
                        (
                            "one or more ECDSA signature blocks were parsed "
                            "but mathematical signature verification is not "
                            "implemented"
                        ),
                        path="security.secure_boot_image",
                    )
                )
            trust_root = security.get("trust_root")
            if (
                isinstance(trust_root, dict)
                and trust_root.get("comparison")
                == "mismatch-unverified-source"
            ):
                manifest["validation"]["warnings"].append(
                    _code_issues(
                        "secure_boot_v2_image_public_key_digest_mismatch",
                        (
                            "signed-image public-key digests do not match "
                            "the package-provided eFuse secure-boot digest "
                            "summary; the summary itself remains unverified"
                        ),
                        path="security.trust_root",
                    )
                )
        anti_rollback = security.get("anti_rollback")
        if (
            isinstance(anti_rollback, dict)
            and anti_rollback.get("comparison")
            == "image-below-efuse-unverified-source"
            and security["secure_boot"]
            in {"v1", "v2", "enabled-unspecified"}
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_image_secure_version_below_efuse",
                    (
                        "application secure_version is below the "
                        "package-provided eFuse secure_version; the summary "
                        "remains unverified"
                    ),
                    path="security.anti_rollback",
                )
            )
        if (
            security["secure_boot"] == "v2"
            and secure_boot_image_status not in {
                "signed-image-observed",
                "invalid",
            }
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "secure_boot_v2_image_signature_not_observed",
                    (
                        "Secure Boot v2 is indicated by config/eFuse evidence "
                        "but no digest-matching v2 signature sector was parsed "
                        "from the bootloader or application image"
                    ),
                    path="security.secure_boot_image",
                )
            )
        if review["status"] == "REVIEW_REQUIRED":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "static_review_required",
                    (
                        f"static review produced "
                        f"{len(review['findings'])} finding(s); values are "
                        "redacted in the manifest"
                    ),
                    path="review.findings",
                )
            )
        filesystems = manifest["target"].get("filesystems", [])
        unavailable_filesystems = [
            row
            for row in filesystems
            if row.get("status")
            in {
                "UNAVAILABLE",
                "UNSUPPORTED",
                "UNFORMATTED",
                "INVALID",
                "PARTIAL",
            }
        ]
        if unavailable_filesystems:
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "filesystem_inventory_incomplete",
                    (
                        "one or more data filesystems could not be fully "
                        "inventoried"
                    ),
                    path="target.filesystems",
                )
            )
        sensitive_files = [
            file
            for filesystem in filesystems
            for file in filesystem.get("sensitive_files", [])
        ]
        if sensitive_files:
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "filesystem_sensitive_file",
                    (
                        f"{len(sensitive_files)} sensitive-looking "
                        "filesystem path(s) require review"
                    ),
                    path="target.filesystems",
                )
            )
            review.setdefault("findings", []).extend(
                {
                    "code": "filesystem_sensitive_path",
                    "category": "filesystem",
                    "severity": "warning",
                    "message": (
                        "sensitive-looking filesystem path; path and content "
                        "are represented by hashes"
                    ),
                    "path_sha256": file["path_sha256"],
                    "evidence_sha256": file["sha256"],
                }
                for file in sensitive_files[:64]
            )
            review["status"] = "REVIEW_REQUIRED"
        if any(
            row.get("limits", {}).get("files_truncated")
            or row.get("limits", {}).get("directories_truncated")
            for row in filesystems
        ):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "filesystem_inventory_truncated",
                    "filesystem inventory reached a listing limit",
                    path="target.filesystems",
                )
            )
        if review["sbom"]["status"] == "NOT_PROVIDED":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "sbom_not_provided",
                    "package does not include a recognized SPDX/CycloneDX SBOM",
                    path="review.sbom",
                )
            )
        elif review["sbom"]["status"] != "PASS":
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "sbom_invalid",
                    "package SBOM could not be summarized",
                    path="review.sbom",
                )
            )
        if any(review["limits"].values()):
            manifest["validation"]["warnings"].append(
                _code_issues(
                    "static_review_truncated",
                    "one or more static-review limits were reached",
                    path="review.limits",
                )
            )
        if device_profile is not None:
            capability = validate_capabilities(manifest, device_profile)
            manifest["validation"]["errors"].extend(capability["errors"])
            manifest["validation"]["warnings"].extend(capability["warnings"])
            if capability["status"] == "REJECTED":
                manifest["validation"]["status"] = "REJECTED"
        manifest["manifest_id"] = canonical_json_sha256(
            manifest_identity_payload(manifest)
        )
        manifest_path = output_dir / f"{destination.stem}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        )
        return {
            "manifest": manifest,
            "manifest_path": str(manifest_path),
            "image_path": str(destination),
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def validate_manifest_structure(manifest: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest.schema_version must be 1")
    if manifest.get("kind") != "m5stack-firmware-manifest":
        errors.append("manifest.kind is invalid")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        errors.append("manifest.artifact must be an object")
    else:
        if artifact.get("kind") not in {
            "merged-flash",
            "segmented-flash",
        }:
            errors.append("manifest.artifact.kind is invalid")
        if not isinstance(artifact.get("file"), str):
            errors.append("manifest.artifact.file is required")
        if (
            not isinstance(artifact.get("size"), int)
            or artifact.get("size", 0) <= 0
        ):
            errors.append("manifest.artifact.size must be positive")
        digest = artifact.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            errors.append("manifest.artifact.sha256 is invalid")
        segments = artifact.get("segments")
        if segments is not None:
            if not isinstance(segments, list) or not segments:
                errors.append(
                    "manifest.artifact.segments must be a non-empty array"
                )
            else:
                for index, segment in enumerate(segments):
                    prefix = f"manifest.artifact.segments[{index}]"
                    if not isinstance(segment, dict):
                        errors.append(f"{prefix} must be an object")
                        continue
                    if (
                        not isinstance(segment.get("offset"), int)
                        or segment.get("offset", -1) < 0
                    ):
                        errors.append(f"{prefix}.offset is invalid")
                    if not isinstance(segment.get("file"), str):
                        errors.append(f"{prefix}.file is required")
                    if (
                        not isinstance(segment.get("size"), int)
                        or segment.get("size", 0) <= 0
                    ):
                        errors.append(f"{prefix}.size must be positive")
                    segment_digest = segment.get("sha256")
                    if (
                        not isinstance(segment_digest, str)
                        or len(segment_digest) != 64
                        or any(
                            char not in "0123456789abcdef"
                            for char in segment_digest
                        )
                    ):
                        errors.append(f"{prefix}.sha256 is invalid")
                    declared_integrity = segment.get("declared_integrity")
                    if declared_integrity is None:
                        continue
                    if (
                        not isinstance(declared_integrity, dict)
                        or set(declared_integrity)
                        != {"status", "algorithms", "weak_digest"}
                        or declared_integrity.get("status") != "verified"
                        or not isinstance(
                            declared_integrity.get("algorithms"),
                            list,
                        )
                        or not declared_integrity.get("algorithms")
                        or set(declared_integrity.get("algorithms", []))
                        - {"size", "sha256", "sha1", "md5"}
                        or len(set(declared_integrity.get("algorithms", [])))
                        != len(declared_integrity.get("algorithms", []))
                        or not isinstance(
                            declared_integrity.get("weak_digest"),
                            bool,
                        )
                    ):
                        errors.append(
                            f"{prefix}.declared_integrity is invalid"
                        )
    target = manifest.get("target")
    if not isinstance(target, dict):
        errors.append("manifest.target must be an object")
    else:
        if normalize_soc(target.get("soc")) is None:
            errors.append("manifest.target.soc is unsupported")
        if (
            not isinstance(target.get("flash_size"), int)
            or target.get("flash_size", 0) <= 0
        ):
            errors.append("manifest.target.flash_size must be positive")
    security = manifest.get("security")
    if not isinstance(security, dict):
        errors.append("manifest.security must be an object")
    else:
        for key in ("secure_boot", "flash_encryption", "efuse"):
            if key not in security:
                errors.append(f"manifest.security.{key} is required")
        if security.get("secure_boot") not in SECURE_BOOT_VALUES:
            errors.append("manifest.security.secure_boot is invalid")
        if (
            security.get("flash_encryption")
            not in FLASH_ENCRYPTION_VALUES
        ):
            errors.append(
                "manifest.security.flash_encryption is invalid"
            )
        if (
            not isinstance(security.get("efuse"), str)
            or not security.get("efuse")
        ):
            errors.append("manifest.security.efuse is invalid")
        if (
            "secure_boot_config" in security
            and security.get("secure_boot_config")
            not in SECURE_BOOT_CONFIG_VALUES
        ):
            errors.append(
                "manifest.security.secure_boot_config is invalid"
            )
        if (
            "flash_encryption_config" in security
            and security.get("flash_encryption_config")
            not in FLASH_ENCRYPTION_CONFIG_VALUES
        ):
            errors.append(
                "manifest.security.flash_encryption_config is invalid"
            )
        efuse_summary = security.get("efuse_summary")
        if efuse_summary is not None:
            if not isinstance(efuse_summary, dict):
                errors.append(
                    "manifest.security.efuse_summary must be an object"
                )
            else:
                for field in ("secure_boot", "flash_encryption"):
                    if field not in efuse_summary:
                        errors.append(
                            "manifest.security.efuse_summary."
                            f"{field} is required"
                        )
                if (
                    efuse_summary.get("secure_boot")
                    not in SECURE_BOOT_VALUES
                ):
                    errors.append(
                        "manifest.security.efuse_summary.secure_boot "
                        "is invalid"
                    )
                if (
                    efuse_summary.get("flash_encryption")
                    not in FLASH_ENCRYPTION_VALUES
                ):
                    errors.append(
                        "manifest.security.efuse_summary.flash_encryption "
                        "is invalid"
                    )
                secure_version = efuse_summary.get("secure_version")
                if (
                    secure_version is not None
                    and (
                        not isinstance(secure_version, int)
                        or isinstance(secure_version, bool)
                        or secure_version < 0
                    )
                ):
                    errors.append(
                        "manifest.security.efuse_summary.secure_version "
                        "is invalid"
                    )
        trust_root = security.get("trust_root")
        if trust_root is not None:
            if not isinstance(trust_root, dict):
                errors.append(
                    "manifest.security.trust_root must be an object"
                )
            else:
                if trust_root.get("status") != "not-verified":
                    errors.append(
                        "manifest.security.trust_root must not claim "
                        "a verified trust root"
                    )
                if trust_root.get("comparison") not in {
                    "not-applicable",
                    "efuse-summary-not-included",
                    "efuse-key-digest-unavailable",
                    "match-unverified-source",
                    "mismatch-unverified-source",
                }:
                    errors.append(
                        "manifest.security.trust_root.comparison is invalid"
                    )
                if trust_root.get("source") not in {
                    "package-espefuse-json-unverified",
                    "not-included",
                }:
                    errors.append(
                        "manifest.security.trust_root.source is invalid"
                    )
                matching_pairs = trust_root.get("matching_pairs")
                if not isinstance(matching_pairs, list):
                    errors.append(
                        "manifest.security.trust_root.matching_pairs must be "
                        "an array"
                    )
                else:
                    for pair in matching_pairs:
                        digest = (
                            pair.get("public_key_digest_sha256")
                            if isinstance(pair, dict)
                            else None
                        )
                        if (
                            not isinstance(pair, dict)
                            or not isinstance(pair.get("image"), str)
                            or not pair["image"]
                            or not isinstance(digest, str)
                            or len(digest) != 64
                            or any(
                                char not in "0123456789abcdef"
                                for char in digest
                            )
                        ):
                            errors.append(
                                "manifest.security.trust_root.matching_pairs "
                                "is invalid"
                            )
                            break
                not_claimed = trust_root.get("not_claimed")
                if (
                    not isinstance(not_claimed, list)
                    or not not_claimed
                    or any(
                        not isinstance(value, str) or not value
                        for value in not_claimed
                    )
                ):
                    errors.append(
                        "manifest.security.trust_root.not_claimed is invalid"
                    )
        anti_rollback = security.get("anti_rollback")
        if anti_rollback is not None:
            if not isinstance(anti_rollback, dict):
                errors.append(
                    "manifest.security.anti_rollback must be an object"
                )
            else:
                if anti_rollback.get("status") != "not-verified":
                    errors.append(
                        "manifest.security.anti_rollback must not claim "
                        "verified runtime enforcement"
                    )
                if anti_rollback.get("comparison") not in {
                    "image-secure-version-unavailable",
                    "efuse-summary-not-included",
                    "efuse-secure-version-unavailable",
                    "image-below-efuse-unverified-source",
                    "image-satisfies-efuse-unverified-source",
                }:
                    errors.append(
                        "manifest.security.anti_rollback.comparison is invalid"
                    )
                if anti_rollback.get("source") not in {
                    "package-espefuse-json-unverified",
                    "not-included",
                }:
                    errors.append(
                        "manifest.security.anti_rollback.source is invalid"
                    )
                for key in (
                    "image_secure_version",
                    "efuse_secure_version",
                ):
                    value = anti_rollback.get(key)
                    if value is not None and not isinstance(value, int):
                        errors.append(
                            f"manifest.security.anti_rollback.{key} is invalid"
                        )
                not_claimed = anti_rollback.get("not_claimed")
                if (
                    not isinstance(not_claimed, list)
                    or not not_claimed
                    or any(
                        not isinstance(value, str) or not value
                        for value in not_claimed
                    )
                ):
                    errors.append(
                        "manifest.security.anti_rollback.not_claimed is invalid"
                    )
        secure_boot_image = security.get("secure_boot_image")
        if secure_boot_image is not None:
            if not isinstance(secure_boot_image, dict):
                errors.append(
                    "manifest.security.secure_boot_image must be an object"
                )
            else:
                if secure_boot_image.get("status") not in {
                    "not-found",
                    "signed-image-observed",
                    "invalid",
                }:
                    errors.append(
                        "manifest.security.secure_boot_image.status is invalid"
                    )
                if (
                    secure_boot_image.get("signature_authenticity")
                    != "not-verified"
                ):
                    errors.append(
                        "manifest.security.secure_boot_image must not claim "
                        "verified signature authenticity"
                    )
                if secure_boot_image.get("trust_root") != "not-verified":
                    errors.append(
                        "manifest.security.secure_boot_image must not claim "
                        "a verified trust root"
                    )
                if not isinstance(secure_boot_image.get("images"), list):
                    errors.append(
                        "manifest.security.secure_boot_image.images must be "
                        "an array"
                    )
                else:
                    for image in secure_boot_image["images"]:
                        if not isinstance(image, dict):
                            errors.append(
                                "manifest.security.secure_boot_image.images "
                                "must contain objects"
                            )
                            continue
                        for block in image.get("blocks", []):
                            if (
                                not isinstance(block, dict)
                                or block.get("signature_math")
                                not in {
                                    "valid",
                                    "invalid",
                                    "not-implemented",
                                }
                                or not (
                                    isinstance(
                                        block.get("signature_math_valid"),
                                        bool,
                                    )
                                    or block.get("signature_math_valid") is None
                                )
                            ):
                                errors.append(
                                    "manifest.security.secure_boot_image "
                                    "signature_math is invalid"
                                )
                                break
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("manifest.capabilities is required")
    else:
        unknown = set(capabilities) - {
            "required",
            "optional",
            "detected",
            "observed",
            "observation",
        }
        if unknown:
            errors.append("manifest.capabilities contains unknown fields")
        for key in ("required", "optional"):
            if key not in capabilities:
                errors.append(
                    f"manifest.capabilities.{key} is required"
                )
        for key in ("required", "optional", "detected"):
            if key in capabilities and not isinstance(
                capabilities[key],
                list,
            ):
                errors.append(
                    f"manifest.capabilities.{key} must be an array"
                )
            for key in ("required", "optional"):
                values = capabilities.get(key, [])
                if isinstance(values, list):
                    if len(values) > 64:
                        errors.append(
                            f"manifest.capabilities.{key} exceeds 64 entries"
                        )
                    if any(
                        not isinstance(value, str)
                        or not value
                        or len(value) > 64
                        for value in values
                    ):
                        errors.append(
                            f"manifest.capabilities.{key} must contain "
                            "strings of 1 to 64 characters"
                        )
            required_values = capabilities.get("required", [])
            optional_values = capabilities.get("optional", [])
            if isinstance(required_values, list) and isinstance(
                optional_values,
                list,
            ):
                required_set = {
                    CAPABILITY_ALIASES.get(value.strip().lower(), value.strip().lower())
                    for value in required_values
                    if isinstance(value, str) and value.strip()
                }
                optional_set = {
                    CAPABILITY_ALIASES.get(value.strip().lower(), value.strip().lower())
                    for value in optional_values
                    if isinstance(value, str) and value.strip()
                }
                if required_set & optional_set:
                    errors.append(
                        "manifest.capabilities.required and optional overlap"
                    )
            detections = capabilities.get("detected", [])
            if isinstance(detections, list) and any(
                not isinstance(item, dict)
                or not isinstance(item.get("capability"), str)
                or item.get("source") != "sdkconfig"
                or not isinstance(item.get("flag"), str)
                for item in detections
            ):
                errors.append(
                    "manifest.capabilities.detected entries are invalid"
                )
            observations = capabilities.get("observed", [])
            if isinstance(observations, list) and any(
                not isinstance(item, dict)
                or set(item)
                - {
                    "capability",
                    "source",
                    "confidence",
                    "signatures",
                }
                or not isinstance(item.get("capability"), str)
                or item.get("source") != "image-signature"
                or item.get("confidence") != "low"
                or not isinstance(item.get("signatures"), list)
                or not item.get("signatures")
                or len(item.get("signatures", [])) > 8
                or any(
                    not isinstance(signature, str)
                    or not signature
                    or len(signature) > 64
                    for signature in item.get("signatures", [])
                )
                or len(set(item.get("signatures", [])))
                != len(item.get("signatures", []))
                for item in observations
            ):
                errors.append(
                    "manifest.capabilities.observed entries are invalid"
                )
            observation = capabilities.get("observation")
            if observation is not None and (
                not isinstance(observation, dict)
                or observation.get("status") not in {
                    "SCANNED",
                    "TRUNCATED",
                }
                or observation.get("source") != "normalized-flash"
                or not isinstance(observation.get("bytes_total"), int)
                or not isinstance(observation.get("bytes_scanned"), int)
                or observation["bytes_total"] <= 0
                or not 0
                < observation["bytes_scanned"]
                <= observation["bytes_total"]
                or not isinstance(observation.get("truncated"), bool)
                or observation.get("truncated")
                != (observation.get("status") == "TRUNCATED")
            ):
                errors.append(
                    "manifest.capabilities.observation is invalid"
                )
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("manifest.provenance must be an object")
    review = manifest.get("review")
    if review is not None and not isinstance(review, dict):
        errors.append("manifest.review must be an object when present")
    elif isinstance(review, dict):
        if review.get("schema_version") != 1:
            errors.append("manifest.review.schema_version must be 1")
        if review.get("status") not in {"CLEAN", "REVIEW_REQUIRED"}:
            errors.append("manifest.review.status is invalid")
        for key in (
            "coverage",
            "findings",
            "urls",
            "encoded_blobs",
            "sbom",
            "limits",
        ):
            expected = list if key in {"findings", "urls", "encoded_blobs"} else dict
            if not isinstance(review.get(key), expected):
                errors.append(f"manifest.review.{key} has invalid type")
    license_policy = manifest.get("license_policy")
    source_license_scan = manifest.get("source_license_scan")
    if source_license_scan is not None:
        if not isinstance(source_license_scan, dict):
            errors.append("manifest.source_license_scan must be an object")
        else:
            if source_license_scan.get("schema_version") != 1:
                errors.append(
                    "manifest.source_license_scan.schema_version must be 1"
                )
            if source_license_scan.get("status") not in {
                "PASS",
                "PARTIAL",
                "NOT_PROVIDED",
            }:
                errors.append(
                    "manifest.source_license_scan.status is invalid"
                )
            for key in ("files", "not_claimed"):
                if not isinstance(source_license_scan.get(key), list):
                    errors.append(
                        f"manifest.source_license_scan.{key} has invalid type"
                    )
            for key in ("limits", "coverage"):
                if not isinstance(source_license_scan.get(key), dict):
                    errors.append(
                        f"manifest.source_license_scan.{key} has invalid type"
                    )
    if license_policy is not None:
        if not isinstance(license_policy, dict):
            errors.append("manifest.license_policy must be an object")
        else:
            if license_policy.get("schema_version") != 1:
                errors.append(
                    "manifest.license_policy.schema_version must be 1"
                )
            if license_policy.get("status") not in {
                "PASS",
                "REVIEW_REQUIRED",
                "REJECTED",
            }:
                errors.append(
                    "manifest.license_policy.status is invalid"
                )
            for key in (
                "allowed_licenses",
                "denied_licenses",
                "discovered_licenses",
                "sources",
                "findings",
                "limits",
            ):
                if not isinstance(license_policy.get(key), list):
                    errors.append(
                        f"manifest.license_policy.{key} has invalid type"
                    )
            if not isinstance(license_policy.get("coverage"), dict):
                errors.append(
                    "manifest.license_policy.coverage has invalid type"
                )
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("status") not in {
        "PASS",
        "REJECTED",
    }:
        errors.append("manifest.validation.status is invalid")
    else:
        for key in ("errors", "warnings"):
            if not isinstance(validation.get(key), list):
                errors.append(
                    f"manifest.validation.{key} must be an array"
                )
        if (
            isinstance(license_policy, dict)
            and license_policy.get("status") == "REJECTED"
            and validation.get("status") != "REJECTED"
        ):
            errors.append(
                "manifest.validation.status must be REJECTED when "
                "license_policy.status is REJECTED"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize a WebBurner/M5Burner merged or segmented package "
            "into a validated v1 firmware manifest"
        )
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device-id")
    parser.add_argument("--flash-size")
    parser.add_argument("--require-capability", action="append", default=[])
    parser.add_argument("--optional-capability", action="append", default=[])
    parser.add_argument("--allow-license", action="append", default=[])
    parser.add_argument("--deny-license", action="append", default=[])
    parser.add_argument(
        "--print",
        choices=("summary", "manifest"),
        default="summary",
    )
    args = parser.parse_args()
    flash_size = int(args.flash_size, 0) if args.flash_size else None
    try:
        result = import_package(
            args.input,
            args.out_dir,
            device_id=args.device_id,
            flash_size=flash_size,
            required_capabilities=args.require_capability,
            optional_capabilities=args.optional_capability,
            allowed_licenses=args.allow_license,
            denied_licenses=args.deny_license,
        )
    except ManifestError as error:
        parser.error(str(error))
    validation_status = result["manifest"]["validation"]["status"]
    if args.print == "manifest":
        print(json.dumps(result["manifest"], ensure_ascii=False, indent=2))
    else:
        manifest = result["manifest"]
        print(
            json.dumps(
                {
                    "status": validation_status,
                    "image": result["image_path"],
                    "manifest": result["manifest_path"],
                    "manifest_id": manifest["manifest_id"],
                    "artifact_sha256": manifest["artifact"]["sha256"],
                    "flash_size": manifest["target"]["flash_size"],
                    "soc": manifest["target"]["soc"],
                    "source_format": manifest["provenance"]["source_format"],
                    "errors": manifest["validation"]["errors"],
                    "warnings": manifest["validation"]["warnings"],
                },
                indent=2,
            )
        )
    return 0 if validation_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
