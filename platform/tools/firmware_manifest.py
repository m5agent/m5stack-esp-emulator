#!/usr/bin/env python3
"""Normalize WebBurner/M5Burner packages into a validated flash manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
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
    "display",
    "gpio",
    "imu",
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
    "display-output": "display",
    "framebuffer": "display",
    "lcd": "display",
    "magnetometer": "imu",
    "screen": "display",
    "storage": "sd",
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
    ("psram", ("CONFIG_SPIRAM", "CONFIG_SPIRAM_BOOT_INIT")),
)
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    data = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256_bytes(data)


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


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    files = archive.infolist()
    if len(files) > MAX_PACKAGE_FILES:
        raise ManifestError(
            f"archive contains {len(files)} entries; max is {MAX_PACKAGE_FILES}"
        )
    total = 0
    target_root = target.resolve()
    for entry in files:
        total += entry.file_size
        if total > MAX_PACKAGE_BYTES:
            raise ManifestError(
                f"archive expands above {MAX_PACKAGE_BYTES} bytes"
            )
        destination = (target / entry.filename).resolve()
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
        with archive.open(entry) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


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
    for name in candidates:
        path = root / name
        if not path.is_file():
            continue
        value = _load_json(path)
        if isinstance(value, dict) and (
            "builds" in value or "parts" in value
        ):
            return path
    return None


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


def _segments_from_web_manifest(
    root: Path,
    document: dict,
) -> tuple[list[dict], dict]:
    builds = document.get("builds")
    if isinstance(builds, list):
        if not builds or any(not isinstance(item, dict) for item in builds):
            raise ManifestError("WebBurner builds must be a non-empty object list")
        build = builds[0]
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
                else int(str(raw_offset), 0)
            )
        except (TypeError, ValueError) as error:
            raise ManifestError(
                f"WebBurner part {index} has invalid offset"
            ) from error
        if offset < 0:
            raise ManifestError(f"WebBurner part {index} has negative offset")
        source = _resolve_package_file(root, part.get("path"))
        segments.append(
            {
                "offset": offset,
                "path": source,
                **resource(source, root=root),
            }
        )
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
        candidates = []
        for pattern in names:
            if "*" in pattern:
                candidates.extend(root.rglob(pattern))
            else:
                candidates.extend(root.rglob(pattern))
        if candidates:
            resources[kind] = resource(
                sorted(candidates, key=lambda item: item.as_posix())[0],
                root=root,
            )
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
    return sorted(candidates, key=lambda item: item.as_posix())[0]


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


def validate_capabilities(
    manifest: dict,
    device: dict,
) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
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
    if security.get("secure_boot") in {
        "v1",
        "v2",
        "enabled-unspecified",
    }:
        errors.append(
            _code_issues(
                "secure_boot_not_modeled",
                "target profile does not model the required secure-boot chain",
                requirement=security.get("secure_boot"),
                available="not modeled",
                path="security.secure_boot",
            )
        )
    if security.get("flash_encryption") == "enabled":
        errors.append(
            _code_issues(
                "flash_encryption_not_modeled",
                "target profile does not model this flash-encryption mode",
                requirement="enabled",
                available="not modeled",
                path="security.flash_encryption",
            )
        )
    elif security.get("flash_encryption") == "partition-encryption-marked":
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
    required = manifest.get("capabilities", {}).get("required", [])
    optional = manifest.get("capabilities", {}).get("optional", [])
    device_capabilities = _device_capability_set(device)
    for requirement in required:
        normalized = CAPABILITY_ALIASES.get(
            str(requirement).strip().lower(),
            str(requirement).strip().lower(),
        )
        if normalized not in KNOWN_CAPABILITIES:
            warnings.append(
                _code_issues(
                    "unknown_required_capability",
                    (
                        f"capability {requirement!r} is not recognized by "
                        "the compatibility checker"
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
    for detection in manifest.get("capabilities", {}).get("detected", []):
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
    return {
        "secure_boot": secure_boot,
        "flash_encryption": flash_encryption,
        "secure_boot_config": configured_secure_boot,
        "flash_encryption_config": configured_flash_encryption,
        "efuse": "summary-included" if efuse is not None else "not-included",
        "efuse_summary": efuse,
        "secure_version": descriptor.get("secure_version"),
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
    for index in range(8):
        purpose = _efuse_text(document, f"KEY_PURPOSE_{index}")
        if purpose is not None:
            purposes.append(
                {
                    "block": index,
                    "purpose": purpose,
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
    temporary = Path(tempfile.mkdtemp(prefix="m5-firmware-package-"))
    try:
        root = _package_root(input_path, temporary)
        web_manifest = _choose_web_manifest(root)
        flasher_args = next(
            (
                path
                for path in root.rglob("flasher_args.json")
                if path.is_file()
            ),
            None,
        )
        if web_manifest is not None:
            segments, package_meta = _segments_from_web_manifest(
                root,
                _load_json(web_manifest),
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
            {
                key: value
                for key, value in manifest.items()
                if key not in {"manifest_id", "created_at"}
            }
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
    capabilities = manifest.get("capabilities")
    if capabilities is not None:
        if not isinstance(capabilities, dict):
            errors.append("manifest.capabilities must be an object")
        else:
            unknown = set(capabilities) - {"required", "optional", "detected"}
            if unknown:
                errors.append("manifest.capabilities contains unknown fields")
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
                if isinstance(values, list) and any(
                    not isinstance(value, str) or not value
                    for value in values
                ):
                    errors.append(
                        f"manifest.capabilities.{key} must contain strings"
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
    elif (
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
