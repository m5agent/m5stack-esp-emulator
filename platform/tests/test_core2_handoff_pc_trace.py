#!/usr/bin/env python3
from __future__ import annotations

import json
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
RUNNER = (
    ROOT
    / "tests/firmware/core2_handoff_trace/run_pc_trace.py"
)


class Core2HandoffPcTraceTests(DocsContractBase):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
