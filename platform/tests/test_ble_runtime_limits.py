#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from ble_runtime_limits import (
    BLE_PEER_MAX_SCAN_TIMEOUT_SECONDS,
    BLE_PEER_MIN_SCAN_TIMEOUT_SECONDS,
    BLE_PEER_SESSION_TIMEOUT_MARGIN_SECONDS,
    BLE_RECONNECT_CYCLE_SECONDS,
    BLE_RECONNECT_STARTUP_SECONDS,
    MAX_BLE_HOLD_SECONDS,
    ble_peer_scan_timeout_seconds,
    reconnect_workload_timeout_seconds,
)


class BleRuntimeLimitsTests(unittest.TestCase):
    def test_ble_peer_scan_timeout_follows_session_readiness(self) -> None:
        self.assertEqual(
            ble_peer_scan_timeout_seconds(30),
            BLE_PEER_MIN_SCAN_TIMEOUT_SECONDS,
        )
        self.assertEqual(
            ble_peer_scan_timeout_seconds(90),
            90 - BLE_PEER_SESSION_TIMEOUT_MARGIN_SECONDS,
        )
        self.assertEqual(
            ble_peer_scan_timeout_seconds(300),
            BLE_PEER_MAX_SCAN_TIMEOUT_SECONDS,
        )

    def test_ble_peer_scan_timeout_rejects_invalid_readiness(self) -> None:
        for value in (0, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ble_peer_scan_timeout_seconds(value)
        for value in (True, "90"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                ble_peer_scan_timeout_seconds(value)  # type: ignore[arg-type]

    def test_reconnect_timeout_scales_with_workload(self) -> None:
        one_cycle = reconnect_workload_timeout_seconds(1, 2)
        maximum = reconnect_workload_timeout_seconds(121, 2)

        self.assertEqual(
            one_cycle,
            BLE_RECONNECT_STARTUP_SECONDS
            + BLE_RECONNECT_CYCLE_SECONDS
            + 2,
        )
        self.assertGreater(maximum, 900)
        self.assertGreater(maximum, one_cycle)

    def test_reconnect_timeout_accounts_for_delay_and_stays_bounded(self) -> None:
        no_delay = reconnect_workload_timeout_seconds(121, 0)
        delayed = reconnect_workload_timeout_seconds(121, 30)

        self.assertGreater(delayed, no_delay)
        self.assertLessEqual(delayed, MAX_BLE_HOLD_SECONDS)

    def test_reconnect_timeout_rejects_invalid_workloads(self) -> None:
        for cycles, delay in ((0, 2), (122, 2), (1, -1), (1, 31)):
            with (
                self.subTest(cycles=cycles, delay=delay),
                self.assertRaises(ValueError),
            ):
                reconnect_workload_timeout_seconds(cycles, delay)
        for cycles, delay in ((True, 2), (1.5, 2), (1, "2")):
            with (
                self.subTest(cycles=cycles, delay=delay),
                self.assertRaises(TypeError),
            ):
                reconnect_workload_timeout_seconds(cycles, delay)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
