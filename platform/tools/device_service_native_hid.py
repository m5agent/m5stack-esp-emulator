"""Native VHCI admission and evidence for the pinned AirMouseS3 stock image."""
from __future__ import annotations

import subprocess
from pathlib import Path

from device_service_errors import ServiceError

STICKS3_NATIVE_HID_PROFILE = "sticks3-native-hid"
AIRMOUSE_SOURCE_SHA256 = "bdb567de990ef5c2a0fd113c033b259acd17e49717c9fdb5e9cc9d3776b208d8"
AIRMOUSE_FLASH_SHA256 = "08d4806570618bc41ab73a481d6a9d7f1e95833af735dc075344427950d8a03a"
AIRMOUSE_BLE_NAME = "AirStick"
NATIVE_HCI_DEVICE = "esp32-native-hci"

# Verified against the ESP32-S3 SDK controller archive, the stock image's
# executable instructions and its registered callback. Do not use these
# addresses with other builds, even builds made from the same source tag.
AIRMOUSE_HCI_PROPERTIES = {
    "env-pointer-address": 0x3FCEFF58,
    "c2h-callback-offset": 8,
    "c2h-allocator-address": 0x40377C60,
    "c2h-idle-call-pc": 0x403804EC,
    "api-vhci-send-hook-pc": 0x420391D0,
    "api-vhci-send-return-pc": 0x420391D3,
}


def require_airmouse_image(source: dict, flash_sha256: str) -> None:
    if (
        source.get("kind") != "merged"
        or source.get("artifact_id") != AIRMOUSE_SOURCE_SHA256
        or flash_sha256 != AIRMOUSE_FLASH_SHA256
    ):
        raise ServiceError(
            "sticks3_native_hid_image_mismatch",
            "the native HID profile requires the original AirMouseS3 v1.0 merged BIN",
            409,
        )


def require_native_hid_backend(qemu: Path) -> None:
    try:
        result = subprocess.run(
            [str(qemu), "-device", f"{NATIVE_HCI_DEVICE},help"],
            check=True, capture_output=True, text=True, timeout=2,
        )
        properties = {line.strip().split("=", 1)[0] for line in result.stdout.splitlines()}
        if set(AIRMOUSE_HCI_PROPERTIES) <= properties:
            return
    except (OSError, subprocess.SubprocessError):
        pass
    raise ServiceError(
        "sticks3_native_hid_backend_unavailable",
        "the QEMU backend does not support the StickS3 native VHCI ABI",
        503,
    )


def airmouse_native_hid_args(port: int) -> list[str]:
    props = ",".join(f"{name}={value:#x}" for name, value in AIRMOUSE_HCI_PROPERTIES.items())
    return [
        "-accel", "tcg,thread=single",
        "-icount", "shift=5",
        "-nic", "none",
        "-chardev", f"socket,id=hci,host=127.0.0.1,port={port},nodelay=on",
        "-device", f"{NATIVE_HCI_DEVICE},id=sticks3-vhci,chardev=hci,{props}",
    ]


def native_hid_evidence(probe_log: str) -> dict:
    markers = [line.split(" ", 1)[0] for line in probe_log.splitlines() if line]
    checks = {
        "paired": "BLE_HID_PAIRING_COMPLETE" in markers,
        "hid_service": "BLE_HID_SERVICE_DISCOVERED" in markers,
        "report_map": "BLE_HID_REPORT_MAP" in markers,
        "subscribed": "BLE_HID_SUBSCRIBED" in markers,
        "input_reports": markers.count("BLE_HID_REPORT") >= 2 and "BLE_HID_PASS" in markers,
    }
    if "BLE_HID_FAIL" in markers or "BLE_BUMBLE_ERROR" in markers:
        status = "FAIL"
    elif all(checks.values()):
        status = "PASS"
    elif checks["subscribed"]:
        status = "AWAITING_INPUT"
    else:
        status = "RUNNING"
    return {
        "schema_version": 1,
        "kind": "m5stack-sticks3-native-hid-proof",
        "scope": "simulation-only-not-hardware-validation",
        "profile": STICKS3_NATIVE_HID_PROFILE,
        "transport": "esp32s3-native-vhci",
        "source_firmware_sha256": AIRMOUSE_SOURCE_SHA256,
        "status": status,
        "checks": checks,
        "reports_observed": markers.count("BLE_HID_REPORT"),
        "ip_network_backend": "disabled",
    }
