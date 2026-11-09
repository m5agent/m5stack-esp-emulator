"""Runtime evidence negative controls; no firmware or QEMU is executed."""
import copy
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime_evidence import observe_runtime, finalize_runtime_result


class RuntimeEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.binary = Path(temporary.name) / "qemu-system-xtensa"
        self.binary.write_bytes(b"actual-service-runtime-fixture")
        self.session = {"session_id": "offline-fixture", "state": "running",
                        "pid": 123, "firmware_sha256": "firmware-fixture"}
        self.client = SimpleNamespace(url="http://localhost:8941", runtime_proofs={},
                                      json=lambda *a, **kw: copy.deepcopy(self.session))
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("M5_UNIT_EXPECT_RUNTIME_SHA256", None)
        os.environ.pop("M5_QEMU_XTENSA", None)
        process = patch("runtime_evidence._process_executable", return_value=(self.binary, "offline fixture"))
        self.process = process.start()
        self.addCleanup(process.stop)

    def test_hash_comes_from_actual_session_executable(self):
        proof = observe_runtime(self.client, self.session)
        self.assertEqual(proof["status"], "VERIFIED")
        self.assertEqual(proof["runtime_binary_sha256"], hashlib.sha256(self.binary.read_bytes()).hexdigest())

    def test_configured_path_is_an_expectation_not_an_observation(self):
        other = self.binary.parent / "other-runtime"
        other.write_bytes(b"different configured runtime")
        os.environ["M5_QEMU_XTENSA"] = str(other)
        proof = observe_runtime(self.client, self.session)
        self.assertEqual(proof["status"], "NOT VERIFIED")
        self.assertNotEqual(proof["runtime_binary_sha256"], proof["expected_runtime_binary_sha256"])

    def test_session_identity_change_rejects_the_sample(self):
        for field in ("session_id", "pid", "firmware_sha256", "state"):
            confirmed = copy.deepcopy(self.session)
            confirmed[field] = "changed"
            self.client.json = lambda *a, **kw: confirmed
            self.assertEqual(observe_runtime(self.client, self.session)["status"], "NOT VERIFIED", field)

    def test_worker_or_remote_pid_is_not_inspected_as_a_local_process(self):
        self.session["worker"] = {"worker_id": "remote-worker", "generation": 2}
        self.assertEqual(observe_runtime(self.client, self.session)["status"], "NOT VERIFIED")
        self.session.pop("worker")
        self.client.url = "https://example.com"
        self.assertEqual(observe_runtime(self.client, self.session)["status"], "NOT VERIFIED")
        self.process.assert_not_called()

    def test_local_worker_requires_matching_live_lease_and_process_ancestry(self):
        self.session["worker"] = {"worker_id": "local-worker", "generation": 2}
        worker = {"worker_id": "local-worker", "generation": 2, "pid": 12,
                  "instance_id": "worker-instance", "active_lease_ids": ["offline-fixture"]}
        self.client.json = lambda path, **kw: copy.deepcopy(worker if path == "worker" else self.session)
        with patch("runtime_evidence.subprocess.check_output", return_value="12\n"):
            proof = observe_runtime(self.client, self.session)
        self.assertEqual(proof["status"], "VERIFIED")
        self.assertTrue(proof["local_worker_ancestry_verified"])
        worker["active_lease_ids"] = []
        self.assertEqual(observe_runtime(self.client, self.session)["status"], "NOT VERIFIED")

    def test_local_worker_ancestry_mismatch_stays_unverified(self):
        self.session["worker"] = {"worker_id": "local-worker", "generation": 2}
        worker = {"worker_id": "local-worker", "generation": 2, "pid": 12,
                  "instance_id": "worker-instance", "active_lease_ids": ["offline-fixture"]}
        self.client.json = lambda path, **kw: copy.deepcopy(worker if path == "worker" else self.session)
        with patch("runtime_evidence.subprocess.check_output", return_value="1\n"):
            proof = observe_runtime(self.client, self.session)
        self.assertEqual(proof["status"], "NOT VERIFIED")

    def test_failed_pid_inspection_does_not_fall_back_to_configured_hash(self):
        os.environ["M5_QEMU_XTENSA"] = str(self.binary)
        self.process.side_effect = PermissionError("PID executable unavailable")
        proof = observe_runtime(self.client, self.session)
        self.assertEqual(proof["status"], "NOT VERIFIED")
        self.assertNotIn("runtime_binary_sha256", proof)

    def test_missing_model_is_unavailable_infrastructure_not_firmware_failure(self):
        result = {"status": "FAIL", "error": "qemu-system-xtensa: Unit model is unavailable: rtc"}
        finalize_runtime_result(self.client, result)
        self.assertEqual(result["status"], "NOT RUN")
        self.assertEqual(result["classification"], "runtime-infrastructure")
        self.assertIn("Unit model is unavailable: rtc", result["error"])

    def test_firmware_failure_is_preserved(self):
        result = {"status": "FAIL", "error": "guest sensor value differs"}
        self.assertEqual(finalize_runtime_result(self.client, result)["status"], "FAIL")

    def test_unknown_hash_never_reuses_runner_assumption_or_claims_pass(self):
        result = {"status": "PASS", "runtime_binary_sha256": "stale-assumption"}
        finalize_runtime_result(self.client, result)
        self.assertIsNone(result["runtime_binary_sha256"])
        self.assertEqual(result["status"], "PARTIAL")

    def test_verified_session_proof_is_written_to_result(self):
        proof = observe_runtime(self.client, self.session)
        self.client.runtime_proofs[self.session["session_id"]] = proof
        result = {"status": "PASS", "session_id": self.session["session_id"]}
        finalize_runtime_result(self.client, result)
        self.assertEqual(result["runtime_binary_sha256"], proof["runtime_binary_sha256"])
        self.assertEqual(result["status"], "PASS")


    def test_explicit_session_lookup_preserves_hash_only_result_identity(self):
        proof = observe_runtime(self.client, self.session)
        sid = self.session["session_id"]
        self.client.runtime_proofs[sid] = proof
        result = {"status": "PASS", "session_id_sha256": hashlib.sha256(sid.encode()).hexdigest()}
        finalize_runtime_result(self.client, result, session_id=sid)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["runtime_provenance"]["status"], "VERIFIED")
        self.assertEqual(result["runtime_binary_sha256"], proof["runtime_binary_sha256"])
        self.assertNotIn("session_id", result["runtime_provenance"])
        self.assertEqual(proof["session_id"], sid)

    def test_expected_hash_mismatch_fails_a_functionally_passing_result(self):
        os.environ["M5_UNIT_EXPECT_RUNTIME_SHA256"] = "0" * 64
        sid = self.session["session_id"]
        proof = observe_runtime(self.client, self.session)
        self.client.runtime_proofs[sid] = proof
        result = {"status": "PASS", "session_id": sid}
        finalize_runtime_result(self.client, result)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["classification"], "runtime-provenance")
        self.assertEqual(result["runtime_binary_sha256"], proof["runtime_binary_sha256"])
        self.assertEqual(result["runtime_provenance"]["expected_runtime_binary_sha256"], "0" * 64)


