"""Validate and bind a whole internal filesystem fixture without applying it."""

from __future__ import annotations

from hashlib import sha256

from device_service_errors import ServiceError
from device_service_parsing import is_sha256
from firmware_analysis import (
    PARTITION_TABLE_OFFSET,
    PARTITION_TABLE_SIZE,
    analyze_esp_image,
    find_app_descriptor,
    parse_partition_table,
)
from firmware_filesystems import FAT_SUBTYPE, LITTLEFS_SUBTYPE, SPIFFS_SUBTYPE, inventory_data_partition
from firmware_manifest import canonical_json_sha256


MAX_FLASH_BYTES = 64 * 1024 * 1024
MAX_FS_FIXTURE_BYTES = 32 * 1024 * 1024
SECTOR_BYTES = 4096
PARTITION_TYPE_DATA = 1
PARTITION_TYPE_APP = 0
PARTITION_FLAG_READONLY = 2
SAFE_SECURITY_STATES = ("disabled", "not-indicated")


def parse_fs_fixture(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or value.keys() != {"image_artifact_id", "partition_label", "format"}:
        raise ServiceError(
            "invalid_fs_fixture",
            "storage.filesystem requires image_artifact_id, partition_label and format",
            400,
        )
    artifact_id, label, fmt = value["image_artifact_id"], value["partition_label"], value["format"]
    if not isinstance(artifact_id, str) or not is_sha256(artifact_id):
        raise ServiceError("invalid_fs_fixture", "image_artifact_id must be a lowercase SHA-256", 400)
    try:
        valid_label = (
            isinstance(label, str) and label.isprintable() and label.strip() == label
            and 0 < len(label.encode("utf-8")) <= 16 and "\ufffd" not in label
        )
    except UnicodeError:
        valid_label = False
    if not valid_label:
        raise ServiceError("invalid_fs_fixture", "partition_label must be a printable ESP partition label", 400)
    if fmt not in ("littlefs", "spiffs"):
        raise ServiceError("invalid_fs_fixture", "format must be littlefs or spiffs", 400)
    return {"image_artifact_id": artifact_id, "partition_label": label, "format": fmt}


def _secure_firmware() -> ServiceError:
    return ServiceError(
        "fs_fixture_secure_firmware",
        "internal filesystem fixtures require an unsigned, unencrypted flash layout",
        409,
    )


def _check_security(security: dict | None) -> None:
    if security is None:
        return
    if not isinstance(security, dict) or any(
        key in security and security[key] not in SAFE_SECURITY_STATES
        for key in ("secure_boot", "secure_boot_config", "flash_encryption", "flash_encryption_config")
    ):
        raise _secure_firmware()
    efuse = security.get("efuse_summary")
    if "efuse" in security:
        expected = "not-included" if efuse is None else "summary-included"
        if security["efuse"] != expected:
            raise _secure_firmware()
    if efuse is not None and (
        not isinstance(efuse, dict) or any(
            efuse.get(key) not in SAFE_SECURITY_STATES for key in ("secure_boot", "flash_encryption")
        )
    ):
        raise _secure_firmware()
    signatures = security.get("secure_boot_image")
    if signatures is not None:
        if not isinstance(signatures, dict) or signatures.get("status") != "not-found":
            raise _secure_firmware()
        images = signatures.get("images", [])
        if not isinstance(images, list) or any(
            not isinstance(row, dict)
            or row.get("status") != "not-found"
            or row.get("candidate_count") or row.get("block_count") or row.get("blocks")
            for row in images
        ):
            raise _secure_firmware()


def _resolve_partition(firmware: bytes, label: str, fmt: str) -> tuple[dict, list[dict]]:
    table = parse_partition_table(firmware)
    if not table["valid"] or table["warnings"]:
        raise ServiceError("fs_fixture_invalid_layout", "firmware partition table is invalid or incomplete", 409)
    partitions = sorted(table["partitions"], key=lambda row: row["offset"])
    prior_end = PARTITION_TABLE_OFFSET + PARTITION_TABLE_SIZE
    for row in partitions:
        end = row["offset"] + row["size"]
        if row["size"] <= 0 or row["offset"] < prior_end or end > len(firmware):
            raise ServiceError("fs_fixture_invalid_layout", "firmware partition ranges overlap or exceed flash", 409)
        if row["flags"] & ~PARTITION_FLAG_READONLY:
            raise _secure_firmware()
        prior_end = end

    matches = [row for row in partitions if row["label"] == label]
    if len(matches) != 1:
        raise ServiceError("fs_fixture_partition_not_unique", "partition_label must identify exactly one partition", 409)
    partition = matches[0]
    allowed = (
        fmt == "littlefs" and (
            partition["subtype"] == LITTLEFS_SUBTYPE
            or (partition["subtype"] == FAT_SUBTYPE and label == "vfs")
        )
        or fmt == "spiffs" and partition["subtype"] == SPIFFS_SUBTYPE
    )
    if partition["type"] != PARTITION_TYPE_DATA or not allowed or partition["flags"] != 0:
        raise ServiceError("fs_fixture_partition_unsupported", "selected partition does not permit this filesystem fixture", 409)
    if partition["offset"] % SECTOR_BYTES or partition["size"] % SECTOR_BYTES:
        raise ServiceError("fs_fixture_invalid_layout", "filesystem partition is not erase-sector aligned", 409)
    if not 2 * SECTOR_BYTES <= partition["size"] <= MAX_FS_FIXTURE_BYTES:
        raise ServiceError("fs_fixture_partition_unsupported", "filesystem partition size is outside supported bounds", 409)
    return partition, partitions


def _unsigned_image(firmware: bytes, offset: int, region_end: int, chip: int) -> dict:
    image = analyze_esp_image(firmware, offset)
    if not image["valid"] or image.get("chip_id") != chip or not image.get("segment_count"):
        raise ServiceError("fs_fixture_invalid_layout", "firmware boot/application image is invalid for the target chip", 409)
    # The final segment is followed by a checksum in the last byte of a
    # 16-byte-aligned image, then an optional 32-byte SHA-256 digest.
    checksum_end = offset + ((image["image_end"] - offset + 16) & ~15)
    end = checksum_end + (32 if image["hash_appended"] else 0)
    if end > region_end:
        raise ServiceError("fs_fixture_invalid_layout", "firmware boot/application image exceeds its region", 409)
    if image["hash_appended"] and sha256(firmware[offset:checksum_end]).digest() != firmware[checksum_end:end]:
        raise ServiceError("fs_fixture_invalid_layout", "firmware boot/application image hash does not match", 409)
    # With no established signing policy, reject any trailer beyond the
    # ordinary image and its declared digest, including unsupported v1/v2
    # signatures, rather than relying on recognition of one signature format.
    if firmware.count(0xFF, end, region_end) != region_end - end:
        raise _secure_firmware()
    return image


def _check_images(firmware: bytes, partitions: list[dict], boot_offset: int, chip: int, *, uiflow: bool) -> None:
    if type(boot_offset) is not int or boot_offset != (0x1000 if chip == 0 else 0):
        raise ServiceError("fs_fixture_invalid_layout", "expected bootloader offset does not match the target chip", 409)
    if firmware.count(0xFF, 0, boot_offset) != boot_offset:
        raise _secure_firmware()
    _unsigned_image(firmware, boot_offset, PARTITION_TABLE_OFFSET, chip)
    app_count = 0
    for partition in partitions:
        offset, size = partition["offset"], partition["size"]
        if partition["type"] != PARTITION_TYPE_APP or firmware.count(0xFF, offset, offset + size) == size:
            continue
        image = _unsigned_image(firmware, offset, offset + size, chip)
        app_count += 1
        if uiflow:
            desc = find_app_descriptor(firmware, offset, image["image_end"])
            if not (
                desc is not None and desc["project_name"] == "micropython"
                and desc["version"].lower().startswith("v2.")
                and firmware.find(b"_uiflow_run_main", offset, image["image_end"]) >= 0
                and any(
                    firmware.find(marker, offset, image["image_end"]) >= 0
                    for marker in (b"UIFLOW2", b"UiFlow2", b"uiflow2.m5stack.com")
                )
            ):
                raise ServiceError("fs_fixture_partition_unsupported", "legacy vfs requires a verified UIFlow2 image fingerprint", 409)
    if not app_count:
        raise ServiceError("fs_fixture_invalid_layout", "firmware declares no populated application image", 409)


def _inventory(data: bytes, partition: dict, fmt: str, *, existing: bool) -> dict:
    try:
        result = inventory_data_partition(data, partition, max_file_bytes=partition["size"])
    except Exception as error:
        raise ServiceError(
            "fs_fixture_invalid_image", "filesystem inventory could not inspect the image", 400
        ) from error
    if result and result.get("status") == "UNAVAILABLE":
        raise ServiceError("fs_fixture_verifier_unavailable", "filesystem verifier is unavailable", 503)
    if (
        not result or result.get("status") != "PASS" or result.get("type") != fmt
        or result.get("errors")
        or result.get("limits", {}).get("files_truncated")
        or result.get("limits", {}).get("directories_truncated")
        or not 0 <= result["total_file_bytes"] <= partition["size"]
    ):
        raise ServiceError(
            "fs_fixture_unverified_geometry" if existing else "fs_fixture_invalid_image",
            "existing partition filesystem could not be verified" if existing
            else "fixture is malformed, unsupported or incomplete",
            409 if existing else 400,
        )
    return result


def _geometry(result: dict, fmt: str, size: int) -> dict:
    if fmt == "littlefs":
        if result.get("block_size") == SECTOR_BYTES and result.get("block_count") == size // SECTOR_BYTES:
            return {"block_size": SECTOR_BYTES, "block_count": size // SECTOR_BYTES}
    elif result.get("lut_validated") and result.get("selected_config"):
        candidates = [
            tuple(row["score"][key] for key in ("complete_objects", "valid_data_pages", "index_pages", "objects"))
            for row in result["config_attempts"] if row["match"]
        ]
        if candidates and candidates.count(max(candidates)) == 1:
            return dict(result["selected_config"])
    raise ServiceError("fs_fixture_unverified_geometry", "filesystem geometry is unsupported or ambiguous", 409)


def plan_fs_fixture(
    firmware: bytes,
    fixture: bytes,
    request: dict,
    *,
    firmware_sha256: str,
    expected_chip_id: int,
    bootloader_offset: int,
    security: dict | None = None,
) -> dict:
    """Return a deterministic, content-bound plan for a session-owned copy."""
    parsed = parse_fs_fixture(request)
    if not parsed:
        raise ServiceError("invalid_fs_fixture", "filesystem fixture request is required", 400)
    if not isinstance(firmware, bytes) or not PARTITION_TABLE_OFFSET + PARTITION_TABLE_SIZE < len(firmware) <= MAX_FLASH_BYTES:
        raise ServiceError("fs_fixture_invalid_layout", "firmware must be immutable complete flash bytes", 409)
    if type(expected_chip_id) is not int or not 0 <= expected_chip_id <= 0xFFFF:
        raise ServiceError("fs_fixture_invalid_layout", "firmware requires a known target chip", 409)
    if sha256(firmware).hexdigest() != firmware_sha256:
        raise ServiceError("fs_fixture_firmware_mismatch", "passed flash bytes differ from their expected SHA-256", 409)
    if not isinstance(fixture, bytes) or not 0 < len(fixture) <= MAX_FS_FIXTURE_BYTES:
        raise ServiceError("fs_fixture_invalid_image", "fixture must be immutable bytes within the image size limit", 400)
    fixture_sha = sha256(fixture).hexdigest()
    if fixture_sha != parsed["image_artifact_id"]:
        raise ServiceError("fs_fixture_artifact_mismatch", "filesystem fixture bytes differ from the artifact identity", 409)
    _check_security(security)
    fmt, label = parsed["format"], parsed["partition_label"]
    partition, partitions = _resolve_partition(firmware, label, fmt)
    offset, size = partition["offset"], partition["size"]
    if len(fixture) != size:
        raise ServiceError("fs_fixture_invalid_size", "filesystem image size must equal the partition size", 400)
    legacy_vfs = partition["subtype"] == FAT_SUBTYPE
    _check_images(firmware, partitions, bootloader_offset, expected_chip_id, uiflow=legacy_vfs)

    result = _inventory(fixture, {**partition, "offset": 0}, fmt, existing=False)
    geometry = _geometry(result, fmt, size)
    original = memoryview(firmware)[offset:offset + size]
    erased = firmware.count(0xFF, offset, offset + size) == size
    if legacy_vfs or fmt == "spiffs" or not erased:
        existing = _inventory(firmware, partition, fmt, existing=True)
        if _geometry(existing, fmt, size) != geometry:
            raise ServiceError("fs_fixture_geometry_mismatch", "fixture and existing filesystem geometry differ", 409)
    plan = {
        "schema_version": 1,
        **parsed,
        "subtype": partition["subtype"],
        "offset": offset,
        "size": size,
        "fixture_sha256": fixture_sha,
        "base_flash_sha256": firmware_sha256,
        "base_partition_sha256": sha256(original).hexdigest(),
        "geometry": geometry,
        "file_count": result["file_count"],
        "file_bytes": result["total_file_bytes"],
    }
    return {**plan, "plan_sha256": canonical_json_sha256(plan)}
