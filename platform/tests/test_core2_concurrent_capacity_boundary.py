"""Freeze the Core2 concurrent capacity boundary and recheck policy."""
from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT
    / "docs/evidence/2026-10-30-core2-concurrent-capacity-boundary/"
    "summary.json"
)
GUEST = ROOT / "tests/uiflow2/unified_core2/main.py"
RUNNER = ROOT / "tests/uiflow2/core2_native_hci/run_service_5x.py"


class Core2ConcurrentCapacityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(EVIDENCE.read_text())

    def test_nine_instance_capacity_is_not_admitted(self) -> None:
        capacity = self.evidence["capacity"]
        self.assertEqual(capacity["default_max_sessions"], 12)
        self.assertEqual(capacity["default_max_per_device"], 8)
        self.assertFalse(capacity["nine_instance_admitted"])
        self.assertEqual(capacity["nine_instance_attempts"], 3)
        self.assertEqual(capacity["nine_instance_passes"], 2)
        self.assertEqual(capacity["nine_instance_failures"], 1)

    def test_nine_instance_failure_is_bound_to_the_ack_crash(self) -> None:
        failure = self.evidence["raw_evidence"]["nine_failure"]
        self.assertEqual(failure["status"], "FAIL")
        self.assertEqual(failure["attempts_passed"], 8)
        self.assertEqual(failure["attempts_failed"], 1)
        self.assertEqual(failure["maximum_concurrent_sessions"], 9)
        self.assertEqual(failure["failed_attempt"], "attempt-8")
        self.assertEqual(
            failure["first_panic"]["symbol"],
            "ble_hs_hci_process_ack",
        )
        self.assertEqual(failure["first_panic"]["pc"], "0x402630cc")
        self.assertFalse(failure["peer_gatt_timeout"])

    def test_current_runtime_has_two_independent_two_instance_passes(
        self,
    ) -> None:
        for name in ("current_two_pass_a", "current_two_pass_b"):
            with self.subTest(batch=name):
                batch = self.evidence["raw_evidence"][name]
                self.assertEqual(batch["status"], "PASS")
                self.assertEqual(batch["attempts_passed"], 2)
                self.assertEqual(batch["maximum_concurrent_sessions"], 2)
                self.assertEqual(batch["stagger_seconds"], 0)
                self.assertEqual(batch["hold_seconds"], 60)

        aggregate = self.evidence["current_two_instance"]
        self.assertEqual(aggregate["runs"], 4)
        self.assertEqual(aggregate["passes"], 4)
        self.assertEqual(aggregate["failures"], 0)
        self.assertEqual(aggregate["psram_error_markers"], 0)
        self.assertEqual(aggregate["network_recheck_error_markers"], 0)
        self.assertEqual(aggregate["hli_posts"], 45)
        self.assertEqual(aggregate["hli_consumed"], 45)
        self.assertEqual(aggregate["hli_errors"], 0)
        self.assertEqual(aggregate["panic_count"], 0)
        self.assertEqual(aggregate["qom_memory_bytes"], 8 << 20)

    def test_guest_has_bounded_network_recheck_retry(self) -> None:
        guest = GUEST.read_text()
        self.assertIn("NETWORK_RECHECK_ATTEMPTS = 3", guest)
        self.assertIn("NETWORK_RETRY_DELAY_MS = 1000", guest)
        self.assertIn("def run_network_recheck(", guest)
        self.assertIn(
            "UNIFIED_CORE2_HTTP_RECHECK_RETRY",
            guest,
        )
        self.assertIn(
            "UNIFIED_CORE2_PUBLIC_RECHECK_RETRY",
            guest,
        )

    def test_psram_and_network_errors_have_distinct_evidence_fields(
        self,
    ) -> None:
        runner = RUNNER.read_text()
        self.assertIn('"error_markers": [', runner)
        self.assertIn('"network_recheck_error_markers": [', runner)
        self.assertIn('"network_recheck_retry_markers": [', runner)


if __name__ == "__main__":
    unittest.main()
