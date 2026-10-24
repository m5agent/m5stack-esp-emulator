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
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_agent import (  # noqa: E402
    CredentialReloader,
    WorkerAgent,
    WorkerAgentError,
    atomic_write,
    credential_file_fingerprint,
    initialize_identity,
    load_credential_generation,
    parse_arguments,
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
                "error": "stub session failed" if state == "failed" else None,
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


class FakeCredentialApi:
    def __init__(self):
        self.worker_identity = {
            "worker_id": "fleet-worker",
            "generation": 1,
        }
        self.token = None
        self.ssl_context = None

    def configure_credentials(self, *, token, ssl_context):
        self.token = token
        self.ssl_context = ssl_context


class TransientResultApi(FakeApi):
    def __init__(self):
        super().__init__(session_states=["running"])
        self.result_failures = 2

    def json(self, path, *, method="GET", payload=None, timeout=60):
        if path == "/api/v1/jobs/job-test/result" and self.result_failures:
            self.result_failures -= 1
            self.calls.append((method, path, payload))
            raise WorkerAgentError(
                "stub control service restart",
                transient=True,
            )
        return super().json(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )


class TransientClaimApi(FakeApi):
    def json(self, path, *, method="GET", payload=None, timeout=60):
        if path == "/api/v1/jobs/claim":
            self.calls.append((method, path, payload))
            raise WorkerAgentError(
                "stub claim connection lost",
                transient=True,
            )
        return super().json(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )


class FakeRuntimeApi:
    def __init__(self):
        self.calls = []
        self.evidence = evidence_zip()
        self.health_ok = True

    def json(self, path, *, method="GET", payload=None, timeout=60):
        self.calls.append((method, path, payload))
        if path == "/api/health":
            return {"ok": self.health_ok}
        if path == "/api/v1/sessions":
            return {"session_id": "b" * 32}
        if path == f"/api/v1/sessions/{'b' * 32}":
            return {
                "session_id": "b" * 32,
                "device_id": "sticks3",
                "runtime": "qemu-unified",
                "state": "running",
            }
        if path == f"/api/v1/sessions/{'b' * 32}?purge=0":
            return {"session_id": "b" * 32, "state": "stopped"}
        raise AssertionError((method, path, payload))

    def request(self, path, *, method="GET", payload=None, timeout=60):
        self.calls.append((method, path, payload))
        if "/evidence?" in path:
            return 200, self.evidence, "application/zip"
        raise AssertionError((method, path, payload))


class TransientRuntimeApi(FakeRuntimeApi):
    def __init__(self):
        super().__init__()
        self.session_failures = 2
        self.evidence_failures = 2

    def json(self, path, *, method="GET", payload=None, timeout=60):
        if (
            path == f"/api/v1/sessions/{'b' * 32}"
            and self.session_failures
        ):
            self.session_failures -= 1
            self.calls.append((method, path, payload))
            raise WorkerAgentError(
                "stub runtime restart",
                transient=True,
            )
        return super().json(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )

    def request(self, path, *, method="GET", payload=None, timeout=60):
        if "/evidence?" in path and self.evidence_failures:
            self.evidence_failures -= 1
            self.calls.append((method, path, payload))
            raise WorkerAgentError(
                "stub runtime evidence unavailable",
                transient=True,
            )
        return super().request(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )


class TransientRuntimeCreateApi(FakeRuntimeApi):
    def json(self, path, *, method="GET", payload=None, timeout=60):
        if path == "/api/v1/sessions" and method == "POST":
            self.calls.append((method, path, payload))
            raise WorkerAgentError(
                "stub create response lost",
                transient=True,
            )
        return super().json(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )


class WorkerAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.tmp.name) / "agent"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def agent(
        self,
        api,
        *,
        runtime_api=None,
        endpoint=None,
        heartbeat_interval=15,
        control_reconnect_timeout=30,
        runtime_reconnect_timeout=30,
    ):
        identity = initialize_identity(self.work_dir, "worker-test")
        return WorkerAgent(
            api,
            runtime_api=runtime_api,
            work_dir=self.work_dir,
            identity=identity,
            endpoint=endpoint,
            capabilities={"qemu": True},
            heartbeat_interval=heartbeat_interval,
            control_reconnect_timeout=control_reconnect_timeout,
            runtime_reconnect_timeout=runtime_reconnect_timeout,
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

    def test_worker_local_runtime_plane_runs_and_cleans_the_session(self):
        control_api = FakeApi()
        runtime_api = FakeRuntimeApi()
        agent = self.agent(
            control_api,
            runtime_api=runtime_api,
            endpoint="https://worker.example:8788",
        )

        self.assertTrue(agent.work_once())

        control_paths = [call[1] for call in control_api.calls]
        runtime_paths = [call[1] for call in runtime_api.calls]
        self.assertEqual(runtime_paths[0], "/api/health")
        registration_call = next(
            call for call in control_api.calls if call[1] == "/api/v1/workers"
        )
        self.assertEqual(
            registration_call[2]["endpoint"],
            "https://worker.example:8788",
        )
        self.assertIn("/api/v1/jobs/claim", control_paths)
        self.assertIn("/api/v1/jobs/job-test/result", control_paths)
        self.assertFalse(
            any(path.startswith("/api/v1/sessions") for path in control_paths)
        )
        self.assertIn("/api/v1/sessions", runtime_paths)
        self.assertIn(f"/api/v1/sessions/{'b' * 32}?purge=0", runtime_paths)
        self.assertTrue(
            any("/evidence?" in path for path in runtime_paths)
        )

        result = json.loads(
            (self.work_dir / "job-test" / "result.json").read_text()
        )
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(
            result["summary"]["execution_plane"],
            "worker-local",
        )
        self.assertEqual(
            result["evidence_sha256"],
            hashlib.sha256(runtime_api.evidence).hexdigest(),
        )

        with mock.patch.object(
            sys,
            "argv",
            [
                "worker_agent.py",
                "--service-url",
                "http://control.example:8787",
                "--runtime-service-url",
                "http://runtime.example:8788",
                "--advertise-endpoint",
                "https://worker.example:8788",
            ],
        ):
            args = parse_arguments()
        self.assertEqual(args.service_url, "http://control.example:8787")
        self.assertEqual(
            args.runtime_service_url,
            "http://runtime.example:8788",
        )
        self.assertEqual(
            args.advertise_endpoint,
            "https://worker.example:8788",
        )

        unhealthy_runtime = FakeRuntimeApi()
        unhealthy_runtime.health_ok = False
        control_without_capacity = FakeApi()
        unhealthy_agent = self.agent(
            control_without_capacity,
            runtime_api=unhealthy_runtime,
        )
        with self.assertRaisesRegex(
            WorkerAgentError,
            "runtime health did not return ok=true",
        ):
            unhealthy_agent.register()
        self.assertEqual(control_without_capacity.calls, [])

        control_calls_before_recheck = len(control_api.calls)
        runtime_api.health_ok = False
        with self.assertRaisesRegex(
            WorkerAgentError,
            "runtime health did not return ok=true",
        ):
            agent.work_once()
        self.assertEqual(
            len(control_api.calls),
            control_calls_before_recheck,
        )

    def test_transient_control_restart_reregisters_and_reports_same_lease(self):
        api = TransientResultApi()
        agent = self.agent(
            api,
            control_reconnect_timeout=2,
        )

        self.assertTrue(agent.work_once())

        registration_calls = [
            call for call in api.calls if call[1] == "/api/v1/workers"
        ]
        result_calls = [
            call for call in api.calls if call[1] == "/api/v1/jobs/job-test/result"
        ]
        self.assertGreaterEqual(len(registration_calls), 2)
        self.assertEqual(len(result_calls), 3)
        result = json.loads(
            (self.work_dir / "job-test" / "result.json").read_text()
        )
        self.assertEqual(result["state"], "PASS")
        self.assertEqual(
            result["evidence_sha256"],
            hashlib.sha256(api.evidence).hexdigest(),
        )

        unsafe_claim_api = TransientClaimApi()
        unsafe_claim_agent = self.agent(
            unsafe_claim_api,
            control_reconnect_timeout=2,
        )
        unsafe_claim_agent.register()
        with self.assertRaisesRegex(
            WorkerAgentError,
            "claim connection lost",
        ):
            unsafe_claim_agent.claim()
        self.assertEqual(
            sum(
                call[1] == "/api/v1/jobs/claim"
                for call in unsafe_claim_api.calls
            ),
            1,
        )

    def test_known_runtime_session_retries_status_and_evidence(self):
        control_api = FakeApi()
        runtime_api = TransientRuntimeApi()
        agent = self.agent(
            control_api,
            runtime_api=runtime_api,
            runtime_reconnect_timeout=2,
        )

        self.assertTrue(agent.work_once())

        session_path = f"/api/v1/sessions/{'b' * 32}"
        self.assertEqual(
            sum(call[1] == session_path for call in runtime_api.calls),
            3,
        )
        self.assertEqual(
            sum("/evidence?" in call[1] for call in runtime_api.calls),
            3,
        )
        self.assertEqual(runtime_api.session_failures, 0)
        self.assertEqual(runtime_api.evidence_failures, 0)
        result = json.loads(
            (self.work_dir / "job-test" / "result.json").read_text()
        )
        self.assertEqual(result["state"], "PASS")

        create_api = TransientRuntimeCreateApi()
        create_agent = self.agent(
            FakeApi(),
            runtime_api=create_api,
            runtime_reconnect_timeout=2,
        )
        self.assertTrue(create_agent.work_once())
        self.assertEqual(
            sum(
                call[1] == "/api/v1/sessions"
                and call[0] == "POST"
                for call in create_api.calls
            ),
            1,
        )
        create_result = json.loads(
            (self.work_dir / "job-test" / "result.json").read_text()
        )
        self.assertEqual(create_result["state"], "FAIL")
        self.assertIn(
            "create response lost",
            create_result["summary"]["error"],
        )

    def test_session_failure_is_reported_and_cleaned_up(self):
        api = FakeApi(session_states=["failed"])
        agent = self.agent(api)
        self.assertTrue(agent.work_once())
        result = json.loads((self.work_dir / "job-test" / "result.json").read_text())
        self.assertEqual(result["state"], "FAIL")
        self.assertIn(
            "terminal state failed: stub session failed",
            result["summary"]["error"],
        )
        result_calls = [
            call for call in api.calls if call[1] == "/api/v1/jobs/job-test/result"
        ]
        self.assertEqual(len(result_calls), 1)
        self.assertEqual(result_calls[0][2]["state"], "FAIL")
        self.assertIn(
            f"/api/v1/sessions/{'a' * 32}?purge=0",
            [call[1] for call in api.calls],
        )

    def test_credential_files_reload_atomically_with_secret_free_receipt(self):
        token_path = Path(self.tmp.name) / "active.token"
        receipt_dir = Path(self.tmp.name) / "receipts"
        token_path.write_text("token-a\n")
        api = FakeCredentialApi()
        load_failure = False

        def load_token():
            if load_failure:
                raise RuntimeError("invalid staged token")
            return token_path.read_text().strip()

        reloader = CredentialReloader(
            [token_path],
            load_token=load_token,
            load_ssl_context=lambda: None,
            receipt_dir=receipt_dir,
        )
        reloader.mark_current()
        self.assertFalse(reloader.apply(api))

        atomic_write(token_path, b"token-b\n")
        expected_fingerprint = credential_file_fingerprint([token_path])
        self.assertTrue(reloader.apply(api))
        self.assertEqual(api.token, "token-b")
        receipt_path = next(receipt_dir.glob("worker-*.json"))
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(
            receipt["credential_fingerprint"],
            expected_fingerprint,
        )
        self.assertNotIn("token-b", receipt_path.read_text())
        self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)

        load_failure = True
        atomic_write(token_path, b"token-c\n")
        self.assertFalse(reloader.apply(api))
        self.assertEqual(api.token, "token-b")
        self.assertEqual(
            json.loads(receipt_path.read_text())["credential_fingerprint"],
            expected_fingerprint,
        )

    def test_credential_generation_pointer_reloads_one_atomic_snapshot(self):
        pointer = Path(self.tmp.name) / "worker-generation.json"
        generation_a = Path(self.tmp.name) / "a"
        generation_b = Path(self.tmp.name) / "b"
        generation_a.mkdir()
        generation_b.mkdir()
        for directory, label in ((generation_a, "A"), (generation_b, "B")):
            for name in ("ca.crt", "client.crt", "client.key"):
                (directory / name).write_text(f"{label}\n")
        (generation_a / "token").write_text("token-a\n")
        (generation_b / "token").write_text("token-b\n")

        def publish(directory: Path, generation: str) -> None:
            atomic_write(
                pointer,
                (
                    json.dumps(
                        {
                            "schema_version": 1,
                            "generation": generation,
                            "token_file": f"{directory.name}/token",
                            "ca_file": f"{directory.name}/ca.crt",
                            "client_cert": f"{directory.name}/client.crt",
                            "client_key": f"{directory.name}/client.key",
                        }
                    )
                    + "\n"
                ).encode(),
            )

        publish(generation_a, "A")
        loaded = load_credential_generation(pointer)
        self.assertEqual(loaded["generation"], "A")
        self.assertEqual(loaded["token_file"], generation_a / "token")
        api = FakeCredentialApi()

        def load_token():
            current = load_credential_generation(pointer)
            return current["token_file"].read_text().strip()

        reloader = CredentialReloader(
            [pointer],
            load_token=load_token,
            load_ssl_context=lambda: None,
        )
        reloader.mark_current()
        publish(generation_b, "B")
        self.assertTrue(reloader.apply(api))
        self.assertEqual(api.token, "token-b")

        atomic_write(
            pointer,
            (json.dumps({"schema_version": 2}) + "\n").encode(),
        )
        with self.assertRaisesRegex(ValueError, "schema_version"):
            load_credential_generation(pointer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
