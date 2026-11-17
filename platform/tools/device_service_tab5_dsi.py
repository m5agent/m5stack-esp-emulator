"""Receive the native esp-emu Tab5 DSI stream without guest symbols."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import struct
import threading
import time

from device_service_errors import ServiceError


TAB5_DSI_RUNTIME_SHA256 = "633a35f993300a765634ed78a2dbcfd5ffcd5c3f2f354a2dddabeb6108240828"
TAB5_GT911_PART_SHA256 = "a0852d08d6cc04a11dcdd57c417b497f857be3e6265f8b690968ae3338cd3ce9"
TAB5_ST7123_I2C_PART_SHA256 = "6eaa3664fd81ce7e8f56bc0f84ad124ca2afcce21c947e74bbb41f1d9802d106"
TAB5_ST7123_TOUCH_PART_SHA256 = "fcd3ae013162555e7198e7aed0b58e2fbb8860477132d96fa60155cd11f62454"
TAB5_ST7123_HOLD_PART_SHA256 = "0999697f5aad5b87d8802f628c0313425866a9d3ad232c1b5e0db15b2fe12e87"
TAB5_ST7123_DRAG_PART_SHA256 = "56e83f9a99119642ce34bbfde838cd96556d8587c52baba411729569f3d1f63d"
TAB5_ST7123_POWER_PART_SHA256 = "655ee4735028357d21ab9341c9d3a6cf14bc6720b6869be763f29b1458feb0a9"
TAB5_PARTS_SOURCE = Path(__file__).resolve().parents[1] / "esp-parts"
TAB5_GT911_SIZE = (720, 1280)
MAX_PART_BYTES = 144 * 1024
MAX_MESSAGE_BYTES = 128 * 1024
MAX_PIXELS = 2 * 1024 * 1024
MAX_DIMENSION = 2048
RGB565_LE = 1
BGR888 = 2
PIXEL_BYTES = {RGB565_LE: 2, BGR888: 3}

# esp-emulator v1.1.0 proto/esp_cosim.proto: Register v1, device name,
# one claim of DsiClaim VC0. Co-sim writes are length-prefixed protobuf.
REGISTER_VC0 = b"\x22\x12\x08\x01\x12\x09tab5-view\x1a\x03\xa2\x01\x00"


def tab5_dsi_runtime(value: str) -> Path:
    """Admit the exact native release that was tested with the DSI receiver."""
    try:
        runtime = Path(value).resolve(strict=True)
        if runtime.is_file() and os.access(runtime, os.X_OK):
            with runtime.open("rb") as binary:
                if hashlib.file_digest(binary, "sha256").hexdigest() == TAB5_DSI_RUNTIME_SHA256:
                    return runtime
    except (OSError, RuntimeError, ValueError):
        pass
    raise ServiceError(
        "tab5_dsi_runtime_unavailable", "configured Tab5 DSI runtime is not the qualified esp-emu 1.1.0 release", 409
    )


def tab5_dsi_board_devices(board: str) -> tuple[str, ...]:
    """Select the hardware I²C identification registers of the panel revision."""
    if not board:
        return ()
    if board == "gt911-ili9881c":
        # GT911 backup address on Tab5 HP I2C controller 1. The product ID
        # begins with ASCII "911" at 0x8140; zero touch status means idle.
        return ("1:0x14,width=2,fill=0,reg=0x8140=0x39,reg=0x8141=0x31,reg=0x8142=0x31",)
    if board == "st7123":
        # M5GFX uses firmware version 3 for the ST7123. After GPIO board
        # detection its touch driver can also read the ID over hardware I²C.
        return ("1:0x55,width=2,fill=0,reg=0x0000=0x03",)
    raise ServiceError("tab5_dsi_board_unavailable", "unknown native DSI Tab5 board revision", 409)


def parse_tab5_board_overrides(value: str, allowed: frozenset[str]) -> dict[str, str]:
    if not value:
        return {}
    try:
        overrides = json.loads(value)
        if not isinstance(overrides, dict):
            raise ValueError("expected an object")
        for digest, board in overrides.items():
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None or not isinstance(board, str) or not board:
                raise ValueError("each entry needs an admitted firmware SHA and board revision")
            tab5_dsi_board_devices(board)
        if allowed and not overrides.keys() <= allowed:
            raise ValueError("board override hashes must be in the configured DSI allowlist")
    except (ServiceError, ValueError) as error:
        raise ValueError(f"M5_TAB5_DSI_BOARD_OVERRIDES: {error}") from error
    return overrides


def stage_tab5_gt911_part(value: str, board: str, session_dir: Path) -> Path:
    """Bind the source board and exact ESP Part bytes to this guest."""
    if board != "gt911-ili9881c":
        raise ServiceError(
            "tab5_gt911_part_unavailable", "Tab5 GT911 requires the gt911-ili9881c board revision", 409
        )
    return _stage_tab5_part(
        value, session_dir, "tab5-gt911", "m5_tab5_gt911.wasm", (TAB5_GT911_PART_SHA256,),
        "tab5_gt911_part_unavailable",
    )[0]


def stage_tab5_st7123_i2c_part(value: str, session_dir: Path) -> Path:
    return _stage_tab5_part(
        value, session_dir, "tab5-st7123-gpio", "m5_tab5_gpio_i2c.wasm", (TAB5_ST7123_I2C_PART_SHA256,),
        "tab5_st7123_i2c_part_unavailable",
    )[0]


def stage_tab5_st7123_touch_part(value: str, session_dir: Path) -> tuple[Path, str]:
    return _stage_tab5_part(
        value, session_dir, "tab5-st7123-gpio", "m5_tab5_gpio_i2c.wasm",
        (TAB5_ST7123_TOUCH_PART_SHA256, TAB5_ST7123_HOLD_PART_SHA256, TAB5_ST7123_DRAG_PART_SHA256,
         TAB5_ST7123_POWER_PART_SHA256),
        "tab5_st7123_touch_part_unavailable",
    )


def _stage_tab5_part(
    value: str, session_dir: Path, source: str, module: str, expected: tuple[str, ...], error_code: str,
) -> tuple[Path, str]:
    try:
        with Path(value).open("rb") as stream:
            part = stream.read(MAX_PART_BYTES + 1)
        if len(part) > MAX_PART_BYTES:
            raise ValueError("ESP Part exceeds size limit")
        digest = hashlib.sha256(part).hexdigest()
        if digest not in expected:
            raise ValueError("unexpected ESP Part hash")
        board = "board-power.json" if digest == TAB5_ST7123_POWER_PART_SHA256 else "board.json"
        config = (TAB5_PARTS_SOURCE / source / board).read_bytes()
        (session_dir / module).write_bytes(part)
        path = session_dir / "tab5-cosim-board.json"
        path.write_bytes(config)
        return path, digest
    except (OSError, ValueError) as error:
        raise ServiceError(
            error_code, "configured Tab5 ESP Part could not be verified", 409
        ) from error


class Tab5NativeTouch:
    """Submit native Tab5 input and wait for guest consumption."""

    CONTROLLER: str
    PART_NAME: str
    ALLOW_EXPIRED_REPORTS = False

    def __init__(self, port: int):
        self.port = port

    def _error(self, code: str, description: str) -> ServiceError:
        return ServiceError(f"tab5_{self.CONTROLLER}_{code}", f"Tab5 {self.CONTROLLER.upper()} {description}", 409)

    def _command(self, command: str) -> str:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1) as sock:
                sock.sendall((command + "\n").encode("ascii"))
                with sock.makefile("rb") as stream:
                    reply = stream.readline(1024)
            if reply.endswith(b"\n"):
                return reply.decode("ascii").strip()
        except (OSError, UnicodeError):
            pass
        raise self._error("unavailable", "control endpoint is unavailable")

    def _part_state(self) -> dict[str, str]:
        response = self._command(f"part {self.PART_NAME} state")
        if response.startswith("ok "):
            try:
                return dict(item.split("=", 1) for item in response[3:].split())
            except ValueError:
                pass
        raise self._error("unavailable", "state could not be read")

    def _state(self) -> tuple[int, int, int, bool]:
        values = self._part_state()
        if values.get("power_latched") == "true" and values.get("chip_enabled") == "false":
            raise ServiceError("tab5_guest_powered_off", "Tab5 board latch holds the guest powered off", 409)
        try:
            if values["ready"] in {"true", "false"} and values["contact"] in {"true", "false"}:
                reports = int(values["reports"])
                acknowledged = int(values["acknowledged"])
                rejected = int(values["rejected_inputs"])
                if 0 <= acknowledged <= reports and rejected >= 0:
                    idle = values["ready"] == values["contact"] == "false"
                    return reports, acknowledged, rejected, idle
        except (KeyError, ValueError):
            pass
        raise self._error("unavailable", "state could not be read")

    def _idle_counters(self) -> tuple[int, int, int]:
        reports, acknowledged, rejected, idle = self._state()
        if not idle or (not self.ALLOW_EXPIRED_REPORTS and reports != acknowledged):
            raise self._error("busy", "has a pending report")
        return reports, acknowledged, rejected

    def _queue(self, action: str) -> None:
        if self._command(f"part {self.PART_NAME} input {action}") != "ok":
            raise self._error("unavailable", "could not queue the input")

    def _wait_acknowledged(self, initial, minimum, check_cancelled, timeout) -> dict:
        reports, acknowledged, rejected = initial
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_cancelled()
            current_reports, current_acknowledged, current_rejected, idle = self._state()
            if current_rejected != rejected:
                raise self._error("busy", "rejected the input")
            observed = current_acknowledged - acknowledged
            if idle and current_reports - reports == observed and observed >= minimum:
                return {
                    "reports": current_reports - reports,
                    "acknowledged": current_acknowledged - acknowledged,
                }
            time.sleep(0.05)
        raise ServiceError(
            f"tab5_{self.CONTROLLER}_ack_timeout",
            f"Tab5 guest did not acknowledge the {self.CONTROLLER.upper()} contact and release", 409,
        )

    def tap(self, x: int, y: int, check_cancelled, *, timeout: float = 12) -> dict:
        initial = self._idle_counters()
        self._queue(f"tap:{x},{y}")
        return self._wait_acknowledged(initial, 2, check_cancelled, timeout)


class Tab5Gt911Touch(Tab5NativeTouch):
    """Submit GT911 taps and single-contact drags."""

    CONTROLLER = "gt911"
    PART_NAME = "gt911"
    DRAG_STEPS = 5
    DRAG_STEP_MS = 60

    def drag(self, x1: int, y1: int, x2: int, y2: int, check_cancelled, *, timeout: float = 12) -> dict:
        initial = self._idle_counters()
        prefix, separator, value = self._command("part clock").partition(" ")
        if prefix != "ok" or not separator or not value.isdecimal():
            raise ServiceError("tab5_gt911_unavailable", "Tab5 GT911 guest clock is unavailable", 409)
        start_ms = int(value) + self.DRAG_STEP_MS
        release_ms = start_ms + self.DRAG_STEP_MS * (self.DRAG_STEPS + 1)
        try:
            self._queue(f"down:{x1},{y1} at {start_ms}")
            for step in range(1, self.DRAG_STEPS + 1):
                x = x1 + (x2 - x1) * step // self.DRAG_STEPS
                y = y1 + (y2 - y1) * step // self.DRAG_STEPS
                self._queue(f"move:{x},{y} at {start_ms + self.DRAG_STEP_MS * step}")
        finally:
            # Close the contact even if an intermediate command failed.
            try:
                self._queue(f"up at {release_ms}")
            except ServiceError as error:
                raise ServiceError(
                    "tab5_gt911_release_uncertain", "Tab5 GT911 release could not be scheduled", 409
                ) from error
        return self._wait_acknowledged(initial, self.DRAG_STEPS + 2, check_cancelled, timeout)


class Tab5St7123Touch(Tab5NativeTouch):
    """Submit ST7123 taps, holds and drags with guest readback receipts."""

    CONTROLLER = "st7123"
    PART_NAME = "software-i2c"
    ALLOW_EXPIRED_REPORTS = True
    DRAG_MOVES = 5
    DRAG_MIN_MS = 60 * (DRAG_MOVES + 1)

    def power_state(self) -> dict:
        values = self._part_state()
        try:
            latched, enabled = values["power_latched"], values["chip_enabled"]
            at_ns = int(values["power_latched_ns"])
            if latched in ("true", "false") and enabled in ("true", "false") and at_ns >= 0:
                return {
                    "latched": latched == "true",
                    "chip_enabled": enabled == "true",
                    "latched_at_guest_ns": at_ns if latched == "true" else None,
                }
        except (KeyError, ValueError):
            pass
        raise self._error("unavailable", "power latch state could not be read")

    def hold(self, x: int, y: int, milliseconds: int, check_cancelled, *, timeout: float = 20) -> tuple[dict, dict]:
        initial = self._idle_counters()
        self._queue(f"hold:{x},{y},{milliseconds}")
        reports = self._wait_acknowledged(initial, 2, check_cancelled, timeout)
        state = self._part_state()
        try:
            actual_ms = int(state["hold_ms"])
            refreshed = int(state["refresh_acknowledged"])
        except (KeyError, ValueError) as error:
            raise self._error("unavailable", "hold evidence could not be read") from error
        if actual_ms < milliseconds or refreshed <= 0:
            raise self._error("ack_timeout", "hold duration or refresh was not observed by the guest")
        return reports, {
            "completion": "guest-observed",
            "hold_seconds": milliseconds / 1000,
            "guest_hold_ms": actual_ms,
            "refresh_acknowledged": refreshed,
        }

    def drag(self, x1: int, y1: int, x2: int, y2: int, check_cancelled, *, timeout: float = 12) -> tuple[dict, dict]:
        initial = self._idle_counters()
        self._queue(f"drag:{x1},{y1}:{x2},{y2}")
        expected = self.DRAG_MOVES + 2
        reports = self._wait_acknowledged(initial, expected, check_cancelled, timeout)
        try:
            actual_ms = int(self._part_state()["drag_ms"])
        except (KeyError, ValueError) as error:
            raise self._error("unavailable", "drag evidence could not be read") from error
        if reports["acknowledged"] != expected or actual_ms < self.DRAG_MIN_MS:
            raise self._error("ack_timeout", "complete drag timing was not observed by the guest")
        return reports, {
            "completion": "guest-observed",
            "guest_drag_ms": actual_ms,
            "moves_acknowledged": self.DRAG_MOVES,
        }


class DsiProtocolError(ValueError):
    pass


def _varint(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 64, 7):
        if position >= len(data):
            break
        byte = data[position]
        position += 1
        if shift == 63 and byte > 1:
            break
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, position
    raise DsiProtocolError("invalid co-sim varint")


def _fields(data: bytes) -> dict[int, int | bytes]:
    fields: dict[int, int | bytes] = {}
    position = 0
    while position < len(data):
        key, position = _varint(data, position)
        field, wire = key >> 3, key & 7
        if not field:
            raise DsiProtocolError("invalid co-sim field")
        if wire == 0:
            fields[field], position = _varint(data, position)
            continue
        if wire == 2:
            size, position = _varint(data, position)
        elif wire in {1, 5}:
            size = 8 if wire == 1 else 4
        else:
            raise DsiProtocolError("unsupported co-sim wire type")
        end = position + size
        if end > len(data):
            raise DsiProtocolError("truncated co-sim field")
        fields[field] = data[position:end]
        position = end
    return fields


def _integer(fields: dict[int, int | bytes], number: int) -> int:
    value = fields.get(number, 0)
    if not isinstance(value, int):
        raise DsiProtocolError("invalid co-sim integer")
    return value


def _bytes(fields: dict[int, int | bytes], number: int) -> bytes:
    value = fields.get(number, b"")
    if not isinstance(value, bytes):
        raise DsiProtocolError("invalid co-sim byte field")
    return value


def _read_exact(sock: socket.socket, size: int) -> bytes:
    frame = bytearray()
    while len(frame) < size:
        chunk = sock.recv(size - len(frame))
        if not chunk:
            raise EOFError("co-sim disconnected")
        frame.extend(chunk)
    return bytes(frame)


def _read_message(sock: socket.socket) -> dict[int, int | bytes]:
    (size,) = struct.unpack("<I", _read_exact(sock, 4))
    if not 2 <= size <= MAX_MESSAGE_BYTES:
        raise DsiProtocolError("invalid co-sim packet size")
    data = _read_exact(sock, size)
    (topic_length,) = struct.unpack_from("<H", data)
    if topic_length > size - 2:
        raise DsiProtocolError("invalid co-sim topic size")
    return _fields(data[2 + topic_length:])


@dataclass(frozen=True)
class DsiFrame:
    width: int
    height: int
    pixel_format: int
    pixels: bytes
    number: int
    guest_time_ns: int
    captured_at: float


class DsiFramebuffer:
    """Apply changed rows only to a complete baseline in one chip generation."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.format = None
        self.snapshot: DsiFrame | None = None
        self.pending_number: int | None = None
        self.pending_time = 0
        self.pixels = bytearray()
        self.pending_rows = bytearray()

    def _configure(self, fields: dict[int, int | bytes]) -> None:
        if not _integer(fields, 1):
            self.reset()
            return
        width, height, pixel_format = (_integer(fields, key) for key in (2, 3, 4))
        if (
            not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION
            or width * height > MAX_PIXELS or pixel_format not in PIXEL_BYTES
        ):
            raise DsiProtocolError("unsupported DSI format")
        shape = (width, height, pixel_format)
        if self.format != shape:
            self.reset()
            self.format = shape
            self.pixels = bytearray(width * height * PIXEL_BYTES[pixel_format])
            self.pending_rows = bytearray(height)

    def _publish(self) -> None:
        assert self.format is not None and self.pending_number is not None
        if self.snapshot is None and 0 in self.pending_rows:
            raise DsiProtocolError("incomplete initial DSI frame")
        self.snapshot = DsiFrame(
            *self.format, bytes(self.pixels), self.pending_number, self.pending_time, time.time()
        )
        self.pending_number = None
        self.pending_rows = bytearray(self.format[1])

    def _apply_rows(self, fields: dict[int, int | bytes], timestamp: int) -> None:
        if self.format is None:
            raise DsiProtocolError("DSI rows preceded stream format")
        width, height, pixel_format = self.format
        number, y, count = (_integer(fields, key) for key in (1, 2, 3))
        stride = width * PIXEL_BYTES[pixel_format]
        data = _bytes(fields, 4)
        if not 1 <= count <= height - y or len(data) != count * stride:
            raise DsiProtocolError("invalid DSI row span")
        if self.pending_number is not None and number > self.pending_number:
            self._publish()
        if (self.snapshot and number <= self.snapshot.number) or (
            self.pending_number is not None and number != self.pending_number
        ):
            raise DsiProtocolError("out-of-order DSI frame")
        if any(self.pending_rows[y:y + count]):
            raise DsiProtocolError("overlapping DSI rows")
        self.pending_number = number
        self.pending_time = timestamp
        self.pixels[y * stride:(y + count) * stride] = data
        self.pending_rows[y:y + count] = b"\x01" * count
        if 0 not in self.pending_rows:
            self._publish()

    def receive(self, message: dict[int, int | bytes]) -> None:
        if 9 in message:  # ChipReset establishes a new guest timeline.
            self.reset()
            return
        timestamp = _integer(message, 1)
        if 36 in message:
            event = _fields(_bytes(message, 36))
            if 2 in event:
                self._configure(_fields(_bytes(event, 2)))
            if 3 in event:
                self._apply_rows(_fields(_bytes(event, 3)), timestamp)
        elif 2 in message and self.pending_number is not None and timestamp > self.pending_time:
            # Row pieces from one native frame are sent together. A subsequent
            # clock watermark confirms the last diff even when the screen rests.
            self._publish()


