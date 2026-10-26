"""Offline provenance faults; these tests do not execute firmware or QEMU."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web_ui_bridge import WebUIBridge, _process_executable


class ProcessExecutableTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.executable = Path(directory.name) / "fixture-runtime"
        self.executable.write_bytes(b"offline-executable-fixture")

    def test_linux_uses_strict_proc_exe_without_ps(self):
        with patch("web_ui_bridge.sys.platform", "linux"), patch("web_ui_bridge.Path") as path_type, patch("web_ui_bridge.subprocess.check_output") as ps:
            path_type.return_value.resolve.return_value = self.executable
            path, source = _process_executable(2468)
            path_type.assert_called_once_with("/proc/2468/exe")
            path_type.return_value.resolve.assert_called_once_with(strict=True)
            ps.assert_not_called()
        self.assertEqual(path, self.executable)
        self.assertIn("/proc", source)

    def test_linux_missing_proc_image_does_not_fallback(self):
        with patch("web_ui_bridge.sys.platform", "linux"), patch("web_ui_bridge.Path") as path_type, patch("web_ui_bridge.subprocess.check_output") as ps:
            path_type.return_value.resolve.side_effect = FileNotFoundError("process image unavailable")
            with self.assertRaises(FileNotFoundError):
                _process_executable(2468)
            ps.assert_not_called()

    def test_macos_uses_absolute_ps_path(self):
        with patch("web_ui_bridge.sys.platform", "darwin"), patch("web_ui_bridge.subprocess.check_output", return_value=str(self.executable) + "\n") as ps:
            path, source = _process_executable(2468)
            ps.assert_called_once_with(["ps", "-p", "2468", "-o", "comm="], text=True)
        self.assertEqual(path, self.executable)
        self.assertIn("macOS", source)

    def test_short_comm_is_rejected(self):
        with patch("web_ui_bridge.sys.platform", "darwin"), patch("web_ui_bridge.subprocess.check_output", return_value="python3\n"):
            with self.assertRaisesRegex(RuntimeError, "executable is unavailable"):
                _process_executable(2468)


class RuntimeProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bridge = WebUIBridge.__new__(WebUIBridge)
        self.bridge.output = Path(self.directory.name)
        self.bridge.url = "http://127.0.0.1:8787"
        self.session = {
            "session_id": "offline-provenance-fixture", "pid": os.getpid(),
            "state": "running", "firmware_sha256": "offline-fixture",
            "worker": {"worker_id": "fixture-worker", "generation": 6},
        }
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("M5_UNIT_EXPECT_RUNTIME_SHA256", None)

    def test_nested_worker_is_sampled_and_confirmed(self):
        proof = self.bridge.runtime_provenance(self.session, lambda: copy.deepcopy(self.session))
        self.assertEqual(proof["status"], "VERIFIED")
        self.assertEqual(proof["worker_id"], "fixture-worker")
        self.assertEqual(proof["worker_generation"], 6)
        self.assertRegex(proof["runtime_binary_sha256"], r"^[0-9a-f]{64}$")

    def test_nested_generation_change_is_not_verified(self):
        confirmed = copy.deepcopy(self.session)
        confirmed["worker"]["generation"] = 7
        proof = self.bridge.runtime_provenance(self.session, lambda: confirmed)
        self.assertEqual(proof["status"], "NOT VERIFIED")
        self.assertIn("changed", proof["error"])

    def test_missing_worker_stays_unknown(self):
        self.session.pop("worker")
        proof = self.bridge.runtime_provenance(self.session, lambda: copy.deepcopy(self.session))
        self.assertEqual(proof["status"], "VERIFIED")
        self.assertIsNone(proof["worker_id"])
        self.assertIsNone(proof["worker_generation"])
        self.assertIn("Null worker fields remain unknown", proof["method"])

    def test_required_hash_mismatch_fails_and_preserves_receipt(self):
        os.environ["M5_UNIT_EXPECT_RUNTIME_SHA256"] = "f" * 64
        with self.assertRaisesRegex(RuntimeError, "required live executable"):
            self.bridge.runtime_provenance(self.session, lambda: copy.deepcopy(self.session))
        proof = json.loads((self.bridge.output / self.session["session_id"] / "runtime-provenance.json").read_text())
        self.assertEqual(proof["status"], "NOT VERIFIED")
        self.assertIn("differs", proof["error"])

    def test_browser_failure_receipt_preserves_redacted_diagnostic(self):
        workspace = Path(__file__).resolve().parents[2]
        self.bridge.note_failure(self.session["session_id"], "before-evidence", RuntimeError(str(workspace / "fixture.py")))
        failures = json.loads((self.bridge.output / self.session["session_id"] / "bridge-errors.json").read_text())
        self.assertEqual(failures[0]["phase"], "before-evidence")
        self.assertEqual(failures[0]["error"], "<workspace>/fixture.py")


if __name__ == "__main__":
    unittest.main()
