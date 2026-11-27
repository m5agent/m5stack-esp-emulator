"""Pinned esp32sim native runtime and its private single-owner control stream."""
from __future__ import annotations

from dataclasses import dataclass
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
from firmware_analysis import find_flash_bootloader, parse_partition_table

RUNTIME = "esp32sim"
BACKEND = "esp32sim-esp32s3"
ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "scripts/esp32sim-runtime.lock.json"
ROM_NAME = "esp32s3_rev0_rom.elf"
P4_ROM_NAME = "esp32p4_rev0_rom.elf"
P4_REV3_ROM_NAME = "esp32p4_rev300_rom.elf"
C6_ROM_NAME = "esp32c6_rev0_rom.elf"
MAX_PCM_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class Board:
    name: str
    flash: int
    psram: int
    size: tuple[int, int]
    chip_id: int = 9

    @property
    def is_tab5(self):
        return self.chip_id == 0x12


BOARDS = {
    "cores3": Board("m5stack-cores3", 16 << 20, 8 << 20, (320, 240)),
    "cardputer-adv": Board("m5stack-cardputer-adv", 8 << 20, 0, (240, 135)),
    "tab5": Board("m5stack-tab5", 16 << 20, 32 << 20, (720, 1280), 0x12),
}
TAB5_PANELS = {
    "gt911-ili9881c": BOARDS["tab5"],
    "st7123": Board("m5stack-tab5-st7123", 16 << 20, 32 << 20, (720, 1280), 0x12),
}
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
            return [self.binary, self.rom]
        return [
            self.binary_for(board),
            *(self.rom.with_name(name) for name in (P4_ROM_NAME, P4_REV3_ROM_NAME, C6_ROM_NAME)),
            *(self.manifest.parent / "tab5-c6" / item["path"] for item in lock["tab5_c6"]["files"].values()),
        ]

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
            "flash_bytes": board.flash, "psram_bytes": board.psram,
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


def parse_network(value):
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {"profile", "ssid", "psk", "policy"}:
        raise ServiceError("invalid_network", "esp32sim accepts profile, ssid, psk and policy", 400)
    if value.get("profile", "esp32sim-sta") != "esp32sim-sta":
        raise ServiceError("not_supported_on_runtime", "esp32sim supports the esp32sim-sta profile", 409)
    request_policy = value.get("policy")
    policy = parse_network_policy(request_policy)
    if (not isinstance(request_policy, dict)
            or request_policy.keys() - {"isolation", "egress", "dns"}
            or request_policy.get("isolation") != "trusted-host"
            or policy.isolation != "trusted-host" or policy.egress != "native"
            or policy.allowed_hosts or policy.allowed_domains or policy.allowed_endpoints):
        raise ServiceError("not_supported_on_runtime", "esp32sim NAT requires explicit trusted-host native policy", 409)
    ssid, psk = value.get("ssid", "esp32sim"), value.get("psk", "")
    for text, name, minimum, maximum in ((ssid, "ssid", 1, 32), (psk, "psk", 8, 63)):
        if (not isinstance(text, str) or not text.isascii() or "," in text
                or (text and not text.isprintable())
                or (name == "ssid" or text) and not minimum <= len(text) <= maximum):
            raise ServiceError("invalid_network", f"Invalid esp32sim Wi-Fi {name}", 400)
    return {"profile": "esp32sim-sta", "ssid": ssid, "psk": psk, "policy": policy.evidence()}


def spawn_command(installation, board, fd, flash, *, sd=None, cam=None, mic=None, network=None, pcap=None):
    rom = installation.rom.with_name(p4_rom_name(flash)) if board.is_tab5 else installation.rom
    command = [
        str(installation.binary_for(board)), "--board", board.name, "--rom", str(rom),
        "--boot", "rom", "--flash-image", str(flash), "--console", "none",
        "--service-fd", str(fd),
    ]
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
    if network:
        settings = f"ssid={network['ssid']}"
        if network["psk"]:
            settings += f",psk={network['psk']}"
        command += ["--wifi", settings, "--net", "nat"]
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


