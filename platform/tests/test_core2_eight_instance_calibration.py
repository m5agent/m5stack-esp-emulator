"""Reconcile the eight-instance Core2 throughput calibration."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FAILURE = (
    ROOT
    / "tests/uiflow2/core2_native_hci/"
    "evidence-2026-10-25-core2-concurrent-8x120-threshold-fail.json"
)
EXPECTED_SHA256 = (
    "a1241057e0063de5cdf16564dc1c986291469ea60ff4f17461e3d55d488b2a0a"
)
PASS_FILES = {
    "batch-a": (
        ROOT
        / "tests/uiflow2/core2_native_hci/"
        "evidence-2026-10-25-core2-concurrent-8x120-fixed-icount-pass-a.json",
        "36d52c32d6156b6282c1208a72f12eac50b1d87eacbb85cc9caf2a47ce1f989c",
    ),
    "batch-b": (
        ROOT
        / "tests/uiflow2/core2_native_hci/"
        "evidence-2026-10-25-core2-concurrent-8x120-fixed-icount-pass-b.json",
        "96d12ff41e2def7ab48813b499590a914de6b6da3ed7805b69c1f26d7d971fe7",
    ),
}
EXPECTED_FRAME_SHA256 = (
    "cd2f2033fa92dabd8a60dd4e81bbefd3656b855123e762aef5080188ddf5192f"
)


class Core2EightInstanceCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads(FAILURE.read_text())
        cls.passes = {
            name: json.loads(path.read_text())
            for name, (path, _digest) in PASS_FILES.items()
        }

    def test_failure_is_retained_as_throughput_calibration(self) -> None:
        self.assertEqual(
            hashlib.sha256(FAILURE.read_bytes()).hexdigest(),
            EXPECTED_SHA256,
        )
        evidence = self.evidence
        self.assertEqual(evidence["status"], "FAIL")
        self.assertEqual(evidence["attempts_requested"], 8)
        self.assertEqual(evidence["attempts_passed"], 4)
        self.assertEqual(evidence["attempts_failed"], 4)
        self.assertEqual(evidence["maximum_concurrent_sessions"], 8)
        self.assertTrue(evidence["concurrency_observed"])
        self.assertEqual(evidence["hold_seconds_per_attempt"], 120)

    def test_only_the_psram_sweep_floor_blocks_the_batch(self) -> None:
        for run in self.evidence["runs"]:
            with self.subTest(attempt=run["attempt"]):
                self.assertEqual(run["network_status"], "PASS")
                self.assertEqual(run["qom_nodes"], 31)
                health = run["native_hci_health"]
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-c2h-events"], 36)
                self.assertEqual(health["hli-c2h-acls"], 9)
                self.assertEqual(health["trace-hs-sched-reset"], 0)
                self.assertEqual(health["dropped-packets"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
                self.assertIn(len(run["psram"]["sweeps"]), (11, 12))

        failed = [
            run for run in self.evidence["runs"] if run["status"] == "FAIL"
        ]
        self.assertEqual(len(failed), 4)
        for run in failed:
            self.assertEqual(run["failure_class"], "check_failed")
            self.assertEqual(len(run["psram"]["sweeps"]), 11)
        self.assertEqual(
            self.evidence["checks_per_attempt"]["psram_sustained_stress"],
            "FAIL",
        )

    def test_other_co_resident_checks_remain_green(self) -> None:
        checks = self.evidence["checks_per_attempt"]
        for name in (
            "active_ble_link_during_hold",
            "api_evidence",
            "bounded_tcg_cache",
            "deterministic_icount",
            "evidence_zip",
            "external_nus_gatt",
            "frame_png",
            "hold_stable",
            "native_hci_health",
            "pcap_file_in_evidence_zip",
            "psram_guest_stress",
            "psram_machine_capacity",
            "public_dns_http",
            "wifi_dhcp_http",
        ):
            self.assertEqual(checks[name], "PASS", name)

    def test_calibrated_pass_evidence_is_frozen(self) -> None:
        for name, (path, expected_digest) in PASS_FILES.items():
            with self.subTest(batch=name):
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected_digest,
                )
                evidence = self.passes[name]
                self.assertEqual(evidence["status"], "PASS")
                self.assertEqual(evidence["gate_result"], "PASS")
                self.assertEqual(evidence["attempts_requested"], 8)
                self.assertEqual(evidence["attempts_passed"], 8)
                self.assertEqual(evidence["attempts_failed"], 0)
                self.assertEqual(evidence["maximum_concurrent_sessions"], 8)
                self.assertTrue(evidence["concurrency_observed"])
                self.assertEqual(evidence["stagger_seconds"], 0)
                self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
                self.assertEqual(evidence["psram_gate"], "PASS")
                self.assertTrue(evidence["input_assets_unchanged_during_run"])

    def test_calibrated_eight_instance_leases_remain_fully_green(self) -> None:
        sweep_counts: list[int] = []
        for name, evidence in self.passes.items():
            for run in evidence["runs"]:
                with self.subTest(batch=name, attempt=run["attempt"]):
                    self.assertEqual(run["status"], "PASS")
                    self.assertEqual(run["network_status"], "PASS")
                    self.assertEqual(
                        run["qemu_accelerator"],
                        "tcg,thread=single,tb-size=128",
                    )
                    self.assertEqual(
                        run["qemu_icount"],
                        "shift=5,align=off,sleep=off",
                    )
                    self.assertEqual(run["frame_sha256"], EXPECTED_FRAME_SHA256)
                    self.assertEqual(run["qom_nodes"], 31)
                    self.assertEqual(run["qom_memory_bytes"], 8 << 20)
                    sweeps = run["psram"]["sweeps"]
                    sweep_counts.append(len(sweeps))
                    self.assertEqual(
                        run["psram_requirements"]["minimum_sweeps"],
                        10,
                    )
                    self.assertIn(len(sweeps), (11, 12))
                    self.assertEqual(sweeps, list(range(1, len(sweeps) + 1)))
                    health = run["native_hci_health"]
                    self.assertEqual(health["hli-posts"], 45)
                    self.assertEqual(health["hli-consumed"], 45)
                    self.assertEqual(health["hli-errors"], 0)
                    self.assertEqual(health["hli-c2h-events"], 36)
                    self.assertEqual(health["hli-c2h-acls"], 9)
                    self.assertEqual(health["trace-hs-sched-reset"], 0)
                    self.assertEqual(health["dropped-packets"], 0)
                    self.assertEqual(
                        run["failure_diagnostics"]["panic_count"],
                        0,
                    )

        self.assertEqual(len(sweep_counts), 16)
        self.assertEqual(sum(sweep_counts), 188)
        self.assertEqual(sum(count == 11 for count in sweep_counts), 4)
        self.assertEqual(sum(count == 12 for count in sweep_counts), 12)

    def test_calibration_changes_only_the_runner_floor(self) -> None:
        failure_tools = self.evidence["tool_hashes"]
        pass_tools = self.passes["batch-a"]["tool_hashes"]
        self.assertNotEqual(failure_tools["runner"], pass_tools["runner"])
        for name in (
            "device_service",
            "qemu_accel",
            "ble_runtime_limits",
            "ble_probe",
            "network_policy",
            "unified_http_guestfwd",
        ):
            self.assertEqual(failure_tools[name], pass_tools[name])
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for evidence in self.passes.values()
                for run in evidence["runs"]
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
