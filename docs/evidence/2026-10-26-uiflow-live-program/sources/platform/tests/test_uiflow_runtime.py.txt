"""Isolated UART protocol tests; no firmware, interpreter guest or service.

The console models GuestConsole's persistent byte windows and a peer with a
limited receive window. Application markers are scripted peer output: these
tests establish host protocol behavior, never guest/hardware execution PASS.
"""
from __future__ import annotations

import ast
import heapq
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from guest_console import GuestConsoleError, MAX_RESPONSE_BYTES
import uiflow_runtime
from uiflow_runtime import (
    ExecutionStateScanner, UIFlowRuntimeError, execution_markers, execution_state, run_source,
)


PROMPT = b"raw REPL; CTRL-B to exit\r\n>"
EXECUTION = "run-20261026-a"


class VirtualClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []
        self.events = []
        self.sequence = 0

    def monotonic(self):
        return self.now

    def later(self, delay, callback):
        self.sequence += 1
        heapq.heappush(self.events, (self.now + delay, self.sequence, callback))

    def sleep(self, duration):
        if duration < 0:
            raise AssertionError("negative sleep")
        self.sleeps.append(duration)
        target = self.now + duration
        while self.events and self.events[0][0] <= target:
            when, _, callback = heapq.heappop(self.events)
            self.now = when
            callback()
        self.now = target


class ProtocolConsole:
    """Scripted peer exposing GuestConsole's protocol read/write methods.

    Reads do not consume bytes. A fragmented receive becomes visible only as
    virtual time advances, so the runtime must preserve its own byte cursor.
    """

    def __init__(
        self, clock, *, mode="paste", window=128, history=b"",
        output=None, fragmented=False, prompt=True, negotiation=None,
        acknowledge=True, eof_prefix=b"", credit_control=b"\x01",
        grant_credit=True,
    ):
        self.clock = clock
        self.mode = mode
        self.window = window
        self.log = bytearray(history)
        self.output = execution_markers(EXECUTION)["START"] if output is None else output
        self.fragmented = fragmented
        self.prompt = prompt
        self.negotiation = negotiation
        self.acknowledge = acknowledge
        self.eof_prefix = eof_prefix
        self.credit_control = credit_control
        self.grant_credit = grant_credit
        self.credit = window
        self.source = bytearray()
        self.source_writes = []
        self.writes = []
        self.waits = []
        self.reads = []
        self.negotiated = False
        self.submitted = False
        self.submitted_at = None
        self.submissions = 0
        self.max_credit_use = 0
        self.terminal = None

    def emit(self, data, *, fragmented=None):
        if fragmented is None:
            fragmented = self.fragmented
        if not fragmented or len(data) <= 1:
            self.log.extend(data)
            return
        # One byte now and the rest across several future read opportunities.
        self.log.extend(data[:1])
        for index in range(1, len(data)):
            chunk = data[index:index + 1]
            self.clock.later(index * 0.001, lambda chunk=chunk: self.log.extend(chunk))

    def offset(self):
        return len(self.log)

    def read_from(self, offset, limit):
        self.reads.append((offset, limit))
        return bytes(self.log[offset:offset + limit])

    def read_exact(self, offset, size, timeout, cancelled=None):
        deadline = self.clock.monotonic() + timeout
        while True:
            if cancelled is not None and cancelled():
                raise GuestConsoleError("console_cancelled", "console operation cancelled")
            if self.clock.monotonic() >= deadline:
                raise GuestConsoleError("console_timeout", "console byte wait timed out")
            data = self.read_from(offset, size)
            if len(data) == size:
                return data
            if self.terminal is not None:
                raise self.terminal
            self.clock.sleep(min(0.005, deadline - self.clock.monotonic()))

    def wait_for(self, marker, offset, timeout, cancelled=None):
        self.waits.append((marker, offset, timeout))
        deadline = self.clock.monotonic() + timeout
        while True:
            if cancelled is not None and cancelled():
                raise GuestConsoleError("console_cancelled", "console operation cancelled")
            if self.clock.monotonic() >= deadline:
                raise GuestConsoleError("console_timeout", "console marker wait timed out")
            data = self.read_from(offset, 1024 * 1024)
            if marker in data:
                # Match real GuestConsole: retain all received trailing bytes.
                return data, offset + len(data)
            self.clock.sleep(min(0.005, deadline - self.clock.monotonic()))

    def _grant(self):
        if self.submitted:
            return
        if self.credit_control == b"\x01":
            self.credit += self.window
        self.log.extend(self.credit_control)

    def write(self, data, timeout=5):
        if not isinstance(data, bytes) or timeout <= 0:
            raise AssertionError("invalid console write")
        self.writes.append((self.clock.monotonic(), data, timeout))
        if data == b"\r\x03":
            return len(data)
        if data == b"\r\x01":
            if self.prompt:
                self.emit(PROMPT)
            return len(data)
        if data == b"\x05A\x01":
            self.negotiated = True
            response = self.negotiation
            if response is None:
                response = (
                    b"R\x01" + self.window.to_bytes(2, "little")
                    if self.mode == "paste" else b"R\x00"
                )
            self.emit(response)
            return len(data)
        if not self.negotiated:
            raise AssertionError("source written before raw REPL negotiation")
        if data == b"\x04":
            if not self.source:
                raise AssertionError("empty Ctrl-D would soft-reset the guest")
            # An EOF sent in response to an early peer EOF only aborts transfer.
            if self.credit_control == b"\x04" and not self.submitted:
                self.submitted = True
                return len(data)
            if self.submitted:
                raise AssertionError("duplicate source submission/reset")
            self.submitted = True
            self.submitted_at = self.clock.monotonic()
            self.submissions += 1
            if self.acknowledge:
                ack = b"\x04" if self.mode == "paste" else b"OK"
                # EOF/OK and START deliberately share a receive by default.
                self.emit(self.eof_prefix + ack + self.output)
            return len(data)
        if self.submitted:
            raise AssertionError("source written after submission")
        if self.mode == "paste":
            if len(data) > self.credit:
                raise AssertionError("host exceeded peer's raw-paste credit")
            self.credit -= len(data)
            self.max_credit_use = max(self.max_credit_use, self.window - self.credit)
            if self.credit == 0 and self.grant_credit:
                self.clock.later(0.003, self._grant)
        self.source.extend(data)
        self.source_writes.append((self.clock.monotonic(), data))
        return len(data)


class UIFlowRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.clock = VirtualClock()
        self.patch = mock.patch.object(
            uiflow_runtime, "time",
            SimpleNamespace(monotonic=self.clock.monotonic, sleep=self.clock.sleep),
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def console(self, **options):
        return ProtocolConsole(self.clock, **options)

    def execute(self, console, source="print('hello')\n", **options):
        defaults = {"timeout": 2, "cancelled": lambda: False}
        defaults.update(options)
        return run_source(console, source, EXECUTION, **defaults)

    def assert_error(self, code, function, error_class=UIFlowRuntimeError):
        with self.assertRaises(error_class) as caught:
            function()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def assert_no_reset(self, console):
        self.assertEqual(console.submissions, 1)
        self.assertEqual(console.writes[0][1], b"\r\x03")
        self.assertEqual(console.writes[1][1], b"\r\x01")
        self.assertGreaterEqual(console.writes[1][0] - console.writes[0][0], 0.1)
        self.assertTrue(console.source, "Ctrl-D must submit nonempty source")
        self.assertNotIn(b"machine.reset", console.source)
        self.assertNotIn(b"soft_reset", console.source)
        self.assertNotIn(b"\r\x04", [row[1] for row in console.writes])

    def test_execution_markers_are_bound_to_exact_execution_id(self):
        markers = execution_markers(EXECUTION)
        self.assertEqual(markers["START"], b"__M5_EXEC_run-20261026-a__:START")
        for state, expected in (("START", "running"), ("DONE", "completed"), ("ERROR", "failed")):
            with self.subTest(state=state):
                self.assertEqual(execution_state(b"noise\r\n" + markers[state], EXECUTION), expected)
                self.assertIsNone(execution_state(markers[state], "run-20261026"))
                self.assertIsNone(execution_state(markers[state], EXECUTION + "-old"))

    def test_error_overrides_done_and_start_in_one_serial_window(self):
        markers = execution_markers(EXECUTION)
        self.assertEqual(execution_state(markers["START"] + markers["DONE"], EXECUTION), "completed")
        self.assertEqual(execution_state(b"\r\n".join(markers.values()), EXECUTION), "failed")

    def test_scanner_advances_bounded_windows_and_recovers_split_marker(self):
        marker = execution_markers(EXECUTION)["DONE"]
        prefix = b"old history"
        console = self.console(history=prefix + b"x" * (MAX_RESPONSE_BYTES - 7) + marker + b"tail")
        scanner = ExecutionStateScanner(EXECUTION, len(prefix))
        self.assertIsNone(scanner.scan(console))
        self.assertEqual(scanner.cursor, len(prefix) + MAX_RESPONSE_BYTES)
        self.assertLessEqual(len(scanner._tail), len(marker))
        self.assertEqual(scanner.scan(console), "completed")
        self.assertEqual(scanner.cursor, console.offset())
        self.assertTrue(all(limit <= MAX_RESPONSE_BYTES for _, limit in console.reads))
        console.log.extend(b"noise" * MAX_RESPONSE_BYTES)
        for _ in range(5):
            self.assertEqual(scanner.scan(console), "completed")
        self.assertEqual(scanner.cursor, console.offset())
        self.assertLess(len(scanner._tail), max(map(len, execution_markers(EXECUTION).values())))

    def test_scanner_preserves_terminal_state_across_later_start_and_noise(self):
        markers = execution_markers(EXECUTION)
        console = self.console(history=markers["ERROR"])
        scanner = ExecutionStateScanner(EXECUTION, 0)
        self.assertEqual(scanner.scan(console), "failed")
        console.log.extend(markers["START"] + markers["DONE"])
        self.assertEqual(scanner.scan(console), "failed")
        self.assertEqual(scanner.scan(console), "failed")

    def test_application_marker_after_large_output_is_observed(self):
        marker = execution_markers(EXECUTION)["START"]
        console = self.console(output=b"x" * (MAX_RESPONSE_BYTES + 17) + marker)
        result = self.execute(console)
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["next_offset"], console.offset())
        self.assertTrue(all(limit <= MAX_RESPONSE_BYTES for _, limit in console.reads))

    def test_reader_failures_propagate_during_negotiation_and_application_wait(self):
        for code in ("console_eof", "console_log_error", "console_read_error", "console_closed"):
            for phase in ("negotiation", "application"):
                with self.subTest(code=code, phase=phase):
                    console = self.console(**({"negotiation": b"R"} if phase == "negotiation" else {"output": b""}))
                    self.clock.later(0.15, lambda console=console, code=code: setattr(
                        console, "terminal", GuestConsoleError(code, "reader stopped"),
                    ))
                    started = self.clock.monotonic()
                    self.assert_error(code, lambda: self.execute(console), GuestConsoleError)
                    self.assertLess(self.clock.monotonic() - started, 0.3)

    def test_small_raw_paste_window_never_exceeds_credit(self):
        console = self.console(window=128)
        result = self.execute(console, source="print('long')\n" * 40)
        self.assertGreater(len(console.source_writes), 4)
        self.assertTrue(all(len(data) <= 128 for _, data in console.source_writes))
        self.assertLessEqual(console.max_credit_use, 128)
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["transfer_mode"], "raw-paste")
        self.assertTrue(result["acknowledged"])
        self.assertEqual(result["cleanup_mode"], "interrupt-only")
        self.assert_no_reset(console)

    def test_window_smaller_than_chunk_cap_is_respected(self):
        console = self.console(window=17)
        self.assertEqual(self.execute(console)["state"], "running")
        self.assertTrue(all(len(data) <= 17 for _, data in console.source_writes))
        self.assertLessEqual(console.max_credit_use, 17)

    def test_fragmented_prompt_window_grants_eof_and_marker_keep_byte_cursor(self):
        console = self.console(fragmented=True, window=128)
        result = self.execute(console)
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["serial_offset"], len(PROMPT))
        self.assertLessEqual(result["next_offset"], console.offset())
        self.assertIn(execution_markers(EXECUTION)["START"], console.read_from(
            result["serial_offset"], result["next_offset"] - result["serial_offset"],
        ))

    def test_paste_eof_and_start_same_receive_are_not_discarded(self):
        console = self.console(history=b"boot history\r\n")
        result = self.execute(console)
        self.assertEqual(result["serial_offset"], len(b"boot history\r\n" + PROMPT))
        received = console.read_from(result["serial_offset"], 1024 * 1024)
        self.assertIn(b"\x04" + execution_markers(EXECUTION)["START"], received)
        self.assertEqual(result["next_offset"], console.offset())

    def test_extra_paste_credit_before_eof_is_accepted(self):
        console = self.console(eof_prefix=b"\x01\x01")
        self.assertEqual(self.execute(console)["state"], "running")

    def test_r0_fallback_paces_utf8_source_in_small_chunks(self):
        console = self.console(mode="raw")
        result = self.execute(console, source="print('温度\\n\\\"单位\\\"')\n" * 20)
        self.assertEqual(result["transfer_mode"], "raw-repl-paced")
        self.assertTrue(all(len(data) <= 128 for _, data in console.source_writes))
        self.assertGreater(len(console.source_writes), 4)
        for (before, _), (after, _) in zip(console.source_writes, console.source_writes[1:]):
            self.assertGreaterEqual(after - before, 0.0099)
        self.assertEqual(result["state"], "running")
        self.assert_no_reset(console)

    def test_fragmented_fallback_ok_and_marker_are_not_lost(self):
        console = self.console(mode="raw", fragmented=True)
        result = self.execute(console)
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["transfer_mode"], "raw-repl-paced")

    def test_done_and_error_are_application_results_after_transport_ack(self):
        markers = execution_markers(EXECUTION)
        for output, state in (
            (markers["START"] + b"\r\n42\r\n" + markers["DONE"], "completed"),
            (b"SyntaxError: invalid syntax\r\n" + markers["ERROR"], "failed"),
            (markers["START"] + b"Traceback\r\n" + markers["ERROR"], "failed"),
        ):
            with self.subTest(state=state, output=output):
                console = self.console(output=output)
                result = self.execute(console)
                self.assertEqual(result["state"], state)
                self.assertTrue(result["acknowledged"])

    def test_ack_without_fresh_application_marker_times_out(self):
        for mode in ("paste", "raw"):
            with self.subTest(mode=mode):
                console = self.console(mode=mode, output=b"received only\r\n")
                self.assert_error("program_timeout", lambda: self.execute(console, timeout=0.6))
                self.assertTrue(console.submitted)
                self.assert_no_reset(console)

    def test_old_execution_markers_after_submission_do_not_ack_new_application(self):
        old = b"\r\n".join(execution_markers("previous-run").values())
        console = self.console(output=old)
        self.assert_error("program_timeout", lambda: self.execute(console, timeout=0.6))

    def test_same_execution_marker_in_old_log_and_old_prompt_are_not_reused(self):
        history = PROMPT + b"\r\n" + execution_markers(EXECUTION)["DONE"]
        console = self.console(history=history, prompt=False)
        self.assert_error("console_timeout", lambda: self.execute(console, timeout=0.4), GuestConsoleError)
        self.assertEqual(console.waits[0][1], len(history))
        self.assertFalse(console.negotiated)
        self.assertFalse(console.source)

    def test_old_same_execution_markers_before_new_prompt_do_not_count(self):
        console = self.console(history=execution_markers(EXECUTION)["DONE"], output=b"")
        self.assert_error("program_timeout", lambda: self.execute(console, timeout=0.5))

    def test_source_unicode_quotes_controls_and_multiline_form_valid_wrapper(self):
        source = 'message = "中文与\'引号\'、\\路径"\r\nprint(message)\n# controls: \x00\x03\x04\n'
        console = self.console()
        self.execute(console, source)
        module = ast.parse(console.source.decode("utf-8"))
        outer = module.body[0]
        self.assertIsInstance(outer, ast.Try)
        compiled = outer.body[0].value
        self.assertIsInstance(compiled, ast.Call)
        self.assertEqual(compiled.func.id, "compile")
        self.assertEqual(compiled.args[0].value, source)
        self.assertEqual(compiled.args[1].value, f"<m5-{EXECUTION}>")
        self.assertEqual(compiled.args[2].value, "exec")
        self.assertLess(outer.body[0].lineno, outer.body[1].lineno)
        self.assertEqual(outer.body[1].value.args[0].value, execution_markers(EXECUTION)["START"].decode())
        self.assertEqual(outer.handlers[0].type.id, "BaseException")
        self.assertEqual(outer.handlers[0].body[-1].value.args[0].value, execution_markers(EXECUTION)["ERROR"].decode())
        self.assertEqual(outer.orelse[0].value.args[0].value, execution_markers(EXECUTION)["DONE"].decode())
        self.assertNotIn(b"\x04", console.source)

    def test_cancel_before_start_writes_nothing(self):
        console = self.console()
        self.assert_error("program_cancelled", lambda: self.execute(console, cancelled=lambda: True))
        self.assertEqual(console.writes, [])

    def test_cancel_during_interrupt_separation_does_not_enter_raw_or_submit(self):
        console = self.console()
        start = self.clock.monotonic()
        self.assert_error("program_cancelled", lambda: self.execute(
            console, cancelled=lambda: self.clock.monotonic() - start >= 0.035,
        ))
        self.assertEqual([row[1] for row in console.writes], [b"\r\x03"])

    def test_cancel_during_source_transfer_does_not_submit_incomplete_source(self):
        console = self.console()
        self.assert_error("program_cancelled", lambda: self.execute(
            console, cancelled=lambda: len(console.source) >= 128,
        ))
        self.assertEqual(len(console.source), 128)
        self.assertFalse(console.submitted)
        self.assertNotIn(b"\x04", [row[1] for row in console.writes])

    def test_cancel_while_waiting_for_application_marker(self):
        console = self.console(output=b"")
        self.assert_error("program_cancelled", lambda: self.execute(
            console, cancelled=lambda: console.submitted_at is not None
            and self.clock.monotonic() - console.submitted_at >= 0.04,
        ))
        self.assertTrue(console.submitted)
        self.assertTrue(any(offset >= len(PROMPT) and limit == 1 for offset, limit in console.reads))
        self.assert_no_reset(console)

    def test_empty_caller_source_still_submits_nonempty_wrapper_without_reset(self):
        console = self.console(output=execution_markers(EXECUTION)["DONE"])
        result = self.execute(console, source="")
        self.assertEqual(result["state"], "completed")
        self.assertTrue(console.source.startswith(b"try:\n"))
        self.assert_no_reset(console)

    def test_timeout_during_negotiation_is_bounded(self):
        console = self.console(negotiation=b"R")
        start = self.clock.monotonic()
        self.assert_error("program_timeout", lambda: self.execute(console, timeout=0.3))
        self.assertAlmostEqual(self.clock.monotonic() - start, 0.3)
        self.assertFalse(console.source)

    def test_missing_paste_credit_times_out_without_overrunning_guest(self):
        console = self.console(window=128, grant_credit=False)
        self.assert_error("program_timeout", lambda: self.execute(console, timeout=0.3))
        self.assertEqual(len(console.source), 128)
        self.assertEqual(len(console.source_writes), 1)
        self.assertFalse(console.submitted)

    def test_missing_source_eof_ack_times_out_even_if_marker_is_in_history(self):
        console = self.console(acknowledge=False, history=execution_markers(EXECUTION)["START"])
        self.assert_error("program_timeout", lambda: self.execute(console, timeout=0.4))
        self.assertTrue(console.submitted)

    def test_invalid_negotiation_window_and_control_fail_closed(self):
        cases = (
            {"negotiation": b"NO"},
            {"window": 0},
            {"credit_control": b"?"},
            {"credit_control": b"\x04"},
        )
        for options in cases:
            with self.subTest(options=options):
                console = self.console(**options)
                self.assert_error("program_protocol_error", lambda: self.execute(console))

    def test_invalid_paste_eof_and_plain_ack_fail_closed(self):
        for options in (
            {"eof_prefix": b"?"},
            {"mode": "raw", "eof_prefix": b"NO"},
        ):
            with self.subTest(options=options):
                console = self.console(**options)
                self.assert_error("program_protocol_error", lambda: self.execute(console))

    def test_prompt_wait_obeys_console_timeout_and_cancellation_contract(self):
        console = self.console(prompt=False)
        start = self.clock.monotonic()
        self.assert_error("console_cancelled", lambda: self.execute(
            console, cancelled=lambda: self.clock.monotonic() - start >= 0.15,
        ), GuestConsoleError)
        self.assertFalse(console.negotiated)


if __name__ == "__main__":
    unittest.main()
