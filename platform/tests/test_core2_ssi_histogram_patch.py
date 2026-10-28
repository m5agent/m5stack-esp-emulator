#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0071-esp32-ssi-transaction-profile.patch"
)


class Core2SsiHistogramPatchTests(unittest.TestCase):
    def test_patch_aggregates_exact_commands_and_rx_lengths(self):
        patch = PATCH.read_text()
        self.assertIn("ESP32_HANDOFF_SSI_COMMAND_COUNT 65536u", patch)
        self.assertIn("ESP32_HANDOFF_SSI_RX_LENGTH_BUCKETS 257u", patch)
        self.assertIn("ESP32_HANDOFF_SSI_GAP_BUCKETS 9u", patch)
        self.assertIn("ssi_command_counts[command]", patch)
        self.assertIn("ssi_rx_length_counts[rx_length_bucket]", patch)
        self.assertIn("ssi_gap_counts[gap_bucket]", patch)
        self.assertIn("event=freeze-command", patch)
        self.assertIn("event=freeze-rx-length", patch)
        self.assertIn("event=freeze-timing", patch)
        self.assertIn("event=freeze-gap", patch)
        self.assertIn(
            "ESP32_HANDOFF_SSI_RX_LENGTH_OVERFLOW_BUCKET",
            patch,
        )

    def test_patch_is_diagnostic_and_does_not_change_spi_timing(self):
        patch = PATCH.read_text()
        self.assertNotIn("qemu_clock_notify", patch)
        self.assertNotIn("qemu_clock_warp", patch)
        self.assertNotIn("cpu_exit", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)


if __name__ == "__main__":
    unittest.main()
