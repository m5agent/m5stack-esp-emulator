"""Pinned esp32sim native runtime and its private single-owner control stream."""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import struct
import threading
import time

from device_service_errors import ServiceError
from device_service_network import parse_network_policy
from device_service_input import action_seconds, control_name
from device_service_encoder import (
    DEFAULT_EDGE_PERIOD_MS, validate_encoder_delta, validate_encoder_edge_period_ms,
)
from firmware_analysis import find_flash_bootloader, parse_partition_table

RUNTIME = "esp32sim"
BACKEND = "esp32sim-esp32s3"
ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "scripts/esp32sim-runtime.lock.json"
ROM_NAME = "esp32s3_rev0_rom.elf"
CLASSIC_ROM_NAME = "esp32_rev300_rom.elf"
P4_ROM_NAME = "esp32p4_rev0_rom.elf"
P4_REV3_ROM_NAME = "esp32p4_rev300_rom.elf"
C6_ROM_NAME = "esp32c6_rev0_rom.elf"
MAX_PCM_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Board:
    name: str
    flash: int
    psram: int
    size: tuple[int, int] | None
    chip_id: int = 9
    touch: bool = False

    @property
    def is_tab5(self):
        return self.chip_id == 0x12

    @property
    def rom_name(self):
        return {0: CLASSIC_ROM_NAME, 13: C6_ROM_NAME}.get(self.chip_id, ROM_NAME)


def _load_boards():
    groups = {"esp32-lx6": 0, "esp32-s3": 9, "esp32-c6": 13, "esp32-p4": 0x12}
    catalog = json.loads((ROOT / "devices/catalog.source.json").read_text())
    boards, variants = {}, {}
    for device in catalog["devices"]:
        native = device["runtime"].get(RUNTIME)
        if native is None:
            continue
        device_id = device["id"]
        board = Board(
            native["board"], native["flash_bytes"], native["psram_bytes"],
            tuple(native["frame_size"]) if "frame_size" in native else None,
            groups[device["group"]], native.get("touch", False),
        )
        boards[device_id] = board
        if native.get("variants"):
            variants[device_id] = {
                name: replace(board, name=values.get("board", board.name),
                              flash=values.get("flash_bytes", board.flash))
                for name, values in native["variants"].items()
            }
    return boards, variants


BOARDS, BOARD_VARIANTS = _load_boards()
TAB5_PANELS = {
    "gt911-ili9881c": BOARDS["tab5"],
    **BOARD_VARIANTS["tab5"],
}
SD_DEVICES = frozenset({
    "cores3", "stackchan", "cardputer", "cardputer-adv", "tab5", "basic-v27",
    "core2", "paperdiy", "papermono", "papers3", "papercolor", "stamplc",
})
CAMERA_DEVICES = frozenset({"cores3", "stackchan", "atoms3r-cam", "atoms3r-m12"})
CAMERA_SEQUENCE_DEVICES = frozenset({"atoms3r-cam", "atoms3r-m12"})
GROVE_TMP105_DEVICES = frozenset({"atom-echo", "basic-v27"})
ATOM_IO_DEVICES = frozenset({"atom-echo", "atomu", "atom-lite", "atom-matrix", "atom-matrix-v11"})
UART_REPL_DEVICES = ATOM_IO_DEVICES | {"cores3", "core2"}
S3_ATOM_IO_PINS = {
    "atoms3-lite": 41, "atoms3u": 41, "atom-echos3r": 41,
    "atoms3r-cam": 41, "atoms3r-m12": 41,
}
# Paths are scoped by the catalog's per-device probes. For example, /board/imu
# is an MPU6886 on StickC and a BMI270 on StickS3.
LEGACY_STATE_PATHS = {
    "/machine/aw9523": "aw9523",
    "/machine/aw9523-59": "aw9523",
    "/machine/axp2101": "pmic",
    "/machine/bmi270": "imu",
    "/machine/bmm150": "magnetometer",
    "/machine/es8311": "es8311",
    "/machine/et047tc1": "panel/controller",
    "/machine/gc0308": "gc0308",
    "/machine/ina226": "ina226",
    "/machine/ina226-40": "ina226",
    "/machine/ip2315": "charger",
    "/machine/ip5306": "ip5306",
    "/machine/lm75-48": "lm75",
    "/machine/lp5562": "lp5562",
    "/machine/ltr553": "ltr553",
    "/machine/m5-lcd-cam": "camera",
    "/machine/m5ioe1": "ioe1",
    "/machine/m5pm1": "pmic",
    "/machine/mpu6886": "imu",
    "/machine/ov3660": "ov3660",
    "/machine/pcf8563": "rtc",
    "/machine/pi4ioe-43": "pi4ioe",
    "/machine/rx8130": "rtc",
    "/machine/rx8130-32": "rtc",
    "/machine/si12t": "si12t",
    "/machine/sht40": "sht40",
}
BOARD_STATE_DEVICES = frozenset({
    *S3_ATOM_IO_PINS, "atoms3", "atoms3r", "basic-v27", "papercolor", "paperdiy",
    "papermono", "papers3", "stackchan", "stamplc", "stickc", "stickc-plus",
    "stickc-plus2", "sticks3", "stopwatch",
})
NATIVE_BOARD_STATE_PATHS = {
    "nanoc6": {"rgb": "/machine/board/rgb", "ir": "/machine/board/ir",
               "button": "/machine/soc/gpio/9"},
    "nesso-n1": {name: f"/machine/board/{path}" for name, path in (
        ("pi4ioe-43", "pi4ioe-43"), ("pi4ioe-44", "pi4ioe-44"),
        ("bq27220", "bq27220"), ("aw32001", "aw32001"), ("bmi270", "imu"),
    )},
    "tab5": {name: f"/machine/board/{path}" for name, path in (
        ("pi4ioe-43", "pi4ioe-43"), ("pi4ioe-44", "pi4ioe-44"),
        ("ina226", "ina226"), ("rx8130", "rtc"), ("bmi270", "imu"), ("panel", "panel/controller"),
    )},
}


