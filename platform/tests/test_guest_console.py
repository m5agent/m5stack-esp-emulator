"""Real temporary Unix socket transport tests; no guest or Device Service."""
from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from guest_console import GuestConsole, GuestConsoleError, MAX_RESPONSE_BYTES


class GuestConsoleTests(unittest.TestCase):
    def setUp(self):
        # Keep AF_UNIX paths below macOS's sockaddr_un length limit.
        self.temp = tempfile.TemporaryDirectory(prefix="m5-console-", dir="/tmp")
        self.directory = Path(self.temp.name)
        self.path = self.directory / "uart.sock"
        self.log = self.directory / "serial.log"
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.settimeout(2)
        self.consoles = []
        self.peers = []
        self.threads = []

    def tearDown(self):
        for console in self.consoles:
            console.close()
        for peer in self.peers:
            peer.close()
        self.listener.close()
        for thread in self.threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive(), "fixture thread leaked")
        self.temp.cleanup()

    def console(self):
        console = GuestConsole(self.path, self.log)
        self.consoles.append(console)
        return console

    def listen(self):
        self.listener.bind(str(self.path))
        self.listener.listen(4)

    def accept(self):
        peer, _ = self.listener.accept()
        peer.settimeout(2)
        self.peers.append(peer)
        return peer

    def connected(self):
        self.listen()
        console = self.console().connect(timeout=1)
        return console, self.accept()

    def background(self, function):
        result = {}

        def run():
            try:
                result["value"] = function()
            except BaseException as error:
                result["error"] = error

        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        return thread, result

    def assert_code(self, code, function):
        with self.assertRaises(GuestConsoleError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_binary_log_appends_and_byte_windows_survive_close(self):
        history = b"old\xff\x00READY\r\n"
        self.log.write_bytes(history)
        console, peer = self.connected()
        self.assertEqual(console.offset(), len(history))
        start = console.offset()
        payload = "中文".encode() + b"\x00\xfeNEW-READY"
        peer.sendall(payload)
        observed, next_offset = console.wait_for(b"NEW-READY", start, timeout=1)
        self.assertEqual(observed, payload)
        self.assertEqual(next_offset, start + len(payload))
        self.assertEqual(console.read_from(start + 1, 4), payload[1:5])
        console.close()
        console.close()
        self.assertFalse(console._reader.is_alive())
        self.assertEqual(console.read_from(start, len(payload)), payload)
        self.assertEqual(self.log.read_bytes(), history + payload)
        self.assertTrue(self.path.exists(), "closing client must not remove server socket")

    def test_marker_crosses_receives_and_returns_received_trailing_bytes(self):
        console, peer = self.connected()
        entered = threading.Event()
        thread, result = self.background(lambda: console.wait_for(
            b"READY", 0, timeout=1, cancelled=lambda: entered.set() or False,
        ))
        self.assertTrue(entered.wait(1))
        peer.sendall(b"\xffRE")
        console.wait_for(b"RE", 0, timeout=1)
        peer.sendall(b"ADY\x00tail")
        console.wait_for(b"tail", 0, timeout=1)
        thread.join(timeout=1)
        self.assertNotIn("error", result)
        received, offset = result["value"]
        self.assertIn(b"READY", received)
        self.assertEqual(console.read_from(0, offset), received)
        all_received, end = console.wait_for(b"READY", 0, timeout=1)
        self.assertEqual(all_received, b"\xffREADY\x00tail")
        self.assertEqual(end, len(all_received))

    def test_old_marker_cannot_satisfy_new_window(self):
        console, peer = self.connected()
        peer.sendall(b"READY-old")
        _, start = console.wait_for(b"READY-old", 0, timeout=1)
        peer.sendall(b"new-data")
        console.wait_for(b"new-data", start, timeout=1)
        self.assert_code("console_timeout", lambda: console.wait_for(b"READY", start, timeout=0.06))
        peer.sendall(b"READY-new")
        observed, end = console.wait_for(b"READY-new", start, timeout=1)
        self.assertEqual(observed, b"new-dataREADY-new")
        self.assertEqual(end, start + len(observed))

    def test_independent_waiters_do_not_consume_each_others_bytes(self):
        console, peer = self.connected()
        started = [threading.Event(), threading.Event()]
        tasks = [self.background(lambda i=i: console.wait_for(
            b"END", 0, timeout=1, cancelled=lambda: started[i].set() or False,
        )) for i in range(2)]
        self.assertTrue(all(event.wait(1) for event in started))
        peer.sendall(b"shared-END")
        for thread, result in tasks:
            thread.join(timeout=1)
            self.assertNotIn("error", result)
            self.assertEqual(result["value"], (b"shared-END", 10))

    def test_eof_preserves_tail_and_has_distinct_wait_error(self):
        console, peer = self.connected()
        peer.sendall(b"tail-END")
        peer.shutdown(socket.SHUT_WR)
        received, end = console.wait_for(b"END", 0, timeout=1)
        self.assertEqual(received, b"tail-END")
        self.assert_code("console_eof", lambda: console.wait_for(b"missing", end, timeout=1))
        self.assertEqual(console.read_from(0, end), received)
        self.assert_code("console_eof", lambda: console.write(b"cannot-reopen"))
        self.assert_code("console_eof", lambda: console.connect(timeout=1))

    def test_check_alive_reports_connection_eof_and_close_without_waiting(self):
        self.listen()
        console = self.console()
        self.assert_code("console_not_connected", console.check_alive)
        console.connect(timeout=1)
        peer = self.accept()
        self.assertIsNone(console.check_alive())
        peer.sendall(b"saved-tail")
        peer.shutdown(socket.SHUT_WR)
        self.assert_code("console_eof", lambda: console.read_exact(0, 11, timeout=1))
        self.assert_code("console_eof", console.check_alive)
        self.assertEqual(console.read_from(0, 10), b"saved-tail")
        console.close()
        self.assert_code("console_closed", console.check_alive)

    def test_exact_read_waits_for_fragmented_window_and_preserves_trailing_data(self):
        console, peer = self.connected()
        entered = threading.Event()
        thread, result = self.background(lambda: console.read_exact(
            0, 4, timeout=1, cancelled=lambda: entered.set() or False,
        ))
        self.assertTrue(entered.wait(1))
        peer.sendall(b"ab")
        console.wait_for(b"ab", 0, timeout=1)
        self.assertTrue(thread.is_alive())
        peer.sendall(b"cd-tail")
        thread.join(timeout=1)
        self.assertNotIn("error", result)
        self.assertEqual(result["value"], b"abcd")
        self.assertEqual(console.read_exact(0, 4, timeout=1), b"abcd")
        self.assertEqual(console.wait_for(b"tail", 4, timeout=1)[0], b"-tail")

    def test_exact_read_reports_eof_immediately_after_partial_window(self):
        console, peer = self.connected()
        peer.sendall(b"R")
        peer.shutdown(socket.SHUT_WR)
        before = time.monotonic()
        self.assert_code("console_eof", lambda: console.read_exact(0, 2, timeout=5))
        self.assertLess(time.monotonic() - before, 0.5)
        self.assertEqual(console.read_exact(0, 1, timeout=1), b"R")

    def test_exact_read_reports_log_sink_error_without_waiting_for_timeout(self):
        console, peer = self.connected()
        console._log.close()
        peer.sendall(b"R")
        before = time.monotonic()
        self.assert_code("console_log_error", lambda: console.read_exact(0, 2, timeout=5))
        self.assertLess(time.monotonic() - before, 0.5)

    def test_exact_read_reports_socket_reader_error_without_waiting_for_timeout(self):
        console, _ = self.connected()
        with mock.patch("guest_console.select.select", side_effect=OSError("reader unavailable")):
            before = time.monotonic()
            self.assert_code("console_read_error", lambda: console.read_exact(0, 2, timeout=5))
        self.assertLess(time.monotonic() - before, 0.5)
        self.assert_code("console_read_error", console.check_alive)

    def test_exact_read_cancellation_and_close_wake_without_socket_data(self):
        console, _ = self.connected()
        cancelled, entered = threading.Event(), threading.Event()
        thread, result = self.background(lambda: console.read_exact(
            0, 2, timeout=5, cancelled=lambda: entered.set() or cancelled.is_set(),
        ))
        self.assertTrue(entered.wait(1))
        cancelled.set()
        thread.join(timeout=1)
        self.assertEqual(result["error"].code, "console_cancelled")
        entered.clear()
        thread, result = self.background(lambda: console.read_exact(
            0, 2, timeout=5, cancelled=lambda: entered.set() or False,
        ))
        self.assertTrue(entered.wait(1))
        console.close()
        thread.join(timeout=1)
        self.assertEqual(result["error"].code, "console_closed")

    def test_wait_cancel_and_close_wake_without_socket_data(self):
        console, _ = self.connected()
        cancelled, entered = threading.Event(), threading.Event()
        thread, result = self.background(lambda: console.wait_for(
            b"missing", 0, timeout=5,
            cancelled=lambda: entered.set() or cancelled.is_set(),
        ))
        self.assertTrue(entered.wait(1))
        cancelled.set()
        thread.join(timeout=1)
        self.assertEqual(result["error"].code, "console_cancelled")
        entered.clear()
        thread, result = self.background(lambda: console.wait_for(
            b"missing", 0, timeout=5, cancelled=lambda: entered.set() or False,
        ))
        self.assertTrue(entered.wait(1))
        before = time.monotonic()
        console.close()
        thread.join(timeout=1)
        self.assertLess(time.monotonic() - before, 1)
        self.assertEqual(result["error"].code, "console_closed")
        self.assertFalse(console._reader.is_alive())

    def test_cancellation_callback_can_close_console(self):
        console, _ = self.connected()
        self.assert_code("console_cancelled", lambda: console.wait_for(
            b"missing", 0, timeout=1, cancelled=lambda: console.close() or True,
        ))
        self.assertFalse(console._reader.is_alive())

    def test_connect_retries_until_socket_exists_and_is_idempotent(self):
        console = self.console()
        entered = threading.Event()
        thread, result = self.background(lambda: console.connect(
            timeout=1, cancelled=lambda: entered.set() or False,
        ))
        self.assertTrue(entered.wait(1))
        self.listen()
        peer = self.accept()
        thread.join(timeout=1)
        self.assertNotIn("error", result)
        reader = console._reader
        self.assertIs(console.connect(timeout=1), console)
        self.assertIs(console._reader, reader)
        peer.sendall(b"CONNECTED")
        self.assertEqual(console.wait_for(b"CONNECTED", 0, timeout=1)[0], b"CONNECTED")

    def test_concurrent_connects_publish_one_reader_and_connection(self):
        self.listen()
        console = self.console()
        gate = threading.Barrier(3)
        tasks = [self.background(lambda: (gate.wait(timeout=1), console.connect(timeout=1))[1]) for _ in range(2)]
        gate.wait(timeout=1)
        self.accept()
        for thread, result in tasks:
            thread.join(timeout=1)
            self.assertNotIn("error", result)
            self.assertIs(result["value"], console)
        self.listener.settimeout(0.06)
        with self.assertRaises((socket.timeout, TimeoutError)):
            self.listener.accept()
        self.assertTrue(console._reader.is_alive())

    def test_connect_timeout_cancel_and_close_are_distinct_and_bounded(self):
        console = self.console()
        before = time.monotonic()
        self.assert_code("console_connect_timeout", lambda: console.connect(timeout=0.06))
        self.assertLess(time.monotonic() - before, 1)
        self.assert_code("console_cancelled", lambda: console.connect(timeout=1, cancelled=lambda: True))
        entered = threading.Event()
        thread, result = self.background(lambda: console.connect(
            timeout=5, cancelled=lambda: entered.set() or False,
        ))
        self.assertTrue(entered.wait(1))
        console.close()
        thread.join(timeout=1)
        self.assertEqual(result["error"].code, "console_closed")
        self.assertIsNone(console._socket)
        self.assertIsNone(console._reader)
        self.assert_code("console_closed", lambda: console.connect(timeout=1))

    def test_concurrent_large_writes_are_whole_transactions(self):
        console, peer = self.connected()
        console._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        size = 128 * 1024
        expected = size * 2

        def receive():
            chunks = bytearray()
            while len(chunks) < expected:
                chunk = peer.recv(min(4096, expected - len(chunks)))
                if not chunk:
                    raise RuntimeError("fixture peer closed before the full transaction")
                chunks.extend(chunk)
            return bytes(chunks)

        reader, captured = self.background(receive)
        gate = threading.Barrier(3)
        tasks = [self.background(lambda value=value: (gate.wait(timeout=1), console.write(value * size, timeout=2))[1]) for value in (b"A", b"B")]
        gate.wait(timeout=1)
        for thread, result in tasks:
            thread.join(timeout=3)
            self.assertNotIn("error", result)
            self.assertEqual(result["value"], size)
        reader.join(timeout=3)
        self.assertNotIn("error", captured)
        self.assertIn(captured["value"], (b"A" * size + b"B" * size, b"B" * size + b"A" * size))

    def test_write_timeout_reports_partial_count_and_does_not_retry(self):
        console, peer = self.connected()
        console._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        error = self.assert_code("console_write_timeout", lambda: console.write(b"X" * (8 * MAX_RESPONSE_BYTES), timeout=0.06))
        self.assertGreater(error.sent_bytes, 0)
        self.assertLess(error.sent_bytes, 8 * MAX_RESPONSE_BYTES)
        peer.setblocking(False)
        received = bytearray()
        while True:
            try:
                received.extend(peer.recv(65536))
            except BlockingIOError:
                break
        self.assertEqual(len(received), error.sent_bytes)
        self.assertEqual(received, b"X" * error.sent_bytes)

    def test_write_lock_deadline_and_close_interrupt_blocked_writer(self):
        console, peer = self.connected()
        console._socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        thread, result = self.background(lambda: console.write(b"A" * (8 * MAX_RESPONSE_BYTES), timeout=5))
        self.assertTrue(peer.recv(1), "first write must enter the real socket before contention")
        error = self.assert_code("console_write_timeout", lambda: console.write(b"B", timeout=0.06))
        self.assertEqual(error.sent_bytes, 0)
        console.close()
        thread.join(timeout=1)
        self.assertEqual(result["error"].code, "console_closed")
        self.assertGreater(result["error"].sent_bytes, 0)

    def test_wait_response_limit_is_exact_and_never_silently_truncated(self):
        console, peer = self.connected()
        payload = b"x" * (MAX_RESPONSE_BYTES - 4) + b"END!"
        peer.sendall(payload)
        observed, end = console.wait_for(b"END!", 0, timeout=2)
        self.assertEqual(observed, payload)
        self.assertEqual(end, MAX_RESPONSE_BYTES)
        peer.sendall(b"y")
        console.wait_for(b"y", end, timeout=1)
        self.assert_code("console_response_too_large", lambda: console.wait_for(b"END!", 0, timeout=1))
        self.assertEqual(console.offset(), MAX_RESPONSE_BYTES + 1)
        self.assertEqual(console.read_from(end, 1), b"y")

    def test_log_failure_wakes_waiters_as_log_error(self):
        console, peer = self.connected()
        console._log.close()  # Deterministic disk sink failure, not fake UART data.
        peer.sendall(b"cannot-save")
        self.assert_code("console_log_error", lambda: console.wait_for(b"missing", 0, timeout=1))
        self.assert_code("console_log_error", lambda: console.write(b"cannot-continue"))
        self.assert_code("console_log_error", console.check_alive)

    def test_stalled_log_writer_does_not_block_close_lock_or_lose_sink(self):
        console, peer = self.connected()
        original = console._log
        entered, release = threading.Event(), threading.Event()

        class StalledSink:
            def write(self, data):
                entered.set()
                if not release.wait(timeout=3):
                    raise OSError("fixture sink was not released")
                return original.write(data)

            def close(self):
                original.close()

        console._log = StalledSink()
        try:
            peer.sendall(b"persist-before-exit")
            self.assertTrue(entered.wait(1))
            before = time.monotonic()
            self.assert_code("console_close_timeout", console.close)
            self.assertLess(time.monotonic() - before, 1.5)
            self.assertFalse(original.closed, "live reader retains ownership of its log sink")
        finally:
            release.set()
            console.close()
        self.assertFalse(console._reader.is_alive())
        self.assertEqual(self.log.read_bytes(), b"persist-before-exit")

    def test_stalled_log_reader_does_not_block_close_or_publish_late_success(self):
        console, peer = self.connected()
        peer.sendall(b"END")
        console.wait_for(b"END", 0, timeout=1)
        read = console.read_from
        entered, release = threading.Event(), threading.Event()

        def stalled_read(offset, limit):
            entered.set()
            if not release.wait(timeout=2):
                raise RuntimeError("fixture read was not released")
            return read(offset, limit)

        console.read_from = stalled_read
        thread, result = self.background(lambda: console.wait_for(b"END", 0, timeout=3))
        try:
            self.assertTrue(entered.wait(1))
            before = time.monotonic()
            console.close()
            self.assertLess(time.monotonic() - before, 1)
        finally:
            release.set()
        thread.join(timeout=1)
        self.assertEqual(result["error"].code, "console_closed")

    def test_arguments_are_validated_and_future_reads_are_empty(self):
        console = self.console()
        for timeout in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                self.assert_code("invalid_console_argument", lambda: console.connect(timeout=timeout))
        for marker, offset in ((b"", 0), ("text", 0), (b"x", -1), (b"x", True), (b"x", 1)):
            with self.subTest(marker=marker, offset=offset):
                self.assert_code("invalid_console_argument", lambda: console.wait_for(marker, offset, timeout=1))
        self.assert_code("invalid_console_argument", lambda: console.write("text"))
        self.assert_code("console_not_connected", lambda: console.write(b"x"))
        self.assert_code("invalid_console_argument", lambda: console.read_from(0, -1))
        self.assert_code("console_response_too_large", lambda: console.read_from(0, MAX_RESPONSE_BYTES + 1))
        self.assert_code("invalid_console_argument", lambda: console.read_exact(1, 1, timeout=1))
        self.assert_code("console_response_too_large", lambda: console.read_exact(0, MAX_RESPONSE_BYTES + 1, timeout=1))
        self.assertEqual(console.read_from(10**100, 1), b"")
        self.assertEqual(console.read_from(0, 0), b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
