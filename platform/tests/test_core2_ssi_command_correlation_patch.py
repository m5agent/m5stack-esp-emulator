#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0072-esp32-ssi-command-correlation.patch"
)


class Core2SsiCommandCorrelationPatchTests(unittest.TestCase):
    def test_patch_has_bounded_joint_and_per_command_profiles(self):
        patch = PATCH.read_text()
        self.assertIn("ESP32_HANDOFF_SSI_PAIR_SLOTS 4096u", patch)
        self.assertIn(
            "ESP32_HANDOFF_SSI_COMMAND_TIMING_SLOTS 1024u",
            patch,
        )
        self.assertIn("ssi_pair_keys", patch)
        self.assertIn("ssi_pair_overflow", patch)
        self.assertIn("ssi_command_timing_gap_ns", patch)
        self.assertIn("ssi_command_timing_overflow", patch)
        self.assertIn("ssi_transition_keys", patch)
        self.assertIn("ssi_transition_overflow", patch)
        self.assertIn("freeze-command-length", patch)
        self.assertIn("freeze-command-length-overflow", patch)
        self.assertIn("freeze-command-gap", patch)
        self.assertIn("freeze-command-gap-overflow", patch)
        self.assertIn("freeze-command-transition", patch)
        self.assertIn("freeze-command-transition-overflow", patch)

    def test_patch_does_not_add_scheduler_controls(self):
        patch = PATCH.read_text()
        self.assertNotIn("qemu_clock_notify", patch)
        self.assertNotIn("qemu_clock_warp", patch)
        self.assertNotIn("cpu_exit", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)


if __name__ == "__main__":
    unittest.main()