class ControlTokenFileTests(unittest.TestCase):
    def test_file_is_used_without_disclosing_or_overriding_explicit_credentials(self):
        from run_service_cases import Client
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "control-token"
            path.write_text("offline-control-fixture\n")
            with patch.dict(os.environ, {"M5_SERVICE_API_TOKEN_FILE": str(path),
                                         "M5_SERVICE_API_TOKEN": "", "M5_UNIT_WEB_BRIDGE": "0"}):
                self.assertEqual(Client("http://localhost").token, "offline-control-fixture")
                self.assertEqual(Client("http://localhost", token="explicit-fixture").token, "explicit-fixture")

    def test_runtime_stderr_blocker_is_detected_before_a_missing_guest_marker(self):
        from run_service_cases import Client, wait_for
        client = Client("http://localhost", token="offline-fixture")
        session = {"state": "booting", "session_id": "offline-fixture"}
        def response(path, **kwargs):
            if "/logs?" in path:
                return {"stderr": "Adding SPI flash device\nqemu-system-xtensa: Unit model is unavailable: rtc\n"}
            return session
        client.json = response
        with self.assertRaisesRegex(RuntimeError, "Unit model is unavailable: rtc"):
            wait_for(client, session["session_id"], lambda text: False)


if __name__ == "__main__":
    unittest.main()
