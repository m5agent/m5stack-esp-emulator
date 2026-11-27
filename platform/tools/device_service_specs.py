"""Device catalogue parsing and runtime-profile selection for Device Service."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Any

from device_service_esp32sim import BACKEND as ESP32SIM_BACKEND, Installation, RUNTIME as ESP32SIM_RUNTIME
from device_service_errors import ServiceError
from device_service_native_hid import STICKS3_NATIVE_HID_PROFILE
from device_service_parsing import parse_size


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"
PROFILES = ROOT / "platform/qemu/profiles.json"
DEVICE_CATALOG = ROOT / "devices/catalog.source.json"

SERVICE_MEMORY_OVERRIDES = {"core2": "8"}
# These boards wire SD media to the GP-SPI controller. A profile may list
# an SD peripheral that is still planned or lacks card-detect support.
SPI_SD_DEVICE_IDS = frozenset({
    "core2", "cores3", "cardputer", "cardputer-adv", "papercolor",
    "papers3", "paperdiy",
})
QEMU_PROBE_TIMEOUT = 2
EXCLUDED_DEVICES = {
    "cardputer-zero": "CardputerZero uses a separate Linux backend",
}

NETWORK_PROFILES = {
    "uiflow2-sticks3",
    "esp-idf-http",
    "esp-idf-smoke",
    "idf-dns-udp",
    "esp-idf-wrong-password",
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
CORE2_UNIFIED_PROFILE = "core2-unified"
CORE2_NATIVE_VHCI_PROFILE = "core2-native-vhci"
CORE2_NATIVE_HCI_PROFILE = "core2-native-hci"
NANOC6_HCI_BLE_PROFILE = "nanoc6-hci-ble"
NESSO_UNIFIED_PROFILE = "nesso-unified"
STICKS3_WIFI_PROFILE = "uiflow2-sticks3-wifi"
STICKS3_UNIFIED_PROFILE = "uiflow2-sticks3-unified"
CORES3_UNIFIED_PROFILE = "uiflow2-cores3-unified"
CARDPUTER_ADV_UNIFIED_PROFILE = "uiflow2-cardputer-adv-unified"
STOPWATCH_UNIFIED_PROFILE = "uiflow2-stopwatch-unified"
ATOMS3R_UNIFIED_PROFILE = "uiflow2-atoms3r-unified"
PAPERCOLOR_UNIFIED_PROFILE = "uiflow2-papercolor-unified"
PAPERMONO_UNIFIED_PROFILE = "uiflow2-papermono-unified"
STACKCHAN_UNIFIED_PROFILE = "uiflow2-stackchan-unified"
STAMPLC_UNIFIED_PROFILE = "uiflow2-stamplc-unified"
UNIFIED_PROFILES = {
    NANOC6_HCI_BLE_PROFILE,
    NESSO_UNIFIED_PROFILE,
    STICKS3_UNIFIED_PROFILE,
    CORES3_UNIFIED_PROFILE,
    CARDPUTER_ADV_UNIFIED_PROFILE,
    STOPWATCH_UNIFIED_PROFILE,
    ATOMS3R_UNIFIED_PROFILE,
    PAPERCOLOR_UNIFIED_PROFILE,
    PAPERMONO_UNIFIED_PROFILE,
    STACKCHAN_UNIFIED_PROFILE,
    STAMPLC_UNIFIED_PROFILE,
    CORE2_UNIFIED_PROFILE,
    CORE2_NATIVE_VHCI_PROFILE,
    CORE2_NATIVE_HCI_PROFILE,
}


def backend_qemu_path(backend_id: str, configured: str) -> Path:
    override_name = {
        "qemu-esp32s3": "M5_QEMU_XTENSA",
        "qemu-esp32lx6": "M5_QEMU_XTENSA",
        "qemu-esp32c6": "M5_QEMU_RISCV32",
    }.get(backend_id)
    raw = os.environ.get(override_name, "").strip() if override_name else ""
    path = Path(raw) if raw else ROOT / configured
    return path if path.is_absolute() else ROOT / path


def backend_rom_dir(backend_id: str, configured: str) -> Path:
    override_name = {
        "qemu-esp32s3": "M5_QEMU_XTENSA_ROM_DIR",
        "qemu-esp32lx6": "M5_QEMU_XTENSA_ROM_DIR",
        "qemu-esp32c6": "M5_QEMU_RISCV32_ROM_DIR",
    }.get(backend_id)
    raw = os.environ.get(override_name, "").strip() if override_name else ""
    path = Path(raw) if raw else ROOT / configured
    return path if path.is_absolute() else ROOT / path


def _qemu_file_identity(binary: Path) -> tuple[int, ...]:
    info = binary.stat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError(f"QEMU executable is not a regular file: {binary}")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@lru_cache(maxsize=16)
def _qemu_machine_names(binary: Path, _file_identity: tuple[int, ...]) -> frozenset[str]:
    output = subprocess.run(
        [str(binary), "-machine", "help"], check=True, capture_output=True,
        timeout=QEMU_PROBE_TIMEOUT, text=True, encoding="utf-8", errors="replace",
    ).stdout
    return frozenset(line.split()[0] for line in output.splitlines() if line.strip())


@lru_cache(maxsize=32)
def _qemu_qom_properties(
    binary: Path,
    _file_identity: tuple[int, ...],
    typename: str,
) -> frozenset[tuple[str, str]]:
    commands = (
        {"execute": "qmp_capabilities"},
        {"execute": "qom-list-properties", "arguments": {"typename": typename}, "id": "properties"},
        {"execute": "quit"},
    )
    output = subprocess.run(
        [str(binary), "-M", "none", "-S", "-display", "none", "-qmp", "stdio"],
        input="".join(json.dumps(command) + "\n" for command in commands),
        check=True, capture_output=True, timeout=QEMU_PROBE_TIMEOUT,
        text=True, encoding="utf-8",
    ).stdout
    for line in output.splitlines():
        if not line.strip():
            continue
        message = json.loads(line)
        if isinstance(message, dict) and message.get("id") == "properties":
            properties = message.get("return")
            if isinstance(properties, list):
                return frozenset(
                    (row["name"], row["type"])
                    for row in properties
                    if isinstance(row, dict)
                    and isinstance(row.get("name"), str)
                    and isinstance(row.get("type"), str)
                )
            break
    raise ValueError(f"missing QMP property list for {typename}")


def qemu_has_qom_property(
    binary: Path, typename: str, name: str, property_type: str
) -> bool:
    """Discover a property on the configured QEMU binary without booting a guest."""
    try:
        return (name, property_type) in _qemu_qom_properties(
            binary, _qemu_file_identity(binary), typename
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


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
    peripherals: list[str]
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
    require_machine_probe: bool = False
    qemu_console_index: int = 0

    default_runtime: str = "qemu"

    @property
    def esp32sim_installation(self) -> Installation:
        return Installation.discover()

    @property
    def has_display(self) -> bool:
        display = self.display or {}
        return bool(display.get("width") and display.get("height"))

    @property
    def has_sd_card(self) -> bool:
        if self.id == "paperdiy":
            return (
                self.service_kind == "qemu"
                and self.machine == "m5paperdiy"
                and "sd-card-spi" in self.peripherals
                and qemu_has_qom_property(
                    self.qemu, "m5paperdiy-machine", "sd-card-detect-model", "bool"
                )
            )
        if self.id in SPI_SD_DEVICE_IDS:
            return any(model in self.peripherals for model in ("sd", "sd-card-spi"))
        return "sd" in self.peripherals

    @property
    def has_sd_hotplug(self) -> bool:
        return (
            self.id == "paperdiy" and self.has_sd_card
            and qemu_has_qom_property(
                self.qemu, "m5paperdiy-machine", "sd-card-hotplug-model", "bool"
            )
        )

    @property
    def has_unit_audio_pcm(self) -> bool:
        return (
            self.id == "dial" and self.service_kind == "qemu" and self.machine == "m5dial"
            and qemu_has_qom_property(self.qemu, "m5dial-machine", "media-pcm-supported", "bool")
        )

    @property
    def has_sd_write_stamp(self) -> bool:
        return self.service_kind == "qemu" and (
            self.id in {"cardputer", "cardputer-adv"} or self.has_sd_hotplug
        )

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
            and (
                self.flash_emulator is None
                or self.flash_emulator.is_file()
                or os.environ.get("M5_SERVICE_FLASH_MODE") == "host-image"
            )
            and self.missing_backend_machine is None
        )

    @property
    def missing_backend_machine(self) -> str | None:
        if not self.require_machine_probe or not self.qemu.is_file():
            return None
        try:
            if self.machine in _qemu_machine_names(self.qemu, _qemu_file_identity(self.qemu)):
                return None
        except (OSError, subprocess.SubprocessError):
            pass
        return self.machine

    @property
    def missing_backend_files(self) -> list[Path]:
        if self.service_kind == "tab5":
            return [
                path
                for path in (
                    self.emulator,
                    self.rom,
                    self.efuse,
                    self.c6_firmware,
                    self.reference_path,
                )
                if path is not None and not path.is_file()
            ]
        missing = []
        if not self.qemu.is_file():
            missing.append(self.qemu)
        if not self.rom_dir.is_dir():
            missing.append(self.rom_dir)
        if (
            self.flash_emulator is not None
            and not self.flash_emulator.is_file()
            and os.environ.get("M5_SERVICE_FLASH_MODE") != "host-image"
        ):
            missing.append(self.flash_emulator)
        return missing


def load_device_specs() -> dict[str, DeviceSpec]:
    matrix = json.loads(MATRIX.read_text())
    profiles = json.loads(PROFILES.read_text())
    catalog_source = json.loads(DEVICE_CATALOG.read_text())
    profiles_by_id = {
        row["id"]: row for row in profiles["devices"]
    }
    source_by_id = {
        row["id"]: row for row in catalog_source["devices"]
    }
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
                and row["mode"] in {"ui", "console", "service-ui"}
            )
            service_kind = "qemu"
            qemu = (
                backend_qemu_path(row["backend"], backend["qemu"])
                if backend.get("qemu")
                else ROOT / "__missing_qemu__"
            )
            rom_dir = (
                backend_rom_dir(row["backend"], backend["rom_dir"])
                if backend.get("rom_dir")
                else ROOT / "__missing_rom__"
            )
            emulator = None
            elf = None
            rom = None
            efuse = None
            c6_firmware = None
            flash_emulator = None
            if backend.get("esp_emu_chip"):
                configured_emulator = os.environ.get(
                    "M5_SERVICE_ESP_EMU", ""
                ).strip()
                flash_emulator = (
                    Path(configured_emulator)
                    if configured_emulator
                    else ROOT / ".work/bin/esp-emu"
                )
                if not flash_emulator.is_absolute():
                    flash_emulator = ROOT / flash_emulator
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
                    f"{device_id} has invalid network_status "
                    f"{network_status!r}",
                    500,
                )
            network_profiles = (
                sorted(NETWORK_PROFILES - {"uiflow2-sticks3"})
                if network_chip
                else []
            )
            if device_id == "sticks3" and network_chip:
                network_profiles.insert(0, STICKS3_WIFI_PROFILE)
                network_profiles.insert(0, "uiflow2-sticks3")
                network_profiles.insert(0, STICKS3_UNIFIED_PROFILE)
                network_profiles.insert(0, STICKS3_NATIVE_HID_PROFILE)
            if device_id == "cores3" and network_chip:
                network_profiles.insert(0, CORES3_UNIFIED_PROFILE)
            if device_id == "cardputer-adv" and network_chip:
                network_profiles.insert(
                    0, CARDPUTER_ADV_UNIFIED_PROFILE
                )
            if device_id == "stopwatch" and network_chip:
                network_profiles.insert(0, STOPWATCH_UNIFIED_PROFILE)
            if device_id == "atoms3r" and network_chip:
                network_profiles.insert(0, ATOMS3R_UNIFIED_PROFILE)
            if device_id == "papercolor" and network_chip:
                network_profiles.insert(0, PAPERCOLOR_UNIFIED_PROFILE)
            if device_id == "papermono" and network_chip:
                network_profiles.insert(0, PAPERMONO_UNIFIED_PROFILE)
            if device_id == "stackchan" and network_chip:
                network_profiles.insert(0, STACKCHAN_UNIFIED_PROFILE)
            if device_id == "stamplc" and network_chip:
                network_profiles.insert(0, STAMPLC_UNIFIED_PROFILE)
            if device_id == "nanoc6" and network_chip:
                network_profiles.insert(0, NANOC6_HCI_BLE_PROFILE)
            if device_id == "nesso-n1" and network_chip:
                network_profiles.insert(0, NESSO_UNIFIED_PROFILE)
            if (
                device_id == "core2"
                and (
                    os.environ.get("M5_CORE2_RADIO_QEMU")
                    or os.environ.get("M5_CORE2_WIFI_QEMU")
                )
            ):
                core2_radio_qemu_path()
                network_profiles = [
                    CORE2_NATIVE_HCI_PROFILE,
                    CORE2_NATIVE_VHCI_PROFILE,
                    CORE2_UNIFIED_PROFILE,
                    CORE2_WIFI_PROFILE,
                    CORE2_BLE_PROFILE,
                    CORE2_HCI_GATT_PROFILE,
                ]
                network_status = "validated"
            reason = excluded_reason
            if not backend and reason is None:
                reason = (
                    f"backend {row['backend']} is not registered for "
                    "service execution"
                )
            if not supported and reason is None:
                reason = (
                    f"backend mode {row.get('mode')} is not enabled "
                    "for this service"
                )
        catalog_runtime = source.get("runtime", {})
        specs[device_id] = DeviceSpec(
            id=device_id,
            name=profile.get("name", device_id),
            group=profile.get("group", ""),
            soc=profile.get("soc", ""),
            sku=source.get("sku", ""),
            device_codes=(
                [source["uiflow2"]["firmware"]["firmware_id"]]
                if (uiflow_source.get("firmware") or {}).get(
                    "firmware_id"
                )
                else []
            ),
            backend=row["backend"],
            machine=row.get("machine", ""),
            flash_size=(
                16 << 20
                if device_id == "tab5"
                else int(row["flash_size"], 0) if row.get("flash_size")
                else (source.get("runtime", {}).get("esp32sim") or {}).get("flash_bytes", 0)
            ),
            display=profile.get("display"),
            peripherals=list(profile.get("peripherals", [])),
            reference_path=reference,
            qemu=qemu,
            rom_dir=rom_dir,
            efuse_driver=row.get("efuse_driver", backend.get("efuse_driver")),
            memory=SERVICE_MEMORY_OVERRIDES.get(
                device_id, row.get("memory")
            ),
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
                if isinstance(
                    profile.get("runtime_state", {}), dict
                )
                else {}
            ),
            reason=reason,
            default_runtime=(
                ESP32SIM_RUNTIME
                if (catalog_runtime.get("backend") == ESP32SIM_BACKEND
                    or catalog_runtime.get(ESP32SIM_RUNTIME, {}).get("default") is True)
                else "qemu"
            ),
            require_machine_probe=profile.get("require_machine_probe") is True,
        )
    return specs
