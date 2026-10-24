#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/core2_native_hci/run_service_5x.py"
SPEC = importlib.util.spec_from_file_location("core2_native_hci_runner", RUNNER)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def healthy(**overrides: int) -> dict[str, int]:
    values = {
        "hli-valid": 1,
        "hli-posts": 48,
        "hli-consumed": 48,
        "hli-errors": 0,
        "hli-c2h-events": 39,
        "hli-c2h-acls": 9,
        "hli-queue-depth": 0,
        "meta-queue-depth": 0,
        "dropped-packets": 0,
        "tx-queue-depth": 0,
        "last-error": 0,
        "peer-closed": 0,
    }
    values.update(overrides)
    return values


class Core2NativeHciHealthTests(unittest.TestCase):
    def test_accepts_queue_full_only_after_peer_close(self) -> None:
        self.assertTrue(
            runner.native_hci_health_ok(
                healthy(
                    **{
                        "last-error": 2,
                        "peer-closed": 1,
                        "tx-queue-depth": 32,
                    }
                )
            )
        )
        self.assertFalse(
            runner.native_hci_health_ok(healthy(**{"last-error": 2}))
        )
        self.assertFalse(
            runner.native_hci_health_ok(
                healthy(
                    **{
                        "last-error": 2,
                        "peer-closed": 1,
                        "dropped-packets": 0,
                        "tx-queue-depth": 0,
                    }
                )
            )
        )

    def test_rejects_hli_errors_and_queue_depth(self) -> None:
        self.assertFalse(
            runner.native_hci_health_ok(healthy(**{"hli-errors": 1}))
        )
        self.assertFalse(
            runner.native_hci_health_ok(healthy(**{"meta-queue-depth": 1}))
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
