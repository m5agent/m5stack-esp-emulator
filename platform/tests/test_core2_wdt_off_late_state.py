#!/usr/bin/env python3
from __future__ import annotations

import json

from _docs_contract_support import DocsContractBase, ROOT

EVIDENCE = (
    ROOT
    / "tests/firmware/core2_handoff_trace/"
    "evidence-2026-10-26-core2-wdt-off-late-state.json"
)
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0041-esp32-handoff-register-stack-dump.patch"
)


class Core2WdtOffLateStateTests(DocsContractBase):
    def test_wdt_off_late_state_is_bounded_and_artifact_bound(self) -> None:
        evidence = json.loads(EVIDENCE.read_text())
        self.assertEqual(evidence["kind"], "core2-wdt-off-late-state")
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(evidence["runtime"]["wdt_disabled"])
        self.assertEqual(
            evidence["runtime"]["qemu_binary_sha256"],
            "b7ed19e7502e2a04ef48287c3622061ee640077bacc469e571ece5b6f802c1ea",
        )
        self.assertEqual(len(evidence["snapshots"]), 2)
        early, late = evidence["snapshots"]
        self.assertEqual(early["pause_target_ns"], 45_000_000_000)
        self.assertEqual(late["pause_target_ns"], 120_000_000_000)

        for snapshot in (early, late):
            self.assertEqual(snapshot["cpu"]["0"]["pc"], "0x4026306e")
            self.assertEqual(snapshot["cpu"]["0"]["state_flags"], 1)
            self.assertEqual(snapshot["cpu"]["1"]["pc"], "0x40100049")
            self.assertEqual(snapshot["cpu"]["1"]["state_flags"], 2)
            self.assertTrue(snapshot["serial"]["has_setup_text"] is False)
            self.assertTrue(snapshot["serial"]["has_repl_prompt"] is False)
            self.assertEqual(
                snapshot["cpu1_objects"]["a2"]["offset24"],
                "0x00000001",
            )
            self.assertEqual(
                snapshot["cpu1_objects"]["a3"]["offset24"],
                "0x00000001",
            )
            self.assertEqual(
                snapshot["cpu1_objects"]["a10"]["offset28"],
                "0x00000000",
            )

        self.assertEqual(
            early["flash_handoff"],
            {
                "cache_sync_calls": 49848,
                "changed_pages": 45847,
                "state_updates": 49265,
                "last_cache_sync_ns": 43914275000,
            },
        )
        self.assertEqual(
            late["flash_handoff"],
            {
                "cache_sync_calls": 49848,
                "changed_pages": 45847,
                "state_updates": 49265,
                "last_cache_sync_ns": 43987842000,
            },
        )
        self.assertEqual(
            early["ssi"]["transactions"],
            late["ssi"]["transactions"],
        )
        self.assertEqual(
            early["ssi"]["rx_bytes"],
            late["ssi"]["rx_bytes"],
        )
        self.assertLess(late["flash_handoff"]["last_cache_sync_ns"], 45_000_000_000)
        self.assertLess(late["ssi"]["last_event_ns"], 45_000_000_000)
        self.assertGreater(late["crosscore_writes"], early["crosscore_writes"])
        self.assertEqual(
            evidence["classification"]["wdt_disabled_diagnostic"],
            "FLASH_WORK_COMPLETED_LATE_LOOP",
        )
        self.assertEqual(
            evidence["classification"]["runtime_03"],
            "OPEN",
        )

        patch = PATCH.read_text()
        self.assertIn("M5SW_ESP32_HANDOFF_STACK_WORDS", patch)
        self.assertIn("event=freeze-reg", patch)
        self.assertIn("event=freeze-point", patch)
        self.assertIn("event=stack-word", patch)
        self.assertIn("xtensa_cpu_get_areg", patch)


if __name__ == "__main__":
    import unittest

    unittest.main()