def supports_device_state(device, features):
    return (device == "stackchan"
            or device == "dial" and "dial-encoder-state" in features
            or device in ATOM_IO_DEVICES and "state-snapshot" in features
            or device in NATIVE_BOARD_STATE_PATHS and "expanded-board-state" in features
            or device in BOARD_STATE_DEVICES and "board-device-state" in features)

# Normalized Flash digests with same-firmware HTTP session comparison.
# Keep unspecified images and legacy-only feature requests on esp-emu.
TAB5_DEFAULT_FIRMWARE = {
    "507f2aeeddfdd71357c019122cc76785b710ba24a4dc3adeb840d61c9ee8b1a7": "st7123",
    "4da826b590d879ccb7728b20257c1847a8093868eb2752600994f1242438bdeb": "gt911-ili9881c",
}


def p4_rom_name(flash):
    # The CLI selects rev >= 3 from the P4 bootloader header at 0x2000.
    with flash.open("rb") as stream:
        stream.seek(0x2000)
        header = stream.read(24)
    if len(header) == 24 and header[0] == 0xE9 and header[12:14] == b"\x12\0":
        if int.from_bytes(header[15:17], "little") >= 300:
            return P4_REV3_ROM_NAME
    return P4_ROM_NAME


@dataclass(frozen=True)
class Installation:
    binary: Path
    rom: Path
    manifest: Path

    @classmethod
    def discover(cls):
        folder = Path(os.environ.get("M5_ESP32SIM_RUNTIME_DIR", ROOT / ".work/esp32sim-runtime")).resolve()
        rom_dir = Path(os.environ.get("ESP32SIM_ROM_DIR", folder / "roms")).resolve()
        return cls(folder / "esp32sim", rom_dir / ROM_NAME, folder / "runtime.json")

    def binary_for(self, board):
        return self.binary.with_name("esp32sim-p4") if board.is_tab5 else self.binary

    def runtime_paths(self, board, lock):
        if not board.is_tab5:
            return [self.binary, self.board_rom(board)]
        return [
            self.binary_for(board),
            *(self.rom.with_name(name) for name in (P4_ROM_NAME, P4_REV3_ROM_NAME, C6_ROM_NAME)),
            *(self.manifest.parent / "tab5-c6" / item["path"] for item in lock["tab5_c6"]["files"].values()),
        ]

    def board_rom(self, board):
        return self.rom if board.rom_name == ROM_NAME else self.rom.with_name(board.rom_name)

    def missing(self, board):
        lock = json.loads(LOCK.read_text())
        return [path for path in [self.manifest, *self.runtime_paths(board, lock)] if not path.is_file()]

    def identity(self, board, flash=None):
        try:
            lock = json.loads(LOCK.read_text())
            manifest = json.loads(self.manifest.read_text())
            binary, *assets = self.runtime_paths(board, lock)
            digest = asset_sha(binary)
            expected_binary = manifest["p4_binary_sha256" if board.is_tab5 else "binary_sha256"]
            if (manifest["commit"] != lock["commit"] or expected_binary != digest
                    or manifest["service_patch_sha256"] != lock["service_patch_sha256"]
                    or not os.access(binary, os.X_OK)):
                raise ValueError("esp32sim executable differs from runtime manifest")
            rom = p4_rom_name(flash) if board.is_tab5 and flash is not None else assets[0].name
            observed = {path.name: asset_sha(path) for path in assets}
            expected = {path.name: lock["roms"][path.name] for path in assets if path.suffix == ".elf"}
            if board.is_tab5:
                expected.update({Path(row["path"]).name: row["sha256"]
                                 for row in lock["tab5_c6"]["files"].values()})
            if observed != expected:
                raise ValueError("esp32sim ROM or co-processor asset differs from runtime lock")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ServiceError(
                "backend_not_ready",
                f"Provision the pinned esp32sim assets for {board.name}; see docs/deployment.md", 503,
            ) from error
        return {
            "runtime": RUNTIME, "commit": lock["commit"], "binary_sha256": digest,
            "rom_sha256": observed[rom], "board": board.name, "control_protocol": 1,
            "service_patch_sha256": lock["service_patch_sha256"],
            "flash_bytes": board.flash, "psram_bytes": board.psram,
            **({"service_features": lock["service_features"]} if "service_features" in lock else {}),
            **({"rom": rom, "coprocessor": {"esp_hosted_version": lock["tab5_c6"]["version"],
                 "rom_sha256": observed[C6_ROM_NAME],
                 "images_sha256": {k: row["sha256"] for k, row in lock["tab5_c6"]["files"].items()}}}
               if board.is_tab5 else {}),
        }

    def ready(self, board):
        try:
            self.identity(board)
        except ServiceError:
            return False
        return True


