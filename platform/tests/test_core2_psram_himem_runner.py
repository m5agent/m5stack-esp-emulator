#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/firmware/core2_psram_himem/run_test.py"
SPEC = importlib.util.spec_from_file_location("core2_psram_himem_runner", RUNNER)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class Core2PsramHimemRunnerTests(unittest.TestCase):
    def test_parses_himem_markers_and_qom_capacity(self) -> None:
        serial = "\n".join(
            (
                "CORE2_HIMEM_PHYS_BYTES 4456448",
                "CORE2_HIMEM_RESERVED_BYTES 262144",
                "CORE2_HIMEM_PHYS_START",
                "CORE2_HIMEM_BANK_PASS",
            )
        )
        parsed = runner.parse_serial(serial)
        self.assertEqual(parsed["physical_bytes"], 4_456_448)
        self.assertEqual(parsed["reserved_bytes"], 262_144)
        self.assertEqual(parsed["bank_pass_count"], 1)
        self.assertEqual(parsed["mismatch_count"], 0)
        self.assertEqual(parsed["failure_markers"], [])
        self.assertEqual(
            runner.qom_memory_bytes(
                {"nodes": {"memory": {"value": {"size": 8 << 20}}}}
            ),
            8 << 20,
        )

    def test_detects_bank_mismatch_and_failure_markers(self) -> None:
        serial = "\n".join(
            (
                "CORE2_HIMEM_PHYS_BYTES 4456448",
                "CORE2_HIMEM_RESERVED_BYTES 262144",
                "CORE2_HIMEM_MISMATCH block=0 offset=0 actual=00 expected=5a",
                "CORE2_HIMEM_FAIL ESP_FAIL",
            )
        )
        parsed = runner.parse_serial(serial)
        self.assertEqual(parsed["mismatch_count"], 1)
        self.assertEqual(len(parsed["failure_markers"]), 1)

    def test_committed_evidence_passes_three_independent_leases(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/core2_psram_himem/"
                "evidence-2026-10-25-core2-himem-bank-switch-3x.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["validation"], "virtual-device validation")
        self.assertEqual(evidence["attempts_requested"], 3)
        self.assertEqual(evidence["attempts_completed"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(len(evidence["runs"]), 3)
        self.assertEqual(
            len({run["session_id_sha256"] for run in evidence["runs"]}),
            3,
        )
        for run in evidence["runs"]:
            self.assertEqual(run["status"], "PASS")
            self.assertEqual(run["physical_himem_bytes"], 4_456_448)
            self.assertEqual(run["reserved_mmu_bytes"], 262_144)
            self.assertEqual(run["machine_memory_bytes"], 8 << 20)
            self.assertTrue(all(run["checks"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
