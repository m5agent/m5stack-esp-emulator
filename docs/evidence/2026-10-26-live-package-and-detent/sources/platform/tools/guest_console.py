"""Single-owner raw UART transport for a QEMU Unix socket chardev.

QEMU must not also write ``log_path`` via its logfile option. This client is
its only writer; protocol consumers read independent byte windows from disk.
"""
from __future__ import annotations

import errno
import math
import select
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

MAX_RESPONSE_BYTES = 1024 * 1024
POLL_INTERVAL = 0.05
CLOSE_TIMEOUT = 1.0


class GuestConsoleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.sent_bytes = 0


def _timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise GuestConsoleError(
            "invalid_console_argument", "timeout must be a positive finite number"
        )
    return float(value)


def _position(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise GuestConsoleError(
            "invalid_console_argument", f"{name} must be a non-negative integer"
        )
    return value


class GuestConsole:
    def __init__(self, path: Path, log_path: Path):
        self.path = Path(path)
        self.log_path = Path(log_path)
        self._condition = threading.Condition()
        self._connect_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._closed = threading.Event()
        self._socket: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._terminal: GuestConsoleError | None = None
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = self.log_path.open("ab", buffering=0)
            self._offset = self._log.tell()
        except OSError as error:
            raise GuestConsoleError(
                "console_log_error", f"cannot open console log: {error}"
            ) from error

    def _check_cancelled(self, cancelled: Callable[[], bool] | None = None) -> None:
        if cancelled is not None and cancelled():
            raise GuestConsoleError("console_cancelled", "console operation cancelled")
        if self._closed.is_set():
            raise GuestConsoleError("console_closed", "console is closed")

    def _acquire(
        self, lock, deadline: float, code: str,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        while True:
            self._check_cancelled(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GuestConsoleError(code, "console operation timed out")
            if lock.acquire(timeout=min(POLL_INTERVAL, remaining)):
                return

    def connect(
        self, timeout: float = 5,
        cancelled: Callable[[], bool] | None = None,
    ) -> GuestConsole:
        deadline = time.monotonic() + _timeout(timeout)
        self._acquire(self._connect_lock, deadline, "console_connect_timeout", cancelled)
        try:
            self._check_cancelled(cancelled)
            with self._condition:
                if self._terminal is not None:
                    raise self._terminal
                if self._socket is not None:
                    return self
            while True:
                self._check_cancelled(cancelled)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise GuestConsoleError(
                        "console_connect_timeout", "console socket did not become available"
                    )
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    sock.settimeout(min(POLL_INTERVAL, remaining))
                    sock.connect(str(self.path))
                    sock.setblocking(False)
                    self._check_cancelled(cancelled)
                    with self._condition:
                        self._check_cancelled()
                        self._socket = sock
                        self._reader = threading.Thread(
                            target=self._read_loop, args=(sock,),
                            name="guest-console-reader", daemon=True,
                        )
                        try:
                            self._reader.start()
                        except BaseException:
                            self._socket = None
                            self._reader = None
                            raise
                    return self
                except OSError as error:
                    if error.errno not in {
                        errno.ENOENT, errno.ECONNREFUSED, errno.EAGAIN,
                        errno.EINPROGRESS, errno.ETIMEDOUT,
                    } and not isinstance(error, (socket.timeout, TimeoutError)):
                        raise GuestConsoleError(
                            "console_connect_error", f"cannot connect console socket: {error}"
                        ) from error
                finally:
                    with self._condition:
                        if self._socket is not sock:
                            sock.close()
                self._closed.wait(min(POLL_INTERVAL, max(0, deadline - time.monotonic())))
        finally:
            self._connect_lock.release()

    def _read_loop(self, sock: socket.socket) -> None:
        terminal = None
        try:
            while not self._closed.is_set():
                readable, _, _ = select.select([sock], [], [], POLL_INTERVAL)
                if not readable:
                    continue
                try:
                    data = sock.recv(65536)
                except BlockingIOError:
                    continue
                if not data:
                    terminal = GuestConsoleError("console_eof", "guest console reached EOF")
                    break
                try:
                    view = memoryview(data)
                    while view:
                        written = self._log.write(view)
                        if not written:
                            raise OSError("console log write made no progress")
                        with self._condition:
                            self._offset += written
                            self._condition.notify_all()
                        view = view[written:]
                except (OSError, ValueError) as error:
                    terminal = GuestConsoleError(
                        "console_log_error", f"cannot append console log: {error}"
                    )
                    break
        except (OSError, ValueError) as error:
            terminal = GuestConsoleError(
                "console_read_error", f"cannot read console socket: {error}"
            )
        finally:
            with self._condition:
                if terminal is not None and not self._closed.is_set():
                    self._terminal = terminal
                self._condition.notify_all()

    def write(self, data: bytes, timeout: float = 5) -> int:
        if not isinstance(data, bytes):
            raise GuestConsoleError("invalid_console_argument", "console input must be bytes")
        deadline = time.monotonic() + _timeout(timeout)
        sent = 0
        acquired = False
        try:
            self._acquire(self._write_lock, deadline, "console_write_timeout")
            acquired = True
            while sent < len(data):
                self._check_cancelled()
                with self._condition:
                    self._check_cancelled()
                    if self._terminal is not None:
                        raise self._terminal
                    sock = self._socket
                if sock is None:
                    raise GuestConsoleError("console_not_connected", "console is not connected")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise GuestConsoleError("console_write_timeout", "console write timed out")
                _, writable, _ = select.select([], [sock], [], min(POLL_INTERVAL, remaining))
                if not writable:
                    continue
                try:
                    count = sock.send(memoryview(data)[sent:])
                except BlockingIOError:
                    continue
                if count == 0:
                    raise GuestConsoleError("console_eof", "console write reached EOF")
                sent += count
            self._check_cancelled()
            return sent
        except GuestConsoleError as error:
            # A partial write is never retried as a whole transaction.
            failure = GuestConsoleError(error.code, f"{error.message} (sent_bytes={sent})")
            failure.sent_bytes = sent
            raise failure from error
        except (OSError, ValueError) as error:
            failure = GuestConsoleError(
                "console_closed" if self._closed.is_set() else "console_write_error",
                f"cannot write console socket: {error} (sent_bytes={sent})",
            )
            failure.sent_bytes = sent
            raise failure from error
        finally:
            if acquired:
                self._write_lock.release()

    def offset(self) -> int:
        with self._condition:
            return self._offset

    def check_alive(self) -> None:
        """Report current transport health without waiting for socket data."""
        with self._condition:
            self._check_cancelled()
            if self._terminal is not None:
                raise self._terminal
            if self._socket is None:
                raise GuestConsoleError("console_not_connected", "console is not connected")

    def read_from(self, offset: int, limit: int) -> bytes:
        offset = _position(offset, "offset")
        limit = _position(limit, "limit")
        if limit > MAX_RESPONSE_BYTES:
            raise GuestConsoleError(
                "console_response_too_large", "console read exceeds 1 MiB"
            )
        with self._condition:
            length = min(limit, max(0, self._offset - offset))
        if not length:
            return b""
        try:
            with self.log_path.open("rb") as stream:
                stream.seek(offset)
                return stream.read(length)
        except OSError as error:
            raise GuestConsoleError(
                "console_log_error", f"cannot read console log: {error}"
            ) from error

    def read_exact(
        self, offset: int, size: int, timeout: float,
        cancelled: Callable[[], bool] | None = None,
    ) -> bytes:
        """Wait for an independent exact byte window, or report reader failure.

        ``read_from`` also serves retained history after close, so it cannot
        report a terminal live reader by itself. Protocol reads use this
        method to avoid turning EOF or a log sink failure into a timeout.
        """
        offset = _position(offset, "offset")
        size = _position(size, "size")
        if size > MAX_RESPONSE_BYTES:
            raise GuestConsoleError(
                "console_response_too_large", "console read exceeds 1 MiB"
            )
        deadline = time.monotonic() + _timeout(timeout)
        with self._condition:
            if offset > self._offset:
                raise GuestConsoleError(
                    "invalid_console_argument", "offset is past the console log"
                )
        while True:
            self._check_cancelled(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GuestConsoleError("console_timeout", "console byte wait timed out")
            with self._condition:
                if self._offset - offset >= size:
                    break
                if self._terminal is not None:
                    raise self._terminal
                self._condition.wait(min(POLL_INTERVAL, remaining))
        data = self.read_from(offset, size)
        self._check_cancelled(cancelled)
        if len(data) != size:
            raise GuestConsoleError(
                "console_log_error", "console log lost committed bytes"
            )
        return data

    def wait_for(
        self, marker: bytes, offset: int, timeout: float,
        cancelled: Callable[[], bool] | None = None,
    ) -> tuple[bytes, int]:
        if not isinstance(marker, bytes) or not marker or len(marker) > MAX_RESPONSE_BYTES:
            raise GuestConsoleError(
                "invalid_console_argument", "marker must be 1 to 1 MiB of bytes"
            )
        cursor = _position(offset, "offset")
        deadline = time.monotonic() + _timeout(timeout)
        response = bytearray()
        with self._condition:
            if cursor > self._offset:
                raise GuestConsoleError(
                    "invalid_console_argument", "offset is past the console log"
                )
        while True:
            # Callbacks and disk I/O must not block close from taking this lock.
            self._check_cancelled(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GuestConsoleError("console_timeout", "console marker wait timed out")
            with self._condition:
                available = self._offset - cursor
                if len(response) + available > MAX_RESPONSE_BYTES:
                    raise GuestConsoleError(
                        "console_response_too_large", "console wait response exceeds 1 MiB"
                    )
                if not available:
                    if self._terminal is not None:
                        raise self._terminal
                    self._condition.wait(min(POLL_INTERVAL, remaining))
                    continue
            chunk = self.read_from(cursor, available)
            self._check_cancelled(cancelled)
            if len(chunk) != available:
                raise GuestConsoleError(
                    "console_log_error", "console log lost committed bytes"
                )
            search_from = max(0, len(response) - len(marker) + 1)
            response.extend(chunk)
            cursor += len(chunk)
            if response.find(marker, search_from) >= 0:
                return bytes(response), cursor

    def close(self) -> None:
        self._closed.set()
        with self._condition:
            sock, self._socket = self._socket, None
            reader = self._reader
            self._condition.notify_all()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=CLOSE_TIMEOUT)
            if reader.is_alive():
                raise GuestConsoleError(
                    "console_close_timeout", "console reader did not stop within one second"
                )
        self._log.close()