@lru_cache(maxsize=16)
def file_sha(path, _inode, _size, _mtime):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def asset_sha(path):
    stat = path.stat()
    return file_sha(path, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def validate_memory(board, data, psram):
    if psram is not None and (type(psram) is not int or not 0 <= psram <= board.psram):
        raise ServiceError("unsupported_firmware_capability", "Firmware PSRAM exceeds the esp32sim board capacity", 409)
    boot = find_flash_bootloader(data, board.chip_id)
    declared = boot.get("flash_size")
    partitions = parse_partition_table(data)["partitions"]
    partition_end = max((p["offset"] + p["size"] for p in partitions), default=0)
    if len(data) > board.flash or (declared is not None and (partition_end > declared or declared > board.flash)):
        raise ServiceError("firmware_flash_mismatch", "Firmware flash layout exceeds the esp32sim board capacity", 422)


def parse_network(value, *, restricted_supported=False, softap_supported=False):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {"profile", "ssid", "psk", "policy", "mode"}:
        raise ServiceError("invalid_network", "esp32sim accepts profile, ssid, psk, policy and mode", 400)
    profile = value.get("profile", "esp32sim-sta")
    if profile == "esp32sim-softap":
        if not softap_supported or value.get("mode") != "restricted" or "policy" in value:
            raise ServiceError("not_supported_on_runtime", "esp32sim-softap requires a supported board, restricted mode and no host policy", 409)
    elif profile != "esp32sim-sta":
        raise ServiceError("not_supported_on_runtime", "Unsupported esp32sim network profile", 409)
    request_policy = value.get("policy")
    mode = value.get("mode", "nat")
    if mode == "restricted":
        if not restricted_supported or "policy" in value:
            raise ServiceError("not_supported_on_runtime", "Restricted esp32sim mode requires a pinned runtime and no host policy", 409)
        dns = "guest" if profile == "esp32sim-softap" else "emulated"
        policy_evidence = {"isolation": "emulator", "egress": "deny-all", "dns": dns}
    elif mode == "nat":
        policy = parse_network_policy(request_policy)
        if (not isinstance(request_policy, dict)
                or request_policy.keys() - {"isolation", "egress", "dns"}
                or request_policy.get("isolation") != "trusted-host"
                or policy.isolation != "trusted-host" or policy.egress != "native"
                or policy.allowed_hosts or policy.allowed_domains or policy.allowed_endpoints):
            raise ServiceError("not_supported_on_runtime", "esp32sim NAT requires explicit trusted-host native policy", 409)
        policy_evidence = policy.evidence()
    else:
        raise ServiceError("invalid_network", "esp32sim network mode must be nat or restricted", 400)
    ssid, psk = value.get("ssid", "esp32sim"), value.get("psk", "")
    for text, name, minimum, maximum in ((ssid, "ssid", 1, 32), (psk, "psk", 8, 63)):
        if (not isinstance(text, str) or not text.isascii() or "," in text
                or (text and not text.isprintable())
                or (name == "ssid" or text) and not minimum <= len(text) <= maximum):
            raise ServiceError("invalid_network", f"Invalid esp32sim Wi-Fi {name}", 400)
    return {"profile": profile, "ssid": ssid, "psk": psk, "mode": mode, "policy": policy_evidence}


def spawn_command(installation, board, fd, flash, *, sd=None, cam=None, mic=None, network=None,
                  pcap=None, flash_readback=None, sd_initially_ejected=False, grove_tmp105=False,
                  stereo_capture=False):
    rom = installation.rom.with_name(p4_rom_name(flash)) if board.is_tab5 else installation.board_rom(board)
    command = [
        str(installation.binary_for(board)), "--board", board.name, "--rom", str(rom),
        "--boot", "rom", "--flash-image", str(flash), "--console", "none",
        "--service-fd", str(fd),
    ]
    if board.chip_id in {0, 13}:
        command += ["--chip", "esp32" if board.chip_id == 0 else "c6",
                    "--flash-mb", str(board.flash >> 20)]
    if board.is_tab5:
        lock = json.loads(LOCK.read_text())["tab5_c6"]
        paths = {"rom": installation.rom.with_name(C6_ROM_NAME)}
        paths.update({key: installation.manifest.parent / "tab5-c6" / row["path"]
                      for key, row in lock["files"].items()})
        if any("," in str(path) for path in paths.values()):
            raise ServiceError("backend_not_ready", "Tab5 co-processor asset paths cannot contain commas", 503)
        options = [f"{key}={path}" for key, path in paths.items()]
        # This ESP-Hosted 2.0.13 build needs the baseband calibration shim
        # used by the upstream Tab5 WLAN regression fixture.
        options.append(f"stub={lock['bb_init']}=0")
        command += ["--coproc", "c6:" + ",".join(options)]
    for flag, path in (("--sd-rw", sd), ("--cam-image", cam), ("--mic-wav", mic)):
        if path is not None:
            command += [flag, str(path)]
    if flash_readback is not None:
        command += ["--service-flash-out", str(flash_readback)]
    if stereo_capture:
        command += ["--service-stereo"]
    if sd_initially_ejected:
        command += ["--sd-ejected"]
    if grove_tmp105:
        command += ["--grove", "tmp105"]
    if network:
        settings = f"ssid={network['ssid']}"
        if network["psk"]:
            settings += f",psk={network['psk']}"
        if network.get("profile") == "esp32sim-softap":
            command += ["--wifi-sta", settings]
        else:
            command += ["--wifi", settings, "--net", network.get("mode", "nat")]
        if pcap is not None:
            command += ["--pcap", str(pcap)]
    return command


KEYS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789`-=[];',./\\") | {
    "tab", "fn", "shift", "ctrl", "opt", "alt", "del", "enter", "space",
}
KEY_ALIASES = {
    "backspace": "del", "delete": "del", "return": "enter", "ret": "enter",
    "spc": "space", "compose": "fn", "menu": "fn", "meta_l": "opt",
    "comma": ",", "dot": ".", "slash": "/", "semicolon": ";",
    "grave_accent": "`", "bracket_left": "[", "bracket_right": "]",
    "backslash": "\\", "apostrophe": "'", "minus": "-", "equal": "=",
}


