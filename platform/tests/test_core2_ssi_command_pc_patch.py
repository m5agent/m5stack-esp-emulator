#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0073-esp32-ssi-command-pc.patch"
)


class Core2SsiCommandPcPatchTests(unittest.TestCase):
    def test_patch_aggregates_issuer_cpu_and_pc(self):
        patch = PATCH.read_text()
        self.assertIn("ESP32_HANDOFF_SSI_COMMAND_PC_SLOTS 2048u", patch)
        self.assertIn("ssi_command_pc_keys", patch)
        self.assertIn("ssi_command_pc_counts", patch)
        self.assertIn("ssi_command_pc_overflow", patch)
        self.assertIn("current_cpu->cc->get_pc", patch)
        self.assertIn("event=freeze-command-pc", patch)
        self.assertIn("event=freeze-command-pc-overflow", patch)

    def test_patch_does_not_add_scheduler_controls(self):
        patch = PATCH.read_text()
        self.assertNotIn("qemu_clock_notify", patch)
        self.assertNotIn("qemu_clock_warp", patch)
        self.assertNotIn("cpu_exit", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)


if __name__ == "__main__":
    unittest.main()
