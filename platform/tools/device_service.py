#!/usr/bin/env python3
"""Leased, on-demand virtual M5Stack device service.

This module is intentionally a local, trusted-workstation service. It owns the
process lifecycle for QEMU/esp-emu-backed ESP32 devices and exposes an HTTP
API through serve.py. Selected devices support same-instance QEMU WiFi/BLE or
HCI-offload profiles; Tab5 is supported with an explicit partial-peripheral
warning.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import ipaddress
import json
import math
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass
from contextlib import contextmanager
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

from ble_runtime_limits import (  # noqa: E402
    MAX_BLE_LINGER_SECONDS,
    MAX_BLE_RECONNECT_CYCLES,
    MAX_BLE_RECONNECT_DELAY_SECONDS,
    ble_peer_scan_timeout_seconds,
    reconnect_workload_timeout_seconds,
)
from esp_flash import default_env, flash_with_esp_emu, flash_with_qemu  # noqa: E402
from uiflow_source import UIFlowSourceError, build_uiflow_source_image  # noqa: E402
from program_revisions import MAX_REVISIONS, ProgramRevisionStore, RevisionError  # noqa: E402
from preview_retention import PreviewRetention, RetentionRoots, add_session_roots  # noqa: E402
from program_packages import (  # noqa: E402
    MAX_FILE_BYTES as MAX_PROGRAM_FILE_BYTES,
    MAX_PACKAGE_BYTES, MAX_PACKAGE_FILES, MAX_PACKAGES,
    ProgramPackageStore, ProgramPackageError, _snapshot as program_package_snapshot,
)
from mpy_bytecode import MPYBytecodeError, validate_bytecode  # noqa: E402
from uiflow_package_runtime import deploy_package, validate_mpy  # noqa: E402
from uiflow_main_loader import main_loader_verified, probe_main_loader  # noqa: E402
from frame_cache import CaptureResult, FrameCache, FrameGenerationChanged  # noqa: E402
from uiflow_runtime import (  # noqa: E402
    ExecutionStateScanner, LIVE_PROGRAM_DEVICES, LIVE_READY_MARKER,
    UIFlowRuntimeError, live_bootstrap_files, run_mpy, run_source, synchronize_raw_repl,
)
from firmware_analysis import (  # noqa: E402
    analyze_esp_image,
    analyze_firmware,
    detect_secure_boot_v2_signature,
    expected_chip_id,
    find_app_descriptor,
    parse_partition_table,
)
from firmware_manifest import (  # noqa: E402
    ManifestError,
    canonical_json_sha256,
    import_package,
    load_device_profile,
    manifest_identity_payload,
    normalize_capability_declarations,
    validate_capabilities,
    validate_manifest_structure,
)
from network_egress import (  # noqa: E402
    EgressEndpoint,
    endpoint_contains_address,
    requires_external_gateway,
    requires_external_ipv6,
)
from network_egress import (
    capability as egress_capability,
)
from network_lane import normalize_hostfwd, normalize_i2c_device  # noqa: E402
from network_policy import (  # noqa: E402
    NetworkPolicy,
    NetworkPolicyError,
    build_sandbox_command,
    namespace_capability,
    qemu_user_netdev,
)
from network_sandbox import (  # noqa: E402
    SandboxError,
    validate_cname_record_bindings,
)
from pcap_summary import PcapError, summarize_pcap  # noqa: E402
from qemu_accel import core2_accel_args  # noqa: E402
from run_profile_ui_test import (  # noqa: E402
    QMP,
    QMPCommandError,
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
)
from run_tab5_ui_test import (
    wait_for_path as wait_for_fs_path,
)
from run_tab5_ui_test import (
    wait_for_port as wait_for_tcp_port,
)
from run_tab5_ui_test import (
    write_png as write_tab5_png,
)
from storage_policy import StoragePolicy, directory_size_bytes  # noqa: E402
from unit_runtime import UnitError, UnitRegistry  # noqa: E402
from unit_adc_fixture import (  # noqa: E402
    CARDPUTER_FIXTURE,
    FIXTURE as UNIT_ADC_FIXTURE,
    apply_s3_adc_calibration,
    load_fixture as load_adc_fixture,
    verify_firmware as verify_adc_firmware,
)
from worker_auth import WorkerAuthError, WorkerAuthVerifier  # noqa: E402
from worker_directory import (  # noqa: E402
    WorkerDirectory,
    WorkerDirectoryError,
)
from worker_queue import WorkerJobQueue, WorkerQueueError  # noqa: E402
from worker_registry import WorkerRegistry, WorkerRegistryError  # noqa: E402
from xtensa_elf_symbols import (  # noqa: E402
    ElfSymbolError,
    core2_native_hci_device_args,
    core2_native_vhci_addresses,
)

DEFAULT_STATE_DIR = ROOT / "platform/.cache/service"
DEFAULT_MAX_SESSIONS = 12
DEFAULT_MAX_PER_DEVICE = 8
SERVICE_MEMORY_OVERRIDES = {"core2": "8"}
TAB5_I2C_DEVICES = (
    "1:0x32,fill=0",
    "1:0x41,fill=0,reg=0xFE=0x54,reg=0xFF=0x49,"
    "reg=0x02=0x19,reg=0x03=0x00,reg=0x04=0xB0",
    "1:0x43,fill=0,reg=0x01=0xA2",
    "1:0x44,fill=0,reg=0x01=0xA2,reg=0x0F=0x00",
    "1:0x68,fill=0,reg=0x00=0x24",
)
QMP_COMMAND_TIMEOUT = 2
QMP_START_TIMEOUT = 60
SESSION_STOP_WAIT_SECONDS = 1.0
# QAPI QKeyCode from the pinned Espressif QEMU base, qapi/ui.json:
# https://github.com/espressif/qemu/blob/40edccac415693c5130f91c01d84176ae6008566/qapi/ui.json
# send_key_event otherwise leaves unknown qcodes to a late QMP rejection.
QEMU_INPUT_QCODES = frozenset("""
unmapped shift shift_r alt alt_r ctrl ctrl_r menu esc 1 2 3 4 5 6 7 8 9 0
minus equal backspace tab q w e r t y u i o p bracket_left bracket_right ret
a s d f g h j k l semicolon apostrophe grave_accent backslash z x c v b n m
comma dot slash asterisk spc caps_lock f1 f2 f3 f4 f5 f6 f7 f8 f9 f10 num_lock
scroll_lock kp_divide kp_multiply kp_subtract kp_add kp_enter kp_decimal sysrq
kp_0 kp_1 kp_2 kp_3 kp_4 kp_5 kp_6 kp_7 kp_8 kp_9 less f11 f12 print home pgup
pgdn end left up down right insert delete stop again props undo front copy open
paste find cut lf help meta_l meta_r compose pause ro hiragana henkan yen
muhenkan katakanahiragana kp_comma kp_equals power sleep wake audionext
audioprev audiostop audioplay audiomute volumeup volumedown mediaselect mail
calculator computer ac_home ac_back ac_forward ac_refresh ac_bookmarks lang1
lang2 f13 f14 f15 f16 f17 f18 f19 f20 f21 f22 f23 f24
""".split())
EXCLUDED_DEVICES = {
    "cardputer-zero": "CardputerZero uses a separate Linux backend",
}
MAX_ARTIFACT_BYTES = 96 * 1024 * 1024
MAX_ARTIFACT_CHUNK_BYTES = 8 * 1024 * 1024
MAX_SERIAL_READ = 256 * 1024
SESSION_IDEMPOTENCY_SCHEMA_VERSION = 1
MAX_SESSION_IDEMPOTENCY_ENTRIES = 4096
ACTIVE_STATES = {"provisioning", "flashing", "booting", "running"}
OCCUPIED_STATES = ACTIVE_STATES | {"stopping"}
ALLOWED_RUNTIME_ENV = {
    "M5SW_CORE2_PMIC",
    "M5SW_ESPNOW_LOOPBACK",
    "M5SW_ESPNOW_PEER_LOCAL_PORT",
    "M5SW_ESPNOW_PEER_LMK",
    "M5SW_ESPNOW_PEER_PMK",
    "M5SW_ESPNOW_PEER_REMOTE_PORT",
    "M5SW_ESPNOW_PEER_TRACE",
    "M5SW_I2S_DMA_IRQ",
    "M5SW_I2S_PCM_FILE",
    "M5SW_I2S_RX_PCM_FILE",
    "M5SW_I2S_TRACE",
    "M5SW_RMT_RX_FILE",
    "M5SW_RMT_TX_FILE",
    "M5SW_RMT_TRACE",
    "M5SW_INPUT_TRACE",
    "M5SW_FT_TRACE",
    "M5SW_I2C_TRACE",
    "M5SW_CAMERA_TRACE",
    "M5SW_GDMA_TRACE",
    "M5SW_GPSPI_TRACE",
    "M5SW_SPI_XFER_TRACE",
    "M5SW_LCD_TRACE",
}
PRIVATE_RUNTIME_ENV = frozenset({
    "M5SW_ESPNOW_PEER_LMK",
    "M5SW_ESPNOW_PEER_PMK",
})
BOOLEAN_RUNTIME_TRACES = frozenset({
    "M5SW_CAMERA_TRACE",
    "M5SW_ESPNOW_LOOPBACK",
    "M5SW_ESPNOW_PEER_TRACE",
    "M5SW_GDMA_TRACE",
    "M5SW_GPSPI_TRACE",
    "M5SW_FT_TRACE",
    "M5SW_INPUT_TRACE",
    "M5SW_I2C_TRACE",
    "M5SW_LCD_TRACE",
    "M5SW_RMT_TRACE",
    "M5SW_SPI_XFER_TRACE",
})
CORE2_PMIC_VARIANTS = {"axp192", "axp2101"}
PLAIN_QEMU_AUDIO_DEVICES = frozenset({
    "cores3",
    "cardputer-adv",
    "stopwatch",
    "sticks3",
    "core2",
})
NETWORK_LANE = ROOT / "platform/tools/network_lane.py"
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
UNIFIED_HTTP_GUESTFWD = (
    ROOT / "platform/tools/unified_http_guestfwd.py"
)
NATIVE_VHCI_GDB_SCRIPT = (
    ROOT / "tests/uiflow2/core2_radio_probe/native_vhci_bridge.gdb"
)
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
UNIFIED_HTTP_PORTS = {
    STICKS3_WIFI_PROFILE: 18080,
    NANOC6_HCI_BLE_PROFILE: 18090,
    NESSO_UNIFIED_PROFILE: 18091,
    STICKS3_UNIFIED_PROFILE: 18080,
    CORES3_UNIFIED_PROFILE: 18081,
    CARDPUTER_ADV_UNIFIED_PROFILE: 18082,
    STOPWATCH_UNIFIED_PROFILE: 18083,
    ATOMS3R_UNIFIED_PROFILE: 18084,
    PAPERCOLOR_UNIFIED_PROFILE: 18085,
    PAPERMONO_UNIFIED_PROFILE: 18086,
    STACKCHAN_UNIFIED_PROFILE: 18087,
    STAMPLC_UNIFIED_PROFILE: 18088,
    CORE2_UNIFIED_PROFILE: 18089,
    CORE2_NATIVE_VHCI_PROFILE: 18089,
    CORE2_NATIVE_HCI_PROFILE: 18089,
}
QEMU_WIFI_RUNTIME = "qemu-wifi"
QEMU_BLE_RUNTIME = "qemu-ble"
QEMU_UNIFIED_RUNTIME = "qemu-unified"
QEMU_RADIO_RUNTIMES = frozenset(
    {QEMU_WIFI_RUNTIME, QEMU_BLE_RUNTIME, QEMU_UNIFIED_RUNTIME}
)
QEMU_QMP_RUNTIMES = frozenset({"qemu", *QEMU_RADIO_RUNTIMES})
QEMU_SESSION_RUNTIMES = frozenset({"qemu", "network", *QEMU_RADIO_RUNTIMES})
SINGLE_GUEST_PROFILES = frozenset(
    {*UNIFIED_PROFILES, NESSO_UNIFIED_PROFILE}
)


def controlled_http_requests_match(requests: list[dict]) -> bool:
    return bool(requests) and all(
        item.get("path") == "/unified"
        and item.get("host") == "qemu.test"
        for item in requests
    )


def qemu_runtime_memory(
    memory: str | None,
    profile: str | None,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Describe the QEMU PSRAM selection without claiming physical timing."""
    requested: int | None
    try:
        requested = int(memory) if memory is not None else None
    except (TypeError, ValueError):
        requested = None
    native_controller = profile in {
        CORE2_NATIVE_VHCI_PROFILE,
        CORE2_NATIVE_HCI_PROFILE,
    }
    cli_requested = 0 if native_controller else requested
    effective = cli_requested
    effective_source = "qemu-cli-request"
    if native_controller and device_id == "core2":
        # The m5core2 machine resolves `-m 0` to its 8 MiB board default.
        # QOM evidence verifies memory=8 MiB and has_psram=true.
        effective = 8
        effective_source = "validated-m5core2-qom"
    if native_controller:
        policy = "native-controller-machine-default-psram"
    elif effective == 0:
        policy = "qemu-no-psram"
    elif effective is not None:
        policy = "qemu-emulated-psram"
    else:
        policy = "not-configured"
    return {
        "requested_psram_mib": requested,
        "cli_requested_psram_mib": cli_requested,
        "effective_psram_mib": effective,
        "effective_source": effective_source,
        "policy": policy,
        "claim": "qemu-memory-configuration-only",
        "physical_cache_psram_timing": "NOT RUN",
    }


