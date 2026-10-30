"""Stateless esp-emu network execution request parsing."""
from __future__ import annotations

from typing import Any

from device_service_errors import ServiceError
from device_service_parsing import is_sha256, parse_capture_pcap
from device_service_specs import DeviceSpec
from network_lane import normalize_hostfwd, normalize_i2c_device


def parse_network_execution(
    spec: DeviceSpec,
    value: Any,
) -> dict:
    if not spec.network_chip or not spec.network_profiles:
        raise ServiceError(
            "network_not_supported",
            f"{spec.id} has no esp-emu network runtime",
            409,
        )
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_network", "network must be an object", 400)
    default_profile = (
        "esp-idf-http"
        if "esp-idf-http" in spec.network_profiles
        else spec.network_profiles[0]
    )
    profile = value.get("profile", default_profile)
    if profile not in spec.network_profiles:
        raise ServiceError(
            "unsupported_network_profile",
            f"network profile {profile!r} is not available for {spec.id}",
            400,
        )
    defaults = {
        "esp-idf-http": {"wifi": True, "ble": False, "tcp": True},
        "esp-idf-smoke": {"wifi": True, "ble": True, "tcp": False},
        "idf-dns-udp": {"wifi": True, "ble": False, "tcp": False},
        "esp-idf-wrong-password": {
            "wifi": True,
            "ble": False,
            "tcp": False,
        },
        "esp-idf-coex": {"wifi": True, "ble": True, "tcp": False},
        "uiflow2-sticks3": {"wifi": False, "ble": True, "tcp": False},
        "generic-observe": {"wifi": True, "ble": False, "tcp": False},
    }[profile]
    net_mode = value.get(
        "net_mode",
        "user,restrict=yes" if profile == "generic-observe" else "user",
    )
    if net_mode not in {"user", "user,restrict=yes"}:
        raise ServiceError(
            "invalid_network",
            "network.net_mode must be 'user' or 'user,restrict=yes'",
            400,
        )
    capture_pcap = parse_capture_pcap(
        value.get("capture_pcap"),
        default=False,
    )
    if capture_pcap:
        raise ServiceError(
            "pcap_not_supported",
            "runtime=network uses esp-emu user networking, which does not "
            "expose an Ethernet pcap; use runtime=qemu-unified",
            409,
        )
    raw_hostfwd = value.get("hostfwd", [])
    if not isinstance(raw_hostfwd, list) or len(raw_hostfwd) > 8:
        raise ServiceError(
            "invalid_network",
            "network.hostfwd must contain at most 8 entries",
            400,
        )
    hostfwd: list[str] = []
    seen_forwards: set[tuple[str, int]] = set()
    for index, item in enumerate(raw_hostfwd):
        if not isinstance(item, dict):
            raise ServiceError(
                "invalid_network",
                f"network.hostfwd[{index}] must be an object",
                400,
            )
        protocol = item.get("protocol")
        host_port = item.get("host_port")
        guest_port = item.get("guest_port")
        if protocol not in {"tcp", "udp"}:
            raise ServiceError(
                "invalid_network",
                f"network.hostfwd[{index}].protocol must be tcp or udp",
                400,
            )
        if (
            isinstance(host_port, bool)
            or not isinstance(host_port, int)
            or not 1024 <= host_port <= 65535
            or isinstance(guest_port, bool)
            or not isinstance(guest_port, int)
            or not 1 <= guest_port <= 65535
        ):
            raise ServiceError(
                "invalid_network",
                (
                    f"network.hostfwd[{index}] ports must use host 1024-65535 "
                    "and guest 1-65535"
                ),
                400,
            )
        key = (str(protocol), host_port)
        if key in seen_forwards:
            raise ServiceError(
                "invalid_network",
                f"network.hostfwd contains duplicate {protocol}/{host_port}",
                400,
            )
        seen_forwards.add(key)
        try:
            hostfwd.append(
                normalize_hostfwd(
                    f"{protocol}:127.0.0.1:{host_port}-:{guest_port}"
                )
            )
        except ValueError as error:
            raise ServiceError(
                "invalid_network",
                f"network.hostfwd[{index}] is invalid: {error}",
                400,
            ) from error
    console_mode = value.get(
        "console_mode",
        (
            spec.network_console
            if profile == "generic-observe"
            else "uart0"
        ),
    )
    if console_mode not in {"auto", "uart0", "usb-jtag"}:
        raise ServiceError(
            "invalid_network",
            "network.console_mode must be auto, uart0 or usb-jtag",
            400,
        )

    def boolean(name: str) -> bool:
        candidate = value.get(name, defaults[name])
        if not isinstance(candidate, bool):
            raise ServiceError(
                "invalid_network", f"network.{name} must be a boolean", 400
            )
        return candidate

    ssid = value.get("wifi_ssid", "myssid")
    password = value.get("wifi_password", "mypassword")
    firmware_ap_password = value.get("firmware_ap_password")
    wifi_auth = value.get("wifi_auth", "wpa2-wpa3")
    psram_size = value.get(
        "psram_size",
        "8M" if spec.network_chip == "esp32s3" else "0",
    )
    if not isinstance(ssid, str) or not 1 <= len(ssid) <= 32:
        raise ServiceError(
            "invalid_network", "network.wifi_ssid must be 1-32 characters", 400
        )
    if not isinstance(password, str) or len(password) > 63:
        raise ServiceError(
            "invalid_network", "network.wifi_password is invalid", 400
        )
    if firmware_ap_password is not None and (
        not isinstance(firmware_ap_password, str)
        or len(firmware_ap_password) > 63
        or (firmware_ap_password and len(firmware_ap_password) < 8)
    ):
        raise ServiceError(
            "invalid_network",
            (
                "network.firmware_ap_password must be empty for an open AP "
                "or 8-63 characters"
            ),
            400,
        )
    if wifi_auth not in {"wpa2-wpa3", "wpa3-sae", "wpa2-psk", "open"}:
        raise ServiceError(
            "invalid_network", "network.wifi_auth is not supported", 400
        )
    if psram_size not in {"0", "2M", "4M", "8M", "16M", "32M", "64M"}:
        raise ServiceError(
            "invalid_network", "network.psram_size is not supported", 400
        )
    try:
        timeout = float(value.get("timeout_seconds", 60))
    except (TypeError, ValueError) as error:
        raise ServiceError(
            "invalid_network", "network.timeout_seconds must be numeric", 400
        ) from error
    if not 5 <= timeout <= 300:
        raise ServiceError(
            "invalid_network",
            "network.timeout_seconds must be between 5 and 300",
            400,
        )
    elf_artifact_id = value.get("elf_artifact_id")
    if elf_artifact_id is not None and (
        not isinstance(elf_artifact_id, str) or not is_sha256(elf_artifact_id)
    ):
        raise ServiceError(
            "invalid_network", "network.elf_artifact_id is invalid", 400
        )
    ble_name = value.get(
        "ble_name",
        "nimble-bleprph"
        if profile == "esp-idf-coex"
        else "M5-NETWORK-LANE",
    )
    if not isinstance(ble_name, str) or not 1 <= len(ble_name) <= 29:
        raise ServiceError(
            "invalid_network", "network.ble_name must be 1-29 characters", 400
        )
    wifi = boolean("wifi")
    ble = boolean("ble")
    tcp = boolean("tcp")
    if (
        ble
        and profile in {
            "uiflow2-sticks3",
            "esp-idf-coex",
            "generic-observe",
        }
        and not elf_artifact_id
    ):
        raise ServiceError(
            "elf_required",
            f"{profile} BLE requires network.elf_artifact_id",
            400,
        )
    expected_markers = value.get("expected_markers", [])
    if (
        not isinstance(expected_markers, list)
        or len(expected_markers) > 16
        or any(
            not isinstance(marker, str) or not 1 <= len(marker) <= 200
            for marker in expected_markers
        )
    ):
        raise ServiceError(
            "invalid_network",
            "network.expected_markers must contain at most 16 short strings",
            400,
        )
    raw_i2c_devices = value.get("i2c_devices", [])
    if (
        not isinstance(raw_i2c_devices, list)
        or len(raw_i2c_devices) > 32
        or any(not isinstance(item, str) for item in raw_i2c_devices)
    ):
        raise ServiceError(
            "invalid_network",
            "network.i2c_devices must contain at most 32 strings",
            400,
        )
    try:
        i2c_devices = [
            normalize_i2c_device(item) for item in raw_i2c_devices
        ]
    except ValueError as error:
        raise ServiceError(
            "invalid_network",
            f"network.i2c_devices is invalid: {error}",
            400,
        ) from error
    return {
        "profile": profile,
        "chip": spec.network_chip,
        "wifi": wifi,
        "ble": ble,
        "tcp": tcp,
        "wifi_ssid": ssid,
        "wifi_password": password,
        "firmware_ap_password": firmware_ap_password,
        "wifi_auth": wifi_auth,
        "psram_size": psram_size,
        "ble_name": ble_name,
        "timeout_seconds": timeout,
        "elf_artifact_id": elf_artifact_id,
        "expected_markers": expected_markers,
        "net_mode": net_mode,
        "hostfwd": hostfwd,
        "console_mode": console_mode,
        "i2c_devices": i2c_devices,
        "capture_pcap": False,
    }
