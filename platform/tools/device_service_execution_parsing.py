"""Stateless storage and NVS execution request parsers."""
from __future__ import annotations

from typing import Any

from device_service_errors import ServiceError
from device_service_parsing import is_sha256
from device_service_specs import DeviceSpec, SPI_SD_DEVICE_IDS


def storage_interface(spec: DeviceSpec) -> str:
    """Board-wired SD protocol used by the session disk.

    These native boards use the GP-SPI SD endpoint; other supported storage
    profiles retain their SDMMC block attachment.
    """
    return "spi" if spec.id in SPI_SD_DEVICE_IDS else "sdmmc"


def parse_storage_execution(
    spec: DeviceSpec,
    value: Any,
    *,
    has_sd_card: bool | None = None,
) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_storage", "storage must be an object", 400)
    unknown = sorted(set(value) - {"sd_image_artifact_id", "sd_initially_ejected"})
    if unknown:
        raise ServiceError(
            "invalid_storage",
            "unsupported storage fields: " + ", ".join(unknown),
            400,
        )
    artifact_id = value.get("sd_image_artifact_id")
    if not isinstance(artifact_id, str) or not is_sha256(artifact_id):
        raise ServiceError(
            "invalid_storage",
            "storage.sd_image_artifact_id must be a SHA-256 artifact id",
            400,
        )
    initially_ejected = value.get("sd_initially_ejected", False)
    if type(initially_ejected) is not bool:
        raise ServiceError("invalid_storage", "storage.sd_initially_ejected must be a boolean", 400)
    if not (spec.has_sd_card if has_sd_card is None else has_sd_card):
        raise ServiceError(
            "storage_not_supported",
            f"{spec.id} has no modeled SD-card interface",
            409,
        )
    if initially_ejected and not spec.has_sd_hotplug:
        raise ServiceError("sd_hotplug_not_supported", "the selected board cannot eject session media", 409)
    return {
        "interface": storage_interface(spec),
        "format": "raw",
        "sd_image_artifact_id": artifact_id,
        **({"sd_initially_ejected": True} if initially_ejected else {}),
    }


def parse_nvs_execution(value: Any) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_nvs", "nvs must be an object", 400)
    unknown = sorted(set(value) - {"image_artifact_id", "partition_label"})
    if unknown:
        raise ServiceError(
            "invalid_nvs",
            "unsupported nvs fields: " + ", ".join(unknown),
            400,
        )
    artifact_id = value.get("image_artifact_id")
    if not isinstance(artifact_id, str) or not is_sha256(artifact_id):
        raise ServiceError(
            "invalid_nvs",
            "nvs.image_artifact_id must be a SHA-256 artifact id",
            400,
        )
    partition_label = value.get("partition_label", "nvs")
    if (
        not isinstance(partition_label, str)
        or not partition_label
        or len(partition_label) > 16
    ):
        raise ServiceError(
            "invalid_nvs",
            "nvs.partition_label must be a non-empty partition label",
            400,
        )
    return {
        "partition_label": partition_label,
        "image_artifact_id": artifact_id,
    }
