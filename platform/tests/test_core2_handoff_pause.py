#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / (
    "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-handoff-pause.json"
)
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0038-esp32-handoff-pause.patch"


class Core2HandoffPauseTests(unittest.TestCase):
    def test_pause_evidence_captures_both_sides_of_the_gap(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["status"], "PARTIAL")
        self.assertEqual(
            evidence["artifact_mapping"]["uart_isr_symbol_mapping"],
            "REJECTED",
        )
        runs = {run["name"]: run for run in evidence["runs"]}
        self.assertEqual(
            set(runs),
            {"near_final_feed", "inside_feed_to_timeout_gap"},
        )
        early = runs["near_final_feed"]
        late = runs["inside_feed_to_timeout_gap"]
        self.assertEqual(early["pause_event_ns"], 14_800_033_000)
        self.assertEqual(late["pause_event_ns"], 15_301_447_000)
        self.assertEqual(
            late["lldb_state"]["cpu0"]["pc"],
            "0x40087980",
        )
        self.assertEqual(
            late["lldb_state"]["cpu1"]["pc"],
            "0x40084484",
        )
        self.assertEqual(
            late["lldb_state"]["cpu1"]["intset"],
            "0x00000040",
        )
        self.assertEqual(
            late["lldb_state"]["cpu1"]["interrupt_request"],
            "0x00000002",
        )
        for run in runs.values():
            self.assertEqual(
                run["serial"]["sha256"],
                "e996276519b4f8882739ff1c494dcecba313c99278857a53a984c1c9986a1b62",
            )
            self.assertFalse(run["serial"]["has_repl_prompt"])
        regression = evidence["regression"]["core2_uiflow2"]
        self.assertEqual(regression["cases_passed"], 6)
        self.assertEqual(regression["checks_passed"], 24)
        self.assertFalse(regression["retry_used"])
        self.assertEqual(
            evidence["validation_suite"]["platform_unittest"]["passed"],
            508,
        )

    def test_pause_patch_is_opt_in_and_uses_sigstop(self) -> None:
        patch = PATCH.read_text()
        self.assertIn("M5SW_ESP32_HANDOFF_PAUSE_NS", patch)
        self.assertIn("raise(SIGSTOP)", patch)
        self.assertIn("esp32_handoff_pause_start", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)


if __name__ == "__main__":
    unittest.main()
