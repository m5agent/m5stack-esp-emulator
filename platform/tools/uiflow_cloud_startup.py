"""Pinned stock UIFlow startup using real Wi-Fi and an isolated NVS fixture.

This module never edits the application or filesystem and never supplies an
access code. The original guest obtains its code from the real cloud service.
"""
from __future__ import annotations

import hashlib
import re

from device_service_errors import ServiceError
from device_service_specs import core2_radio_qemu_path
from nvs_image import NvsU8, build_nvs_image


# Official cached images with the stock startup/NVS contract. A replacement
# image needs explicit admission; a product name alone does not establish it.
CLOUD_REFERENCE_SHA256 = {
    "cores3": "5847a2bcae33d6bb8942de1c3ae92295a8441b6a3424c78e444fc748c9508ded",
    "sticks3": "fd85648dfa1fd9656448aa45e86ee63be537a4534e959e422c0be4d45b3466c7",
    "core2": "57868df3d1bb0cbd03fdca3eac0db8a9c6578a70195e4479822147b29ef691ae",
    "atoms3r": "c289f7df74919b0b544e524d0117661e81429e0c3a4bb42623ccdf42200b952e",
    "stopwatch": "0bcb9269f42186ec0a66b503a4d97bb005fec72848c4374475a53009e1d3b24b",
    "cardputer-adv": "fe39163d55d4c9b00eb9ff6d5ccce5fcaa4922819bcea8a75d83e3bd09a2af62",
}


def parse_uiflow_startup(payload: dict) -> dict | None:
    if "uiflow_startup" not in payload:
        return None
    value = payload["uiflow_startup"]
    if (not isinstance(value, dict) or set(value) != {"mode", "reference_sha256"}
            or value.get("mode") != "cloud"
            or not isinstance(value.get("reference_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["reference_sha256"]) is None):
        raise ServiceError("invalid_uiflow_startup", "uiflow_startup requires mode=cloud and the advertised reference_sha256", 400)
    conflicts = {"program_mode", "program_transport", "firmware_id", "source", "nvs",
                 "base_firmware_id", "expected_base_sha256", "uiflow_source_sha256",
                 "wifi_monitor_fixture"}
    if conflicts.intersection(payload) or payload.get("runtime", "qemu-wifi") != "qemu-wifi":
        raise ServiceError("uiflow_startup_conflict", "cloud startup requires the stock reference, qemu-wifi and its own NVS configuration", 409)
    env = payload.get("runtime_env", {})
    if isinstance(env, dict) and any(str(key).startswith(("M5SW_WIFI_", "M5SW_S3_WIFI_", "M5SW_CLASSIC_WIFI_")) for key in env):
        raise ServiceError("uiflow_startup_conflict", "cloud startup Wi-Fi configuration cannot be overridden", 409)
    return dict(value)


def verified_cloud_reference(spec, expected_sha256: str | None = None) -> dict:
    admitted = CLOUD_REFERENCE_SHA256.get(spec.id)
    if not admitted or not spec.reference_path or not spec.supported or not spec.backend_ready:
        raise ServiceError("uiflow_startup_unavailable", "stock UIFlow cloud startup is unavailable for this device", 409)
    if spec.id == "core2":
        core2_radio_qemu_path()
    try:
        with spec.reference_path.open("rb") as handle:
            data = handle.read(spec.flash_size + 1)
    except OSError as error:
        raise ServiceError("uiflow_startup_unavailable", "stock UIFlow reference is not readable", 409) from error
    digest = hashlib.sha256(data).hexdigest()
    if digest != admitted or len(data) > spec.flash_size:
        raise ServiceError("uiflow_startup_unavailable", "cached image is not an admitted stock UIFlow reference", 409)
    if expected_sha256 is not None and expected_sha256 != digest:
        raise ServiceError("uiflow_startup_reference_mismatch", "UIFlow reference differs from the advertised caller pin", 409)
    return {"firmware_id": digest, "sha256": digest, "size": len(data), "path": spec.reference_path, "data": data}


def cloud_startup_capability(spec) -> dict:
    try:
        reference = verified_cloud_reference(spec)
    except ServiceError:
        return {"modes": []}
    return {"modes": ["cloud"], "reference_sha256": reference["sha256"], "runtime": "qemu-wifi"}


def prepare_cloud_reference(service, spec, reference: dict, *, pad_image) -> dict:
    """Use the normal Flash padding primitive without rewriting firmware metadata."""
    artifact = service.upload_artifact(reference["data"], name=f"{spec.id}-uiflow-stock.bin")
    normalized = service.upload_artifact(
        pad_image(service.artifacts.path(artifact["artifact_id"]), spec.flash_size),
        name=f"{spec.id}-uiflow-normalized.bin",
    )
    return {
        "firmware_id": normalized["artifact_id"], "sha256": normalized["artifact_id"],
        "size": normalized["size"], "path": service.artifacts.path(normalized["artifact_id"]),
        "source_artifacts": list(dict.fromkeys((artifact["artifact_id"], normalized["artifact_id"]))),
        "provenance": {"kind": "uiflow-cloud", "artifact_id": artifact["artifact_id"], "metadata": {
            "reference_sha256": reference["sha256"], "reference_size": reference["size"],
            "normalized_sha256": normalized["artifact_id"], "normalized_size": normalized["size"],
            "normalization": "trailing-ff-padding",
        }},
    }


def cloud_network_request(value) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_network", "network must be an object", 400)
    fixed = {"wifi_ssid": "myssid", "wifi_password": "", "wifi_auth": "open", "http_fixture": False}
    if any(key in value and (type(value[key]) is not type(expected) or value[key] != expected)
           for key, expected in fixed.items()):
        raise ServiceError("uiflow_startup_conflict", "cloud startup requires its matching virtual AP and no HTTP fixture", 409)
    # Existing policy parsing and capability enforcement remain authoritative.
    return {"capture_pcap": True, **fixed, **value}


def cloud_nvs_image(partition_size: int) -> bytes:
    return build_nvs_image(partition_size, {"uiflow": {
        "server": "uiflow2.m5stack.com", "net_mode": "WIFI", "protocol": "DHCP",
        "ip_addr": "", "netmask": "", "gateway": "", "dns": "8.8.8.8",
        "ssid0": "myssid", "pswd0": "", "ssid1": "", "pswd1": "", "ssid2": "", "pswd2": "",
        "sntp0": "ntp.aliyun.com", "sntp1": "jp.pool.ntp.org", "sntp2": "pool.ntp.org",
        "tz": "GMT0", "boot_option": NvsU8(1),
    }})