def input_command(device, payload, *, board=None):
    if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
        raise ServiceError("invalid_input", "input kind is required", 400)
    kind = payload["kind"]
    action = payload.get("action", "tap")
    if not isinstance(action, str):
        raise ServiceError("invalid_input", "action must be a string", 400)
    action = action.lower()
    settle = action_seconds(payload, "settle_seconds", 0.3, minimum=0)
    board = board or BOARDS[device]
    if kind in {"touch", "longpress"} and board.touch:
        width, height = board.size
        x = bounded_int(payload.get("x"), "x", width - 1)
        y = bounded_int(payload.get("y"), "y", height - 1)
        if action not in ("tap", "click", "hold", "down", "up"):
            raise ServiceError("invalid_input", "Expected tap, click, hold, down or up", 400)
        if action in {"down", "up"}:
            return "touch", (x, y, int(action == "down"), 0), settle
        seconds = action_seconds(payload, "seconds", 1) if action == "hold" else (
            action_seconds(payload, "hold_seconds", 0.5) if kind == "longpress" else 0.12)
        return "touch", (x, y, 1, math.ceil(seconds * 1000)), settle
    if kind == "drag" and board.touch:
        width, height = board.size
        points = tuple(bounded_int(payload.get(field), field, limit)
                       for field, limit in (("x1", width - 1), ("y1", height - 1),
                                            ("x2", width - 1), ("y2", height - 1)))
        return "drag", points, settle
    if kind == "encoder" and device in {"dial", "stickt2"}:
        delta = validate_encoder_delta(payload.get("delta"))
        if device == "stickt2":
            if "edge_period_ms" in payload:
                raise ServiceError("not_supported_on_runtime", "StickT2's I2C encoder accepts a detent delta", 409)
            return "encoder-step", (delta,), settle
        period = validate_encoder_edge_period_ms(payload.get("edge_period_ms", DEFAULT_EDGE_PERIOD_MS))
        return "encoder", (delta, period), settle
    if device == "tab5" and kind == "touch-contact":
        width, height = BOARDS[device].size
        contact = bounded_int(payload.get("contact_id"), "contact_id", 4)
        x = bounded_int(payload.get("x"), "x", width - 1)
        y = bounded_int(payload.get("y"), "y", height - 1)
        if action not in {"down", "up"}:
            raise ServiceError("invalid_input", "touch-contact requires down or up", 400)
        return "contact", (contact, x, y, int(action == "down")), settle
    if device == "tab5" and kind == "usb-hid":
        if action == "attach" and payload.get("device") in ("keyboard", "gamepad"):
            return "usb-hid", (payload["device"],), settle
        if action == "detach":
            return "usb-unplug", (), settle
        if action == "report":
            data = payload.get("report")
            if isinstance(data, list) and len(data) in (3, 8):
                return "usb-report", tuple(f"{bounded_int(value, 'report byte', 255):02x}" for value in data), settle
        raise ServiceError("invalid_input", "Use usb-hid attach, detach or a 3/8-byte report", 400)
    if kind in {"key", "keyboard", "button"}:
        field = "control" if kind == "button" else "key"
        name = control_name(payload.get(field), field)
        if kind == "key" and name in {"p", "3"} and device in {
            "cores3", "papercolor", "papermono", "stackchan", "sticks3", "stopwatch",
        }:
            name = "power"
        core2_button_x = {"a": 63, "b": 160, "c": 258}.get(name) if device == "core2" else None
        if core2_button_x is not None and kind != "keyboard":
            # The FT6336 touch strip extends past the 240-row framebuffer.
            if action in ("down", "up"):
                return "touch", (core2_button_x, 260, int(action == "down"), 0), settle
            if action in ("tap", "click", "hold"):
                seconds = action_seconds(payload, "seconds", 1, maximum=10) if action == "hold" else (
                    action_seconds(payload, "hold_seconds", 0.45) if kind == "key" else 0.12)
                return "touch", (core2_button_x, 260, 1, math.ceil(seconds * 1000)), settle
        if kind == "button" and device == "cardputer-adv" and name in {"boot", "g0", "btn", "gpio0"} and action in ("down", "up"):
            return "gpio", (int(action == "up"),), settle
        if device in {"cardputer", "cardputer-adv"} and kind in {"keyboard", "key"} and action in ("down", "up"):
            key = KEY_ALIASES.get(name, name)
            if key in KEYS:
                return "key-edge", (key, int(action == "down")), settle
        mapped = gpio_button(device, name) if kind in {"button", "key"} else None
        if mapped and action in {"down", "up"}:
            return "button", (mapped, int(action == "up"), 0), settle
        if kind in {"button", "key"} and device == "nesso-n1" and action in {"down", "up"}:
            key = {"key1": "A", "key2": "B", "a": "A", "b": "B"}.get(name)
            if key:
                return "key", (key, action), settle
        if action not in ("tap", "click", "hold"):
            raise ServiceError("invalid_input", "Expected tap, click or hold", 400)
        duration = action_seconds(payload, "seconds", 1, maximum=10 if kind == "button" else 5) if action == "hold" else (
            action_seconds(payload, "hold_seconds", 0.12) if kind == "key" else 0.12)
        hold = math.ceil(duration * 1000)
        if mapped:
            return "button", (mapped, 0, hold), settle
        if kind in {"button", "key"}:
            if device in {"cores3", "stackchan"} and name == "power":
                return "pwrkey", (hold,), settle
            if device in {"papercolor", "papermono", "sticks3", "stopwatch"} and name in {"power", "pwr"}:
                if action == "hold":
                    raise ServiceError("not_supported_on_runtime", "This PM1 model exposes a power-key pulse", 409)
                return "pwrkey", (), settle
            if device in {"cardputer", "cardputer-adv"} and name in {"boot", "g0", "btn", "gpio0"}:
                return "press", (hold,), settle
            if device == "stamplc":
                key = {"key1": "a", "key2": "b", "key3": "c", "a": "a", "b": "b", "c": "c"}.get(name)
                if key:
                    return "plc-key", (key, hold), settle
            if device in {"stickc", "stickc-plus", "stickc-plus-se", "stickt2"} and name in {"power", "pwr"}:
                return "pmic-key", ("long" if action == "hold" else "short",), settle
        if kind != "button" and device in {"cardputer", "cardputer-adv"}:
            key = KEY_ALIASES.get(name, name)
            if key in KEYS:
                return "key", (key, hold), settle
    if kind == "imu":
        accel = vector(payload, "accel", 32)
        gyro = vector(payload, "gyro", 4000)
        if "mag" in payload:
            if device not in {"cores3", "stackchan"}:
                raise ServiceError("not_supported_on_runtime", "Use a separate mag sample on boards with a separate magnetometer command", 409)
            return kind, (*accel, *gyro, *vector(payload, "mag", 2000)), settle
        return kind, (*accel, *gyro), settle
    if kind == "mag" and device in {"atoms3r", "atoms3r-cam", "atoms3r-m12", "m5stick"}:
        return kind, tuple(vector(payload, "mag", 2000)), settle
    if kind == "als" and device in {"cores3", "stackchan"}:
        return kind, tuple(bounded_int(payload.get(key), key, limit)
                           for key, limit in (("ch0", 65535), ("ch1", 65535), ("proximity", 2047))), settle
    if kind == "battery" and device in {"cores3", "stackchan"}:
        charging = payload.get("charging")
        if type(charging) is not bool or ("vbus" in payload and type(payload["vbus"]) is not bool):
            raise ServiceError("invalid_input", "battery charging and optional vbus must be boolean", 400)
        args = (bounded_int(payload.get("mv"), "mv", 16383),
                bounded_int(payload.get("percent"), "percent", 100), int(charging))
        return kind, (*args, int(payload["vbus"])) if "vbus" in payload else args, settle
    if kind == "battery" and device == "tab5":
        charging = payload.get("charging")
        if type(charging) is not bool:
            raise ServiceError("invalid_input", "battery charging must be boolean", 400)
        return kind, (bounded_int(payload.get("mv"), "mv", 16000),
                      bounded_int(payload.get("ma"), "ma", 32767, minimum=-32768),
                      int(charging)), settle
    if kind == "battery":
        return (*battery_command(device, board, payload), settle)
    if kind in {"rfid", "nfc-tag"}:
        op = {("dial", "rfid"): "rfid", ("papermono", "nfc-tag"): "paper-tag",
              ("stackchan", "nfc-tag"): "nfc-tag"}.get((device, kind))
        if op:
            uid = payload.get("uid")
            allowed = (8,) if op == "rfid" else (8, 14)
            if uid is None:
                return op, ("none",), settle
            if (not isinstance(uid, str) or len(uid) not in allowed
                    or any(c not in "0123456789abcdefABCDEF" for c in uid)):
                raise ServiceError("invalid_input", "Provide a hexadecimal tag UID or null", 400)
            return op, (uid.lower(),), settle
    if kind == "ir-nec" and device == "sticks3":
        address = bounded_int(payload.get("address"), "address", 65535)
        command = bounded_int(payload.get("command"), "command", 255)
        return kind, (f"{address:04x}", f"{command:02x}"), settle
    if (kind == "sht40" and device == "papercolor" or
            kind == "enviii" and board.name == "m5stack-nanoc6-enviii"):
        return kind, (bounded_number(payload, "temperature_c", -40, 125),
                      bounded_number(payload, "humidity_pct", 0, 100)), settle
    if kind == "head-touch" and device == "stackchan":
        return kind, (bounded_int(payload.get("pad"), "pad", 2),
                      bounded_int(payload.get("strength"), "strength", 3)), settle
    if kind == "plc-temperature" and device == "stamplc":
        return kind, (round(bounded_number(payload, "temperature_c", -55, 125) * 1000),), settle
    if (kind == "plc-input" and device == "stamplc" or
            kind == "pm1-gpio" and device in {"sticks3", "stopwatch"}):
        level = payload.get("high")
        if type(level) is not bool:
            raise ServiceError("invalid_input", "high must be boolean", 400)
        return kind, (bounded_int(payload.get("channel"), "channel", 7 if kind == "plc-input" else 4),
                      int(level)), settle
    if kind == "adc" and board.chip_id == 9:
        pin = bounded_int(payload.get("gpio"), "gpio", 20, minimum=1)
        volts = payload.get("volts")
        if type(volts) not in (int, float) or not 0 <= volts <= 3.3:
            raise ServiceError("invalid_input", "volts must be between 0 and 3.3", 400)
        return kind, (pin, volts), settle
    raise ServiceError("not_supported_on_runtime", "Input has no esp32sim board mapping", 409)


