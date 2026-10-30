"""QEMU WiFi security parsing and runtime environment projection."""
from __future__ import annotations

from device_service_errors import ServiceError


def parse_qemu_wifi_security(value: dict) -> dict:
    ssid = value.get("wifi_ssid", "myssid")
    password = value.get("wifi_password", "")
    wifi_auth = value.get("wifi_auth", "open")
    if not isinstance(ssid, str) or not 1 <= len(ssid) <= 32:
        raise ServiceError(
            "invalid_network",
            "network.wifi_ssid must be 1-32 characters",
            400,
        )
    if not isinstance(password, str) or len(password) > 63:
        raise ServiceError(
            "invalid_network",
            "network.wifi_password is invalid",
            400,
        )
    if wifi_auth not in {"open", "wpa2-psk"}:
        raise ServiceError(
            "unsupported_wifi_security",
            "QEMU WiFi currently supports only open or wpa2-psk",
            409,
        )
    if wifi_auth == "wpa2-psk" and not 8 <= len(password) <= 63:
        raise ServiceError(
            "invalid_network",
            "network.wifi_password must be 8-63 characters for wpa2-psk",
            400,
        )
    if wifi_auth == "open":
        password = ""
    return {
        "wifi_ssid": ssid,
        "wifi_password": password,
        "wifi_auth": wifi_auth,
    }


def apply_qemu_wifi_environment(
    env: dict[str, str],
    nic: str | None,
    network_config: dict,
) -> None:
    if nic not in {"misc.esp32_wifi", "misc.esp32s3.wifi"}:
        return
    auth = str(network_config.get("wifi_auth", "open"))
    env["M5SW_WIFI_SSID"] = str(
        network_config.get("wifi_ssid", "myssid")
    )
    env["M5SW_WIFI_PASSWORD"] = str(
        network_config.get("wifi_password", "")
    )
    env["M5SW_WIFI_AUTH"] = auth
    if nic == "misc.esp32s3.wifi" and auth == "wpa2-psk":
        env["M5SW_S3_WIFI_TRACE"] = "1"
