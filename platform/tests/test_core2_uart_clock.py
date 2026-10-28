#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tests/firmware/core2_handoff_trace/run_pause_sweep.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "core2_pause_sweep_uart_clock",
        RUNNER,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Core2UartClockTests(unittest.TestCase):
    def test_uart_bytes_are_joined_into_virtual_time_lines(self):
        runner = load_runner()
        trace = "\n".join(
            (
                "[uart-tx] now=100 42",
                "[esp32-handoff] ignored",
                "[uart-tx] now=110 4f",
                "[uart-tx] now=120 41",
                "[uart-tx] now=130 52",
                "[uart-tx] now=140 44",
                "[uart-tx] now=150 0d",
                "[uart-tx] now=160 0a",
            )
        )
        self.assertEqual(
            runner.parse_uart_tx_lines(trace),
            [
                {
                    "start_ns": 100,
                    "end_ns": 160,
                    "text": "BOARD",
                }
            ],
        )

    def test_partial_uart_line_is_not_reported_as_complete(self):
        runner = load_runner()
        self.assertEqual(
            runner.parse_uart_tx_lines("[uart-tx] now=100 41"),
            [],
        )

    def test_line_limit_is_bounded(self):
        runner = load_runner()
        trace = "\n".join(
            f"[uart-tx] now={index} 0a" for index in range(10)
        )
        self.assertEqual(len(runner.parse_uart_tx_lines(trace, limit=3)), 3)


if __name__ == "__main__":
    unittest.main()