class Tab5DsiReceiver:
    """Own one bounded co-sim stream for one P4 process."""

    def __init__(self, port: int):
        self._port = port
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._buffer = DsiFramebuffer()
        self._state = "connecting"
        self._thread = threading.Thread(target=self._run, name="tab5-dsi-receiver", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        if self._thread.ident is not None:
            self._thread.join(timeout=2)

    def snapshot(self) -> tuple[DsiFrame | None, str]:
        with self._lock:
            return self._buffer.snapshot, self._state

    def _connect(self) -> socket.socket:
        until = time.monotonic() + 8
        while not self._stop.is_set() and time.monotonic() < until:
            try:
                return socket.create_connection(("127.0.0.1", self._port), timeout=0.25)
            except OSError:
                self._stop.wait(0.05)
        raise OSError("co-sim endpoint unavailable")

    def _run(self) -> None:
        try:
            with self._connect() as sock:
                with self._lock:
                    self._sock = sock
                    if self._stop.is_set():
                        return
                sock.sendall(struct.pack("<I", len(REGISTER_VC0)) + REGISTER_VC0)
                sock.settimeout(2)
                ack = _fields(_bytes(_read_message(sock), 5))
                if _integer(ack, 5) != 1:
                    raise DsiProtocolError("DSI registration refused")
                sock.settimeout(None)
                with self._lock:
                    self._state = "connected"
                while not self._stop.is_set():
                    message = _read_message(sock)
                    with self._lock:
                        self._buffer.receive(message)
        except (OSError, EOFError, DsiProtocolError) as error:
            with self._lock:
                self._state = "protocol_error" if isinstance(error, DsiProtocolError) else "disconnected"
                self._buffer.reset()
        finally:
            with self._lock:
                self._sock = None