def gpio_button(device, name):
    if device == "stackchan":
        return {"a": "a", "left": "a", "1": "a", "b": "b", "right": "b", "2": "b"}.get(name)
    if device in {"atom-lite", "atom-matrix", "atom-matrix-v11", "atomu", "atom-echo"}:
        return "a" if name in {"a", "user", "button", "btn", "btn1"} else None
    if device.startswith("atoms3") or device == "atom-echos3r":
        return {"a": "button", "user": "button", "button": "button", "boot": "boot"}.get(name)
    if device == "nanoc6":
        return "boot" if name in {"a", "button", "boot"} else None
    if device == "dial":
        return {"a": "a", "button": "a", "boot": "boot"}.get(name)
    if device == "cardputer":
        return "g0" if name in {"g0", "boot", "btn", "gpio0", "f12"} else None
    if device == "m5stick":
        return "a" if name == "a" else None
    if device == "stickc-plus2" and name in {"c", "pwr", "power"}:
        return "pwr"
    if device == "basic-v27":
        return name if name in {"a", "b", "c"} else None
    if device in {"papermono", "papercolor"}:
        return {
            "a": "a", "b": "b", "key1": "a", "key2": "b",
            **({"c": "c", "key3": "c"} if device == "papercolor" else {}),
        }.get(name)
    if device in {"paperdiy", "stickc", "stickc-plus", "stickc-plus-se", "stickc-plus2", "stickt2",
                  "sticks3", "stopwatch"}:
        return name if name in {"a", "b"} else None
    return None


