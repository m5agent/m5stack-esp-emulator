"""QEMU WiFi security parsing and runtime environment projection."""
from __future__ import annotations

import hashlib
import json

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


STICKS3_MONITOR_PROFILE = "sticks3-monitor-fixture"
STICKS3_MONITOR_NIC = "misc.esp32s3.wifi"
STICKS3_MONITOR_MAC = "02:00:00:00:20:04"
STICKS3_MONITOR_SSID = "m5-monitor-lab"
WIFI_ENV_PREFIXES = ("M5SW_WIFI_", "M5SW_S3_WIFI_", "M5SW_CLASSIC_WIFI_", "M5SW_ESPNOW_")


def parse_sticks3_wifi_monitor(payload: dict) -> dict | None:
    if "wifi_monitor_fixture" not in payload:
        return None
    mode = payload["wifi_monitor_fixture"]
    if mode not in ("beacon", "no-beacon"):
        raise ServiceError("invalid_wifi_monitor_fixture", "wifi_monitor_fixture must be beacon or no-beacon", 400)
    if payload.get("device_id") != "sticks3" or payload.get("runtime", "qemu") != "qemu":
        raise ServiceError("wifi_monitor_fixture_not_supported", "the fixture requires StickS3 runtime=qemu", 409)
    runtime_env = payload.get("runtime_env")
    conflicting_overrides = isinstance(runtime_env, dict) and any(
        isinstance(key, str) and key.startswith(WIFI_ENV_PREFIXES) for key in runtime_env
    )
    if conflicting_overrides or any(
        payload.get(key) is not None for key in ("network", "program_mode", "program_transport")
    ):
        raise ServiceError(
            "wifi_monitor_fixture_conflict",
            "the fixture cannot be combined with network, Wi-Fi runtime overrides or program options",
            400,
        )
    config = {
        "profile": STICKS3_MONITOR_PROFILE,
        "fixture": mode,
        "radio_enabled": mode == "beacon",
        "wifi_ssid": STICKS3_MONITOR_SSID,
        "wifi_auth": "open",
        "channel": 1,
        "nic": STICKS3_MONITOR_NIC,
        "host_backends": 0,
    }
    return config | {"fixture_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}


def apply_sticks3_monitor_environment(env: dict[str, str]) -> None:
    for key in tuple(env):
        if key.startswith(WIFI_ENV_PREFIXES):
            del env[key]
    env.update(M5SW_WIFI_SSID=STICKS3_MONITOR_SSID, M5SW_WIFI_AUTH="open", M5SW_S3_WIFI_TRACE="1")


def configure_sticks3_monitor_radio(qmp_call, enabled: bool) -> None:
    """Fail closed on an unexpected topology before allowing guest execution."""
    if qmp_call("query-status")["return"]["running"]:
        raise ServiceError("wifi_monitor_fixture_isolation", "guest must be paused before the fixture audit", 503)
    network = qmp_call("human-monitor-command", **{"command-line": "info network"})["return"]
    rows = [line.strip() for line in network.splitlines() if line.strip()]
    nic = STICKS3_MONITOR_NIC
    endpoint = f"\\ hub0port0: {nic}.0: index=0,type=nic,model={nic},macaddr={STICKS3_MONITOR_MAC}"
    if rows != ["hub 0", endpoint]:
        raise ServiceError("wifi_monitor_fixture_isolation", "expected exactly one peerless S3 Wi-Fi NIC", 503)
    children = qmp_call("qom-list", path="/machine/unattached")["return"]
    radios = [entry["name"] for entry in children if entry["type"] == f"child<{nic}>"]
    if len(radios) != 1:
        raise ServiceError("wifi_monitor_fixture_isolation", "expected exactly one S3 Wi-Fi controller", 503)
    path = f"/machine/unattached/{radios[0]}"
    qmp_call("qom-set", path=path, property="radio-enabled", value=enabled)
    if qmp_call("qom-get", path=path, property="radio-enabled")["return"] is not enabled:
        raise ServiceError("wifi_monitor_fixture_isolation", "radio state mismatch before boot", 503)