def input_command(device, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
        raise ServiceError("invalid_input", "input kind is required", 400)
    kind = payload["kind"]
    action = payload.get("action", "tap")
    if not isinstance(action, str):
        raise ServiceError("invalid_input", "action must be a string", 400)
    action = action.lower()
    settle = action_seconds(payload, "settle_seconds", 0.3, minimum=0)
    if kind in {"touch", "longpress"} and device in {"cores3", "tab5"}:
        width, height = BOARDS[device].size
        x = bounded_int(payload.get("x"), "x", width - 1)
        y = bounded_int(payload.get("y"), "y", height - 1)
        if action not in ("tap", "click", "hold", "down", "up"):
            raise ServiceError("invalid_input", "Expected tap, click, hold, down or up", 400)
        if action in {"down", "up"}:
            return "touch", (x, y, int(action == "down"), 0), settle
        seconds = action_seconds(payload, "seconds", 1) if action == "hold" else (
            action_seconds(payload, "hold_seconds", 0.5) if kind == "longpress" else 0.12)
        return "touch", (x, y, 1, math.ceil(seconds * 1000)), settle
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
        if kind == "button" and device == "cardputer-adv" and name in {"boot", "g0", "btn", "gpio0"} and action in ("down", "up"):
            return "gpio", (int(action == "up"),), settle
        if device == "cardputer-adv" and kind in {"keyboard", "key"} and action in ("down", "up"):
            key = KEY_ALIASES.get(name, name)
            if key in KEYS:
                return "key-edge", (key, int(action == "down")), settle
        if action not in ("tap", "click", "hold"):
            raise ServiceError("invalid_input", "Expected tap, click or hold", 400)
        duration = action_seconds(payload, "seconds", 1, maximum=10 if kind == "button" else 5) if action == "hold" else (
            action_seconds(payload, "hold_seconds", 0.12) if kind == "key" else 0.12)
        hold = math.ceil(duration * 1000)
        if kind == "button":
            if device == "cores3" and name == "power":
                return "pwrkey", (hold,), settle
            if device == "cardputer-adv" and name in {"boot", "g0", "btn", "gpio0"}:
                return "press", (hold,), settle
        elif device == "cardputer-adv":
            key = KEY_ALIASES.get(name, name)
            if key in KEYS:
                return "key", (key, hold), settle
    if kind == "imu":
        accel = vector(payload, "accel", 32)
        gyro = vector(payload, "gyro", 4000)
        if "mag" in payload:
            if device != "cores3":
                raise ServiceError("not_supported_on_runtime", "Only CoreS3 exposes magnetometer injection", 409)
            return kind, (*accel, *gyro, *vector(payload, "mag", 2000)), settle
        return kind, (*accel, *gyro), settle
    if kind == "als" and device == "cores3":
        return kind, tuple(bounded_int(payload.get(key), key, limit)
                           for key, limit in (("ch0", 65535), ("ch1", 65535), ("proximity", 2047))), settle
    if kind == "battery" and device == "cores3":
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
    if kind == "adc" and device != "tab5":
        pin = bounded_int(payload.get("gpio"), "gpio", 20, minimum=1)
        volts = payload.get("volts")
        if type(volts) not in (int, float) or not 0 <= volts <= 3.3:
            raise ServiceError("invalid_input", "volts must be between 0 and 3.3", 400)
        return kind, (pin, volts), settle
    raise ServiceError("not_supported_on_runtime", "Input has no esp32sim board mapping", 409)


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


class Control:
    """Single socket reader, bounded waits, and a reply ID for each scheduler sample."""

    def __init__(self, sock, on_text, on_audio):
        self.socket = sock
        self.socket.settimeout(5)
        self.on_text = on_text
        self.on_audio = on_audio
        self.condition = threading.Condition()
        self.write_lock = threading.Lock()
        self.pending = {}
        self.sequence = 0
        self.closed = False
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

    def request(self, op, args=()):
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
                raise ServiceError("runtime_control_unavailable", f"esp32sim gave no {op} reply", 503)
            if isinstance(reply, dict) and not reply.get("ok"):
                if op == "frame":
                    raise ServiceError("frame_unavailable", "esp32sim has not produced a framebuffer", 409)
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
