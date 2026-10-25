"""Validate the committed fixed-icount Core2 five-instance evidence."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = ROOT / "tests/uiflow2/core2_native_hci"
EVIDENCE_FILES = {
    "batch-a": (
        EVIDENCE_ROOT
        / "evidence-2026-10-25-core2-concurrent-5x120-"
        "fixed-icount-blefirst-pass-a.json",
        "87dd71664fe4a9a7035051572a934254505608ce28313b7d5f0ff45fa857670a",
    ),
    "batch-b": (
        EVIDENCE_ROOT
        / "evidence-2026-10-25-core2-concurrent-5x120-"
        "fixed-icount-blefirst-pass-b.json",
        "8f9a913af3af0b4c43326a363dec0d5766df10379f7bdd8f27d1bf6a48508e9f",
    ),
}
EXPECTED_ICOUNT = "shift=5,align=off,sleep=off"
EXPECTED_FRAME_SHA256 = (
    "cd2f2033fa92dabd8a60dd4e81bbefd3656b855123e762aef5080188ddf5192f"
)


class Core2FixedIcountConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = {
            name: json.loads(path.read_text())
            for name, (path, _digest) in EVIDENCE_FILES.items()
        }

    @staticmethod
    def assert_pass_checks(value: dict[str, Any]) -> None:
        for key in (
            "active_ble_link_during_hold",
            "api_evidence",
            "ble_cycle_count",
            "bounded_tcg_cache",
            "deterministic_icount",
            "evidence_zip",
            "external_nus_gatt",
            "frame_png",
            "hold_stable",
            "manifest_session_binding",
            "native_hci_health",
            "pcap_file_in_evidence_zip",
            "psram_guest_stress",
            "psram_machine_capacity",
            "psram_sustained_stress",
            "public_dns_http",
            "wifi_dhcp_http",
        ):
            if key in value:
                assert value[key] == "PASS", key

    def test_evidence_files_are_immutable_and_artifact_bound(self) -> None:
        for name, (path, expected_digest) in EVIDENCE_FILES.items():
            with self.subTest(batch=name):
                self.assertTrue(path.is_file())
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected_digest,
                )
                evidence = self.evidence[name]
                self.assertEqual(evidence["schema_version"], 1)
                self.assertEqual(evidence["validation"], "virtual-device validation")
                self.assertEqual(evidence["status"], "PASS")
                self.assertEqual(evidence["gate_result"], "PASS")
                self.assertEqual(evidence["runtime"], "qemu-unified")
                self.assertEqual(evidence["profile"], "core2-native-hci")
                self.assertTrue(evidence["psram_required"])
                self.assertEqual(evidence["psram_gate"], "PASS")
                self.assertTrue(evidence["input_assets_unchanged_during_run"])
                self.assertEqual(evidence["input_asset_drift"], {})
                self.assertIsNone(evidence["first_failure"])
                self.assertEqual(evidence["attempts_requested"], 5)
                self.assertEqual(evidence["attempts_completed"], 5)
                self.assertEqual(evidence["attempts_passed"], 5)
                self.assertEqual(evidence["attempts_failed"], 0)
                self.assertEqual(evidence["maximum_concurrent_sessions"], 5)
                self.assertEqual(evidence["concurrency_requested"], 5)
                self.assertTrue(evidence["concurrency_observed"])
                self.assertEqual(evidence["stagger_seconds"], 0)
                self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
                self.assertEqual(len(evidence["runs"]), 5)
                self.assert_pass_checks(evidence["checks_per_attempt"])

    def test_each_lease_exercises_the_unified_data_plane(self) -> None:
        for name, evidence in self.evidence.items():
            for run in evidence["runs"]:
                with self.subTest(batch=name, attempt=run["attempt"]):
                    self.assertEqual(run["status"], "PASS")
                    self.assertIsNone(run["failure_class"])
                    self.assertEqual(run["network_status"], "PASS")
                    self.assertEqual(
                        run["qemu_accelerator"],
                        "tcg,thread=single,tb-size=128",
                    )
                    self.assertEqual(run["qemu_icount"], EXPECTED_ICOUNT)
                    self.assertEqual(
                        run["frame_sha256"],
                        EXPECTED_FRAME_SHA256,
                    )
                    self.assertGreater(run["frame_bytes"], 0)
                    self.assertEqual(run["qom_nodes"], 31)
                    self.assertEqual(run["qom_memory_bytes"], 8 << 20)
                    self.assertGreater(run["pcap_bytes"], 0)
                    self.assertGreater(run["evidence_bytes"], 0)
                    self.assertGreater(
                        run["session_finished_epoch"],
                        run["session_started_epoch"],
                    )

                    health = run["native_hci_health"]
                    self.assertEqual(health["hli-valid"], 1)
                    self.assertEqual(health["hli-posts"], 45)
                    self.assertEqual(health["hli-consumed"], 45)
                    self.assertEqual(health["hli-errors"], 0)
                    self.assertEqual(health["hli-c2h-events"], 36)
                    self.assertEqual(health["hli-c2h-acls"], 9)
                    self.assertEqual(health["hli-fast-path-events"], 36)
                    self.assertEqual(health["hli-fast-path-acls"], 9)
                    self.assertEqual(health["hli-event-prealloc-depth"], 8)
                    self.assertEqual(health["hli-acl-prealloc-depth"], 4)
                    self.assertEqual(health["hli-prealloc-failures"], 0)
                    self.assertEqual(health["trace-hs-sched-reset"], 0)
                    self.assertEqual(health["dropped-packets"], 0)
                    self.assertEqual(health["tx-queue-depth"], 0)
                    self.assertEqual(health["last-error"], 0)
                    self.assertEqual(health["peer-closed"], 0)

                    diagnostics = run["failure_diagnostics"]
                    self.assertEqual(diagnostics["panic_count"], 0)
                    self.assertIsNone(diagnostics["first_panic"])
                    self.assertIsNone(diagnostics["last_panic"])
                    self.assertFalse(diagnostics["peer_gatt_timeout"])
                    self.assertIsNone(diagnostics["session_read_error"])
                    self.assertIsNone(diagnostics["cleanup_error"])

    def test_sustained_psram_and_network_rechecks_stay_live(self) -> None:
        sweep_counts: list[int] = []
        for name, evidence in self.evidence.items():
            for run in evidence["runs"]:
                with self.subTest(batch=name, attempt=run["attempt"]):
                    requirements = run["psram_requirements"]
                    psram = run["psram"]
                    sweeps = psram["sweeps"]
                    sweep_counts.append(len(sweeps))

                    self.assertEqual(requirements["minimum_sweeps"], 12)
                    self.assertGreaterEqual(len(sweeps), 12)
                    self.assertLessEqual(len(sweeps), 15)
                    self.assertEqual(sweeps, list(range(1, len(sweeps) + 1)))
                    self.assertEqual(psram["requested_bytes"], 1 << 20)
                    self.assertEqual(
                        psram["verified_bytes"],
                        len(sweeps) * (1 << 20),
                    )
                    self.assertEqual(psram["init_pass_count"], 1)
                    self.assertEqual(psram["stress_pass_count"], 1)
                    self.assertGreaterEqual(
                        len(psram["heartbeats"]),
                        requirements["minimum_heartbeats"],
                    )
                    self.assertGreaterEqual(
                        psram["http_recheck_pass_count"],
                        requirements["minimum_http_rechecks"],
                    )
                    self.assertGreaterEqual(
                        psram["public_recheck_pass_count"],
                        requirements["minimum_public_rechecks"],
                    )
                    self.assertEqual(psram["error_markers"], [])

        self.assertEqual(sum(sweep_counts), 147)
        self.assertEqual(sum(1 for count in sweep_counts if count == 14), 3)
        self.assertEqual(sum(1 for count in sweep_counts if count == 15), 7)

    def test_batches_use_the_same_frozen_inputs(self) -> None:
        batches = list(self.evidence.values())
        for key in ("qemu_sha256", "elf_sha256"):
            self.assertEqual(
                len({batch[key] for batch in batches}),
                1,
            )
        self.assertEqual(
            len(
                {
                    batch["firmware"]["sha256"]
                    for batch in batches
                }
            ),
            1,
        )
        self.assertEqual(
            len({json.dumps(batch["tool_hashes"], sort_keys=True) for batch in batches}),
            1,
        )


if __name__ == "__main__":
    unittest.main()
