#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0074-esp32-spi-panel-dma-dedup.patch"
)


class Core2SpiPanelDmaDedupPatchTests(unittest.TestCase):
    def test_patch_skips_cpu_replay_after_panel_dma(self) -> None:
        patch = PATCH.read_text()
        self.assertIn("bool m5_panel_dma_transferred", patch)
        self.assertIn(
            "esp32_spi_m5_dma_panel(s, value);\n"
            "+            s->m5_panel_dma_transferred = true;",
            patch,
        )
        self.assertIn(
            "if (s->m5_panel && !s->m5_panel_dma_transferred)",
            patch,
        )
        self.assertIn(
            "+    s->m5_panel_dma_transferred = false;",
            patch,
        )

    def test_patch_adds_ramwr_byte_accounting(self) -> None:
        patch = PATCH.read_text()
        self.assertIn("M5SW_PANEL_RAMWR_TRACE", patch)
        self.assertIn("[m5panel-ramwr]", patch)
        self.assertIn("expected=%\" PRIu64 \" written=%\" PRIu64", patch)
        self.assertIn("m5_panel_ramwr_bytes = 0", patch)
        self.assertIn("m5_panel_ramwr_bytes++", patch)

    def test_patch_does_not_change_scheduler_or_watchdog(self) -> None:
        patch = PATCH.read_text()
        self.assertNotIn("qemu_clock_notify", patch)
        self.assertNotIn("qemu_clock_warp", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)


if __name__ == "__main__":
    unittest.main()
