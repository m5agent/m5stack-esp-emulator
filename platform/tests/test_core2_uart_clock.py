#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

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

    def test_phase_profile_groups_guest_pcs_and_flash_reads(self):
        runner = load_runner()
        trace = """\
[esp32-handoff] now=100 cpu=-1 pc=00000000 component=cpu event=sample a=40087980 b=40087234 c=0 d=50000000
[esp32-handoff] now=200 cpu=-1 pc=00000000 component=cpu event=sample a=40087980 b=400977b3 c=0 d=50000000
[esp32-handoff] now=300 cpu=-1 pc=00000000 component=cpu event=sample a=4026306e b=40087234 c=1 d=50000000
[esp32-handoff] now=400 cpu=1 pc=40093b57 component=ssi event=transaction-begin a=3 b=1234 c=0 d=64
[esp32-handoff] now=500 cpu=1 pc=40093b57 component=ssi event=transaction-begin a=3 b=1238 c=0 d=64
[esp32-handoff] now=600 cpu=1 pc=4006222c component=ssi event=transaction-end a=5 b=0 c=0 d=1
"""
        self.assertEqual(
            runner.summarize_phase_profile(trace),
            {
                "pc_samples": 3,
                "sample_window_ns": {"first": 100, "last": 300},
                "cpu0_top_pcs": [
                    {"pc": "0x40087980", "samples": 2},
                    {"pc": "0x4026306e", "samples": 1},
                ],
                "cpu1_top_pcs": [
                    {"pc": "0x40087234", "samples": 2},
                    {"pc": "0x400977b3", "samples": 1},
                ],
                "ssi_transaction_events": 2,
                "ssi_read_events": 2,
                "ssi_read64_events": 2,
            },
        )

    def test_phase_profile_controls_are_explicit_in_runner(self):
        source = RUNNER.read_text()
        self.assertIn("M5SW_ESP32_HANDOFF_PC_SAMPLE_NS", source)
        self.assertIn("M5SW_UART_TRACE", source)
        self.assertIn('"pc_sampling_ns": args.pc_sample_ns', source)
        self.assertIn('"uart_trace": args.uart_trace', source)
        self.assertIn('"phase_profile": summarize_phase_profile(stderr)', source)


if __name__ == "__main__":
    unittest.main()