def battery_command(device, board, payload):
    def number(field, maximum, minimum=0):
        return bounded_int(payload.get(field), field, maximum, minimum=minimum)

    def flag(field):
        value = payload.get(field)
        if type(value) is not bool:
            raise ServiceError("invalid_input", f"{field} must be boolean", 400)
        return int(value)

    if device in {"sticks3", "stopwatch"}:
        return "battery", (number("mv", 65535), flag("charging"))
    if device in {"papermono", "papercolor"}:
        args = (number("mv", 4500, 2500), flag("charging"))
        return "paper-battery", (*args, number("vbus_mv", 5500)) if "vbus_mv" in payload else args
    if device == "core2":
        if board.name == "m5stack-core2-axp192":
            return "battery", (number("mv", 65535), number("ma", 32767, -32768))
        return "battery", (number("mv", 16383), number("percent", 100), flag("charging"))
    if device == "basic-v27":
        return "battery", (number("bars", 4), flag("charging"), flag("full"))
    if device == "nesso-n1":
        return "battery", (number("mv", 65535), number("ma", 32767, -32768),
                           number("percent", 100), flag("vbus"))
    if device in {"stickc", "stickc-plus", "stickc-plus-se", "m5stick"}:
        return "battery-mv", (number("mv", 65535),)
    raise ServiceError("not_supported_on_runtime", "Battery has no esp32sim board mapping", 409)


