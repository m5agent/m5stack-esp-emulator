#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_directory import WorkerDirectory, WorkerDirectoryError  # noqa: E402


class WorkerDirectoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1_800_000_000.0
        self.path = Path(self.tmp.name) / "workers.json"
        self.directory = WorkerDirectory(self.path, clock=lambda: self.now)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def payload(self, **overrides):
        value = {
            "worker_id": "worker-a",
            "instance_id": "instance-a",
            "generation": 1,
            "stale_after_seconds": 10,
            "endpoint": "http://worker.example:8787",
            "capabilities": {"qemu": True, "max_sessions": 4},
            "active_lease_ids": ["lease-2", "lease-1"],
        }
        value.update(overrides)
        return value

    def test_register_heartbeat_and_persistence(self):
        registered = self.directory.register(self.payload())
        self.assertEqual(registered["state"], "ready")
        self.assertEqual(registered["active_lease_count"], 2)
        self.assertEqual(
            registered["active_lease_ids"],
            ["lease-1", "lease-2"],
        )
        self.assertTrue(registered["accepting_leases"])
        mode = self.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

        self.now += 4
        heartbeat = self.directory.heartbeat(
            "worker-a",
            {
                "instance_id": "instance-a",
                "generation": 1,
                "active_lease_ids": ["lease-3"],
                "capabilities": {"qemu": True, "wifi": True},
            },
        )
        self.assertEqual(heartbeat["active_lease_ids"], ["lease-3"])
        self.assertEqual(
            heartbeat["capabilities"],
            {"qemu": True, "wifi": True},
        )

        restored = WorkerDirectory(self.path, clock=lambda: self.now)
        listing = restored.list_workers()
        self.assertEqual(listing["worker_count"], 1)
        self.assertEqual(listing["active_lease_count"], 1)
        self.assertEqual(
            listing["workers"][0]["instance_id"],
            "instance-a",
        )
        self.assertEqual(listing["workers"][0]["generation"], 1)

    def test_registration_retry_is_idempotent_and_preserves_drain(self):
        self.directory.register(self.payload())
        draining = self.directory.drain(
            "worker-a",
            {"instance_id": "instance-a", "generation": 1},
        )
        self.assertEqual(draining["state"], "draining")

        retried = self.directory.register(self.payload())
        self.assertEqual(retried["state"], "draining")
        self.assertEqual(retried["active_lease_ids"], ["lease-1", "lease-2"])

    def test_live_instance_conflict_requires_identity_or_generation(self):
        self.directory.register(self.payload())
        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.register(
                self.payload(instance_id="instance-b", generation=2)
            )
        self.assertEqual(caught.exception.code, "worker_instance_conflict")
        self.assertEqual(caught.exception.status, 409)

        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.heartbeat(
                "worker-a",
                {"instance_id": "instance-b", "generation": 1},
            )
        self.assertEqual(caught.exception.code, "worker_identity_mismatch")

    def test_stale_replacement_advances_generation(self):
        self.directory.register(self.payload())
        self.now += 11
        stale = self.directory.list_workers()["workers"][0]
        self.assertTrue(stale["stale"])
        self.assertFalse(stale["accepting_leases"])

        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.register(
                self.payload(instance_id="instance-b", generation=1)
            )
        self.assertEqual(caught.exception.code, "worker_generation_conflict")

        replacement = self.directory.register(
            self.payload(
                instance_id="instance-b",
                generation=2,
                active_lease_ids=[],
            )
        )
        self.assertEqual(replacement["instance_id"], "instance-b")
        self.assertEqual(replacement["generation"], 2)
        self.assertTrue(replacement["accepting_leases"])
        self.assertEqual(replacement["active_lease_count"], 0)

    def test_drain_stop_and_stopped_terminal_state(self):
        self.directory.register(self.payload(active_lease_ids=[]))
        drained = self.directory.drain(
            "worker-a",
            {"instance_id": "instance-a", "generation": 1},
        )
        self.assertEqual(drained["state"], "drained")
        self.assertIsNotNone(drained["drained_at"])

        stopped = self.directory.stop(
            "worker-a",
            {"instance_id": "instance-a", "generation": 1},
        )
        self.assertEqual(stopped["state"], "stopped")
        self.assertIsNotNone(stopped["stopped_at"])
        repeated = self.directory.stop(
            "worker-a",
            {"instance_id": "instance-a", "generation": 1},
        )
        self.assertEqual(repeated["state"], "stopped")

        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.heartbeat(
                "worker-a",
                {
                    "instance_id": "instance-a",
                    "generation": 1,
                    "state": "ready",
                },
            )
        self.assertEqual(caught.exception.code, "worker_stopped")

        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.register(self.payload())
        self.assertEqual(caught.exception.code, "worker_generation_conflict")

        replacement = self.directory.register(
            self.payload(
                instance_id="instance-b",
                generation=2,
                active_lease_ids=[],
            )
        )
        self.assertEqual(replacement["state"], "ready")

    def test_recent_results_are_bounded_and_persisted(self):
        self.directory.register(self.payload(active_lease_ids=[]))
        for index in range(35):
            result = self.directory.record_result(
                "worker-a",
                {
                    "instance_id": "instance-a",
                    "generation": 1,
                    "lease_id": f"lease-{index}",
                    "state": "PASS" if index % 2 else "FAIL",
                    "evidence_sha256": f"{index:064x}",
                },
            )
            self.assertEqual(result["lease_id"], f"lease-{index}")

        worker = WorkerDirectory(
            self.path,
            clock=lambda: self.now,
        ).list_workers()["workers"][0]
        self.assertEqual(len(worker["recent_results"]), 32)
        self.assertEqual(
            worker["recent_results"][0]["lease_id"],
            "lease-3",
        )
        self.assertEqual(
            worker["recent_results"][-1]["lease_id"],
            "lease-34",
        )

    def test_invalid_endpoint_capabilities_and_results(self):
        for endpoint in (
            "ftp://worker.example",
            "http://user:secret@worker.example",
            "http://worker.example?token=secret",
            "http://worker.example/#fragment",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(WorkerDirectoryError) as caught:
                    self.directory.register(self.payload(endpoint=endpoint))
                self.assertEqual(caught.exception.code, "invalid_worker")

        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.register(
                self.payload(capabilities={"blob": "x" * 17_000})
            )
        self.assertEqual(caught.exception.code, "invalid_worker")

        self.directory.register(self.payload())
        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.record_result(
                "worker-a",
                {
                    "instance_id": "instance-a",
                    "generation": 1,
                    "lease_id": "lease-1",
                    "state": "PASS",
                    "evidence_sha256": "not-a-sha256",
                },
            )
        self.assertEqual(caught.exception.code, "invalid_worker_result")

    def test_worker_and_lease_capacity_limits(self):
        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.register(
                self.payload(
                    active_lease_ids=[
                        f"lease-{index}" for index in range(129)
                    ]
                )
            )
        self.assertEqual(caught.exception.code, "invalid_worker")

        for index in range(128):
            self.directory.register(
                self.payload(
                    worker_id=f"worker-{index:03d}",
                    instance_id=f"instance-{index:03d}",
                    active_lease_ids=[],
                )
            )
        with self.assertRaises(WorkerDirectoryError) as caught:
            self.directory.register(
                self.payload(
                    worker_id="worker-128",
                    instance_id="instance-128",
                    active_lease_ids=[],
                )
            )
        self.assertEqual(caught.exception.code, "worker_capacity_exceeded")
        self.assertEqual(caught.exception.status, 409)

    def test_worker_directory_schema_validation(self):
        self.path.write_text(
            json.dumps({"schema_version": 999, "workers": {}})
        )
        with self.assertRaises(WorkerDirectoryError) as caught:
            WorkerDirectory(self.path)
        self.assertEqual(caught.exception.code, "worker_directory_invalid")
        self.assertEqual(caught.exception.status, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
