#!/usr/bin/env python3
"""Leased, on-demand virtual M5Stack device service.

This module is intentionally a local, trusted-workstation service. It owns the
process lifecycle for QEMU/esp-emu-backed ESP32 devices and exposes an HTTP
API through serve.py. Network emulation is outside this first service scope;
Tab5 is supported with an explicit partial-peripheral warning.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"
PROFILES = ROOT / "platform/qemu/profiles.json"
DEVICE_CATALOG = ROOT / "devices/catalog.source.json"
TEST_TOOLS = ROOT / "tests/uiflow2"
if str(TEST_TOOLS) not in sys.path:
    sys.path.insert(0, str(TEST_TOOLS))

from esp_flash import default_env, flash_with_esp_emu, flash_with_qemu  # noqa: E402
from run_profile_ui_test import (  # noqa: E402
    QMP,
    read_ppm,
    send_input,
    wait_qmp,
    write_rgb_png,
)
from run_tab5_ui_test import (  # noqa: E402
    capture_framebuffer,
    free_tcp_port,
    inject_touch,
    logical_to_raw_touch,
    orient_rgb565,
    rgb565_to_rgb,
    wait_for_path as wait_for_fs_path,
    wait_for_port as wait_for_tcp_port,
    write_png as write_tab5_png,
)
from firmware_analysis import (  # noqa: E402
    analyze_esp_image,
    analyze_firmware,
    expected_chip_id,
    parse_partition_table,
)
from network_lane import normalize_i2c_device  # noqa: E402

DEFAULT_STATE_DIR = ROOT / "platform/.cache/service"
DEFAULT_MAX_SESSIONS = 12
DEFAULT_MAX_PER_DEVICE = 8
QMP_COMMAND_TIMEOUT = 2
QMP_START_TIMEOUT = 60
EXCLUDED_DEVICES = {
    "cardputer-zero": "CardputerZero uses a separate Linux backend",
}
MAX_ARTIFACT_BYTES = 96 * 1024 * 1024
MAX_SERIAL_READ = 256 * 1024
ACTIVE_STATES = {"provisioning", "flashing", "booting", "running"}
ALLOWED_RUNTIME_ENV = {
    "M5SW_I2S_DMA_IRQ",
    "M5SW_I2S_PCM_FILE",
    "M5SW_I2S_RX_PCM_FILE",
    "M5SW_I2S_TRACE",
}
NETWORK_LANE = ROOT / "platform/tools/network_lane.py"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
DEFAULT_NETWORK_EMULATOR = (
    ROOT
    / ".work/esp-emu-versions/0.50.0"
    / "esp-emu-0.50.0-aarch64-apple-darwin/esp-emu"
)
NETWORK_PROFILES = {
    "uiflow2-sticks3",
    "esp-idf-http",
    "esp-idf-smoke",
    "idf-dns-udp",
    "esp-idf-coex",
    "generic-observe",
}
NETWORK_STATUSES = {
    "validated",
    "unverified",
    "board-init-blocked",
    "not-supported",
}
CORE2_WIFI_PROFILE = "core2-openmac"
CORE2_BLE_PROFILE = "core2-ble-advertise"
CORE2_HCI_GATT_PROFILE = "core2-hci-gatt"
STICKS3_UNIFIED_PROFILE = "uiflow2-sticks3-unified"
CORES3_UNIFIED_PROFILE = "uiflow2-cores3-unified"
CARDPUTER_ADV_UNIFIED_PROFILE = "uiflow2-cardputer-adv-unified"
UNIFIED_PROFILES = {
    STICKS3_UNIFIED_PROFILE,
    CORES3_UNIFIED_PROFILE,
    CARDPUTER_ADV_UNIFIED_PROFILE,
}
UNIFIED_HTTP_PORTS = {
    STICKS3_UNIFIED_PROFILE: 18080,
    CORES3_UNIFIED_PROFILE: 18081,
    CARDPUTER_ADV_UNIFIED_PROFILE: 18082,
}
QEMU_WIFI_RUNTIME = "qemu-wifi"
QEMU_BLE_RUNTIME = "qemu-ble"
CORE2_HCI_GATT_MARKERS = (
    "CORE2_HCI_BLE_READY",
    "CORE2_HCI_BLE_RX",
    "CORE2_HCI_BLE_ACK_SENT",
)
CORE2_HCI_PROBE_MARKERS = (
    "BLE_BUMBLE_FOUND",
    "BLE_BUMBLE_CONNECTED",
    "BLE_BUMBLE_GATT_DISCOVERED",
    "BLE_BUMBLE_SUBSCRIBED",
    "BLE_BUMBLE_WRITE",
    "BLE_BUMBLE_NOTIFICATION_OK",
    "BLE_BUMBLE_PASS",
)
STICKS3_UNIFIED_MARKERS = (
    "UNIFIED_STICKS3_WIFI_CONNECTED",
    "UNIFIED_STICKS3_HTTP_PASS",
    "UNIFIED_STICKS3_BLE_RX",
    "UNIFIED_STICKS3_BLE_ACK_SENT",
)
CORES3_UNIFIED_MARKERS = (
    "UNIFIED_CORES3_WIFI_CONNECTED",
    "UNIFIED_CORES3_HTTP_PASS",
    "UNIFIED_CORES3_BLE_RX",
    "UNIFIED_CORES3_BLE_ACK_SENT",
)
CARDPUTER_ADV_UNIFIED_MARKERS = (
    "UNIFIED_CARDPUTER_WIFI_CONNECTED",
    "UNIFIED_CARDPUTER_HTTP_PASS",
    "UNIFIED_CARDPUTER_BLE_RX",
    "UNIFIED_CARDPUTER_BLE_ACK_SENT",
)
UNIFIED_MARKERS = {
    STICKS3_UNIFIED_PROFILE: STICKS3_UNIFIED_MARKERS,
    CORES3_UNIFIED_PROFILE: CORES3_UNIFIED_MARKERS,
    CARDPUTER_ADV_UNIFIED_PROFILE: CARDPUTER_ADV_UNIFIED_MARKERS,
}
UNIFIED_READY_MARKERS = {
    STICKS3_UNIFIED_PROFILE: "UNIFIED_STICKS3_READY",
    CORES3_UNIFIED_PROFILE: "UNIFIED_CORES3_READY",
    CARDPUTER_ADV_UNIFIED_PROFILE: "UNIFIED_CARDPUTER_READY",
}
UNIFIED_HTTP_BODIES = {
    STICKS3_UNIFIED_PROFILE: b"UNIFIED_STICKS3_OK\n",
    CORES3_UNIFIED_PROFILE: b"UNIFIED_CORES3_OK\n",
    CARDPUTER_ADV_UNIFIED_PROFILE: b"UNIFIED_CARDPUTER_OK\n",
}
UNIFIED_BLE_IDENTITIES = {
    "sticks3": ("M5-STICKS3-UNIFIED", "M5_STICKS3_UNIFIED"),
    "cores3": ("M5-CORES3-UNIFIED", "M5_CORES3_UNIFIED"),
    "cardputer-adv": ("M5-CPTR-ADV-UNIFIED", "M5_CPTR_ADV"),
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redacted_network_config(config: dict | None) -> dict:
    safe = dict(config or {})
    if safe.get("password"):
        safe["password"] = "<redacted>"
    return safe


def parse_int(value: Any, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise ServiceError("invalid_request", f"{field} must be an integer", 400)


def parse_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        width, height = value.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return None


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON without exposing a partially-written session record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    os.replace(temporary, path)


class UnifiedHttpFixture:
    """Controlled HTTP endpoint used by a unified board probe."""

    def __init__(
        self,
        log_path: Path,
        body: bytes = b"UNIFIED_STICKS3_OK\n",
        port: int = 18080,
    ):
        self.requests: list[dict[str, str]] = []
        self.log_path = log_path
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                record = {
                    "path": self.path,
                    "host": self.headers.get("Host", ""),
                }
                owner.requests.append(record)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="m5-unified-http",
            daemon=True,
        )
        self.thread.start()

    def close(self) -> None:
        self.log_path.write_text(
            json.dumps(self.requests, ensure_ascii=False, indent=2) + "\n"
        )
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


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
        not isinstance(elf_artifact_id, str) or not _is_sha256(elf_artifact_id)
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
        "wifi_auth": wifi_auth,
        "psram_size": psram_size,
        "ble_name": ble_name,
        "timeout_seconds": timeout,
        "elf_artifact_id": elf_artifact_id,
        "expected_markers": expected_markers,
        "net_mode": net_mode,
        "console_mode": console_mode,
        "i2c_devices": i2c_devices,
    }


def core2_radio_qemu_path() -> Path:
    raw_path = os.environ.get("M5_CORE2_RADIO_QEMU") or os.environ.get(
        "M5_CORE2_WIFI_QEMU"
    )
    if not raw_path:
        raise ServiceError(
            "qemu_wifi_backend_unavailable",
            "M5_CORE2_RADIO_QEMU must point to a QEMU build with "
            "classic ESP32 WiFi/BT support",
            503,
        )
    path = Path(raw_path)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ServiceError(
            "qemu_wifi_backend_unavailable",
            "Core2 radio QEMU does not point to an executable file",
            503,
        )
    return path


def parse_qemu_wifi_execution(
    spec: DeviceSpec,
    value: Any,
) -> dict:
    if spec.id != "core2":
        raise ServiceError(
            "qemu_wifi_not_supported",
            "qemu-wifi is currently limited to Core2 classic ESP32",
            409,
        )
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_network", "network must be an object", 400)
    profile = value.get("profile", CORE2_WIFI_PROFILE)
    if profile != CORE2_WIFI_PROFILE:
        raise ServiceError(
            "unsupported_network_profile",
            f"unsupported qemu-wifi profile: {profile!r}",
            400,
        )
    net_mode = value.get("net_mode", "user")
    if net_mode != "user":
        raise ServiceError(
            "invalid_network",
            "qemu-wifi currently supports only net_mode=user",
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
    attempts = value.get("attempts", 5)
    if not isinstance(attempts, int) or not 1 <= attempts <= 10:
        raise ServiceError(
            "invalid_network",
            "network.attempts must be an integer from 1 to 10",
            400,
        )
    core2_radio_qemu_path()
    return {
        "profile": profile,
        "net_mode": net_mode,
        "nic": "misc.esp32_wifi",
        "expected_markers": expected_markers,
        "attempts": attempts,
    }


def parse_qemu_ble_execution(
    spec: DeviceSpec,
    value: Any,
) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_network", "network must be an object", 400)
    if spec.id == "core2":
        supported_profiles = {
            CORE2_BLE_PROFILE,
            CORE2_HCI_GATT_PROFILE,
        }
        default_profile = CORE2_BLE_PROFILE
    elif spec.id == "sticks3":
        supported_profiles = {STICKS3_UNIFIED_PROFILE}
        default_profile = STICKS3_UNIFIED_PROFILE
    elif spec.id == "cores3":
        supported_profiles = {CORES3_UNIFIED_PROFILE}
        default_profile = CORES3_UNIFIED_PROFILE
    elif spec.id == "cardputer-adv":
        supported_profiles = {CARDPUTER_ADV_UNIFIED_PROFILE}
        default_profile = CARDPUTER_ADV_UNIFIED_PROFILE
    else:
        raise ServiceError(
            "qemu_ble_not_supported",
            "qemu-ble is not supported for this device",
            409,
        )
    profile = value.get("profile", default_profile)
    if profile not in supported_profiles:
        raise ServiceError(
            "unsupported_network_profile",
            f"unsupported qemu-ble profile: {profile!r}",
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
    if profile == CORE2_HCI_GATT_PROFILE and not expected_markers:
        expected_markers = list(CORE2_HCI_GATT_MARKERS)
    elif profile in UNIFIED_MARKERS and not expected_markers:
        expected_markers = list(UNIFIED_MARKERS[profile])
    attempts = value.get("attempts", 5)
    if not isinstance(attempts, int) or not 1 <= attempts <= 10:
        raise ServiceError(
            "invalid_network",
            "network.attempts must be an integer from 1 to 10",
            400,
        )
    if spec.id == "core2":
        core2_radio_qemu_path()
    return {
        "profile": profile,
        "expected_markers": expected_markers,
        "attempts": attempts,
        "nic": (
            "misc.esp32_wifi"
            if spec.id == "core2"
            else "misc.esp32s3.wifi"
        ),
        "ble_name": (
            "M5-CORE2-HCI"
            if spec.id == "core2"
            else UNIFIED_BLE_IDENTITIES[spec.id][0]
        ),
    }


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


@dataclass(frozen=True)
class DeviceSpec:
    id: str
    name: str
    group: str
    soc: str
    sku: str
    device_codes: list[str]
    backend: str
    machine: str
    flash_size: int
    display: dict | None
    reference_path: Path | None
    qemu: Path
    rom_dir: Path
    efuse_driver: str | None
    memory: str | None
    env: dict[str, str]
    mode: str
    expected_size: tuple[int, int] | None
    supported: bool
    flash_emulator: Path | None
    service_kind: str
    emulator: Path | None
    elf: Path | None
    rom: Path | None
    efuse: Path | None
    c6_firmware: Path | None
    peripheral_status: str
    network_chip: str | None
    network_profiles: list[str]
    network_console: str
    network_status: str
    warnings: list[str]
    state_probes: dict[str, dict[str, Any]]
    reason: str | None

    @property
    def has_display(self) -> bool:
        display = self.display or {}
        return bool(display.get("width") and display.get("height"))

    @property
    def reference_available(self) -> bool:
        return bool(self.reference_path and self.reference_path.is_file())

    @property
    def backend_ready(self) -> bool:
        if self.service_kind == "tab5":
            return all(
                path is not None and path.is_file()
                for path in (
                    self.emulator,
                    self.rom,
                    self.efuse,
                    self.c6_firmware,
                    self.reference_path,
                )
            )
        return (
            self.qemu.is_file()
            and self.rom_dir.is_dir()
            and (self.flash_emulator is None or self.flash_emulator.is_file())
        )


def load_device_specs() -> dict[str, DeviceSpec]:
    matrix = json.loads(MATRIX.read_text())
    profiles = json.loads(PROFILES.read_text())
    catalog_source = json.loads(DEVICE_CATALOG.read_text())
    profiles_by_id = {row["id"]: row for row in profiles["devices"]}
    source_by_id = {row["id"]: row for row in catalog_source["devices"]}
    specs = {}
    for row in matrix["devices"]:
        device_id = row["id"]
        backend = matrix["backends"].get(row["backend"], {})
        profile = profiles_by_id.get(device_id, {})
        source = source_by_id.get(device_id, {})
        uiflow_source = source.get("uiflow2") or {}
        excluded_reason = EXCLUDED_DEVICES.get(device_id)
        reference = ROOT / row["base"] if row.get("base") else None
        if device_id == "tab5":
            supported = True
            service_kind = "tab5"
            qemu = ROOT / "__missing_qemu__"
            rom_dir = ROOT / "__missing_rom__"
            emulator = ROOT / row["emulator"]
            elf = ROOT / row["elf"]
            rom = ROOT / row["rom"]
            efuse = ROOT / row["efuse"]
            c6_firmware = ROOT / row["c6_firmware"]
            flash_emulator = emulator
            network_chip = None
            network_profiles: list[str] = []
            network_console = "auto"
            network_status = "not-supported"
            reason = None
        else:
            supported = (
                excluded_reason is None
                and bool(backend)
                and row["backend"].startswith("qemu-esp32")
                and row["mode"] in {"ui", "console"}
            )
            service_kind = "qemu"
            qemu = (
                ROOT / backend["qemu"]
                if backend.get("qemu")
                else ROOT / "__missing_qemu__"
            )
            rom_dir = (
                ROOT / backend["rom_dir"]
                if backend.get("rom_dir")
                else ROOT / "__missing_rom__"
            )
            emulator = None
            elf = None
            rom = None
            efuse = None
            c6_firmware = None
            flash_emulator = (
                ROOT / ".work/bin/esp-emu"
                if backend.get("esp_emu_chip")
                else None
            )
            network_chip = backend.get("esp_emu_chip")
            network_console = row.get("network_console", "auto")
            network_status = (
                row.get("network_status", "unverified")
                if network_chip
                else "not-supported"
            )
            if network_status not in NETWORK_STATUSES:
                raise ServiceError(
                    "invalid_network_status",
                    f"{device_id} has invalid network_status {network_status!r}",
                    500,
                )
            network_profiles = (
                sorted(NETWORK_PROFILES - {"uiflow2-sticks3"})
                if network_chip
                else []
            )
            if device_id == "sticks3" and network_chip:
                network_profiles.insert(0, "uiflow2-sticks3")
                network_profiles.insert(0, STICKS3_UNIFIED_PROFILE)
            if device_id == "cores3" and network_chip:
                network_profiles.insert(0, CORES3_UNIFIED_PROFILE)
            if device_id == "cardputer-adv" and network_chip:
                network_profiles.insert(0, CARDPUTER_ADV_UNIFIED_PROFILE)
            if (
                device_id == "core2"
                and (
                    os.environ.get("M5_CORE2_RADIO_QEMU")
                    or os.environ.get("M5_CORE2_WIFI_QEMU")
                )
            ):
                core2_radio_qemu_path()
                network_profiles = [
                    CORE2_WIFI_PROFILE,
                    CORE2_BLE_PROFILE,
                    CORE2_HCI_GATT_PROFILE,
                ]
                network_status = "unverified"
            reason = excluded_reason
            if not backend and reason is None:
                reason = (
                    f"backend {row['backend']} is not registered for service execution"
                )
            if not supported and reason is None:
                reason = f"backend mode {row.get('mode')} is not enabled for this service"
        specs[device_id] = DeviceSpec(
            id=device_id,
            name=profile.get("name", device_id),
            group=profile.get("group", ""),
            soc=profile.get("soc", ""),
            sku=source.get("sku", ""),
            device_codes=(
                [source["uiflow2"]["firmware"]["firmware_id"]]
                if (uiflow_source.get("firmware") or {}).get("firmware_id")
                else []
            ),
            backend=row["backend"],
            machine=row.get("machine", ""),
            flash_size=(
                16 << 20
                if device_id == "tab5"
                else int(row.get("flash_size", "0"), 0)
            ),
            display=profile.get("display"),
            reference_path=reference,
            qemu=qemu,
            rom_dir=rom_dir,
            efuse_driver=backend.get("efuse_driver"),
            memory=row.get("memory"),
            env=row.get("env", {}),
            mode=row["mode"],
            expected_size=parse_size(row.get("expected_size")),
            supported=supported,
            flash_emulator=flash_emulator,
            service_kind=service_kind,
            emulator=emulator,
            elf=elf,
            rom=rom,
            efuse=efuse,
            c6_firmware=c6_firmware,
            peripheral_status=profile.get(
                "peripheral_status",
                "simulated" if supported else "not-applicable",
            ),
            network_chip=network_chip,
            network_profiles=network_profiles,
            network_console=network_console,
            network_status=network_status,
            warnings=list(profile.get("blockers", [])),
            state_probes=(
                profile.get("runtime_state", {})
                if isinstance(profile.get("runtime_state", {}), dict)
                else {}
            ),
            reason=reason,
        )
    return specs


class ArtifactStore:
    """Content-addressed binary artifacts used by firmware manifests."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _meta(self, artifact_id: str) -> Path:
        return self.root / f"{artifact_id}.json"

    def _data(self, artifact_id: str) -> Path:
        return self.root / f"{artifact_id}.bin"

    def create(
        self,
        data: bytes,
        *,
        name: str = "",
        content_type: str = "application/octet-stream",
    ) -> dict:
        if not data:
            raise ServiceError("empty_artifact", "artifact must not be empty", 400)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ServiceError(
                "artifact_too_large",
                f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes",
                413,
            )
        artifact_id = hashlib.sha256(data).hexdigest()
        with self._lock:
            if not self._data(artifact_id).exists():
                temp = self.root / f".{artifact_id}.{uuid.uuid4().hex}.tmp"
                temp.write_bytes(data)
                temp.replace(self._data(artifact_id))
            record = {
                "artifact_id": artifact_id,
                "sha256": artifact_id,
                "size": len(data),
                "name": name or f"artifact-{artifact_id[:12]}.bin",
                "content_type": content_type,
                "created_at": iso_now(),
            }
            self._meta(artifact_id).write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            )
        return record

    def read(self, artifact_id: str) -> bytes:
        if not isinstance(artifact_id, str) or not _is_sha256(artifact_id):
            raise ServiceError("unknown_artifact", "invalid artifact id", 404)
        with self._lock:
            path = self._data(artifact_id)
            if not path.is_file():
                raise ServiceError(
                    "unknown_artifact", f"unknown artifact: {artifact_id}", 404
                )
            return path.read_bytes()

    def path(self, artifact_id: str) -> Path:
        self.get(artifact_id)
        with self._lock:
            path = self._data(artifact_id)
            if not path.is_file():
                raise ServiceError(
                    "unknown_artifact", f"artifact data is missing: {artifact_id}", 404
                )
            return path

    def get(self, artifact_id: str) -> dict:
        if not isinstance(artifact_id, str) or not _is_sha256(artifact_id):
            raise ServiceError("unknown_artifact", "invalid artifact id", 404)
        with self._lock:
            meta = self._meta(artifact_id)
            if not meta.is_file():
                raise ServiceError(
                    "unknown_artifact", f"unknown artifact: {artifact_id}", 404
                )
            return json.loads(meta.read_text())

    def list(self) -> list[dict]:
        with self._lock:
            records = [
                json.loads(path.read_text())
                for path in self.root.glob("*.json")
            ]
        return sorted(
            records,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def delete(self, artifact_id: str) -> dict:
        record = self.get(artifact_id)
        with self._lock:
            self._data(artifact_id).unlink(missing_ok=True)
            self._meta(artifact_id).unlink(missing_ok=True)
        return {"artifact_id": artifact_id, "deleted": True, "record": record}


class FirmwareStore:
    """Build complete/flash-sized images from uploaded or segmented artifacts."""

    def __init__(self, root: Path, artifacts: ArtifactStore, specs: dict[str, DeviceSpec]):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts = artifacts
        self.specs = specs
        self._lock = threading.RLock()

    def _meta(self, firmware_id: str) -> Path:
        return self.root / f"{firmware_id}.json"

    def _data(self, firmware_id: str) -> Path:
        return self.root / f"{firmware_id}.bin"

    def create(self, payload: dict) -> dict:
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or device_id not in self.specs:
            raise ServiceError("unknown_device", "device_id is required", 400)
        spec = self.specs[device_id]
        if not spec.supported:
            raise ServiceError(
                "unsupported_device",
                spec.reason or "device is not enabled for this service",
                409,
            )
        kind = payload.get("kind", "merged")
        image = bytearray(b"\xff" * spec.flash_size)
        intervals: list[tuple[int, int]] = []

        if kind == "merged":
            artifact_id = payload.get("artifact_id")
            data = self.artifacts.read(artifact_id)
            if len(data) > spec.flash_size:
                raise ServiceError(
                    "firmware_too_large",
                    f"firmware is {len(data)} bytes; device flash is {spec.flash_size}",
                    413,
                )
            image[: len(data)] = data
            intervals.append((0, len(data)))
            source = {"kind": "merged", "artifact_id": artifact_id}
        elif kind == "segmented":
            segments = payload.get("segments")
            if not isinstance(segments, list) or not segments:
                raise ServiceError(
                    "invalid_segments", "segments must be a non-empty list", 400
                )
            source_segments = []
            for index, segment in enumerate(segments):
                if not isinstance(segment, dict):
                    raise ServiceError(
                        "invalid_segments",
                        f"segments[{index}] must be an object",
                        400,
                    )
                offset = parse_int(segment.get("offset"), f"segments[{index}].offset")
                artifact_id = segment.get("artifact_id")
                data = self.artifacts.read(artifact_id)
                end = offset + len(data)
                if offset < 0 or end > spec.flash_size:
                    raise ServiceError(
                        "segment_out_of_range",
                        f"segment {index} range 0x{offset:x}-0x{end:x} "
                        f"exceeds flash size 0x{spec.flash_size:x}",
                        400,
                    )
                if not data:
                    raise ServiceError(
                        "empty_artifact",
                        f"segment {index} artifact is empty",
                        400,
                    )
                for start, existing_end in intervals:
                    if offset < existing_end and start < end:
                        raise ServiceError(
                            "overlapping_segments",
                            f"segment {index} overlaps another segment",
                            400,
                        )
                image[offset:end] = data
                intervals.append((offset, end))
                source_segments.append({"offset": offset, "artifact_id": artifact_id})
            source = {"kind": "segmented", "segments": source_segments}
        else:
            raise ServiceError(
                "unsupported_firmware_kind",
                "kind must be 'merged' or 'segmented'",
                400,
            )

        if not intervals:
            raise ServiceError("empty_firmware", "firmware has no data", 400)
        image_bytes = bytes(image)
        firmware_id = hashlib.sha256(image_bytes).hexdigest()
        record = {
            "firmware_id": firmware_id,
            "sha256": firmware_id,
            "device_id": device_id,
            "flash_size": spec.flash_size,
            "size": len(image_bytes),
            "kind": kind,
            "source": source,
            "header_magic": image_bytes[0],
            "created_at": iso_now(),
        }
        with self._lock:
            data_path = self._data(firmware_id)
            if not data_path.exists():
                temp = self.root / f".{firmware_id}.{uuid.uuid4().hex}.tmp"
                temp.write_bytes(image_bytes)
                temp.replace(data_path)
            self._meta(firmware_id).write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n"
            )
        return record

    def get(self, firmware_id: str) -> dict:
        if not _is_sha256(firmware_id):
            raise ServiceError("unknown_firmware", "invalid firmware id", 404)
        with self._lock:
            meta = self._meta(firmware_id)
            if not meta.is_file():
                raise ServiceError(
                    "unknown_firmware", f"unknown firmware: {firmware_id}", 404
                )
            return json.loads(meta.read_text())

    def path(self, firmware_id: str) -> Path:
        self.get(firmware_id)
        path = self._data(firmware_id)
        if not path.is_file():
            raise ServiceError("unknown_firmware", "firmware data missing", 404)
        return path

    def analyze(self, firmware_id: str) -> dict:
        record = self.get(firmware_id)
        spec = self.specs[record["device_id"]]
        result = analyze_firmware(
            self.path(firmware_id),
            expected_chip_id_value=expected_chip_id(spec.soc),
        )
        analysis = {
            "firmware_id": firmware_id,
            "device_id": record["device_id"],
            "device_chip": spec.soc,
            **result,
        }
        analysis_path = self.root / f"{firmware_id}.analysis.json"
        analysis_path.write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2) + "\n"
        )
        return analysis

    def get_analysis(self, firmware_id: str) -> dict:
        self.get(firmware_id)
        analysis_path = self.root / f"{firmware_id}.analysis.json"
        if not analysis_path.is_file():
            return self.analyze(firmware_id)
        return json.loads(analysis_path.read_text())


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def rgb_metrics(pixels: bytes) -> tuple[int, int]:
    nonblack = 0
    colors = set()
    for offset in range(0, len(pixels) - 2, 3):
        rgb = pixels[offset:offset + 3]
        if any(rgb):
            nonblack += 1
            if len(colors) < 512:
                colors.add(rgb)
    return nonblack, len(colors)


