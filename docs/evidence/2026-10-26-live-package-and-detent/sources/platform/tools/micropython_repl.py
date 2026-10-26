"""Finite raw-REPL RPC over an already-owned guest UART.

Based on MicroPython tools/pyboard.py's raw-paste credit and double-EOF
protocol. This never opens another console or requests a soft reset. A caller
must hold the session's program owner for the entire exchange.
"""
from __future__ import annotations

import time

from guest_console import GuestConsoleError
from uiflow_runtime import UIFlowRuntimeError


class RawREPL:
    def __init__(self, console, *, timeout: float, cancelled=lambda: False):
        self.console = console
        self.deadline = time.monotonic() + timeout
        self.cancelled = cancelled
        self.cursor = None

    def remaining(self):
        if self.cancelled():
            raise UIFlowRuntimeError("program_cancelled", "session is stopping")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise UIFlowRuntimeError("program_timeout", "guest command timed out")
        return remaining

    def _wait(self, marker):
        start = self.cursor
        try:
            data, _ = self.console.wait_for(marker, start, self.remaining(), self.cancelled)
        except GuestConsoleError as error:
            if error.code == "console_timeout":
                raise UIFlowRuntimeError("program_timeout", "guest command timed out") from error
            raise
        # wait_for may return bytes beyond its marker; consume the exact prefix
        # so coalesced stdout/EOF/stderr/EOF/prompt remain independently parsed.
        index = data.find(marker)
        if index < 0:
            raise UIFlowRuntimeError("program_protocol_error", "guest marker was not received")
        self.cursor = start + index + len(marker)
        return data[:index]

    def _read(self, size):
        try:
            data = self.console.read_exact(self.cursor, size, self.remaining(), self.cancelled)
        except GuestConsoleError as error:
            if error.code == "console_timeout":
                raise UIFlowRuntimeError("program_timeout", "guest command timed out") from error
            raise
        self.cursor += size
        return data

    def _write(self, data):
        self.console.write(data, timeout=self.remaining())

    def synchronize(self, on_synchronized=None):
        self.cursor = self.console.offset()
        self._write(b"\r\x03")
        until = time.monotonic() + 0.1
        while time.monotonic() < until:
            self.remaining()
            time.sleep(0.01)
        self._write(b"\r\x01")
        self._wait(b"raw REPL; CTRL-B to exit\r\n>")
        if on_synchronized is not None:
            on_synchronized()

    def execute(self, source: str, *, max_output: int = 65536):
        try:
            return self._execute(source, max_output=max_output)
        except BaseException:
            # A caller must synchronize again after an incomplete exchange.
            self.cursor = None
            raise

    def _execute(self, source: str, *, max_output: int):
        if self.cursor is None:
            raise UIFlowRuntimeError("program_protocol_error", "raw REPL is not synchronized")
        if not isinstance(source, str) or not source.strip():
            # Ctrl-D at an empty prompt is a soft reset, never a finite RPC.
            raise ValueError("raw REPL command must contain source")
        data = source.encode("utf-8")
        self._write(b"\x05A\x01")
        response = self._read(2)
        if response == b"R\x01":
            window = int.from_bytes(self._read(2), "little")
            if window <= 0:
                raise UIFlowRuntimeError("program_protocol_error", "invalid raw-paste window")
            credit, sent = window, 0
            while sent < len(data):
                while credit == 0 or self.console.offset() > self.cursor:
                    control = self._read(1)
                    if control == b"\x01":
                        credit += window
                    elif control == b"\x04":
                        self._write(b"\x04")
                        raise UIFlowRuntimeError("program_protocol_error", "guest ended source transfer early")
                    else:
                        raise UIFlowRuntimeError("program_protocol_error", "invalid raw-paste credit")
                count = min(credit, 128, len(data) - sent)
                self._write(data[sent:sent + count])
                sent += count
                credit -= count
            self._write(b"\x04")
            control = self._read(1)
            while control == b"\x01":
                control = self._read(1)
            if control != b"\x04":
                raise UIFlowRuntimeError("program_protocol_error", "guest did not acknowledge source EOF")
            transfer = "raw-paste"
        elif response == b"R\x00":
            for start in range(0, len(data), 128):
                self._write(data[start:start + 128])
                time.sleep(min(0.01, self.remaining()))
            self._write(b"\x04")
            if self._read(2) != b"OK":
                raise UIFlowRuntimeError("program_protocol_error", "guest did not acknowledge source")
            transfer = "raw-repl-paced"
        else:
            raise UIFlowRuntimeError("program_protocol_error", "guest rejected raw-paste negotiation")
        stdout = self._wait(b"\x04")
        stderr = self._wait(b"\x04")
        if self._read(1) != b">":
            raise UIFlowRuntimeError("program_protocol_error", "guest did not return to raw REPL")
        if len(stdout) + len(stderr) > max_output:
            raise UIFlowRuntimeError("program_rpc_output_too_large", "guest command output exceeded its bound")
        if stderr:
            raise UIFlowRuntimeError("program_rpc_failed", "guest command failed; see the retained serial log")
        return {"stdout": stdout, "transfer_mode": transfer, "next_offset": self.cursor}
