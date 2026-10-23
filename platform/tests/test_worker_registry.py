#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_registry import WorkerRegistry, WorkerRegistryError  # noqa: E402


class WorkerRegistryTests(unittest.TestCase):
    def test_drain_resume_and_lease_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = WorkerRegistry(
                Path(tmp) / "worker.json",
                heartbeat_interval=3600,
                stale_after=7200,
            )
            try:
                started = registry.start()
                self.assertEqual(started["state"], "ready")
                self.assertTrue(started["accepting_leases"])

                registry.reserve_lease("lease-1", owner="test")
                draining = registry.drain()
                self.assertEqual(draining["state"], "draining")
                self.assertEqual(draining["active_lease_ids"], ["lease-1"])
                self.assertFalse(draining["accepting_leases"])
                with self.assertRaisesRegex(
                    WorkerRegistryError,
                    r"state=draining",
                ):
                    registry.reserve_lease("lease-2")

                released = registry.release_lease(
                    "lease-1",
                    result={
                        "status": "stopped",
                        "runtime": "qemu-wifi",
                        "network_status": "PARTIAL",
                    },
                )
                self.assertEqual(released["lease_id"], "lease-1")
                drained = registry.snapshot()
                self.assertEqual(drained["state"], "drained")
                self.assertEqual(drained["active_lease_count"], 0)
                self.assertEqual(
                    drained["recent_results"][-1]["lease_id"],
                    "lease-1",
                )

                resumed = registry.resume()
                self.assertEqual(resumed["state"], "ready")
                registry.reserve_lease("lease-2")
                self.assertEqual(
                    registry.snapshot()["active_lease_ids"],
                    ["lease-2"],
                )
            finally:
                registry.close()

    def test_restart_abandons_active_leases_and_advances_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "worker.json"
            first = WorkerRegistry(
                state_path,
                worker_id="worker-test",
                heartbeat_interval=3600,
                stale_after=7200,
            )
            first.start()
            first.reserve_lease("lease-active")
            first_snapshot = first.close()
            self.assertEqual(first_snapshot["state"], "stopped")
            self.assertEqual(first_snapshot["active_lease_ids"], ["lease-active"])

            second = WorkerRegistry(
                state_path,
                heartbeat_interval=3600,
                stale_after=7200,
            )
            try:
                started = second.start()
                self.assertEqual(started["worker_id"], "worker-test")
                self.assertEqual(started["generation"], 2)
                self.assertEqual(started["active_lease_ids"], [])
                self.assertEqual(
                    started["abandoned_leases"][-1]["lease_id"],
                    "lease-active",
                )
                self.assertEqual(
                    started["abandoned_leases"][-1]["reason"],
                    "worker process restarted",
                )
            finally:
                second.close()

    def test_state_directory_has_one_live_worker(self):
        with self.assertRaisesRegex(
            WorkerRegistryError,
            "worker_id must be",
        ):
            WorkerRegistry(
                Path(tempfile.gettempdir()) / "unused-worker.json",
                worker_id="bad\nworker",
            )
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "worker.json"
            first = WorkerRegistry(
                state_path,
                heartbeat_interval=3600,
                stale_after=7200,
            )
            second = WorkerRegistry(
                state_path,
                heartbeat_interval=3600,
                stale_after=7200,
            )
            first.start()
            try:
                with self.assertRaises(WorkerRegistryError) as caught:
                    second.start()
                self.assertEqual(caught.exception.code, "worker_state_locked")
                self.assertEqual(caught.exception.status, 409)
            finally:
                first.close()
                second.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
