#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0091-esp32-timg-feed-reschedule.patch"
)


class Esp32TimgWdtReschedulePatchTests(unittest.TestCase):
    def test_feed_replaces_pending_stage_deadline(self):
        patch = PATCH.read_text()
        self.assertIn(
            "timer_mod_ns(&ws->stage_timer, ns_now + ns_to_timeout);",
            patch,
        )
        self.assertIn(
            "-    timer_mod_anticipate_ns("
            "&ws->stage_timer, ns_now + ns_to_timeout);",
            patch,
        )
        self.assertIn(
            "+    timer_mod_ns("
            "&ws->stage_timer, ns_now + ns_to_timeout);",
            patch,
        )
        self.assertIn(
            "timer_mod_anticipate_ns() deliberately keeps the earlier deadline",
            patch,
        )
        self.assertIn("successful WDTFEED", patch)

    def test_patch_does_not_change_watchdog_configuration(self):
        patch = PATCH.read_text()
        forbidden = (
            "M5SW_DISABLE_WDT",
            "wdt_disable",
            "qemu_clock_warp",
            "qemu_clock_notify",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, patch)


if __name__ == "__main__":
    unittest.main()
