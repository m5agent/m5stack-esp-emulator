"""Receive the native esp-emu Tab5 DSI stream without guest symbols."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import socket
import struct
import threading
import time

from device_service_errors import ServiceError


TAB5_DSI_RUNTIME_SHA256 = "633a35f993300a765634ed78a2dbcfd5ffcd5c3f2f354a2dddabeb6108240828"
TAB5_GT911_PART_SHA256 = "a0852d08d6cc04a11dcdd57c417b497f857be3e6265f8b690968ae3338cd3ce9"
TAB5_GT911_SOURCE = Path(__file__).resolve().parents[1] / "esp-parts" / "tab5-gt911"
TAB5_GT911_SIZE = (720, 1280)
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
    """Select the stock board's idle touch-identification register device."""
    if not board:
        return ()
    if board == "gt911-ili9881c":
        # GT911 backup address on Tab5 HP I2C controller 1. The product ID
        # begins with ASCII "911" at 0x8140; zero touch status means idle.
        return ("1:0x14,width=2,fill=0,reg=0x8140=0x39,reg=0x8141=0x31,reg=0x8142=0x31",)
    raise ServiceError("tab5_dsi_board_unavailable", "unknown native DSI Tab5 board revision", 409)


def stage_tab5_gt911_part(value: str, board: str, session_dir: Path) -> Path:
    """Bind the source board and exact ESP Part bytes to this guest."""
    if board != "gt911-ili9881c":
        raise ServiceError(
            "tab5_gt911_part_unavailable", "Tab5 GT911 requires the gt911-ili9881c board revision", 409
        )
    try:
        with Path(value).open("rb") as module:
            part = module.read(128 * 1024 + 1)
        if hashlib.sha256(part).hexdigest() != TAB5_GT911_PART_SHA256:
            raise ValueError("unexpected ESP Part hash")
        config = (TAB5_GT911_SOURCE / "board.json").read_bytes()
        (session_dir / "m5_tab5_gt911.wasm").write_bytes(part)
        path = session_dir / "tab5-cosim-board.json"
        path.write_bytes(config)
        return path
    except (OSError, ValueError) as error:
        raise ServiceError(
            "tab5_gt911_part_unavailable", "configured Tab5 GT911 ESP Part could not be verified", 409
        ) from error


class Tab5Gt911Touch:
    """Submit one tap through the native controller and observe guest ACKs."""

    def __init__(self, port: int):
        self.port = port

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
        raise ServiceError("tab5_gt911_unavailable", "Tab5 GT911 control endpoint is unavailable", 409)

    def _state(self) -> tuple[int, int, int, bool]:
        response = self._command("part gt911 state")
        try:
            if response.startswith("ok "):
                values = dict(item.split("=", 1) for item in response[3:].split())
                if values["ready"] in {"true", "false"} and values["contact"] in {"true", "false"}:
                    reports = int(values["reports"])
                    acknowledged = int(values["acknowledged"])
                    rejected = int(values["rejected_inputs"])
                    if 0 <= acknowledged <= reports and rejected >= 0:
                        idle = values["ready"] == values["contact"] == "false"
                        return reports, acknowledged, rejected, idle
        except (KeyError, ValueError):
            pass
        raise ServiceError("tab5_gt911_unavailable", "Tab5 GT911 state could not be read", 409)

    def tap(self, x: int, y: int, check_cancelled, *, timeout: float = 12) -> dict:
        reports, acknowledged, rejected, idle = self._state()
        if not idle or reports != acknowledged:
            raise ServiceError("tab5_gt911_busy", "Tab5 GT911 has a pending report", 409)
        if self._command(f"part gt911 input tap:{x},{y}") != "ok":
            raise ServiceError("tab5_gt911_unavailable", "Tab5 GT911 could not queue the tap", 409)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_cancelled()
            current_reports, current_acknowledged, current_rejected, idle = self._state()
            if current_rejected != rejected:
                raise ServiceError("tab5_gt911_busy", "Tab5 GT911 rejected the tap", 409)
            if idle and current_reports == current_acknowledged and current_acknowledged - acknowledged >= 2:
                return {
                    "reports": current_reports - reports,
                    "acknowledged": current_acknowledged - acknowledged,
                }
            time.sleep(0.05)
        raise ServiceError(
            "tab5_gt911_ack_timeout", "Tab5 guest did not acknowledge both GT911 tap reports", 409
        )


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
