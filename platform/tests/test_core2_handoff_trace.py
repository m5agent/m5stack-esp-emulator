#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-handoff-timeline.json"
)
PC_SYMBOLIZATION = (
    ROOT
    / "tests/firmware/core2_handoff_trace/"
    "pc-symbolization-2026-10-26-core2-handoff.json"
)


class Core2HandoffTraceTests(unittest.TestCase):
    def test_repeated_normal_watchdog_runs_share_feed_gap(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        run_list = {
            "normal_watchdog": evidence["normal_watchdog"]["trace"][
                "wdt_timeouts"
            ],
            "normal_watchdog_replicate": evidence[
                "normal_watchdog_replicate"
            ]["trace"]["wdt_timeouts"],
        }
        for run_name, timeouts in run_list.items():
            tg1_stage0 = next(
                item
                for item in timeouts
                if item["timer_group"] == 1 and item["stage"] == 0
            )
            self.assertEqual(tg1_stage0["feed_gap_ns"], 800_000_000)
            self.assertGreater(tg1_stage0["feed_count"], 10_000)
            self.assertEqual(tg1_stage0["mode"], 1)
            self.assertGreater(
                tg1_stage0["now_ns"],
                tg1_stage0["last_feed_ns"],
            )
            tg1_stage1 = next(
                (
                    item
                    for item in timeouts
                    if item["timer_group"] == 1 and item["stage"] == 1
                ),
                None,
            )
            if run_name == "normal_watchdog":
                self.assertIsNotNone(tg1_stage1)
                self.assertEqual(tg1_stage1["feed_gap_ns"], 2_400_000_000)
                self.assertEqual(tg1_stage1["mode"], 3)
            else:
                self.assertIsNone(tg1_stage1)
        self.assertEqual(
            evidence["normal_watchdog"]["serial"]["sha256"],
            "e996276519b4f8882739ff1c494dcecba313c99278857a53a984c1c9986a1b62",
        )
        self.assertTrue(
            evidence["normal_watchdog"]["serial"]["has_micropython_banner"]
        )
        self.assertFalse(
            evidence["normal_watchdog"]["serial"]["has_repl_prompt"]
        )

    def test_wdt_disabled_sampling_matches_trace_off_serial(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        disabled = evidence["wdt_disabled"]
        self.assertEqual(evidence["classification"]["wdt_disabled"], "BANNER_ONLY")
        self.assertTrue(disabled["serial_matches_trace_off"])
        self.assertTrue(disabled["serial"]["has_micropython_banner"])
        self.assertFalse(disabled["serial"]["has_repl_prompt"])
        self.assertEqual(disabled["trace"]["wdt_timeouts"], [])
        self.assertFalse(disabled["trace"]["has_post_boot_reset_event"])
        self.assertGreater(
            disabled["trace"]["last_event_ns"],
            14_000_000_000,
        )

    def test_trace_patch_and_summarizer_contract(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        history = (
            ROOT / "docs/core2-cache-panic-investigation.md"
        ).read_text()
        for run_name in ("normal_watchdog", "normal_watchdog_replicate"):
            tg1_stage0 = next(
                item
                for item in evidence[run_name]["trace"]["wdt_timeouts"]
                if item["timer_group"] == 1 and item["stage"] == 0
            )
            self.assertIn(
                f"{tg1_stage0['feed_count']:,}",
                history,
            )
        patch_path = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0037-esp32-handoff-trace.patch"
        )
        patch = patch_path.read_text()
        patch_readme = (
            ROOT / "patches/qemu-m5stack-peripherals/README.md"
        ).read_text()
        normalized_patch_readme = " ".join(
            patch_readme.replace("**", "").split()
        )
        self.assertIn("M5SW_ESP32_HANDOFF_TRACE", patch)
        self.assertIn("M5SW_ESP32_HANDOFF_TRACE_SAMPLE", patch)
        self.assertIn("esp32_handoff_trace_event_always", patch)
        self.assertIn("wdt-timeout-gap", patch)
        self.assertIn("receive-data", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)
        self.assertIn(
            "not a validated raw-upstream bootstrap recipe",
            normalized_patch_readme,
        )
        self.assertIn("predecessor-bound", patch_readme)
        self.assertEqual(
            evidence["runtime"]["trace_patch_sha256"],
            "4ef1cbaa60373132c5f2e375a5a39c590007b133f1359a7e3e76e22375e7bf5a",
        )
        self.assertEqual(
            evidence["regression"]["core2_group"]["cases_passed"],
            6,
        )
        self.assertEqual(
            evidence["regression"]["full_uiflow2_matrix"]["cases_passed"],
            67,
        )
        self.assertEqual(
            evidence["regression"]["full_uiflow2_matrix"]["checks_passed"],
            274,
        )
        self.assertFalse(
            evidence["regression"]["full_uiflow2_matrix"]["retry_used"]
        )
        suite = evidence["validation_suite"]
        self.assertEqual(suite["platform_unittest"]["passed"], 504)
        self.assertEqual(suite["docs_contract"]["passed"], 41)
        self.assertEqual(suite["qemu_profile_contract"]["passed"], 19)
        self.assertEqual(
            suite["patch_predecessor_forward_reverse_check"],
            "PASS",
        )
        self.assertIn("0036 applied", suite["patch_baseline"])

        pc_control = evidence["pc_sampling_control"]
        self.assertEqual(
            evidence["classification"]["pc_sampling_control"],
            "PERTURBED_EARLIER_RESET_SAME_800_MS_GAP",
        )
        self.assertEqual(
            pc_control["trace"]["wdt_timeouts"][0]["feed_gap_ns"],
            800_000_000,
        )
        window = pc_control["trace"]["pc_final_feed_to_timeout_window"]
        self.assertEqual(window["samples"], 800)
        self.assertEqual(
            set(window["cpu_pc_pairs"]),
            {
                "0x400843ac:0x4008649c",
                "0x400843ac:0x4008649e",
                "0x400843af:0x4008649c",
                "0x400843af:0x4008649e",
                "0x400843b1:0x4008649c",
                "0x400843b1:0x4008649e",
            },
        )
        self.assertEqual(
            window["other_trace_events"],
            {
                "timg:wdt-int-raised": 1,
                "timg:wdt-timeout": 1,
                "timg:wdt-timeout-gap": 1,
            },
        )
        self.assertFalse(
            pc_control["symbolization"]["artifact_bound_to_public_image"]
        )
        self.assertEqual(
            pc_control["symbolization"],
            json.loads(PC_SYMBOLIZATION.read_text()),
        )

        summary_path = (
            ROOT / "tests/firmware/core2_handoff_trace/summarize.py"
        )
        spec = importlib.util.spec_from_file_location(
            "core2_handoff_summarize",
            summary_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            module.classify_pc_sampling_control(
                evidence["normal_watchdog"]["trace"],
                pc_control["trace"],
            ),
            "PERTURBED_EARLIER_RESET_SAME_800_MS_GAP",
        )
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.stderr"
            serial = Path(tmp) / "serial.log"
            trace.write_text(
                "[esp32-handoff] now=7 cpu=1 pc=40001234 "
                "component=timg event=wdt-timeout a=1 b=0 c=1 d=5\n"
                "[esp32-handoff] now=7 cpu=1 pc=40001234 "
                "component=timg event=wdt-timeout-gap a=1 b=0 "
                "c=2 d=3\n"
            )
            serial.write_text(
                " _   _(_)/ _| | _____\n"
            )
            parsed = module.summarize_trace(trace)
            summary = module.serial_summary(serial)
            normal_trace = {
                "wdt_timeouts": parsed["wdt_timeouts"],
                "last_event_ns": 10,
            }
            pc_trace = {
                "wdt_timeouts": parsed["wdt_timeouts"],
                "last_event_ns": 7,
            }
            classification = module.classify_pc_sampling_control(
                normal_trace,
                pc_trace,
            )
        self.assertEqual(parsed["trace_event_count"], 2)
        self.assertEqual(parsed["wdt_timeouts"][0]["feed_gap_ns"], 2)
        self.assertTrue(summary["has_micropython_banner"])
        self.assertEqual(
            classification,
            "PC_SAMPLING_FEED_GAP_CHANGED",
        )


if __name__ == "__main__":
    unittest.main()