def bounded_number(payload, field, minimum, maximum):
    value = payload.get(field)
    if type(value) not in (int, float) or not minimum <= value <= maximum:
        raise ServiceError("invalid_input", f"{field} must be between {minimum} and {maximum}", 400)
    return value


def bounded_int(value, field, maximum, *, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ServiceError("invalid_input", f"{field} must be an integer between {minimum} and {maximum}", 400)
    return value


def vector(payload, field, limit):
    value = payload.get(field)
    if (not isinstance(value, list) or len(value) != 3
            or any(type(component) not in (int, float) or not -limit <= component <= limit for component in value)):
        raise ServiceError("invalid_input", f"{field} requires three numbers between {-limit} and {limit}", 400)
    return value


def decode_frame(data, board):
    if len(data) < 5 or data[0] != 1:
        raise ServiceError("invalid_runtime_frame", "Missing esp32sim framebuffer", 502)
    width, height = struct.unpack_from("<HH", data, 1)
    if (width, height) != board.size or len(data) != 5 + width * height * 2:
        raise ServiceError("invalid_runtime_frame", "Unexpected esp32sim framebuffer geometry", 502)
    return width, height, data[5:]


def read_state(control):
    reply = control.request("state-snapshot")
    nodes = reply.get("value") if isinstance(reply, dict) else None
    if (not isinstance(nodes, dict) or "/soc" not in nodes or "/board" not in nodes
            or any(not isinstance(fields, dict) or path.split("/", 2)[:2] not in (["", "soc"], ["", "board"])
                   for path, fields in nodes.items())):
        raise ServiceError("invalid_runtime_state", "Invalid esp32sim state snapshot", 502)
    tree = {"/machine": {}}
    for path, fields in nodes.items():
        parent = "/machine"
        for component in path[1:].split("/"):
            parent += "/" + component
            tree.setdefault(parent, {})
        tree[parent].update(fields)
    return tree


def state_properties(tree, path):
    if not isinstance(path, str) or path not in tree:
        raise ServiceError("unknown_state_path", "No modeled esp32sim component at this path", 404)
    fields = dict(tree[path])
    prefix = path + "/"
    direct = sorted(name[len(prefix):] for name in tree
                    if name.startswith(prefix) and "/" not in name[len(prefix):])
    return fields, direct


def atom_io_state(tree, pin=39, *, with_leds=True):
    high = tree.get(f"/machine/soc/gpio/{pin}", {}).get("level")
    if type(high) is not bool:
        return None
    values = {"pressed": not high, "input-level": high}
    if not with_leds:
        return values
    leds = tree.get("/machine/board/leds", {})
    rgb, updates = leds.get("rgb"), leds.get("updates")
    if (not isinstance(rgb, list) or len(rgb) not in {1, 25}
            or type(updates) is not int or updates < 0):
        return None
    if any(not isinstance(pixel, list) or len(pixel) != 3
           or any(type(value) is not int or not 0 <= value <= 255 for value in pixel)
           for pixel in rgb):
        return None
    packed = [int.from_bytes(bytes(pixel), "big") for pixel in rgb]
    return {**values, "led-rgb": packed[0] if len(packed) == 1 else packed, "led-frames": updates}


def legacy_device_state(tree, probes):
    components, errors = {}, {}
    for name, probe in probes.items():
        path = probe["path"]
        node = LEGACY_STATE_PATHS.get(path)
        if path == "/machine/rmt0":
            fields = tree.get("/machine/soc/rmt/0", {})
        else:
            fields = tree.get(f"/machine/board/{node}" if node else path, {})
        expected = probe["properties"]
        properties = {key: fields[key] for key in expected if key in fields}
        if properties:
            components[name] = {"path": path, "properties": properties}
        missing = {key: "No modeled esp32sim property" for key in expected if key not in fields}
        if missing:
            errors[name] = missing
    return components, errors


def state_type(value):
    return {int: "int", bool: "bool", str: "str", float: "number", list: "array", dict: "object"}.get(type(value), "null")


class Control:
    """Single socket reader, bounded waits, and a reply ID for each scheduler sample."""

    def __init__(self, sock, on_text, on_audio, on_stereo=None):
        self.socket = sock
        self.socket.settimeout(5)
        self.on_text = on_text
        self.on_audio = on_audio
        self.on_stereo = on_stereo
        self.condition = threading.Condition()
        self.write_lock = threading.Lock()
        self.pending = {}
        self.sequence = 0
        self.closed = False
        self.poweroff_frame = None
        self.reader = threading.Thread(target=self._read, name="esp32sim-control", daemon=True)
        self.reader.start()

    def _read(self):
        try:
            with self.socket.makefile("rb") as stream:
                # A healthy VM emits stats frequently. Socket deadlines
                # bound transport stalls even between requests.
                while header := stream.read(2):
                    opcode, size = header
                    if size >= 126:
                        size = int.from_bytes(stream.read(2 if size == 126 else 8), "big")
                    if not 0 < size <= 8 << 20:
                        raise ValueError("invalid esp32sim message length")
                    data = stream.read(size)
                    if len(data) != size:
                        raise EOFError()
                    if opcode == 0x81:
                        message = json.loads(data)
                        if message.get("t") == "service":
                            self._reply(message["id"], message)
                        else:
                            self.on_text(message)
                    elif opcode == 0x82 and data[0] == 6:
                        self._reply(struct.unpack_from("<I", data, 1)[0], data[5:])
                    elif opcode == 0x82 and data[0] == 2:
                        self.on_audio(struct.unpack_from("<I", data, 1)[0], data[5:])
                    elif opcode == 0x82 and data[0] == 8 and self.on_stereo is not None:
                        self.on_stereo(struct.unpack_from("<I", data, 1)[0], data[5:])
                    elif opcode == 0x82 and data[0] == 7:
                        with self.condition:
                            self.poweroff_frame = data[1:]
        except (OSError, ValueError, EOFError, struct.error):
            pass
        finally:
            with self.condition:
                self.closed = True
                self.condition.notify_all()
            self._shutdown()

    def _reply(self, request_id, message):
        with self.condition:
            if request_id in self.pending:
                self.pending[request_id] = message
                self.condition.notify_all()

    def send(self, message):
        encoded = json.dumps(message, separators=(",", ":")).encode()
        try:
            with self.write_lock:
                self.socket.sendall(struct.pack(">I", len(encoded)) + encoded)
        except OSError as error:
            self._shutdown()
            raise ServiceError("runtime_control_unavailable", "esp32sim control socket closed", 503) from error

    def request(self, op, args=(), *, allow_disconnect=False):
        deadline = time.monotonic() + 10
        with self.condition:
            if self.closed or len(self.pending) >= 32:
                raise ServiceError("runtime_control_unavailable", "esp32sim control unavailable", 503)
            self.sequence = (self.sequence + 1) % (1 << 32)
            request_id = self.sequence
            self.pending[request_id] = None
        try:
            self.send({"t": "service", "id": request_id, "op": op, "args": " ".join(map(str, args))})
            with self.condition:
                while self.pending[request_id] is None and not self.closed:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self.condition.wait(remaining)
                reply = self.pending[request_id]
            if reply is None:
                if allow_disconnect and self.closed:
                    return None
                raise ServiceError("runtime_control_unavailable", f"esp32sim gave no {op} reply", 503)
            if isinstance(reply, dict) and not reply.get("ok"):
                if op == "frame":
                    raise ServiceError("frame_unavailable", "esp32sim has not produced a framebuffer", 404)
                raise ServiceError("runtime_input_rejected", f"esp32sim refused {op}", 409)
            return reply
        finally:
            with self.condition:
                self.pending.pop(request_id, None)

    def _shutdown(self):
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self):
        self._shutdown()
        self.reader.join(timeout=6)
        self.socket.close()
