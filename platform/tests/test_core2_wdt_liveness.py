#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tests/firmware/core2_handoff_trace/run_wdt_liveness.py"
)
EVIDENCE = (
    ROOT
    / "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-wdt-liveness-3x.json"
)
sys.path.insert(0, str(RUNNER.parent))
SPEC = importlib.util.spec_from_file_location(
    "core2_wdt_liveness_runner",
    RUNNER,
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def synthetic_trace(
    *,
    feed_times: list[int],
    reset_ns: int,
    tg1_timeout_ns: int | None = None,
) -> str:
    lines = [
        "[esp32-handoff] now=5000000000 cpu=-1 pc=00000000 "
        "component=timg event=wdt-timeout a=0 b=0 c=1 d=900000000",
        "[esp32-handoff] now=5000010000 cpu=-1 pc=00000000 "
        "component=timg event=wdt-timeout-gap "
        "a=0 b=0 c=5000000000 d=1",
        "[esp32-handoff] now=5000050000 cpu=-1 pc=00000000 "
        "component=timg event=wdt-int-masked "
        "a=0 b=0 c=4 d=1",
        "[esp32-timg] TG0 timeout now=5000009000 stage=0 mode=1",
        "[esp32-timg] TG0 arm now=5000010000 stage=1 "
        "timeout=00004e20 count=00000000 delta=00004e20 ns=10000000000",
    ]
    for feed_ns in feed_times:
        lines.extend(
            [
                "[esp32-timg] TG1 WDTFEED",
                "[esp32-timg] TG1 feed stage=0 timeout=00000640",
                f"[esp32-timg] TG1 arm now={feed_ns} stage=0 "
                "timeout=00000640 count=00000000 delta=00000640 "
                "ns=800000000",
            ]
        )
    if tg1_timeout_ns is not None:
        lines.extend(
            [
                f"[esp32-handoff] now={tg1_timeout_ns} cpu=-1 pc=00000000 "
                "component=timg event=wdt-timeout "
                "a=1 b=0 c=1 d=15000000000",
                f"[esp32-handoff] now={tg1_timeout_ns + 1000} "
                "cpu=-1 pc=00000000 component=timg event=wdt-timeout-gap "
                f"a=1 b=0 c={tg1_timeout_ns - 15000000000} d=100",
            ]
        )
    lines.extend(
        [
            f"[esp32-handoff] now={reset_ns - 6000000} "
            "cpu=-1 pc=00000000 component=timg event=wdt-timeout "
            "a=0 b=1 c=3 d=900000000",
            f"[esp32-handoff] now={reset_ns - 5000000} "
            "cpu=-1 pc=00000000 component=timg event=wdt-timeout-gap "
            f"a=0 b=1 c={reset_ns - 900000000} d=2",
            f"[esp32-timg] TG0 timeout now={reset_ns - 4000000} "
            "stage=1 mode=3",
            f"[esp32-handoff] now={reset_ns} "
            "cpu=-1 pc=00000000 component=timg event=wdt-reset "
            "a=0 b=311296 c=65536 d=26000000",
            "[esp32-timg] TG0 reset config0=0004c000 "
            "config1=00010000 timeout=018cba80 en_at_reset=1 flash_boot=1",
        ]
    )
    return "\n".join(lines)


class Core2WdtLivenessTests(unittest.TestCase):
    def test_three_runs_distinguish_bootloader_reset_from_tg1_stall(
        self,
    ) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["kind"], "core2-wdt-liveness")
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["firmware"]["normalized_flash_sha256"],
            "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc",
        )
        self.assertEqual(
            evidence["runtime"]["qemu_binary_sha256"],
            "f7ac5a0352eb4345f5c3b719a5dd656c5c0cdfb3d805cf258f144d1ae1fb6718",
        )
        self.assertEqual(evidence["runtime"]["pc_trace"], "NOT RUN")
        self.assertEqual(len(evidence["runs"]), 3)
        self.assertFalse(evidence["failures"])
        for run in evidence["runs"]:
            self.assertEqual(
                run["classification"],
                "BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE",
            )
            self.assertTrue(run["tg0"]["stage0_interrupt_masked"])
            self.assertLess(
                run["tg0"]["stage0_timeout_ns"],
                run["tg0"]["stage1_timeout_ns"],
            )
            self.assertLess(
                run["tg0"]["stage1_timeout_ns"],
                run["first_boot_reset_ns"],
            )
            self.assertEqual(
                run["tg0"][
                    "reconfigure_feed_or_protect_after_stage0"
                ],
                0,
            )
            self.assertEqual(run["tg1"]["timeout_count_before_reset"], 0)
            self.assertLessEqual(
                run["tg1"]["last_feed_gap_to_reset_ns"],
                evidence["runtime"]["tg1_live_gap_limit_ns"],
            )
            self.assertLessEqual(
                run["tg1"]["max_feed_interval_ns"],
                evidence["runtime"]["tg1_max_gap_limit_ns"],
            )
            self.assertEqual(run["tg1"]["intervals_over_100ms"], 0)
            self.assertFalse(run["serial"]["has_repl_prompt"])
            self.assertEqual(
                run["frame"]["sha256"],
                "57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43",
            )
        self.assertEqual(
            evidence["classification"]["single_tg1_800ms_gap"],
            "NOT_REPRODUCED",
        )

    def test_bootloader_stage1_reset_can_coexist_with_live_tg1(self) -> None:
        reset_ns = 15_900_000_000
        feed_times = list(range(1_000_000_000, reset_ns - 2_000_000, 50_000_000))
        feed_times.append(reset_ns - 1_000_000)
        result = runner.summarize_wdt_liveness(
            synthetic_trace(feed_times=feed_times, reset_ns=reset_ns),
            "MicroPython\nno prompt\n",
            b"\x89PNG\r\n\x1a\nframe",
        )
        self.assertEqual(
            result["classification"],
            "BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE",
        )
        self.assertTrue(result["tg0"]["stage0_interrupt_masked"])
        self.assertEqual(
            result["tg0"]["reconfigure_feed_or_protect_after_stage0"],
            0,
        )
        self.assertEqual(result["tg1"]["timeout_count_before_reset"], 0)
        self.assertLessEqual(
            result["tg1"]["last_feed_gap_to_reset_ns"],
            runner.TG1_FEED_LIVE_GAP_NS,
        )
        self.assertFalse(result["serial"]["has_repl_prompt"])

    def test_tg1_interrupt_timeout_takes_priority(self) -> None:
        reset_ns = 15_900_000_000
        result = runner.summarize_wdt_liveness(
            synthetic_trace(
                feed_times=[15_799_000_000],
                reset_ns=reset_ns,
                tg1_timeout_ns=15_899_000_000,
            ),
            "MicroPython\n",
            b"\x89PNG\r\n\x1a\nframe",
        )
        self.assertEqual(
            result["classification"],
            "TG1_INTERRUPT_WDT_BEFORE_RESET",
        )
        self.assertEqual(result["tg1"]["timeout_count_before_reset"], 1)

    def test_stalled_tg1_feed_is_not_reported_as_live(self) -> None:
        reset_ns = 15_900_000_000
        feed_times = list(range(1_000_000_000, 14_000_000_000, 50_000_000))
        result = runner.summarize_wdt_liveness(
            synthetic_trace(feed_times=feed_times, reset_ns=reset_ns),
            "MicroPython\n",
            b"\x89PNG\r\n\x1a\nframe",
        )
        self.assertEqual(
            result["classification"],
            "TG1_FEED_STALLED_BEFORE_TG0_RESET",
        )
        self.assertGreater(
            result["tg1"]["last_feed_gap_to_reset_ns"],
            runner.TG1_FEED_LIVE_GAP_NS,
        )


if __name__ == "__main__":
    unittest.main()
