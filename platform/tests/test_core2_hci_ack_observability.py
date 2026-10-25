#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tests/uiflow2/core2_native_hci"
RUN = EVIDENCE / (
    "evidence-2026-10-25-core2-concurrent-5x20-ack-observability.json"
)
DEFAULT_RUN = EVIDENCE / (
    "evidence-2026-10-25-core2-ack-observability-default-1x.json"
)
SUMMARY = EVIDENCE / (
    "evidence-2026-10-25-core2-ack-observability-summary.json"
)
TRACE = EVIDENCE / (
    "evidence-2026-10-25-core2-ack-observability-trace-summary.log"
)
SERIAL = EVIDENCE / (
    "evidence-2026-10-25-core2-ack-observability-serial-summary.log"
)
PEER = EVIDENCE / (
    "evidence-2026-10-25-core2-ack-observability-peer-summary.log"
)


class Core2HciAckObservabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.aggregate = json.loads(RUN.read_text())
        cls.default_run = json.loads(DEFAULT_RUN.read_text())
        cls.summary = json.loads(SUMMARY.read_text())
        cls.trace = TRACE.read_text()
        cls.serial = SERIAL.read_text()
        cls.peer = PEER.read_text()

    def test_aggregate_preserves_zero_stagger_failure(self) -> None:
        self.assertEqual(self.aggregate["status"], "FAIL")
        self.assertEqual(self.aggregate["attempts_requested"], 5)
        self.assertEqual(self.aggregate["attempts_passed"], 3)
        self.assertEqual(self.aggregate["attempts_failed"], 2)
        self.assertEqual(self.aggregate["maximum_concurrent_sessions"], 5)
        self.assertEqual(self.aggregate["stagger_seconds"], 0)
        self.assertTrue(
            self.aggregate["input_assets_unchanged_during_run"]
        )
        self.assertEqual(
            self.aggregate["qemu_sha256"],
            "c1c7e448971c4f189784ff7bba00327a29807c24afd49f65cb4aa0cca2e6e9ce",
        )

    def test_first_response_is_delayed_past_guest_ack_timeout(self) -> None:
        window = self.summary["first_ack_window"]
        self.assertEqual(window["reset_commands_before_first_hli"], 3)
        self.assertEqual(window["guest_ack_timeout_count_before_first_hli"], 2)
        self.assertEqual(window["response_to_hli_delay_ns"], 4_506_306_000)
        self.assertTrue(window["first_hli_packet_is_late_reset_complete"])
        self.assertIn(
            "direction=bumble-to-device seq=2 len=7 shown=7 "
            "hex=040e0401030c00",
            self.trace,
        )
        self.assertIn(
            "direction=device-to-hli seq=7 len=7 shown=7 "
            "hex=040e0401030c00",
            self.trace,
        )

    def test_default_profile_path_still_passes(self) -> None:
        self.assertEqual(self.default_run["status"], "PASS")
        self.assertEqual(self.default_run["attempts_requested"], 1)
        self.assertEqual(self.default_run["attempts_passed"], 1)
        self.assertEqual(self.default_run["hold_seconds_per_attempt"], 10)
        self.assertEqual(self.default_run["qemu_sha256"],
                         self.aggregate["qemu_sha256"])
        health = self.default_run["runs"][0]["native_hci_health"]
        self.assertEqual(health["hli-posts"], 45)
        self.assertEqual(health["hli-consumed"], 45)
        self.assertEqual(health["hli-errors"], 0)
        self.assertEqual(
            self.default_run["runs"][0]["failure_diagnostics"]
            ["panic_count"],
            0,
        )

    def test_initial_ack_state_is_empty_before_delay(self) -> None:
        state = self.summary["guest_ack_state"]
        self.assertIsNone(
            state["at_first_hci_rx_ack_check"]["ack_pointer"]
        )
        self.assertEqual(
            state["at_first_hci_rx_ack_check"]
            ["semaphore_count_register"],
            0,
        )
        self.assertIn(
            "name=hci_rx_ack_check",
            self.trace,
        )
        self.assertIn(
            "ctx=0x3ffe2fd0 ack=0x00000000 sem_count_reg=0x00000000",
            self.trace,
        )

    def test_late_reset_complete_breaks_ack_pairing(self) -> None:
        self.assertIn(
            "direction=guest-to-bumble seq=8 len=4 shown=4 hex=01011000",
            self.trace,
        )
        self.assertIn(
            "direction=device-to-hli seq=9 len=7 shown=7 "
            "hex=040e0401030c00",
            self.trace,
        )
        self.assertIn(
            "direction=bumble-to-device seq=10 len=15 shown=15 "
            "hex=040e0c0101100009000009ffff0000",
            self.trace,
        )
        self.assertIn(
            "name=hs_sched_reset t=3548836438295000",
            self.trace,
        )
        self.assertIn(
            "HCI process ack returned 12",
            self.serial,
        )
        self.assertIn(
            "Guru Meditation Error: Core  1 panic'ed (LoadProhibited)",
            self.serial,
        )
        self.assertIn(
            "PC      : 0x402630cc",
            self.serial,
        )
        self.assertIn("BLE_BUMBLE_FAIL", self.peer)

    def test_evidence_files_match_recorded_hashes(self) -> None:
        expected = {
            RUN: (
                "aabb52f19a56e9789b2afcfc5d59b0b9"
                "c0a4748e10065874f7f9a4b31db5cb4b"
            ),
            DEFAULT_RUN: (
                "1f86bc10fa61564bdc963df89a9402a1"
                "b8129be26de07151a7d835f3aaaa8f3c"
            ),
            TRACE: (
                "19c40a078b2c9ba08b063571f2af7251"
                "2abd286eaa8dc7cc1547c7dedcacebbc"
            ),
            SERIAL: (
                "0d38992ab881d19bb12fb8f699dcf241"
                "6f6fbddabce5a42ae708b7ff59de9d9c"
            ),
            PEER: (
                "5e4c647a3f6dc533b594bd369f812783"
                "dafdae327680cf2270f2239d7319b4b2"
            ),
        }
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
