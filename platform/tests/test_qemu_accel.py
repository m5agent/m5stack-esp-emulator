"""Contract tests for the shared Core2 QEMU accelerator arguments."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

import qemu_accel

ROOT = Path(__file__).resolve().parents[2]
QEMU_PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0090-icount-percpu-fairness-cap.patch"
)
BUDGET_SUMMARY = (
    ROOT
    / "docs/evidence/2026-10-29-core2-icount-percpu-budget/summary.json"
)


class Core2QemuAccelTests(unittest.TestCase):
    def core2_args_with(self, value: str | None) -> list[str]:
        environment = os.environ.copy()
        environment.pop(qemu_accel.CORE2_ICOUNT_SHIFT_ENV, None)
        environment.pop(qemu_accel.CORE2_ICOUNT_MAX_PERCPU_NS_ENV, None)
        environment.pop(qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV, None)
        if value is not None:
            environment[qemu_accel.CORE2_ICOUNT_SHIFT_ENV] = value
        with mock.patch.dict(os.environ, environment, clear=True):
            return qemu_accel.core2_accel_args()

    def test_default_is_fixed_deterministic_icount(self) -> None:
        environment = os.environ.copy()
        environment.pop(qemu_accel.CORE2_ICOUNT_SHIFT_ENV, None)
        environment.pop(qemu_accel.CORE2_ICOUNT_MAX_PERCPU_NS_ENV, None)
        environment.pop(qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV, None)
        with mock.patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                qemu_accel.core2_accel_args(),
                [
                    "-accel",
                    "tcg,thread=single,tb-size=128",
                    "-icount",
                    "shift=5,align=off,sleep=off",
                ],
            )
            self.assertEqual(
                os.environ[qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV],
                "10000",
            )
        self.assertEqual(
            qemu_accel.CORE2_ICOUNT_MODE,
            "shift=5,align=off,sleep=off",
        )

    def test_environment_override_is_normalized(self) -> None:
        expected = [
            "-accel",
            "tcg,thread=single,tb-size=128",
            "-icount",
            "shift=7,align=off,sleep=off",
        ]
        self.assertEqual(self.core2_args_with("7"), expected)
        self.assertEqual(self.core2_args_with(" 07 "), expected)
        self.assertEqual(
            self.core2_args_with("auto")[-1],
            "shift=auto,align=off,sleep=off",
        )

    def test_environment_override_rejects_invalid_values(self) -> None:
        for value in ("", "-1", "11", "fast", "5.0"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    r"M5_CORE2_ICOUNT_SHIFT must be auto or 0-10",
                ):
                    self.core2_args_with(value)

    def test_percpu_budget_default_and_overrides(self) -> None:
        environment = os.environ.copy()
        environment.pop(qemu_accel.CORE2_ICOUNT_SHIFT_ENV, None)
        environment.pop(qemu_accel.CORE2_ICOUNT_MAX_PERCPU_NS_ENV, None)
        environment.pop(qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV, None)
        with mock.patch.dict(os.environ, environment, clear=True):
            qemu_accel.core2_accel_args()
            self.assertEqual(
                os.environ[qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV],
                "10000",
            )

            os.environ[
                qemu_accel.CORE2_ICOUNT_MAX_PERCPU_NS_ENV
            ] = "5000"
            qemu_accel.core2_accel_args()
            self.assertEqual(
                os.environ[qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV],
                "5000",
            )

            os.environ[
                qemu_accel.CORE2_ICOUNT_MAX_PERCPU_NS_ENV
            ] = "0"
            qemu_accel.core2_accel_args()
            self.assertNotIn(
                qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV,
                os.environ,
            )

    def test_percpu_budget_rejects_invalid_values(self) -> None:
        environment = os.environ.copy()
        environment.pop(qemu_accel.QEMU_ICOUNT_MAX_PERCPU_NS_ENV, None)
        for value in ("-1", "1", "999", "1000000001", "fast"):
            with self.subTest(value=value):
                environment[
                    qemu_accel.CORE2_ICOUNT_MAX_PERCPU_NS_ENV
                ] = value
                with mock.patch.dict(os.environ, environment, clear=True):
                    with self.assertRaisesRegex(
                        ValueError,
                        (
                            "M5_CORE2_ICOUNT_MAX_PERCPU_NS "
                            "must be 0 or 1000-1000000000"
                        ),
                    ):
                        qemu_accel.core2_accel_args()

    def test_qemu_percpu_budget_patch_is_scoped(self) -> None:
        patch = QEMU_PATCH.read_text()
        self.assertIn("M5SW_ICOUNT_MAX_PERCPU_NS", patch)
        self.assertIn("icount_get_max_percpu_ns", patch)
        self.assertIn("icount_percpu_budget", patch)
        self.assertIn("MIN(timeslice, icount_round(max_slice_ns))", patch)
        self.assertNotIn("M5SW_DISABLE_WDT", patch)
        self.assertNotIn("hw/ssi", patch)

    def test_percpu_budget_evidence_keeps_runtime_open(self) -> None:
        evidence = json.loads(BUDGET_SUMMARY.read_text())
        self.assertEqual(evidence["status"], "PARTIAL")
        self.assertEqual(
            evidence["comparison"]["uncapped"]["cpu1_initiator"][
                "can_start_to_call_return_mean_ns"
            ],
            563667,
        )
        self.assertEqual(
            evidence["comparison"]["capped"]["cpu1_initiator"][
                "can_start_to_call_return_mean_ns"
            ],
            56249,
        )
        self.assertEqual(
            evidence["core2_uiflow2_device_group"]["pass_count"],
            6,
        )
        self.assertEqual(
            evidence["classification"]["runtime03"],
            "OPEN",
        )


if __name__ == "__main__":
    unittest.main()
