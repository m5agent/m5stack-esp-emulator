#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

from _docs_contract_support import DocsContractBase, ROOT


EVIDENCE = (
    ROOT
    / "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-handoff-state-sweep.json"
)
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0039-esp32-handoff-state-dump.patch"
)
RUNNER = (
    ROOT
    / "tests/firmware/core2_handoff_trace/run_pause_sweep.py"
)


class Core2HandoffStateSweepTests(DocsContractBase):
    def test_exact_time_state_sweep_is_artifact_bound(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["kind"], "core2-handoff-pause-sweep")
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["firmware"]["normalized_flash_sha256"],
            "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc",
        )
        self.assertEqual(evidence["runtime"]["runtime"], "qemu")
        self.assertIsNone(evidence["runtime"]["icount_shift"])
        self.assertEqual(
            evidence["runtime"]["qemu_binary_sha256"],
            "f7ac5a0352eb4345f5c3b719a5dd656c5c0cdfb3d805cf258f144d1ae1fb6718",
        )
        snapshots = {
            row["pause_target_ns"]: row
            for row in evidence["snapshots"]
        }
        self.assertEqual(
            set(snapshots),
            {14_800_000_000, 15_300_000_000, 15_900_000_000},
        )
        self.assertEqual(
            snapshots[14_800_000_000]["cpu"]["0"]["pc"],
            "0x40087980",
        )
        self.assertEqual(
            snapshots[15_300_000_000]["cpu"]["0"]["pc"],
            "0x40087980",
        )
        self.assertNotEqual(
            snapshots[14_800_000_000]["cpu"]["1"]["pc"],
            snapshots[15_900_000_000]["cpu"]["1"]["pc"],
        )
        self.assertEqual(
            snapshots[14_800_000_000]["memory"]["0x3ffc7ec9"],
            "0x01",
        )

        for row in snapshots.values():
            counters = row["dport"]["freeze-counters"]
            io = row["io"]["ssi:freeze-counters"]
            self.assertGreater(counters["a"], 16_100)
            self.assertEqual(counters["b"], 6_679)
            self.assertGreater(io["a"], 6_900)
            self.assertGreater(io["b"], 230_000)

        ordered = [snapshots[key] for key in sorted(snapshots)]
        self.assertLess(
            ordered[0]["io"]["ssi:freeze-counters"]["a"],
            ordered[1]["io"]["ssi:freeze-counters"]["a"],
        )
        self.assertLess(
            ordered[1]["io"]["ssi:freeze-counters"]["a"],
            ordered[2]["io"]["ssi:freeze-counters"]["a"],
        )
        self.assertEqual(
            evidence["classification"]["guest_deadlock"],
            "NOT PROVEN",
        )
        self.assertEqual(
            evidence["classification"]["uart_storm"],
            "REJECTED",
        )

    def test_state_dump_patch_keeps_sampling_off_and_actions_bounded(self) -> None:
        patch = PATCH.read_text()
        self.assertIn("M5SW_ESP32_HANDOFF_DUMP_STATE", patch)
        self.assertIn("M5SW_ESP32_HANDOFF_PAUSE_ACTION", patch)
        self.assertIn('strcmp(action, "exit")', patch)
        self.assertIn("0x3ffc7ec8", patch)
        self.assertIn("0x3ffc7ec9", patch)
        self.assertIn("0x3ffc7750", patch)
        self.assertIn("0x3ffc7754", patch)
        self.assertIn("freeze-counters", patch)
        self.assertIn("esp32_handoff_metrics", patch)
        self.assertNotIn("changed_pages == 0", patch)

        runner = RUNNER.read_text()
        self.assertIn("M5SW_ESP32_HANDOFF_PAUSE_NS", runner)
        self.assertIn("M5SW_ESP32_HANDOFF_DUMP_STATE", runner)
        self.assertIn("--attempts", runner)
        self.assertIn("--capture-frame", runner)
        self.assertIn('run_dir / "frame.png"', runner)
        self.assertIn("signal.SIGCONT", runner)
        self.assertIn("immediately-after-pause-resume", runner)
        self.assertIn('"frame_capture": args.capture_frame', runner)
        self.assertIn('"CAPTURED_BLACK"', runner)
        self.assertIn('"CAPTURED_NONBLANK"', runner)
        self.assertIn(
            'env.pop("M5SW_ESP32_HANDOFF_PAUSE_ACTION", None)',
            runner,
        )
        self.assertIn('"ttl_seconds": 3600', runner)
        self.assertIn('"3600"', runner)
        self.assertIn('choices=("qemu", "qemu-wifi")', runner)
        compile(runner, str(RUNNER), "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
