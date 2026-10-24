#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_agent import (  # noqa: E402
    WorkerAgent,
    initialize_identity,
)


def evidence_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", "{}\n")
    return output.getvalue()


class FakeApi:
    def __init__(self, *, session_states=None):
        self.calls = []
        self.session_states = list(session_states or ["running"])
        self.evidence = evidence_zip()

    def json(self, path, *, method="GET", payload=None, timeout=60):
        self.calls.append((method, path, payload))
        if path == "/api/v1/workers":
            return {"worker": {"worker_id": payload["worker_id"]}}
        if path.endswith("/heartbeat") and path.startswith("/api/v1/workers/"):
            return {"worker": {"worker_id": payload["worker_id"]}}
        if path == "/api/v1/jobs/claim":
            return {
                "job": {
                    "job_id": "job-test",
                    "lease": {
                        "lease_id": "lease-test",
                        "worker_id": payload["worker_id"],
                        "instance_id": payload["instance_id"],
                        "generation": payload["generation"],
                    },
                    "request": {
                        "session": {
                            "device_id": "sticks3",
                            "runtime": "qemu",
                        }
                    },
                }
            }
        if path == "/api/v1/sessions":
            return {"session_id": "a" * 32}
        if path == f"/api/v1/sessions/{'a' * 32}":
            state = (
                self.session_states.pop(0)
                if len(self.session_states) > 1
                else self.session_states[0]
            )
            return {
                "session_id": "a" * 32,
                "device_id": "sticks3",
                "runtime": "qemu",
                "state": state,
            }
        if path.startswith("/api/v1/jobs/job-test/heartbeat"):
            return {"job": {"job_id": "job-test"}}
        if path.startswith("/api/v1/jobs/job-test/result"):
            return {"job": {"job_id": "job-test", "status": "completed"}}
        if path.startswith(f"/api/v1/sessions/{'a' * 32}?purge=0"):
            return {"session_id": "a" * 32, "state": "stopped"}
        if path.endswith("/stop"):
            return {"worker": {"worker_id": payload["worker_id"]}}
        raise AssertionError((method, path, payload))

    def request(self, path, *, method="GET", payload=None, timeout=60):
        self.calls.append((method, path, payload))
        if "/evidence?" in path:
            return 200, self.evidence, "application/zip"
        raise AssertionError((method, path, payload))


class WorkerAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp.name) / "agent"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def agent(self, api, *, heartbeat_interval=15):
        identity = initialize_identity(self.work_dir, "worker-test")
        return WorkerAgent(
            api,
            work_dir=self.work_dir,
            identity=identity,
            capabilities={"qemu": True},
            heartbeat_interval=heartbeat_interval,
        )

    def test_identity_generation_is_persistent_and_bounded(self):
        first = initialize_identity(self.work_dir, "worker-test")
        second = initialize_identity(self.work_dir, "worker-test")
        other = initialize_identity(self.work_dir, "other-worker")
        self.assertEqual(first["generation"], 1)
        self.assertEqual(second["generation"], 2)
        self.assertEqual(other["generation"], 1)
        self.assertNotEqual(first["instance_id"], second["instance_id"])
        self.assertEqual(
            (self.work_dir / "agent-state.json").stat().st_mode & 0o777,
            0o600,
        )

    def test_executes_real_http_session_contract_and_persists_evidence(self):
        api = FakeApi()
        agent = self.agent(api)
        self.assertTrue(agent.work_once())
        result_path = self.work_dir / "job-test" / "result.json"
        evidence_path = self.work_dir / "job-test" / "evidence.zip"
        result = json.loads(result_path.read_text())
        expected_sha = hashlib.sha256(api.evidence).hexdigest()
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(result["evidence_sha256"], expected_sha)
        self.assertTrue(evidence_path.is_file())
        self.assertEqual(
            evidence_path.stat().st_mode & 0o777,
            0o600,
        )
        paths = [call[1] for call in api.calls]
        self.assertIn("/api/v1/jobs/claim", paths)
        self.assertIn("/api/v1/jobs/job-test/result", paths)
        evidence_calls = [call[1] for call in api.calls if "/evidence?" in call[1]]
        self.assertEqual(
            evidence_calls,
            [
                f"/api/v1/sessions/{'a' * 32}/evidence?"
                "include=manifest%2Cserial%2Cframes%2Clogs%2Cnetwork%2Cqom"
            ],
        )
        self.assertIn(
            f"/api/v1/sessions/{'a' * 32}?purge=0",
            paths,
        )

    def test_session_failure_is_reported_and_cleaned_up(self):
        api = FakeApi(session_states=["failed"])
        agent = self.agent(api)
        self.assertTrue(agent.work_once())
        result = json.loads((self.work_dir / "job-test" / "result.json").read_text())
        self.assertEqual(result["state"], "FAIL")
        self.assertIn("terminal state failed", result["summary"]["error"])
        result_calls = [
            call for call in api.calls if call[1] == "/api/v1/jobs/job-test/result"
        ]
        self.assertEqual(len(result_calls), 1)
        self.assertEqual(result_calls[0][2]["state"], "FAIL")
        self.assertIn(
            f"/api/v1/sessions/{'a' * 32}?purge=0",
            [call[1] for call in api.calls],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
