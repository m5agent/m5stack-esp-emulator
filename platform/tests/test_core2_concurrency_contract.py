#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from device_service import DEFAULT_MAX_PER_DEVICE, DEFAULT_MAX_SESSIONS

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/core2_native_hci/run_service_5x.py"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "core2_service_concurrency_runner",
        RUNNER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Core2 service runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Core2ConcurrencyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()

    def test_concurrency_limit_matches_service_per_device_capacity(self) -> None:
        self.assertEqual(
            self.runner.MAX_CONCURRENCY,
            DEFAULT_MAX_PER_DEVICE,
        )
        self.assertEqual(DEFAULT_MAX_SESSIONS, 12)
        self.assertEqual(DEFAULT_MAX_PER_DEVICE, 8)

    def test_concurrency_accepts_five_and_service_limit(self) -> None:
        for value in (1, 5, DEFAULT_MAX_PER_DEVICE):
            self.assertEqual(
                self.runner.validate_concurrency(value),
                value,
            )

    def test_concurrency_rejects_out_of_range_values(self) -> None:
        for value in (0, -1, DEFAULT_MAX_PER_DEVICE + 1):
            with self.assertRaises(ValueError):
                self.runner.validate_concurrency(value)

    def test_nine_instance_zero_stagger_is_not_admitted(self) -> None:
        with self.assertRaises(ValueError):
            self.runner.validate_concurrency(9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
