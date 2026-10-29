#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest

from _docs_contract_support import DocsContractBase, ROOT


EVIDENCE = (
    ROOT
    / "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-handoff-pc-trace.json"
)
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0040-xtensa-handoff-pc-trace.patch"
)
IO_BOUNDARY_PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0089-xtensa-handoff-pc-trace-io-boundary.patch"
)
RUNNER = (
    ROOT
    / "tests/firmware/core2_handoff_trace/run_pc_trace.py"
)


class Core2HandoffPcTraceTests(DocsContractBase):
    def load_runner(self):
        runner_dir = str(RUNNER.parent)
        if runner_dir not in sys.path:
            sys.path.insert(0, runner_dir)
        spec = importlib.util.spec_from_file_location(
            "core2_handoff_pc_trace_runner",
            RUNNER,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_episode_summary_pairs_bin_bound_setter_phases(self) -> None:
        runner = self.load_runner()
        events = [
            {"now_ns": 1_900_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x40087A25},
            {"now_ns": 2_000_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x40087965},
            {"now_ns": 2_100_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x4008797A},
            {"now_ns": 2_500_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x40087B02},
            {"now_ns": 2_800_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x40087A25},
            {"now_ns": 3_000_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x40087965},
            {"now_ns": 3_050_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x4008797A},
            {"now_ns": 3_400_000_000, "component": "cpu", "event": "pc-trace", "pc": 0x40087B02},
        ]
        summary = runner.summarize_handoff_episodes(events, None)
        self.assertEqual(summary["events"], 8)
        self.assertEqual(summary["incomplete_blocks"], 0)
        self.assertEqual(
            summary["block_wait"],
            {
                "count": 2,
                "total_ns": 900_000_000,
                "mean_ns": 450_000_000,
                "p50_ns": 500_000_000,
                "p95_ns": 500_000_000,
                "max_ns": 500_000_000,
            },
        )
        self.assertEqual(
            summary["clear_to_can_start"]["total_ns"],
            150_000_000,
        )
        self.assertEqual(
            summary["can_start_to_complete"]["total_ns"],
            750_000_000,
        )
        self.assertEqual(
            summary["complete_to_initiator_prepare"]["total_ns"],
            300_000_000,
        )
        self.assertEqual(
            summary["initiator_prepare_to_block_clear"]["total_ns"],
            300_000_000,
        )
        self.assertEqual(
            summary["complete_to_block_clear"]["total_ns"],
            500_000_000,
        )

    def test_setter_trace_proves_repeated_completed_handoffs(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["kind"], "core2-handoff-pc-trace")
        self.assertEqual(evidence["status"], "DIAGNOSTIC")
        self.assertEqual(
            evidence["firmware"]["normalized_flash_sha256"],
            "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc",
        )
        summary = evidence["summary"]
        self.assertEqual(summary["first_wdt_timeout_ns"], 5_913_935_000)
        self.assertEqual(summary["first_wdt_reset_ns"], 15_914_787_000)
        self.assertEqual(summary["first_boot_pc_events"], 17_507)
        self.assertEqual(summary["pc_counts"]["0x40087965"], 4_377)
        self.assertEqual(summary["pc_counts"]["0x4008797a"], 4_377)
        self.assertEqual(summary["pc_counts"]["0x40087a25"], 4_377)
        self.assertEqual(summary["pc_counts"]["0x40087b02"], 4_376)
        self.assertEqual(
            summary["classification"]["handoff_cycles"],
            "REPEATED",
        )
        self.assertEqual(
            summary["classification"]["permanent_deadlock"],
            "NOT SUPPORTED",
        )
        self.assertEqual(summary["classification"]["legacy_boot"], "FAIL")
        self.assertTrue(summary["serial"]["has_micropython_banner"])
        self.assertFalse(summary["serial"]["has_repl_prompt"])
        self.assertEqual(
            summary["frame"]["sha256"],
            "57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43",
        )

    def test_ipc_summary_pairs_initiator_and_peer_phases(self) -> None:
        runner = self.load_runner()
        base = 1_000_000_000
        events = [
            {"now_ns": base + 100, "cpu": 1, "component": "cpu", "event": "pc-trace", "pc": 0x40087A25},
            {"now_ns": base + 110, "cpu": 0, "component": "cpu", "event": "pc-trace", "pc": 0x400889FB},
            {"now_ns": base + 120, "cpu": 0, "component": "cpu", "event": "pc-trace", "pc": 0x40088A2E},
            {"now_ns": base + 130, "cpu": 0, "component": "cpu", "event": "pc-trace", "pc": 0x40087965},
            {"now_ns": base + 140, "cpu": 0, "component": "cpu", "event": "pc-trace", "pc": 0x4008797A},
            {"now_ns": base + 200, "cpu": 1, "component": "cpu", "event": "pc-trace", "pc": 0x40087A31},
            {"now_ns": base + 300, "cpu": 1, "component": "cpu", "event": "pc-trace", "pc": 0x40087B02},
            {"now_ns": base + 350, "cpu": 0, "component": "cpu", "event": "pc-trace", "pc": 0x40088A31},
            {"now_ns": base + 1_100, "cpu": 1, "component": "cpu", "event": "pc-trace", "pc": 0x40087A25},
            {"now_ns": base + 1_110, "cpu": 0, "component": "cpu", "event": "pc-trace", "pc": 0x400889FB},
        ]
        summary = runner.summarize_ipc_handoff_phases(events, None)
        direction = summary["cpu1_initiator"]
        self.assertEqual(direction["prepare_events"], 2)
        self.assertEqual(direction["complete_episodes"], 1)
        self.assertEqual(direction["incomplete_episodes"], 1)
        phases = direction["phases"]
        self.assertEqual(phases["prepare_to_queue_wake"]["total_ns"], 10)
        self.assertEqual(
            phases["queue_wake_to_callback_enter"]["total_ns"],
            10,
        )
        self.assertEqual(
            phases["callback_enter_to_block_clear"]["total_ns"],
            10,
        )
        self.assertEqual(phases["block_clear_to_can_start"]["total_ns"], 10)
        self.assertEqual(
            phases["can_start_to_call_return"]["total_ns"],
            60,
        )
        self.assertEqual(
            phases["call_return_to_complete"]["total_ns"],
            100,
        )
        self.assertEqual(
            phases["complete_to_callback_return"]["total_ns"],
            50,
        )

    def test_pc_trace_patch_is_default_off_and_bin_bound(self) -> None:
        patch = PATCH.read_text()
        self.assertIn("M5SW_XTENSA_PC_TRACE", patch)
        self.assertIn("handoff_pc_trace", patch)
        self.assertIn("g_strsplit", patch)
        self.assertIn("INTENABLE", patch)
        self.assertIn("INTSET", patch)

        runner = RUNNER.read_text()
        self.assertIn("DEFAULT_PCS", runner)
        self.assertIn("0x40087965", runner)
        self.assertIn("0x40087A25", runner)
        self.assertIn("0x40087B02", runner)
        self.assertIn("first_wdt_reset_ns", runner)
        self.assertIn("permanent_deadlock", runner)
        self.assertIn("summarize_handoff_episodes", runner)
        self.assertIn("block_wait", runner)
        self.assertIn("clear_to_can_start", runner)
        self.assertIn("can_start_to_complete", runner)
        self.assertIn("complete_to_initiator_prepare", runner)
        self.assertIn("initiator_prepare_to_block_clear", runner)
        self.assertIn("complete_to_block_clear", runner)
        self.assertIn("ipc_handoff_phases", runner)
        self.assertIn("summarize_ipc_handoff_phases", runner)
        self.assertIn("--ipc-phases", runner)
        self.assertIn("--expected-image-sha256", runner)

    def test_pc_trace_io_boundary_prevents_bad_icount_read(self) -> None:
        patch = IO_BOUNDARY_PATCH.read_text()
        self.assertIn("translator_io_start(&dc->base)", patch)
        self.assertIn("!cpu->neg.can_do_io", patch)
        self.assertIn("Bad icount read", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
