"""Wire-protocol tests only: no firmware, guest filesystem or QEMU execution."""
from __future__ import annotations

import unittest
from unittest import mock

from guest_console import GuestConsoleError
from micropython_repl import RawREPL
from uiflow_runtime import UIFlowRuntimeError


class Wire:
    def __init__(self, *, paste=True, window=8, stdout=b"answer\r\n", stderr=b""):
        self.log = bytearray()
        self.writes = []
        self.sources = []
        self.paste, self.window = paste, window
        self.stdout, self.stderr = stdout, stderr
        self.transfer = False
        self.credit = window
        self.pending = bytearray()
        self.tail = b">"
        self.closed = False

    def offset(self):
        return len(self.log)

    def write(self, data, *, timeout):
        self.writes.append(data)
        if data == b"\r\x01":
            self.log.extend(b"noise\r\nraw REPL; CTRL-B to exit\r\n>")
        elif data == b"\x05A\x01":
            self.transfer = True
            self.pending.clear()
            self.credit = self.window
            self.log.extend(b"R\x01" + self.window.to_bytes(2, "little") if self.paste else b"R\x00")
        elif self.transfer and data == b"\x04":
            self.transfer = False
            self.sources.append(bytes(self.pending))
            self.log.extend((b"\x04" if self.paste else b"OK") + self.stdout + b"\x04" + self.stderr + b"\x04" + self.tail)
        elif self.transfer:
            self.pending.extend(data)
            if self.paste:
                self.credit -= len(data)
                if self.credit == 0:
                    self.log.extend(b"\x01")
                    self.credit = self.window

    def read_exact(self, offset, size, timeout, cancelled):
        if self.closed:
            raise GuestConsoleError("console_closed", "closed")
        if offset + size > len(self.log):
            raise GuestConsoleError("console_timeout", "missing bytes")
        return bytes(self.log[offset:offset + size])

    def wait_for(self, marker, offset, timeout, cancelled):
        if self.closed:
            raise GuestConsoleError("console_closed", "closed")
        data = bytes(self.log[offset:])
        if marker not in data:
            raise GuestConsoleError("console_timeout", "missing marker")
        return data, len(self.log)


class RawREPLTests(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch("micropython_repl.time.sleep", return_value=None)
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def client(self, wire=None, **kwargs):
        wire = wire or Wire()
        client = RawREPL(wire, timeout=5, **kwargs)
        client.synchronize()
        return client, wire

    def test_credit_transfer_and_coalesced_double_eof(self):
        client, wire = self.client()
        result = client.execute("print('a rather long source')\n")
        self.assertEqual(result["stdout"], b"answer\r\n")
        self.assertEqual(result["transfer_mode"], "raw-paste")
        self.assertEqual(result["next_offset"], wire.offset())
        self.assertEqual(wire.sources, [b"print('a rather long source')\n"])

    def test_multiple_commands_share_one_synchronization(self):
        client, wire = self.client()
        client.execute("x=1")
        client.execute("x=2")
        self.assertEqual(wire.sources, [b"x=1", b"x=2"])
        self.assertEqual(wire.writes.count(b"\r\x03"), 1)
        self.assertEqual(wire.writes.count(b"\r\x01"), 1)

    def test_raw_repl_fallback_keeps_pacing(self):
        client, wire = self.client(Wire(paste=False))
        result = client.execute("x='" + "a" * 500 + "'")
        self.assertEqual(result["transfer_mode"], "raw-repl-paced")
        self.assertTrue(all(len(data) <= 128 for data in wire.writes))

    def test_empty_source_never_sends_soft_reset(self):
        for source in ("", " \n"):
            client, wire = self.client()
            before = list(wire.writes)
            with self.assertRaises(ValueError):
                client.execute(source)
            self.assertEqual(wire.writes, before)

    def test_execute_requires_synchronization(self):
        wire = Wire()
        with self.assertRaisesRegex(UIFlowRuntimeError, "not synchronized"):
            RawREPL(wire, timeout=5).execute("x=1")
        self.assertEqual(wire.writes, [])

    def test_stderr_is_failure_without_leaking_its_contents(self):
        client, _ = self.client(Wire(stderr=b"private source details"))
        with self.assertRaises(UIFlowRuntimeError) as caught:
            client.execute("raise Exception()")
        self.assertEqual(caught.exception.code, "program_rpc_failed")
        self.assertNotIn("private source", str(caught.exception))
        self.assertIsNone(client.cursor)

    def test_output_limit_counts_stdout_and_stderr(self):
        client, _ = self.client(Wire(stdout=b"abc"))
        with self.assertRaises(UIFlowRuntimeError) as caught:
            client.execute("print('abc')", max_output=2)
        self.assertEqual(caught.exception.code, "program_rpc_output_too_large")

    def test_missing_prompt_fails_without_a_new_command(self):
        client, wire = self.client()
        wire.tail = b"!"
        with self.assertRaises(UIFlowRuntimeError) as caught:
            client.execute("x=1")
        self.assertEqual(caught.exception.code, "program_protocol_error")
        before = len(wire.writes)
        with self.assertRaises(UIFlowRuntimeError):
            client.execute("x=2")
        self.assertEqual(len(wire.writes), before)

    def test_zero_raw_paste_window_is_rejected(self):
        client, _ = self.client(Wire(window=0))
        with self.assertRaises(UIFlowRuntimeError) as caught:
            client.execute("x=1")
        self.assertEqual(caught.exception.code, "program_protocol_error")

    def test_cancellation_does_not_write_to_console(self):
        wire = Wire()
        client = RawREPL(wire, timeout=5, cancelled=lambda: True)
        with self.assertRaises(UIFlowRuntimeError) as caught:
            client.synchronize()
        self.assertEqual(caught.exception.code, "program_cancelled")
        self.assertEqual(wire.writes, [])

    def test_disconnect_does_not_turn_into_history_timeout(self):
        client, wire = self.client()
        wire.closed = True
        with self.assertRaises(GuestConsoleError) as caught:
            client.execute("x=1")
        self.assertEqual(caught.exception.code, "console_closed")

    def test_timeout_and_sync_callback(self):
        wire = Wire()
        client = RawREPL(wire, timeout=5)
        callback = mock.Mock()
        client.synchronize(callback)
        callback.assert_called_once_with()
        wire.tail = b""
        with self.assertRaises(UIFlowRuntimeError) as caught:
            client.execute("x=1")
        self.assertEqual(caught.exception.code, "program_timeout")


if __name__ == "__main__":
    unittest.main()
