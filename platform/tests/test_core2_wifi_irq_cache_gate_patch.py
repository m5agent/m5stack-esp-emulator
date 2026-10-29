#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0092-esp32-wifi-irq-cache-gate.patch"
)


class Core2WifiIrqCacheGatePatchTests(unittest.TestCase):
    def test_wifi_level_is_held_until_instruction_cache_is_ready(self):
        patch = PATCH.read_text()
        self.assertIn(
            "cs->dport->cache_ready[cs->core_id],\n"
            "+        iram0_enabled",
            patch,
        )
        self.assertIn(
            "s->cache_ready[cpu]\n"
            "+                        || !esp32_intmatrix_cache_sensitive(input)",
            patch,
        )
        self.assertIn(
            "return input == ETS_WIFI_MAC_INTR_SOURCE;",
            patch,
        )
        self.assertIn(
            "s->cache_ready[cpu] = !!level;",
            patch,
        )
        self.assertIn(
            "esp32_intmatrix_update_outputs(s);",
            patch,
        )

    def test_cache_gate_does_not_mask_handoff_or_cache_errors(self):
        patch = PATCH.read_text()
        forbidden = (
            "ETS_FROM_CPU_INTR0_SOURCE",
            "ETS_FROM_CPU_INTR1_SOURCE",
            "ETS_FROM_CPU_INTR2_SOURCE",
            "ETS_FROM_CPU_INTR3_SOURCE",
            "ETS_CACHE_IA_INTR_SOURCE",
            "M5SW_DISABLE_WDT",
            "timer_mod_anticipate_ns",
            "qemu_clock_warp",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, patch)

    def test_patch_is_ordered_after_existing_wifi_dependencies(self):
        bootstrap = (
            ROOT / "scripts/bootstrap-unit-runtime.py"
        ).read_text()
        current = bootstrap.index(
            "0064-esp32-intmatrix-pending-irq-remap.patch"
        )
        gate = bootstrap.index(
            "0092-esp32-wifi-irq-cache-gate.patch"
        )
        self.assertLess(current, gate)


if __name__ == "__main__":
    unittest.main()
