#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_auth import (  # noqa: E402
    WorkerAuthError,
    WorkerAuthVerifier,
    is_worker_auth_path,
    sign_worker_request,
)


class WorkerAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_800_000_000
        self.identity = {
            "worker_id": "worker-a",
            "instance_id": "instance-a",
            "generation": 1,
        }
        self.body = b'{"worker_id":"worker-a"}'
        self.path = "/api/v1/jobs/claim"
        self.headers = sign_worker_request(
            "master-secret",
            self.identity,
            "POST",
            self.path,
            self.body,
            timestamp=self.now,
            nonce="a" * 32,
        )
        self.verifier = WorkerAuthVerifier(
            "master-secret",
            clock=lambda: self.now,
        )

    def test_worker_paths_are_explicit(self):
        self.assertTrue(is_worker_auth_path("POST", self.path))
        self.assertTrue(
            is_worker_auth_path(
                "POST",
                "/api/v1/jobs/job-a/result",
            )
        )
        self.assertTrue(
            is_worker_auth_path(
                "POST",
                "/api/v1/workers/worker-a/heartbeat",
            )
        )
        self.assertFalse(
            is_worker_auth_path(
                "POST",
                "/api/v1/jobs/job-a/cancel",
            )
        )
        self.assertFalse(is_worker_auth_path("POST", "/api/v1/workers"))

    def test_valid_signature_returns_identity(self):
        verified = self.verifier.verify(
            self.headers,
            "POST",
            self.path,
            self.body,
        )
        self.assertEqual(verified, self.identity)
        with self.assertRaises(WorkerAuthError) as caught:
            self.verifier.verify(
                self.headers,
                "POST",
                self.path,
                self.body + b" ",
            )
        self.assertEqual(caught.exception.code, "worker_auth_invalid")

    def test_timestamp_and_replay_are_rejected(self):
        self.verifier.clock = lambda: self.now + 91
        with self.assertRaises(WorkerAuthError) as expired:
            self.verifier.verify(
                self.headers,
                "POST",
                self.path,
                self.body,
            )
        self.assertEqual(expired.exception.code, "worker_auth_expired")

        self.verifier.clock = lambda: self.now
        self.verifier.verify(
            self.headers,
            "POST",
            self.path,
            self.body,
        )
        with self.assertRaises(WorkerAuthError) as replay:
            self.verifier.verify(
                self.headers,
                "POST",
                self.path,
                self.body,
            )
        self.assertEqual(replay.exception.code, "worker_auth_replay")
        self.assertEqual(replay.exception.status, 409)

    def test_generation_is_part_of_the_key(self):
        other = {
            **self.identity,
            "generation": 2,
        }
        with self.assertRaises(WorkerAuthError) as caught:
            self.verifier.verify(
                {
                    **self.headers,
                    "X-M5-Worker-Generation": "2",
                },
                "POST",
                self.path,
                self.body,
            )
        self.assertEqual(caught.exception.code, "worker_auth_invalid")
        signed = sign_worker_request(
            "master-secret",
            other,
            "POST",
            self.path,
            self.body,
            timestamp=self.now,
            nonce="b" * 32,
        )
        self.assertEqual(
            self.verifier.verify(signed, "POST", self.path, self.body),
            other,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
