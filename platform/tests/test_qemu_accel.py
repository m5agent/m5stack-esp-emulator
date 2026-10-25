"""Contract tests for the shared Core2 QEMU accelerator arguments."""
from __future__ import annotations

import os
import unittest
from unittest import mock

import qemu_accel


class Core2QemuAccelTests(unittest.TestCase):
    def core2_args_with(self, value: str | None) -> list[str]:
        environment = os.environ.copy()
        environment.pop(qemu_accel.CORE2_ICOUNT_SHIFT_ENV, None)
        if value is not None:
            environment[qemu_accel.CORE2_ICOUNT_SHIFT_ENV] = value
        with mock.patch.dict(os.environ, environment, clear=True):
            return qemu_accel.core2_accel_args()

    def test_default_is_fixed_deterministic_icount(self) -> None:
        self.assertEqual(
            self.core2_args_with(None),
            [
                "-accel",
                "tcg,thread=single,tb-size=128",
                "-icount",
                "shift=5,align=off,sleep=off",
            ],
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


if __name__ == "__main__":
    unittest.main()
