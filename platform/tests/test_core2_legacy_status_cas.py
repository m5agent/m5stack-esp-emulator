#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0075-esp32-legacy-status-cas-correlation.patch"
)
EPISODE_PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0086-esp32-legacy-cas-episode-profile.patch"
)
RUNNER = (
    ROOT
    / "tests/firmware/core2_handoff_trace/run_pause_sweep.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "core2_legacy_status_cas_runner",
        RUNNER,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Core2LegacyStatusCasPatchTests(unittest.TestCase):
    def test_patch_records_status_cache_and_cas_context(self):
        patch = PATCH.read_text()
        self.assertIn("ssi_rdsr_status_counts", patch)
        self.assertIn("ssi_rdsr_context_keys", patch)
        self.assertIn("esp32_handoff_cache_snapshot", patch)
        self.assertIn("freeze-rdsr-status", patch)
        self.assertIn("freeze-rdsr-cache-delta", patch)
        self.assertIn("s32c1i_caller_a0s", patch)
        self.assertIn("component=s32c1i", patch)
        self.assertIn("event=freeze-total", patch)
        self.assertIn("freeze-caller", patch)
        self.assertIn("M5SW_XTENSA_CONTENDED_CAS_YIELD", patch)

    def test_episode_patch_counts_hold_intervals_without_icount_abort(self):
        patch = EPISODE_PATCH.read_text()
        self.assertIn("ESP32_HANDOFF_S32C1I_EPISODE_BUCKETS", patch)
        self.assertIn("s32c1i_episode_duration_ns_max", patch)
        self.assertIn("freeze-episodes", patch)
        self.assertIn("freeze-episode-lock-attempts", patch)
        self.assertIn("no-I/O translation block", patch)
        self.assertIn("!cpu_state->neg.can_do_io", patch)
        self.assertIn("qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)

    def test_patch_keeps_controls_opt_in_and_wdt_unchanged(self):
        patch = PATCH.read_text()
        self.assertIn("getenv(\"M5SW_XTENSA_CONTENDED_CAS_YIELD\")", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)
        self.assertNotIn("qemu_clock_notify", patch)
        self.assertNotIn("qemu_clock_warp", patch)


class Core2LegacyStatusCasRunnerTests(unittest.TestCase):
    def test_rdsr_profile_preserves_status_context_and_cache_deltas(self):
        runner = load_runner()
        trace = "\n".join(
            (
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-count a=2 b=0 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-status a=0 b=1 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-status a=2 b=1 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-previous-command a=187 b=2 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-previous-command-hi a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-previous-length a=64 b=2 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-gap a=900 b=600 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-fast-read a=2 b=82 c=14999743 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-fast-read-byte a=255 b=2 c=1 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-interrupt a=0 b=2 c=2 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-context a=2 b=1 c=4006222c d=1",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-context a=0 b=0 c=4006222c d=1",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-context-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-cache-delta a=0 b=2 c=8 d=4",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-last a=2 b=187 c=6291538 d=1380933465",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-last-context a=1 b=395552 c=0 d=4006222c",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-last-cache a=2829504 b=211956 c=5911 d=79997688220",
                "[esp32-handoff] now=10 cpu=-1 pc=00000000 component=ssi event=freeze-rdsr-last-cache1 a=211980 b=84 c=0 d=0",
            )
        )
        profile = runner.summarize_rdsr_profile(runner.parse_trace(trace))
        self.assertEqual(profile["count"], 2)
        self.assertEqual(profile["statuses"], {"0x00": 1, "0x02": 1})
        self.assertEqual(
            profile["contexts"]["0x02"],
            {"cpu1:0x4006222c": 1},
        )
        self.assertEqual(
            profile["cache_delta"]["0"],
            {"nonzero": 2, "total": 8, "max": 4},
        )
        self.assertEqual(profile["last_context"]["pc"], "0x4006222c")
        self.assertEqual(profile["context_total"], 2)
        self.assertEqual(profile["context_overflow"], 0)

    def test_cas_profile_preserves_lock_owner_caller_and_outcome(self):
        runner = load_runner()
        trace = "\n".join(
            (
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-total a=4 b=1 c=3 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-pc a=0 b=1 c=40095b2e d=1",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-pc a=0 b=0 c=40095b2e d=3",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-pc-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-lock a=3ffbf2cc b=4 c=1 d=b33fffff",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-lock-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-old a=0000abab b=3 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-old a=b33fffff b=1 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-old-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=20 cpu=0 pc=8009655c component=s32c1i event=freeze-caller a=40095b2e b=1 c=3ffbf2cc d=1",
                "[esp32-handoff] now=20 cpu=0 pc=8009655c component=s32c1i event=freeze-caller a=40095b2e b=0 c=3ffbf2cc d=3",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-caller-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=40096500 component=s32c1i event=freeze-holder a=40095b2e b=1 c=3ffbf2cc d=3",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-holder-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-episodes a=1 b=500 c=500 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-episode-bucket a=0 b=1 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-episode-lock a=3ffbf2cc b=1 c=500 d=500",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-episode-lock-attempts a=3ffbf2cc b=3 c=3 d=200",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-episode-lock-overflow a=0 b=0 c=0 d=0",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-episode-last a=3ffbf2cc b=500 c=3 d=1",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-last a=40095b2e b=3ffbf2cc c=b33fffff d=0000abab",
                "[esp32-handoff] now=20 cpu=-1 pc=00000000 component=s32c1i event=freeze-last-context a=1 b=1 c=8009655c d=0",
            )
        )
        profile = runner.summarize_s32c1i_profile(runner.parse_trace(trace))
        self.assertEqual(profile["total"], 4)
        self.assertEqual(profile["success"], 1)
        self.assertEqual(profile["failure"], 3)
        self.assertEqual(profile["contended"], 3)
        self.assertEqual(
            profile["locks"]["0x3ffbf2cc"],
            {
                "count": 4,
                "success": 1,
                "last_old": 0xB33FFFFF,
            },
        )
        self.assertEqual(profile["old_values"]["0x0000abab"], 3)
        self.assertEqual(
            profile["callers"][
                "cpu0:success=0:site=0x40095b2e:"
                "caller=0x8009655c:lock=0x3ffbf2cc"
            ],
            3,
        )
        self.assertEqual(
            profile["holders"][
                "holder_cpu1:holder=0x40096500:"
                "site=0x40095b2e:lock=0x3ffbf2cc"
            ],
            3,
        )
        self.assertEqual(
            profile["episodes"],
            {
                "count": 1,
                "duration_ns_total": 500,
                "duration_ns_max": 500,
                "incomplete": 0,
            },
        )
        self.assertEqual(
            profile["episode_locks"]["0x3ffbf2cc"],
            {
                "count": 1,
                "duration_ns_total": 500,
                "duration_ns_max": 500,
                "attempts_total": 3,
                "attempts_max": 3,
                "attempt_gap_ns_max": 200,
            },
        )
        self.assertEqual(profile["episode_buckets"], {"0": 1})
        self.assertEqual(
            profile["episode_last"]["lock"],
            "0x3ffbf2cc",
        )
        self.assertEqual(profile["last_context"]["caller"], 0x8009655C)


if __name__ == "__main__":
    unittest.main()