def runtime_psram_mismatch(
    memory: str | None,
    profile: str | None,
    required_bytes: object,
    device_id: str | None = None,
) -> dict[str, Any] | None:
    """Return a structured preflight issue for an undersized QEMU PSRAM lane."""
    if not isinstance(required_bytes, int) or required_bytes <= 0:
        return None
    runtime_memory = qemu_runtime_memory(memory, profile, device_id)
    effective_mib = runtime_memory["effective_psram_mib"]
    if not isinstance(effective_mib, int):
        return None
    available_bytes = effective_mib << 20
    if required_bytes <= available_bytes:
        return None
    return {
        "code": "runtime_psram_mismatch",
        "message": (
            f"firmware declares {required_bytes} bytes of PSRAM; "
            f"runtime profile provides {available_bytes}"
        ),
        "requirement": required_bytes,
        "available": available_bytes,
        "path": "target.psram_size",
        "runtime_profile": profile,
        "memory_policy": runtime_memory["policy"],
    }


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
NANOC6_HCI_BLE_MARKERS = (
    "NANOC6_HCI_BOARD 140",
    "NANOC6_HCI_RGB 1 00FF00",
    "NANOC6_HCI_BLUE 1",
    "NANOC6_HCI_IR 0x56 0xA3",
    "NANOC6_HCI_WIFI_SCAN",
    "NANOC6_HCI_WIFI_CONNECTED 10.0.2.15",
    "NANOC6_HCI_HTTP_PASS",
    "NANOC6_HCI_BUTTON_PRESS",
    "NANOC6_HCI_BUTTON_RELEASE",
    "NANOC6_HCI_BLE_RX",
    "NANOC6_HCI_BLE_ACK_SENT",
    "NANOC6_HCI_READY",
)
NANOC6_BLE_IDENTITY = ("M5-NANOC6-HCI", "M5_NANOC6_HCI")
NESSO_UNIFIED_MARKERS = (
    "UNIFIED_NESSO_BOARD 23",
    "UNIFIED_NESSO_DISPLAY 135 240",
    "UNIFIED_NESSO_POWER 100 4300 1",
    "UNIFIED_NESSO_IMU 0.25 -0.50 0.75 10.0 -20.0 30.0",
    "UNIFIED_NESSO_LORA M5LORA",
    "UNIFIED_NESSO_IR 0x56 0xA3",
    "UNIFIED_NESSO_BUZZER 3500",
    "UNIFIED_NESSO_WIFI_SCAN",
    "UNIFIED_NESSO_WIFI_CONNECTED 10.0.2.15",
    "UNIFIED_NESSO_HTTP_PASS",
    "UNIFIED_NESSO_TOUCH",
    "UNIFIED_NESSO_BUTTON 1",
    "UNIFIED_NESSO_BLE_RX",
    "UNIFIED_NESSO_BLE_ACK_SENT",
    "UNIFIED_NESSO_READY",
)
NESSO_BLE_IDENTITY = ("M5-NESSO-UNIFIED", "M5_NESSO_UNIFIED")
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
STOPWATCH_UNIFIED_MARKERS = (
    "UNIFIED_STOPWATCH_WIFI_CONNECTED",
    "UNIFIED_STOPWATCH_HTTP_PASS",
    "UNIFIED_STOPWATCH_BLE_RX",
    "UNIFIED_STOPWATCH_BLE_ACK_SENT",
)
ATOMS3R_UNIFIED_MARKERS = (
    "UNIFIED_ATOMS3R_WIFI_CONNECTED",
    "UNIFIED_ATOMS3R_HTTP_PASS",
    "UNIFIED_ATOMS3R_BLE_RX",
    "UNIFIED_ATOMS3R_BLE_ACK_SENT",
)
PAPERCOLOR_UNIFIED_MARKERS = (
    "UNIFIED_PAPERCOLOR_WIFI_CONNECTED",
    "UNIFIED_PAPERCOLOR_HTTP_PASS",
    "UNIFIED_PAPERCOLOR_BLE_RX",
    "UNIFIED_PAPERCOLOR_BLE_ACK_SENT",
)
PAPERMONO_UNIFIED_MARKERS = (
    "UNIFIED_PAPERMONO_WIFI_CONNECTED",
    "UNIFIED_PAPERMONO_HTTP_PASS",
    "UNIFIED_PAPERMONO_BLE_RX",
    "UNIFIED_PAPERMONO_BLE_ACK_SENT",
)
STACKCHAN_UNIFIED_MARKERS = (
    "UNIFIED_STACKCHAN_WIFI_CONNECTED",
    "UNIFIED_STACKCHAN_HTTP_PASS",
    "UNIFIED_STACKCHAN_BLE_RX",
    "UNIFIED_STACKCHAN_BLE_ACK_SENT",
)
STAMPLC_UNIFIED_MARKERS = (
    "UNIFIED_STAMPLC_WIFI_CONNECTED",
    "UNIFIED_STAMPLC_HTTP_PASS",
    "UNIFIED_STAMPLC_BLE_RX",
    "UNIFIED_STAMPLC_BLE_ACK_SENT",
)
CORE2_UNIFIED_MARKERS = (
    "UNIFIED_CORE2_WIFI_CONNECTED",
    "UNIFIED_CORE2_HTTP_PASS",
    "UNIFIED_CORE2_PUBLIC_DNS",
    "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
    "UNIFIED_CORE2_BLE_RX",
    "UNIFIED_CORE2_BLE_ACK_SENT",
)
UNIFIED_MARKERS = {
    STICKS3_UNIFIED_PROFILE: STICKS3_UNIFIED_MARKERS,
    CORES3_UNIFIED_PROFILE: CORES3_UNIFIED_MARKERS,
    CARDPUTER_ADV_UNIFIED_PROFILE: CARDPUTER_ADV_UNIFIED_MARKERS,
    STOPWATCH_UNIFIED_PROFILE: STOPWATCH_UNIFIED_MARKERS,
    ATOMS3R_UNIFIED_PROFILE: ATOMS3R_UNIFIED_MARKERS,
    PAPERCOLOR_UNIFIED_PROFILE: PAPERCOLOR_UNIFIED_MARKERS,
    PAPERMONO_UNIFIED_PROFILE: PAPERMONO_UNIFIED_MARKERS,
    STACKCHAN_UNIFIED_PROFILE: STACKCHAN_UNIFIED_MARKERS,
    STAMPLC_UNIFIED_PROFILE: STAMPLC_UNIFIED_MARKERS,
    CORE2_UNIFIED_PROFILE: CORE2_UNIFIED_MARKERS,
    CORE2_NATIVE_VHCI_PROFILE: CORE2_UNIFIED_MARKERS,
    CORE2_NATIVE_HCI_PROFILE: CORE2_UNIFIED_MARKERS,
}
UNIFIED_READY_MARKERS = {
    NANOC6_HCI_BLE_PROFILE: "NANOC6_HCI_READY",
    NESSO_UNIFIED_PROFILE: "UNIFIED_NESSO_READY",
    STICKS3_UNIFIED_PROFILE: "UNIFIED_STICKS3_READY",
    CORES3_UNIFIED_PROFILE: "UNIFIED_CORES3_READY",
    CARDPUTER_ADV_UNIFIED_PROFILE: "UNIFIED_CARDPUTER_READY",
    STOPWATCH_UNIFIED_PROFILE: "UNIFIED_STOPWATCH_READY",
    ATOMS3R_UNIFIED_PROFILE: "UNIFIED_ATOMS3R_READY",
    PAPERCOLOR_UNIFIED_PROFILE: "UNIFIED_PAPERCOLOR_READY",
    PAPERMONO_UNIFIED_PROFILE: "UNIFIED_PAPERMONO_READY",
    STACKCHAN_UNIFIED_PROFILE: "UNIFIED_STACKCHAN_READY",
    STAMPLC_UNIFIED_PROFILE: "UNIFIED_STAMPLC_READY",
    CORE2_UNIFIED_PROFILE: "UNIFIED_CORE2_READY",
    CORE2_NATIVE_VHCI_PROFILE: "UNIFIED_CORE2_READY",
    CORE2_NATIVE_HCI_PROFILE: "UNIFIED_CORE2_READY",
}
UNIFIED_HTTP_BODIES = {
    STICKS3_WIFI_PROFILE: b"STICKS3_WIFI_OK\n",
    NANOC6_HCI_BLE_PROFILE: b"UNIFIED_NANOC6_OK\n",
    NESSO_UNIFIED_PROFILE: b"UNIFIED_NESSO_OK\n",
    STICKS3_UNIFIED_PROFILE: b"UNIFIED_STICKS3_OK\n",
    CORES3_UNIFIED_PROFILE: b"UNIFIED_CORES3_OK\n",
    CARDPUTER_ADV_UNIFIED_PROFILE: b"UNIFIED_CARDPUTER_OK\n",
    STOPWATCH_UNIFIED_PROFILE: b"UNIFIED_STOPWATCH_OK\n",
    ATOMS3R_UNIFIED_PROFILE: b"UNIFIED_ATOMS3R_OK\n",
    PAPERCOLOR_UNIFIED_PROFILE: b"UNIFIED_PAPERCOLOR_OK\n",
    PAPERMONO_UNIFIED_PROFILE: b"UNIFIED_PAPERMONO_OK\n",
    STACKCHAN_UNIFIED_PROFILE: b"UNIFIED_STACKCHAN_OK\n",
    STAMPLC_UNIFIED_PROFILE: b"UNIFIED_STAMPLC_OK\n",
    CORE2_UNIFIED_PROFILE: b"UNIFIED_CORE2_OK\n",
    CORE2_NATIVE_VHCI_PROFILE: b"UNIFIED_CORE2_OK\n",
    CORE2_NATIVE_HCI_PROFILE: b"UNIFIED_CORE2_OK\n",
}
UNIFIED_BLE_IDENTITIES = {
    "nanoc6": NANOC6_BLE_IDENTITY,
    "nesso-n1": NESSO_BLE_IDENTITY,
    "sticks3": ("M5-STICKS3-UNIFIED", "M5_STICKS3_UNIFIED"),
    "cores3": ("M5-CORES3-UNIFIED", "M5_CORES3_UNIFIED"),
    "cardputer-adv": ("M5-CPTR-ADV-UNIFIED", "M5_CPTR_ADV"),
    "stopwatch": ("M5-STOPWATCH-UNIFIED", "M5_STOPWATCH_U"),
    "atoms3r": ("M5-ATOMS3R-UNIFIED", "M5_ATOMS3R_U"),
    "papercolor": ("M5-PAPERCOLOR-UNIFIED", "M5_PAPERCOLOR_U"),
    "papermono": ("M5-PAPERMONO-UNIFIED", "M5_PAPERMONO_U"),
    "stackchan": ("M5-STACKCHAN-UNIFIED", "M5_STACKCHAN_U"),
    "stamplc": ("M5-STAMPLC-UNIFIED", "M5_STAMPLC_U"),
    "core2": ("M5-CORE2-UNIFIED", "M5_CORE2_UNIFIED"),
}
STACKCHAN_UNIFIED_QOM = (
    ("/machine/aw9523", "input-bits", 61439),
    ("/machine/ina226", "bus-voltage-mv", 4000),
    ("/machine/ina226", "current-ma", 250),
    ("/machine/ina226", "shunt-ohms", 0.08),
    ("/machine/pcf8563", "unix-time", 1792630923),
    ("/machine/ltr553", "light-level", 640),
    ("/machine/ltr553", "proximity-level", 321),
    ("/machine/axp2101", "vbat-mv", 4000),
    ("/machine/axp2101", "vin-mv", 5000),
    ("/machine/axp2101", "charging", True),
    ("/machine/bmm150", "mag-x", 30),
    ("/machine/bmm150", "mag-y", -20),
    ("/machine/bmm150", "mag-z", 45),
    ("/machine/bmi270", "accel-x", 0.25),
    ("/machine/bmi270", "accel-y", -0.5),
    ("/machine/bmi270", "accel-z", 0.75),
    ("/machine/bmi270", "gyro-x", 10),
    ("/machine/bmi270", "gyro-y", -20),
    ("/machine/bmi270", "gyro-z", 30),
)
STAMPLC_UNIFIED_QOM = (
    ("/machine/lm75-48", "temperature-c", 37.5),
    ("/machine/ina226-40", "bus-voltage-mv", 4000),
    ("/machine/ina226-40", "current-ma", 250),
    ("/machine/ina226-40", "shunt-ohms", 0.08),
    ("/machine/aw9523-59", "input-bits", 61680),
    ("/machine/rx8130-32", "unix-time", 1792630923),
)
CORE2_UNIFIED_QOM = (
    ("/machine/axp2101", "vbat-mv", 4000),
    ("/machine/axp2101", "vin-mv", 5000),
    ("/machine/axp2101", "charging", True),
    ("/machine/ina3221-40", "bus1-mv", 4800),
    ("/machine/ina3221-40", "current1-ma", 240),
    ("/machine/ina3221-40", "shunt-ohms", 0.01),
    ("/machine/pcf8563", "unix-time", 1792630923),
    ("/machine/mpu6886", "accel-x", 0.25),
    ("/machine/mpu6886", "accel-y", -0.5),
    ("/machine/mpu6886", "accel-z", 0.75),
    ("/machine/mpu6886", "gyro-x", 10),
    ("/machine/mpu6886", "gyro-y", -20),
    ("/machine/mpu6886", "gyro-z", 30),
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redacted_network_config(config: dict | None) -> dict:
    safe = dict(config or {})
    for key in ("password", "wifi_password", "firmware_ap_password"):
        if key in safe and safe[key] is not None:
            safe[key] = "<redacted>"
    return safe


def redacted_runtime_env(runtime_env: dict[str, str] | None) -> dict[str, str]:
    return {
        key: "<redacted>" if key in PRIVATE_RUNTIME_ENV else value
        for key, value in (runtime_env or {}).items()
    }


def qemu_station_mac(session_id: str) -> str:
    digest = hashlib.sha256(
        f"m5stack-qemu-wifi:{session_id}".encode()
    ).digest()
    return ":".join(
        f"{value:02x}"
        for value in (0x02, digest[0], digest[1], digest[2], digest[3], digest[4])
    )


def set_s3_efuse_mac(efuse: bytearray, mac: str) -> None:
    raw = bytes.fromhex(mac.replace(":", ""))
    if len(raw) != 6 or len(efuse) < 30:
        raise ValueError("ESP32-S3 eFuse MAC fixture is invalid")
    efuse[24:30] = raw[::-1]


def set_esp32_efuse_mac(efuse: bytearray, mac: str) -> None:
    raw = bytes.fromhex(mac.replace(":", ""))
    if len(raw) != 6 or len(efuse) < 10:
        raise ValueError("ESP32 eFuse MAC fixture is invalid")
    efuse[4:10] = raw


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


def parse_capture_pcap(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ServiceError(
            "invalid_network",
            "network.capture_pcap must be a boolean",
            400,
        )
    return value


def parse_network_policy(
    value: Any,
    *,
    implicit_endpoints: tuple[EgressEndpoint, ...] = (),
) -> NetworkPolicy:
    try:
        policy = NetworkPolicy.from_mapping(value)
        if policy.egress == "allowlist" and implicit_endpoints:
            policy = policy.with_allowed_endpoints(implicit_endpoints)
        if policy.dns == "controlled" and not policy.allowed_endpoints:
            raise NetworkPolicyError(
                "dns=controlled requires at least one allowed endpoint"
            )
        return policy
    except NetworkPolicyError as error:
        raise ServiceError(
            "invalid_network_policy",
            str(error),
            400,
        ) from error


def parse_dns_cname_records(
    value: Any,
    policy: NetworkPolicy,
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ServiceError(
            "invalid_network",
            "network.cname_records must be an object",
            400,
        )
    if value and (
        policy.egress != "allowlist"
        or policy.dns != "controlled"
    ):
        raise ServiceError(
            "invalid_network",
            "network.cname_records requires egress=allowlist and "
            "dns=controlled",
            400,
        )
    try:
        return validate_cname_record_bindings(
            value,
            policy.allowed_hosts,
            policy.allowed_hosts,
            policy.allowed_domains,
        )
    except SandboxError as error:
        raise ServiceError(
            "invalid_network",
            str(error),
            400,
        ) from error


def require_allowlist_http_fixture(
    profile: str,
    policy: NetworkPolicy,
    *,
    http_fixture: bool = True,
) -> None:
    if policy.egress != "allowlist" or (
        http_fixture and profile in UNIFIED_HTTP_PORTS
    ):
        return
    controlled_names = policy.allowed_hosts or policy.allowed_domains
    if controlled_names and policy.dns == "controlled":
        slirp_host = ipaddress.ip_address("10.0.2.2")
        if not any(
            endpoint_contains_address(endpoint, slirp_host)
            for endpoint in policy.allowed_endpoints
        ):
            raise ServiceError(
                "allowlist_not_supported",
                "dns=controlled Host/domain allowlists resolve to "
                "10.0.2.2 and require a controlled HTTP profile or an "
                "exact 10.0.2.2 endpoint",
                400,
            )
        return
    if policy.allowed_endpoints:
        return
    raise ServiceError(
        "allowlist_not_supported",
        "network.policy.egress=allowlist requires allowed_endpoints or a "
        "profile with a controlled HTTP fixture",
        400,
    )


def implicit_allowlist_endpoints(
    profile: str,
) -> tuple[EgressEndpoint, ...]:
    port = UNIFIED_HTTP_PORTS.get(profile)
    if port is None:
        return ()
    return (EgressEndpoint(protocol="tcp", address="10.0.2.2", port=port),)


def require_network_capabilities(policy: NetworkPolicy) -> None:
    if policy.isolation != "namespace":
        return
    if namespace_capability()["status"] != "PASS":
        raise ServiceError(
            "network_isolation_unavailable",
            "network namespace isolation is unavailable on this runtime",
            503,
        )
    if policy.egress != "allowlist":
        return
    capability = egress_capability(
        require_gateway=requires_external_gateway(
            policy.allowed_endpoints
        ),
        require_ipv6=requires_external_ipv6(policy.allowed_endpoints),
    )
    if capability["status"] != "PASS":
        raise ServiceError(
            "egress_policy_unavailable",
            "; ".join(capability["errors"]),
            503,
        )


def qemu_pcap_options(path: Path, *, netdev: str = "wifi0") -> list[str]:
    return [
        "-object",
        (
            f"filter-dump,id=netdump,netdev={netdev},"
            f"file={path},maxlen=262144"
        ),
    ]


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON without exposing a partially-written session record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    os.replace(temporary, path)


def inspect_process(pid: int) -> dict[str, Any]:
    """Return a PID identity snapshot suitable for safe re-attach."""

    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return {"exists": False, "start_token": None, "command": None}
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return {"exists": False, "start_token": None, "command": None}

    def probe(field: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    "ps",
                    "-ww",
                    "-p",
                    str(pid),
                    "-o",
                    f"{field}=",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else None

    start_token = probe("lstart")
    command = probe("command")
    return {
        "exists": bool(start_token and command),
        "start_token": start_token,
        "command": command,
    }


class UnifiedHttpFixture:
    """Controlled HTTP endpoint used by a unified board probe."""

    def __init__(
        self,
        log_path: Path,
        body: bytes = b"UNIFIED_STICKS3_OK\n",
        port: int = 18080,
        *,
        seed_requests: list[dict[str, Any]] | None = None,
        generation: int = 1,
    ):
        self.requests: list[dict[str, Any]] = [
            dict(item) for item in (seed_requests or [])
        ]
        self.log_path = log_path
        self.generation = max(1, int(generation))
        self._lock = threading.RLock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                record = {
                    "path": self.path,
                    "host": self.headers.get("Host", ""),
                    "received_at": iso_now(),
                    "fixture_generation": owner.generation,
                }
                with owner._lock:
                    owner.requests.append(record)
                    owner._persist_locked()
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

    def _persist_locked(self) -> None:
        atomic_write_json(self.log_path, self.requests)

    def request_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self.requests]

    def close(self) -> None:
        with self._lock:
            self._persist_locked()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def parse_storage_execution(
    spec: DeviceSpec,
    value: Any,
) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_storage", "storage must be an object", 400)
    unknown = sorted(set(value) - {"sd_image_artifact_id"})
    if unknown:
        raise ServiceError(
            "invalid_storage",
            "unsupported storage fields: " + ", ".join(unknown),
            400,
        )
    artifact_id = value.get("sd_image_artifact_id")
    if not isinstance(artifact_id, str) or not _is_sha256(artifact_id):
        raise ServiceError(
            "invalid_storage",
            "storage.sd_image_artifact_id must be a SHA-256 artifact id",
            400,
        )
    if not spec.has_sd_card:
        raise ServiceError(
            "storage_not_supported",
            f"{spec.id} has no modeled SD-card interface",
            409,
        )
    return {
        "interface": "sdmmc",
        "format": "raw",
        "sd_image_artifact_id": artifact_id,
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
    if not isinstance(artifact_id, str) or not _is_sha256(artifact_id):
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


def resolve_nvs_partition(
    firmware_path: Path,
    *,
    flash_size: int,
    partition_label: str,
) -> dict:
    data = firmware_path.read_bytes()
    table = parse_partition_table(data, image_size=flash_size)
    if not table["valid"]:
        raise ServiceError(
            "invalid_firmware_partition_table",
            "cannot apply NVS fixture: "
            + "; ".join(table.get("errors", ["invalid partition table"])),
            409,
        )
    matches = [
        partition
        for partition in table["partitions"]
        if partition["type"] == 1
        and partition["subtype"] == 2
        and partition["label"] == partition_label
    ]
    if not matches:
        raise ServiceError(
            "nvs_partition_not_found",
            f"firmware has no NVS partition labelled {partition_label!r}",
            409,
        )
    return dict(matches[0])


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


def native_vhci_gdb_path() -> Path:
    raw_path = os.environ.get("M5_XTENSA_GDB")
    if raw_path:
        path = Path(raw_path)
    else:
        candidates = sorted(
            (
                Path.home()
                / ".espressif/tools/xtensa-esp-elf-gdb"
            ).glob("*/xtensa-esp-elf-gdb/bin/xtensa-esp32-elf-gdb")
        )
        path = candidates[-1] if candidates else Path()
    if (
        not path
        or not path.is_file()
        or not os.access(path, os.X_OK)
        or not NATIVE_VHCI_GDB_SCRIPT.is_file()
    ):
        raise ServiceError(
            "native_bt_backend_unavailable",
            "native Core2 VHCI requires an executable xtensa GDB and bridge",
            503,
        )
    return path


def parse_qemu_wifi_execution(
    spec: DeviceSpec,
    value: Any,
) -> dict:
    if spec.id == "core2":
        default_profile = CORE2_WIFI_PROFILE
        supported_profile = CORE2_WIFI_PROFILE
        nic = "misc.esp32_wifi"
    elif spec.id == "sticks3":
        default_profile = STICKS3_WIFI_PROFILE
        supported_profile = STICKS3_WIFI_PROFILE
        nic = "misc.esp32s3.wifi"
    elif spec.backend == "qemu-esp32s3":
        default_profile = "generic-observe"
        supported_profile = "generic-observe"
        nic = "misc.esp32s3.wifi"
    else:
        raise ServiceError(
            "qemu_wifi_not_supported",
            (
                "qemu-wifi is supported for Core2, StickS3 and generic "
                "ESP32-S3 observe profiles"
            ),
            409,
        )
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_network", "network must be an object", 400)
    profile = value.get("profile", default_profile)
    if profile != supported_profile:
        raise ServiceError(
            "unsupported_network_profile",
            f"unsupported qemu-wifi profile: {profile!r}",
            400,
        )
    http_fixture = value.get("http_fixture", True)
    if not isinstance(http_fixture, bool):
        raise ServiceError(
            "invalid_network",
            "network.http_fixture must be a boolean",
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
    policy = parse_network_policy(
        value.get("policy"),
        implicit_endpoints=(
            implicit_allowlist_endpoints(profile)
            if http_fixture
            else ()
        ),
    )
    cname_records = parse_dns_cname_records(
        value.get("cname_records"),
        policy,
    )
    require_allowlist_http_fixture(
        profile,
        policy,
        http_fixture=http_fixture,
    )
    require_network_capabilities(policy)
    capture_pcap = parse_capture_pcap(
        value.get("capture_pcap"),
        default=policy.capture_pcap,
    )
    if spec.id == "core2":
        core2_radio_qemu_path()
    security = parse_qemu_wifi_security(value)
    return {
        "profile": profile,
        "net_mode": net_mode,
        "nic": nic,
        **security,
        "expected_markers": expected_markers,
        "attempts": attempts,
        "capture_pcap": capture_pcap,
        "http_fixture": http_fixture,
        "policy": policy.evidence(),
        "cname_records": cname_records,
    }


def parse_qemu_ble_execution(
    spec: DeviceSpec,
    value: Any,
    *,
    runtime: str = QEMU_BLE_RUNTIME,
) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ServiceError("invalid_network", "network must be an object", 400)
    if spec.id == "core2":
        supported_profiles = {
            CORE2_BLE_PROFILE,
            CORE2_HCI_GATT_PROFILE,
            CORE2_UNIFIED_PROFILE,
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
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
    elif spec.id == "stopwatch":
        supported_profiles = {STOPWATCH_UNIFIED_PROFILE}
        default_profile = STOPWATCH_UNIFIED_PROFILE
    elif spec.id == "atoms3r":
        supported_profiles = {ATOMS3R_UNIFIED_PROFILE}
        default_profile = ATOMS3R_UNIFIED_PROFILE
    elif spec.id == "papercolor":
        supported_profiles = {PAPERCOLOR_UNIFIED_PROFILE}
        default_profile = PAPERCOLOR_UNIFIED_PROFILE
    elif spec.id == "papermono":
        supported_profiles = {PAPERMONO_UNIFIED_PROFILE}
        default_profile = PAPERMONO_UNIFIED_PROFILE
    elif spec.id == "stackchan":
        supported_profiles = {STACKCHAN_UNIFIED_PROFILE}
        default_profile = STACKCHAN_UNIFIED_PROFILE
    elif spec.id == "stamplc":
        supported_profiles = {STAMPLC_UNIFIED_PROFILE}
        default_profile = STAMPLC_UNIFIED_PROFILE
    elif spec.id == "nanoc6":
        supported_profiles = {NANOC6_HCI_BLE_PROFILE}
        default_profile = NANOC6_HCI_BLE_PROFILE
    elif spec.id == "nesso-n1":
        supported_profiles = {NESSO_UNIFIED_PROFILE}
        default_profile = NESSO_UNIFIED_PROFILE
    else:
        raise ServiceError(
            (
                "qemu_unified_not_supported"
                if runtime == QEMU_UNIFIED_RUNTIME
                else "qemu_ble_not_supported"
            ),
            f"{runtime} is not supported for this device",
            409,
        )
    profile = value.get("profile", default_profile)
    if runtime == QEMU_UNIFIED_RUNTIME and profile not in SINGLE_GUEST_PROFILES:
        raise ServiceError(
            "qemu_unified_profile_required",
            f"{profile!r} is a radio-specific profile; "
            "runtime=qemu-unified requires a single-guest unified profile",
            400,
        )
    if profile not in supported_profiles:
        raise ServiceError(
            "unsupported_network_profile",
            f"unsupported {runtime} profile: {profile!r}",
            400,
        )
    http_fixture = value.get("http_fixture", True)
    if not isinstance(http_fixture, bool):
        raise ServiceError(
            "invalid_network",
            "network.http_fixture must be a boolean",
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
    elif profile == NANOC6_HCI_BLE_PROFILE and not expected_markers:
        expected_markers = list(NANOC6_HCI_BLE_MARKERS)
    elif profile == NESSO_UNIFIED_PROFILE and not expected_markers:
        expected_markers = list(NESSO_UNIFIED_MARKERS)
    elif profile in UNIFIED_MARKERS and not expected_markers:
        expected_markers = list(UNIFIED_MARKERS[profile])
    elf_artifact_id = value.get("elf_artifact_id")
    if elf_artifact_id is not None and (
        not isinstance(elf_artifact_id, str)
        or not _is_sha256(elf_artifact_id)
    ):
        raise ServiceError(
            "invalid_network",
            "network.elf_artifact_id is invalid",
            400,
        )
    if profile in {
        CORE2_NATIVE_VHCI_PROFILE,
        CORE2_NATIVE_HCI_PROFILE,
    }:
        if not elf_artifact_id:
            raise ServiceError(
                "elf_required",
                f"{profile} requires network.elf_artifact_id",
                400,
            )
    if profile == CORE2_NATIVE_VHCI_PROFILE:
        native_vhci_gdb_path()
    attempts = value.get("attempts", 5)
    if not isinstance(attempts, int) or not 1 <= attempts <= 10:
        raise ServiceError(
            "invalid_network",
            "network.attempts must be an integer from 1 to 10",
            400,
        )
    policy = parse_network_policy(
        value.get("policy"),
        implicit_endpoints=(
            implicit_allowlist_endpoints(profile)
            if http_fixture
            else ()
        ),
    )
    cname_records = parse_dns_cname_records(
        value.get("cname_records"),
        policy,
    )
    require_allowlist_http_fixture(
        profile,
        policy,
        http_fixture=http_fixture,
    )
    require_network_capabilities(policy)
    capture_pcap = parse_capture_pcap(
        value.get("capture_pcap"),
        default=policy.capture_pcap,
    )
    ble_linger_seconds = value.get(
        "ble_linger_seconds",
        20 if profile in UNIFIED_PROFILES else 15,
    )
    if (
        isinstance(ble_linger_seconds, bool)
        or not isinstance(ble_linger_seconds, (int, float))
        or not 0 <= ble_linger_seconds <= MAX_BLE_LINGER_SECONDS
    ):
        raise ServiceError(
            "invalid_network",
            "network.ble_linger_seconds must be from 0 to "
            f"{MAX_BLE_LINGER_SECONDS}",
            400,
        )
    reconnect_cycles = value.get("ble_reconnect_cycles", 1)
    if (
        isinstance(reconnect_cycles, bool)
        or not isinstance(reconnect_cycles, int)
        or not 1 <= reconnect_cycles <= MAX_BLE_RECONNECT_CYCLES
    ):
        raise ServiceError(
            "invalid_network",
            "network.ble_reconnect_cycles must be an integer from 1 to "
            f"{MAX_BLE_RECONNECT_CYCLES}",
            400,
        )
    reconnect_delay = value.get("ble_reconnect_delay_seconds", 2)
    if (
        isinstance(reconnect_delay, bool)
        or not isinstance(reconnect_delay, (int, float))
        or not 0 <= reconnect_delay <= MAX_BLE_RECONNECT_DELAY_SECONDS
    ):
        raise ServiceError(
            "invalid_network",
            "network.ble_reconnect_delay_seconds must be from 0 to "
            f"{MAX_BLE_RECONNECT_DELAY_SECONDS}",
            400,
        )
    post_pass_continuity = value.get("ble_post_pass_continuity", False)
    if not isinstance(post_pass_continuity, bool):
        raise ServiceError(
            "invalid_network",
            "network.ble_post_pass_continuity must be a boolean",
            400,
        )
    ble_peer_role=value.get("ble_peer_role","central")
    if not isinstance(ble_peer_role,str) or ble_peer_role not in {"central","peripheral"}:
        raise ServiceError("invalid_network","network.ble_peer_role must be central or peripheral",400)
    if ble_peer_role=="peripheral" and spec.id not in {"cores3","cardputer-adv"}:
        raise ServiceError("invalid_network","peripheral BLE peer is admitted only for CoreS3 and Cardputer-ADV",400)
    if ble_peer_role=="peripheral" and (reconnect_cycles!=1 or post_pass_continuity):
        raise ServiceError("invalid_network","peripheral BLE peer supports one exchange and no post-pass continuity",400)
    if post_pass_continuity and (
        profile
        not in {
            CORE2_HCI_GATT_PROFILE,
            NANOC6_HCI_BLE_PROFILE,
            NESSO_UNIFIED_PROFILE,
            *UNIFIED_PROFILES,
        }
        or policy.isolation != "trusted-host"
    ):
        raise ServiceError(
            "invalid_network",
            "network.ble_post_pass_continuity requires a BLE profile "
            "with trusted-host isolation",
            400,
        )
    if spec.id == "core2":
        core2_radio_qemu_path()
    security = (
        parse_qemu_wifi_security(value)
        if spec.backend == "qemu-esp32s3"
        else {}
    )
    if (
        profile in {
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
        }
        and policy.isolation == "namespace"
    ):
        raise ServiceError(
            "native_bt_isolation_unavailable",
            "native Core2 BLE currently requires trusted-host isolation",
            409,
        )
    return {
        "profile": profile,
        **security,
        "expected_markers": expected_markers,
        "attempts": attempts,
        "capture_pcap": capture_pcap,
        "http_fixture": http_fixture,
        "ble_linger_seconds": float(ble_linger_seconds),
        "ble_reconnect_cycles": reconnect_cycles,
        "ble_reconnect_delay_seconds": float(reconnect_delay),
        "ble_post_pass_continuity": post_pass_continuity,
        "ble_peer_role":ble_peer_role,
        "policy": policy.evidence(),
        "cname_records": cname_records,
        "elf_artifact_id": elf_artifact_id,
        "nic": (
            "misc.esp32_wifi"
            if spec.id == "core2"
            else "misc.esp32c6.wifi"
            if spec.id in {"nanoc6", "nesso-n1"}
            else "misc.esp32s3.wifi"
        ),
        "ble_name": (
            UNIFIED_BLE_IDENTITIES["core2"][0]
            if profile in {
                CORE2_UNIFIED_PROFILE,
                CORE2_NATIVE_VHCI_PROFILE,
                CORE2_NATIVE_HCI_PROFILE,
            }
            else "M5-CORE2-HCI"
            if spec.id == "core2"
            else NANOC6_BLE_IDENTITY[0]
            if spec.id == "nanoc6"
            else NESSO_BLE_IDENTITY[0]
            if spec.id == "nesso-n1"
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


def _normalize_management_binding(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"preview_id", "owner_epoch", "expected_reference_sha256"}:
        raise ServiceError("invalid_preview_binding", "a complete internal Preview binding is required", 400)
    if any(not isinstance(value[key], str) or not 1 <= len(value[key]) <= 128
           or any(ord(char) < 32 for char in value[key]) for key in ("preview_id", "owner_epoch")):
        raise ServiceError("invalid_preview_binding", "invalid internal Preview identity", 400)
    if not isinstance(value["expected_reference_sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", value["expected_reference_sha256"]) is None:
        raise ServiceError("invalid_preview_binding", "a lowercase reference SHA256 pin is required", 400)
    return dict(value)


def _require_live_package_entrypoint(revision: dict, loader_capabilities: dict | None = None) -> None:
    # Check before allocating an execution or interrupting its predecessor.
    # Immutable storage admission does not imply a loader in the guest firmware.
    entrypoint = revision.get("entrypoint", "main.py")
    if entrypoint != "main.py" and not (entrypoint == "main.mpy" and main_loader_verified(loader_capabilities)):
        raise ServiceError(
            "program_mpy_entrypoint_unsupported",
            "main.mpy requires this session's verified bytecode run-as-main loader; wait for its bootstrap probe or use a compatible base",
            409,
        )


def _validate_checkpoint_bytecode(files: dict[str, bytes]) -> None:
    """Reject known-invalid/native containers without touching the guest.

    This is host format admission only. Deployment still compares bytecode
    version and small-int requirements with the actual guest capabilities.
    """
    for path, data in files.items():
        if not path.lower().endswith(".mpy"):
            continue
        if len(data) < 4 or data[0] != ord("M"):
            raise ServiceError("program_mpy_invalid", "invalid .mpy header", 409)
        if data[2] != 0:
            raise ServiceError(
                "program_mpy_native_unsupported", "only bytecode-only .mpy dependencies are admitted", 409,
            )
        try:
            validate_bytecode(data)
        except MPYBytecodeError as error:
            raise ServiceError(
                "program_mpy_invalid", "invalid or unsupported bytecode-only .mpy container", 409,
            ) from error


class SessionCancelled(ServiceError):
    """A lifecycle transaction was superseded by an explicit stop request."""

    def __init__(self):
        super().__init__("session_stopping", "session stop was requested", 409)


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

    @property
    def has_display(self) -> bool:
        display = self.display or {}
        return bool(display.get("width") and display.get("height"))

    @property
    def has_sd_card(self) -> bool:
        return "sd" in self.peripherals

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
        if self.flash_emulator is not None and not self.flash_emulator.is_file():
            missing.append(self.flash_emulator)
        return missing


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
                configured_emulator = os.environ.get("M5_SERVICE_ESP_EMU", "").strip()
                flash_emulator = Path(configured_emulator) if configured_emulator else ROOT / ".work/bin/esp-emu"
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
                    f"{device_id} has invalid network_status {network_status!r}",
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
            if device_id == "cores3" and network_chip:
                network_profiles.insert(0, CORES3_UNIFIED_PROFILE)
            if device_id == "cardputer-adv" and network_chip:
                network_profiles.insert(0, CARDPUTER_ADV_UNIFIED_PROFILE)
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
            peripherals=list(profile.get("peripherals", [])),
            reference_path=reference,
            qemu=qemu,
            rom_dir=rom_dir,
            efuse_driver=backend.get("efuse_driver"),
            memory=SERVICE_MEMORY_OVERRIDES.get(device_id, row.get("memory")),
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

    def _upload_dir(self) -> Path:
        return self.root / ".uploads"

    def _upload_meta(self, upload_id: str) -> Path:
        return self._upload_dir() / f"{upload_id}.json"

    def _upload_part(self, upload_id: str) -> Path:
        return self._upload_dir() / f"{upload_id}.part"

    def _load_upload(self, upload_id: str) -> dict:
        if (
            not isinstance(upload_id, str)
            or len(upload_id) != 32
            or any(char not in "0123456789abcdef" for char in upload_id)
        ):
            raise ServiceError("unknown_upload", "invalid upload id", 404)
        meta = self._upload_meta(upload_id)
        if not meta.is_file():
            raise ServiceError(
                "unknown_upload", f"unknown upload: {upload_id}", 404
            )
        try:
            return json.loads(meta.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ServiceError(
                "invalid_upload_state",
                f"upload metadata is unreadable: {upload_id}",
                409,
            ) from error

    def _save_upload(self, record: dict) -> None:
        upload_dir = self._upload_dir()
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = self._upload_meta(record["upload_id"])
        temp = upload_dir / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp.open("w") as sink:
                sink.write(
                    json.dumps(record, ensure_ascii=False, indent=2) + "\n"
                )
                sink.flush()
                os.fsync(sink.fileno())
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)

    def prune_uploads(self, *, now: float, grace_seconds: float) -> dict:
        """Remove abandoned staging data while preserving recent resumable state."""
        upload_dir = self._upload_dir()
        if not upload_dir.is_dir():
            return {"files_removed": 0, "bytes_removed": 0}
        cutoff = float(now) - max(0.0, float(grace_seconds))
        removed: list[Path] = []
        with self._lock:
            metadata = {
                path.stem: path
                for path in upload_dir.glob("*.json")
                if path.is_file()
            }
            parts = {
                path.stem: path
                for path in upload_dir.glob("*.part")
                if path.is_file()
            }
            referenced_parts: set[str] = set()
            for upload_id, meta in metadata.items():
                try:
                    age_is_old = meta.stat().st_mtime < cutoff
                except OSError:
                    continue
                if not age_is_old:
                    continue
                part = parts.get(upload_id)
                if part is not None:
                    referenced_parts.add(upload_id)
                    removed.append(part)
                removed.append(meta)
            for upload_id, part in parts.items():
                if upload_id in referenced_parts:
                    continue
                try:
                    if part.stat().st_mtime < cutoff:
                        removed.append(part)
                except OSError:
                    continue
            for temp in upload_dir.glob(".*.tmp"):
                try:
                    if temp.is_file() and temp.stat().st_mtime < cutoff:
                        removed.append(temp)
                except OSError:
                    continue
            bytes_removed = 0
            unique_removed = {path for path in removed if path.exists()}
            removed_count = 0
            for path in unique_removed:
                try:
                    size = path.stat().st_size
                    path.unlink(missing_ok=True)
                    removed_count += 1
                    bytes_removed += size
                except OSError:
                    continue
        return {
            "files_removed": removed_count,
            "bytes_removed": bytes_removed,
        }

    def begin_upload(
        self,
        *,
        expected_size: int,
        expected_sha256: str,
        name: str = "",
        content_type: str = "application/octet-stream",
    ) -> dict:
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size <= 0
        ):
            raise ServiceError(
                "invalid_upload", "expected_size must be positive", 400
            )
        if expected_size > MAX_ARTIFACT_BYTES:
            raise ServiceError(
                "artifact_too_large",
                f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes",
                413,
            )
        if not _is_sha256(expected_sha256):
            raise ServiceError(
                "invalid_upload", "expected_sha256 must be a SHA256", 400
            )
        upload_id = uuid.uuid4().hex
        record = {
            "upload_id": upload_id,
            "status": "uploading",
            "expected_size": expected_size,
            "expected_sha256": expected_sha256.lower(),
            "received_bytes": 0,
            "chunks": 0,
            "name": name or f"artifact-{upload_id[:12]}.bin",
            "content_type": content_type or "application/octet-stream",
            "created_at": iso_now(),
            "updated_at": iso_now(),
            "artifact_id": None,
        }
        with self._lock:
            self._upload_dir().mkdir(parents=True, exist_ok=True)
            self._upload_part(upload_id).write_bytes(b"")
            self._save_upload(record)
        return record

    def append_upload_chunk(
        self,
        upload_id: str,
        *,
        offset: int,
        data: bytes,
        sha256: str,
    ) -> dict:
        if not data:
            raise ServiceError("empty_chunk", "chunk must not be empty", 400)
        if len(data) > MAX_ARTIFACT_CHUNK_BYTES:
            raise ServiceError(
                "chunk_too_large",
                f"chunk exceeds {MAX_ARTIFACT_CHUNK_BYTES} bytes",
                413,
            )
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ServiceError("invalid_offset", "offset must be non-negative", 400)
        if not _is_sha256(sha256):
            raise ServiceError(
                "invalid_chunk", "chunk SHA256 header is required", 400
            )
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(actual_sha256, sha256.lower()):
            raise ServiceError(
                "chunk_hash_mismatch", "chunk SHA256 does not match body", 409
            )
        with self._lock:
            record = self._load_upload(upload_id)
            if record.get("status") != "uploading":
                raise ServiceError(
                    "upload_closed", "upload is not accepting chunks", 409
                )
            received = int(record.get("received_bytes", 0))
            expected_size = int(record["expected_size"])
            if offset != received:
                raise ServiceError(
                    "invalid_chunk_offset",
                    f"expected offset {received}, got {offset}",
                    409,
                )
            if received + len(data) > expected_size:
                raise ServiceError(
                    "chunk_exceeds_artifact",
                    "chunk would exceed expected_size",
                    413,
                )
            part = self._upload_part(upload_id)
            if not part.is_file():
                raise ServiceError(
                    "upload_data_missing",
                    "upload staging file is missing",
                    409,
                )
            if part.stat().st_size != received:
                raise ServiceError(
                    "upload_data_mismatch",
                    (
                        f"upload staging file has {part.stat().st_size} bytes, "
                        f"metadata records {received}"
                    ),
                    409,
                )
            try:
                with part.open("r+b") as sink:
                    sink.seek(received)
                    written = sink.write(data)
                    if written != len(data):
                        raise OSError(
                            f"short chunk write: {written} of {len(data)} bytes"
                        )
                    sink.flush()
                    os.fsync(sink.fileno())
                record["received_bytes"] = received + len(data)
                record["chunks"] = int(record.get("chunks", 0)) + 1
                record["updated_at"] = iso_now()
                self._save_upload(record)
            except Exception as error:
                try:
                    with part.open("r+b") as sink:
                        sink.truncate(received)
                        sink.flush()
                        os.fsync(sink.fileno())
                except OSError as rollback_error:
                    raise ServiceError(
                        "upload_rollback_failed",
                        "failed to restore the last committed upload offset",
                        500,
                    ) from rollback_error
                if isinstance(error, ServiceError):
                    raise
                raise ServiceError(
                    "upload_write_failed",
                    "artifact chunk could not be committed",
                    500,
                ) from error
            return {
                **record,
                "next_offset": record["received_bytes"],
            }

    def complete_upload(self, upload_id: str) -> dict:
        with self._lock:
            record = self._load_upload(upload_id)
            if record.get("status") == "completed":
                return self.get(str(record["artifact_id"]))
            if record.get("status") != "uploading":
                raise ServiceError(
                    "upload_closed", "upload cannot be completed", 409
                )
            part = self._upload_part(upload_id)
            if not part.is_file():
                raise ServiceError(
                    "upload_data_missing", "upload staging file is missing", 409
                )
            received = int(record.get("received_bytes", 0))
            if received != int(record["expected_size"]):
                raise ServiceError(
                    "incomplete_upload",
                    (
                        f"received {received} of "
                        f"{record['expected_size']} bytes"
                    ),
                    409,
                )
            digest = hashlib.sha256()
            with part.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            artifact_id = digest.hexdigest()
            if not hmac.compare_digest(
                artifact_id, str(record["expected_sha256"])
            ):
                raise ServiceError(
                    "artifact_hash_mismatch",
                    "completed artifact SHA256 does not match expected_sha256",
                    409,
                )
            data_path = self._data(artifact_id)
            if data_path.exists():
                part.unlink(missing_ok=True)
            else:
                part.replace(data_path)
            artifact = {
                "artifact_id": artifact_id,
                "sha256": artifact_id,
                "size": received,
                "name": record["name"],
                "content_type": record["content_type"],
                "created_at": iso_now(),
            }
            self._meta(artifact_id).write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2) + "\n"
            )
            record["status"] = "completed"
            record["artifact_id"] = artifact_id
            record["updated_at"] = iso_now()
            self._save_upload(record)
            return artifact

    def get_upload(self, upload_id: str) -> dict:
        with self._lock:
            return self._load_upload(upload_id)

    def abort_upload(self, upload_id: str) -> dict:
        with self._lock:
            record = self._load_upload(upload_id)
            if record.get("status") == "completed":
                raise ServiceError(
                    "upload_closed", "completed upload cannot be aborted", 409
                )
            self._upload_part(upload_id).unlink(missing_ok=True)
            self._upload_meta(upload_id).unlink(missing_ok=True)
            return {
                "upload_id": upload_id,
                "aborted": True,
                "received_bytes": record.get("received_bytes", 0),
            }

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

    @staticmethod
    def _read_uiflow_base_file(path: Path, limit: int) -> bytes:
        """Read one bounded regular-file snapshot without following symlinks."""
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                    raise ServiceError("uiflow_base_integrity_error", "base storage must contain a bounded regular file", 409)
                with os.fdopen(descriptor, "rb") as stream:
                    descriptor = None
                    data = stream.read(limit + 1)
                if len(data) != info.st_size:
                    raise ServiceError("uiflow_base_integrity_error", "base storage changed while being read", 409)
                return data
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        except OSError as error:
            raise ServiceError("uiflow_base_unreadable", "base storage is unavailable or is not a regular file", 409) from error

    @staticmethod
    def _uiflow_family_markers(app_bytes: bytes) -> list[str]:
        """Return admitted UIFlow2 build fingerprints without assuming one casing."""
        markers = ("_uiflow_run_main", "UIFLOW2", "UiFlow2", "uiflow2.m5stack.com")
        return [marker for marker in markers if marker.encode("ascii") in app_bytes]

    def _explicit_uiflow_base(self, spec: DeviceSpec, payload: dict) -> tuple[bytes, dict, dict]:
        """Re-admit an immutable manifest image for this source composition.

        The pin covers flash-sized stored bytes, which can differ from the
        original upload after normalization/padding. Neither caller family
        labels nor a mountable LittleFS alone establish UIFlow compatibility.
        """
        base_id = payload["base_firmware_id"]
        if not isinstance(base_id, str) or not _is_sha256(base_id):
            raise ServiceError("invalid_uiflow_request", "base_firmware_id must be a stored firmware ID", 400)
        expected = payload.get("expected_base_sha256")
        if expected is None:
            raise ServiceError("uiflow_base_binding_required", "an explicit base requires expected_base_sha256 of the normalized stored image", 400)
        if not isinstance(expected, str) or not _is_sha256(expected):
            raise ServiceError("invalid_uiflow_base", "expected_base_sha256 must be a lowercase SHA256", 400)
        with self._lock:
            if not self._meta(base_id).exists() and not self._meta(base_id).is_symlink():
                raise ServiceError("unknown_firmware", "base firmware is not stored", 404)
            try:
                record = json.loads(self._read_uiflow_base_file(self._meta(base_id), 8 * 1024 * 1024))
            except (ValueError, UnicodeError) as error:
                raise ServiceError("uiflow_base_integrity_error", "base metadata is invalid", 409) from error
            base = self._read_uiflow_base_file(self._data(base_id), spec.flash_size)
        actual_sha = hashlib.sha256(base).hexdigest()
        if actual_sha != expected:
            raise ServiceError("uiflow_base_hash_mismatch", "expected_base_sha256 must match the normalized stored image bytes", 409)
        if not isinstance(record, dict) or any(record.get(key) != base_id for key in ("firmware_id", "sha256")) or actual_sha != base_id:
            raise ServiceError("uiflow_base_integrity_error", "stored base identity differs from its bytes", 409)
        if record.get("device_id") != spec.id:
            raise ServiceError("firmware_device_mismatch", "base firmware belongs to another device", 409)
        if record.get("flash_size") != spec.flash_size or record.get("size") != len(base) or len(base) != spec.flash_size:
            raise ServiceError("flash_size_mismatch", "base firmware must match the target normalized flash size", 409)
        source = record.get("source")
        if record.get("kind") == "manifest" and isinstance(source, dict) and source.get("kind") == "manifest":
            manifest = record.get("manifest")
            recorded_manifest_ids = (record.get("manifest_id"), source.get("manifest_id"))
            recorded_artifact_id = source.get("artifact_id")
        else:
            raise ServiceError("uiflow_base_not_admitted", "explicit bases require the existing firmware-manifest intake", 409)
        try:
            structure_errors = validate_manifest_structure(manifest)
        except (TypeError, ValueError) as error:
            raise ServiceError("invalid_firmware_manifest", "stored base manifest is invalid", 409) from error
        if structure_errors:
            raise ServiceError("invalid_firmware_manifest", "stored base manifest is invalid", 409)
        manifest_id = canonical_json_sha256(manifest_identity_payload(manifest))
        if manifest.get("manifest_id") != manifest_id or any(value != manifest_id for value in recorded_manifest_ids):
            raise ServiceError("firmware_manifest_id_mismatch", "stored base manifest identity differs", 409)
        target, artifact = manifest["target"], manifest["artifact"]
        if target.get("psram_size") is not None and (type(target["psram_size"]) is not int or target["psram_size"] < 0):
            raise ServiceError("invalid_firmware_manifest", "base PSRAM requirement must be an integer or null", 409)
        artifact_id = artifact.get("artifact_id", artifact.get("sha256"))
        artifact_size = artifact["size"]
        if (
            artifact.get("kind") != "merged-flash" or recorded_artifact_id != artifact_id
            or artifact_id != artifact.get("sha256") or not 0 < artifact_size <= len(base)
            or hashlib.sha256(base[:artifact_size]).hexdigest() != artifact["sha256"]
            or any(byte != 0xff for byte in base[artifact_size:])
        ):
            raise ServiceError("uiflow_base_integrity_error", "base manifest artifact differs from normalized stored bytes", 409)
        if manifest.get("device_id") not in (None, spec.id) or target["flash_size"] != spec.flash_size or target.get("chip_id") != expected_chip_id(spec.soc):
            raise ServiceError("uiflow_base_not_admitted", "base manifest target differs from the device", 409)
        profile = load_device_profile(spec.id)
        compatibility = validate_capabilities(manifest, profile) if profile is not None else None
        if compatibility is None or compatibility["status"] != "PASS" or manifest.get("validation", {}).get("status") != "PASS" or manifest.get("validation", {}).get("errors"):
            raise ServiceError("unsupported_firmware_capability", "base manifest requirements are not admitted by the target profile", 409,
                               issues=(compatibility or {}).get("errors", []) + manifest.get("validation", {}).get("errors", []))
        table = parse_partition_table(base, image_size=spec.flash_size)
        if not table["valid"] or table["warnings"] or any(part["flags"] != 0 for part in table["partitions"]):
            raise ServiceError("uiflow_base_not_admitted", "base requires an unflagged valid partition table", 409)
        declared_table = target.get("partition_table") or {}
        if not isinstance(declared_table, dict) or declared_table.get("offset") != table["offset"] or declared_table.get("partitions") != table["partitions"]:
            raise ServiceError("uiflow_base_integrity_error", "base manifest partition layout differs from actual bytes", 409)
        boot_image = analyze_esp_image(base, 0)
        bootloader_absent = not boot_image["valid"] and spec.id == "core2"
        if not boot_image["valid"] and not bootloader_absent:
            raise ServiceError("uiflow_base_not_admitted", "base bootloader image is invalid", 409)
        images = [] if bootloader_absent else [(boot_image, 0x8000)]
        families = []
        for part in table["partitions"]:
            if part["type"] != 0 or not any(byte != 0xff for byte in base[part["offset"]:part["offset"] + 32]):
                continue
            end = part["offset"] + part["size"]
            image = analyze_esp_image(base, part["offset"])
            images.append((image, end))
            descriptor = find_app_descriptor(base, part["offset"], min(image.get("image_end", end), end))
            app_bytes = base[part["offset"]:min(image.get("image_end", end), end)]
            family_markers = self._uiflow_family_markers(app_bytes)
            if (
                not descriptor
                or descriptor.get("project_name") != "micropython"
                or not re.match(r"[Vv]2\.", descriptor.get("version", ""))
                or "_uiflow_run_main" not in family_markers
                or not any(marker != "_uiflow_run_main" for marker in family_markers)
            ):
                raise ServiceError("uiflow_base_not_admitted", "base application lacks the supported UIFlow2 compatibility fingerprint", 409)
            if target.get("application") != descriptor:
                raise ServiceError("uiflow_base_integrity_error", "base application descriptor differs from the manifest", 409)
            families.append({"offset": part["offset"], "project_name": descriptor["project_name"],
                             "version": descriptor["version"], "family_markers": family_markers})
        if not families or any(not image["valid"] or image.get("chip_id") != expected_chip_id(spec.soc) or image.get("image_end", end + 1) > end for image, end in images):
            raise ServiceError("uiflow_base_not_admitted", "base boot/application image is invalid or targets another chip", 409)
        signatures = [detect_secure_boot_v2_signature(base, image, region_end=end) for image, end in images]
        if any(item["status"] != "not-found" or item.get("candidate_count") for item in signatures):
            raise ServiceError("uiflow_base_not_admitted", "signed or invalid secure-boot images cannot be used for UIFlow source composition", 409)
        provenance = {
            "kind": "stored-manifest", "manifest_id": manifest_id,
            "stored_sha256": actual_sha, "stored_size": len(base),
            "pin_scope": "normalized-stored-flash-image",
            "artifact_id": artifact_id, "artifact_sha256": artifact["sha256"], "artifact_size": artifact_size,
            "artifact_source_sha256": artifact.get("source_sha256"),
            "compatibility": compatibility,
            "family": {"classification": "STATIC_COMPATIBILITY_FINGERPRINT_NOT_AUTHENTICATION", "applications": families,
                       "markers": family_markers,
                       "bootloader_region": "absent-known-core2-app-only-image" if bootloader_absent else "present",
                       "runtime": "NOT RUN"},
        }
        return base, manifest, provenance

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

        if kind == "uiflow":
            allowed = {"kind", "device_id", "files", "expected_base_sha256", "base_firmware_id"}
            if set(payload) - allowed:
                raise ServiceError("invalid_uiflow_request", "unknown UIFlow source fields", 400)
            if device_id not in LIVE_PROGRAM_DEVICES:
                raise ServiceError(
                    "unsupported_uiflow_device",
                    "UIFlow source intake requires an admitted UIFlow2 QEMU device",
                    409,
                )
            base_manifest = base_provenance = None
            explicit_base = "base_firmware_id" in payload
            if explicit_base:
                base, base_manifest, base_provenance = self._explicit_uiflow_base(spec, payload)
            elif not spec.reference_path or not spec.reference_path.is_file():
                raise ServiceError("reference_firmware_missing", "cached UIFlow2 reference is required", 409)
            try:
                if not explicit_base:
                    base = spec.reference_path.read_bytes()
                composed, source_metadata = build_uiflow_source_image(
                    base, spec.flash_size, payload.get("files"),
                    expected_base_sha256=payload.get("expected_base_sha256"),
                )
            except UIFlowSourceError as error:
                raise ServiceError(error.code, error.message, error.status) from error
            except OSError as error:
                raise ServiceError("reference_firmware_unreadable", "cannot read cached UIFlow2 reference", 503) from error
            source_bytes = json.dumps(
                payload["files"], ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            if hashlib.sha256(source_bytes).hexdigest() != source_metadata["source_sha256"]:
                raise ServiceError("uiflow_source_integrity_error", "source binding differs", 500)
            image[:] = composed
            intervals.append((0, len(composed)))
            if explicit_base:
                source_metadata = {**source_metadata, "base_firmware_id": payload["base_firmware_id"],
                                   "base_provenance": base_provenance}
            # Delay artifact publication until the firmware's CAS provenance
            # is checked under the store lock. Rejected aliases publish nothing.
            source = {"kind": "uiflow", "artifact_id": source_metadata["source_sha256"], "metadata": source_metadata}
        elif kind == "merged":
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
        elif kind == "manifest":
            manifest = payload.get("manifest")
            structure_errors = validate_manifest_structure(manifest)
            if structure_errors:
                raise ServiceError(
                    "invalid_firmware_manifest",
                    "; ".join(structure_errors),
                    400,
                )
            manifest_device = manifest.get("device_id")
            if manifest_device not in {None, device_id}:
                raise ServiceError(
                    "firmware_device_mismatch",
                    (
                        f"manifest targets {manifest_device!r}, "
                        f"not {device_id!r}"
                    ),
                    409,
                )
            manifest_id = manifest.get("manifest_id")
            if manifest_id:
                expected_manifest_id = canonical_json_sha256(
                    manifest_identity_payload(manifest)
                )
                if manifest_id != expected_manifest_id:
                    raise ServiceError(
                        "firmware_manifest_id_mismatch",
                        "manifest_id does not match canonical manifest content",
                        409,
                    )
            artifact_record = manifest["artifact"]
            if artifact_record.get("kind") != "merged-flash":
                raise ServiceError(
                    "unsupported_manifest_artifact",
                    (
                        "Device Service manifest creation currently "
                        "requires a normalized merged-flash artifact"
                    ),
                    400,
                )
            artifact_id = artifact_record.get("artifact_id")
            if not artifact_id:
                artifact_id = artifact_record.get("sha256")
            data = self.artifacts.read(artifact_id)
            data_sha256 = hashlib.sha256(data).hexdigest()
            if data_sha256 != artifact_record.get("sha256"):
                raise ServiceError(
                    "firmware_sha256_mismatch",
                    "manifest artifact hash does not match uploaded artifact",
                    409,
                )
            if len(data) != artifact_record.get("size"):
                raise ServiceError(
                    "firmware_size_mismatch",
                    "manifest artifact size does not match uploaded artifact",
                    409,
                )
            if manifest["target"]["flash_size"] != spec.flash_size:
                raise ServiceError(
                    "flash_size_mismatch",
                    (
                        f"manifest flash size {manifest['target']['flash_size']} "
                        f"does not match device flash {spec.flash_size}"
                    ),
                    409,
                )
            if len(data) > spec.flash_size:
                raise ServiceError(
                    "firmware_too_large",
                    f"firmware is {len(data)} bytes; device flash is {spec.flash_size}",
                    413,
                )
            profile = load_device_profile(device_id)
            if profile is None:
                raise ServiceError(
                    "unknown_device",
                    f"no compatibility profile for {device_id}",
                    400,
                )
            compatibility = validate_capabilities(manifest, profile)
            manifest_errors = list(
                manifest.get("validation", {}).get("errors", [])
            )
            if (
                compatibility["status"] != "PASS"
                or manifest.get("validation", {}).get("status") != "PASS"
            ):
                raise ServiceError(
                    "unsupported_firmware_capability",
                    "firmware requires capabilities unavailable in the target profile",
                    409,
                    issues=manifest_errors + compatibility["errors"],
                )
            image[: len(data)] = data
            intervals.append((0, len(data)))
            source = {
                "kind": "manifest",
                "manifest_id": manifest.get("manifest_id"),
                "artifact_id": artifact_id,
                "compatibility": compatibility,
            }
        else:
            raise ServiceError(
                "unsupported_firmware_kind",
                "kind must be 'merged', 'segmented', 'manifest' or 'uiflow'",
                400,
            )

        if not intervals:
            raise ServiceError("empty_firmware", "firmware has no data", 400)
        image_bytes = bytes(image)
        firmware_id = hashlib.sha256(image_bytes).hexdigest()
        if kind == "uiflow" and base_manifest is not None and firmware_id == payload["base_firmware_id"]:
            raise ServiceError("uiflow_source_context_conflict", "source composition must not replace its base manifest context", 409)
        record = {
            "firmware_id": firmware_id,
            "sha256": firmware_id,
            "device_id": device_id,
            "flash_size": spec.flash_size,
            "size": len(image_bytes),
            "kind": kind,
            "source": source,
            **({"base_manifest": base_manifest} if kind == "uiflow" and base_manifest is not None else {}),
            **(
                {
                    "manifest": manifest,
                    "manifest_id": manifest.get("manifest_id"),
                }
                if kind == "manifest"
                else {}
            ),
            "header_magic": image_bytes[0],
            "created_at": iso_now(),
        }
        with self._lock:
            meta_path = self._meta(firmware_id)
            if meta_path.exists() or meta_path.is_symlink():
                try:
                    existing = json.loads(self._read_uiflow_base_file(meta_path, 8 * 1024 * 1024))
                except (ServiceError, ValueError, UnicodeError) as error:
                    raise ServiceError("uiflow_source_context_conflict", "existing firmware provenance cannot be safely compared", 409) from error
                if not isinstance(existing, dict):
                    raise ServiceError("uiflow_source_context_conflict", "existing firmware provenance cannot be safely compared", 409)
                if "base_manifest" in existing or "base_manifest" in record:
                    context_keys = ("kind", "device_id", "source", "base_manifest")
                    old_context = {key: existing[key] for key in context_keys if key in existing}
                    new_context = {key: record[key] for key in context_keys if key in record}
                    # Public re-import regenerates only this non-semantic
                    # timestamp. Keep every other manifest/source field exact.
                    for context in (old_context, new_context):
                        if isinstance(context.get("base_manifest"), dict):
                            context["base_manifest"] = context["base_manifest"].copy()
                            context["base_manifest"].pop("created_at", None)
                    if old_context != new_context:
                        raise ServiceError("uiflow_source_context_conflict", "firmware bytes already have a different source or base-manifest context", 409)
            if kind == "uiflow":
                self.artifacts.create(
                    source_bytes, name=f"{device_id}-uiflow-source.json", content_type="application/json",
                )
            data_path = self._data(firmware_id)
            if not data_path.exists():
                temp = self.root / f".{firmware_id}.{uuid.uuid4().hex}.tmp"
                temp.write_bytes(image_bytes)
                temp.replace(data_path)
            meta_path.write_text(
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
            **(
                {
                    "manifest_id": record.get("manifest_id"),
                    "manifest": record.get("manifest"),
                    "compatibility": record.get("source", {}).get(
                        "compatibility"
                    ),
                }
                if record.get("kind") == "manifest"
                else {}
            ),
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

    def list(self) -> list[dict]:
        with self._lock:
            records = [
                json.loads(path.read_text())
                for path in self.root.glob("*.json")
                if not path.name.endswith(".analysis.json")
            ]
        return sorted(
            records,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )

    def delete(self, firmware_id: str) -> dict:
        record = self.get(firmware_id)
        with self._lock:
            self._data(firmware_id).unlink(missing_ok=True)
            self._meta(firmware_id).unlink(missing_ok=True)
            (self.root / f"{firmware_id}.analysis.json").unlink(
                missing_ok=True
            )
        return {"firmware_id": firmware_id, "deleted": True, "record": record}


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def default_session_ready_timeout(
    network_config: dict[str, Any] | None,
) -> float:
    profile = (network_config or {}).get("profile")
    if profile in {
        CORE2_HCI_GATT_PROFILE,
        CORE2_NATIVE_VHCI_PROFILE,
        NANOC6_HCI_BLE_PROFILE,
        NESSO_UNIFIED_PROFILE,
        *UNIFIED_PROFILES,
    }:
        return 90.0
    return 30.0


def effective_session_ready_timeout(
    network_config: dict[str, Any] | None,
    requested_timeout: float | None = None,
) -> float:
    """Keep application readiness and BLE reconnect workload budgets aligned."""
    timeout = float(
        default_session_ready_timeout(network_config)
        if requested_timeout is None
        else requested_timeout
    )
    config = network_config or {}
    if config.get("profile") not in {
        CORE2_HCI_GATT_PROFILE,
        CORE2_NATIVE_VHCI_PROFILE,
        NANOC6_HCI_BLE_PROFILE,
        NESSO_UNIFIED_PROFILE,
        *UNIFIED_PROFILES,
    }:
        return timeout
    cycles = int(config.get("ble_reconnect_cycles", 1))
    delay = float(config.get("ble_reconnect_delay_seconds", 2))
    return max(
        timeout,
        reconnect_workload_timeout_seconds(cycles, delay),
    )


def _timestamp_age_seconds(value: Any, *, now: float | None = None) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    return max(0.0, (now or time.time()) - timestamp)


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
        return flash_with_esp_emu(
            chip=matrix_backend["esp_emu_chip"],
            image=image,
            flash_size=spec.flash_size,
            out_dir=out_dir,
            env=env,
            timeout=600,
            emulator=spec.flash_emulator,
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
        units: list[dict] | None = None,
        unit_contract: dict | None = None,
        runtime: str = "qemu",
        network_config: dict | None = None,
        storage_config: dict | None = None,
        storage_info: dict | None = None,
        nvs_config: dict | None = None,
        nvs_info: dict | None = None,
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
        worker_id: str | None = None,
        worker_generation: int | None = None,
        worker_lease_active: bool = False,
        process_start_token: str | None = None,
        reattached_process: bool = False,
        companions: dict | None = None,
        persist: bool = True,
        firmware_provenance: dict | None = None,
        program_transport: str | None = None,
        program_bootstrap: bool = False,
        management_binding: dict | None = None,
    ):
        self.service = service
        self.id = session_id
        self.spec = spec
        self.firmware_id = firmware_id
        self.firmware_path = firmware_path
        self.firmware_sha = firmware_sha
        self.firmware_source = firmware_source
        self.source_artifacts = source_artifacts
        self.firmware_provenance = (
            json.loads(json.dumps(firmware_provenance)) if firmware_provenance else None
        )
        self.runtime_env = dict(runtime_env or {})
        self.units = json.loads(json.dumps(units or []))
        self.unit_contract = (
            json.loads(json.dumps(unit_contract)) if unit_contract is not None
            else UnitRegistry().freeze([unit["unit_id"] for unit in self.units])
            if self.units and not restored else None
        )
        self.runtime = runtime
        self.program_transport = program_transport
        # Only service-owned bootstraps are safe to probe before the first Run.
        # Never interrupt an arbitrary manually prepared application's startup.
        self.program_bootstrap = program_bootstrap is True and program_transport == "uart-repl"
        self._program_capabilities = {"status": "unknown", "mpy_entrypoint": False,
                                      "reason": "bootstrap-probe-pending" if self.program_bootstrap and not restored else "not-probed"}
        self.management_binding = _normalize_management_binding(management_binding) if management_binding is not None else None
        self._management_handle = object() if self.management_binding is not None else None
        self._console = None
        self._program_lock = threading.Lock()
        self._program = None
        self.network_config = dict(network_config or {})
        self.storage_config = dict(storage_config or {})
        self.storage_info = (
            dict(storage_info) if isinstance(storage_info, dict) else None
        )
        self.nvs_config = dict(nvs_config or {})
        self.nvs_info = (
            dict(nvs_info) if isinstance(nvs_info, dict) else None
        )
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
        self.process_start_token = process_start_token
        self._reattached_process = bool(reattached_process)
        self.flash_info = flash_info
        self.virtual_flash: Path | None = None
        self.qmp_path = Path("/tmp") / f"m5-service-{session_id}.sock"
        self.dir = service.state_dir / "sessions" / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.serial0 = self.dir / "serial.log"
        self.serial1 = self.dir / "serial1.log"
        self.console_path = Path("/tmp") / f"m5-console-{session_id}.sock"
        self.program_path = self.dir / "program.json"
        self._program_restore_error = None
        if restored and program_transport and self.program_path.is_file():
            try:
                program = json.loads(self.program_path.read_text())
                if not isinstance(program, dict) or any(
                    not isinstance(program.get(field), str)
                    or len(program[field]) != size
                    or any(char not in "0123456789abcdef" for char in program[field])
                    for field, size in (("execution_id", 32), ("revision_id", 64))
                ) or program.get("state") not in (
                    "submitting", "running", "completed", "failed", "unknown",
                    "interrupt-requested", "interrupted", "cancelled",
                ) or type(program.get("serial_offset")) is not int or program["serial_offset"] < 0:
                    raise ValueError("invalid program identity")
                if program["state"] in {"running", "submitting", "unknown", "interrupt-requested"}:
                    program.update(state="unknown", output_gap_possible=True,
                                   error={"code": "program_output_gap"})
                self._program = program
            except (OSError, UnicodeError, ValueError):
                self._program_restore_error = "program history could not be verified"
        self.last_frame_path = self.dir / "last-frame.png"
        self.last_frame_meta_path = self.dir / "last-frame.json"
        self.device_state_path = self.dir / "device-state.json"
        self.unit_state_path = self.dir / "unit-state.json"
        self.unit_config_path = self.dir / "units-runtime.json"
        self.unit_adc_calibration_path = self.dir / "unit-adc-calibration.json"
        self.session_record_path = self.dir / "session.json"
        self.events_path = self.dir / "events.json"
        self.stdout_path = self.dir / "qemu.stdout"
        self.stderr_path = self.dir / "qemu.stderr"
        self.hci_probe_log = self.dir / "ble-probe.log"
        self.native_vhci_log = self.dir / "native-vhci-gdb.log"
        self.http_fixture_log = self.dir / "http-fixture.json"
        self.dns_fixture_log = self.dir / "dns-fixture.json"
        self.network_isolation_path = self.dir / "network-isolation.json"
        self.network_pcap = self.dir / "network.pcap"
        self.network_pcap_summary = self.dir / "network.pcap.json"
        self.sd_card_image = self.dir / "sd-card.img"
        self.storage_summary_path = self.dir / "storage.json"
        self.nvs_summary_path = self.dir / "nvs.json"
        self.speaker_pcm = self.dir / "speaker.pcm"
        self.microphone_source_pcm = self.dir / "microphone-source.pcm"
        self.rmt_source = self.dir / "nec-source.rmt"
        self.rmt_capture = self.dir / "nec-capture.rmt"
        self.hci_port: int | None = None
        self.gdb_port: int | None = None
        self._hci_probe: subprocess.Popen | None = None
        self._external_hci_probe_pid: int | None = None
        self._external_hci_probe_start_token: str | None = None
        self._external_hci_probe_command_sha256: str | None = None
        self._native_vhci_gdb: subprocess.Popen | None = None
        self._http_fixture: UnifiedHttpFixture | None = None
        self._companions: dict[str, dict[str, Any]] = {
            str(kind): dict(value)
            for kind, value in (companions or {}).items()
            if isinstance(kind, str) and isinstance(value, dict)
        }
        self._proc: subprocess.Popen | None = None
        self._qmp: QMP | None = None
        self._lock = threading.RLock()
        # Never wait for this lock while holding _lock or the service lock.
        # It owns resource creation, publication and teardown, including waits.
        self._lifecycle_lock = threading.RLock()
        self._lifecycle_depth = 0
        self._stop_request_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._stop_complete = threading.Event()
        self._stop_purge = False
        self._stop_retain_flash: bool | None = None
        self._stop_intent_version = 0
        self._purged_snapshot: dict | None = None
        self._provision_error: str | None = None
        self._last_frame_persisted_at = 0.0
        self._preview_frames = FrameCache()
        self._frame_epoch = 0
        self.unified_frame_changed: bool | None = None
        self.events: list[dict] = [dict(event) for event in (events or [])]
        self.restored = restored
        self.interrupted = interrupted
        self.worker_id = worker_id or service.worker.worker_id
        self.worker_generation = (
            int(worker_generation)
            if worker_generation is not None
            else service.worker.generation
        )
        self._worker_lease_active = bool(worker_lease_active)
        if events is None:
            self._record_event(
                "created", device_id=spec.id, firmware_id=firmware_id
            )
        if persist:
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

    def _release_worker_lease(
        self,
        *,
        state: str | None = None,
        error: str | None = None,
    ) -> str | None:
        if not self._worker_lease_active:
            return None
        network_status = (self.network_result or {}).get("status")
        result = {
            "device_id": self.spec.id,
            "state": state or self.state,
            "runtime": self.runtime,
            "firmware_sha256": self.firmware_sha,
            "network_status": network_status,
            "network_pcap_available": self.network_pcap.is_file(),
            "evidence_available": self.last_frame_path.is_file()
            or self.serial0.is_file(),
            "error": error or self.error,
        }
        try:
            self.service.worker.release_lease(self.id, result=result)
        except Exception as release_error:
            message = str(release_error)
            self._record_event(
                "worker_lease_release_failed",
                error=message,
            )
            return message
        self._worker_lease_active = False
        self._record_event(
            "worker_lease_released",
            worker_id=self.worker_id,
            generation=self.worker_generation,
            result_state=result["state"],
        )
        return None

    def _session_record(self) -> dict:
        return {
            "schema_version": 1,
            "session_id": self.id,
            "device_id": self.spec.id,
            "state": self.state,
            "pid": self.pid,
            "process_start_token": self.process_start_token,
            "reattached_process": self._reattached_process,
            "firmware_id": self.firmware_id,
            "firmware_sha256": self.firmware_sha,
            "firmware_source": self.firmware_source,
            "source_artifacts": list(self.source_artifacts),
            **({"program_transport": self.program_transport} if self.program_transport else {}),
            **({"program_bootstrap": self.program_bootstrap,
                "program_capabilities": self.program_capabilities()} if self.program_transport else {}),
            **({"management_binding": dict(self.management_binding)} if self.management_binding is not None else {}),
            **({"firmware_provenance": self.firmware_provenance} if self.firmware_provenance else {}),
            "runtime_env": redacted_runtime_env(self.runtime_env),
            "units": self.units,
            "unit_contract": self.unit_contract,
            "runtime": self.runtime,
            "network": redacted_network_config(self.network_config),
            "network_result": self.network_result,
            "storage_config": dict(self.storage_config),
            "storage": self.storage_info,
            "nvs_config": dict(self.nvs_config),
            "nvs": self.nvs_info,
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
            "worker_id": self.worker_id,
            "worker_generation": self.worker_generation,
            "worker_lease_active": self._worker_lease_active,
            "companions": {
                kind: dict(value)
                for kind, value in self._companions.items()
            },
        }

    def _persist_session(self) -> None:
        atomic_write_json(self.session_record_path, self._session_record())

    def _process_identity_matches(self) -> bool:
        if self.pid is None or not self.process_start_token:
            return False
        identity = inspect_process(self.pid)
        return bool(
            identity["exists"]
            and identity["start_token"] == self.process_start_token
            and str(self.qmp_path) in str(identity["command"] or "")
        )

    def _requires_http_fixture(self) -> bool:
        profile = self.network_config.get("profile")
        return (
            self.network_config.get("http_fixture", True)
            and (
                profile in UNIFIED_PROFILES
                or profile == STICKS3_WIFI_PROFILE
            )
        )

    def _requires_hci_probe(self) -> bool:
        profile = self.network_config.get("profile")
        return (
            self.runtime in {QEMU_BLE_RUNTIME, QEMU_UNIFIED_RUNTIME}
            and profile
            in {
                CORE2_HCI_GATT_PROFILE,
                NANOC6_HCI_BLE_PROFILE,
                NESSO_UNIFIED_PROFILE,
                *UNIFIED_PROFILES,
            }
        )

    def _companion_process_matches(
        self,
        pid: int,
        start_token: str,
        command_sha256: str,
    ) -> bool:
        identity = inspect_process(pid)
        command = identity.get("command")
        return bool(
            identity["exists"]
            and identity["start_token"] == start_token
            and isinstance(command, str)
            and hashlib.sha256(command.encode()).hexdigest()
            == command_sha256
        )

    def _companion_snapshot(self) -> dict[str, dict[str, Any]]:
        safe_fields = (
            "state",
            "pid",
            "port",
            "generation",
            "ownership_verified",
            "adopted",
            "recovery_action",
            "continuity_trigger",
        )
        return {
            "http_fixture": {
                "required": self._requires_http_fixture(),
                **{
                    key: value
                    for key, value in self._companions.get(
                        "http", {}
                    ).items()
                    if key in safe_fields
                },
            },
            "ble_probe": {
                "required": self._requires_hci_probe(),
                **{
                    key: value
                    for key, value in self._companions.get(
                        "ble", {}
                    ).items()
                    if key in safe_fields
                },
            },
        }

    def _recovery_scope(self) -> str | None:
        if not self._reattached_process:
            return None
        if self._requires_http_fixture() or self._requires_hci_probe():
            return "qemu-control-plane+companions"
        return "qemu-control-plane"

    def _read_http_fixture_requests(self) -> list[dict[str, Any]]:
        if not self.http_fixture_log.is_file():
            return []
        try:
            loaded = json.loads(self.http_fixture_log.read_text())
        except json.JSONDecodeError as error:
            raise ServiceError(
                "companion_recovery_failed",
                f"HTTP fixture evidence is malformed: {error}",
                409,
            ) from error
        if not isinstance(loaded, list) or any(
            not isinstance(item, dict) for item in loaded
        ):
            raise ServiceError(
                "companion_recovery_failed",
                "HTTP fixture evidence is not a request object list",
                409,
            )
        return [dict(item) for item in loaded]

    def _update_companion(self, companion_name: str, **fields: Any) -> None:
        self._companions.setdefault(companion_name, {}).update(fields)

    def _close_http_fixture(self) -> None:
        fixture = self._http_fixture
        if fixture is None:
            state = self._companions.get("http")
            if (
                isinstance(state, dict)
                and state.get("kind") == "qemu-guestfwd-command"
                and state.get("state") in {"running", "recovered", "adopted"}
            ):
                self._update_companion(
                    "http",
                    state="terminated",
                    ownership_verified=False,
                    adopted=False,
                    terminated_at=iso_now(),
                )
            return
        try:
            fixture.close()
        except OSError:
            pass
        self._http_fixture = None
        self._update_companion(
            "http",
            state="terminated",
            ownership_verified=False,
            adopted=False,
            terminated_at=iso_now(),
        )

    def _recover_ble_probe(self) -> dict[str, Any]:
        state = self._companions.get("ble")
        if not isinstance(state, dict):
            raise ServiceError(
                "companion_recovery_failed",
                "BLE companion ownership metadata is missing",
                409,
            )
        pid = state.get("pid")
        start_token = state.get("start_token")
        command_sha256 = state.get("command_sha256")
        port = state.get("port")
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(start_token, str)
            or not start_token
            or not isinstance(command_sha256, str)
            or not _is_sha256(command_sha256)
            or not isinstance(port, int)
            or isinstance(port, bool)
            or not 1 <= port <= 65535
        ):
            raise ServiceError(
                "companion_recovery_failed",
                "BLE companion ownership metadata is invalid",
                409,
            )
        if self._companion_process_matches(
            pid,
            start_token,
            command_sha256,
        ):
            probe_log = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            self.hci_port = port
            self._external_hci_probe_pid = pid
            self._external_hci_probe_start_token = start_token
            self._external_hci_probe_command_sha256 = command_sha256
            self._update_companion(
                "ble",
                state="adopted",
                ownership_verified=True,
                adopted=True,
                recovery_action="adopt",
                adopted_at=iso_now(),
                previous_pid=pid,
                pid=pid,
                port=port,
            )
            self._record_event(
                "hci_probe_adopted",
                pid=pid,
                port=port,
                prior_peer_pass="BLE_BUMBLE_PASS" in probe_log,
            )
            self._persist_session()
            return dict(self._companions["ble"])
        probe_log = (
            self.hci_probe_log.read_text(errors="replace")
            if self.hci_probe_log.is_file()
            else ""
        )
        if "BLE_BUMBLE_PASS" in probe_log:
            self._update_companion(
                "ble",
                state="completed",
                ownership_verified=False,
                adopted=False,
                recovery_action="retain-completed-evidence",
                recovered_at=iso_now(),
            )
            self._record_event(
                "hci_probe_completed_before_restart",
                pid=pid,
                port=port,
            )
            self._persist_session()
            return dict(self._companions["ble"])
        raise ServiceError(
            "companion_recovery_failed",
            "BLE companion PID/start-time/command ownership "
            "does not match and no completion evidence exists",
            409,
        )

    def _recover_http_fixture(self) -> dict[str, Any]:
        state = self._companions.get("http")
        if not isinstance(state, dict):
            raise ServiceError(
                "companion_recovery_failed",
                "HTTP fixture recovery metadata is missing",
                409,
            )
        expected_port = UNIFIED_HTTP_PORTS.get(
            self.network_config.get("profile")
        )
        persisted_port = state.get("port")
        if (
            not isinstance(persisted_port, int)
            or isinstance(persisted_port, bool)
            or expected_port is None
            or persisted_port != expected_port
        ):
            raise ServiceError(
                "companion_recovery_failed",
                "HTTP fixture port metadata does not match the profile",
                409,
            )
        if state.get("kind") == "qemu-guestfwd-command":
            self._update_companion(
                "http",
                state="adopted",
                ownership_verified=True,
                adopted=True,
                recovery_action="qemu-process-owned",
                recovered_at=iso_now(),
            )
            self._persist_session()
            return dict(self._companions["http"])
        self._launch_http_fixture(recover=True)
        assert "http" in self._companions
        return dict(self._companions["http"])

    def _recover_companions(self) -> dict[str, dict[str, Any]]:
        http_required = self._requires_http_fixture()
        ble_required = self._requires_hci_probe()
        if not http_required and not ble_required:
            return self._companion_snapshot()
        policy = NetworkPolicy.from_mapping(
            self.network_config.get("policy")
        )
        if policy.isolation != "trusted-host":
            raise ServiceError(
                "companion_recovery_unsupported",
                "namespace-managed companion ownership cannot be "
                "recovered by the restarted Device Service",
                409,
            )
        if ble_required:
            self._recover_ble_probe()
        if http_required:
            try:
                self._recover_http_fixture()
            except ServiceError as error:
                self._update_companion(
                    "http",
                    state="recovery-failed",
                    ownership_verified=False,
                    adopted=False,
                    recovery_action="fail-closed",
                    error=error.message,
                )
                self._persist_session()
                raise
        return self._companion_snapshot()

    def reattach(self) -> dict:
        with self._lifecycle_operation():
            try:
                return self._reattach_runtime()
            except Exception as error:
                self._request_failure(error)
                raise

    def _reattach_runtime(self) -> dict:
        if self.runtime not in QEMU_QMP_RUNTIMES:
            raise ServiceError(
                "reattach_unsupported",
                "runtime has no re-attachable QMP control plane",
                409,
            )
        if self.state not in ACTIVE_STATES:
            raise ServiceError(
                "reattach_not_active",
                "session is not in an active state",
                409,
            )
        if not self._process_identity_matches():
            raise ServiceError(
                "reattach_identity_mismatch",
                "PID/start-time/QMP ownership does not match the session",
                409,
            )
        qmp: QMP | None = None
        qemu_running = False
        try:
            qmp = wait_qmp(self.qmp_path, timeout=5)
            qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
            status_result = qmp.cmd("query-status")
            status = (status_result.get("return") or {}).get("status")
            if status != "running":
                raise ServiceError(
                    "reattach_not_running",
                    f"QEMU status is {status!r}, not running",
                    409,
                )
            qemu_running = True
            if self.program_transport == "uart-repl":
                from guest_console import GuestConsole

                self._console = GuestConsole(self.console_path, self.serial0)
                self._console.connect(timeout=5, cancelled=self._stop_event.is_set)
                with self._lock:
                    if self._program and self._program["state"] in {"running", "submitting", "unknown"}:
                        self._program.update(state="unknown", output_gap_possible=True,
                                             error={"code": "program_output_gap"})
                        self._persist_program()
                self._record_event("program_console_reattached", output_gap_possible=True)
            companion_recovery = self._recover_companions()
            if self._worker_lease_active:
                self.service.worker.reserve_lease(
                    self.id,
                    owner="service-restart-reattach",
                )
        except ServiceError:
            if qmp is not None:
                qmp.close()
            self._close_http_fixture()
            if qemu_running:
                self._reattached_process = True
                self._terminate_process()
            raise
        except (OSError, RuntimeError, WorkerRegistryError) as error:
            if qmp is not None:
                qmp.close()
            self._close_http_fixture()
            if qemu_running:
                self._reattached_process = True
                self._terminate_process()
            raise ServiceError(
                "reattach_unavailable",
                f"QMP/worker/companion planes could not be re-attached: {error}",
                409,
            ) from error
        self._qmp = qmp
        self._proc = None
        self._reattached_process = True
        self.restored = True
        self.interrupted = False
        self.completed_at = None
        self.error = None
        self.worker_generation = self.service.worker.generation
        self._record_event(
            "reattached",
            pid=self.pid,
            previous_state=self.state,
            qmp_status=status,
            recovery_scope=self._recovery_scope(),
            companions=self._companion_snapshot(),
        )
        self._persist_session()
        return {
            "pid": self.pid,
            "qmp_status": status,
            "worker_generation": self.worker_generation,
            "recovery_scope": self._recovery_scope(),
            "companion_recovery": companion_recovery,
        }

    def mark_interrupted(self, previous_state: str, reason: str) -> None:
        self.state = "failed"
        self.error = (
            "service restarted before the session completed; "
            f"previous state was {previous_state}: {reason}"
        )
        self.completed_at = self.completed_at or iso_now()
        self.interrupted = True
        self._reattached_process = False
        self._worker_lease_active = False
        for kind, companion in self._companions.items():
            if companion.get("state") not in {"completed", "terminated"}:
                companion.update(
                    {
                        "state": "recovery-failed",
                        "ownership_verified": False,
                        "adopted": False,
                    }
                )
        self._record_event(
            "interrupted",
            previous_state=previous_state,
            reason=reason,
        )
        self._persist_session()

    def snapshot(self) -> dict:
        if self._stop_event.is_set() and not self._stop_complete.is_set():
            return self._pending_stop_snapshot()
        with self._lock:
            if (
                self._proc is not None
                and self._proc.poll() is not None
                and self.state in ACTIVE_STATES
            ):
                self._handle_process_exit(self._proc.returncode)
            elif (
                self._reattached_process
                and self.state in ACTIVE_STATES
                and not self._process_identity_matches()
            ):
                self._handle_process_exit(
                    None,
                    reason="re-attached QEMU process disappeared or changed identity",
                )
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
            if (
                self.runtime == QEMU_WIFI_RUNTIME
                and self.network_config
                and self.state in ACTIVE_STATES
                and (self.network_result or {}).get("status") != "PASS"
            ):
                self.network_result = self._build_network_evidence()
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
                **({"program_transport": self.program_transport,
                    "program": self._program,
                    "program_capabilities": self.program_capabilities()} if self.program_transport else {}),
                **({"management_binding": dict(self.management_binding)} if self.management_binding is not None else {}),
                **({"firmware_provenance": self.firmware_provenance} if self.firmware_provenance else {}),
                "runtime_env": redacted_runtime_env(self.runtime_env),
                "runtime": self.runtime,
                "runtime_memory": (
                    qemu_runtime_memory(
                        self.spec.memory,
                        (
                            self.network_config.get("profile")
                            if isinstance(self.network_config, dict)
                            else None
                        ),
                        self.spec.id,
                    )
                    if self.runtime != "network"
                    else None
                ),
                "network": self.network_result
                or (
                    {
                        "status": "RUNNING",
                        "profile": self.network_config.get("profile"),
                        "hostfwd": list(
                            self.network_config.get("hostfwd", [])
                        ),
                        "firmware_ap_password_configured": (
                            self.network_config.get("firmware_ap_password")
                            is not None
                        ),
                    }
                    if self.network_config
                    else None
                ),
                "storage": self.storage_info,
                "units": self.units,
                "nvs": self.nvs_info,
                "flash": self.flash_info,
                "flash_retained": bool(
                    self.virtual_flash is not None
                    and self.virtual_flash.is_file()
                ),
                "serial_bytes": serial_size,
                "created_at": self.created_at,
                "expires_at": datetime.fromtimestamp(
                    self.expires_at, timezone.utc
                ).isoformat(),
                "error": self.error,
                "display": self.spec.display,
                "display_available": (
                    self.runtime in QEMU_QMP_RUNTIMES
                    and self.spec.has_display
                ),
                "last_frame_available": self.last_frame_path.is_file(),
                "last_frame_captured_at": frame_meta.get("captured_at"),
                "device_state_supported": bool(
                    self.runtime in QEMU_QMP_RUNTIMES
                    and self.spec.state_probes
                ),
                "last_device_state_available": self.device_state_path.is_file(),
                "last_device_state_at": state_meta.get("captured_at"),
                "completed_at": self.completed_at,
                "event_count": len(self.events),
                "restored": self.restored,
                "interrupted": self.interrupted,
                "reattached_process": self._reattached_process,
                "recovery_scope": self._recovery_scope(),
                "companions": self._companion_snapshot(),
                "worker": {
                    "worker_id": self.worker_id,
                    "generation": self.worker_generation,
                    "lease_active": self._worker_lease_active,
                },
            }

    def _handle_process_exit(
        self,
        returncode: int | None,
        *,
        reason: str | None = None,
    ) -> None:
        # The transaction owner handles startup/reset failures. A snapshot or
        # janitor must not remove resources while that owner can still publish.
        with self._lock:
            if self._lifecycle_depth or self._stop_event.is_set():
                return
            self._terminate_runtime()
            self.state = "failed"
            self.error = (
                self.error
                or reason
                or f"process exited with code {returncode}"
            )
            self.completed_at = self.completed_at or iso_now()
            self._record_event("process_exited", returncode=returncode)
            self._reattached_process = False
            self._close_http_fixture()
            self._terminate_hci_probe()
            if self.runtime in QEMU_RADIO_RUNTIMES:
                self._finalize_network_capture()
            if not self.service.storage_policy.retain_session_flash:
                self._release_virtual_flash()
            release_error = self._release_worker_lease(
                state="failed",
                error=self.error,
            )
            if release_error:
                self._provision_error = self.error
                self.state = "stopping"
                self.completed_at = None
                self._stop_event.set()
            self._persist_session()

    def start(self) -> None:
        thread = threading.Thread(
            target=self._provision,
            name=f"m5-session-{self.id}",
            daemon=True,
        )
        thread.start()

    def _check_cancelled(self) -> None:
        if self._stop_event.is_set() or self.state in {"stopped", "failed"}:
            raise SessionCancelled()

    def _request_failure(self, error: Exception) -> None:
        with self._stop_request_lock:
            if not self._stop_event.is_set():
                self._provision_error = str(error)
                self.error = str(error)
                self._stop_event.set()

    @contextmanager
    def _lifecycle_operation(self):
        try:
            with self._lifecycle_lock:
                with self._lock:
                    self._check_cancelled()
                    self._lifecycle_depth += 1
                try:
                    yield
                finally:
                    self._lifecycle_depth -= 1
        finally:
            # This is outside the lifecycle lock. It covers reset and reattach
            # as well as provisioning; no caller has to retry a pending stop.
            if not self._lifecycle_depth and self._stop_event.is_set() and not self._stop_complete.is_set():
                try:
                    self.stop()
                except Exception:
                    # stop persisted the cleanup failure; the janitor retries
                    # without freeing capacity or claiming a terminal result.
                    pass

    def _pending_stop_snapshot(self) -> dict:
        # QMP startup may hold _lock for its entire handshake. Cancellation
        # acknowledgement must not wait for it or pretend teardown finished.
        return {
            "session_id": self.id,
            "device_id": self.spec.id,
            "state": "stopping",
            "stop_pending": True,
            "runtime": self.runtime,
            "firmware_id": self.firmware_id,
            "firmware_sha256": self.firmware_sha,
            "error": self.error,
            "units": self.units,
            "display": self.spec.display,
            "created_at": self.created_at,
            "completed_at": None,
            "expires_at": datetime.fromtimestamp(self.expires_at, timezone.utc).isoformat(),
            "worker": {
                "worker_id": self.worker_id,
                "generation": self.worker_generation,
                "lease_active": self._worker_lease_active,
            },
        }

    def _set_state(self, state: str) -> None:
        with self._lock:
            with self._stop_request_lock:
                self._check_cancelled()
                previous = self.state
                self.state = state
            self._record_event("state", **{"from": previous, "to": state})
            self._persist_session()

    @staticmethod
    def _read_json_list(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _network_isolation_evidence(self) -> dict[str, Any]:
        if not self.network_isolation_path.is_file():
            return {
                "status": "NOT_RUN",
                "reason": "network isolation evidence is unavailable",
            }
        try:
            evidence = json.loads(self.network_isolation_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            return {
                "status": "FAIL",
                "reason": str(error),
            }
        if not isinstance(evidence, dict):
            return {
                "status": "FAIL",
                "reason": "network isolation evidence is not an object",
            }
        evidence["status"] = (
            "PASS"
            if evidence.get("cleanup_completed") is True
            else "ACTIVE"
        )
        return evidence

    def _build_network_evidence(self) -> dict:
        if self.runtime not in QEMU_RADIO_RUNTIMES:
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
        if profile == NANOC6_HCI_BLE_PROFILE:
            probe_log = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            serial_markers = [
                str(marker)
                for marker in self.network_config.get(
                    "expected_markers",
                    NANOC6_HCI_BLE_MARKERS,
                )
            ]
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

            def rmt_check(script: str, *arguments: str) -> dict:
                if not self.rmt_capture.is_file():
                    return {
                        "status": "NOT_RUN",
                        "reason": "RMT capture file is missing",
                    }
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
                result = subprocess.run(
                    [
                        sys.executable,
                        str(TEST_TOOLS / script),
                        str(self.rmt_capture),
                        *arguments,
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                return {
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "detail": result.stdout.strip(),
                }

            ws2812 = rmt_check(
                "check_rmt_ws2812.py",
                "--led",
                "0,255,0",
            )
            nec = rmt_check(
                "check_rmt_nec.py",
                "--address",
                "0x56",
                "--command",
                "0xa3",
            )
            checks["rmt:ws2812_green"] = ws2812["status"] == "PASS"
            checks["rmt:nec"] = nec["status"] == "PASS"
            http_requests: list[dict] = []
            if self._http_fixture is not None:
                http_requests = self._http_fixture.request_snapshot()
            elif self.http_fixture_log.is_file():
                try:
                    loaded = json.loads(self.http_fixture_log.read_text())
                    if isinstance(loaded, list):
                        http_requests = [
                            item for item in loaded if isinstance(item, dict)
                        ]
                except json.JSONDecodeError:
                    http_requests = []
            checks["http:controlled_request"] = (
                controlled_http_requests_match(http_requests)
            )
            if all(checks.values()):
                status = "PASS"
            elif serial.strip() or probe_log.strip():
                status = "PARTIAL"
            else:
                status = "RUNNING" if self.state in ACTIVE_STATES else "FAIL"
            rmt_bytes = (
                self.rmt_capture.read_bytes()
                if self.rmt_capture.is_file()
                else b""
            )
            ble_name, ble_payload = NANOC6_BLE_IDENTITY
            return {
                "schema_version": 1,
                "kind": "m5stack-nanoc6-board-hci-ble-qemu-proof",
                "scope": "simulation-only-not-hardware-validation",
                "status": status,
                "session_id": self.id,
                "device_id": self.spec.id,
                "profile": profile,
                "runtime": {
                    "name": "qemu",
                    "guest_process_count": 1,
                    "console": "USB-Serial-JTAG",
                    "hci_transport": "UART1 H4",
                    "ble_controller": "Bumble",
                    "ble_peer": "external Bumble peer",
                    "wifi_nic": self.network_config.get("nic"),
                    "wifi": "PASS via QEMU ESP32-C6 MAC/DMA and SLiRP",
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
                "rmt": {
                    "bytes": len(rmt_bytes),
                    "sha256": (
                        hashlib.sha256(rmt_bytes).hexdigest()
                        if rmt_bytes
                        else None
                    ),
                    "ws2812": ws2812,
                    "nec": nec,
                },
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
                    "native ESP32-C6 Bluetooth controller/radio model",
                    "RF privacy, security, range or performance",
                    "untrusted-firmware sandboxing",
                ],
            }
        if profile == NESSO_UNIFIED_PROFILE:
            probe_log = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            serial_markers = [
                str(marker)
                for marker in self.network_config.get(
                    "expected_markers",
                    NESSO_UNIFIED_MARKERS,
                )
            ]
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

            def data_check(
                script: str,
                path: Path,
                *arguments: str,
            ) -> dict:
                if not path.is_file():
                    return {
                        "status": "NOT_RUN",
                        "reason": f"{path.name} is missing",
                    }
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
                result = subprocess.run(
                    [
                        sys.executable,
                        str(TEST_TOOLS / script),
                        str(path),
                        *arguments,
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                return {
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "detail": result.stdout.strip(),
                }

            nec = data_check(
                "check_rmt_nec.py",
                self.rmt_capture,
                "--address",
                "0x56",
                "--command",
                "0xa3",
            )
            pcm = data_check(
                "check_pcm.py",
                self.speaker_pcm,
                "--min-nonzero",
                "1000",
                "--min-peak-to-peak",
                "1000",
            )
            checks["rmt:nec"] = nec["status"] == "PASS"
            checks["pcm:buzzer"] = pcm["status"] == "PASS"
            http_requests: list[dict] = []
            if self._http_fixture is not None:
                http_requests = self._http_fixture.request_snapshot()
            elif self.http_fixture_log.is_file():
                try:
                    loaded = json.loads(self.http_fixture_log.read_text())
                    if isinstance(loaded, list):
                        http_requests = [
                            item for item in loaded if isinstance(item, dict)
                        ]
                except json.JSONDecodeError:
                    http_requests = []
            checks["http:controlled_request"] = (
                controlled_http_requests_match(http_requests)
            )
            try:
                frame = self.frame_metrics()
                checks["frame:nonblank"] = frame["nonblack_pixels"] > 100
            except ServiceError as error:
                frame = {"error": error.message}
                checks["frame:nonblank"] = False
            if self.unified_frame_changed is not None:
                checks["frame:touch_redraw"] = self.unified_frame_changed
            if all(checks.values()):
                status = "PASS"
            elif serial.strip() or probe_log.strip():
                status = "PARTIAL"
            else:
                status = "RUNNING" if self.state in ACTIVE_STATES else "FAIL"
            rmt_bytes = (
                self.rmt_capture.read_bytes()
                if self.rmt_capture.is_file()
                else b""
            )
            pcm_bytes = (
                self.speaker_pcm.read_bytes()
                if self.speaker_pcm.is_file()
                else b""
            )
            ble_name, ble_payload = NESSO_BLE_IDENTITY
            return {
                "schema_version": 1,
                "kind": "m5stack-nesso-board-hci-ble-qemu-proof",
                "scope": "simulation-only-not-hardware-validation",
                "status": status,
                "session_id": self.id,
                "device_id": self.spec.id,
                "profile": profile,
                "runtime": {
                    "name": "qemu",
                    "guest_process_count": 1,
                    "console": "USB-Serial-JTAG",
                    "hci_transport": "UART1 H4",
                    "ble_controller": "Bumble",
                    "ble_peer": "external Bumble peer",
                    "display": "135x240",
                    "wifi_nic": self.network_config.get("nic"),
                    "wifi": "PASS via QEMU ESP32-C6 MAC/DMA and SLiRP",
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
                "frame": {
                    key: value for key, value in frame.items() if key not in {"png", "captured_monotonic"}
                },
                "rmt": {
                    "bytes": len(rmt_bytes),
                    "sha256": (
                        hashlib.sha256(rmt_bytes).hexdigest()
                        if rmt_bytes
                        else None
                    ),
                    "nec": nec,
                },
                "pcm": {
                    "bytes": len(pcm_bytes),
                    "sha256": (
                        hashlib.sha256(pcm_bytes).hexdigest()
                        if pcm_bytes
                        else None
                    ),
                    "check": pcm,
                },
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
                    "native ESP32-C6 Bluetooth controller/radio model",
                    "RF privacy, security, range or performance",
                    "untrusted-firmware sandboxing",
                ],
            }
        if profile in UNIFIED_PROFILES:
            default_markers = UNIFIED_MARKERS[profile]
            ble_name, ble_payload = UNIFIED_BLE_IDENTITIES[self.spec.id]
            probe_log = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            native_bridge_log = (
                self.native_vhci_log.read_text(errors="replace")
                if self.native_vhci_log.is_file()
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
                http_requests = self._http_fixture.request_snapshot()
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
            ble_peer_role = self.network_config.get("ble_peer_role", "central")
            peer_markers = (
                "BLE_PERIPHERAL_CONNECTED", "BLE_PERIPHERAL_SUBSCRIBED",
                "BLE_PERIPHERAL_WRITE", "BLE_PERIPHERAL_NOTIFICATION_SENT",
                "BLE_PERIPHERAL_PASS",
            ) if ble_peer_role == "peripheral" else CORE2_HCI_PROBE_MARKERS
            checks.update(
                {
                    f"peer:{marker}": marker in probe_log
                    for marker in peer_markers
                }
            )
            checks["http:controlled_request"] = (
                controlled_http_requests_match(http_requests)
            )
            if profile == CORE2_NATIVE_VHCI_PROFILE:
                checks.update(
                    {
                        "bridge:ready": (
                            "NATIVE_VHCI_BRIDGE_READY" in native_bridge_log
                        ),
                        "bridge:h2c": "NATIVE_VHCI_H2C" in native_bridge_log,
                        "bridge:c2h": "NATIVE_VHCI_C2H" in native_bridge_log,
                        "bridge:acl_h2c": (
                            "NATIVE_VHCI_H2C 0201" in native_bridge_log
                        ),
                        "bridge:acl_c2h": (
                            "NATIVE_VHCI_C2H 0201" in native_bridge_log
                        ),
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
                "kind": f"m5stack-{self.spec.id}-unified-qemu-proof",
                "scope": "simulation-only-not-hardware-validation",
                "status": status,
                "session_id": self.id,
                "device_id": self.spec.id,
                "profile": profile,
                "runtime": {
                    "name": "qemu",
                    "guest_process_count": 1,
                    "memory": qemu_runtime_memory(
                        self.spec.memory,
                        profile,
                        self.spec.id,
                    ),
                    "wifi_nic": self.network_config.get("nic"),
                    "hci_transport": (
                        "ESP32 native HCI device + HLI to Bumble"
                        if profile == CORE2_NATIVE_HCI_PROFILE
                        else "ESP32 VHCI via GDB bridge to Bumble"
                        if profile == CORE2_NATIVE_VHCI_PROFILE
                        else "UART2 H4"
                        if profile == STACKCHAN_UNIFIED_PROFILE
                        else "UART1 H4"
                    ),
                    "ble_controller": "Bumble",
                    "ble_peer": "external Bumble peer",
                    "ble_peer_role": ble_peer_role,
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
                "bridge_log_bytes": len(native_bridge_log.encode()),
                "bridge_log_sha256": (
                    hashlib.sha256(native_bridge_log.encode()).hexdigest()
                    if profile == CORE2_NATIVE_VHCI_PROFILE
                    else None
                ),
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
                    (
                        "bit-exact Espressif BT baseband/controller"
                        if profile in {
                            CORE2_NATIVE_VHCI_PROFILE,
                            CORE2_NATIVE_HCI_PROFILE,
                        }
                        else "native ESP32 WiFi PHY or Bluetooth controller model"
                        if self.spec.id == "core2"
                        else "native ESP32-S3 WiFi PHY or Bluetooth controller model"
                    ),
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
        cname_records = self.network_config.get("cname_records", {})
        if isinstance(cname_records, dict) and cname_records:
            dns_requests = self._read_json_list(self.dns_fixture_log)
            chain_matches = []
            for alias, terminal in cname_records.items():
                matching = next(
                    (
                        row
                        for row in dns_requests
                        if row.get("name") == alias
                        and row.get("qtype") == "1"
                    ),
                    None,
                )
                chain_matches.append(
                    isinstance(matching, dict)
                    and matching.get("decision") == "allow"
                    and matching.get("cname_terminal") == terminal
                    and bool(matching.get("cname_chain"))
                )
            checks["dns:cname_chain"] = bool(chain_matches) and all(
                chain_matches
            )
        policy_config = self.network_config.get("policy")
        if (
            profile == STICKS3_WIFI_PROFILE
            and isinstance(policy_config, dict)
            and policy_config.get("dns") == "controlled"
        ):
            http_requests = self._read_json_list(self.http_fixture_log)
            allowed_hosts = {
                str(host)
                for host in policy_config.get("allowed_hosts", [])
            }
            checks["http:controlled_request"] = any(
                row.get("decision") == "allow"
                and row.get("status") == "200"
                and str(row.get("host", "")).rsplit(":", 1)[0]
                in allowed_hosts
                for row in http_requests
            )
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
                if self.runtime in {QEMU_BLE_RUNTIME, QEMU_UNIFIED_RUNTIME}
                else "external peer coverage",
                "malware sandboxing",
            ],
        }

    def _finalize_network_capture(self) -> dict | None:
        if not self.network_config.get("capture_pcap", False):
            return None
        if not self.network_pcap.is_file():
            return None
        try:
            summary = summarize_pcap(self.network_pcap)
        except (OSError, PcapError) as error:
            failure = {
                "schema_version": 1,
                "kind": "m5stack-pcap-summary",
                "status": "FAIL",
                "reason": str(error),
                "capture": {
                    "bytes": self.network_pcap.stat().st_size,
                    "sha256": hashlib.sha256(
                        self.network_pcap.read_bytes()
                    ).hexdigest(),
                },
            }
            atomic_write_json(self.network_pcap_summary, failure)
            self._record_event(
                "network_capture_summary_failed",
                error=str(error),
            )
            return failure
        summary = {
            "status": "PASS",
            **summary,
        }
        atomic_write_json(self.network_pcap_summary, summary)
        self._record_event(
            "network_capture_summarized",
            packets=summary.get("packets", 0),
            capture_sha256=summary.get("input", {}).get("sha256"),
        )
        return summary

    def _network_capture_evidence(self) -> dict:
        if not self.network_config.get("capture_pcap", False):
            return {
                "status": "NOT_RUN",
                "reason": "network.capture_pcap is disabled",
            }
        if self.network_pcap_summary.is_file():
            try:
                return json.loads(self.network_pcap_summary.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        if self.network_pcap.is_file():
            return {
                "status": "CAPTURING",
                "bytes": self.network_pcap.stat().st_size,
            }
        return {
            "status": "NOT_RUN",
            "reason": "capture file has not been created",
        }

    def network_evidence(self) -> dict:
        evidence = self._build_network_evidence()
        if self.network_config.get("policy"):
            evidence["policy"] = self.network_config["policy"]
            evidence["isolation"] = self._network_isolation_evidence()
            evidence["dns_requests"] = self._read_json_list(
                self.dns_fixture_log
            )
            evidence["http_fixture_requests"] = self._read_json_list(
                self.http_fixture_log
            )
        evidence["packet_capture"] = self._network_capture_evidence()
        previous = self.network_result or {}
        self.network_result = evidence
        if (
            previous.get("status") != evidence.get("status")
            or previous.get("checks") != evidence.get("checks")
        ):
            self._persist_session()
        return evidence

    def _apply_nvs_fixture(self) -> None:
        if not self.nvs_config:
            return
        if self.virtual_flash is None or not self.virtual_flash.is_file():
            raise RuntimeError("session flash is unavailable for NVS fixture")
        artifact_id = str(self.nvs_config["image_artifact_id"])
        source = self.service.artifacts.path(artifact_id)
        source_data = source.read_bytes()
        source_sha256 = hashlib.sha256(source_data).hexdigest()
        if source_sha256 != artifact_id:
            raise RuntimeError("NVS fixture checksum changed before session apply")
        offset = int(self.nvs_config["offset"])
        size = int(self.nvs_config["size"])
        if len(source_data) != size:
            raise RuntimeError("NVS fixture size does not match partition")
        with self.virtual_flash.open("r+b") as flash:
            flash.seek(offset)
            flash.write(source_data)
        effective_sha256 = hashlib.sha256(
            self.virtual_flash.read_bytes()
        ).hexdigest()
        self.nvs_info = {
            "partition_label": self.nvs_config["partition_label"],
            "offset": offset,
            "size": size,
            "artifact_id": artifact_id,
            "sha256": source_sha256,
            "bytes": len(source_data),
            "session_isolated_overlay": True,
            "source_artifact_modified": False,
            "base_flash_sha256": self.firmware_sha,
            "effective_flash_sha256": effective_sha256,
        }
        self.flash_info = {
            **(self.flash_info or {}),
            "base_flash_sha256": self.firmware_sha,
            "effective_flash_sha256": effective_sha256,
            "nvs_partition": {
                "label": self.nvs_config["partition_label"],
                "offset": offset,
                "size": size,
                "fixture_sha256": source_sha256,
            },
        }
        atomic_write_json(self.nvs_summary_path, self.nvs_info)
        self._record_event("nvs_fixture_applied", **self.nvs_info)

    def _provision(self) -> None:
        try:
            with self._lifecycle_operation():
                try:
                    self._provision_runtime()
                except SessionCancelled:
                    pass
                except Exception as error:
                    self._request_failure(error)
        except SessionCancelled:
            # Stop before this thread starts is cancellation, not a failure.
            pass

    def _terminate_runtime(self) -> None:
        self._terminate_process()

    def _provision_runtime(self) -> None:
        self._set_state("flashing")
        prepared = self.service.prepare_flash(
            self.spec,
            self.firmware_path,
            self.firmware_sha,
            runtime=self.runtime,
        )
        self._check_cancelled()
        self.virtual_flash = self.dir / "virtual-flash.bin"
        shutil.copyfile(prepared["path"], self.virtual_flash)
        self._check_cancelled()
        self.flash_info = {
            **prepared["info"],
            "session_isolated_copy": True,
        }
        self._record_event("flash_prepared", **self.flash_info)
        if self.storage_config:
            artifact_id = self.storage_config["sd_image_artifact_id"]
            source = self.service.artifacts.path(artifact_id)
            shutil.copyfile(source, self.sd_card_image)
            self._check_cancelled()
            storage_sha = hashlib.sha256(
                self.sd_card_image.read_bytes()
            ).hexdigest()
            if storage_sha != artifact_id:
                raise RuntimeError(
                    "session-isolated SD image checksum changed"
                )
            self.storage_info = {
                "interface": "sdmmc",
                "format": "raw",
                "artifact_id": artifact_id,
                "sha256": storage_sha,
                "bytes": self.sd_card_image.stat().st_size,
                "session_isolated_copy": True,
                "writable": True,
            }
            atomic_write_json(
                self.storage_summary_path,
                self.storage_info,
            )
            self._record_event("storage_prepared", **self.storage_info)
        if (
            self.nvs_config
            and self.runtime not in QEMU_RADIO_RUNTIMES
        ):
            self._apply_nvs_fixture()
        self._persist_session()
        self._set_state("booting")
        if self.runtime in QEMU_RADIO_RUNTIMES:
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
        if self.program_bootstrap:
            self._probe_program_loader()
        self._set_state("running")

    def _provision_qemu_radio(self, clean_flash: Path) -> None:
        attempts = int(self.network_config.get("attempts", 5))
        last_error: ServiceError | None = None
        for attempt in range(1, attempts + 1):
            self._check_cancelled()
            if attempt > 1:
                if self.virtual_flash is None:
                    self.virtual_flash = self.dir / "virtual-flash.bin"
                shutil.copyfile(clean_flash, self.virtual_flash)
                self._check_cancelled()
            self._apply_nvs_fixture()
            self._check_cancelled()
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
                    in {
                        CORE2_HCI_GATT_PROFILE,
                        NANOC6_HCI_BLE_PROFILE,
                        NESSO_UNIFIED_PROFILE,
                        *UNIFIED_PROFILES,
                    }
                ):
                    self._wait_hci_probe_result(self.ready_timeout)
                self.network_result = self.network_evidence()
                self._record_event(
                    "qemu_radio_attempt",
                    attempt=attempt,
                    status="PASS",
                )
                return
            except SessionCancelled:
                raise
            except ServiceError as error:
                self._check_cancelled()
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
                    self.native_vhci_log,
                    self.stdout_path,
                    self.stderr_path,
                    self.network_pcap,
                    self.network_pcap_summary,
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
        # Reconnect workloads can legitimately exceed the legacy 30-second
        # single-cycle budget. The session's ready timeout bounds the wait.
        deadline = time.time() + max(1.0, timeout)
        while time.time() < deadline:
            self._check_cancelled()
            text = (
                self.hci_probe_log.read_text(errors="replace")
                if self.hci_probe_log.is_file()
                else ""
            )
            pass_marker="BLE_PERIPHERAL_PASS" if self.network_config.get("ble_peer_role")=="peripheral" else "BLE_BUMBLE_PASS"
            if pass_marker in text:
                self._record_event("ble_peer_pass")
                return
            if "BLE_BUMBLE_FAIL" in text or "BLE_BUMBLE_ERROR" in text or "BLE_PERIPHERAL_FAIL" in text:
                raise ServiceError(
                    "ble_peer_failed",
                    "external BLE peer did not complete the GATT exchange",
                    409,
                )
            if not self._hci_probe_running():
                raise ServiceError(
                    "ble_peer_failed",
                    "external BLE peer exited before GATT completion",
                    409,
                )
            self._stop_event.wait(0.1)
        raise ServiceError(
            "ble_peer_failed",
            "timed out waiting for external BLE peer completion",
            408,
        )

    def _hci_probe_running(self) -> bool:
        if self._hci_probe is not None:
            return self._hci_probe.poll() is None
        if self._external_hci_probe_pid is None:
            return False
        return self._companion_process_matches(
            self._external_hci_probe_pid,
            str(self._external_hci_probe_start_token or ""),
            str(self._external_hci_probe_command_sha256 or ""),
        )

    def _hci_probe_command(self) -> tuple[list[str], dict[str, str]]:
        if not BLE_PROBE.is_file():
            raise RuntimeError(f"BLE probe is missing: {BLE_PROBE}")
        profile = self.network_config.get("profile")
        unified = profile in UNIFIED_PROFILES
        nanoc6_hci = profile == NANOC6_HCI_BLE_PROFILE
        c6_hci = nanoc6_hci or profile == NESSO_UNIFIED_PROFILE
        extended_exchange = unified or c6_hci
        if unified:
            name_prefix, payload = UNIFIED_BLE_IDENTITIES[self.spec.id]
        elif nanoc6_hci:
            name_prefix, payload = NANOC6_BLE_IDENTITY
        elif profile == NESSO_UNIFIED_PROFILE:
            name_prefix, payload = NESSO_BLE_IDENTITY
        else:
            name_prefix = "M5-CORE2-HCI"
            payload = "M5_CORE2_HCI"
        self.hci_port = free_tcp_port()
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                [
                    str(os.environ.get("M5_PYTHON_DEPS") or ROOT / ".work/py"),
                    env.get("PYTHONPATH", ""),
                ],
            )
        )
        if c6_hci or profile in {
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
        }:
            env["BLE_HCI_TRACE"] = "1"
        command = [
            sys.executable,
            str(BLE_PROBE),
            "--role",
            self.network_config.get("ble_peer_role","central"),
            "--port",
            str(self.hci_port),
            "--name-prefix",
            name_prefix,
            "--payload",
            payload,
            "--subscribe",
            "--expect-notification-prefix",
            "ACK:",
            "--gatt-request-timeout",
            "30" if extended_exchange else "10",
            "--notification-timeout",
            "30" if extended_exchange else "10",
            "--timeout",
            (
                str(int(ble_peer_scan_timeout_seconds(self.ready_timeout)))
                if extended_exchange
                else "25"
            ),
            "--write-delay",
            "2" if extended_exchange else "1",
            "--linger",
            str(
                self.network_config.get(
                    "ble_linger_seconds",
                    20 if unified else 15,
                )
            ),
            "--reconnect-cycles",
            str(self.network_config.get("ble_reconnect_cycles", 1)),
            "--reconnect-delay",
            str(
                self.network_config.get(
                    "ble_reconnect_delay_seconds",
                    2,
                )
            ),
        ]
        if self.network_config.get("ble_post_pass_continuity"):
            command.extend(
                [
                    "--post-pass-trigger",
                    str(self.dir / "ble-continuity.trigger"),
                    "--post-pass-trigger-timeout",
                    str(self.ready_timeout),
                ]
            )
        return command, env

    def _launch_hci_probe(self) -> None:
        self._check_cancelled()
        command, env = self._hci_probe_command()
        output = self.hci_probe_log.open("wb")
        try:
            self._check_cancelled()
            self._hci_probe = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._check_cancelled()
        finally:
            output.close()
        deadline = time.time() + 10
        while time.time() < deadline:
            self._check_cancelled()
            if (
                self.hci_probe_log.is_file()
                and "BLE_PROBE_READY"
                in self.hci_probe_log.read_text(errors="replace")
            ):
                assert self._hci_probe is not None
                identity = inspect_process(self._hci_probe.pid)
                command = identity.get("command")
                start_token = identity.get("start_token")
                if (
                    not identity["exists"]
                    or not isinstance(command, str)
                    or not isinstance(start_token, str)
                ):
                    raise ServiceError(
                        "ble_peer_failed",
                        "external BLE peer ownership could not be inspected",
                        503,
                    )
                command_sha256 = hashlib.sha256(
                    command.encode()
                ).hexdigest()
                self._update_companion(
                    "ble",
                    kind="ble-probe",
                    state="running",
                    pid=self._hci_probe.pid,
                    start_token=start_token,
                    command_sha256=command_sha256,
                    port=self.hci_port,
                    ownership_verified=True,
                    adopted=False,
                    recovery_action="adopt-on-restart",
                    continuity_trigger=(
                        "ble-continuity.trigger"
                        if self.network_config.get(
                            "ble_post_pass_continuity"
                        )
                        else None
                    ),
                    started_at=iso_now(),
                )
                self._record_event(
                    "hci_probe_started",
                    pid=self._hci_probe.pid,
                )
                self._persist_session()
                return
            if self._hci_probe.poll() is not None:
                raise ServiceError(
                    "ble_peer_failed",
                    "external BLE peer exited during startup",
                    503,
                )
            self._stop_event.wait(0.05)
        raise ServiceError(
            "ble_peer_failed",
            "external BLE peer did not become ready",
            504,
        )

    def _launch_native_vhci_gdb(self) -> None:
        self._check_cancelled()
        if self.hci_port is None or self.gdb_port is None:
            raise RuntimeError("native VHCI ports are not allocated")
        elf_artifact_id = self.network_config.get("elf_artifact_id")
        if not elf_artifact_id:
            raise RuntimeError("native VHCI ELF artifact is missing")
        command = [
            str(native_vhci_gdb_path()),
            "-q",
            "-batch",
            "-x",
            str(NATIVE_VHCI_GDB_SCRIPT),
        ]
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
        env["M5_NATIVE_BT_HCI_PORT"] = str(self.hci_port)
        env["M5_NATIVE_GDB_PORT"] = str(self.gdb_port)
        elf_path = self.service.artifacts.path(str(elf_artifact_id))
        env["M5_NATIVE_BT_ELF"] = str(elf_path)
        try:
            symbols = core2_native_vhci_addresses(elf_path)
        except ElfSymbolError as error:
            raise ServiceError(
                "native_bt_elf_invalid",
                f"native VHCI ELF symbols are unavailable: {error}",
                409,
            ) from error
        env.update(
            {
                name: f"0x{value:08x}"
                for name, value in symbols.items()
            }
        )
        self._record_event(
            "native_vhci_symbols",
            **symbols,
        )
        output = self.native_vhci_log.open("wb")
        try:
            self._check_cancelled()
            self._native_vhci_gdb = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._check_cancelled()
        finally:
            output.close()
        deadline = time.time() + 10
        while time.time() < deadline:
            self._check_cancelled()
            if (
                self.native_vhci_log.is_file()
                and "NATIVE_VHCI_BRIDGE_READY"
                in self.native_vhci_log.read_text(errors="replace")
            ):
                self._record_event(
                    "native_vhci_bridge_started",
                    pid=self._native_vhci_gdb.pid,
                )
                return
            if self._native_vhci_gdb.poll() is not None:
                raise ServiceError(
                    "native_bt_backend_unavailable",
                    "native VHCI GDB bridge exited during startup",
                    503,
                )
            self._stop_event.wait(0.05)
        raise ServiceError(
            "native_bt_backend_unavailable",
            "native VHCI GDB bridge did not become ready",
            504,
        )

    def _launch_http_fixture(self, *, recover: bool = False) -> None:
        self._check_cancelled()
        profile = self.network_config.get("profile")
        body = UNIFIED_HTTP_BODIES.get(profile)
        port = UNIFIED_HTTP_PORTS.get(profile)
        if body is None or port is None:
            raise ServiceError(
                "http_fixture_failed",
                f"no controlled HTTP port for profile {profile}",
                500,
            )
        previous = self._companions.get("http", {})
        previous_generation = previous.get("generation", 0)
        if recover:
            if (
                not isinstance(previous_generation, int)
                or isinstance(previous_generation, bool)
                or previous_generation < 1
            ):
                raise ServiceError(
                    "companion_recovery_failed",
                    "HTTP fixture generation metadata is invalid",
                    409,
                )
            seed_requests = self._read_http_fixture_requests()
            generation = previous_generation + 1
        else:
            seed_requests = []
            generation = 1
        try:
            self._check_cancelled()
            self._http_fixture = UnifiedHttpFixture(
                self.http_fixture_log,
                body=body,
                port=port,
                seed_requests=seed_requests,
                generation=generation,
            )
            self._check_cancelled()
        except OSError as error:
            raise ServiceError(
                "http_fixture_failed",
                f"controlled HTTP fixture could not start: {error}",
                503,
            ) from error
        self._update_companion(
            "http",
            kind="in-process-http-fixture",
            state="recovered" if recover else "running",
            pid=os.getpid(),
            port=port,
            generation=generation,
            ownership_verified=True,
            adopted=False,
            recovery_action="recreate" if recover else "keep-running",
            recovered_at=iso_now() if recover else None,
            started_at=iso_now(),
        )
        self._record_event(
            "http_fixture_recovered" if recover else "http_fixture_started",
            port=port,
            generation=generation,
        )
        self._persist_session()

    def _configure_guestfwd_http_fixture(self) -> str:
        profile = self.network_config.get("profile")
        body = UNIFIED_HTTP_BODIES.get(profile)
        port = UNIFIED_HTTP_PORTS.get(profile)
        if body is None or port is None:
            raise ServiceError(
                "http_fixture_failed",
                f"no controlled HTTP port for profile {profile}",
                500,
            )
        self.http_fixture_log.unlink(missing_ok=True)
        command = [
            sys.executable,
            str(UNIFIED_HTTP_GUESTFWD),
            "--log",
            str(self.http_fixture_log),
            "--body-hex",
            body.hex(),
        ]
        self._update_companion(
            "http",
            kind="qemu-guestfwd-command",
            state="running",
            pid=None,
            port=port,
            generation=1,
            ownership_verified=True,
            adopted=False,
            recovery_action="qemu-process-owned",
            started_at=iso_now(),
        )
        self._record_event(
            "http_guestfwd_configured",
            port=port,
            generation=1,
        )
        self._persist_session()
        return shlex.join(command)

    def _prepare_stackchan_peripheral_inputs(self) -> None:
        commands = (
            (
                ROOT / "tests/uiflow2/make_pcm_tone.py",
                str(self.microphone_source_pcm),
                "--frequency",
                "440",
                "--sample-rate",
                "16000",
                "--seconds",
                "1",
                "--amplitude",
                "12000",
            ),
            (
                ROOT / "tests/uiflow2/make_rmt_nec.py",
                str(self.rmt_source),
                "--address",
                "0x56",
                "--command",
                "0xa3",
            ),
        )
        for arguments in commands:
            result = subprocess.run(
                [sys.executable, *(str(item) for item in arguments)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "StackChan fixture generation failed: "
                    + result.stdout.strip()
                )
        self._record_event("stackchan_peripheral_inputs_prepared")

    def _prepare_microphone_tone(self, label: str, event: str, *, channels: int = 1) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/uiflow2/make_pcm_tone.py"),
                str(self.microphone_source_pcm),
                "--frequency",
                "440",
                "--sample-rate",
                "16000",
                "--seconds",
                "1",
                "--amplitude",
                "12000",
                "--channels",
                str(channels),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                label + " fixture generation failed: " + result.stdout.strip()
            )
        self._record_event(event)

    def _prepare_core2_peripheral_inputs(self) -> None:
        self._prepare_microphone_tone("Core2", "core2_peripheral_inputs_prepared")

    def _plain_qemu_audio_enabled(self) -> bool:
        return self.runtime == "qemu" and self.spec.id in PLAIN_QEMU_AUDIO_DEVICES

    def _plain_qemu_audio_environment(self, env: dict[str, str]) -> None:
        if not self._plain_qemu_audio_enabled():
            return
        # Do not inherit another session's output/input paths from the server
        # shell. Existing explicit diagnostic runtime_env overrides are kept.
        defaults = {
            "M5SW_I2S_DMA_IRQ": "1",
            "M5SW_I2S_PCM_FILE": str(self.speaker_pcm),
            "M5SW_I2S_RX_PCM_FILE": str(self.microphone_source_pcm),
        }
        for key, value in defaults.items():
            env[key] = self.runtime_env.get(key, value)

    def _qemu_storage_environment(self, env: dict[str, str]) -> None:
        # The SPI SD model opens this path itself; -drive if=sd only feeds the
        # SoC SDMMC model. Never inherit an unrelated host/session disk path.
        env.pop("M5SW_SPI_SD_IMAGE", None)
        if self.storage_config:
            env["M5SW_SPI_SD_IMAGE"] = str(self.sd_card_image)

    def _apply_profile_qom(
        self,
        marker: str,
        profile: str,
        setup: tuple[tuple[str, str, Any], ...],
        pause: bool = True,
    ) -> None:
        deadline = time.time() + 20
        while time.time() < deadline:
            self._check_cancelled()
            serial = (
                self.serial0.read_text(errors="replace")
                if self.serial0.is_file()
                else ""
            )
            if marker in serial:
                break
            if self._proc is None or self._proc.poll() is not None:
                raise ServiceError(
                    "session_exited",
                    f"device exited before marker {marker!r}",
                    409,
                )
            self._stop_event.wait(0.05)
        else:
            raise ServiceError(
                "qom_timeout",
                f"timed out waiting for marker {marker!r}",
                408,
            )
        assert self._qmp is not None
        try:
            if pause:
                self._qmp.cmd("stop")
            for path, prop, value in setup:
                self._qmp.cmd("qom-set", path=path, property=prop, value=value)
            if pause:
                self._qmp.cmd("cont")
        except (OSError, RuntimeError) as error:
            if pause:
                try:
                    self._qmp.cmd("cont")
                except (OSError, RuntimeError):
                    pass
            raise ServiceError(
                "qom_error",
                f"{profile} runtime state injection failed: {error}",
                503,
            ) from error
        self._record_event(
            "profile_qom_applied",
            profile=profile,
            property_count=len(setup),
        )

    def _exercise_nanoc6_button(self) -> None:
        def wait_for_serial(marker: str, timeout: float = 10) -> None:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if (
                    self.serial0.is_file()
                    and marker in self.serial0.read_text(errors="replace")
                ):
                    return
                if self._proc is None or self._proc.poll() is not None:
                    raise ServiceError(
                        "session_exited",
                        "NanoC6 QEMU exited before button input injection",
                        409,
                    )
                time.sleep(0.05)
            raise ServiceError(
                "ready_timeout",
                f"NanoC6 serial marker timed out: {marker}",
                408,
            )

        wait_for_serial("NANOC6_HCI_BUTTON_READY")
        self._qmp_call(
            "qom-set",
            path="/machine",
            property="button-gpio9",
            value=True,
        )
        wait_for_serial("NANOC6_HCI_BUTTON_PRESS")
        self._qmp_call(
            "qom-set",
            path="/machine",
            property="button-gpio9",
            value=False,
        )
        wait_for_serial("NANOC6_HCI_BUTTON_RELEASE")
        self._record_event("nanoc6_button_input", press=True, release=True)

    def _exercise_nesso_unified(self) -> None:
        def wait_for_serial(marker: str, timeout: float = 20) -> None:
            deadline = time.time() + timeout
            while time.time() < deadline:
                if (
                    self.serial0.is_file()
                    and marker in self.serial0.read_text(errors="replace")
                ):
                    return
                if self._proc is None or self._proc.poll() is not None:
                    raise ServiceError(
                        "session_exited",
                        "Nesso QEMU exited before unified input injection",
                        409,
                    )
                time.sleep(0.05)
            raise ServiceError(
                "ready_timeout",
                f"Nesso serial marker timed out: {marker}",
                408,
            )

        wait_for_serial("UNIFIED_NESSO_IO_CONFIG_READY", timeout=40)
        for path, prop, value in (
            ("/machine/nesso-bq27220", "battery-mv", 4300),
            ("/machine/nesso-bq27220", "current-ma", 250),
            ("/machine/nesso-bq27220", "battery-level", 96),
            ("/machine/nesso-aw32001", "charging", True),
            ("/machine/nesso-bmi270", "accel-x", 0.25),
            ("/machine/nesso-bmi270", "accel-y", -0.50),
            ("/machine/nesso-bmi270", "accel-z", 0.75),
            ("/machine/nesso-bmi270", "gyro-x", 10),
            ("/machine/nesso-bmi270", "gyro-y", -20),
            ("/machine/nesso-bmi270", "gyro-z", 30),
        ):
            self._qmp_call(
                "qom-set",
                path=path,
                property=prop,
                value=value,
            )
        wait_for_serial("UNIFIED_NESSO_READY", timeout=60)
        before = self.frame_metrics(force_persist=True)
        send_input(self._qmp, "touch:67,175", (135, 240), 1.0)
        send_input(self._qmp, "key:a", (135, 240), 0.8)
        wait_for_serial("UNIFIED_NESSO_TOUCH")
        wait_for_serial("UNIFIED_NESSO_BUTTON 1")
        after = self.frame_metrics(force_persist=True)
        self.unified_frame_changed = before["png"] != after["png"]
        self._record_event(
            "nesso_unified_input",
            touch=True,
            button=True,
            frame_changed=self.unified_frame_changed,
        )

    def _launch(self) -> None:
        self._check_cancelled()
        assert self.virtual_flash is not None
        efuse = self.dir / "efuse.bin"
        efuse_data = bytearray(4096)
        # The device matrix uses the same package-version encoding as the
        # existing profile runner.
        if "efuse_pkg_version" in self.service.raw_device(self.spec.id):
            pkg = int(self.service.raw_device(self.spec.id)["efuse_pkg_version"])
            efuse_data[36:40] = (pkg << 21).to_bytes(4, "little")
        espnow_peer_lane = (
            "M5SW_ESPNOW_PEER_LOCAL_PORT" in self.runtime_env
            and "M5SW_ESPNOW_PEER_REMOTE_PORT" in self.runtime_env
        )
        peer_mac_lane = (
            espnow_peer_lane
            and self.spec.backend in {"qemu-esp32s3", "qemu-esp32lx6"}
        )
        wifi_mac = (
            qemu_station_mac(self.id)
            if peer_mac_lane
            or (
                self.spec.backend == "qemu-esp32s3"
                and self.network_config.get("wifi_auth") == "wpa2-psk"
            )
            else None
        )
        if wifi_mac:
            if self.spec.backend == "qemu-esp32s3":
                set_s3_efuse_mac(efuse_data, wifi_mac)
            elif self.spec.backend == "qemu-esp32lx6":
                set_esp32_efuse_mac(efuse_data, wifi_mac)
        if self.spec.backend == "qemu-esp32s3":
            adc_path = None
            adc_raw = None
            if any(unit["unit_id"] in {"angle", "light"} for unit in self.units):
                frozen = (self.unit_contract or {}).get("fixtures", {}).get("esp32s3-adc")
                if frozen:
                    adc_raw = frozen["raw_utf8"].encode("utf-8")
                    if hashlib.sha256(adc_raw).hexdigest() != frozen["sha256"]:
                        raise ServiceError("runtime_model_gap", "frozen ADC fixture hash mismatch", 409)
                    adc_path = UNIT_ADC_FIXTURE
            elif self.spec.id == "cardputer-adv":
                adc_path = CARDPUTER_FIXTURE
            if adc_path is not None:
                fixture = load_adc_fixture(path=adc_path, raw=adc_raw)
                fixture_bytes = adc_raw if adc_raw is not None else adc_path.read_bytes()
                firmware = self.firmware_path.read_bytes()
                try:
                    verify_adc_firmware(firmware, fixture)
                except ValueError:
                    receipt = {
                        "schema_version": 1, "status": "not-applied",
                        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
                        "reason": "application bytes do not match the synthetic calibration profile; raw ADC remains available",
                        "hardware_validation": False,
                    }
                else:
                    calibration_args = {
                        "backend": self.spec.backend,
                        "firmware": firmware,
                        "fixture_path": adc_path,
                    }
                    if adc_raw is not None:
                        calibration_args["fixture_raw"] = adc_raw
                    receipt = {
                        **apply_s3_adc_calibration(efuse_data, **calibration_args),
                        "status": "applied",
                    }
                atomic_write_json(self.unit_adc_calibration_path, receipt)
        efuse.write_bytes(efuse_data)
        try:
            self.qmp_path.unlink()
        except FileNotFoundError:
            pass
        unified = self.network_config.get("profile") in UNIFIED_PROFILES
        core2_radio = (
            self.spec.id == "core2"
            and self.runtime in QEMU_RADIO_RUNTIMES
        )
        qemu_path = (
            core2_radio_qemu_path()
            if core2_radio
            else self.spec.qemu
        )
        profile = self.network_config.get("profile")
        native_vhci = profile == CORE2_NATIVE_VHCI_PROFILE
        native_hci = profile == CORE2_NATIVE_HCI_PROFILE
        native_bt = native_vhci or native_hci
        policy = NetworkPolicy.from_mapping(
            self.network_config.get("policy")
        )
        isolated = policy.isolation == "namespace"
        hci_gatt = (
            self.runtime in {QEMU_BLE_RUNTIME, QEMU_UNIFIED_RUNTIME}
            and profile
            in {
                CORE2_HCI_GATT_PROFILE,
                NANOC6_HCI_BLE_PROFILE,
                NESSO_UNIFIED_PROFILE,
                *UNIFIED_PROFILES,
            }
        )
        guestfwd_http_command: str | None = None
        ble_probe_command: list[str] | None = None
        ble_probe_env: dict[str, str] = {}
        if hci_gatt and not isolated:
            self._launch_hci_probe()
        elif hci_gatt:
            ble_probe_command, ble_probe_env = self._hci_probe_command()
        if self._requires_http_fixture() and not isolated:
            if profile == CORE2_NATIVE_HCI_PROFILE:
                guestfwd_http_command = (
                    self._configure_guestfwd_http_fixture()
                )
            else:
                self._launch_http_fixture()
        if profile == STACKCHAN_UNIFIED_PROFILE:
            self._prepare_stackchan_peripheral_inputs()
        elif profile in {
            CORE2_UNIFIED_PROFILE,
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
        }:
            self._prepare_core2_peripheral_inputs()
        elif self._plain_qemu_audio_enabled():
            self._prepare_microphone_tone(
                self.spec.id, "plain_qemu_audio_inputs_prepared",
                channels=2 if self.spec.id == "cores3" else 1,
            )
        if native_vhci:
            self.gdb_port = free_tcp_port()
        command = [
            str(qemu_path),
            "-M", self.spec.machine,
            "-drive", f"file={self.virtual_flash},if=mtd,format=raw",
            "-L", str(self.spec.rom_dir),
            "-display", "none",
        ]
        if native_vhci:
            command[1:1] = [
                "-S",
                "-gdb",
                f"tcp::{self.gdb_port}",
            ]
        if self.spec.id == "core2":
            # Ordinary board sessions run the same dual-core guest and timers
            # as radio sessions; both need the deterministic LX6 clock.
            command.extend(core2_accel_args())
        if self.storage_config:
            if not self.sd_card_image.is_file():
                raise RuntimeError("session SD image is unavailable")
            command.extend(
                [
                    "-drive",
                    f"file={self.sd_card_image},if=sd,format=raw",
                ]
            )
        if profile in {NANOC6_HCI_BLE_PROFILE, NESSO_UNIFIED_PROFILE}:
            assert self.hci_port is not None
            command.extend(
                [
                    "-serial",
                    "null",
                    "-chardev",
                    (
                        "socket,id=hci,host=127.0.0.1,"
                        f"port={self.hci_port},nodelay=on"
                    ),
                    "-serial",
                    "chardev:hci",
                    "-serial",
                    f"file:{self.serial0}",
                ]
            )
        elif native_hci:
            assert self.hci_port is not None
            elf_artifact_id = self.network_config.get("elf_artifact_id")
            if not elf_artifact_id:
                raise RuntimeError("native HCI ELF artifact is missing")
            try:
                native_hci_device = core2_native_hci_device_args(
                    self.service.artifacts.path(str(elf_artifact_id))
                )
            except ElfSymbolError as error:
                raise ServiceError(
                    "native_bt_elf_invalid",
                    f"native HCI ELF symbols are unavailable: {error}",
                    409,
                ) from error
            command.extend(
                [
                    "-serial",
                    f"file:{self.serial0}",
                    "-serial",
                    f"file:{self.serial1}",
                    "-chardev",
                    (
                        "socket,id=hci,host=127.0.0.1,"
                        f"port={self.hci_port},server=off,nodelay=on"
                    ),
                    "-device",
                    native_hci_device,
                ]
            )
        else:
            if self.program_transport == "uart-repl":
                # Start paused: the unique reader must own the socket before
                # any guest UART output, including the initial REPL banner.
                command.extend([
                    "-S", "-chardev",
                    f"socket,id=program-console,path={self.console_path},server=on,wait=off",
                    "-serial", "chardev:program-console",
                ])
            else:
                command.extend(["-serial", f"file:{self.serial0}"])
            if hci_gatt and not native_bt:
                assert self.hci_port is not None
                if profile == STACKCHAN_UNIFIED_PROFILE:
                    command.extend(["-serial", f"file:{self.serial1}"])
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
        nic: str | None = None
        if self.runtime == QEMU_WIFI_RUNTIME or unified:
            configured_nic = self.network_config.get("nic")
            if configured_nic:
                nic = configured_nic
            else:
                s3_wifi = (
                    unified
                    or self.network_config.get("profile")
                    == STICKS3_WIFI_PROFILE
                )
                nic = (
                    "misc.esp32s3.wifi"
                    if s3_wifi
                    else "misc.esp32_wifi"
                )
            command.extend(
                [
                    "-nic",
                    qemu_user_netdev(
                        nic=nic,
                        policy=policy,
                        mac=wifi_mac,
                        guest_forwards=(
                            [
                                (
                                    "tcp:10.0.2.2:"
                                    f"{UNIFIED_HTTP_PORTS[profile]}"
                                    f"-cmd:{guestfwd_http_command}"
                                )
                            ]
                            if guestfwd_http_command is not None
                            else None
                        ),
                    ),
                ]
            )
            if self.network_config.get("capture_pcap", False):
                self.network_pcap.unlink(missing_ok=True)
                self.network_pcap_summary.unlink(missing_ok=True)
                command.extend(qemu_pcap_options(self.network_pcap))
        if self.spec.efuse_driver != "none":
            command.extend(
                [
                    "-drive", f"if=none,id=efuse,file={efuse},format=raw",
                    "-global",
                    f"driver={self.spec.efuse_driver},property=drive,value=efuse",
                ]
            )
        # Keep the memory policy explicit: native-controller profiles request
        # `-m 0`, while other QEMU devices use their declared emulated PSRAM
        # size. The m5core2 machine resolves `-m 0` to its 8 MiB default, so
        # evidence reports the QOM-effective value separately. Board inventory
        # size is not a runtime-memory claim, and neither setting proves
        # physical cache/PSRAM timing.
        if self.spec.memory is not None or native_bt:
            command.extend(
                [
                    "-m",
                    "0" if native_bt else str(self.spec.memory),
                ]
            )
        env = os.environ.copy()
        env.update(self.spec.env)
        env.update(self.runtime_env)
        self._plain_qemu_audio_environment(env)
        self._qemu_storage_environment(env)
        # Never inherit another session's external wiring from the host shell.
        env.pop("M5_UNIT_CONFIG", None)
        if self.units:
            atomic_write_json(self.unit_config_path, {
                "schema_version": 1, "attachments": self.units,
            })
            env["M5_UNIT_CONFIG"] = str(self.unit_config_path)
        if nic == "misc.esp32s3.wifi":
            env["M5SW_WIFI_SSID"] = str(
                self.network_config.get("wifi_ssid", "myssid")
            )
            env["M5SW_WIFI_PASSWORD"] = str(
                self.network_config.get("wifi_password", "")
            )
            env["M5SW_WIFI_AUTH"] = str(
                self.network_config.get("wifi_auth", "open")
            )
            if self.network_config.get("wifi_auth") == "wpa2-psk":
                env["M5SW_S3_WIFI_TRACE"] = "1"
        if unified:
            env["M5SW_I2S_DMA_IRQ"] = "1"
            env["M5SW_I2S_PCM_FILE"] = str(self.speaker_pcm)
        if native_hci:
            env["M5_NATIVE_HCI_TRACE"] = "1"
        if profile == STACKCHAN_UNIFIED_PROFILE:
            env["M5SW_I2S_RX_PCM_FILE"] = str(self.microphone_source_pcm)
            env["M5SW_RMT_RX_FILE"] = str(self.rmt_source)
            env["M5SW_RMT_TX_FILE"] = str(self.rmt_capture)
            env["M5SW_RMT_TRACE"] = "1"
        if profile == STAMPLC_UNIFIED_PROFILE:
            env["M5SW_CAN_ECHO"] = "1"
            env["M5SW_RS485_ECHO"] = "1"
        if profile in {
            CORE2_UNIFIED_PROFILE,
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
        }:
            env["M5SW_I2S_RX_PCM_FILE"] = str(self.microphone_source_pcm)
        if profile == NANOC6_HCI_BLE_PROFILE:
            env["M5SW_RMT_TX_FILE"] = str(self.rmt_capture)
            env["M5SW_RMT_TRACE"] = "1"
        if profile == NESSO_UNIFIED_PROFILE:
            env["M5SW_I2S_PCM_FILE"] = str(self.speaker_pcm)
            env["M5SW_RMT_TX_FILE"] = str(self.rmt_capture)
            env["M5SW_RMT_TRACE"] = "1"
            env["M5SW_SX1262_TRACE"] = "1"
        launch_command = command
        if isolated:
            sandbox_config: dict[str, Any] = {
                "policy": policy.evidence(),
            }
            control_tcp_ports = sorted(
                {
                    port
                    for port in (self.hci_port, self.gdb_port)
                    if port is not None
                }
            )
            if control_tcp_ports:
                sandbox_config["control"] = {
                    "tcp_ports": control_tcp_ports,
                }
            if policy.dns == "controlled":
                cname_records = (
                    self.network_config.get("cname_records", {})
                    if isinstance(
                        self.network_config.get("cname_records", {}),
                        dict,
                    )
                    else {}
                )
                dns_hosts = {
                    host: "10.0.2.2"
                    for host in policy.allowed_hosts
                    if host not in cname_records
                }
                dns_domain_records = {
                    domain: ["10.0.2.2"]
                    for domain in policy.allowed_domains
                }
                sandbox_config["dns"] = {
                    "mode": "controlled",
                    "host": "127.0.0.1",
                    "port": 53,
                    "hosts": dns_hosts,
                    "domain_records": dns_domain_records,
                    "cname_records": cname_records,
                    "log": str(self.dns_fixture_log),
                }
            if http_profile:
                http_body = UNIFIED_HTTP_BODIES.get(profile)
                http_port = UNIFIED_HTTP_PORTS.get(profile)
                if http_body is None or http_port is None:
                    raise ServiceError(
                        "http_fixture_failed",
                        f"no controlled HTTP port for profile {profile}",
                        500,
                    )
                http_fixture: dict[str, Any] = {
                    "port": http_port,
                    "body": http_body.decode(),
                    "log": str(self.http_fixture_log),
                }
                if policy.allowed_hosts:
                    http_fixture["allowed_hosts"] = list(
                        policy.allowed_hosts
                    )
                if policy.allowed_domains:
                    http_fixture["allowed_domains"] = list(
                        policy.allowed_domains
                    )
                sandbox_config["http"] = http_fixture
            if hci_gatt:
                assert ble_probe_command is not None
                sandbox_config["ble_probe"] = {
                    "command": ble_probe_command,
                    "log": str(self.hci_probe_log),
                    "ready_marker": "BLE_PROBE_READY",
                    "ready_timeout_seconds": 10,
                    "env": {
                        key: value
                        for key, value in ble_probe_env.items()
                        if key == "BLE_HCI_TRACE"
                    },
                }
            sandbox_config_path = self.dir / "network-sandbox.json"
            sandbox_config["isolation_evidence"] = str(
                self.network_isolation_path
            )
            atomic_write_json(sandbox_config_path, sandbox_config)
            try:
                launch_command = build_sandbox_command(
                    command,
                    config_path=sandbox_config_path,
                )
            except NetworkPolicyError as error:
                raise ServiceError(
                    "network_isolation_unavailable",
                    str(error),
                    503,
                ) from error
            self._record_event(
                "network_sandbox_started",
                isolation=policy.isolation,
                egress=policy.egress,
                dns=policy.dns,
                allowed_domains=list(policy.allowed_domains),
            )
        stdout = self.stdout_path.open("wb")
        stderr = self.stderr_path.open("wb")
        try:
            self._check_cancelled()
            self._proc = subprocess.Popen(
                launch_command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
            self._check_cancelled()
        finally:
            stdout.close()
            stderr.close()
        self.pid = self._proc.pid
        identity = inspect_process(self.pid)
        self.process_start_token = (
            str(identity["start_token"])
            if identity["exists"] and identity["start_token"]
            else None
        )
        self._reattached_process = False
        self._persist_session()
        if native_vhci:
            self._launch_native_vhci_gdb()
        with self._lock:
            try:
                # Booting frame/state requests may already own the connection.
                if self._qmp is None:
                    self._qmp = wait_qmp(self.qmp_path, timeout=QMP_START_TIMEOUT)
                self._check_cancelled()
            except RuntimeError as error:
                raise ServiceError(
                    "qmp_timeout",
                    f"QEMU QMP socket did not become ready: {error}",
                    504,
                ) from error
            self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
        if self.program_transport == "uart-repl":
            from guest_console import GuestConsole

            self._console = GuestConsole(self.console_path, self.serial0)
            self._console.connect(timeout=5, cancelled=self._stop_event.is_set)
            self._check_cancelled()
            self._qmp_call("cont")
            self._record_event("program_console_connected", transport="uart-repl")
        self._verify_units_runtime()
        if profile == NANOC6_HCI_BLE_PROFILE:
            self._exercise_nanoc6_button()
        elif profile == NESSO_UNIFIED_PROFILE:
            self._exercise_nesso_unified()
        if profile == STACKCHAN_UNIFIED_PROFILE:
            self._apply_profile_qom(
                "UNIFIED_STACKCHAN_IMU_CONFIG_READY",
                STACKCHAN_UNIFIED_PROFILE,
                STACKCHAN_UNIFIED_QOM,
            )
        elif profile == STAMPLC_UNIFIED_PROFILE:
            self._apply_profile_qom(
                "UNIFIED_STAMPLC_IO_CONFIG_READY",
                STAMPLC_UNIFIED_PROFILE,
                STAMPLC_UNIFIED_QOM,
            )
        elif profile in {
            CORE2_UNIFIED_PROFILE,
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
        }:
            self._apply_profile_qom(
                "UNIFIED_CORE2_IO_CONFIG_READY",
                str(profile),
                CORE2_UNIFIED_QOM,
                pause=False,
            )

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
                if isinstance(error, QMPCommandError) and name == "qom-set" and str(arguments.get("path", "")).startswith("/machine/units/"):
                    # A real controller rejection (for example a full UART RX
                    # FIFO) is an input conflict. The QMP transport is healthy.
                    raise ServiceError("unit_input_rejected", str(error), 409) from error
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

    def _qmp_execute(self, name: str, arguments: dict):
        """Execute a QMP command whose argument names collide with Python."""

        with self._lock:
            if (
                self._proc is None
                or self._proc.poll() is not None
            ):
                raise ServiceError(
                    "session_not_running",
                    "device process is not running",
                    409,
                )
            if self._qmp is None:
                self._qmp = wait_qmp(self.qmp_path, timeout=5)
                self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
            try:
                self._qmp.sock.settimeout(QMP_COMMAND_TIMEOUT)
                request = {
                    "execute": name,
                    "arguments": arguments,
                }
                self._qmp.sock.sendall(
                    (json.dumps(request) + "\n").encode()
                )
                while True:
                    reply = json.loads(self._qmp.readline())
                    if "event" in reply:
                        continue
                    if "error" in reply:
                        raise RuntimeError(reply["error"])
                    return reply
            except (OSError, RuntimeError, ValueError) as error:
                try:
                    self._qmp.close()
                except OSError:
                    pass
                self._qmp = None
                raise ServiceError(
                    "qmp_error",
                    f"QMP command failed: {error}",
                    503,
                ) from error

    def wait_for_marker(self, marker: str, timeout: float) -> dict:
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            self._check_cancelled()
            if self.serial0.exists() and marker in self.serial0.read_text(
                errors="replace"
            ):
                self._check_cancelled()
                self._record_event("serial_marker", marker=marker)
                return self.snapshot()
            if self._proc and self._proc.poll() is not None:
                raise ServiceError(
                    "session_exited",
                    f"device exited before marker {marker!r}",
                    409,
                )
            self._stop_event.wait(0.1)
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
            self._check_cancelled()
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
                self._check_cancelled()
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
                            if key not in {"png", "captured_monotonic"}
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
            self._stop_event.wait(0.75)
        raise ServiceError(
            "ready_timeout",
            "application did not satisfy the requested readiness conditions",
            408,
            serial_markers=found_markers,
        )

    def serial_read(self, offset: int = 0, limit: int = 65536) -> dict:
        limit = min(max(int(limit), 1), MAX_SERIAL_READ)
        with self._lock:
            try:
                with self.serial0.open("rb") as stream:
                    size = stream.seek(0, os.SEEK_END)
                    offset = min(max(int(offset), 0), size)
                    stream.seek(offset)
                    chunk = stream.read(min(limit, size - offset))
            except FileNotFoundError:
                return {
                    "session_id": self.id,
                    "offset": offset,
                    "next_offset": offset,
                    "data": "",
                    "bytes": 0,
                }
        return {
            "session_id": self.id,
            "offset": offset,
            "next_offset": offset + len(chunk),
            "data": chunk.decode("utf-8", errors="replace"),
            "bytes": len(chunk),
        }

    def _program_identity(self) -> dict:
        return {"session_id": self.id, "device_id": self.spec.id,
                "firmware_sha256": self.firmware_sha, "runtime": self.runtime,
                "pid": self.pid, "process_start_token": self.process_start_token,
                "worker_generation": self.worker_generation}

    def program_capabilities(self) -> dict:
        """Resolve this live guest's evidence, never caller or historical claims."""
        identity = self._program_identity()
        record = getattr(self, "_program_capabilities", {})
        process = getattr(self, "_proc", None)
        if (self.state == "running" and self.program_transport == "uart-repl"
                and (process is None or process.poll() is None)
                and type(identity["pid"]) is int and identity["pid"] > 0
                and isinstance(identity["process_start_token"], str) and identity["process_start_token"]
                and record.get("identity") == identity):
            if main_loader_verified(record):
                return json.loads(json.dumps(record))
            if record.get("status") == "unsupported" and record.get("mpy_entrypoint") is False:
                return json.loads(json.dumps(record))
        return {"schema_version": 1, "status": "unknown", "mpy_entrypoint": False, "identity": identity,
                "reason": record.get("reason", "live-loader-evidence-unavailable")}

    def _invalidate_program_loader(self, reason: str) -> None:
        was_verified = main_loader_verified(getattr(self, "_program_capabilities", None))
        self._program_capabilities = {"schema_version": 1, "status": "unknown", "mpy_entrypoint": False, "reason": reason}
        if was_verified:
            self._record_event("program_loader_invalidated", reason=reason)
            self._persist_session()

    @contextmanager
    def program_admission(self):
        """Keep a known loader revocation from racing a Preview intent write."""
        with self._lock:
            yield self.program_capabilities()

    def _check_program_loader_restoration(self, program: dict | None, console, *, prompt_confirmed: bool = False) -> bool:
        if not program or program.get("entrypoint") != "main.mpy":
            return True
        scanner = getattr(self, "_program_scanner", None)
        if scanner is None or scanner.execution_id != program["execution_id"]:
            scanner = ExecutionStateScanner(program["execution_id"], program.get("serial_offset", 0))
        end = console.offset()
        while scanner.cursor < end:
            scanner.scan(console)
        # LOAD is only an import request. Once a fresh raw prompt confirms the
        # binary has stopped, only DONE/ERROR positively prove wrapper cleanup.
        # An actively running import has no terminal marker yet and keeps its
        # proof; cancellation before LOAD never changed the importer owner.
        missing_terminal = prompt_confirmed and scanner.load_requested and scanner.state not in {"completed", "failed"}
        if not scanner.restore_failed and not missing_terminal:
            return True
        with self._lock:
            self._invalidate_program_loader("binary-repl-owner-restoration-unconfirmed")
            program.update(loader_restore_failed=True, owner_restored=False,
                           execution_phase="owner-unconfirmed", state="unknown",
                           error={"code": "program_main_loader_restore_failed", "message": "Binary execution did not confirm its original REPL owner"})
            atomic_write_json(self.dir / "programs" / f"{program['execution_id']}.json", program)
            if self._program is program:
                self._persist_program()
        return False

    def _probe_program_loader(self) -> None:
        """Probe only our inert bootstrap, before public Run becomes available."""
        self._check_cancelled()
        if self._console is None or not self._program_lock.acquire(blocking=False):
            raise UIFlowRuntimeError("program_loader_probe_unavailable", "bootstrap console ownership is unavailable")
        try:
            record = probe_main_loader(self._console, timeout=min(20.0, self.ready_timeout),
                                       cancelled=self._stop_event.is_set)
            self._check_cancelled()
            if (not isinstance(record, dict) or record.get("status") not in {"verified", "unsupported"}
                    or record.get("probe", {}).get("owner_restored") is not True
                    or record.get("status") == "verified" and not main_loader_verified(record)):
                raise UIFlowRuntimeError("program_loader_probe_unconfirmed", "guest loader proof or owner restoration is incomplete")
            self._program_capabilities = {**record, "identity": self._program_identity(), "observed_at": iso_now()}
            atomic_write_json(self.dir / "program-capabilities.json", self._program_capabilities)
            self._record_event("program_loader_observed", capabilities=self._program_capabilities)
        finally:
            self._program_lock.release()

    def _persist_program(self) -> None:
        if self._stop_purge:
            return
        atomic_write_json(self.program_path, self._program)
        atomic_write_json(self.dir / "programs" / f"{self._program['execution_id']}.json", self._program)

    def program_status(self) -> dict:
        from guest_console import GuestConsoleError

        with self._lock:
            program = getattr(self, "_program", None)
            if program is not None and not program.get("cancel_requested") and program["state"] in {"running", "submitting", "unknown"}:
                console = getattr(self, "_console", None)
                if self.state != "running" or console is None:
                    program.update(state="unknown", error={"code": "program_runtime_unverified"})
                    self._persist_program()
                else:
                    scanner = getattr(self, "_program_scanner", None)
                    if scanner is None or scanner.execution_id != program["execution_id"]:
                        scanner = ExecutionStateScanner(program["execution_id"], program.get("serial_offset", 0))
                        self._program_scanner = scanner
                    try:
                        state = scanner.scan(console)
                        if scanner.restore_failed:
                            self._check_program_loader_restoration(program, console)
                            state = None
                        elif program.get("entrypoint") == "main.mpy" and state in {"completed", "failed"}:
                            program.update(owner_restored=True, execution_phase="import-returned" if state == "completed" else "load-or-execute-failed")
                        if state == "running" and program.get("output_gap_possible"):
                            state = "unknown"
                        if state not in {"completed", "failed"}:
                            console.check_alive()
                    except GuestConsoleError as error:
                        state = None
                        program.update(state="unknown", observed_at=iso_now(),
                                       error={"code": error.code, "message": error.message})
                        self._persist_program()
                    if state and state != program["state"]:
                        program.update(state=state, observed_at=iso_now())
                        program.pop("error", None)
                        self._persist_program()
            return {"session_id": self.id, "program_transport": self.program_transport,
                    "program_capabilities": self.program_capabilities(),
                    "program": json.loads(json.dumps(program)),
                    "history_error": self._program_restore_error}

    def run_program(self, payload: dict) -> dict:
        """Run one source checkpoint in the existing MicroPython VM over UART."""
        self.require_management_handle()
        return self._run_program(payload)

    def require_management_handle(self, handle=None) -> None:
        """Trusted internal capability; HTTP must never deserialize a handle."""
        if getattr(self, "management_binding", None) is not None and handle is not self._management_handle:
            raise ServiceError("session_managed_by_preview", "session mutations are managed by its Preview", 409)

    def run_revision(self, revision_id: str, *, execution_id: str, expected_execution_id: str | None,
                     timeout_seconds: float = 120, cancelled=None, on_synchronized=None,
                     management_handle=None) -> dict:
        """Run an existing immutable package using a caller-reserved execution ID."""
        self.require_management_handle(management_handle)
        if not isinstance(execution_id, str) or re.fullmatch(r"[0-9a-f]{32}", execution_id) is None:
            raise ServiceError("invalid_program", "execution_id must be a reserved lowercase UUID hex", 400)
        return self._run_program({"revision_id": revision_id, "expected_execution_id": expected_execution_id,
                                  "timeout_seconds": timeout_seconds}, reserved_execution_id=execution_id,
                                 cancelled=cancelled, on_synchronized=on_synchronized)

    def _run_program(self, payload: dict, *, reserved_execution_id=None, cancelled=None, on_synchronized=None) -> dict:
        from guest_console import GuestConsoleError

        cancellation_seen = False

        def run_cancelled():
            nonlocal cancellation_seen
            if cancelled is not None and cancelled():
                cancellation_seen = True
            return cancellation_seen

        def transport_cancelled():
            return self._stop_event.is_set() or run_cancelled()

        if not isinstance(payload, dict) or sum(key in payload for key in ("source", "files", "revision_id")) != 1:
            raise ServiceError("invalid_program", "exactly one of source, files or revision_id is required", 400)
        reference = "revision_id" in payload
        package = reference or "files" in payload
        allowed = ({"revision_id", "expected_execution_id", "timeout_seconds"} if reference else
                   {"files", "entrypoint", "source_kind", "expected_execution_id", "timeout_seconds"} if package else
                   {"source", "expected_execution_id", "timeout_seconds"})
        if set(payload) - allowed or "expected_execution_id" not in payload:
            raise ServiceError("invalid_program", "invalid program fields or missing expected_execution_id", 400)
        if reference and (not isinstance(payload["revision_id"], str)
                          or re.fullmatch(r"[0-9a-f]{64}", payload["revision_id"]) is None):
            raise ServiceError("invalid_program", "revision_id must be a lowercase SHA256 package ID", 400)
        if not package and not isinstance(payload["source"], str):
            raise ServiceError("invalid_program", "source must be a UTF-8 string", 400)
        source = "" if package else payload["source"]
        try:
            source_size = len(source.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ServiceError("invalid_program", "source must be valid UTF-8", 400) from error
        if source_size > 65536:
            raise ServiceError("program_too_large", "live source execution is limited to 64 KiB", 413)
        timeout = payload.get("timeout_seconds", 120 if package else 10)
        maximum_timeout = 120 if package else 30
        if type(timeout) not in {int, float} or not 1 <= timeout <= maximum_timeout:
            raise ServiceError("invalid_program", f"timeout_seconds must be between 1 and {maximum_timeout}", 400)
        if package and not reference and payload.get("entrypoint", "main.py") == "main.mpy":
            # Known rejection precedes package publication or interruption.
            _require_live_package_entrypoint(payload, self.program_capabilities())
            try:
                _, _, inline_files = program_package_snapshot({key: payload[key] for key in ("files", "entrypoint", "source_kind") if key in payload})
                _validate_checkpoint_bytecode(inline_files)
                if payload.get("entrypoint") == "main.mpy":
                    validate_mpy(inline_files, self.program_capabilities())
            except (ProgramPackageError, UIFlowRuntimeError) as error:
                raise ServiceError(error.code, error.message, getattr(error, "status", 409)) from error
        if not self._program_lock.acquire(blocking=False):
            raise ServiceError("program_busy", "a program transfer already owns this console", 409)
        try:
            if transport_cancelled():
                raise ServiceError("program_cancelled", "session is stopping or stopped", 409)
            if self.state != "running" or self.program_transport != "uart-repl" or self._console is None:
                raise ServiceError("program_transport_unavailable", "a running uart-repl session is required", 409)
            if self._program_restore_error:
                raise ServiceError("program_history_unavailable", self._program_restore_error, 409)
            current_id = self._program["execution_id"] if self._program else None
            if payload["expected_execution_id"] != current_id:
                raise ServiceError("program_generation_conflict", "expected_execution_id is stale", 409)
            if reserved_execution_id is not None and (self.dir / "programs" / f"{reserved_execution_id}.json").exists():
                raise ServiceError("program_execution_conflict", "reserved execution_id already exists; observe it instead of resubmitting", 409,
                                   execution_id=reserved_execution_id)
            try:
                if reference:
                    revision = self.service.program_packages.get(payload["revision_id"])
                    _require_live_package_entrypoint(revision, self.program_capabilities())
                    package_files = self.service.program_packages.read_files(payload["revision_id"])
                    _validate_checkpoint_bytecode(package_files)
                    if revision["entrypoint"] == "main.mpy":
                        validate_mpy(package_files, self.program_capabilities())
                elif package:
                    revision = self.service.program_packages.create({key: payload[key] for key in ("files", "entrypoint", "source_kind") if key in payload})
                    package_files = self.service.program_packages.read_files(revision["revision_id"])
                else:
                    revision = self.service.program_revisions.create({"files": {"main.py": source}})
            except (RevisionError, ProgramPackageError, UIFlowRuntimeError) as error:
                raise ServiceError(error.code, error.message, getattr(error, "status", 409)) from error
            if len(list((self.dir / "programs").glob("*.json"))) >= 256:
                raise ServiceError("program_quota_exceeded", "this session retains at most 256 executions", 429)
            execution_id = reserved_execution_id or uuid.uuid4().hex
            with self._lock:
                # Revision storage may block while stop closes the transport.
                # Re-admit after that work and retain the exact console owner.
                if transport_cancelled():
                    raise ServiceError("program_cancelled", "session is stopping or stopped", 409)
                console = self._console
                if self.state != "running" or console is None:
                    raise ServiceError("program_transport_unavailable", "a running uart-repl session is required", 409)
                if package and revision["entrypoint"] == "main.mpy":
                    _require_live_package_entrypoint(revision, self.program_capabilities())
                previous = self._program
                if self._program and self._program["state"] in {"running", "unknown"}:
                    self._program.update(state="interrupt-requested", interruption_confirmed=False)
                    self._persist_program()
                self._program = {
                    "execution_id": execution_id, "revision_id": revision["revision_id"],
                    "source_sha256": revision["source_sha256"], "source_bytes": len(source.encode("utf-8")),
                    "state": "submitting", "submitted_at": iso_now(),
                    "firmware_sha256": self.firmware_sha, "pid": self.pid,
                    "execution_mode": "same-guest-uart-repl", "cleanup_mode": "interrupt-only",
                    "serial_offset": console.offset(),
                }
                if package:
                    self._program.update(source_kind="uiflow2-package", entrypoint=revision["entrypoint"],
                                         source_bytes=len(package_files[revision["entrypoint"]]),
                                         total_file_bytes=revision["total_file_bytes"], file_count=len(package_files))
                    if revision["entrypoint"] == "main.mpy":
                        self._program.update(loader_capabilities=self.program_capabilities(),
                                             execution_phase="preparing", application_started=None, application_ready=None)
                if reserved_execution_id is not None and previous is not None:
                    self._program["replaces_execution_id"] = previous["execution_id"]
                self._preview_frames.invalidate()
                self._persist_program()
                self._record_event("program_submitted", **self._program)

            synchronization_notified = False

            def synchronized():
                nonlocal synchronization_notified
                if transport_cancelled():
                    raise UIFlowRuntimeError("program_cancelled", "session is stopping")
                if previous and not self._check_program_loader_restoration(previous, console, prompt_confirmed=True):
                    self._record_event("program_previous_owner_unconfirmed", execution_id=previous["execution_id"])
                if previous and previous["state"] == "interrupt-requested":
                    with self._lock:
                        if transport_cancelled():
                            raise UIFlowRuntimeError("program_cancelled", "session is stopping")
                        previous.update(state="interrupted", interruption_confirmed=True, interrupted_at=iso_now())
                        atomic_write_json(self.dir / "programs" / f"{previous['execution_id']}.json", previous)
                if not synchronization_notified and on_synchronized is not None:
                    synchronization_notified = True
                    on_synchronized()

            def package_progress(values):
                with self._lock:
                    if self._stop_purge:
                        raise UIFlowRuntimeError("program_cancelled", "session was purged")
                    deployment = self._program.setdefault("deployment", {})
                    deployment.update(values)
                    deployment.setdefault("events", []).append({**values, "observed_at": iso_now()})
                    self._persist_program()
                    if transport_cancelled():
                        raise UIFlowRuntimeError("program_cancelled", "session is stopping")

            try:
                execution_timeout = float(timeout)
                if package:
                    package_started = time.monotonic()
                    deployment = deploy_package(console, package_files, revision, timeout=execution_timeout,
                                                cancelled=transport_cancelled, on_synchronized=synchronized,
                                                on_progress=package_progress,
                                                **({"loader_capabilities": self.program_capabilities()} if revision["entrypoint"] == "main.mpy" else {}))
                    execution_timeout -= time.monotonic() - package_started
                    if execution_timeout <= 0:
                        raise UIFlowRuntimeError("program_timeout", "package deployment used its execution acknowledgement budget")
                if package and revision["entrypoint"] == "main.mpy":
                    result = run_mpy(console, execution_id, package_path=deployment["package_path"],
                                     entrypoint_sha256=hashlib.sha256(package_files["main.mpy"]).hexdigest(),
                                     loader_capabilities=self.program_capabilities(), timeout=execution_timeout,
                                     cancelled=transport_cancelled, on_synchronized=synchronized)
                else:
                    result = run_source(console, source, execution_id,
                                        timeout=execution_timeout, cancelled=transport_cancelled,
                                        on_synchronized=synchronized,
                                        **({"source_path": "main.py"} if package else {}))
            except (GuestConsoleError, UIFlowRuntimeError) as error:
                with self._lock:
                    if error.code == "program_main_loader_restore_failed":
                        self._invalidate_program_loader("binary-repl-owner-restoration-unconfirmed")
                    if self._stop_purge:
                        raise ServiceError("program_cancelled", "session was purged", 409,
                                           execution_id=execution_id) from error
                    if previous and previous["state"] == "interrupt-requested":
                        previous.update(state="unknown", interruption_confirmed=False)
                        atomic_write_json(self.dir / "programs" / f"{previous['execution_id']}.json", previous)
                    known_package_failure = package and error.code in {
                        "program_mpy_invalid", "program_mpy_incompatible", "program_mpy_native_unsupported",
                        "program_mpy_capability_unknown", "program_package_integrity", "program_package_guest_quota",
                        "program_package_no_space", "program_package_short_write", "program_rpc_failed",
                    }
                    token_cancelled = run_cancelled()
                    self._program.update(state="cancelled" if self._stop_event.is_set() else "interrupt-requested" if token_cancelled else "failed" if known_package_failure else "unknown",
                                         error={"code": error.code, "message": error.message})
                    if token_cancelled:
                        self._program.update(cancel_requested=True, interruption_confirmed=False)
                    self._persist_program()
                    self._record_event("program_unconfirmed", execution_id=execution_id, code=error.code)
                raise ServiceError("program_cancelled" if token_cancelled else error.code, error.message,
                                   409 if self._stop_event.is_set() or token_cancelled or known_package_failure else 504,
                                   execution_id=execution_id) from error
            with self._lock:
                if self._stop_purge:
                    raise ServiceError("program_cancelled", "session was purged", 409,
                                       execution_id=execution_id)
                if self._stop_event.is_set():
                    result["state"] = "cancelled"
                elif run_cancelled():
                    self._program.update(state="interrupt-requested", cancel_requested=True, interruption_confirmed=False,
                                         error={"code": "program_cancelled", "message": "Run cancellation requested; guest interruption is unconfirmed"})
                    self._persist_program()
                    self._record_event("program_unconfirmed", execution_id=execution_id, code="program_cancelled")
                    raise ServiceError("program_cancelled", "Run cancellation requested; guest interruption is unconfirmed", 409,
                                       execution_id=execution_id)
                self._program.update(result, observed_at=iso_now())
                self._persist_program()
                self._record_event("program_observed", execution_id=execution_id, program_state=result["state"])
            return self.program_status()
        finally:
            self._program_lock.release()

    def interrupt_program(self, *, expected_execution_id: str | None, timeout_seconds: float = 10,
                          management_handle=None) -> dict:
        """Independently confirm raw REPL after a cancelled/unknown transaction."""
        from guest_console import GuestConsoleError

        self.require_management_handle(management_handle)
        if type(timeout_seconds) not in {int, float} or not 1 <= timeout_seconds <= 120:
            raise ServiceError("invalid_program", "timeout_seconds must be between 1 and 120", 400)
        if not self._program_lock.acquire(blocking=False):
            raise ServiceError("program_busy", "a program transfer already owns this console", 409)
        try:
            with self._lock:
                if self._stop_event.is_set():
                    raise ServiceError("program_cancelled", "session is stopping or stopped", 409)
                current_id = self._program["execution_id"] if self._program else None
                if current_id != expected_execution_id:
                    raise ServiceError("program_generation_conflict", "expected_execution_id is stale", 409)
                console = self._console
                if self.state != "running" or self.program_transport != "uart-repl" or console is None:
                    raise ServiceError("program_transport_unavailable", "a running uart-repl session is required", 409)
                self._preview_frames.invalidate()
                if self._program:
                    self._program.update(state="interrupt-requested", cancel_requested=True, interruption_confirmed=False)
                    self._persist_program()
            try:
                receipt = synchronize_raw_repl(console, timeout=float(timeout_seconds), cancelled=self._stop_event.is_set)
                if not self._check_program_loader_restoration(self._program, console, prompt_confirmed=True):
                    receipt["owner_restored"] = False
            except (GuestConsoleError, UIFlowRuntimeError) as error:
                with self._lock:
                    if not self._stop_purge and self._program:
                        self._program.update(state="cancelled" if self._stop_event.is_set() else "unknown", interruption_confirmed=False,
                                             error={"code": error.code, "message": error.message})
                        self._persist_program()
                raise ServiceError(error.code, error.message, 409 if self._stop_event.is_set() else 504,
                                   execution_id=expected_execution_id) from error
            with self._lock:
                if self._stop_purge or self._stop_event.is_set():
                    raise ServiceError("program_cancelled", "session is stopping or stopped", 409, execution_id=expected_execution_id)
                if self._program:
                    self._program.update(state="interrupted", interruption_confirmed=True, interrupted_at=iso_now(), interrupt_ack=receipt)
                    if receipt.get("owner_restored") is not False:
                        self._program.pop("error", None)
                    self._persist_program()
                previous_id = self._program.get("replaces_execution_id") if self._program else None
                if previous_id:
                    try:
                        if not isinstance(previous_id, str) or re.fullmatch(r"[0-9a-f]{32}", previous_id) is None:
                            raise ValueError("invalid prior execution identity")
                        previous_path = self.dir / "programs" / f"{previous_id}.json"
                        previous = json.loads(previous_path.read_text())
                        if not isinstance(previous, dict) or previous.get("execution_id") != previous_id:
                            raise ValueError("invalid prior execution record")
                    except (OSError, UnicodeError, ValueError):
                        self._record_event("program_previous_history_unavailable", execution_id=expected_execution_id)
                    else:
                        if previous.get("state") in {"running", "submitting", "unknown", "interrupt-requested"}:
                            previous.update(state="interrupted", interruption_confirmed=True, interrupted_at=iso_now())
                            atomic_write_json(previous_path, previous)
                self._record_event("program_interrupted", execution_id=expected_execution_id)
            return {**self.program_status(), "interrupt_ack": receipt}
        finally:
            self._program_lock.release()

    def _frame_generation(self) -> tuple:
        with self._lock:
            return (self.state, self._stop_event.is_set(), self.pid,
                    self.process_start_token, self._frame_epoch,
                    self._proc.poll() if self._proc is not None else None,
                    self._program.get("execution_id") if self._program else None)

    def preview_frame(self, max_age_ms: int) -> dict:
        """Opt-in shared sample. Ordinary frame/evidence captures remain fresh."""
        if self.runtime == "tab5" or self.runtime == "network":
            raise ServiceError("frame_preview_not_available", "shared preview capture is currently admitted for QEMU runtimes only; omit max_age_ms for the existing backend capture", 409)
        generation = self._frame_generation()
        if generation[1] and generation[0] not in {"stopped", "failed"}:
            raise ServiceError("session_stopping", "session is stopping; wait for retained history", 409)

        def capture():
            metrics = self.frame_metrics(analyze=False)
            return CaptureResult(
                png=metrics["png"], width=metrics["width"], height=metrics["height"],
                source=metrics.get("source", "live"), captured_at=metrics.get("captured_at"),
                captured_monotonic=metrics.get("captured_monotonic"),
                execution_id=metrics.get("execution_id"), revision_id=metrics.get("revision_id"),
                program_state=metrics.get("program_state"),
            )

        try:
            sample = self._preview_frames.get(
                capture, generation=generation, max_age_ms=max_age_ms,
                is_current=lambda value: self._frame_generation() == value,
            )
        except FrameGenerationChanged as error:
            raise ServiceError("frame_generation_changed", "session changed during frame capture; request its current frame", 409) from error
        return sample.as_dict()

    def _frame_program_context(self) -> dict:
        # This labels the execution current during capture, not application
        # readiness or an atomic snapshot with separately sampled Unit state.
        program = self._program or {}
        return {"execution_id": program.get("execution_id"),
                "revision_id": program.get("revision_id"),
                "program_state": program.get("state")}

    def frame_metrics(
        self, *, analyze: bool = True, force_persist: bool = False
    ) -> dict:
        if not self.spec.has_display:
            raise ServiceError(
                "display_not_available",
                "this device has no framebuffer display",
                409,
            )
        with self._lock:
            if self.state not in {"running", "booting"}:
                persisted = self.persisted_frame_metrics()
                if persisted:
                    return persisted
                raise ServiceError(
                    "session_not_running", f"session state is {self.state}", 409
                )
            ppm = self.dir / f"frame-{uuid.uuid4().hex}.ppm"
            png = ppm.with_suffix(".png")
            try:
                self._qmp_call("screendump", filename=str(ppm))
                captured_at = iso_now()
                captured_monotonic = time.monotonic()
                program_context = self._frame_program_context()
                width, height, pixels = read_ppm(ppm)
                write_rgb_png(png, width, height, pixels)
                png_bytes = png.read_bytes()
                metrics = {
                    "png": png_bytes,
                    "width": width,
                    "height": height,
                    "png_bytes": len(png_bytes),
                    "source": "live",
                    "captured_at": captured_at,
                    "captured_monotonic": captured_monotonic,
                    **program_context,
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
        with self._lock:
            self.last_frame_path.write_bytes(metrics["png"])
            self.last_frame_meta_path.write_text(
                json.dumps(
                    {
                        key: value
                        for key, value in metrics.items()
                        if key not in {"png", "captured_monotonic"}
                    }
                    | {"captured_at": metrics.get("captured_at") or iso_now()},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            self._last_frame_persisted_at = time.monotonic()

    def persisted_frame_metrics(self) -> dict | None:
        with self._lock:
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

    def _verify_units_runtime(self) -> None:
        if not self.units:
            return
        if self._unit_registry()[0] is None:
            raise ServiceError("unit_contract_unavailable", "Unit session contract is unrecorded or invalid", 409)
        schema = self._qmp_call(
            "qom-get", path="/machine/units", property="schema-version"
        ).get("return")
        if schema != 1:
            raise ServiceError(
                "runtime_model_gap", "QEMU has no compatible Unit controller manager", 409,
            )
        snapshot = self.unit_state()
        if any(not unit["available"] for unit in snapshot["units"]):
            raise ServiceError(
                "runtime_model_gap", "QEMU Unit model/state contract is incomplete", 409,
            )

    def _unit_registry(self) -> tuple[UnitRegistry | None, str]:
        if not self.units:
            return UnitRegistry(contract={
                "schema_version": 1, "units": {}, "profiles": {}, "source_hashes": {},
            }), "none"
        if self.unit_contract is None:
            return None, "unrecorded"
        try:
            registry = UnitRegistry(contract=self.unit_contract)
            if any(unit["unit_id"] not in registry.units for unit in self.units):
                return None, "invalid"
            return registry, "frozen"
        except (UnitError, KeyError, TypeError):
            return None, "invalid"

    def unit_state(self) -> dict:
        registry, contract_status = self._unit_registry()
        if registry is None:
            saved = json.loads(self.unit_state_path.read_text()) if self.unit_state_path.is_file() else {"units": []}
            prior = {unit["id"]: unit for unit in saved.get("units", []) if isinstance(unit, dict) and "id" in unit}
            reason = "Unit session schema was not recorded or is invalid; writes are disabled"
            return {
                **saved, "session_id": self.id, "state": self.state,
                "source": "persisted" if self.unit_state_path.is_file() else "unavailable",
                "definitions": [], "contract_hashes": {}, "contract_status": contract_status,
                "units": [{
                    **unit, **prior.get(unit["id"], {}), "available": False,
                    "errors": {"contract": reason},
                } for unit in self.units],
                "errors": {"contract": reason},
            }
        if self.state not in {"booting", "running"}:
            if self.unit_state_path.is_file():
                saved = json.loads(self.unit_state_path.read_text())
                return {
                    **saved, "state": self.state, "source": "persisted",
                    "definitions": [registry.unit(unit_id) for unit_id in dict.fromkeys(
                        attachment["unit_id"] for attachment in self.units
                    )],
                    "contract_hashes": registry.source_hashes, "contract_status": contract_status,
                }
            return {
                "session_id": self.id, "state": self.state,
                "source": "unavailable", "units": [],
                "definitions": [registry.unit(unit_id) for unit_id in dict.fromkeys(
                    attachment["unit_id"] for attachment in self.units
                )],
                "contract_hashes": registry.source_hashes, "contract_status": contract_status,
            }
        def read(path, prop):
            with self._lock:
                return self._qmp_call("qom-get", path=path, property=prop).get("return")
        result = {
            "session_id": self.id, "state": self.state,
            "source": "live", "captured_at": iso_now(),
            "units": registry.state(self.units, read),
            "definitions": [registry.unit(unit_id) for unit_id in dict.fromkeys(
                attachment["unit_id"] for attachment in self.units
            )],
            "contract_hashes": registry.source_hashes,
            "contract_status": contract_status,
        }
        if self.units:
            atomic_write_json(self.unit_state_path, result)
        return result

    def validate_unit_input(self, payload: dict) -> dict:
        """Validate all frozen Unit intent before any QMP write or held receipt."""
        if not isinstance(payload, dict) or set(payload) != {"id", "values"}:
            raise ServiceError("invalid_unit_input", "id and values are required", 400)
        attachment = next((unit for unit in self.units if unit["id"] == payload["id"]), None)
        if attachment is None:
            raise ServiceError("unknown_unit_instance", "Unit is not attached to this session", 404)
        registry, contract_status = self._unit_registry()
        if registry is None:
            raise ServiceError("unit_contract_unavailable", f"Unit session contract is {contract_status}; writes are disabled", 409)
        try:
            values = registry.input_values(attachment["unit_id"], payload["values"], live=True)
        except UnitError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        profile = registry.profiles[attachment["unit_id"]]
        for field in values:
            descriptor = profile["inputs"][field]
            if (not isinstance(descriptor, dict)
                    or not isinstance(descriptor.get("property"), str) or not descriptor["property"]
                    or not isinstance(descriptor.get("path", ""), str)):
                raise ServiceError("unit_contract_unavailable", "Unit input descriptor is invalid; writes are disabled", 409)
        return {"id": attachment["id"], "values": values}

    def unit_input(self, payload: dict) -> dict:
        self._check_cancelled()
        if self.state != "running":
            raise ServiceError("session_not_running", f"session state is {self.state}", 409)
        command = self.validate_unit_input(payload)
        attachment = next(unit for unit in self.units if unit["id"] == command["id"])
        registry, _ = self._unit_registry()
        profile = registry.profiles[attachment["unit_id"]]
        values = command["values"]
        with self._lock:
            # Validate the complete payload before changing any physical input.
            for field, value in values.items():
                descriptor = profile["inputs"][field]
                path = f"/machine/units/{attachment['id']}{descriptor.get('path', '')}"
                self._qmp_call("qom-set", path=path, property=descriptor["property"], value=value)
            self._record_event("unit_input", unit_id=attachment["id"], values=values)
        # Read back guest state; accepting an input does not prove the firmware consumed it.
        return self.unit_state()

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

    def validate_input(self, payload: dict) -> dict:
        """Normalize a board command without QMP, sleeps, events or file writes."""
        if not isinstance(payload, dict):
            raise ServiceError("invalid_input", "input must be an object", 400)
        def duration(field, default):
            value = payload.get(field, default)
            try:
                if isinstance(value, bool):
                    raise ValueError("boolean duration")
                value = float(value)
                if not math.isfinite(value) or not 0 <= value < threading.TIMEOUT_MAX:
                    raise ValueError("duration outside supported range")
            except (ValueError, TypeError, OverflowError) as error:
                raise ServiceError("invalid_input", f"{field} must be finite, nonnegative and supported by the host clock", 400) from error
            return value
        def coordinate(field):
            value = payload.get(field, 0)
            try:
                if isinstance(value, bool) or not math.isfinite(float(value)):
                    raise ValueError("invalid coordinate")
                value = int(value)
                # Coordinates are expressed in the frame passed to send_input.
                axis = 0 if field.startswith("x") else 1
                size = (self.spec.expected_size or (1, 1))[axis]
                if not 0 <= value < size:
                    raise ValueError("coordinate outside frame")
            except (ValueError, TypeError, OverflowError) as error:
                raise ServiceError("invalid_input", f"{field} must be a finite coordinate within the frame", 400) from error
            return value
        kind = payload.get("kind")
        action = str(payload.get("action", "tap")).lower()
        command = {"kind": kind, "action": action}
        settle_default = 0.3
        if kind == "key":
            key = str(payload.get("key", ""))
            if not key:
                raise ServiceError("invalid_input", "key is required", 400)
            if self.spec.id != "nanoc6" and key not in QEMU_INPUT_QCODES:
                raise ServiceError("invalid_input", "key must be a supported QEMU qcode", 400)
            if action not in {"tap", "down", "up"}:
                raise ServiceError(
                    "invalid_input",
                    "key action must be tap, down or up",
                    400,
                )
            command["key"] = key
            if action in {"down", "up"}:
                settle_default = 0.02
        elif kind == "touch":
            command.update(x=coordinate("x"), y=coordinate("y"))
        elif kind == "longpress":
            command.update(x=coordinate("x"), y=coordinate("y"), hold_seconds=duration("hold_seconds", 0.5))
        elif kind == "drag":
            command.update({field: coordinate(field) for field in ("x1", "y1", "x2", "y2")})
        else:
            raise ServiceError(
                "invalid_input",
                "kind must be key, touch, longpress or drag",
                400,
            )
        command["settle_seconds"] = duration("settle_seconds", settle_default)
        return command

    def inject(self, payload: dict) -> dict:
        self._check_cancelled()
        if self.state != "running":
            raise ServiceError(
                "session_not_running", f"session state is {self.state}", 409
            )
        command = self.validate_input(payload)
        kind, action, settle = command["kind"], command["action"], command["settle_seconds"]
        if kind == "key":
            spec = f"{'key' if action == 'tap' else 'key' + action}:{command['key']}"
        elif kind == "touch":
            spec = f"touch:{command['x']},{command['y']}"
        elif kind == "longpress":
            spec = f"longpress:{command['x']},{command['y']},{command['hold_seconds']}"
        else:
            spec = f"drag:{command['x1']},{command['y1']},{command['x2']},{command['y2']}"
        frame_size = self.spec.expected_size or (1, 1)
        with self._lock:
            if self.spec.id == "nanoc6" and kind == "key":
                path = "/machine"
                property_name = "button-gpio9"
                if action in {"tap", "down"}:
                    self._qmp_call(
                        "qom-set",
                        path=path,
                        property=property_name,
                        value=True,
                    )
                if action == "tap":
                    time.sleep(settle)
                if action in {"tap", "up"}:
                    self._qmp_call(
                        "qom-set",
                        path=path,
                        property=property_name,
                        value=False,
                    )
            else:
                send_input(self._qmp, spec, frame_size, settle)
            self._record_event("input", spec=spec, action=action)
        return {
            "session_id": self.id,
            "input": spec,
            "action": action,
            "accepted": True,
        }

    def qom_set(self, payload: dict) -> dict:
        self._check_cancelled()
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

    def network_fault(self, payload: dict) -> dict:
        self._check_cancelled()
        action = payload.get("action")
        if action not in {"down", "up"}:
            raise ServiceError(
                "invalid_network_fault",
                "network fault action must be down or up",
                400,
            )
        if self.runtime not in QEMU_RADIO_RUNTIMES:
            raise ServiceError(
                "network_fault_not_supported",
                "network link fault injection requires a QEMU radio runtime",
                409,
            )
        if not self.network_config:
            raise ServiceError(
                "network_fault_not_supported",
                "session has no QEMU network profile",
                409,
            )
        target = payload.get("target", "link")
        if target not in {"link", "radio"}:
            raise ServiceError(
                "invalid_network_fault",
                "network fault target must be link or radio",
                400,
            )
        up = action == "up"
        qom_path = None
        if target == "radio":
            qom_path = self._radio_qom_path()
            result = self._qmp_execute(
                "qom-set",
                {
                    "path": qom_path,
                    "property": "radio-enabled",
                    "value": up,
                },
            )
        else:
            result = self._qmp_execute(
                "set_link",
                {"name": "wifi0", "up": up},
            )
        self._record_event(
            "network_fault",
            action=action,
            target=target,
            netdev="wifi0",
            qom_path=qom_path,
            up=up,
        )
        return {
            "session_id": self.id,
            "network_fault": {
                "action": action,
                "target": target,
                "netdev": "wifi0",
                "qom_path": qom_path,
                "up": up,
                "qmp_result": result.get("return"),
            },
        }

    def _radio_qom_path(self) -> str:
        listing = self._qmp_call(
            "qom-list",
            path="/machine/unattached",
        )["return"]
        candidates = [
            f"/machine/unattached/{entry['name']}"
            for entry in listing
            if entry.get("type")
            in {
                "child<misc.esp32_wifi>",
                "child<misc.esp32c6.wifi>",
                "child<misc.esp32s3.wifi>",
            }
        ]
        for path in candidates:
            properties = self._qmp_call("qom-list", path=path)["return"]
            if any(
                entry.get("name") == "radio-enabled"
                for entry in properties
            ):
                return path
        raise ServiceError(
            "radio_fault_not_supported",
            "this QEMU WiFi model has no radio-enabled QOM property",
            409,
        )

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
            raise ServiceError(
                "flash_not_available",
                "session flash was released; stop with retain_flash=1 "
                "when the full image is required",
                409,
            )
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
        if self.firmware_provenance:
            files["firmware/uiflow-source.json"] = json.dumps(
                self.firmware_provenance, ensure_ascii=False, indent=2,
            ).encode("utf-8")
        if self.program_transport:
            capability_path = self.dir / "program-capabilities.json"
            if capability_path.is_file():
                files["program-capabilities.json"] = capability_path.read_bytes()
            for record_path in sorted((self.dir / "programs").glob("*.json")):
                raw = record_path.read_bytes()
                files[f"programs/{record_path.name}"] = raw
                record = json.loads(raw)
                revision_id = record["revision_id"]
                try:
                    if record.get("source_kind") == "uiflow2-package":
                        source = self.service.program_packages.source(revision_id)
                        metadata = self.service.program_packages.get(revision_id)
                        for path, content in self.service.program_packages.read_files(revision_id).items():
                            files[f"programs/{revision_id}/files/{path}"] = content
                    else:
                        source = self.service.program_revisions.source(revision_id)
                        metadata = self.service.program_revisions.get(revision_id)
                except (RevisionError, ProgramPackageError) as error:
                    raise ServiceError(error.code, error.message, error.status) from error
                files[f"programs/{revision_id}/source.json"] = json.dumps(
                    source, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")
                files[f"programs/{revision_id}/revision.json"] = json.dumps(metadata).encode("utf-8")
        if self.units:
            manifest["units"] = self.unit_state()
            if manifest["units"].get("contract_status") == "frozen":
                files["units/contract.json"] = json.dumps(
                    self.unit_contract, ensure_ascii=False, indent=2,
                ).encode("utf-8")
            if self.unit_config_path.is_file():
                files["units/runtime.json"] = self.unit_config_path.read_bytes()
            if self.unit_state_path.is_file():
                files["units/state.json"] = self.unit_state_path.read_bytes()
        if self.unit_adc_calibration_path.is_file():
            files["units/adc-calibration.json"] = self.unit_adc_calibration_path.read_bytes()
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
                ("native-vhci-gdb.log", self.native_vhci_log),
                ("http-fixture.json", self.http_fixture_log),
                ("dns-fixture.json", self.dns_fixture_log),
                ("c6.log", self.dir / "c6.log"),
            ):
                if path.is_file():
                    files[name] = path.read_bytes()
        if (
            "frames" in include
            and self.spec.has_display
            and self.runtime in QEMU_QMP_RUNTIMES
        ):
            try:
                frame = self.frame_metrics()
                files["frames/current.png"] = frame["png"]
                manifest["frame"] = {
                    key: value for key, value in frame.items() if key not in {"png", "captured_monotonic"}
                }
            except ServiceError as error:
                manifest["frame"] = {"status": "NOT_AVAILABLE", "reason": error.message}
        if (
            (
                self.network_config.get("profile") in UNIFIED_PROFILES
                or self.network_config.get("profile") == NESSO_UNIFIED_PROFILE
                or self._plain_qemu_audio_enabled()
            )
            and self.speaker_pcm.is_file()
        ):
            pcm = self.speaker_pcm.read_bytes()
            files["audio/speaker.pcm"] = pcm
            manifest["audio"] = {
                "bytes": len(pcm),
                "nonzeros": sum(value != 0 for value in pcm),
                "sha256": hashlib.sha256(pcm).hexdigest(),
            }
        profile = self.network_config.get("profile")
        if self._plain_qemu_audio_enabled() or profile in {
            STACKCHAN_UNIFIED_PROFILE,
            CORE2_UNIFIED_PROFILE,
            CORE2_NATIVE_VHCI_PROFILE,
            CORE2_NATIVE_HCI_PROFILE,
        }:
            data_entries = [
                ("audio/microphone-source.pcm", self.microphone_source_pcm),
            ]
            if self._plain_qemu_audio_enabled():
                overridden = "M5SW_I2S_RX_PCM_FILE" in self.runtime_env
                manifest["audio_fixture"] = {
                    "source_kind": "explicit-diagnostic-override" if overridden else "generated-deterministic-tone",
                    "input_override": overridden,
                }
                if overridden:
                    # An unused generated fixture is not evidence of the
                    # explicitly supplied diagnostic source; never copy an
                    # arbitrary caller-selected host file into the bundle.
                    data_entries = []
                else:
                    manifest["audio_fixture"].update({
                        "sample_rate_hz": 16000,
                        "channels": 2 if self.spec.id == "cores3" else 1,
                        "sample_format": "s16le",
                        "frequency_hz": 440,
                        "duration_seconds": 1,
                    })
            if profile == STACKCHAN_UNIFIED_PROFILE:
                data_entries.extend(
                    (
                        ("ir/nec-source.rmt", self.rmt_source),
                        ("ir/nec-capture.rmt", self.rmt_capture),
                    )
                )
            for name, path in data_entries:
                if not path.is_file():
                    continue
                data = path.read_bytes()
                files[name] = data
                manifest.setdefault("device_data", {})[name] = {
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
        if profile in {NANOC6_HCI_BLE_PROFILE, NESSO_UNIFIED_PROFILE}:
            for name, path in (
                ("rmt/capture.bin", self.rmt_capture),
                ("pcm/buzzer.pcm", self.speaker_pcm),
            ):
                if not path.is_file():
                    continue
                data = path.read_bytes()
                files[name] = data
                manifest.setdefault("device_data", {})[name] = {
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
        if (
            "qom" in include
            and self.spec.service_kind == "qemu"
            and self.runtime in QEMU_QMP_RUNTIMES
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
        if self.storage_info:
            storage_bytes = (
                json.dumps(
                    self.storage_info,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            ).encode()
            files["storage/summary.json"] = storage_bytes
            manifest["storage"] = self.storage_info
        if self.nvs_info:
            nvs_bytes = (
                json.dumps(
                    self.nvs_info,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            ).encode()
            files["nvs/summary.json"] = nvs_bytes
            manifest["nvs"] = self.nvs_info
        network_dir = getattr(self, "network_dir", None)
        if isinstance(network_dir, Path) and network_dir.is_dir():
            for name, path in (
                ("network/evidence.json", network_dir / "evidence.json"),
                ("network/lifecycle.json", network_dir / "lifecycle.json"),
                ("network/serial.log", network_dir / "serial.log"),
                ("network/ble-probe.log", network_dir / "ble-probe.log"),
            ):
                if path.is_file():
                    files[name] = path.read_bytes()
            manifest["network"] = self.network_evidence()
        elif self.runtime in QEMU_RADIO_RUNTIMES:
            network_payload = self.network_evidence()
            files["network/evidence.json"] = (
                json.dumps(network_payload, ensure_ascii=False, indent=2) + "\n"
            ).encode()
            manifest["network"] = network_payload
            if self.network_pcap.is_file():
                files["network/capture.pcap"] = self.network_pcap.read_bytes()
            if self.network_pcap_summary.is_file():
                files["network/pcap-summary.json"] = (
                    self.network_pcap_summary.read_bytes()
                )
            if self.dns_fixture_log.is_file():
                files["network/dns-requests.json"] = (
                    self.dns_fixture_log.read_bytes()
                )
            if self.http_fixture_log.is_file():
                files["network/http-fixture.json"] = (
                    self.http_fixture_log.read_bytes()
                )
            if self.network_isolation_path.is_file():
                files["network/isolation.json"] = (
                    self.network_isolation_path.read_bytes()
                )
        if self.virtual_flash and self.virtual_flash.is_file():
            flash_data = self.virtual_flash.read_bytes()
            manifest["flash"] = {
                "size": len(flash_data),
                "sha256": hashlib.sha256(flash_data).hexdigest(),
                "retained": True,
            }
            if "flash" in include:
                files["flash/virtual-flash.bin"] = flash_data
        elif self.flash_info:
            manifest["flash"] = {
                "size": self.spec.flash_size,
                "sha256": self.firmware_sha,
                "retained": False,
                "reason": "session flash released after stop",
            }
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
        self._check_cancelled()
        owns_program = False
        if self.program_transport:
            owns_program = self._program_lock.acquire(blocking=False)
            if not owns_program:
                raise ServiceError("program_busy", "a program transfer owns the console", 409)
        try:
            with self._lock:
                self._frame_epoch += 1
                self._preview_frames.invalidate()
                self._qmp_call("system_reset")
                if self.program_transport:
                    self._invalidate_program_loader("reset-requires-new-loader-proof")
                if self.program_transport and self._program:
                    self._program.update(state="interrupted", interrupted_at=iso_now())
                    self._persist_program()
                self._record_event("reset")
        finally:
            if owns_program:
                self._program_lock.release()
        return {"session_id": self.id, "state": self.state, "reset": True}

    def renew(self, ttl_seconds: int) -> dict:
        self.ttl_seconds = ttl_seconds
        self.expires_at = time.time() + ttl_seconds
        self._persist_session()
        return self.snapshot()

    def _terminate_hci_probe(self) -> None:
        probe = self._hci_probe
        if probe is not None and probe.poll() is None:
            try:
                os.killpg(probe.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    probe.terminate()
                except ProcessLookupError:
                    pass
            try:
                probe.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(probe.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        probe.kill()
                    except ProcessLookupError:
                        pass
                probe.wait(timeout=5)
        self._hci_probe = None

        pid = self._external_hci_probe_pid
        start_token = self._external_hci_probe_start_token
        command_sha256 = self._external_hci_probe_command_sha256
        if (
            pid is not None
            and start_token
            and command_sha256
            and self._companion_process_matches(
                pid,
                start_token,
                command_sha256,
            )
        ):
            def owned() -> bool:
                return self._companion_process_matches(
                    pid,
                    start_token,
                    command_sha256,
                )

            def signal_owned(sig: signal.Signals) -> None:
                try:
                    if os.getpgid(pid) == pid:
                        os.killpg(pid, sig)
                    else:
                        os.kill(pid, sig)
                except (ProcessLookupError, PermissionError):
                    pass

            signal_owned(signal.SIGTERM)
            deadline = time.time() + 5
            while time.time() < deadline and owned():
                time.sleep(0.05)
            if owned():
                signal_owned(signal.SIGKILL)
                deadline = time.time() + 5
                while time.time() < deadline and owned():
                    time.sleep(0.05)
            if owned():
                raise ServiceError("session_cleanup_pending", "owned BLE peer did not terminate", 503)
        self._external_hci_probe_pid = None
        self._external_hci_probe_start_token = None
        self._external_hci_probe_command_sha256 = None
        if "ble" in self._companions:
            self._update_companion(
                "ble",
                state="terminated",
                ownership_verified=False,
                adopted=False,
                terminated_at=iso_now(),
            )

    def _terminate_process(self) -> None:
        external_pid = self.pid if self._reattached_process else None
        external_start = self.process_start_token
        native_gdb = self._native_vhci_gdb
        if native_gdb is not None and native_gdb.poll() is None:
            try:
                os.killpg(native_gdb.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    native_gdb.terminate()
                except ProcessLookupError:
                    pass
            try:
                native_gdb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(native_gdb.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        native_gdb.kill()
                    except ProcessLookupError:
                        pass
                native_gdb.wait(timeout=5)
        self._native_vhci_gdb = None
        proc = self._proc
        if proc is not None and proc.poll() is None:
            isolation = self.network_config.get("policy", {}).get(
                "isolation"
            )
            termination_timeout = 20 if isolation == "namespace" else 5
            try:
                proc.terminate()
                proc.wait(timeout=termination_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if external_pid is not None:
            def owns_external_process() -> bool:
                identity = inspect_process(external_pid)
                return bool(
                    identity["exists"]
                    and identity["start_token"] == external_start
                    and str(self.qmp_path)
                    in str(identity["command"] or "")
                )

            if owns_external_process():
                try:
                    os.kill(external_pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                deadline = time.time() + 5
                while time.time() < deadline and owns_external_process():
                    time.sleep(0.05)
                if owns_external_process():
                    try:
                        os.kill(external_pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    deadline = time.time() + 5
                    while time.time() < deadline and owns_external_process():
                        time.sleep(0.05)
                if owns_external_process():
                    raise ServiceError("session_cleanup_pending", "owned QEMU process did not terminate", 503)
            self._reattached_process = False
            self.pid = None
        self._close_http_fixture()
        self._terminate_hci_probe()
        console = getattr(self, "_console", None)
        if console is not None:
            console.close()
            self._console = None
            with self._lock:
                if self._program and self._program["state"] in {"running", "submitting", "unknown"}:
                    self._program.update(state="interrupted", interrupted_at=iso_now())
                    self._persist_program()
        if self._qmp is not None:
            try:
                self._qmp.close()
            except OSError:
                pass
            self._qmp = None
        if not self._process_identity_matches():
            if getattr(self, "program_transport", None):
                self.console_path.unlink(missing_ok=True)
            try:
                self.qmp_path.unlink()
            except FileNotFoundError:
                pass

    def _release_virtual_flash(self) -> int:
        path = self.virtual_flash
        if path is None or not path.is_file():
            self.virtual_flash = None
            return 0
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        self.virtual_flash = None
        self._record_event("flash_released", bytes=size)
        return size

    def stop(
        self, purge: bool = False, *, retain_flash: bool | None = None
    ) -> dict:
        with self._stop_request_lock:
            self._stop_event.set()
            self._preview_frames.invalidate()
            previous = (self._stop_purge, self._stop_retain_flash)
            self._stop_purge = self._stop_purge or purge
            retain = (
                self.service.storage_policy.retain_session_flash
                if retain_flash is None else bool(retain_flash)
            )
            if self._stop_retain_flash is None:
                self._stop_retain_flash = retain
            elif retain_flash is not None:
                self._stop_retain_flash = self._stop_retain_flash and retain
            if previous != (self._stop_purge, self._stop_retain_flash):
                self._stop_intent_version += 1
                self._stop_complete.clear()
        if not self._lifecycle_lock.acquire(timeout=SESSION_STOP_WAIT_SECONDS):
            return self._pending_stop_snapshot()
        try:
            if self._purged_snapshot is not None:
                with self._stop_request_lock:
                    self._stop_complete.set()
                return dict(self._purged_snapshot)
            while True:
                with self._stop_request_lock:
                    purge = self._stop_purge
                    retain = self._stop_retain_flash
                    version = self._stop_intent_version
                result = self._finish_stop(purge=purge, retain_flash=retain)
                with self._stop_request_lock:
                    if purge:
                        self._purged_snapshot = dict(result)
                    if version == self._stop_intent_version or purge:
                        self._stop_complete.set()
                        return result
                    # A second request tightened cleanup while teardown was
                    # busy. Consume it before completing this transaction.
                    self._stop_complete.clear()
        except Exception as error:
            with self._lock:
                self._stop_complete.clear()
                self.state = "stopping"
                self.completed_at = None
                self.error = self._provision_error or str(error)
                self._record_event("stop_cleanup_pending", error=str(error))
                self._persist_session()
            raise
        finally:
            self._lifecycle_lock.release()

    def _finish_stop(
        self, purge: bool = False, *, retain_flash: bool | None = None
    ) -> dict:
        retain_flash = (
            self.service.storage_policy.retain_session_flash
            if retain_flash is None
            else bool(retain_flash)
        )
        with self._lock:
            if self.state in {"stopped", "failed"}:
                if self.state == "failed" and self._provision_error is None:
                    self._provision_error = self.error or "session failed"
                self._terminate_runtime()
                if self.runtime in QEMU_RADIO_RUNTIMES:
                    self._finalize_network_capture()
                release_error = self._release_worker_lease(
                    state=self.state,
                    error=self.error,
                )
                if release_error:
                    raise ServiceError("worker_lease_release_pending", release_error, 503)
                if not purge and not retain_flash:
                    self._release_virtual_flash()
                self._persist_session()
                self._stop_complete.set()
                result = self.snapshot()
                if purge:
                    shutil.rmtree(self.dir, ignore_errors=True)
                    result["flash_retained"] = False
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
            if self.units and self.state in {"running", "booting"}:
                try:
                    self.unit_state()
                except (ServiceError, UnitError, OSError):
                    pass
            if self.runtime in QEMU_RADIO_RUNTIMES:
                try:
                    self.network_evidence()
                except ServiceError:
                    pass
            self.state = "stopping"
            if self._qmp is not None:
                try:
                    self._qmp.cmd("quit")
                except (OSError, RuntimeError):
                    pass
            self._terminate_runtime()
            if self.runtime in QEMU_RADIO_RUNTIMES:
                self._finalize_network_capture()
                self.network_result = self.network_evidence()
            if self.runtime == "network":
                evidence = self.network_evidence()
                if evidence.get("status") != "RUNNING":
                    self.network_result = evidence
            network_status = str(
                (self.network_result or {}).get("status", "RUNNING")
            )
            if self._provision_error is not None:
                self.state = "failed"
                self.error = self._provision_error
                self._record_event("failed", error=self.error)
            elif self.runtime == "network" and network_status not in {
                "PASS",
                "PARTIAL",
                "RUNNING",
            }:
                self.state = "failed"
                self.error = (
                    f"network lane completed with status {network_status}"
                )
            else:
                self.state = "stopped"
            self.completed_at = iso_now()
            self._record_event("stopped", purge=purge)
            release_error = self._release_worker_lease(
                state=self.state,
                error=self.error,
            )
            if release_error:
                raise ServiceError("worker_lease_release_pending", release_error, 503)
            if not purge and not retain_flash:
                self._release_virtual_flash()
            self._stop_complete.set()
            result = self.snapshot()
            self._persist_session()
        if purge:
            shutil.rmtree(self.dir, ignore_errors=True)
            result["flash_retained"] = False
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
        self._network_runner_command_sha256: str | None = None
        self._persist_session()

    def _provision_runtime(self) -> None:
        self._set_state("flashing")
        self.virtual_flash = self.dir / "virtual-flash.bin"
        shutil.copyfile(self.firmware_path, self.virtual_flash)
        self._check_cancelled()
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

    def _launch(self) -> None:
        self._check_cancelled()
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
        firmware_ap_password = self.network_config.get(
            "firmware_ap_password"
        )
        if firmware_ap_password is not None:
            command.extend(
                ["--firmware-ap-password", str(firmware_ap_password)]
            )
        for hostfwd in self.network_config.get("hostfwd", []):
            command.extend(["--hostfwd", str(hostfwd)])
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
            self._check_cancelled()
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            self._check_cancelled()
        finally:
            stdout.close()
            stderr.close()
        self.pid = self._proc.pid
        identity = inspect_process(self.pid)
        self.process_start_token = identity.get("start_token")
        command_text = identity.get("command")
        self._network_runner_command_sha256 = (
            hashlib.sha256(command_text.encode()).hexdigest()
            if command_text else None
        )
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
            if self._lifecycle_depth or self._stop_event.is_set():
                return
            try:
                self._verify_network_cleanup()
            except ServiceError as error:
                self._request_failure(error)
                self.state = "stopping"
                self._record_event("stop_cleanup_pending", error=str(error))
                self._persist_session()
                return
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
            if not self.service.storage_policy.retain_session_flash:
                self._release_virtual_flash()
            release_error = self._release_worker_lease(state=self.state, error=self.error)
            if release_error:
                self.state = "stopping"
                self.completed_at = None
                self._stop_event.set()
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
                # Runner cleanup can terminate two independent process groups,
                # each with TERM/KILL grace. Do not kill it mid-finally at 8s.
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except (OSError, ProcessLookupError):
                    proc.kill()
                proc.wait(timeout=5)
        self._verify_network_cleanup()

    def _verify_network_cleanup(self) -> None:
        proc = self._proc
        if proc is None:
            return
        path = self.network_dir / "lifecycle.json"
        if not path.is_file() and proc.poll() in {-signal.SIGTERM, -signal.SIGINT}:
            # The runner atomically journals before its first child creation.
            # A default-signal exit without a receipt is the pre-child path.
            return
        try:
            receipt = json.loads(path.read_text())
        except (OSError, ValueError):
            receipt = {}
        if not isinstance(receipt, dict):
            receipt = {}
        runner = receipt.get("runner") or {}
        if not isinstance(runner, dict):
            runner = {}
        children = receipt.get("children")
        complete = (
            receipt.get("schema_version") == 1
            and proc.poll() is not None
            and receipt.get("kind") == "m5stack-network-lane-lifecycle"
            and receipt.get("state") == "cleanup-complete"
            and receipt.get("cleanup_complete") is True
            and runner.get("pid") == proc.pid
            and (not self.process_start_token or runner.get("start_token") == self.process_start_token)
            and (not self._network_runner_command_sha256 or runner.get("command_sha256") == self._network_runner_command_sha256)
            and isinstance(children, dict)
            and set(children) == {"ble", "emulator"}
            and all(child is None or (
                isinstance(child, dict)
                and child.get("state") == "exited"
                and type(child.get("returncode")) is int
            ) for child in children.values())
        )
        if not complete:
            raise ServiceError(
                "session_cleanup_pending",
                "network runner child cleanup is unconfirmed; lease and ownership retained",
                503,
            )

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
        self._check_cancelled()
        self._unavailable("input injection")

    def qom_set(self, payload: dict):
        self._check_cancelled()
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
        self._check_cancelled()
        self._unavailable("network session reset")


class Tab5DeviceSession(DeviceSession):
    """Tab5 esp-emu session with serial, GDB framebuffer and touch support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._c6_proc: subprocess.Popen | None = None
        self._gdb_port: int | None = None
        self._hosted_socket = Path("/tmp") / f"m5-service-tab5-{self.id}.sock"

    def _provision_runtime(self) -> None:
        self._set_state("flashing")
        prepared = self.service.prepare_flash(
            self.spec, self.firmware_path, self.firmware_sha
        )
        self._check_cancelled()
        self.virtual_flash = self.dir / "virtual-flash.bin"
        shutil.copyfile(prepared["path"], self.virtual_flash)
        self._check_cancelled()
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

    def _launch_tab5(self) -> None:
        self._check_cancelled()
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
        with (self.dir / "c6.log").open("wb") as c6_stdout:
            self._check_cancelled()
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
            self._check_cancelled()
            wait_for_fs_path(self._hosted_socket, self._c6_proc, 25)
            self._check_cancelled()
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
        for i2c_device in TAB5_I2C_DEVICES:
            command.extend(["--i2c-dev", i2c_device])
        try:
            self._check_cancelled()
            self._proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=launch_env,
                stdout=p4_stdout,
                stderr=p4_stderr,
            )
            self._check_cancelled()
        finally:
            p4_stdout.close()
            p4_stderr.close()
        self.pid = self._proc.pid
        self._persist_session()
        wait_for_tcp_port(self._gdb_port, self._proc, 25)
        self._check_cancelled()

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
        self._check_cancelled()
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
        self._check_cancelled()
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
        self._check_cancelled()
        with self._lifecycle_operation():
            if self.state != "running":
                raise ServiceError(
                    "session_not_running", f"session state is {self.state}", 409
                )
            try:
                self._set_state("booting")
                self.serial0.write_bytes(b"")
                self._terminate_tab5()
                self._launch_tab5()
                self._set_state("running")
                self._record_event("reset")
                return {"session_id": self.id, "state": self.state, "reset": True}
            except Exception as error:
                self._request_failure(error)
                raise

    def _terminate_runtime(self) -> None:
        self._terminate_tab5()


class DeviceService:
    def __init__(
        self,
        *,
        state_dir: Path = DEFAULT_STATE_DIR,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_per_device: int = DEFAULT_MAX_PER_DEVICE,
        max_program_revisions: int = MAX_REVISIONS,
        max_program_packages: int = MAX_PACKAGES,
        default_ttl: int = 1800,
        api_token: str | None = None,
        previous_api_token: str | None = None,
        flash_preparer=None,
        storage_policy: StoragePolicy | None = None,
        worker_id: str | None = None,
        worker_state_path: Path | None = None,
        worker_heartbeat_interval: float | None = None,
        worker_stale_after: float | None = None,
    ):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.storage_policy = storage_policy or StoragePolicy.from_env()
        self.specs = load_device_specs()
        self.raw_matrix = json.loads(MATRIX.read_text())
        self.artifacts = ArtifactStore(self.state_dir / "artifacts")
        self.firmware = FirmwareStore(
            self.state_dir / "firmware", self.artifacts, self.specs
        )
        self.program_revisions = ProgramRevisionStore(
            self.state_dir / "program-revisions", max_count=max_program_revisions,
        )
        self.program_packages = ProgramPackageStore(
            self.state_dir / "program-packages", max_count=max_program_packages,
        )
        self.max_sessions = max(1, int(max_sessions))
        self.max_per_device = max(1, int(max_per_device))
        self.default_ttl = max(30, int(default_ttl))
        self.api_token = api_token
        self.previous_api_token = previous_api_token
        self.api_tokens = tuple(
            dict.fromkeys(
                token
                for token in (api_token, previous_api_token)
                if token
            )
        )
        self.worker_auth = WorkerAuthVerifier(
            api_token,
            previous_master_token=previous_api_token,
        )
        self.flash_preparer = flash_preparer or default_flash_preparer
        self._sessions: dict[str, DeviceSession] = {}
        self._lock = threading.RLock()
        self._preview_retention = PreviewRetention(self.state_dir, live_roots=self._preview_live_roots)
        self._preview_control_lock = threading.Lock()
        self._preview_control = None
        self._session_idempotency_path = (
            self.state_dir / "session-idempotency.json"
        )
        self._session_idempotency = self._load_session_idempotency()
        self._flash_lock = threading.Lock()
        self._reference_cache: dict[str, dict] = {}
        self._last_storage_prune_at: float | None = None
        self._last_storage_prune: dict[str, Any] = {}
        heartbeat_interval = float(
            worker_heartbeat_interval
            if worker_heartbeat_interval is not None
            else os.environ.get("M5_WORKER_HEARTBEAT_INTERVAL", "5")
        )
        stale_after = float(
            worker_stale_after
            if worker_stale_after is not None
            else os.environ.get("M5_WORKER_STALE_AFTER", "15")
        )
        capabilities = {
            "qemu": any(
                spec.supported and spec.backend.startswith("qemu-")
                for spec in self.specs.values()
            ),
            "network_namespace": (
                "probe-on-admission"
                if sys.platform == "linux"
                else "unavailable"
            ),
            "network_namespace_platform": sys.platform,
            "pcap": True,
            "tab5": any(
                spec.supported and spec.service_kind == "tab5"
                for spec in self.specs.values()
            ),
        }
        self.worker = WorkerRegistry(
            worker_state_path
            or Path(
                os.environ.get(
                    "M5_WORKER_STATE_PATH",
                    str(self.state_dir / "worker.json"),
                )
            ),
            worker_id=worker_id or os.environ.get("M5_WORKER_ID") or None,
            heartbeat_interval=heartbeat_interval,
            stale_after=stale_after,
            capabilities=capabilities,
        )
        self.worker_directory = WorkerDirectory(
            self.state_dir / "workers.json"
        )
        self.worker_queue = WorkerJobQueue(
            self.state_dir / "jobs.json",
            lease_seconds=float(
                os.environ.get("M5_JOB_LEASE_SECONDS", "60")
            ),
        )
        try:
            self.worker.start()
        except WorkerRegistryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error
        try:
            self._restore_history()
        except Exception:
            self.worker.close()
            raise
        self._stop = threading.Event()
        self._shutdown_lock = threading.Lock()
        self._shutdown_thread: threading.Thread | None = None
        self._worker_closed = False
        self._janitor = threading.Thread(
            target=self._janitor_loop,
            name="m5-session-janitor",
            daemon=True,
        )
        self._janitor.start()

    def _load_session_idempotency(self) -> dict[str, dict[str, Any]]:
        path = self._session_idempotency_path
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version")
            != SESSION_IDEMPOTENCY_SCHEMA_VERSION
            or not isinstance(payload.get("entries"), dict)
        ):
            return {}
        entries: dict[str, dict[str, Any]] = {}
        for key_hash, raw in payload["entries"].items():
            if (
                not isinstance(key_hash, str)
                or len(key_hash) != 64
                or not isinstance(raw, dict)
                or not isinstance(raw.get("request_sha256"), str)
                or len(raw["request_sha256"]) != 64
                or not isinstance(raw.get("session_id"), str)
                or not raw["session_id"]
            ):
                continue
            entries[key_hash] = {
                "request_sha256": raw["request_sha256"],
                "session_id": raw["session_id"],
                "created_at": (
                    raw.get("created_at")
                    if isinstance(raw.get("created_at"), str)
                    else iso_now()
                ),
            }
        if len(entries) > MAX_SESSION_IDEMPOTENCY_ENTRIES:
            retained = sorted(
                entries.items(),
                key=lambda item: item[1]["created_at"],
                reverse=True,
            )[:MAX_SESSION_IDEMPOTENCY_ENTRIES]
            entries = dict(retained)
        return entries

    def _write_session_idempotency_locked(self) -> None:
        path = self._session_idempotency_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f".{path.name}.{uuid.uuid4().hex}.tmp"
        )
        payload = {
            "schema_version": SESSION_IDEMPOTENCY_SCHEMA_VERSION,
            "entries": self._session_idempotency,
        }
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            )
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _session_idempotency_fields(
        payload: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        value = payload.get("idempotency_key")
        if value is None:
            return None, None
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 128
            or any(ord(char) < 32 for char in value)
        ):
            raise ServiceError(
                "invalid_idempotency_key",
                "idempotency_key must be 1-128 printable characters",
                400,
            )
        key_hash = hashlib.sha256(value.encode()).hexdigest()
        canonical = {
            key: item
            for key, item in payload.items()
            if key != "idempotency_key"
        }
        request_hash = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return key_hash, request_hash

    def _session_idempotency_replay_locked(
        self,
        key_hash: str | None,
        request_hash: str | None,
    ) -> DeviceSession | None:
        if key_hash is None or request_hash is None:
            return None
        entry = self._session_idempotency.get(key_hash)
        if entry is None:
            return None
        if entry["request_sha256"] != request_hash:
            raise ServiceError(
                "session_idempotency_conflict",
                "idempotency_key was already used with a different request",
                409,
            )
        session = self._sessions.get(str(entry["session_id"]))
        if session is not None:
            return session
        self._session_idempotency.pop(key_hash, None)
        self._write_session_idempotency_locked()
        return None

    def _remember_session_idempotency_locked(
        self,
        key_hash: str | None,
        request_hash: str | None,
        session_id: str,
    ) -> None:
        if key_hash is None or request_hash is None:
            return
        self._session_idempotency[key_hash] = {
            "request_sha256": request_hash,
            "session_id": session_id,
            "created_at": iso_now(),
        }
        if len(self._session_idempotency) > MAX_SESSION_IDEMPOTENCY_ENTRIES:
            retained = sorted(
                self._session_idempotency.items(),
                key=lambda item: item[1]["created_at"],
                reverse=True,
            )[:MAX_SESSION_IDEMPOTENCY_ENTRIES]
            self._session_idempotency = dict(retained)
        try:
            self._write_session_idempotency_locked()
        except Exception:
            self._session_idempotency.pop(key_hash, None)
            raise

    def _restore_history(self) -> None:
        """Restore history and safely re-attach only verified live QEMU PIDs."""

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
            was_active = persisted_state in ACTIVE_STATES
            interrupted = was_active or persisted_state == "stopping"
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
                if record.get("runtime") in QEMU_SESSION_RUNTIMES
                else "qemu"
            )
            try:
                persisted_pid = (
                    int(record["pid"])
                    if isinstance(record.get("pid"), int)
                    else None
                )
            except (TypeError, ValueError):
                persisted_pid = None
            process_start_token = (
                record.get("process_start_token")
                if isinstance(record.get("process_start_token"), str)
                else None
            )
            worker_lease_active = bool(
                record.get("worker_lease_active")
            )
            reattach_candidate = bool(
                was_active
                and runtime in QEMU_QMP_RUNTIMES
                and persisted_pid is not None
                and persisted_pid > 0
                and process_start_token
                and expires_at > time.time()
            )
            if reattach_candidate:
                interrupted = False
                restored_state = persisted_state
                completed_at = None
                error = None
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
            storage_config = (
                record.get("storage_config")
                if isinstance(record.get("storage_config"), dict)
                else None
            )
            storage_info = (
                record.get("storage")
                if isinstance(record.get("storage"), dict)
                else None
            )
            nvs_config = (
                record.get("nvs_config")
                if isinstance(record.get("nvs_config"), dict)
                else None
            )
            nvs_info = (
                record.get("nvs")
                if isinstance(record.get("nvs"), dict)
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
                program_transport=record.get("program_transport"),
                program_bootstrap=record.get("program_bootstrap") is True,
                management_binding=record.get("management_binding"),
                source_artifacts=[
                    artifact
                    for artifact in source_artifacts
                    if isinstance(artifact, str)
                ],
                firmware_provenance=(
                    record.get("firmware_provenance")
                    if isinstance(record.get("firmware_provenance"), dict) else None
                ),
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
                units=(record.get("units") if isinstance(record.get("units"), list) else []),
                unit_contract=record.get("unit_contract"),
                storage_config=storage_config,
                storage_info=storage_info,
                nvs_config=nvs_config,
                nvs_info=nvs_info,
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
                worker_id=(
                    record.get("worker_id")
                    if isinstance(record.get("worker_id"), str)
                    else None
                ),
                worker_generation=(
                    int(record["worker_generation"])
                    if isinstance(record.get("worker_generation"), int)
                    else None
                ),
                worker_lease_active=worker_lease_active,
                process_start_token=process_start_token,
                companions=(
                    record.get("companions")
                    if isinstance(record.get("companions"), dict)
                    else None
                ),
                persist=False,
            )
            virtual_flash = record_path.parent / "virtual-flash.bin"
            session.virtual_flash = virtual_flash if virtual_flash.is_file() else None
            session.pid = persisted_pid
            if not reattach_candidate:
                session._worker_lease_active = False
            if reattach_candidate:
                try:
                    session.reattach()
                except ServiceError as error:
                    session.mark_interrupted(
                        persisted_state,
                        f"safe re-attach rejected: {error.message}",
                    )
            elif interrupted:
                session.mark_interrupted(
                    persisted_state,
                    "service restarted before session completion",
                )
            else:
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
            "missing_runtime_files": [
                Path(os.path.relpath(path, ROOT)).as_posix()
                for path in spec.missing_backend_files
            ],
            "reference_available": reference_available,
            "backend": spec.backend,
            "machine": spec.machine,
            "flash_size": spec.flash_size,
            "display": spec.display,
            "peripheral_status": spec.peripheral_status,
            "warnings": spec.warnings,
            "firmware_families": ["uiflow2", "generic-flash"],
            "program_modes": ["uiflow-live"] if spec.id in LIVE_PROGRAM_DEVICES else [],
            "program_source_kinds": ["uiflow2-python", "uiflow2-package"] if spec.id in LIVE_PROGRAM_DEVICES else [],
            "program_features": {
                "runtimes": ["qemu"], "entrypoints": ["main.py"],
                "mpy_dependencies": "bytecode-only", "mpy_entrypoint": False,
                "native_mpy": False, "main_namespace": "fresh-exec-globals",
                "cleanup_mode": "interrupt-only",
            } if spec.id in LIVE_PROGRAM_DEVICES else {},
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
                "storage": spec.supported and spec.has_sd_card,
                "network": (
                    spec.network_status == "validated"
                    and bool(spec.network_profiles)
                ),
                "network_capture": (
                    spec.network_status == "validated"
                    and spec.service_kind == "qemu"
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
        if data and len(data) <= MAX_ARTIFACT_BYTES:
            self._ensure_storage_capacity(len(data))
        return self.artifacts.create(
            data, name=name, content_type=content_type or "application/octet-stream"
        )

    def begin_artifact_upload(
        self,
        *,
        expected_size: int,
        expected_sha256: str,
        name: str = "",
        content_type: str = "",
    ) -> dict:
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size <= 0
        ):
            raise ServiceError(
                "invalid_upload", "expected_size must be positive", 400
            )
        if expected_size > MAX_ARTIFACT_BYTES:
            raise ServiceError(
                "artifact_too_large",
                f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes",
                413,
            )
        self._ensure_storage_capacity(expected_size)
        return self.artifacts.begin_upload(
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            name=name,
            content_type=content_type or "application/octet-stream",
        )

    def append_artifact_upload(
        self,
        upload_id: str,
        *,
        offset: int,
        data: bytes,
        sha256: str,
    ) -> dict:
        if data:
            self._ensure_storage_capacity(len(data))
        return self.artifacts.append_upload_chunk(
            upload_id,
            offset=offset,
            data=data,
            sha256=sha256,
        )

    def get_artifact_upload(self, upload_id: str) -> dict:
        return self.artifacts.get_upload(upload_id)

    def complete_artifact_upload(self, upload_id: str) -> dict:
        return self.artifacts.complete_upload(upload_id)

    def abort_artifact_upload(self, upload_id: str) -> dict:
        return self.artifacts.abort_upload(upload_id)

    def import_firmware_package(self, payload: dict) -> dict:
        device_id = str(payload.get("device_id") or "")
        spec = self.specs.get(device_id)
        if spec is None:
            raise ServiceError("unknown_device", "device_id is required", 400)
        if not spec.supported:
            raise ServiceError(
                "unsupported_device",
                spec.reason or "device is not enabled for this service",
                409,
            )
        artifact_id = payload.get("artifact_id")
        artifact = self.artifacts.get(artifact_id)
        try:
            required_capabilities = normalize_capability_declarations(
                payload.get("required_capabilities"),
                field="required_capabilities",
            )
            optional_capabilities = normalize_capability_declarations(
                payload.get("optional_capabilities"),
                field="optional_capabilities",
            )
        except ManifestError as error:
            raise ServiceError(
                "invalid_capability_requirements",
                str(error),
                400,
            ) from error
        original_name = str(artifact.get("name") or f"{artifact_id}.bin")
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".bin", ".zip", ".m5burner", ".webburner"}:
            raise ServiceError(
                "unsupported_firmware_package",
                "package must be .bin, .zip, .m5burner or .webburner",
                400,
            )
        safe_stem = "".join(
            char if char.isalnum() or char in "._-" else "-"
            for char in Path(original_name).stem
        ).strip("-")[:80] or "firmware"
        import_root = self.state_dir / "firmware-imports"
        work_dir = import_root / uuid.uuid4().hex
        source_path = work_dir / f"{safe_stem}{suffix}"
        normalized_dir = work_dir / "normalized"
        self._ensure_storage_capacity(spec.flash_size * 2)
        try:
            work_dir.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(self.artifacts.path(artifact_id), source_path)
            result = import_package(
                source_path,
                normalized_dir,
                device_id=device_id,
                flash_size=spec.flash_size,
                required_capabilities=required_capabilities,
                optional_capabilities=optional_capabilities,
            )
            manifest = result["manifest"]
            validation = manifest.get("validation", {})
            if validation.get("status") != "PASS":
                raise ServiceError(
                    "unsupported_firmware_capability",
                    (
                        "firmware package does not satisfy the target "
                        "device capability profile"
                    ),
                    409,
                    issues=list(validation.get("errors", [])),
                    warnings=list(validation.get("warnings", [])),
                    manifest_id=manifest.get("manifest_id"),
                )
            image_path = Path(result["image_path"])
            normalized = self.artifacts.create(
                image_path.read_bytes(),
                name=image_path.name,
                content_type="application/octet-stream",
            )
            original_artifact_kind = manifest["artifact"].get("kind")
            source_segments = manifest["artifact"].get("segments")
            manifest["artifact"].update(
                {
                    "kind": "merged-flash",
                    "file": image_path.name,
                    "artifact_id": normalized["artifact_id"],
                    "sha256": normalized["artifact_id"],
                    "size": normalized["size"],
                    "normalized_from": original_artifact_kind,
                }
            )
            if source_segments:
                manifest["artifact"]["source_segments"] = source_segments
                manifest["artifact"].pop("segments", None)
            manifest["device_id"] = device_id
            manifest["manifest_id"] = canonical_json_sha256(
                manifest_identity_payload(manifest)
            )
            return self.firmware.create(
                {
                    "device_id": device_id,
                    "kind": "manifest",
                    "manifest": manifest,
                }
            )
        except ManifestError as error:
            raise ServiceError(
                "invalid_firmware_package",
                str(error),
                400,
            ) from error
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            try:
                import_root.rmdir()
            except OSError:
                pass

    def create_firmware(self, payload: dict) -> dict:
        spec = self.specs.get(str(payload.get("device_id") or ""))
        if spec is not None:
            self._ensure_storage_capacity(spec.flash_size)
        return self.firmware.create(payload)

    def create_uiflow_firmware(self, payload: dict) -> dict:
        if "kind" in payload:
            raise ServiceError("invalid_uiflow_request", "kind is not accepted on the UIFlow source endpoint", 400)
        return self.create_firmware({**payload, "kind": "uiflow"})

    def program_base_info(self, spec: DeviceSpec, *, base_firmware_id=None, expected_base_sha256=None) -> dict:
        """Re-admit an optional live-program base without publishing anything."""
        if base_firmware_id is None and expected_base_sha256 is None:
            return {**self.reference_info(spec), "kind": "cached-reference"}
        if base_firmware_id is None or expected_base_sha256 is None:
            raise ServiceError("invalid_program_base", "base_firmware_id and expected_base_sha256 must be supplied together", 400)
        _, _, provenance = self.firmware._explicit_uiflow_base(spec, {
            "base_firmware_id": base_firmware_id, "expected_base_sha256": expected_base_sha256,
        })
        return {"kind": "stored-manifest", "firmware_id": base_firmware_id,
                "sha256": provenance["stored_sha256"], "size": provenance["stored_size"]}

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
        if runtime in QEMU_RADIO_RUNTIMES:
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
                if (
                    spec.id in {"core2", "tab5"}
                    or os.environ.get("M5_SERVICE_FLASH_MODE", "esptool")
                    == "host-image"
                ):
                    virtual_flash = work_dir / "virtual-flash.bin"
                    info = {
                        "transport": "host-image",
                        "verified": True,
                        "flash_size": spec.flash_size,
                        "firmware_sha256": firmware_sha,
                        "virtual_flash": str(virtual_flash),
                    }
                    virtual_flash.write_bytes(
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

    def _program_revision_response(self, revision: dict) -> dict:
        return {
            "revision": revision,
            "limits": {
                "max_revisions": self.program_packages.max_count,
                "max_files": MAX_PACKAGE_FILES,
                "max_file_bytes": MAX_PROGRAM_FILE_BYTES,
                "max_total_file_bytes": MAX_PACKAGE_BYTES,
                "max_http_body_bytes": 2 * 1024 * 1024,
                "gc_enabled": False,
            },
        }

    def create_program_revision(self, payload: dict) -> dict:
        """Save a complete immutable checkpoint; never interrupt or execute it."""
        if not isinstance(payload, dict) or set(payload) != {"source_kind", "entrypoint", "files"}:
            raise ServiceError(
                "invalid_program_revision", "source_kind, entrypoint and files are required and are the only accepted fields", 400,
            )
        try:
            _, _, files = program_package_snapshot(payload)
            _validate_checkpoint_bytecode(files)
            revision = self.program_packages.create(payload)
        except ProgramPackageError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        return self._program_revision_response(revision)

    def get_program_revision(self, revision_id: str) -> dict:
        """Read metadata only; source bytes remain in the immutable store."""
        try:
            revision = self.program_packages.get(revision_id)
        except ProgramPackageError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        return self._program_revision_response(revision)

    def get_program_revision_files(self, revision_id: str) -> dict:
        """Read the verified complete immutable package, without guest work."""
        try:
            revision = self.program_packages.get(revision_id)
            source = self.program_packages.source(revision_id)
        except ProgramPackageError as error:
            raise ServiceError(error.code, error.message, error.status) from error
        return {**self._program_revision_response(revision), "files": source["files"]}

    def preview_control(self):
        """Initialize the optional Preview coordinator without importing it early."""
        with self._preview_control_lock:
            if self._stop.is_set():
                raise ServiceError("service_stopping", "device service is shutting down", 503)
            if self._preview_control is None:
                from preview_service import PreviewService
                self._preview_control = PreviewService(self)
            return self._preview_control

    def create_managed_session(self, payload: dict, *, preview_id: str, owner_epoch: str,
                               expected_reference_sha256: str) -> tuple[dict, object]:
        binding = _normalize_management_binding({"preview_id": preview_id, "owner_epoch": owner_epoch,
                                                 "expected_reference_sha256": expected_reference_sha256})
        if payload.get("program_mode") != "uiflow-live":
            raise ServiceError("unsupported_program_mode", "managed sessions require uiflow-live", 409)
        snapshot = self.create_session(payload, _management_binding=binding)
        handle = self.recover_management_handle(snapshot["session_id"], **binding)
        return snapshot, handle

    def recover_management_handle(self, session_id: str, *, preview_id: str, owner_epoch: str,
                                  expected_reference_sha256: str):
        binding = _normalize_management_binding({"preview_id": preview_id, "owner_epoch": owner_epoch,
                                                 "expected_reference_sha256": expected_reference_sha256})
        session = self.get_session(session_id)
        if session.management_binding != binding:
            raise ServiceError("session_managed_by_preview", "session does not match this Preview binding", 409)
        return session._management_handle

    @staticmethod
    def _require_session_binding(session, binding):
        if getattr(session, "management_binding", None) != binding:
            raise ServiceError("session_managed_by_preview", "idempotent session binding differs", 409)

    def create_session(self, payload: dict, *, _management_binding: dict | None = None) -> dict:
        if any(key in payload for key in ("management_binding", "management_handle", "_management_binding", "preview_id", "owner_epoch", "expected_reference_sha256", "program_capabilities", "runtime_capabilities", "loader_capabilities", "main_mpy", "mpy_entrypoint", "program_bootstrap")):
            raise ServiceError("invalid_request", "Preview management fields are internal and cannot be supplied in a session body", 400)
        if _management_binding is not None:
            _management_binding = _normalize_management_binding(_management_binding)
        if self._stop.is_set():
            raise ServiceError("service_stopping", "device service is shutting down", 503)
        program_transport = payload.get("program_transport")
        if program_transport not in (None, "uart-repl"):
            raise ServiceError("unsupported_program_transport", "program_transport must be uart-repl", 400)
        program_mode = payload.get("program_mode")
        if program_mode not in (None, "uiflow-live"):
            raise ServiceError("unsupported_program_mode", "program_mode must be uiflow-live", 400)
        explicit_program_base = "base_firmware_id" in payload or "expected_base_sha256" in payload
        if explicit_program_base and (program_mode != "uiflow-live" or
                not all(isinstance(payload.get(key), str) and _is_sha256(payload[key])
                        for key in ("base_firmware_id", "expected_base_sha256"))):
            raise ServiceError("invalid_program_base", "uiflow-live with a base_firmware_id and normalized expected_base_sha256 pair is required", 400)
        if explicit_program_base and _management_binding is not None and payload["expected_base_sha256"] != _management_binding["expected_reference_sha256"]:
            raise ServiceError("program_base_binding_mismatch", "Preview base pin differs from its frozen request", 409)
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
        if program_mode:
            if device_id not in LIVE_PROGRAM_DEVICES or payload.get("runtime", "qemu") != "qemu":
                raise ServiceError("unsupported_program_mode", "uiflow-live requires an admitted UIFlow2 QEMU device", 409)
            if "firmware_id" in payload or "uiflow_source_sha256" in payload:
                raise ServiceError("program_mode_firmware_conflict", "uiflow-live prepares its UIFlow2 base; omit firmware_id and source pin", 409)
            if payload.get("ready_marker", LIVE_READY_MARKER) != LIVE_READY_MARKER or payload.get("ready"):
                raise ServiceError("program_mode_ready_conflict", "uiflow-live waits for its UART REPL bootstrap; application readiness belongs to each program", 400)
        if not spec.backend_ready:
            missing = [
                Path(os.path.relpath(path, ROOT)).as_posix()
                for path in spec.missing_backend_files
            ]
            detail = (
                f"; missing: {', '.join(missing)}"
                if missing
                else ""
            )
            raise ServiceError(
                "backend_not_ready",
                (
                    f"runtime files are missing for {device_id}{detail}; "
                    "see docs/deployment.md"
                ),
                503,
                missing=missing,
                documentation="docs/deployment.md",
            )
        idempotency_key_hash, idempotency_request_hash = (
            self._session_idempotency_fields(payload)
        )
        with self._lock:
            if self._stop.is_set():
                raise ServiceError("service_stopping", "device service is shutting down", 503)
            replayed = self._session_idempotency_replay_locked(
                idempotency_key_hash,
                idempotency_request_hash,
            )
            if replayed is not None:
                self._require_session_binding(replayed, _management_binding)
                snapshot = replayed.snapshot()
                snapshot["idempotent_replay"] = True
                return snapshot
        worker_snapshot = self.worker_status()
        if not worker_snapshot["accepting_leases"]:
            raise ServiceError(
                "worker_not_accepting",
                (
                    f"worker is not accepting leases "
                    f"(state={worker_snapshot['state']}, "
                    f"stale={worker_snapshot['stale']})"
                ),
                503,
                worker=worker_snapshot,
            )
        if program_mode:
            # Keep idempotency bound to the original caller request above.
            # Initialization uses the established immutable source/Flash path
            # once; subsequent /program requests only use the live guest UART.
            bootstrap = self.create_uiflow_firmware({"device_id": device_id, "files": live_bootstrap_files(device_id),
                **({"base_firmware_id": payload["base_firmware_id"], "expected_base_sha256": payload["expected_base_sha256"]}
                   if explicit_program_base else
                   {"expected_base_sha256": _management_binding["expected_reference_sha256"]} if _management_binding is not None else {})})
            payload = {**payload, "firmware_id": bootstrap["firmware_id"],
                       "uiflow_source_sha256": bootstrap["source"]["metadata"]["source_sha256"],
                       "ready_marker": LIVE_READY_MARKER}
            program_transport = "uart-repl"
        firmware_id = payload.get("firmware_id")
        manifest_psram = None
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
            if firmware.get("kind") == "manifest":
                manifest_psram = (
                    (firmware.get("manifest") or {})
                    .get("target", {})
                    .get("psram_size")
                )
            elif firmware.get("kind") == "uiflow" and "base_manifest" in firmware:
                # Source composition changes only VFS. The explicit base's
                # security/capability and PSRAM requirements still apply to
                # the resulting runtime; changing kind must not erase them.
                base_manifest = firmware["base_manifest"]
                try:
                    structure_errors = validate_manifest_structure(base_manifest)
                except (TypeError, ValueError) as error:
                    raise ServiceError("invalid_firmware_manifest", "composed firmware base manifest is invalid", 409) from error
                if structure_errors or base_manifest["target"].get("psram_size") is not None and (type(base_manifest["target"]["psram_size"]) is not int or base_manifest["target"]["psram_size"] < 0):
                    raise ServiceError("invalid_firmware_manifest", "composed firmware base manifest is invalid", 409)
                base_id = canonical_json_sha256(manifest_identity_payload(base_manifest))
                metadata = firmware_source.get("metadata")
                provenance = metadata.get("base_provenance") if isinstance(metadata, dict) else None
                if not isinstance(provenance, dict) or base_manifest.get("manifest_id") != base_id or provenance.get("manifest_id") != base_id:
                    raise ServiceError("firmware_manifest_id_mismatch", "composed firmware base manifest identity differs", 409)
                profile = load_device_profile(device_id)
                compatibility = validate_capabilities(base_manifest, profile) if profile is not None else None
                if compatibility is None or compatibility["status"] != "PASS" or base_manifest.get("validation", {}).get("status") != "PASS":
                    raise ServiceError("unsupported_firmware_capability", "composed firmware retains unsupported base requirements", 409,
                                       issues=(compatibility or {}).get("errors", []))
                manifest_psram = base_manifest["target"].get("psram_size")
            source_artifacts = (
                [firmware_source["artifact_id"]]
                if firmware_source.get("kind") in {"merged", "manifest", "uiflow"}
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

        source_pin = payload.get("uiflow_source_sha256")
        is_uiflow_source = source == "uploaded" and firmware_source.get("kind") == "uiflow"
        if is_uiflow_source and source_pin is None:
            raise ServiceError(
                "uiflow_source_binding_required",
                "UIFlow sessions require the composed uiflow_source_sha256",
                400,
            )
        if source_pin is not None:
            if not isinstance(source_pin, str) or len(source_pin) != 64 or any(
                char not in "0123456789abcdef" for char in source_pin
            ):
                raise ServiceError("invalid_uiflow_source_binding", "uiflow_source_sha256 must be a lowercase SHA256", 400)
            if (
                not is_uiflow_source
                or source_pin != firmware_source.get("artifact_id")
                or source_pin != firmware_source.get("metadata", {}).get("source_sha256")
            ):
                raise ServiceError(
                    "uiflow_source_binding_mismatch",
                    "firmware source changed or does not match the requested UIFlow source",
                    409,
                )

        runtime = payload.get("runtime", "qemu")
        if program_transport and (
            runtime != "qemu" or device_id not in LIVE_PROGRAM_DEVICES
            or source == "uploaded" and not is_uiflow_source
        ):
            raise ServiceError("unsupported_program_transport", "UART REPL requires an admitted UIFlow2 QEMU source/reference session", 409)
        if runtime not in QEMU_SESSION_RUNTIMES:
            raise ServiceError(
                "unsupported_runtime",
                "runtime must be qemu, network, qemu-wifi, qemu-ble "
                "or qemu-unified",
                400,
            )
        try:
            unit_registry = UnitRegistry() if "units" in payload else None
            units = (
                unit_registry.attachments(device_id, runtime, payload.get("units"))
                if unit_registry is not None else []
            )
            unit_contract = unit_registry.freeze([unit["unit_id"] for unit in units]) if units else None
        except UnitError as error:
            raise ServiceError(error.code, error.message, error.status) from error
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
        elif runtime in {QEMU_BLE_RUNTIME, QEMU_UNIFIED_RUNTIME}:
            network_config = parse_qemu_ble_execution(
                spec,
                payload.get("network"),
                runtime=runtime,
            )
            if (
                network_config.get("profile") == CORE2_HCI_GATT_PROFILE
                and payload.get("ready_marker") is None
            ):
                payload = dict(payload)
                payload["ready_marker"] = "CORE2_HCI_BLE_ACK_SENT"
            elif (
                network_config.get("profile") == NANOC6_HCI_BLE_PROFILE
                and payload.get("ready_marker") is None
            ):
                payload = dict(payload)
                payload["ready_marker"] = "NANOC6_HCI_BLE_ACK_SENT"
            elif (
                network_config.get("profile") == NESSO_UNIFIED_PROFILE
                and payload.get("ready_marker") is None
            ):
                payload = dict(payload)
                payload["ready_marker"] = "UNIFIED_NESSO_BLE_ACK_SENT"
            elif (
                network_config.get("profile") in UNIFIED_READY_MARKERS
                and payload.get("ready_marker") is None
            ):
                payload = dict(payload)
                payload["ready_marker"] = UNIFIED_READY_MARKERS[
                    network_config["profile"]
                ]
        if network_config:
            elf_artifact_id = network_config.get("elf_artifact_id")
            if elf_artifact_id:
                self.artifacts.get(str(elf_artifact_id))
                if elf_artifact_id not in source_artifacts:
                    source_artifacts.append(str(elf_artifact_id))
        storage_config = parse_storage_execution(
            spec,
            payload.get("storage"),
        )
        if storage_config:
            storage_artifact = self.artifacts.get(
                storage_config["sd_image_artifact_id"]
            )
            size = int(storage_artifact.get("size") or 0)
            if size <= 0 or size % 512:
                raise ServiceError(
                    "invalid_storage_image",
                    "SD image must be non-empty and a multiple of 512 bytes",
                    400,
                )
            artifact_id = storage_config["sd_image_artifact_id"]
            if artifact_id not in source_artifacts:
                source_artifacts.append(artifact_id)
        nvs_config = parse_nvs_execution(payload.get("nvs"))
        if nvs_config:
            if (
                spec.service_kind != "qemu"
                or runtime not in QEMU_QMP_RUNTIMES
            ):
                raise ServiceError(
                    "nvs_not_supported",
                    (
                        "NVS session fixtures require a QEMU guest runtime; "
                        f"{spec.id}/{runtime} does not apply guest flash"
                    ),
                    409,
                )
            artifact_id = nvs_config["image_artifact_id"]
            artifact = self.artifacts.get(artifact_id)
            partition = resolve_nvs_partition(
                firmware_path,
                flash_size=spec.flash_size,
                partition_label=nvs_config["partition_label"],
            )
            expected_size = int(partition["size"])
            actual_size = int(artifact.get("size") or 0)
            if actual_size != expected_size:
                raise ServiceError(
                    "invalid_nvs_image",
                    (
                        f"NVS fixture has {actual_size} bytes; partition "
                        f"{partition['label']!r} requires {expected_size}"
                    ),
                    400,
                )
            nvs_config.update(
                {
                    "offset": int(partition["offset"]),
                    "size": expected_size,
                }
            )
            if artifact_id not in source_artifacts:
                source_artifacts.append(artifact_id)
        if runtime != "network":
            profile = (
                network_config.get("profile")
                if isinstance(network_config, dict)
                else None
            )
            memory_issue = runtime_psram_mismatch(
                spec.memory,
                profile,
                manifest_psram,
                spec.id,
            )
            if memory_issue is not None:
                raise ServiceError(
                    "unsupported_firmware_capability",
                    (
                        "firmware PSRAM requirement exceeds the selected "
                        "QEMU runtime memory policy"
                    ),
                    409,
                    issues=[memory_issue],
                )

        self._ensure_storage_capacity(spec.flash_size)
        with self._lock:
            if self._stop.is_set():
                raise ServiceError("service_stopping", "device service is shutting down", 503)
            replayed = self._session_idempotency_replay_locked(
                idempotency_key_hash,
                idempotency_request_hash,
            )
            if replayed is not None:
                self._require_session_binding(replayed, _management_binding)
                snapshot = replayed.snapshot()
                snapshot["idempotent_replay"] = True
                return snapshot
            active = [
                session
                for session in self._sessions.values()
                if session.state in OCCUPIED_STATES
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
            worker_owner = payload.get("owner")
            if worker_owner is not None and (
                not isinstance(worker_owner, str)
                or len(worker_owner) > 128
                or any(ord(char) < 32 for char in worker_owner)
            ):
                raise ServiceError(
                    "invalid_worker_owner",
                    "owner must be at most 128 printable characters",
                    400,
                )
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
                or (key in BOOLEAN_RUNTIME_TRACES and value != "1")
            ]
            if invalid_env:
                raise ServiceError(
                    "invalid_runtime_env",
                    "unsupported runtime_env keys or values: "
                    + ", ".join(str(key) for key in invalid_env),
                    400,
                )
            espnow_local_port = runtime_env.get("M5SW_ESPNOW_PEER_LOCAL_PORT")
            espnow_remote_port = runtime_env.get("M5SW_ESPNOW_PEER_REMOTE_PORT")
            if (espnow_local_port is None) != (espnow_remote_port is None):
                raise ServiceError(
                    "invalid_runtime_env",
                    "M5SW_ESPNOW_PEER_LOCAL_PORT and "
                    "M5SW_ESPNOW_PEER_REMOTE_PORT must be set together",
                    400,
                )
            if espnow_local_port is not None:
                if not (
                    espnow_local_port.isascii()
                    and espnow_local_port.isdigit()
                    and espnow_remote_port.isascii()
                    and espnow_remote_port.isdigit()
                ):
                    raise ServiceError(
                        "invalid_runtime_env",
                        "ESP-NOW peer ports must be decimal integers",
                        400,
                    )
                try:
                    local_port = int(espnow_local_port)
                    remote_port = int(espnow_remote_port)
                except ValueError as error:
                    raise ServiceError(
                        "invalid_runtime_env",
                        "ESP-NOW peer ports must be decimal integers",
                        400,
                    ) from error
                if (
                    not 1024 <= local_port <= 65535
                    or not 1024 <= remote_port <= 65535
                    or local_port == remote_port
                ):
                    raise ServiceError(
                        "invalid_runtime_env",
                        "ESP-NOW peer ports must be distinct values "
                        "between 1024 and 65535",
                        400,
                    )
                if runtime_env.get("M5SW_ESPNOW_LOOPBACK") is not None:
                    raise ServiceError(
                        "invalid_runtime_env",
                        "M5SW_ESPNOW_LOOPBACK cannot be combined with the "
                        "external ESP-NOW peer bridge",
                        400,
                    )
            espnow_pmk = runtime_env.get("M5SW_ESPNOW_PEER_PMK")
            espnow_lmk = runtime_env.get("M5SW_ESPNOW_PEER_LMK")
            if (espnow_pmk is None) != (espnow_lmk is None):
                raise ServiceError(
                    "invalid_runtime_env",
                    "M5SW_ESPNOW_PEER_PMK and "
                    "M5SW_ESPNOW_PEER_LMK must be set together",
                    400,
                )
            if espnow_pmk is not None:
                if espnow_local_port is None:
                    raise ServiceError(
                        "invalid_runtime_env",
                        "ESP-NOW peer keys require the external peer bridge",
                        400,
                    )
                for key_name, key_value in (
                    ("M5SW_ESPNOW_PEER_PMK", espnow_pmk),
                    ("M5SW_ESPNOW_PEER_LMK", espnow_lmk),
                ):
                    if not (
                        len(key_value) == 32
                        and key_value.isascii()
                        and all(
                            character in "0123456789abcdefABCDEF"
                            for character in key_value
                        )
                    ):
                        raise ServiceError(
                            "invalid_runtime_env",
                            f"{key_name} must contain exactly 32 hexadecimal "
                            "characters",
                            400,
                        )
            core2_pmic = runtime_env.get("M5SW_CORE2_PMIC")
            if core2_pmic is not None:
                if device_id != "core2":
                    raise ServiceError(
                        "invalid_runtime_env",
                        "M5SW_CORE2_PMIC is only valid for the core2 device",
                        400,
                    )
                if core2_pmic not in CORE2_PMIC_VARIANTS:
                    raise ServiceError(
                        "invalid_runtime_env",
                        "M5SW_CORE2_PMIC must be axp192 or axp2101",
                        400,
                    )
            ready_timeout = effective_session_ready_timeout(
                network_config,
                payload.get("ready_timeout_seconds"),
            )
            if runtime == "network":
                session_class = NetworkDeviceSession
            elif spec.service_kind == "tab5":
                session_class = Tab5DeviceSession
            else:
                session_class = DeviceSession
            session_id = uuid.uuid4().hex
            try:
                self.worker.reserve_lease(
                    session_id,
                    owner=worker_owner,
                )
            except WorkerRegistryError as error:
                raise ServiceError(
                    error.code,
                    error.message,
                    error.status,
                ) from error
            try:
                session = session_class(
                    self,
                    session_id=session_id,
                    spec=spec,
                    firmware_id=firmware_id,
                    firmware_path=firmware_path,
                    firmware_sha=firmware_sha,
                    firmware_source=source,
                    program_transport=program_transport,
                    program_bootstrap=program_mode == "uiflow-live",
                    management_binding=_management_binding,
                    source_artifacts=source_artifacts,
                    firmware_provenance=(firmware_source if firmware_source.get("kind") == "uiflow" else None)
                    if source == "uploaded" else None,
                    ttl_seconds=ttl,
                    ready_marker=ready_marker,
                    ready_timeout=ready_timeout,
                    ready_conditions=ready_conditions,
                    runtime_env=runtime_env,
                    units=units,
                    unit_contract=unit_contract,
                    runtime=runtime,
                    network_config=network_config,
                    storage_config=storage_config,
                    nvs_config=nvs_config,
                    worker_id=self.worker.worker_id,
                    worker_generation=self.worker.generation,
                    worker_lease_active=True,
                )
            except Exception:
                self.worker.release_lease(
                    session_id,
                    result={
                        "device_id": device_id,
                        "state": "failed",
                        "runtime": runtime,
                        "firmware_sha256": firmware_sha,
                        "error": "session construction failed",
                    },
                )
                raise
            session._record_event(
                "worker_lease_reserved",
                worker_id=self.worker.worker_id,
                generation=self.worker.generation,
            )
            self._sessions[session.id] = session
            try:
                self._remember_session_idempotency_locked(
                    idempotency_key_hash,
                    idempotency_request_hash,
                    session.id,
                )
            except Exception:
                self._sessions.pop(session.id, None)
                self.worker.release_lease(
                    session.id,
                    result={
                        "device_id": device_id,
                        "state": "failed",
                        "runtime": runtime,
                        "firmware_sha256": firmware_sha,
                        "error": "session idempotency persistence failed",
                    },
                )
                raise
        session.start()
        snapshot = session.snapshot()
        snapshot["idempotent_replay"] = False
        return snapshot

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
                if include_stopped or session.state in OCCUPIED_STATES
            ]
        return {"sessions": [session.snapshot() for session in sessions]}

    def delete_session(
        self,
        session_id: str,
        purge: bool = False,
        *,
        retain_flash: bool | None = None,
    ) -> dict:
        session = self.get_session(session_id)
        if purge:
            with self._retention().session_deletion(
                session.id, managed=getattr(session, "management_binding", None) is not None,
            ) as decision:
                if decision.protected:
                    raise ServiceError(
                        "retained_preview_history", "retained Preview history cannot be purged", 409,
                        retention_reason=decision.reason,
                    )
        result = session.stop(purge=purge, retain_flash=retain_flash)
        if purge and result["state"] in {"stopped", "failed"}:
            with self._lock:
                self._sessions.pop(session_id, None)
        return result

    def clear_stopped(
        self,
        purge: bool = True,
        *,
        retain_flash: bool | None = None,
    ) -> dict:
        with self._lock:
            sessions = [
                session
                for session in self._sessions.values()
                if session.state in {"stopped", "failed"}
            ]
            known_ids = set(self._sessions)
        protected_sessions = []
        skipped_sessions = []
        cleared_sessions = []
        for session in sessions:
            if purge:
                with self._retention().session_deletion(
                    session.id, managed=getattr(session, "management_binding", None) is not None,
                ) as decision:
                    if decision.protected:
                        target = protected_sessions if decision.reason == "retained_managed_history" else skipped_sessions
                        target.append(session.id)
                        continue
            session.stop(
                purge=purge,
                retain_flash=(
                    True
                    if not purge and retain_flash is None
                    else retain_flash
                ),
            )
            if purge:
                with self._lock:
                    self._sessions.pop(session.id, None)
            cleared_sessions.append(session.id)
        orphaned = []
        orphaned_protected = []
        orphaned_skipped = []
        if purge:
            sessions_root = self.state_dir / "sessions"
            try:
                candidates = list(sessions_root.iterdir()) if sessions_root.is_dir() else []
            except OSError:
                candidates = []
                orphaned_skipped.append("sessions_scan_unavailable")
            for path in candidates:
                if path.name in known_ids or not path.is_dir():
                    continue
                with self._lock:
                    if path.name in self._sessions:
                        continue
                with self._retention().session_deletion(path.name, orphan=True) as decision:
                    if decision.protected or path.is_symlink():
                        target = orphaned_protected if decision.reason == "retained_managed_history" else orphaned_skipped
                        target.append(path.name)
                        continue
                    try:
                        shutil.rmtree(path)
                    except OSError:
                        orphaned_skipped.append(path.name)
                    else:
                        orphaned.append(path.name)
        return {
            "cleared": len(cleared_sessions),
            "orphaned_cleared": len(orphaned),
            "purged": purge,
            "protected_sessions": protected_sessions,
            "skipped_sessions": skipped_sessions,
            "orphaned_protected": orphaned_protected,
            "orphaned_skipped": orphaned_skipped,
        }

    def _preview_live_roots(self) -> RetentionRoots:
        with self._lock:
            sessions = tuple(self._sessions.values())
        roots = RetentionRoots()
        for session in sessions:
            managed = getattr(session, "management_binding", None)
            add_session_roots(roots, {
                **({"session_id": session.id} if managed is not None else {}),
                "firmware_id": getattr(session, "firmware_id", None),
                "firmware_sha256": getattr(session, "firmware_sha", None),
                "source_artifacts": list(getattr(session, "source_artifacts", [])),
                "management_binding": managed,
                "firmware_provenance": getattr(session, "firmware_provenance", None),
            })
        return roots

    def _retention(self) -> PreviewRetention:
        # Some internal adapters construct a lightweight service without __init__.
        # Initialization does not perform disk/DB I/O or initialize Preview workers.
        with self._lock:
            retention = getattr(self, "_preview_retention", None)
            if retention is None:
                retention = self._preview_retention = PreviewRetention(
                    self.state_dir, live_roots=self._preview_live_roots,
                )
        return retention

    def preview_allocation_guard(self):
        return self._retention().allocation()

    def delete_artifact(self, artifact_id: str) -> dict:
        with self._retention().cache_deletion("artifact", artifact_id) as decision:
            if decision.protected:
                raise ServiceError(
                    "retained_preview_artifact", "artifact is protected by retained Preview state", 409,
                    retention_reason=decision.reason,
                )
            return self.artifacts.delete(artifact_id)

    def _ensure_storage_capacity(self, additional_bytes: int = 0) -> None:
        reserve = max(0, self.storage_policy.min_free_bytes)
        required = reserve + max(0, int(additional_bytes))
        usage = shutil.disk_usage(self.state_dir)
        if usage.free < required:
            raise ServiceError(
                "storage_exhausted",
                (
                    f"insufficient free space: {usage.free} bytes available, "
                    f"{required} bytes required including the reserve"
                ),
                507,
                available_bytes=usage.free,
                required_bytes=required,
                reserve_bytes=reserve,
            )

    def storage_stats(self) -> dict:
        with self._lock:
            sessions = list(self._sessions.values())
            active = [
                session for session in sessions if session.state in OCCUPIED_STATES
            ]
            history = [
                session
                for session in sessions
                if session.state in {"stopped", "failed"}
            ]
        sessions_root = self.state_dir / "sessions"
        artifacts_root = self.state_dir / "artifacts"
        firmware_root = self.state_dir / "firmware"
        flash_cache_root = self.state_dir / "flash-cache"
        sessions_bytes = directory_size_bytes(sessions_root)
        artifacts_bytes = directory_size_bytes(artifacts_root)
        firmware_bytes = directory_size_bytes(firmware_root)
        flash_cache_bytes = directory_size_bytes(flash_cache_root)
        disk = shutil.disk_usage(self.state_dir)
        return {
            "bytes": directory_size_bytes(self.state_dir),
            "disk": {
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "reserve_bytes": self.storage_policy.min_free_bytes,
            },
            "sessions": {
                "active": len(active),
                "retained": len(history),
                "directories": len(
                    [path for path in sessions_root.glob("*") if path.is_dir()]
                )
                if sessions_root.is_dir()
                else 0,
                "bytes": sessions_bytes,
                "flash_retained": sum(
                    1
                    for session in sessions
                    if session.virtual_flash is not None
                    and session.virtual_flash.is_file()
                ),
            },
            "artifacts": {
                "entries": len(self.artifacts.list()),
                "bytes": artifacts_bytes,
            },
            "firmware": {
                "entries": len(self.firmware.list()),
                "bytes": firmware_bytes,
            },
            "flash_cache": {
                "entries": (
                    len([path for path in flash_cache_root.rglob("*.bin") if path.is_file()])
                    if flash_cache_root.is_dir()
                    else 0
                ),
                "bytes": flash_cache_bytes,
            },
            "policy": self.storage_policy.as_dict(),
            "last_prune_at": (
                datetime.fromtimestamp(
                    self._last_storage_prune_at,
                    timezone.utc,
                ).isoformat()
                if self._last_storage_prune_at is not None
                else None
            ),
            "last_prune": dict(self._last_storage_prune),
        }

    def prune_storage(
        self,
        *,
        include_cache: bool = True,
        now: float | None = None,
    ) -> dict:
        now = time.time() if now is None else float(now)
        policy = self.storage_policy
        with self._lock:
            history = [
                session
                for session in self._sessions.values()
                if session.state in {"stopped", "failed"}
            ]
        rows = []
        protected_sessions = []
        skipped_sessions = []
        protected_bytes = 0
        for session in history:
            with self._retention().session_deletion(
                session.id, managed=getattr(session, "management_binding", None) is not None,
            ) as decision:
                if decision.protected:
                    target = protected_sessions if decision.reason == "retained_managed_history" else skipped_sessions
                    target.append(session.id)
                    protected_bytes += directory_size_bytes(session.dir)
                    continue
            rows.append(
                {
                    "session": session,
                    "sort_at": session.completed_at or session.created_at,
                    "age": _timestamp_age_seconds(
                        session.completed_at or session.created_at,
                        now=now,
                    ),
                    "bytes": directory_size_bytes(session.dir),
                }
            )
        rows.sort(key=lambda row: row["sort_at"])
        selected: list[dict] = []
        selected_ids: set[str] = set()

        def select(row: dict) -> None:
            session_id = row["session"].id
            if session_id not in selected_ids:
                selected.append(row)
                selected_ids.add(session_id)

        if policy.history_ttl_seconds > 0:
            for row in rows:
                if (
                    row["age"] is not None
                    and row["age"] > policy.history_ttl_seconds
                ):
                    select(row)
        remaining = [row for row in rows if row["session"].id not in selected_ids]
        if (
            policy.max_history_sessions > 0
            and len(remaining) + len(protected_sessions) + len(skipped_sessions) > policy.max_history_sessions
        ):
            excess = len(remaining) + len(protected_sessions) + len(skipped_sessions) - policy.max_history_sessions
            for row in remaining[:excess]:
                select(row)
        remaining = [row for row in rows if row["session"].id not in selected_ids]
        retained_bytes = protected_bytes + sum(row["bytes"] for row in remaining)
        if policy.max_history_bytes > 0:
            for row in remaining:
                if retained_bytes <= policy.max_history_bytes:
                    break
                select(row)
                retained_bytes -= row["bytes"]

        removed_sessions = []
        freed_session_bytes = 0
        for row in selected:
            session = row["session"]
            if session.state not in {"stopped", "failed"}:
                continue
            bytes_before = directory_size_bytes(session.dir)
            try:
                self.delete_session(session.id, purge=True)
            except ServiceError as error:
                if error.code != "retained_preview_history":
                    raise
                target = protected_sessions if error.extra.get("retention_reason") == "retained_managed_history" else skipped_sessions
                target.append(session.id)
                continue
            removed_sessions.append(session.id)
            freed_session_bytes += bytes_before

        cache_result = {
            "artifacts_removed": 0,
            "firmware_removed": 0,
            "flash_cache_removed": 0,
            "uploads_removed": 0,
            "freed_bytes": 0,
        }
        if include_cache:
            cache_result = self._prune_firmware_caches(now=now)

        result = {
            "pruned_sessions": len(removed_sessions),
            "session_ids": removed_sessions,
            "protected_sessions": protected_sessions,
            "skipped_sessions": skipped_sessions,
            "freed_session_bytes": freed_session_bytes,
            "cache": cache_result,
            "freed_bytes": freed_session_bytes + cache_result["freed_bytes"],
            "policy": policy.as_dict(),
        }
        self._last_storage_prune_at = now
        self._last_storage_prune = result
        return result

    def _prune_firmware_caches(self, *, now: float) -> dict:
        policy = self.storage_policy
        grace = max(0, policy.cache_grace_seconds)
        retention = self._retention()
        retention_protected = {"firmware": set(), "artifact": set(), "flash": set(), "upload": set()}
        retention_barrier = False

        def delete_cache(kind, identity, delete):
            nonlocal retention_barrier
            with retention.cache_deletion(kind, identity) as decision:
                if decision.protected:
                    retention_protected[kind].add(identity)
                    retention_barrier |= decision.reason == "retention_barrier"
                    return False
                delete()
                return True

        with self._lock:
            sessions = list(self._sessions.values())
        session_firmware_ids = {
            session.firmware_id for session in sessions if session.firmware_id
        }
        session_firmware_shas = {
            session.firmware_sha for session in sessions if session.firmware_sha
        }
        session_artifact_ids = {
            artifact_id
            for session in sessions
            for artifact_id in session.source_artifacts
        }
        cache_roots = (
            self.state_dir / "artifacts",
            self.state_dir / "firmware",
            self.state_dir / "flash-cache",
        )
        cache_bytes_before = sum(
            directory_size_bytes(root) for root in cache_roots
        )
        upload_prune = {"files_removed": 0, "bytes_removed": 0}
        def prune_uploads():
            upload_prune.update(self.artifacts.prune_uploads(now=now, grace_seconds=grace))
        delete_cache("upload", "staging", prune_uploads)

        firmware_records = self.firmware.list()
        kept_firmware = []
        removed_firmware_ids = []
        for record in firmware_records:
            firmware_id = str(record.get("firmware_id") or "")
            age = _timestamp_age_seconds(record.get("created_at"), now=now)
            if (
                firmware_id
                and firmware_id not in session_firmware_ids
                and age is not None
                and age >= grace
            ):
                if delete_cache("firmware", firmware_id, lambda: self.firmware.delete(firmware_id)):
                    removed_firmware_ids.append(firmware_id)
                else:
                    kept_firmware.append(record)
            else:
                kept_firmware.append(record)

        artifacts_kept_by_firmware = set()
        for record in kept_firmware:
            source = record.get("source")
            if not isinstance(source, dict):
                continue
            artifact_id = source.get("artifact_id")
            if isinstance(artifact_id, str):
                artifacts_kept_by_firmware.add(artifact_id)
            for segment in source.get("segments", []):
                if isinstance(segment, dict) and isinstance(
                    segment.get("artifact_id"), str
                ):
                    artifacts_kept_by_firmware.add(segment["artifact_id"])

        kept_firmware_ids = {
            str(record.get("firmware_id"))
            for record in kept_firmware
            if record.get("firmware_id")
        }
        removed_artifacts = []
        for record in self.artifacts.list():
            artifact_id = str(record.get("artifact_id") or "")
            age = _timestamp_age_seconds(record.get("created_at"), now=now)
            if (
                artifact_id
                and artifact_id not in session_artifact_ids
                and artifact_id not in artifacts_kept_by_firmware
                and age is not None
                and age >= grace
            ):
                if delete_cache("artifact", artifact_id, lambda: self.artifacts.delete(artifact_id)):
                    removed_artifacts.append(artifact_id)

        flash_cache_root = self.state_dir / "flash-cache"
        protected_hashes = session_firmware_shas | kept_firmware_ids
        removed_flash_cache = []
        if flash_cache_root.is_dir():
            for path in sorted(flash_cache_root.rglob("*.bin")):
                if path.stem in protected_hashes:
                    continue
                age = max(0.0, now - path.stat().st_mtime)
                if age >= grace:
                    if delete_cache("flash", path.stem, lambda: path.unlink(missing_ok=True)):
                        removed_flash_cache.append(path)
            for directory in sorted(
                [path for path in flash_cache_root.rglob("*") if path.is_dir()],
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    delete_cache("upload", "empty-directory", directory.rmdir)
                except OSError:
                    pass

        cache_bytes_after = sum(
            directory_size_bytes(root) for root in cache_roots
        )
        if policy.max_cache_bytes > 0 and cache_bytes_after > policy.max_cache_bytes:
            eviction_grace = min(grace, 60)
            for record in sorted(
                self.firmware.list(),
                key=lambda item: item.get("created_at", ""),
            ):
                if cache_bytes_after <= policy.max_cache_bytes:
                    break
                firmware_id = str(record.get("firmware_id") or "")
                age = _timestamp_age_seconds(record.get("created_at"), now=now)
                if (
                    not firmware_id
                    or firmware_id in session_firmware_ids
                    or (age is not None and age < eviction_grace)
                ):
                    continue
                if not delete_cache("firmware", firmware_id, lambda: self.firmware.delete(firmware_id)):
                    continue
                removed_firmware_ids.append(firmware_id)
                for cached in flash_cache_root.rglob(f"{firmware_id}.bin"):
                    if delete_cache("flash", cached.stem, lambda: cached.unlink(missing_ok=True)):
                        removed_flash_cache.append(cached)
                cache_bytes_after = sum(
                    directory_size_bytes(root) for root in cache_roots
                )

            protected_artifacts = set(session_artifact_ids)
            for record in self.firmware.list():
                source = record.get("source")
                if not isinstance(source, dict):
                    continue
                artifact_id = source.get("artifact_id")
                if isinstance(artifact_id, str):
                    protected_artifacts.add(artifact_id)
                for segment in source.get("segments", []):
                    if isinstance(segment, dict) and isinstance(
                        segment.get("artifact_id"), str
                    ):
                        protected_artifacts.add(segment["artifact_id"])
            for record in sorted(
                self.artifacts.list(),
                key=lambda item: item.get("created_at", ""),
            ):
                if cache_bytes_after <= policy.max_cache_bytes:
                    break
                artifact_id = str(record.get("artifact_id") or "")
                age = _timestamp_age_seconds(record.get("created_at"), now=now)
                if (
                    not artifact_id
                    or artifact_id in protected_artifacts
                    or (age is not None and age < eviction_grace)
                ):
                    continue
                if not delete_cache("artifact", artifact_id, lambda: self.artifacts.delete(artifact_id)):
                    continue
                removed_artifacts.append(artifact_id)
                cache_bytes_after = sum(
                    directory_size_bytes(root) for root in cache_roots
                )

            cached_files = sorted(
                [
                    path
                    for path in flash_cache_root.rglob("*.bin")
                    if path.stem not in session_firmware_shas
                    and path.stem not in protected_hashes
                ],
                key=lambda path: path.stat().st_mtime,
            )
            for path in cached_files:
                if cache_bytes_after <= policy.max_cache_bytes:
                    break
                age = max(0.0, now - path.stat().st_mtime)
                if age < eviction_grace:
                    continue
                if not delete_cache("flash", path.stem, lambda: path.unlink(missing_ok=True)):
                    continue
                removed_flash_cache.append(path)
                cache_bytes_after = sum(
                    directory_size_bytes(root) for root in cache_roots
                )

        cache_bytes_after = sum(
            directory_size_bytes(root) for root in cache_roots
        )
        return {
            "artifacts_removed": len(removed_artifacts),
            "firmware_removed": len(removed_firmware_ids),
            "flash_cache_removed": len(removed_flash_cache),
            "uploads_removed": upload_prune["files_removed"],
            "freed_bytes": max(0, cache_bytes_before - cache_bytes_after),
            "retention_barrier": retention_barrier,
            "protected": {kind: sorted(values) for kind, values in retention_protected.items()},
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
                if session.state in OCCUPIED_STATES
            ]
            by_device: dict[str, int] = {}
            for session in active:
                by_device[session.spec.id] = by_device.get(session.spec.id, 0) + 1
        unified_s3 = any(
            profile in self.specs[device_id].network_profiles
            for device_id, profile in (
                ("sticks3", STICKS3_UNIFIED_PROFILE),
                ("cores3", CORES3_UNIFIED_PROFILE),
                ("cardputer-adv", CARDPUTER_ADV_UNIFIED_PROFILE),
                ("stopwatch", STOPWATCH_UNIFIED_PROFILE),
                ("atoms3r", ATOMS3R_UNIFIED_PROFILE),
                ("papercolor", PAPERCOLOR_UNIFIED_PROFILE),
                ("papermono", PAPERMONO_UNIFIED_PROFILE),
                ("stackchan", STACKCHAN_UNIFIED_PROFILE),
                ("stamplc", STAMPLC_UNIFIED_PROFILE),
            )
        )
        unified_core2 = (
            CORE2_UNIFIED_PROFILE in self.specs["core2"].network_profiles
        )
        unified_c6 = (
            NANOC6_HCI_BLE_PROFILE in self.specs["nanoc6"].network_profiles
            and NESSO_UNIFIED_PROFILE
            in self.specs["nesso-n1"].network_profiles
        )
        qemu_unified = (
            "enabled-sticks3-cores3-cardputer-adv-stopwatch-atoms3r-"
            "papercolor-papermono-stackchan-stamplc"
            + ("-core2" if unified_core2 else "")
            + ("-c6" if unified_c6 else "")
            + "-wifi-ble"
            if unified_s3 or unified_core2 or unified_c6
            else "disabled"
        )
        qemu_ble_devices = []
        if CORE2_BLE_PROFILE in self.specs["core2"].network_profiles:
            qemu_ble_devices.append("core2-experimental")
        if NANOC6_HCI_BLE_PROFILE in self.specs["nanoc6"].network_profiles:
            qemu_ble_devices.append("nanoc6-hci")
        if NESSO_UNIFIED_PROFILE in self.specs["nesso-n1"].network_profiles:
            qemu_ble_devices.append("nesso-hci")
        qemu_ble = (
            "enabled-" + "-".join(qemu_ble_devices)
            if qemu_ble_devices
            else "disabled"
        )
        worker = self._worker_summary()
        return {
            "max_sessions": self.max_sessions,
            "active_sessions": len(active),
            "available_sessions": (
                max(0, self.max_sessions - len(active))
                if worker["accepting_leases"]
                else 0
            ),
            "max_per_device": self.max_per_device,
            "by_device": by_device,
            "worker": worker,
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
                    "enabled-s3-and-core2"
                    if (
                        any(
                            spec.supported
                            and spec.backend == "qemu-esp32s3"
                            for spec in self.specs.values()
                        )
                        and CORE2_WIFI_PROFILE
                        in self.specs["core2"].network_profiles
                    )
                    else "enabled-s3"
                    if any(
                        spec.supported
                        and spec.backend == "qemu-esp32s3"
                        for spec in self.specs.values()
                    )
                    else "enabled-core2-experimental"
                    if CORE2_WIFI_PROFILE
                    in self.specs["core2"].network_profiles
                    else "disabled"
                ),
                "qemu-ble": qemu_ble,
                "qemu-unified": qemu_unified,
                "tab5": "enabled-partial",
                "flash": "prepared-cache + exact artifact",
            },
        }

    def _worker_summary(self) -> dict:
        snapshot = self.worker_status()
        return {
            key: snapshot.get(key)
            for key in (
                "worker_id",
                "instance_id",
                "generation",
                "state",
                "pid",
                "started_at",
                "heartbeat_at",
                "heartbeat_age_seconds",
                "stale",
                "accepting_leases",
                "active_lease_count",
                "active_lease_ids",
                "drained_at",
            )
        }

    def worker_status(self) -> dict:
        try:
            return self.worker.snapshot()
        except WorkerRegistryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def drain_worker(self) -> dict:
        try:
            worker = self.worker.drain()
        except WorkerRegistryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error
        with self._lock:
            active = [
                {
                    "session_id": session.id,
                    "device_id": session.spec.id,
                    "state": session.state,
                    "expires_at": datetime.fromtimestamp(
                        session.expires_at,
                        timezone.utc,
                    ).isoformat(),
                }
                for session in self._sessions.values()
                if session.state in OCCUPIED_STATES
            ]
        return {"worker": worker, "active_sessions": active}

    def resume_worker(self) -> dict:
        try:
            return {"worker": self.worker.resume()}
        except WorkerRegistryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def list_remote_workers(self) -> dict:
        return self.worker_directory.list_workers()

    def verify_worker_request(
        self,
        headers: Any,
        method: str,
        path: str,
        body: bytes,
    ) -> dict:
        try:
            return self.worker_auth.verify(headers, method, path, body)
        except WorkerAuthError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def set_api_token(self, token: str | None) -> None:
        self.set_api_tokens(token)

    def set_api_tokens(
        self,
        token: str | None,
        previous_token: str | None = None,
    ) -> None:
        with self._lock:
            self.api_token = token or None
            self.previous_api_token = previous_token or None
            self.api_tokens = tuple(
                dict.fromkeys(
                    value
                    for value in (self.api_token, self.previous_api_token)
                    if value
                )
            )
            self.worker_auth = WorkerAuthVerifier(
                self.api_token,
                previous_master_token=self.previous_api_token,
            )

    def register_remote_worker(self, payload: dict) -> dict:
        try:
            return {
                "worker": self.worker_directory.register(payload)
            }
        except WorkerDirectoryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def heartbeat_remote_worker(
        self,
        worker_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "worker": self.worker_directory.heartbeat(
                    worker_id, payload
                )
            }
        except WorkerDirectoryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def drain_remote_worker(
        self,
        worker_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "worker": self.worker_directory.drain(
                    worker_id, payload
                )
            }
        except WorkerDirectoryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def stop_remote_worker(
        self,
        worker_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "worker": self.worker_directory.stop(
                    worker_id, payload
                )
            }
        except WorkerDirectoryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def record_remote_worker_result(
        self,
        worker_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "result": self.worker_directory.record_result(
                    worker_id, payload
                )
            }
        except WorkerDirectoryError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def list_remote_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> dict:
        try:
            return self.worker_queue.list_jobs(
                status=status,
                limit=limit,
            )
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def submit_remote_job(self, payload: dict) -> dict:
        try:
            return {"job": self.worker_queue.submit(payload)}
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def get_remote_job(self, job_id: str) -> dict:
        try:
            return {"job": self.worker_queue.get_job(job_id)}
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def claim_remote_job(self, payload: dict) -> dict:
        try:
            workers = self.worker_directory.list_workers()["workers"]
            return {
                "job": self.worker_queue.claim(payload, workers)
            }
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def heartbeat_remote_job(
        self,
        job_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "job": self.worker_queue.heartbeat(job_id, payload)
            }
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def record_remote_job_result(
        self,
        job_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "job": self.worker_queue.result(job_id, payload)
            }
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def cancel_remote_job(
        self,
        job_id: str,
        payload: dict,
    ) -> dict:
        try:
            return {
                "job": self.worker_queue.cancel(job_id, payload)
            }
        except WorkerQueueError as error:
            raise ServiceError(
                error.code,
                error.message,
                error.status,
            ) from error

    def _janitor_loop(self) -> None:
        last_storage_prune = 0.0
        while not self._stop.wait(2):
            now = time.time()
            with self._lock:
                sessions = list(self._sessions.values())
            # No service-wide lock while process/companion teardown or a
            # bounded pending-stop retry may wait on a session transaction.
            for session in sessions:
                if session._purged_snapshot is not None:
                    with self._lock:
                        if self._sessions.get(session.id) is session:
                            self._sessions.pop(session.id, None)
                    continue
                try:
                    if session.state in ACTIVE_STATES and session._proc is not None and session._proc.poll() is not None:
                        session._handle_process_exit(session._proc.returncode)
                    elif (
                        session.state in ACTIVE_STATES
                        and session._reattached_process
                        and not session._process_identity_matches()
                    ):
                        session._handle_process_exit(
                            None,
                            reason=(
                                "re-attached QEMU process disappeared "
                                "or changed identity"
                            ),
                        )
                    if session._stop_event.is_set() and not session._stop_complete.is_set():
                        session.stop()
                    elif session.state in ACTIVE_STATES and session.expires_at <= now:
                        session.stop(retain_flash=False)
                except Exception:
                    pass
            try:
                self.worker_queue.reconcile(
                    self.worker_directory.list_workers()["workers"]
                )
            except Exception:
                pass
            if (
                now - last_storage_prune
                >= self.storage_policy.prune_interval_seconds
            ):
                last_storage_prune = now
                try:
                    self.prune_storage()
                except Exception:
                    pass

    def _finish_shutdown(self, sessions: list[DeviceSession]) -> None:
        # Cache pruning can already be in flight when _stop is set. Keep the
        # registry ownership until the old janitor can no longer mutate state.
        self._janitor.join()
        pending = list(sessions)
        while pending or self.worker.snapshot().get("active_lease_count", 0):
            remaining = []
            for session in pending:
                try:
                    result = session.stop()
                    if result.get("stop_pending") or session._worker_lease_active:
                        remaining.append(session)
                except Exception:
                    remaining.append(session)
            pending = remaining
            if pending or self.worker.snapshot().get("active_lease_count", 0):
                time.sleep(0.05)
        with self._shutdown_lock:
            if not self._worker_closed:
                self.worker.close()
                self._worker_closed = True

    def close_all(self) -> dict:
        self._stop.set()
        control_lock = getattr(self, "_preview_control_lock", None)
        if control_lock is not None:
            with control_lock:
                control = self._preview_control
            if control is not None:
                control.shutdown()
        if not self.worker.started:
            # A crash/restart handoff may already have released this registry
            # lock. Do not mutate resources or records adopted by its successor.
            return {"state": "ownership_released", "pending_sessions": []}
        if self._janitor is not threading.current_thread():
            self._janitor.join(timeout=SESSION_STOP_WAIT_SECONDS)
        with self._lock:
            sessions = list(self._sessions.values())
        pending = []
        for session in sessions:
            try:
                result = session.stop(
                    retain_flash=True if session.state in {"stopped", "failed"} else None,
                )
                if result.get("stop_pending") or session._worker_lease_active:
                    pending.append(session)
            except Exception:
                pending.append(session)
        with self._shutdown_lock:
            if not pending and not self._janitor.is_alive() and not self.worker.snapshot().get("active_lease_count", 0):
                if not self._worker_closed:
                    self.worker.close()
                    self._worker_closed = True
                return {"state": "stopped", "pending_sessions": []}
            if self._shutdown_thread is None:
                # Interpreter shutdown must wait for the transaction owner.
                # Keep the worker registry lock/heartbeat until cleanup is real.
                self.worker.drain()
                self._shutdown_thread = threading.Thread(
                    target=self._finish_shutdown,
                    args=(pending,),
                    name="m5-service-shutdown",
                    daemon=False,
                )
                self._shutdown_thread.start()
        return {"state": "draining", "pending_sessions": [s.id for s in pending]}


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
    erased_app_partitions = []
    for partition in partition_table["partitions"]:
        if partition["type"] != 0:
            continue
        image = analyze_esp_image(data, partition["offset"])
        if not image["valid"]:
            slot = data[
                partition["offset"] : partition["offset"] + partition["size"]
            ]
            if (
                0x10 <= partition["subtype"] <= 0x1F
                and slot
                and all(value == 0xFF for value in slot)
            ):
                erased_app_partitions.append(
                    {
                        "label": partition["label"],
                        "offset": partition["offset"],
                        "size": partition["size"],
                    }
                )
                continue
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
        "erased_app_partitions": erased_app_partitions,
    }


def _public_flash_info(info: dict) -> dict:
    return {
        key: value
        for key, value in info.items()
        if key not in {"image", "virtual_flash", "qemu", "rom_dir"}
    }
