#!/usr/bin/env python3
"""Normalize WebBurner/M5Burner packages into a validated flash manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from firmware_analysis import analyze_firmware


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "platform/tools/firmware_manifest.schema.json"
CATALOG_PATH = ROOT / "devices/catalog.source.json"
DEVICE_MATRIX_PATH = ROOT / "tests/uiflow2/device_matrix.json"
SCHEMA_VERSION = 1
MAX_PACKAGE_FILES = 4096
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
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


class ManifestError(ValueError):
    """Raised when a firmware package or manifest is invalid."""


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


def _security_metadata(
    analysis: dict,
    sdkconfig: Path | None,
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
    if "CONFIG_SECURE_BOOT_V2_ENABLED=y" in config:
        secure_boot = "v2"
    elif "CONFIG_SECURE_BOOT_V1_ENABLED=y" in config:
        secure_boot = "v1"
    elif "CONFIG_SECURE_BOOT=y" in config:
        secure_boot = "enabled-unspecified"
    elif config:
        secure_boot = "not-indicated"
    else:
        secure_boot = "unknown"
    if "CONFIG_SECURE_FLASH_ENC_ENABLED=y" in config:
        flash_encryption = "enabled"
    elif encrypted:
        flash_encryption = "partition-encryption-marked"
    elif config:
        flash_encryption = "not-indicated"
    else:
        flash_encryption = "unknown"
    return {
        "secure_boot": secure_boot,
        "flash_encryption": flash_encryption,
        "efuse": "not-included",
        "secure_version": descriptor.get("secure_version"),
        "sdkconfig_available": bool(config),
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
) -> dict:
    input_path = input_path.resolve()
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
        copied_resources = {
            key: _copy_resource(
                row,
                source_root=root,
                output_dir=output_dir,
            )
            for key, row in resources.items()
        }
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
            },
            "security": _security_metadata(analysis, sdkconfig_path),
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
                "required": sorted(set(required_capabilities or [])),
                "optional": sorted(set(optional_capabilities or [])),
            },
            "validation": {
                "status": "PASS",
                "errors": [],
                "warnings": [
                    _code_issues(
                        "security_metadata_incomplete",
                        (
                            "eFuse and runtime security state are not "
                            "embedded in a flash image"
                        ),
                        path="security",
                    )
                ],
            },
        }
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
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("manifest.provenance must be an object")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("status") not in {
        "PASS",
        "REJECTED",
    }:
        errors.append("manifest.validation.status is invalid")
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