def default_flash_preparer(
    spec: DeviceSpec, image: Path, firmware_sha: str, out_dir: Path
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = default_env()
    env.update(spec.env)
    if spec.service_kind == "tab5":
        return flash_with_esp_emu(
            chip="esp32p4",
            image=image,
            flash_size=spec.flash_size,
            out_dir=out_dir,
            env=env,
            timeout=900,
            emulator=spec.emulator,
            rom=spec.rom,
            efuse=spec.efuse,
            extra_args=["--psram-size", "32M"],
            no_stub=True,
            chunk_size=1 << 20,
            chunk_ranges=[(0, 0x500000), (0x610000, 0x7F0000)],
            restart_per_chunk=True,
        )
    matrix_backend = json.loads(MATRIX.read_text())["backends"][spec.backend]
    if "esp_emu_chip" in matrix_backend:
        emulator = Path(
            os.environ.get(
                "M5_SERVICE_ESP_EMU",
                str(spec.flash_emulator or ROOT / ".work/bin/esp-emu"),
            )
        )
        return flash_with_esp_emu(
            chip=matrix_backend["esp_emu_chip"],
            image=image,
            flash_size=spec.flash_size,
            out_dir=out_dir,
            env=env,
            timeout=600,
            emulator=emulator,
        )
    return flash_with_qemu(
        chip=matrix_backend["qemu_esptool_chip"],
        machine=spec.machine,
        image=image,
        flash_size=spec.flash_size,
        out_dir=out_dir,
        env=env,
        qemu=spec.qemu,
        rom_dir=spec.rom_dir,
        timeout=900,
        memory=spec.memory,
    )


class DeviceSession:
    def __init__(
        self,
        service: "DeviceService",
        *,
        session_id: str,
        spec: DeviceSpec,
        firmware_id: str,
        firmware_path: Path,
        firmware_sha: str,
        firmware_source: str,
        source_artifacts: list[str],
        ttl_seconds: int,
        ready_marker: str | None,
        ready_timeout: float,
        ready_conditions: dict | None,
        runtime_env: dict[str, str] | None = None,
        runtime: str = "qemu",
        network_config: dict | None = None,
        network_result: dict | None = None,
        events: list[dict] | None = None,
        created_at: str | None = None,
        completed_at: str | None = None,
        expires_at: float | None = None,
        initial_state: str = "provisioning",
        error: str | None = None,
        flash_info: dict | None = None,
        restored: bool = False,
        interrupted: bool = False,
    ):
        self.service = service
        self.id = session_id
        self.spec = spec
        self.firmware_id = firmware_id
        self.firmware_path = firmware_path
        self.firmware_sha = firmware_sha
        self.firmware_source = firmware_source
        self.source_artifacts = source_artifacts
        self.runtime_env = dict(runtime_env or {})
        self.runtime = runtime
        self.network_config = dict(network_config or {})
        self.network_result = (
            dict(network_result) if isinstance(network_result, dict) else None
        )
        self.ttl_seconds = ttl_seconds
        self.ready_marker = ready_marker
        self.ready_timeout = ready_timeout
        self.ready_conditions = ready_conditions or {}
        self.created_at = created_at or iso_now()
        self.completed_at = completed_at
        self.expires_at = (
            expires_at if expires_at is not None else time.time() + ttl_seconds
        )
        self.state = initial_state
        self.error = error
        self.pid: int | None = None
        self.flash_info = flash_info
        self.virtual_flash: Path | None = None
        self.qmp_path = Path("/tmp") / f"m5-service-{session_id}.sock"
        self.dir = service.state_dir / "sessions" / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.serial0 = self.dir / "serial.log"
        self.serial1 = self.dir / "serial1.log"
        self.last_frame_path = self.dir / "last-frame.png"
        self.last_frame_meta_path = self.dir / "last-frame.json"
        self.device_state_path = self.dir / "device-state.json"
        self.session_record_path = self.dir / "session.json"
        self.events_path = self.dir / "events.json"
        self.stdout_path = self.dir / "qemu.stdout"
        self.stderr_path = self.dir / "qemu.stderr"
        self.hci_probe_log = self.dir / "ble-probe.log"
        self.http_fixture_log = self.dir / "http-fixture.json"
        self.speaker_pcm = self.dir / "speaker.pcm"
        self.hci_port: int | None = None
        self._hci_probe: subprocess.Popen | None = None
        self._http_fixture: UnifiedHttpFixture | None = None
        self._proc: subprocess.Popen | None = None
        self._qmp: QMP | None = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._last_frame_persisted_at = 0.0
        self.events: list[dict] = [dict(event) for event in (events or [])]
        self.restored = restored
        self.interrupted = interrupted
        if events is None:
            self._record_event(
                "created", device_id=spec.id, firmware_id=firmware_id
            )
        self._persist_session()

    def _record_event(self, event: str, **details) -> None:
        self.events.append(
            {
                "at": iso_now(),
                "event": event,
                **details,
            }
        )
        self._persist_events()

    def _persist_events(self) -> None:
        atomic_write_json(self.events_path, self.events)

    def _session_record(self) -> dict:
        return {
            "schema_version": 1,
            "session_id": self.id,
            "device_id": self.spec.id,
            "state": self.state,
            "pid": self.pid,
            "firmware_id": self.firmware_id,
            "firmware_sha256": self.firmware_sha,
            "firmware_source": self.firmware_source,
            "source_artifacts": list(self.source_artifacts),
            "runtime_env": dict(self.runtime_env),
            "runtime": self.runtime,
            "network": redacted_network_config(self.network_config),
            "network_result": self.network_result,
            "flash": self.flash_info,
            "ttl_seconds": self.ttl_seconds,
            "ready_marker": self.ready_marker,
            "ready_timeout_seconds": self.ready_timeout,
            "ready_conditions": self.ready_conditions,
            "created_at": self.created_at,
            "expires_at": datetime.fromtimestamp(
                self.expires_at, timezone.utc
            ).isoformat(),
            "completed_at": self.completed_at,
            "error": self.error,
            "restored": self.restored,
            "interrupted": self.interrupted,
        }

    def _persist_session(self) -> None:
        atomic_write_json(self.session_record_path, self._session_record())

    def snapshot(self) -> dict:
        with self._lock:
            if (
                self._proc is not None
                and self._proc.poll() is not None
                and self.state in ACTIVE_STATES
            ):
                self._handle_process_exit(self._proc.returncode)
            serial_size = self.serial0.stat().st_size if self.serial0.exists() else 0
            frame_meta = {}
            if self.last_frame_meta_path.is_file():
                try:
                    frame_meta = json.loads(self.last_frame_meta_path.read_text())
                except json.JSONDecodeError:
                    frame_meta = {}
            state_meta = {}
            if self.device_state_path.is_file():
                try:
                    state_meta = json.loads(self.device_state_path.read_text())
                except json.JSONDecodeError:
                    state_meta = {}
            return {
                "session_id": self.id,
                "device_id": self.spec.id,
                "state": self.state,
                "pid": self.pid,
                "firmware_id": self.firmware_id,
                "firmware_sha256": self.firmware_sha,
                "firmware_source": self.firmware_source,
                "artifact_sha256": (
                    self.source_artifacts[0] if self.source_artifacts else None
                ),
                "source_artifacts": list(self.source_artifacts),
                "runtime_env": dict(self.runtime_env),
                "runtime": self.runtime,
                "network": self.network_result
                or (
                    {
                        "status": "RUNNING",
                        "profile": self.network_config.get("profile"),
                    }
                    if self.network_config
                    else None
                ),
                "flash": self.flash_info,
                "serial_bytes": serial_size,
                "created_at": self.created_at,
                "expires_at": datetime.fromtimestamp(
                    self.expires_at, timezone.utc
                ).isoformat(),
                "error": self.error,
                "display": self.spec.display,
                "display_available": (
                    self.runtime
                    in {"qemu", QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}
                    and self.spec.has_display
                ),
                "last_frame_available": self.last_frame_path.is_file(),
                "last_frame_captured_at": frame_meta.get("captured_at"),
                "device_state_supported": bool(
                    self.runtime
                    in {"qemu", QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}
                    and self.spec.state_probes
                ),
                "last_device_state_available": self.device_state_path.is_file(),
                "last_device_state_at": state_meta.get("captured_at"),
                "completed_at": self.completed_at,
                "event_count": len(self.events),
                "restored": self.restored,
                "interrupted": self.interrupted,
            }

    def _handle_process_exit(self, returncode: int | None) -> None:
        self.state = "failed"
        self.error = self.error or f"process exited with code {returncode}"
        self.completed_at = self.completed_at or iso_now()
        self._record_event("process_exited", returncode=returncode)
        self._persist_session()

    def start(self) -> None:
        thread = threading.Thread(
            target=self._provision,
            name=f"m5-session-{self.id}",
            daemon=True,
        )
        thread.start()

    def _set_state(self, state: str) -> None:
        with self._lock:
            previous = self.state
            self.state = state
            self._record_event("state", **{"from": previous, "to": state})
            self._persist_session()

    def network_evidence(self) -> dict:
        if self.runtime not in {QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}:
            raise ServiceError(
                "network_evidence_not_supported",
                "network evidence is available only for qemu radio sessions",
                409,
            )
        serial = (
            self.serial0.read_text(errors="replace")
            if self.serial0.is_file()
            else ""
        )
        profile = self.network_config.get("profile")
        if profile in UNIFIED_PROFILES:
            default_markers = UNIFIED_MARKERS[profile]
            ble_name, ble_payload = UNIFIED_BLE_IDENTITIES[self.spec.id]
            probe_log = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            serial_markers = [
                str(marker)
                for marker in self.network_config.get(
                    "expected_markers",
                    default_markers,
                )
            ]
            http_requests: list[dict] = []
            if self._http_fixture is not None:
                http_requests = [dict(item) for item in self._http_fixture.requests]
            elif self.http_fixture_log.is_file():
                try:
                    loaded = json.loads(self.http_fixture_log.read_text())
                    if isinstance(loaded, list):
                        http_requests = [
                            item for item in loaded if isinstance(item, dict)
                        ]
                except json.JSONDecodeError:
                    http_requests = []
            checks = {
                f"serial:{marker}": marker in serial
                for marker in serial_markers
            }
            checks.update(
                {
                    f"peer:{marker}": marker in probe_log
                    for marker in CORE2_HCI_PROBE_MARKERS
                }
            )
            checks["http:controlled_request"] = http_requests == [
                {"path": "/unified", "host": "qemu.test"}
            ]
            if all(checks.values()):
                status = "PASS"
            elif serial.strip() or probe_log.strip():
                status = "PARTIAL"
            else:
                status = "RUNNING" if self.state in ACTIVE_STATES else "FAIL"
            return {
                "schema_version": 1,
                "kind": f"m5stack-{self.spec.id}-unified-qemu-proof",
                "scope": "simulation-only-not-hardware-validation",
                "status": status,
                "session_id": self.id,
                "device_id": self.spec.id,
                "profile": profile,
                "runtime": {
                    "name": "qemu",
                    "guest_process_count": 1,
                    "wifi_nic": self.network_config.get("nic"),
                    "hci_transport": "UART1 H4",
                    "ble_controller": "Bumble",
                    "ble_peer": "external Bumble peer",
                    "http_fixture": "controlled local endpoint",
                },
                "checks": checks,
                "expected_markers": serial_markers,
                "http_requests": http_requests,
                "serial_bytes": len(serial.encode()),
                "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
                "peer_log_bytes": len(probe_log.encode()),
                "peer_log_sha256": hashlib.sha256(
                    probe_log.encode()
                ).hexdigest(),
                "gatt": {
                    "name": ble_name,
                    "service": "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
                    "subscribe": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
                    "write": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
                    "payload": ble_payload,
                    "notification": "ACK:" + ble_payload,
                },
                "not_claimed": [
                    "real-hardware behavior",
                    "native ESP32-S3 Bluetooth controller model",
                    "RF security, range or performance",
                    "untrusted-firmware sandboxing",
                ],
            }
        if profile == CORE2_HCI_GATT_PROFILE:
            probe_log = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            serial_markers = [
                str(marker)
                for marker in self.network_config.get(
                    "expected_markers",
                    CORE2_HCI_GATT_MARKERS,
                )
            ]
            checks = {
                f"serial:{index + 1}": marker in serial
                for index, marker in enumerate(serial_markers)
            }
            checks.update(
                {
                    f"peer:{marker}": marker in probe_log
                    for marker in CORE2_HCI_PROBE_MARKERS
                }
            )
            if all(checks.values()):
                status = "PASS"
            elif serial.strip() or probe_log.strip():
                status = "PARTIAL"
            else:
                status = "RUNNING" if self.state in ACTIVE_STATES else "FAIL"
            return {
                "schema_version": 1,
                "kind": "m5stack-qemu-ble-hci-gatt-proof",
                "scope": "simulation-only-not-hardware-validation",
                "status": status,
                "session_id": self.id,
                "profile": profile,
                "runtime": {
                    "name": "qemu",
                    "hci_transport": "UART1 H4",
                    "controller": "Bumble",
                    "peer": "external Bumble peer",
                },
                "checks": checks,
                "expected_markers": serial_markers,
                "serial_bytes": len(serial.encode()),
                "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
                "peer_log_bytes": len(probe_log.encode()),
                "peer_log_sha256": hashlib.sha256(
                    probe_log.encode()
                ).hexdigest(),
                "gatt": {
                    "service": "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
                    "subscribe": "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
                    "write": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
                    "payload": "M5_CORE2_HCI",
                    "notification": "ACK:M5_CORE2_HCI",
                },
                "not_claimed": [
                    "real-hardware behavior",
                    "native ESP32 Bluetooth radio/controller model",
                    "RF range, timing, coexistence or performance",
                    "BLE pairing, security or production throughput",
                    "malware sandboxing",
                ],
            }
        markers = [
            str(marker)
            for marker in self.network_config.get("expected_markers", [])
        ]
        checks = {
            f"marker:{index + 1}": marker in serial
            for index, marker in enumerate(markers)
        }
        if markers and all(checks.values()):
            status = "PASS"
        elif serial.strip():
            status = "PARTIAL"
        else:
            status = "RUNNING" if self.state in ACTIVE_STATES else "FAIL"
        return {
            "schema_version": 1,
            "kind": (
                "m5stack-qemu-wifi-proof"
                if self.runtime == QEMU_WIFI_RUNTIME
                else "m5stack-qemu-ble-proof"
            ),
            "scope": "simulation-only-not-hardware-validation",
            "status": status,
            "session_id": self.id,
            "profile": self.network_config.get("profile"),
            "runtime": {
                "name": "qemu",
                "nic": self.network_config.get("nic"),
                "net_mode": self.network_config.get("net_mode"),
            },
            "checks": checks,
            "expected_markers": markers,
            "serial_bytes": len(serial.encode()),
            "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
            "not_claimed": [
                "real-hardware behavior",
                "BLE" if self.runtime == QEMU_WIFI_RUNTIME else "WiFi",
                "external BLE peer/GATT"
                if self.runtime == QEMU_BLE_RUNTIME
                else "external peer coverage",
                "malware sandboxing",
            ],
        }

    def _provision(self) -> None:
        try:
            self._set_state("flashing")
            prepared = self.service.prepare_flash(
                self.spec,
                self.firmware_path,
                self.firmware_sha,
                runtime=self.runtime,
            )
            self.virtual_flash = self.dir / "virtual-flash.bin"
            shutil.copyfile(prepared["path"], self.virtual_flash)
            self.flash_info = {
                **prepared["info"],
                "session_isolated_copy": True,
            }
            self._record_event("flash_prepared", **self.flash_info)
            self._persist_session()
            self._set_state("booting")
            if self.runtime in {QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}:
                self._provision_qemu_radio(prepared["path"])
            else:
                self._launch()
                if self.ready_conditions:
                    self.wait_ready(
                        {
                            "timeout_seconds": self.ready_timeout,
                            **self.ready_conditions,
                        }
                    )
                elif self.ready_marker:
                    self.wait_for_marker(self.ready_marker, self.ready_timeout)
            self._set_state("running")
        except Exception as error:
            with self._lock:
                self.error = str(error)
                self.state = "failed"
                self.completed_at = self.completed_at or iso_now()
                self._record_event("failed", error=str(error))
                self._persist_session()
            self._terminate_process()

    def _provision_qemu_radio(self, clean_flash: Path) -> None:
        attempts = int(self.network_config.get("attempts", 5))
        last_error: ServiceError | None = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                shutil.copyfile(clean_flash, self.virtual_flash)
            try:
                self._launch()
                if self.ready_conditions:
                    self.wait_ready(
                        {
                            "timeout_seconds": self.ready_timeout,
                            **self.ready_conditions,
                        }
                    )
                elif self.ready_marker:
                    self.wait_for_marker(
                        self.ready_marker,
                        self.ready_timeout,
                    )
                if (
                    self.network_config.get("profile")
                    in {CORE2_HCI_GATT_PROFILE, *UNIFIED_PROFILES}
                ):
                    self._wait_hci_probe_result(self.ready_timeout)
                self.network_result = self.network_evidence()
                self._record_event(
                    "qemu_radio_attempt",
                    attempt=attempt,
                    status="PASS",
                )
                return
            except ServiceError as error:
                last_error = error
                self._record_event(
                    "qemu_radio_attempt",
                    attempt=attempt,
                    status="FAIL",
                    error=error.message,
                )
                self._terminate_process()
                if error.code not in {
                    "ready_timeout",
                    "session_exited",
                    "qmp_timeout",
                    "ble_peer_failed",
                }:
                    raise
                if attempt == attempts:
                    raise
                for path in (
                    self.serial0,
                    self.hci_probe_log,
                    self.stdout_path,
                    self.stderr_path,
                ):
                    if path.is_file():
                        path.replace(
                            path.with_name(
                                f"{path.stem}-attempt-{attempt}{path.suffix}"
                            )
                        )
        if last_error is not None:
            raise last_error

    def _wait_hci_probe_result(self, timeout: float) -> None:
        deadline = time.time() + max(1.0, min(timeout, 30.0))
        while time.time() < deadline:
            text = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            if "BLE_BUMBLE_PASS" in text:
                self._record_event("ble_peer_pass")
                return
            if "BLE_BUMBLE_FAIL" in text or "BLE_BUMBLE_ERROR" in text:
                raise ServiceError(
                    "ble_peer_failed",
                    "external BLE peer did not complete the GATT exchange",
                    409,
                )
            if (
                self._hci_probe is not None
                and self._hci_probe.poll() is not None
            ):
                raise ServiceError(
                    "ble_peer_failed",
                    "external BLE peer exited before GATT completion",
                    409,
                )
            time.sleep(0.1)
        raise ServiceError(
            "ble_peer_failed",
            "timed out waiting for external BLE peer completion",
            408,
        )

    def _launch_hci_probe(self) -> None:
        if not BLE_PROBE.is_file():
            raise RuntimeError(f"BLE probe is missing: {BLE_PROBE}")
        profile = self.network_config.get("profile")
        unified = profile in UNIFIED_PROFILES
        if unified:
            name_prefix, payload = UNIFIED_BLE_IDENTITIES[self.spec.id]
        else:
            name_prefix = "M5-CORE2-HCI"
            payload = "M5_CORE2_HCI"
        self.hci_port = free_tcp_port()
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                [
                    str(ROOT / ".work/py"),
                    env.get("PYTHONPATH", ""),
                ],
            )
        )
        output = self.hci_probe_log.open("wb")
        try:
            self._hci_probe = subprocess.Popen(
                [
                    sys.executable,
                    str(BLE_PROBE),
                    "--port",
                    str(self.hci_port),
                    "--name-prefix",
                    name_prefix,
                    "--payload",
                    payload,
                    "--subscribe",
                    "--expect-notification-prefix",
                    "ACK:",
                    "--notification-timeout",
                    "15" if unified else "10",
                    "--timeout",
                    "40" if unified else "25",
                    "--write-delay",
                    "2" if unified else "1",
                    "--linger",
                    "20" if unified else "15",
                ],
                cwd=ROOT,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            output.close()
        deadline = time.time() + 10
        while time.time() < deadline:
            if (
                self.hci_probe_log.is_file()
                and "BLE_PROBE_READY"
                in self.hci_probe_log.read_text(errors="replace")
            ):
                self._record_event(
                    "hci_probe_started",
                    pid=self._hci_probe.pid,
                )
                return
            if self._hci_probe.poll() is not None:
                raise ServiceError(
                    "ble_peer_failed",
                    "external BLE peer exited during startup",
                    503,
                )
            time.sleep(0.05)
        raise ServiceError(
            "ble_peer_failed",
            "external BLE peer did not become ready",
            504,
        )

    def _launch_http_fixture(self) -> None:
        profile = self.network_config.get("profile")
        body = UNIFIED_HTTP_BODIES.get(profile)
        port = UNIFIED_HTTP_PORTS.get(profile)
        if body is None or port is None:
            raise ServiceError(
                "http_fixture_failed",
                f"no controlled HTTP port for profile {profile}",
                500,
            )
        try:
            self._http_fixture = UnifiedHttpFixture(
                self.http_fixture_log,
                body=body,
                port=port,
            )
        except OSError as error:
            raise ServiceError(
                "http_fixture_failed",
                f"controlled HTTP fixture could not start: {error}",
                503,
            ) from error
        self._record_event("http_fixture_started", port=port)

    def _launch(self) -> None:
        assert self.virtual_flash is not None
        efuse = self.dir / "efuse.bin"
        efuse_data = bytearray(4096)
        # The device matrix uses the same package-version encoding as the
        # existing profile runner.
        if "efuse_pkg_version" in self.service.raw_device(self.spec.id):
            pkg = int(self.service.raw_device(self.spec.id)["efuse_pkg_version"])
            efuse_data[36:40] = (pkg << 21).to_bytes(4, "little")
        efuse.write_bytes(efuse_data)
        try:
            self.qmp_path.unlink()
        except FileNotFoundError:
            pass
        unified = self.network_config.get("profile") in UNIFIED_PROFILES
        core2_radio = (
            self.spec.id == "core2"
            and self.runtime in {QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}
        )
        qemu_path = (
            core2_radio_qemu_path()
            if core2_radio
            else self.spec.qemu
        )
        profile = self.network_config.get("profile")
        hci_gatt = (
            self.runtime == QEMU_BLE_RUNTIME
            and profile in {CORE2_HCI_GATT_PROFILE, *UNIFIED_PROFILES}
        )
        if hci_gatt:
            self._launch_hci_probe()
        if unified:
            self._launch_http_fixture()
        command = [
            str(qemu_path),
            "-M", self.spec.machine,
            "-drive", f"file={self.virtual_flash},if=mtd,format=raw",
            "-L", str(self.spec.rom_dir),
            "-display", "none",
            "-serial", f"file:{self.serial0}",
        ]
        if hci_gatt:
            assert self.hci_port is not None
            command.extend(
                [
                    "-chardev",
                    (
                        "socket,id=hci,host=127.0.0.1,"
                        f"port={self.hci_port},nodelay=on"
                    ),
                    "-serial",
                    "chardev:hci",
                ]
            )
        else:
            command.extend(["-serial", f"file:{self.serial1}"])
        command.extend(
            ["-qmp", f"unix:{self.qmp_path},server=on,wait=off"]
        )
        if self.runtime == QEMU_WIFI_RUNTIME or unified:
            command.extend(
                [
                    "-nic",
                    (
                        "user,model=misc.esp32s3.wifi,id=wifi0"
                        if unified
                        else "user,model=misc.esp32_wifi,id=wifi0"
                    ),
                ]
            )
        if self.spec.efuse_driver != "none":
            command.extend(
                [
                    "-drive", f"if=none,id=efuse,file={efuse},format=raw",
                    "-global",
                    f"driver={self.spec.efuse_driver},property=drive,value=efuse",
                ]
            )
        if self.spec.memory is not None:
            command.extend(["-m", str(self.spec.memory)])
        env = os.environ.copy()
        env.update(self.spec.env)
        env.update(self.runtime_env)
        if unified:
            env["M5SW_I2S_DMA_IRQ"] = "1"
            env["M5SW_I2S_PCM_FILE"] = str(self.speaker_pcm)
        stdout = self.stdout_path.open("wb")
        stderr = self.stderr_path.open("wb")
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            stdout.close()
            stderr.close()
        self.pid = self._proc.pid
        self._persist_session()
        try:
            self._qmp = wait_qmp(self.qmp_path, timeout=QMP_START_TIMEOUT)
        except RuntimeError as error:
            raise ServiceError(
                "qmp_timeout",
                f"QEMU QMP socket did not become ready: {error}",
                504,
            ) from error
        self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)

    def _qmp_call(self, name: str, **arguments):
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                raise ServiceError("session_not_running", "device process is not running", 409)
            if self._qmp is None:
                self._qmp = wait_qmp(self.qmp_path, timeout=5)
                self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
            try:
                self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
                return self._qmp.cmd(name, **arguments)
            except (OSError, RuntimeError) as error:
                try:
                    self._qmp.close()
                except OSError:
                    pass
                self._qmp = None
                timeout = isinstance(error, TimeoutError)
                raise ServiceError(
                    "qmp_timeout" if timeout else "qmp_error",
                    f"QMP command {'timed out' if timeout else 'failed'}: {error}",
                    504 if timeout else 503,
                ) from error

    def wait_for_marker(self, marker: str, timeout: float) -> dict:
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            if self.serial0.exists() and marker in self.serial0.read_text(
                errors="replace"
            ):
                self._record_event("serial_marker", marker=marker)
                return self.snapshot()
            if self._proc and self._proc.poll() is not None:
                raise ServiceError(
                    "session_exited",
                    f"device exited before marker {marker!r}",
                    409,
                )
            time.sleep(0.1)
        raise ServiceError(
            "ready_timeout",
            f"timed out waiting for serial marker {marker!r}",
            408,
        )

    def wait_ready(self, payload: dict) -> dict:
        """Wait for application-level serial and/or framebuffer readiness."""

        timeout = float(payload.get("timeout_seconds", 30))
        conditions = payload.get("ready", payload)
        if not isinstance(conditions, dict):
            raise ServiceError("invalid_ready", "ready must be an object", 400)
        serial_markers = conditions.get("serial_markers", [])
        if isinstance(serial_markers, str):
            serial_markers = [serial_markers]
        if not isinstance(serial_markers, list):
            raise ServiceError(
                "invalid_ready", "serial_markers must be a list", 400
            )
        frame_nonblank = bool(conditions.get("frame_nonblank", False))
        frame_min_bytes = int(conditions.get("frame_min_bytes", 1024))
        frame_min_nonblack = int(
            conditions.get("frame_min_nonblack_pixels", 16)
        )
        require_all = bool(conditions.get("require_all", True))
        if frame_nonblank and not self.spec.has_display:
            raise ServiceError(
                "display_not_available",
                "frame_nonblank was requested for a serial-only device",
                400,
            )
        if not serial_markers and not frame_nonblank:
            return self.snapshot()

        deadline = time.time() + max(0.1, timeout)
        found_markers: list[str] = []
        first_serial_at: str | None = None
        first_frame_at: str | None = None
        last_frame: dict | None = None
        while time.time() < deadline:
            if serial_markers:
                serial_text = (
                    self.serial0.read_text(errors="replace")
                    if self.serial0.exists()
                    else ""
                )
                for marker in serial_markers:
                    if marker in serial_text and marker not in found_markers:
                        found_markers.append(marker)
                        first_serial_at = first_serial_at or iso_now()
                        self._record_event("serial_marker", marker=marker)
            serial_ready = (
                not serial_markers
                or (
                    len(found_markers) == len(serial_markers)
                    if require_all
                    else bool(found_markers)
                )
            )
            frame_ready = False
            if frame_nonblank and (serial_ready or not serial_markers or not require_all):
                try:
                    last_frame = self.frame_metrics()
                    frame_ready = (
                        last_frame["png_bytes"] >= frame_min_bytes
                        and last_frame["nonblack_pixels"] >= frame_min_nonblack
                    )
                    if frame_ready and first_frame_at is None:
                        first_frame_at = iso_now()
                        self._record_event(
                            "frame_nonblank",
                            nonblack_pixels=last_frame["nonblack_pixels"],
                            png_bytes=last_frame["png_bytes"],
                        )
                except ServiceError:
                    frame_ready = False
            criteria = [
                criterion
                for criterion, matched in (
                    ("serial_marker", serial_ready),
                    ("frame_nonblank", frame_ready),
                )
                if criterion in conditions or (
                    criterion == "serial_marker" and serial_markers
                ) or (criterion == "frame_nonblank" and frame_nonblank)
                if matched
            ]
            ready = (
                serial_ready and (frame_ready or not frame_nonblank)
                if require_all
                else bool(criteria)
            )
            if ready:
                self._record_event("application_ready", criteria=criteria)
                return {
                    **self.snapshot(),
                    "ready": True,
                    "ready_reason": criteria,
                    "serial_markers": found_markers,
                    "first_serial_at": first_serial_at,
                    "first_frame_at": first_frame_at,
                    "frame": (
                        {
                            key: value
                            for key, value in last_frame.items()
                            if key != "png"
                        }
                        if last_frame
                        else None
                    ),
                }
            if self._proc is not None and self._proc.poll() is not None:
                raise ServiceError(
                    "session_exited",
                    "device exited before application readiness",
                    409,
                )
            time.sleep(0.75)
        raise ServiceError(
            "ready_timeout",
            "application did not satisfy the requested readiness conditions",
            408,
            serial_markers=found_markers,
        )

    def serial_read(self, offset: int = 0, limit: int = 65536) -> dict:
        limit = min(max(int(limit), 1), MAX_SERIAL_READ)
        with self._lock:
            if not self.serial0.exists():
                return {
                    "session_id": self.id,
                    "offset": offset,
                    "next_offset": offset,
                    "data": "",
                    "bytes": 0,
                }
            data = self.serial0.read_bytes()
        offset = min(max(int(offset), 0), len(data))
        chunk = data[offset:offset + limit]
        return {
            "session_id": self.id,
            "offset": offset,
            "next_offset": offset + len(chunk),
            "data": chunk.decode("utf-8", errors="replace"),
            "bytes": len(chunk),
        }

    def frame_metrics(
        self, *, analyze: bool = True, force_persist: bool = False
    ) -> dict:
        if not self.spec.has_display:
            raise ServiceError(
                "display_not_available",
                "this device has no framebuffer display",
                409,
            )
        if self.state not in {"running", "booting"}:
            persisted = self.persisted_frame_metrics()
            if persisted:
                return persisted
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        with self._lock:
            ppm = self.dir / f"frame-{uuid.uuid4().hex}.ppm"
            png = ppm.with_suffix(".png")
            try:
                self._qmp_call("screendump", filename=str(ppm))
                width, height, pixels = read_ppm(ppm)
                write_rgb_png(png, width, height, pixels)
                png_bytes = png.read_bytes()
                metrics = {
                    "png": png_bytes,
                    "width": width,
                    "height": height,
                    "png_bytes": len(png_bytes),
                    "source": "live",
                }
                if analyze:
                    nonblack, unique_colors = rgb_metrics(pixels)
                    metrics["nonblack_pixels"] = nonblack
                    metrics["unique_colors"] = unique_colors
                if force_persist or time.monotonic() - self._last_frame_persisted_at >= 1:
                    self._persist_frame(metrics)
                return metrics
            finally:
                ppm.unlink(missing_ok=True)
                png.unlink(missing_ok=True)

    def _persist_frame(self, metrics: dict) -> None:
        self.last_frame_path.write_bytes(metrics["png"])
        self.last_frame_meta_path.write_text(
            json.dumps(
                {
                    key: value
                    for key, value in metrics.items()
                    if key != "png"
                }
                | {"captured_at": iso_now()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        self._last_frame_persisted_at = time.monotonic()

    def persisted_frame_metrics(self) -> dict | None:
        if not self.last_frame_path.is_file():
            return None
        meta = {}
        if self.last_frame_meta_path.is_file():
            try:
                meta = json.loads(self.last_frame_meta_path.read_text())
            except json.JSONDecodeError:
                meta = {}
        png = self.last_frame_path.read_bytes()
        return {
            **meta,
            "png": png,
            "png_bytes": len(png),
            "source": "persisted",
        }

    def frame_png(self) -> tuple[bytes, int, int]:
        metrics = self.frame_metrics(analyze=False)
        return metrics["png"], metrics["width"], metrics["height"]

    def device_state(self) -> dict:
        if not self.spec.state_probes:
            return {
                "session_id": self.id,
                "device_id": self.spec.id,
                "state": self.state,
                "supported": False,
                "available": False,
                "reason": "device_state_not_modelled",
                "components": {},
                "errors": {},
            }
        if self.state not in {"running", "booting"}:
            if self.device_state_path.is_file():
                try:
                    persisted = json.loads(self.device_state_path.read_text())
                    return {
                        **persisted,
                        "state": self.state,
                        "source": "persisted",
                    }
                except json.JSONDecodeError:
                    pass
            return {
                "session_id": self.id,
                "device_id": self.spec.id,
                "state": self.state,
                "supported": True,
                "available": False,
                "reason": "session_not_running",
                "components": {},
                "errors": {},
            }

        components: dict[str, dict[str, Any]] = {}
        errors: dict[str, dict[str, str]] = {}
        for component_id, probe in self.spec.state_probes.items():
            path = probe.get("path")
            properties = probe.get("properties", [])
            if not isinstance(path, str) or not isinstance(properties, list):
                errors[component_id] = {
                    "probe": "invalid runtime_state probe"
                }
                continue
            values: dict[str, Any] = {}
            component_errors: dict[str, str] = {}
            for prop in properties:
                if not isinstance(prop, str):
                    continue
                try:
                    with self._lock:
                        result = self._qmp_call(
                            "qom-get", path=path, property=prop
                        )
                    values[prop] = result.get("return")
                except ServiceError as error:
                    component_errors[prop] = error.message
            if values:
                components[component_id] = {
                    "path": path,
                    "properties": values,
                }
            if component_errors:
                errors[component_id] = component_errors

        response = {
            "session_id": self.id,
            "device_id": self.spec.id,
            "state": self.state,
            "supported": True,
            "available": bool(components),
            "source": "live",
            "captured_at": iso_now(),
            "components": components,
            "errors": errors,
        }
        if components:
            self.device_state_path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n"
            )
        return response

    def inject(self, payload: dict) -> dict:
        if self.state != "running":
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        settle = float(payload.get("settle_seconds", 0.3))
        kind = payload.get("kind")
        action = str(payload.get("action", "tap")).lower()
        if kind == "key":
            key = str(payload.get("key", ""))
            if not key:
                raise ServiceError("invalid_input", "key is required", 400)
            if action == "tap":
                spec = f"key:{key}"
            elif action in {"down", "up"}:
                spec = f"key{action}:{key}"
                if "settle_seconds" not in payload:
                    settle = 0.02
            else:
                raise ServiceError(
                    "invalid_input",
                    "key action must be tap, down or up",
                    400,
                )
        elif kind == "touch":
            spec = f"touch:{int(payload.get('x', 0))},{int(payload.get('y', 0))}"
        elif kind == "longpress":
            spec = (
                f"longpress:{int(payload.get('x', 0))},"
                f"{int(payload.get('y', 0))},{float(payload.get('hold_seconds', 0.5))}"
            )
        elif kind == "drag":
            spec = (
                f"drag:{int(payload.get('x1', 0))},{int(payload.get('y1', 0))},"
                f"{int(payload.get('x2', 0))},{int(payload.get('y2', 0))}"
            )
        else:
            raise ServiceError(
                "invalid_input",
                "kind must be key, touch, longpress or drag",
                400,
            )
        frame_size = self.spec.expected_size or (1, 1)
        with self._lock:
            send_input(self._qmp, spec, frame_size, settle)
            self._record_event("input", spec=spec, action=action)
        return {
            "session_id": self.id,
            "input": spec,
            "action": action,
            "accepted": True,
        }

    def qom_set(self, payload: dict) -> dict:
        path = payload.get("path")
        prop = payload.get("property")
        if not isinstance(path, str) or not isinstance(prop, str):
            raise ServiceError(
                "invalid_qom", "path and property are required strings", 400
            )
        value = payload.get("value")
        with self._lock:
            result = self._qmp_call("qom-set", path=path, property=prop, value=value)
            self._record_event(
                "qom_set", path=path, property=prop, value=value
            )
        return {"session_id": self.id, "qom_set": result}

    def qom_get(self, path: str, prop: str) -> dict:
        with self._lock:
            result = self._qmp_call("qom-get", path=path, property=prop)
        return {
            "session_id": self.id,
            "path": path,
            "property": prop,
            "value": result.get("return"),
        }

    def qom_list(self, path: str = "/machine") -> dict:
        with self._lock:
            result = self._qmp_call("qom-list", path=path)
        fields = sorted(
            result.get("return", []), key=lambda item: item.get("name", "")
        )
        return {"session_id": self.id, "path": path, "properties": fields}

    def qom_snapshot(
        self, path: str = "/machine", depth: int = 2, max_nodes: int = 500
    ) -> dict:
        depth = max(0, min(int(depth), 8))
        max_nodes = max(1, min(int(max_nodes), 5000))
        budget = {"remaining": max_nodes}

        def walk(current_path: str, current_depth: int) -> dict:
            if budget["remaining"] <= 0:
                return {"truncated": True}
            with self._lock:
                fields = self._qmp_call("qom-list", path=current_path).get(
                    "return", []
                )
            output = {}
            for field in sorted(fields, key=lambda item: item.get("name", "")):
                if budget["remaining"] <= 0:
                    output["__truncated__"] = True
                    break
                name = field.get("name")
                field_type = str(field.get("type", ""))
                if not name:
                    continue
                budget["remaining"] -= 1
                if field_type.startswith("child<") and current_depth < depth:
                    output[name] = {
                        "__type__": field_type,
                        "children": walk(f"{current_path}/{name}", current_depth + 1),
                    }
                    continue
                try:
                    with self._lock:
                        value = self._qmp_call(
                            "qom-get", path=current_path, property=name
                        ).get("return")
                    output[name] = {"type": field_type, "value": value}
                except ServiceError as error:
                    output[name] = {
                        "type": field_type,
                        "error": error.message,
                    }
            return output

        snapshot = {
            "path": path,
            "depth": depth,
            "created_at": iso_now(),
            "nodes": walk(path, 0),
        }
        snapshot_id = uuid.uuid4().hex
        snapshot_path = self.dir / f"qom-{snapshot_id}.json"
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        )
        self._record_event("qom_snapshot", snapshot_id=snapshot_id, path=path)
        return {
            "session_id": self.id,
            "snapshot_id": snapshot_id,
            **snapshot,
        }

    def _load_qom_snapshot(self, snapshot_id: str) -> dict:
        if not isinstance(snapshot_id, str) or not all(
            char in "0123456789abcdef" for char in snapshot_id
        ):
            raise ServiceError("unknown_snapshot", "invalid qom snapshot id", 404)
        path = self.dir / f"qom-{snapshot_id}.json"
        if not path.is_file():
            raise ServiceError(
                "unknown_snapshot", f"unknown qom snapshot: {snapshot_id}", 404
            )
        return json.loads(path.read_text())

    def qom_diff(self, before: str, after: str) -> dict:
        before_snapshot = self._load_qom_snapshot(before)
        after_snapshot = self._load_qom_snapshot(after)

        def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
            output = {}
            if isinstance(value, dict):
                for key, child in value.items():
                    child_prefix = f"{prefix}/{key}" if prefix else key
                    output.update(flatten(child, child_prefix))
            else:
                output[prefix] = value
            return output

        left = flatten(before_snapshot["nodes"])
        right = flatten(after_snapshot["nodes"])
        added = {key: right[key] for key in sorted(right.keys() - left.keys())}
        removed = {key: left[key] for key in sorted(left.keys() - right.keys())}
        changed = {
            key: {"before": left[key], "after": right[key]}
            for key in sorted(left.keys() & right.keys())
            if left[key] != right[key]
        }
        self._record_event(
            "qom_diff",
            before=before,
            after=after,
            added=len(added),
            removed=len(removed),
            changed=len(changed),
        )
        return {
            "session_id": self.id,
            "before": before,
            "after": after,
            "added": added,
            "removed": removed,
            "changed": changed,
        }

    def flash_get(self, output_format: str = "sha256") -> tuple[bytes | None, dict]:
        if self.virtual_flash is None or not self.virtual_flash.is_file():
            raise ServiceError("flash_not_available", "session flash is unavailable", 409)
        data = self.virtual_flash.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        metadata = {
            "session_id": self.id,
            "format": output_format,
            "size": len(data),
            "sha256": digest,
        }
        if output_format == "bin":
            return data, metadata
        if output_format != "sha256":
            raise ServiceError(
                "invalid_format", "format must be bin or sha256", 400
            )
        return None, metadata

    def flash_snapshot(self) -> dict:
        _, metadata = self.flash_get("sha256")
        assert self.virtual_flash is not None
        snapshot_id = uuid.uuid4().hex
        target = self.dir / f"flash-{snapshot_id}.bin"
        shutil.copyfile(self.virtual_flash, target)
        self._record_event(
            "flash_snapshot", snapshot_id=snapshot_id, sha256=metadata["sha256"]
        )
        return {
            "session_id": self.id,
            "snapshot_id": snapshot_id,
            "size": metadata["size"],
            "sha256": metadata["sha256"],
            "created_at": iso_now(),
        }

    def _flash_snapshot_path(self, snapshot_id: str) -> Path:
        if not isinstance(snapshot_id, str) or not all(
            char in "0123456789abcdef" for char in snapshot_id
        ):
            raise ServiceError("unknown_snapshot", "invalid flash snapshot id", 404)
        path = self.dir / f"flash-{snapshot_id}.bin"
        if not path.is_file():
            raise ServiceError(
                "unknown_snapshot", f"unknown flash snapshot: {snapshot_id}", 404
            )
        return path

    def flash_diff(self, before: str, after: str) -> dict:
        before_path = self._flash_snapshot_path(before)
        after_path = self._flash_snapshot_path(after)
        left = before_path.read_bytes()
        right = after_path.read_bytes()
        if len(left) != len(right):
            raise ServiceError(
                "flash_size_mismatch",
                f"snapshot sizes differ: {len(left)} != {len(right)}",
                409,
            )
        ranges = []
        changed_bytes = 0
        start = None
        for index, (old, new) in enumerate(zip(left, right)):
            if old != new:
                changed_bytes += 1
                if start is None:
                    start = index
            elif start is not None:
                ranges.append({"offset": start, "length": index - start})
                start = None
        if start is not None:
            ranges.append({"offset": start, "length": len(left) - start})
        self._record_event(
            "flash_diff",
            before=before,
            after=after,
            changed_bytes=changed_bytes,
            ranges=len(ranges),
        )
        return {
            "session_id": self.id,
            "before": before,
            "after": after,
            "size": len(left),
            "changed_bytes": changed_bytes,
            "ranges": ranges[:1000],
            "truncated_ranges": len(ranges) > 1000,
        }

    def evidence_bundle(self, include: set[str] | None = None) -> bytes:
        include = include or {
            "manifest",
            "serial",
            "frames",
            "logs",
            "qom",
        }
        files: dict[str, bytes] = {}
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "session": self.snapshot(),
            "device": self.service.get_device(self.spec.id),
            "timeline": list(self.events),
            "included": sorted(include),
            "files": {},
        }
        if "serial" in include:
            for name, path in (("serial.log", self.serial0), ("serial1.log", self.serial1)):
                if path.is_file():
                    files[name] = path.read_bytes()
        if "logs" in include:
            stdout_name = (
                "network-runner.stdout"
                if self.runtime == "network"
                else "qemu.stdout"
            )
            stderr_name = (
                "network-runner.stderr"
                if self.runtime == "network"
                else "qemu.stderr"
            )
            for name, path in (
                (stdout_name, self.stdout_path),
                (stderr_name, self.stderr_path),
                ("ble-probe.log", self.hci_probe_log),
                ("http-fixture.json", self.http_fixture_log),
                ("c6.log", self.dir / "c6.log"),
            ):
                if path.is_file():
                    files[name] = path.read_bytes()
        if (
            "frames" in include
            and self.spec.has_display
            and self.runtime
            in {"qemu", QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}
        ):
            try:
                frame = self.frame_metrics()
                files["frames/current.png"] = frame["png"]
                manifest["frame"] = {
                    key: value for key, value in frame.items() if key != "png"
                }
            except ServiceError as error:
                manifest["frame"] = {"status": "NOT_AVAILABLE", "reason": error.message}
        if (
            self.network_config.get("profile") in UNIFIED_PROFILES
            and self.speaker_pcm.is_file()
        ):
            pcm = self.speaker_pcm.read_bytes()
            files["audio/speaker.pcm"] = pcm
            manifest["audio"] = {
                "bytes": len(pcm),
                "nonzeros": sum(value != 0 for value in pcm),
                "sha256": hashlib.sha256(pcm).hexdigest(),
            }
        if (
            "qom" in include
            and self.spec.service_kind == "qemu"
            and self.runtime
            in {"qemu", QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}
        ):
            try:
                snapshot = self.qom_snapshot(path="/machine", depth=2, max_nodes=500)
                qom_bytes = (
                    self.dir / f"qom-{snapshot['snapshot_id']}.json"
                ).read_bytes()
                files["qom/snapshot.json"] = qom_bytes
                manifest["qom"] = {
                    "snapshot_id": snapshot["snapshot_id"],
                    "path": snapshot["path"],
                    "depth": snapshot["depth"],
                    "created_at": snapshot["created_at"],
                }
            except ServiceError as error:
                manifest["qom"] = {"status": "NOT_AVAILABLE", "reason": error.message}
        network_dir = getattr(self, "network_dir", None)
        if isinstance(network_dir, Path) and network_dir.is_dir():
            for name, path in (
                ("network/evidence.json", network_dir / "evidence.json"),
                ("network/serial.log", network_dir / "serial.log"),
                ("network/ble-probe.log", network_dir / "ble-probe.log"),
            ):
                if path.is_file():
                    files[name] = path.read_bytes()
            manifest["network"] = self.network_evidence()
        elif self.runtime in {QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}:
            network_payload = self.network_evidence()
            files["network/evidence.json"] = (
                json.dumps(network_payload, ensure_ascii=False, indent=2) + "\n"
            ).encode()
            manifest["network"] = network_payload
        if self.virtual_flash and self.virtual_flash.is_file():
            flash_data = self.virtual_flash.read_bytes()
            manifest["flash"] = {
                "size": len(flash_data),
                "sha256": hashlib.sha256(flash_data).hexdigest(),
            }
            if "flash" in include:
                files["flash/virtual-flash.bin"] = flash_data
        for name, data in files.items():
            manifest["files"][name] = {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        files["manifest.json"] = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        self._record_event("evidence_bundle", included=sorted(include))
        return output.getvalue()

    def reset(self) -> dict:
        with self._lock:
            self._qmp_call("system_reset")
            self._record_event("reset")
        return {"session_id": self.id, "state": self.state, "reset": True}

    def renew(self, ttl_seconds: int) -> dict:
        self.ttl_seconds = ttl_seconds
        self.expires_at = time.time() + ttl_seconds
        self._persist_session()
        return self.snapshot()

    def _terminate_process(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        http_fixture = self._http_fixture
        if http_fixture is not None:
            try:
                http_fixture.close()
            except OSError:
                pass
        self._http_fixture = None
        hci_probe = self._hci_probe
        if hci_probe is not None and hci_probe.poll() is None:
            try:
                os.killpg(hci_probe.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    hci_probe.terminate()
                except ProcessLookupError:
                    pass
            try:
                hci_probe.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(hci_probe.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        hci_probe.kill()
                    except ProcessLookupError:
                        pass
                hci_probe.wait(timeout=5)
        self._hci_probe = None
        if self._qmp is not None:
            try:
                self._qmp.close()
            except OSError:
                pass
            self._qmp = None
        try:
            self.qmp_path.unlink()
        except FileNotFoundError:
            pass

    def stop(self, purge: bool = False) -> dict:
        with self._lock:
            if self.state in {"stopped", "failed"}:
                self._terminate_process()
                result = self.snapshot()
                if purge:
                    shutil.rmtree(self.dir, ignore_errors=True)
                return result
            if self.state == "running" and self.spec.has_display:
                try:
                    self.frame_metrics(force_persist=True)
                except ServiceError:
                    pass
            if self.state == "running" and self.spec.state_probes:
                try:
                    self.device_state()
                except ServiceError:
                    pass
            self.state = "stopping"
            if self._qmp is not None:
                try:
                    self._qmp.cmd("quit")
                except (OSError, RuntimeError):
                    pass
            self._terminate_process()
            self.state = "stopped"
            self.completed_at = iso_now()
            self._record_event("stopped", purge=purge)
            result = self.snapshot()
            self._persist_session()
        if purge:
            shutil.rmtree(self.dir, ignore_errors=True)
        return result


class NetworkDeviceSession(DeviceSession):
    """One-shot network/BLE proof executed through the reusable network lane."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.network_dir = self.dir / "network"
        self.network_dir.mkdir(parents=True, exist_ok=True)
        self.serial0 = self.network_dir / "serial.log"
        self.serial1 = self.network_dir / "serial1.log"
        self.stdout_path = self.dir / "network-runner.stdout"
        self.stderr_path = self.dir / "network-runner.stderr"
        self._persist_session()

    def _provision(self) -> None:
        try:
            self._set_state("flashing")
            self.virtual_flash = self.dir / "virtual-flash.bin"
            shutil.copyfile(self.firmware_path, self.virtual_flash)
            self.flash_info = {
                "transport": "network-direct-image",
                "verified": self.virtual_flash.stat().st_size == self.spec.flash_size,
                "flash_size": self.spec.flash_size,
                "firmware_sha256": self.firmware_sha,
                "session_isolated_copy": True,
            }
            self._record_event("flash_prepared", **self.flash_info)
            self._persist_session()
            self._set_state("booting")
            self._launch()
            self._set_state("running")
        except Exception as error:
            with self._lock:
                self.error = str(error)
                self.state = "failed"
                self.completed_at = self.completed_at or iso_now()
                self._record_event("failed", error=str(error))
                self._persist_session()
            self._terminate_process()

    def _launch(self) -> None:
        assert self.virtual_flash is not None
        chip = self.network_config.get("chip")
        if not chip:
            raise ServiceError(
                "network_not_supported",
                f"{self.spec.id} has no esp-emu network chip",
                409,
            )
        emulator = Path(
            os.environ.get("M5_NETWORK_EMULATOR", str(DEFAULT_NETWORK_EMULATOR))
        )
        if not emulator.is_file():
            raise RuntimeError(f"network emulator is missing: {emulator}")
        profile = self.network_config.get("profile")
        elf_artifact_id = self.network_config.get("elf_artifact_id")
        command = [
            sys.executable,
            str(NETWORK_LANE),
            "--profile",
            str(profile),
            "--chip",
            str(chip),
            "--firmware",
            str(self.virtual_flash),
            "--emulator",
            str(emulator),
            "--out-dir",
            str(self.network_dir),
            "--timeout",
            str(self.network_config.get("timeout_seconds", 60)),
            "--ssid",
            str(self.network_config.get("wifi_ssid", "myssid")),
            "--password",
            str(self.network_config.get("wifi_password", "mypassword")),
            "--wifi-auth",
            str(self.network_config.get("wifi_auth", "wpa2-wpa3")),
            "--psram-size",
            str(self.network_config.get("psram_size", "8M")),
            "--net-mode",
            str(self.network_config.get("net_mode", "user")),
            "--console-mode",
            str(self.network_config.get("console_mode", "uart0")),
            "--ble-name",
            str(self.network_config.get("ble_name", "M5-NETWORK-LANE")),
            "--wifi" if self.network_config.get("wifi") else "--no-wifi",
            "--ble" if self.network_config.get("ble") else "--no-ble",
            "--tcp" if self.network_config.get("tcp") else "--no-tcp",
            "--json",
        ]
        if elf_artifact_id:
            command.extend(
                [
                    "--elf",
                    str(self.service.artifacts.path(str(elf_artifact_id))),
                ]
            )
        for marker in self.network_config.get("expected_markers", []):
            command.extend(["--expect", str(marker)])
        for i2c_device in self.network_config.get("i2c_devices", []):
            command.extend(["--i2c-dev", str(i2c_device)])
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                [
                    str(ROOT / ".work/py"),
                    env.get("PYTHONPATH", ""),
                ],
            )
        )
        stdout = self.stdout_path.open("wb")
        stderr = self.stderr_path.open("wb")
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        finally:
            stdout.close()
            stderr.close()
        self.pid = self._proc.pid
        self._persist_session()
        self._record_event(
            "network_started",
            profile=profile,
            chip=chip,
            pid=self.pid,
        )
        threading.Thread(
            target=self._monitor_network_process,
            name=f"m5-network-monitor-{self.id}",
            daemon=True,
        ).start()

    def _network_evidence_path(self) -> Path:
        return self.network_dir / "evidence.json"

    def network_evidence(self) -> dict:
        evidence_path = self._network_evidence_path()
        if evidence_path.is_file():
            try:
                payload = json.loads(evidence_path.read_text())
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass
        return {
            "schema_version": 1,
            "kind": "m5stack-network-lane-proof",
            "scope": "simulation-only-not-hardware-validation",
            "status": self.network_result.get("status", "RUNNING")
            if self.network_result
            else "RUNNING",
            "session_id": self.id,
            "profile": self.network_config.get("profile"),
        }

    def _monitor_network_process(self) -> None:
        proc = self._proc
        if proc is None:
            return
        returncode = proc.wait()
        self._handle_process_exit(returncode)

    def _handle_process_exit(self, returncode: int | None) -> None:
        with self._lock:
            if self.state not in ACTIVE_STATES:
                return
            evidence_path = self._network_evidence_path()
            evidence: dict | None = None
            if evidence_path.is_file():
                try:
                    candidate = json.loads(evidence_path.read_text())
                    if isinstance(candidate, dict):
                        evidence = candidate
                except json.JSONDecodeError:
                    evidence = None
            if evidence is None:
                super()._handle_process_exit(returncode)
                return
            self.network_result = evidence
            status = str(evidence.get("status") or "FAIL")
            self.state = "stopped" if status in {"PASS", "PARTIAL"} else "failed"
            self.error = (
                None
                if status in {"PASS", "PARTIAL"}
                else f"network lane completed with status {status}"
            )
            self.completed_at = self.completed_at or iso_now()
            self._record_event(
                "network_completed",
                status=status,
                returncode=returncode,
                evidence=self._network_evidence_path().name,
            )
            self._persist_session()

    def _terminate_process(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
            except (OSError, ProcessLookupError):
                proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except (OSError, ProcessLookupError):
                    proc.kill()
                proc.wait(timeout=5)

    def _unavailable(self, feature: str):
        raise ServiceError(
            "runtime_feature_not_available",
            f"{feature} is not available in a network-only session",
            409,
        )

    def frame_metrics(self, *, analyze: bool = True, force_persist: bool = False):
        self._unavailable("framebuffer capture")

    def frame_png(self):
        self._unavailable("framebuffer capture")

    def device_state(self):
        self._unavailable("board device state")

    def inject(self, payload: dict):
        self._unavailable("input injection")

    def qom_set(self, payload: dict):
        self._unavailable("QOM")

    def qom_get(self, path: str, prop: str):
        self._unavailable("QOM")

    def qom_list(self, path: str = "/machine"):
        self._unavailable("QOM")

    def qom_snapshot(
        self, path: str = "/machine", depth: int = 2, max_nodes: int = 500
    ):
        self._unavailable("QOM")

    def qom_diff(self, before: str, after: str):
        self._unavailable("QOM")

    def reset(self):
        self._unavailable("network session reset")


class Tab5DeviceSession(DeviceSession):
    """Tab5 esp-emu session with serial, GDB framebuffer and touch support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._c6_proc: subprocess.Popen | None = None
        self._gdb_port: int | None = None
        self._hosted_socket = Path("/tmp") / f"m5-service-tab5-{self.id}.sock"

    def _provision(self) -> None:
        try:
            self._set_state("flashing")
            prepared = self.service.prepare_flash(
                self.spec, self.firmware_path, self.firmware_sha
            )
            self.virtual_flash = self.dir / "virtual-flash.bin"
            shutil.copyfile(prepared["path"], self.virtual_flash)
            self.flash_info = {
                **prepared["info"],
                "session_isolated_copy": True,
            }
            self._record_event("flash_prepared", **self.flash_info)
            self._persist_session()
            self._set_state("booting")
            self._launch_tab5()
            if self.ready_conditions:
                self.wait_ready(
                    {
                        "timeout_seconds": self.ready_timeout,
                        **self.ready_conditions,
                    }
                )
            elif self.ready_marker:
                self.wait_for_marker(self.ready_marker, self.ready_timeout)
            self._set_state("running")
        except Exception as error:
            with self._lock:
                self.error = str(error)
                self.state = "failed"
                self.completed_at = self.completed_at or iso_now()
                self._record_event("failed", error=str(error))
                self._persist_session()
            self._terminate_tab5()

    def _launch_tab5(self) -> None:
        assert self.virtual_flash is not None
        assert self.spec.emulator is not None
        assert self.spec.elf is not None
        assert self.spec.rom is not None
        assert self.spec.efuse is not None
        assert self.spec.c6_firmware is not None
        try:
            self._hosted_socket.unlink()
        except FileNotFoundError:
            pass
        launch_env = os.environ.copy()
        launch_env.update(self.spec.env)
        launch_env.update(self.runtime_env)
        c6_stdout = (self.dir / "c6.log").open("wb")
        self._c6_proc = subprocess.Popen(
            [
                str(self.spec.emulator),
                "--chip", "esp32c6",
                "--firmware", str(self.spec.c6_firmware),
                "--hosted", f"bridge:slave:{self._hosted_socket}",
            ],
            cwd=ROOT,
            env=launch_env,
            stdout=c6_stdout,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for_fs_path(self._hosted_socket, self._c6_proc, 25)
        finally:
            c6_stdout.close()
        self._gdb_port = free_tcp_port()
        p4_stdout = self.serial0.open("wb")
        p4_stderr = self.stderr_path.open("wb")
        command = [
            str(self.spec.emulator),
            "--chip", "esp32p4",
            "--firmware", str(self.virtual_flash),
            "--elf", str(self.spec.elf),
            "--rom", str(self.spec.rom),
            "--efuse", str(self.spec.efuse),
            "--hosted", f"bridge:host:{self._hosted_socket}",
            "--hosted-reset-gpio", "15",
            "--hosted-reset-active-high",
            "--psram-size", "32M",
            "--console", "uart0",
            "--gdb", str(self._gdb_port),
            "--timeout", f"{int(self.ttl_seconds + 120)}s",
        ]
        try:
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=launch_env,
                stdout=p4_stdout,
                stderr=p4_stderr,
            )
        finally:
            p4_stdout.close()
            p4_stderr.close()
        self.pid = self._proc.pid
        self._persist_session()
        wait_for_tcp_port(self._gdb_port, self._proc, 25)

    def _terminate_tab5(self) -> None:
        for proc in (self._proc, self._c6_proc):
            if proc is not None and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
        for proc in (self._proc, self._c6_proc):
            if proc is None:
                continue
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self._proc = None
        self._c6_proc = None
        try:
            self._hosted_socket.unlink()
        except FileNotFoundError:
            pass

    def frame_metrics(
        self, *, analyze: bool = True, force_persist: bool = False
    ) -> dict:
        if self.state not in {"running", "booting"} or self._gdb_port is None:
            persisted = self.persisted_frame_metrics()
            if persisted:
                return persisted
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        if self.firmware_source != "reference":
            raise ServiceError(
                "screenshot_requires_matching_elf",
                "Tab5 screenshot capture requires the reference ELF; "
                "uploaded firmware has no matching symbol file yet",
                409,
            )
        assert self.spec.elf is not None
        name = f"api-frame-{uuid.uuid4().hex}"
        raw_width, raw_height, raw565, _ = capture_framebuffer(
            self.spec.elf, self._gdb_port, self.dir, name
        )
        width, height, oriented = orient_rgb565(
            raw565, raw_width, raw_height, 1
        )
        pixels = rgb565_to_rgb(oriented)
        png = self.dir / f"{name}.png"
        write_tab5_png(png, width, height, pixels)
        try:
            png_bytes = png.read_bytes()
            metrics = {
                "png": png_bytes,
                "width": width,
                "height": height,
                "png_bytes": len(png_bytes),
                "source": "live",
            }
            if analyze:
                nonblack, unique_colors = rgb_metrics(pixels)
                metrics["nonblack_pixels"] = nonblack
                metrics["unique_colors"] = unique_colors
            if force_persist or time.monotonic() - self._last_frame_persisted_at >= 1:
                self._persist_frame(metrics)
            return metrics
        finally:
            png.unlink(missing_ok=True)
            (self.dir / f"{name}.rgb565").unlink(missing_ok=True)

    def frame_png(self) -> tuple[bytes, int, int]:
        metrics = self.frame_metrics(analyze=False)
        return metrics["png"], metrics["width"], metrics["height"]

    def inject(self, payload: dict) -> dict:
        if self.state != "running" or self._gdb_port is None:
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        if self.firmware_source != "reference":
            raise ServiceError(
                "input_requires_matching_elf",
                "Tab5 touch injection currently requires the reference ELF",
                409,
            )
        kind = payload.get("kind")
        if kind not in {"touch", "longpress"}:
            raise ServiceError(
                "unsupported_input",
                "Tab5 service currently supports touch and longpress only",
                409,
            )
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        hold = (
            float(payload.get("hold_seconds", 0.5))
            if kind == "longpress"
            else float(payload.get("settle_seconds", 0.15))
        )
        raw_x, raw_y = logical_to_raw_touch(x, y, 720, 1280, 1)
        assert self.spec.elf is not None
        inject_touch(
            self.spec.elf,
            self._gdb_port,
            self.dir,
            f"api-touch-down-{uuid.uuid4().hex}",
            down=True,
            x=raw_x,
            y=raw_y,
        )
        time.sleep(max(0.05, hold))
        inject_touch(
            self.spec.elf,
            self._gdb_port,
            self.dir,
            f"api-touch-up-{uuid.uuid4().hex}",
            down=False,
            x=raw_x,
            y=raw_y,
        )
        return {
            "session_id": self.id,
            "input": kind,
            "logical": [x, y],
            "raw": [raw_x, raw_y],
            "accepted": True,
        }

    def qom_set(self, payload: dict) -> dict:
        raise ServiceError(
            "qom_not_supported",
            "Tab5 esp-emu sessions do not expose QMP QOM",
            409,
        )

    def qom_get(self, path: str, prop: str) -> dict:
        raise ServiceError(
            "qom_not_supported",
            "Tab5 esp-emu sessions do not expose QMP QOM",
            409,
        )

    def reset(self) -> dict:
        if self.state != "running":
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        self._set_state("booting")
        self.serial0.write_bytes(b"")
        self._terminate_tab5()
        self._launch_tab5()
        self._set_state("running")
        self._record_event("reset")
        return {"session_id": self.id, "state": self.state, "reset": True}

    def stop(self, purge: bool = False) -> dict:
        with self._lock:
            if self.state in {"stopped", "failed"}:
                result = self.snapshot()
                if purge:
                    shutil.rmtree(self.dir, ignore_errors=True)
                return result
            if self.state == "running" and self.spec.has_display:
                try:
                    self.frame_metrics(force_persist=True)
                except ServiceError:
                    pass
            self.state = "stopping"
            self._terminate_tab5()
            self.state = "stopped"
            self.completed_at = iso_now()
            self._record_event("stopped", purge=purge)
            result = self.snapshot()
            self._persist_session()
        if purge:
            shutil.rmtree(self.dir, ignore_errors=True)
        return result


class DeviceService:
    def __init__(
        self,
        *,
        state_dir: Path = DEFAULT_STATE_DIR,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_per_device: int = DEFAULT_MAX_PER_DEVICE,
        default_ttl: int = 1800,
        api_token: str | None = None,
        flash_preparer=None,
    ):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.specs = load_device_specs()
        self.raw_matrix = json.loads(MATRIX.read_text())
        self.artifacts = ArtifactStore(self.state_dir / "artifacts")
        self.firmware = FirmwareStore(
            self.state_dir / "firmware", self.artifacts, self.specs
        )
        self.max_sessions = max(1, int(max_sessions))
        self.max_per_device = max(1, int(max_per_device))
        self.default_ttl = max(30, int(default_ttl))
        self.api_token = api_token
        self.flash_preparer = flash_preparer or default_flash_preparer
        self._sessions: dict[str, DeviceSession] = {}
        self._lock = threading.RLock()
        self._flash_lock = threading.Lock()
        self._reference_cache: dict[str, dict] = {}
        self._restore_history()
        self._stop = threading.Event()
        self._janitor = threading.Thread(
            target=self._janitor_loop,
            name="m5-session-janitor",
            daemon=True,
        )
        self._janitor.start()

    def _restore_history(self) -> None:
        """Restore retained metadata without reviving old QEMU processes."""

        sessions_root = self.state_dir / "sessions"
        if not sessions_root.is_dir():
            return
        for record_path in sorted(
            sessions_root.glob("*/session.json"),
            key=lambda path: path.name,
        ):
            try:
                record = json.loads(record_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            session_id = record.get("session_id")
            device_id = record.get("device_id")
            if (
                not isinstance(session_id, str)
                or session_id != record_path.parent.name
                or not isinstance(device_id, str)
            ):
                continue
            spec = self.specs.get(device_id)
            if spec is None or session_id in self._sessions:
                continue
            persisted_state = str(record.get("state") or "failed")
            interrupted = persisted_state in ACTIVE_STATES or persisted_state == "stopping"
            restored_state = "failed" if interrupted else persisted_state
            if restored_state not in {"stopped", "failed"}:
                restored_state = "failed"
                interrupted = True
            events: list[dict] = []
            events_path = record_path.parent / "events.json"
            if events_path.is_file():
                try:
                    loaded_events = json.loads(events_path.read_text())
                    if isinstance(loaded_events, list):
                        events = [
                            event for event in loaded_events if isinstance(event, dict)
                        ]
                except (OSError, json.JSONDecodeError):
                    events = []
            try:
                expires_at = datetime.fromisoformat(
                    str(record.get("expires_at")).replace("Z", "+00:00")
                ).timestamp()
            except (TypeError, ValueError):
                expires_at = time.time()
            completed_at = record.get("completed_at")
            if interrupted and not completed_at:
                completed_at = iso_now()
            error = record.get("error")
            if interrupted:
                error = (
                    "service restarted before the session completed; "
                    f"previous state was {persisted_state}"
                )
            source_artifacts = record.get("source_artifacts")
            if not isinstance(source_artifacts, list):
                source_artifacts = []
            try:
                ttl_seconds = max(30, int(record.get("ttl_seconds") or 30))
                ready_timeout = float(
                    record.get("ready_timeout_seconds") or 30
                )
            except (TypeError, ValueError):
                continue
            runtime = (
                record.get("runtime")
                if record.get("runtime") in {
                    "qemu",
                    "network",
                    QEMU_WIFI_RUNTIME,
                    QEMU_BLE_RUNTIME,
                }
                else "qemu"
            )
            network_config = (
                record.get("network")
                if isinstance(record.get("network"), dict)
                else None
            )
            network_result = (
                record.get("network_result")
                if isinstance(record.get("network_result"), dict)
                else None
            )
            if runtime == "network":
                session_class = NetworkDeviceSession
            elif spec.service_kind == "tab5":
                session_class = Tab5DeviceSession
            else:
                session_class = DeviceSession
            session = session_class(
                self,
                session_id=session_id,
                spec=spec,
                firmware_id=str(record.get("firmware_id") or ""),
                firmware_path=record_path.parent / "firmware.bin",
                firmware_sha=str(record.get("firmware_sha256") or ""),
                firmware_source=str(record.get("firmware_source") or "unknown"),
                source_artifacts=[
                    artifact
                    for artifact in source_artifacts
                    if isinstance(artifact, str)
                ],
                ttl_seconds=ttl_seconds,
                ready_marker=(
                    record.get("ready_marker")
                    if isinstance(record.get("ready_marker"), str)
                    else None
                ),
                ready_timeout=ready_timeout,
                ready_conditions=(
                    record.get("ready_conditions")
                    if isinstance(record.get("ready_conditions"), dict)
                    else None
                ),
                runtime_env={
                    key: value
                    for key, value in (
                        record.get("runtime_env")
                        if isinstance(record.get("runtime_env"), dict)
                        else {}
                    ).items()
                    if key in ALLOWED_RUNTIME_ENV and isinstance(value, str)
                },
                runtime=runtime,
                network_config=network_config,
                network_result=network_result,
                events=events,
                created_at=(
                    record.get("created_at")
                    if isinstance(record.get("created_at"), str)
                    else None
                ),
                completed_at=(
                    completed_at if isinstance(completed_at, str) else None
                ),
                expires_at=expires_at,
                initial_state=restored_state,
                error=error if isinstance(error, str) else None,
                flash_info=(
                    record.get("flash")
                    if isinstance(record.get("flash"), dict)
                    else None
                ),
                restored=True,
                interrupted=interrupted,
            )
            virtual_flash = record_path.parent / "virtual-flash.bin"
            session.virtual_flash = virtual_flash if virtual_flash.is_file() else None
            if interrupted:
                session._record_event(
                    "interrupted",
                    previous_state=persisted_state,
                    reason="service restarted before session completion",
                )
                session._persist_session()
            self._sessions[session.id] = session

    def raw_device(self, device_id: str) -> dict:
        for row in self.raw_matrix["devices"]:
            if row["id"] == device_id:
                return row
        raise KeyError(device_id)

    def _public_device(self, spec: DeviceSpec) -> dict:
        reference_available = spec.reference_available
        backend_ready = spec.backend_ready
        return {
            "device_id": spec.id,
            "name": spec.name,
            "group": spec.group,
            "soc": spec.soc,
            "sku": spec.sku,
            "device_codes": spec.device_codes,
            "supported": spec.supported,
            "creatable": spec.supported and backend_ready,
            "backend_ready": backend_ready,
            "reference_available": reference_available,
            "backend": spec.backend,
            "machine": spec.machine,
            "flash_size": spec.flash_size,
            "display": spec.display,
            "peripheral_status": spec.peripheral_status,
            "warnings": spec.warnings,
            "firmware_families": ["uiflow2", "generic-flash"],
            "coverage": {
                "peripheral_status": spec.peripheral_status,
                "complete": spec.peripheral_status == "simulated",
            },
            "features": {
                "flash": spec.supported,
                "serial": spec.supported,
                "screenshot": spec.supported and spec.has_display,
                "input": spec.supported,
                "qom": spec.supported and spec.service_kind == "qemu",
                "device_state": bool(spec.state_probes),
                "network": (
                    spec.network_status == "validated"
                    and bool(spec.network_profiles)
                ),
            },
            "network_profiles": list(spec.network_profiles),
            "network_console": spec.network_console,
            "network_status": spec.network_status,
            "reason": spec.reason,
        }

    def list_devices(self, include_unsupported: bool = True) -> dict:
        devices = [
            self._public_device(spec)
            for spec in sorted(self.specs.values(), key=lambda row: row.id)
            if include_unsupported or spec.supported
        ]
        return {
            "service": "m5stack-device-service",
            "api_version": "v1",
            "network_enabled": any(
                spec.network_status == "validated" and spec.network_profiles
                for spec in self.specs.values()
            ),
            "tab5_enabled": False,
            "devices": devices,
        }

    def get_device(self, device_id: str) -> dict:
        spec = self.specs.get(device_id)
        if spec is None:
            raise ServiceError("unknown_device", f"unknown device: {device_id}", 404)
        return self._public_device(spec)

    def upload_artifact(
        self, data: bytes, *, name: str = "", content_type: str = ""
    ) -> dict:
        return self.artifacts.create(
            data, name=name, content_type=content_type or "application/octet-stream"
        )

    def create_firmware(self, payload: dict) -> dict:
        return self.firmware.create(payload)

    def reference_info(self, spec: DeviceSpec) -> dict:
        with self._lock:
            if spec.id in self._reference_cache:
                return self._reference_cache[spec.id]
            if not spec.reference_path or not spec.reference_path.is_file():
                raise ServiceError(
                    "reference_firmware_missing",
                    f"reference firmware is not cached for {spec.id}",
                    409,
                )
            reference_path = spec.reference_path
            if spec.service_kind == "tab5":
                reference_path = self._tab5_reference_image(spec)
            data = reference_path.read_bytes()
            if len(data) > spec.flash_size:
                raise ServiceError(
                    "reference_firmware_too_large",
                    "reference firmware exceeds device flash size",
                    409,
                )
            record = {
                "firmware_id": hashlib.sha256(data).hexdigest(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "path": reference_path,
            }
            self._reference_cache[spec.id] = record
            return record

    def _tab5_reference_image(self, spec: DeviceSpec) -> Path:
        assert spec.reference_path is not None
        target = self.state_dir / "references" / "tab5-uiflow2-service.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        if (
            not target.is_file()
            or target.stat().st_mtime < spec.reference_path.stat().st_mtime
        ):
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tests/uiflow2/tab5_ui_test/make_image.py"),
                    "--base",
                    str(spec.reference_path),
                    "--out",
                    str(target),
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        return target

    def prepare_flash(
        self,
        spec: DeviceSpec,
        image: Path,
        firmware_sha: str,
        *,
        runtime: str = "qemu",
    ) -> dict:
        if runtime in {QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME}:
            data = image.read_bytes()
            info = validate_complete_flash_image(
                data,
                flash_size=spec.flash_size,
                firmware_sha=firmware_sha,
                expected_chip_id_value=expected_chip_id(spec.soc),
            )
            return {
                "path": image,
                "info": _public_flash_info(info),
            }
        cache_dir = self.state_dir / "flash-cache" / spec.id
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{firmware_sha}.bin"
        work_dir = cache_dir / f".work-{uuid.uuid4().hex}"
        with self._flash_lock:
            if cache_path.is_file() and cache_path.stat().st_size == spec.flash_size:
                return {
                    "path": cache_path,
                        "info": _public_flash_info({
                        "transport": "cache",
                        "verified": True,
                        "flash_size": spec.flash_size,
                        "firmware_sha256": firmware_sha,
                        }),
                }
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                if os.environ.get("M5_SERVICE_FLASH_MODE", "esptool") == "host-image":
                    info = {
                        "transport": "host-image",
                        "verified": True,
                        "flash_size": spec.flash_size,
                        "firmware_sha256": firmware_sha,
                    }
                    work_dir.joinpath("virtual-flash.bin").write_bytes(
                        _padded(image.read_bytes(), spec.flash_size)
                    )
                else:
                    info = self.flash_preparer(spec, image, firmware_sha, work_dir)
                produced = Path(info["virtual_flash"])
                if produced.stat().st_size != spec.flash_size:
                    raise ServiceError(
                        "flash_size_mismatch",
                        f"prepared flash size {produced.stat().st_size} "
                        f"!= {spec.flash_size}",
                        500,
                    )
                shutil.copyfile(produced, cache_path)
                return {"path": cache_path, "info": _public_flash_info(info)}
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

    def create_session(self, payload: dict) -> dict:
        device_id = payload.get("device_id")
        if not isinstance(device_id, str):
            raise ServiceError("invalid_request", "device_id is required", 400)
        spec = self.specs.get(device_id)
        if spec is None:
            raise ServiceError("unknown_device", f"unknown device: {device_id}", 404)
        if not spec.supported:
            raise ServiceError(
                "unsupported_device", spec.reason or "device is not enabled", 409
            )
        if not spec.backend_ready:
            raise ServiceError(
                "backend_not_ready",
                f"runtime files are missing for {device_id}",
                503,
            )
        firmware_id = payload.get("firmware_id")
        if firmware_id:
            firmware = self.firmware.get(str(firmware_id))
            if firmware["device_id"] != device_id:
                raise ServiceError(
                    "firmware_device_mismatch",
                    f"firmware belongs to {firmware['device_id']}",
                    409,
                )
            firmware_path = self.firmware.path(str(firmware_id))
            firmware_sha = firmware["sha256"]
            source = "uploaded"
            firmware_source = firmware.get("source", {})
            source_artifacts = (
                [firmware_source["artifact_id"]]
                if firmware_source.get("kind") == "merged"
                and firmware_source.get("artifact_id")
                else [
                    segment["artifact_id"]
                    for segment in firmware_source.get("segments", [])
                    if segment.get("artifact_id")
                ]
            )
        else:
            reference = self.reference_info(spec)
            firmware_id = reference["firmware_id"]
            firmware_path = reference["path"]
            firmware_sha = reference["sha256"]
            source = "reference"
            source_artifacts = []

        runtime = payload.get("runtime", "qemu")
        if runtime not in {
            "qemu",
            "network",
            QEMU_WIFI_RUNTIME,
            QEMU_BLE_RUNTIME,
        }:
            raise ServiceError(
                "unsupported_runtime",
                "runtime must be qemu, network, qemu-wifi or qemu-ble",
                400,
            )
        network_config = None
        if runtime == "network":
            network_config = parse_network_execution(
                spec,
                payload.get("network"),
            )
            elf_artifact_id = network_config.get("elf_artifact_id")
            if elf_artifact_id:
                self.artifacts.get(str(elf_artifact_id))
        elif runtime == QEMU_WIFI_RUNTIME:
            network_config = parse_qemu_wifi_execution(
                spec,
                payload.get("network"),
            )
        elif runtime == QEMU_BLE_RUNTIME:
            network_config = parse_qemu_ble_execution(
                spec,
                payload.get("network"),
            )
            if (
                network_config.get("profile") == CORE2_HCI_GATT_PROFILE
                and payload.get("ready_marker") is None
            ):
                payload = dict(payload)
                payload["ready_marker"] = "CORE2_HCI_BLE_ACK_SENT"
            elif (
                network_config.get("profile") in UNIFIED_READY_MARKERS
                and payload.get("ready_marker") is None
            ):
                payload = dict(payload)
                payload["ready_marker"] = UNIFIED_READY_MARKERS[
                    network_config["profile"]
                ]

        with self._lock:
            active = [
                session
                for session in self._sessions.values()
                if session.state in ACTIVE_STATES
            ]
            if len(active) >= self.max_sessions:
                raise ServiceError(
                    "capacity_exhausted",
                    f"maximum active sessions is {self.max_sessions}",
                    429,
                )
            same_device = [session for session in active if session.spec.id == device_id]
            if len(same_device) >= self.max_per_device:
                raise ServiceError(
                    "device_capacity_exhausted",
                    f"maximum active sessions for {device_id} is {self.max_per_device}",
                    429,
                )
            ttl = int(payload.get("ttl_seconds", self.default_ttl))
            if ttl < 30:
                raise ServiceError("invalid_ttl", "ttl_seconds must be >= 30", 400)
            ready_marker = payload.get("ready_marker")
            if ready_marker is not None and not isinstance(ready_marker, str):
                raise ServiceError("invalid_request", "ready_marker must be a string", 400)
            ready_conditions = payload.get("ready")
            if ready_conditions is not None and not isinstance(
                ready_conditions, dict
            ):
                raise ServiceError("invalid_ready", "ready must be an object", 400)
            runtime_env = payload.get("runtime_env", {})
            if runtime_env is None:
                runtime_env = {}
            if not isinstance(runtime_env, dict):
                raise ServiceError(
                    "invalid_runtime_env", "runtime_env must be an object", 400
                )
            invalid_env = [
                key
                for key, value in runtime_env.items()
                if key not in ALLOWED_RUNTIME_ENV
                or not isinstance(value, str)
                or "\x00" in value
            ]
            if invalid_env:
                raise ServiceError(
                    "invalid_runtime_env",
                    "unsupported runtime_env keys or values: "
                    + ", ".join(str(key) for key in invalid_env),
                    400,
                )
            ready_timeout = float(payload.get("ready_timeout_seconds", 30))
            if runtime == "network":
                session_class = NetworkDeviceSession
            elif spec.service_kind == "tab5":
                session_class = Tab5DeviceSession
            else:
                session_class = DeviceSession
            session = session_class(
                self,
                session_id=uuid.uuid4().hex,
                spec=spec,
                firmware_id=firmware_id,
                firmware_path=firmware_path,
                firmware_sha=firmware_sha,
                firmware_source=source,
                source_artifacts=source_artifacts,
                ttl_seconds=ttl,
                ready_marker=ready_marker,
                ready_timeout=ready_timeout,
                ready_conditions=ready_conditions,
                runtime_env=runtime_env,
                runtime=runtime,
                network_config=network_config,
            )
            self._sessions[session.id] = session
        session.start()
        return session.snapshot()

    def get_session(self, session_id: str) -> DeviceSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise ServiceError("unknown_session", f"unknown session: {session_id}", 404)
        return session

    def list_sessions(self, include_stopped: bool = True) -> dict:
        with self._lock:
            sessions = [
                session
                for session in self._sessions.values()
                if include_stopped or session.state in ACTIVE_STATES
            ]
        return {"sessions": [session.snapshot() for session in sessions]}

    def delete_session(self, session_id: str, purge: bool = False) -> dict:
        session = self.get_session(session_id)
        result = session.stop(purge=purge)
        if purge:
            with self._lock:
                self._sessions.pop(session_id, None)
        return result

    def clear_stopped(self, purge: bool = True) -> dict:
        with self._lock:
            sessions = [
                session
                for session in self._sessions.values()
                if session.state in {"stopped", "failed"}
            ]
            known_ids = set(self._sessions)
        for session in sessions:
            session.stop(purge=purge)
            if purge:
                with self._lock:
                    self._sessions.pop(session.id, None)
        orphaned = []
        if purge:
            sessions_root = self.state_dir / "sessions"
            if sessions_root.is_dir():
                orphaned = [
                    path
                    for path in sessions_root.iterdir()
                    if path.is_dir() and path.name not in known_ids
                ]
                for path in orphaned:
                    shutil.rmtree(path, ignore_errors=True)
        return {
            "cleared": len(sessions),
            "orphaned_cleared": len(orphaned),
            "purged": purge,
        }

    def session_events(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        return {
            "session_id": session.id,
            "events": list(session.events),
        }

    def capacity(self) -> dict:
        with self._lock:
            active = [
                session for session in self._sessions.values()
                if session.state in ACTIVE_STATES
            ]
            by_device: dict[str, int] = {}
            for session in active:
                by_device[session.spec.id] = by_device.get(session.spec.id, 0) + 1
        return {
            "max_sessions": self.max_sessions,
            "active_sessions": len(active),
            "available_sessions": max(0, self.max_sessions - len(active)),
            "max_per_device": self.max_per_device,
            "by_device": by_device,
            "modes": {
                "network": (
                    "enabled-separate-lane"
                    if any(
                        spec.network_status == "validated"
                        and spec.network_profiles
                        for spec in self.specs.values()
                    )
                    else "disabled"
                ),
                "qemu-wifi": (
                    "enabled-core2-experimental"
                    if CORE2_WIFI_PROFILE
                    in self.specs["core2"].network_profiles
                    else "disabled"
                ),
                "qemu-ble": (
                    "enabled-core2-experimental"
                    if CORE2_BLE_PROFILE
                    in self.specs["core2"].network_profiles
                    else "disabled"
                ),
                "qemu-unified": (
                    "enabled-sticks3-cores3-cardputer-adv-wifi-ble"
                    if any(
                        profile in self.specs[device_id].network_profiles
                        for device_id, profile in (
                            ("sticks3", STICKS3_UNIFIED_PROFILE),
                            ("cores3", CORES3_UNIFIED_PROFILE),
                            (
                                "cardputer-adv",
                                CARDPUTER_ADV_UNIFIED_PROFILE,
                            ),
                        )
                    )
                    else "disabled"
                ),
                "tab5": "enabled-partial",
                "flash": "prepared-cache + exact artifact",
            },
        }

    def _janitor_loop(self) -> None:
        while not self._stop.wait(2):
            now = time.time()
            expired = []
            with self._lock:
                for session in self._sessions.values():
                    if (
                        session.state in ACTIVE_STATES
                        and session._proc is not None
                        and session._proc.poll() is not None
                    ):
                        session._handle_process_exit(session._proc.returncode)
                    if session.state in ACTIVE_STATES and session.expires_at <= now:
                        expired.append(session)
            for session in expired:
                try:
                    session.stop()
                except Exception:
                    pass

    def close_all(self) -> None:
        self._stop.set()
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            try:
                session.stop()
            except Exception:
                pass


def _padded(data: bytes, size: int) -> bytes:
    if len(data) > size:
        raise ServiceError(
            "firmware_too_large",
            f"firmware is {len(data)} bytes; flash is {size}",
            413,
        )
    return data + b"\xff" * (size - len(data))


def validate_complete_flash_image(
    data: bytes,
    *,
    flash_size: int,
    firmware_sha: str,
    expected_chip_id_value: int | None,
) -> dict:
    """Validate a complete flash image without rewriting it.

    The qemu radio lanes accept images that are already merged for direct use
    as an MTD drive. They must not invoke esptool or silently pad a partial
    image: doing either would make the resulting boot behavior differ from the
    exact bytes the caller submitted.
    """

    if len(data) != flash_size:
        raise ServiceError(
            "complete_flash_image_required",
            f"qemu radio requires a complete {flash_size}-byte flash image; "
            f"received {len(data)} bytes",
            400,
        )
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != firmware_sha:
        raise ServiceError(
            "firmware_sha256_mismatch",
            "firmware bytes do not match the expected SHA256",
            409,
        )

    bootloader_offset = next(
        (
            offset
            for offset in (0, 0x1000)
            if offset + 24 <= len(data) and data[offset] == 0xE9
        ),
        None,
    )
    if bootloader_offset is None:
        raise ServiceError(
            "direct_flash_layout_invalid",
            "no ESP bootloader image found at flash offset 0 or 0x1000",
            422,
        )
    bootloader = analyze_esp_image(data, bootloader_offset)
    if not bootloader["valid"]:
        raise ServiceError(
            "direct_flash_layout_invalid",
            "bootloader image is invalid: "
            + "; ".join(bootloader.get("errors", [])),
            422,
        )
    if (
        expected_chip_id_value is not None
        and bootloader.get("chip_id") != expected_chip_id_value
    ):
        raise ServiceError(
            "firmware_chip_mismatch",
            f"bootloader chip {bootloader.get('chip')} does not match "
            f"expected chip id 0x{expected_chip_id_value:04x}",
            422,
        )

    partition_table = parse_partition_table(data)
    if not partition_table["valid"]:
        raise ServiceError(
            "direct_flash_layout_invalid",
            "partition table is invalid: "
            + "; ".join(partition_table.get("errors", [])),
            422,
        )
    app_images = []
    for partition in partition_table["partitions"]:
        if partition["type"] != 0:
            continue
        image = analyze_esp_image(data, partition["offset"])
        if not image["valid"]:
            raise ServiceError(
                "direct_flash_layout_invalid",
                f"app partition {partition['label']!r} is invalid: "
                + "; ".join(image.get("errors", [])),
                422,
            )
        if (
            expected_chip_id_value is not None
            and image.get("chip_id") != expected_chip_id_value
        ):
            raise ServiceError(
                "firmware_chip_mismatch",
                f"app partition {partition['label']!r} chip "
                f"{image.get('chip')} does not match expected chip id "
                f"0x{expected_chip_id_value:04x}",
                422,
            )
        app_images.append(
            {
                "label": partition["label"],
                "offset": partition["offset"],
                "size": partition["size"],
                "chip": image.get("chip"),
            }
        )
    if not app_images:
        raise ServiceError(
            "direct_flash_layout_invalid",
            "partition table contains no valid app image",
            422,
        )
    return {
        "transport": "direct-complete-flash-image",
        "verified": True,
        "flash_size": flash_size,
        "firmware_sha256": actual_sha,
        "bootloader_offset": bootloader_offset,
        "bootloader_chip": bootloader.get("chip"),
        "app_partitions": app_images,
    }


def _public_flash_info(info: dict) -> dict:
    return {
        key: value
        for key, value in info.items()
        if key not in {"image", "virtual_flash", "qemu", "rom_dir"}
    }
