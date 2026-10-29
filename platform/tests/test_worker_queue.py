#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_queue import WorkerJobQueue, WorkerQueueError  # noqa: E402


class WorkerJobQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1_800_000_000.0
        self.path = Path(self.tmp.name) / "jobs.json"
        self.queue = WorkerJobQueue(
            self.path,
            lease_seconds=30,
            clock=lambda: self.now,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def worker(self, **overrides):
        value = {
            "worker_id": "worker-a",
            "instance_id": "instance-a",
            "generation": 1,
            "state": "ready",
            "stale": False,
            "accepting_leases": True,
            "capabilities": {"qemu": True, "pcap": True},
        }
        value.update(overrides)
        return value

    def identity(self, **overrides):
        value = {
            "worker_id": "worker-a",
            "instance_id": "instance-a",
            "generation": 1,
        }
        value.update(overrides)
        return value

    def submit(self, **overrides):
        payload = {
            "label": "stick-s3-network-review",
            "request": {
                "device_id": "sticks3",
                "profile": "uiflow2-sticks3-unified",
            },
            "required_capabilities": {"qemu": True, "pcap": True},
            "max_attempts": 2,
        }
        payload.update(overrides)
        return self.queue.submit(payload)

    def claim(self, job_id=None, claim_key=None):
        payload = self.identity()
        if job_id is not None:
            payload["job_id"] = job_id
        if claim_key is not None:
            payload["claim_idempotency_key"] = claim_key
        return self.queue.claim(payload, [self.worker()])

    def test_submit_idempotency_and_persistence(self):
        first = self.submit(idempotency_key="request-1")
        replay = self.submit(idempotency_key="request-1")
        self.assertEqual(first["job_id"], replay["job_id"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

        with self.assertRaises(WorkerQueueError) as caught:
            self.submit(
                idempotency_key="request-1",
                request={"device_id": "cores3"},
            )
        self.assertEqual(caught.exception.code, "idempotency_conflict")
        self.assertEqual(caught.exception.status, 409)

        restored = WorkerJobQueue(
            self.path,
            lease_seconds=30,
            clock=lambda: self.now,
        )
        listing = restored.list_jobs()
        self.assertEqual(listing["job_count"], 1)
        self.assertEqual(listing["counts"]["queued"], 1)
        self.assertEqual(listing["jobs"][0]["job_id"], first["job_id"])

    def test_capability_matching_claim_and_heartbeat(self):
        camera = self.submit(
            label="camera",
            required_capabilities={"camera": True},
        )
        qemu = self.submit(label="qemu")
        claimed = self.claim()
        self.assertEqual(claimed["job_id"], qemu["job_id"])
        self.assertEqual(claimed["status"], "leased")
        self.assertEqual(claimed["attempts"], 1)
        lease = claimed["lease"]
        self.assertEqual(lease["worker_id"], "worker-a")

        self.now += 10
        heartbeat = self.queue.heartbeat(
            claimed["job_id"],
            {
                **self.identity(),
                "lease_id": lease["lease_id"],
            },
        )
        self.assertEqual(
            heartbeat["lease"]["lease_id"],
            lease["lease_id"],
        )
        self.assertNotEqual(
            heartbeat["lease"]["expires_at"],
            lease["expires_at"],
        )
        self.assertEqual(
            self.queue.list_jobs(status="queued")["jobs"][0]["job_id"],
            camera["job_id"],
        )

    def test_claim_idempotency_replays_same_lease_across_restart(self):
        first_job = self.submit(label="first")
        second_job = self.submit(label="second")
        claim_key = "claim-response-loss-001"
        first = self.claim(
            first_job["job_id"],
            claim_key=claim_key,
        )
        self.assertFalse(first["claim_idempotent_replay"])
        lease_id = first["lease"]["lease_id"]
        mapping_text = self.path.read_text()
        self.assertNotIn(claim_key, mapping_text)

        restored = WorkerJobQueue(
            self.path,
            lease_seconds=30,
            clock=lambda: self.now,
        )
        replay = restored.claim(
            {
                **self.identity(),
                "job_id": first_job["job_id"],
                "claim_idempotency_key": claim_key,
            },
            [self.worker(accepting_leases=False)],
        )
        self.assertEqual(replay["job_id"], first_job["job_id"])
        self.assertEqual(replay["lease"]["lease_id"], lease_id)
        self.assertTrue(replay["claim_idempotent_replay"])
        self.assertEqual(
            restored.get_job(second_job["job_id"])["status"],
            "queued",
        )

        with self.assertRaises(WorkerQueueError) as conflict:
            restored.claim(
                {
                    **self.identity(),
                    "job_id": second_job["job_id"],
                    "claim_idempotency_key": claim_key,
                },
                [self.worker()],
            )
        self.assertEqual(
            conflict.exception.code,
            "claim_idempotency_conflict",
        )

        self.now += 31
        with self.assertRaises(WorkerQueueError) as stale:
            restored.claim(
                {
                    **self.identity(),
                    "job_id": first_job["job_id"],
                    "claim_idempotency_key": claim_key,
                },
                [self.worker()],
            )
        self.assertEqual(
            stale.exception.code,
            "claim_idempotency_stale",
        )
        self.assertEqual(
            restored.get_job(first_job["job_id"])["status"],
            "queued",
        )

    def test_empty_claim_is_not_retained_and_v1_state_migrates(self):
        self.assertIsNone(self.claim(claim_key="empty-poll"))
        job = self.submit()
        claimed = self.claim(job["job_id"], claim_key="empty-poll")
        self.assertEqual(claimed["job_id"], job["job_id"])

        record = json.loads(self.path.read_text())
        record.pop("claim_idempotency")
        self.path.write_text(json.dumps(record))
        restored = WorkerJobQueue(
            self.path,
            lease_seconds=30,
            clock=lambda: self.now,
        )
        self.assertEqual(restored.record["claim_idempotency"], {})

    def test_lease_expiry_retries_then_fails(self):
        job = self.submit(max_attempts=2)
        first = self.claim(job["job_id"])
        self.now += 31
        requeued = self.queue.get_job(job["job_id"])
        self.assertEqual(first["attempts"], 1)
        self.assertEqual(requeued["status"], "queued")
        self.assertEqual(requeued["last_release_reason"], "lease_expired")

        second = self.claim(job["job_id"])
        self.assertEqual(second["attempts"], 2)
        self.now += 31
        failed = self.queue.get_job(job["job_id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failure"]["reason"], "lease_expired")
        self.assertIsNone(self.claim(job["job_id"]))

    def test_result_and_cancel_are_terminal(self):
        completed_job = self.submit(label="complete")
        claimed = self.claim(completed_job["job_id"])
        completed = self.queue.result(
            claimed["job_id"],
            {
                **self.identity(),
                "lease_id": claimed["lease"]["lease_id"],
                "state": "PASS",
                "evidence_sha256": "a" * 64,
                "summary": {"checks": 12},
            },
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"]["state"], "PASS")
        self.assertEqual(
            completed["result"]["lease_id"],
            claimed["lease"]["lease_id"],
        )
        with self.assertRaises(WorkerQueueError) as caught:
            self.queue.heartbeat(
                completed_job["job_id"],
                {
                    **self.identity(),
                    "lease_id": claimed["lease"]["lease_id"],
                },
            )
        self.assertEqual(caught.exception.code, "job_not_leased")

        cancelled = self.queue.cancel(
            self.submit(label="cancel")["job_id"],
            {"reason": "operator_cancelled"},
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["failure"]["reason"], "operator_cancelled")

    def test_supervisor_releases_stale_generation_and_stopped_workers(self):
        job = self.submit(max_attempts=3)
        first = self.claim(job["job_id"])
        self.assertEqual(first["attempts"], 1)

        self.queue = WorkerJobQueue(
            self.path,
            lease_seconds=30,
            clock=lambda: self.now,
        )
        self.assertEqual(
            self.queue.get_job(job["job_id"])["status"],
            "leased",
        )
        reconciled = self.queue.reconcile(
            [self.worker(stale=True, accepting_leases=False)]
        )
        self.assertEqual(reconciled["released_jobs"], 1)
        self.assertEqual(self.queue.get_job(job["job_id"])["status"], "queued")

        second = self.claim(job["job_id"])
        self.assertEqual(second["attempts"], 2)
        self.queue.reconcile(
            [
                self.worker(
                    instance_id="instance-b",
                    generation=2,
                )
            ]
        )
        self.assertEqual(
            self.queue.get_job(job["job_id"])["last_release_reason"],
            "worker_generation_changed",
        )

        third = self.claim(job["job_id"])
        self.assertEqual(third["attempts"], 3)
        self.queue.reconcile([self.worker(state="stopped", accepting_leases=False)])
        failed = self.queue.get_job(job["job_id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failure"]["reason"], "worker_stopped")

    def test_reclaimed_job_fences_the_previous_lease_result(self):
        job = self.submit(max_attempts=2)
        first = self.claim(job["job_id"])
        self.queue.reconcile(
            [self.worker(stale=True, accepting_leases=False)]
        )
        second = self.claim(job["job_id"])
        self.assertEqual(second["attempts"], 2)
        self.assertNotEqual(
            first["lease"]["lease_id"],
            second["lease"]["lease_id"],
        )

        with self.assertRaises(WorkerQueueError) as stale_heartbeat:
            self.queue.heartbeat(
                job["job_id"],
                {
                    **self.identity(),
                    "lease_id": first["lease"]["lease_id"],
                },
            )
        self.assertEqual(
            stale_heartbeat.exception.code,
            "job_lease_mismatch",
        )

        with self.assertRaises(WorkerQueueError) as caught:
            self.queue.result(
                job["job_id"],
                {
                    **self.identity(),
                    "lease_id": first["lease"]["lease_id"],
                    "state": "PASS",
                    "summary": {"stale": True},
                },
            )
        self.assertEqual(caught.exception.code, "job_lease_mismatch")
        self.assertEqual(caught.exception.status, 409)
        still_owned = self.queue.get_job(job["job_id"])
        self.assertEqual(still_owned["status"], "leased")
        self.assertEqual(
            still_owned["lease"]["lease_id"],
            second["lease"]["lease_id"],
        )

        completed = self.queue.result(
            job["job_id"],
            {
                **self.identity(),
                "lease_id": second["lease"]["lease_id"],
                "state": "PASS",
                "summary": {"attempt": 2},
            },
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["result"]["summary"]["attempt"], 2)

    def test_validation_and_schema_errors(self):
        for payload in (
            {},
            {"request": []},
            {"request": {}, "max_attempts": 0},
            {"request": {}, "max_attempts": True},
            {"request": {}, "required_capabilities": "qemu"},
            {"request": {"body": "x" * 70_000}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(WorkerQueueError) as caught:
                    self.queue.submit(payload)
                self.assertEqual(caught.exception.code, "invalid_job")

        worker = self.worker(accepting_leases=False)
        self.submit()
        with self.assertRaises(WorkerQueueError) as caught:
            self.queue.claim(self.identity(), [worker])
        self.assertEqual(caught.exception.code, "worker_not_accepting")

        self.path.write_text(json.dumps({"schema_version": 999}))
        with self.assertRaises(WorkerQueueError) as caught:
            WorkerJobQueue(self.path)
        self.assertEqual(caught.exception.code, "worker_queue_invalid")
        self.assertEqual(caught.exception.status, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
