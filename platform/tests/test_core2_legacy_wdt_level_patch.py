#!/usr/bin/env python3
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0095-esp32-legacy-wdt-level-delivery.patch"
)


class Core2LegacyWdtLevelPatchTests(unittest.TestCase):
    def test_only_wdt_level_uses_the_independent_level_gate(self):
        patch = PATCH.read_text()
        self.assertIn(
            "if (it == TIMG_WDT_INT && s->wdt.level_int_en) {\n"
            "+        pending = s->int_raw & (1 << it);",
            patch,
        )
        self.assertIn(
            "+            esp32_timg_int_update(s);",
            patch,
        )
        self.assertIn(
            '0, (s->int_ena & mask) ? "wdt-raise" : "wdt-level",',
            patch,
        )

    def test_masked_status_and_other_timer_sources_keep_int_ena(self):
        patch = PATCH.read_text()
        self.assertNotIn("r = s->int_raw;", patch)
        self.assertNotIn("case A_TIMG_INT_ST:", patch)
        self.assertNotIn("pending = true", patch)
        self.assertIn(
            "timer-group sources retain their existing INT_ENA mask",
            patch,
        )
        self.assertIn("WDT edge path is unchanged", patch)

    def test_patch_does_not_bypass_watchdog_or_clock_semantics(self):
        patch = PATCH.read_text()
        forbidden = (
            "M5SW_DISABLE_WDT",
            "wdt_disable",
            "getenv(",
            "timer_mod_anticipate_ns",
            "qemu_clock_warp",
            "timeout =",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, patch)

    def test_patch_is_last_in_the_runtime_bootstrap_stack(self):
        bootstrap = (
            ROOT / "scripts/bootstrap-unit-runtime.py"
        ).read_text()
        current = bootstrap.index(
            "0094-esp32-classic-wifi-station-data.patch"
        )
        legacy_wdt = bootstrap.index(
            "0095-esp32-legacy-wdt-level-delivery.patch"
        )
        self.assertLess(current, legacy_wdt)

    def test_evidence_binds_three_default_budget_normal_wdt_runs(self):
        evidence = json.loads(
            (
                ROOT
                / "docs/evidence/2026-10-30-core2-legacy-wdt-level-delivery/"
                "summary.json"
            ).read_text()
        )
        self.assertEqual(evidence["attempts"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertEqual(
            evidence["patch"]["sha256"],
            "df008a1f34324c1b4b0d7bc4640f03bb5f9b42b109cfedadfee0b31631411894",
        )
        self.assertEqual(
            evidence["qemu_sha256"],
            "001a938503e7b1d813f388022d849c24bab4f5298602211f70042a5184fcb62d",
        )
        self.assertEqual(evidence["runtime"]["per_vcpu_budget_ns"], 10000)
        self.assertFalse(evidence["wdt_trace"]["stage_one_reset"])
        self.assertTrue(
            all(
                run["observed_virtual_time_ns_max"] > 15_549_776_528
                for run in evidence["runs"]
            )
        )


if __name__ == "__main__":
    unittest.main()
