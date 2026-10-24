#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_auth import (  # noqa: E402
    WorkerAuthError,
    WorkerAuthVerifier,
    is_worker_auth_path,
    read_master_token_file,
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

    def test_previous_master_token_is_accepted_only_during_overlap(self):
        overlap = WorkerAuthVerifier(
            "new-master-secret",
            previous_master_token="old-master-secret",
            clock=lambda: self.now,
        )
        old_headers = sign_worker_request(
            "old-master-secret",
            self.identity,
            "POST",
            self.path,
            self.body,
            timestamp=self.now,
            nonce="c" * 32,
        )
        new_headers = sign_worker_request(
            "new-master-secret",
            self.identity,
            "POST",
            self.path,
            self.body,
            timestamp=self.now,
            nonce="d" * 32,
        )
        self.assertEqual(
            overlap.verify(old_headers, "POST", self.path, self.body),
            self.identity,
        )
        self.assertEqual(
            overlap.verify(new_headers, "POST", self.path, self.body),
            self.identity,
        )

        final = WorkerAuthVerifier(
            "new-master-secret",
            clock=lambda: self.now,
        )
        with self.assertRaises(WorkerAuthError) as rejected:
            final.verify(old_headers, "POST", self.path, self.body)
        self.assertEqual(rejected.exception.code, "worker_auth_invalid")

    def test_master_token_file_is_strict_and_does_not_trim_token_body(self):
        with tempfile.TemporaryDirectory() as temp:
            token_path = Path(temp) / "token"
            token_path.write_text("  token-value  \n")
            self.assertEqual(
                read_master_token_file(token_path),
                "  token-value  ",
            )
            token_path.write_text("")
            with self.assertRaises(WorkerAuthError) as empty:
                read_master_token_file(token_path)
            self.assertEqual(
                empty.exception.code,
                "worker_token_file_invalid",
            )
            token_path.write_bytes(b"\xff")
            with self.assertRaises(WorkerAuthError) as invalid_utf8:
                read_master_token_file(token_path)
            self.assertEqual(
                invalid_utf8.exception.code,
                "worker_token_file_invalid",
            )
        with self.assertRaises(WorkerAuthError) as missing:
            read_master_token_file(Path(temp) / "missing")
        self.assertEqual(
            missing.exception.code,
            "worker_token_file_missing",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
