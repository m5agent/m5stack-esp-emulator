"""Offline admission-runner contracts; no service, UART or guest is started."""
from __future__ import annotations

import base64
from contextlib import redirect_stdout
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_binary_checkpoint_admission as probe


class BinaryCheckpointAdmissionTests(unittest.TestCase):
    nonce = "a" * 32
    execution = "b" * 32

    def checkpoint(self, payload):
        files = probe.decoded_files(payload)
        hashes = {path: probe.sha(data) for path, data in files.items()}
        return {"revision": {"entrypoint": "main.mpy", "source_kind": "uiflow2-package",
                "revision_id": probe.package_identity(payload), "source_sha256": probe.sha(probe.canonical(hashes)),
                "total_file_bytes": sum(map(len, files.values())),
                "files": [{"path": path, "size": len(data), "sha256": probe.sha(data),
                           "kind": "mpy" if path.endswith(".mpy") else "resource"} for path, data in files.items()]},
                "files": {path: {"encoding": "base64", "data": base64.b64encode(data).decode()} for path, data in files.items()}}

    def window(self, *, row=None, execution=None):
        ready = {"kind": "ready", "nonce": self.nonce, "phase": "A"}
        sample = row or {"kind": "sample", "nonce": self.nonce, "phase": "A", "sequence": 3, "motion": True}
        return "\x04__M5_EXEC_" + (execution or self.execution) + "__:START\r\n" + "".join(probe.PREFIX + json.dumps(value) + "\r\n" for value in (ready, sample))

    def test_default_plan_is_offline_without_reading_token_or_creating_output(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(probe, "read_token", side_effect=AssertionError("token read")), \
                mock.patch.object(probe, "Client", side_effect=AssertionError("network")):
            output = Path(directory) / "absent"
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(probe.main(["--device", "all", "--base-url", "invalid://offline", "--token-file", "/missing",
                                             "--out-dir", str(output)]), 0)
            plan = json.loads(stream.getvalue())
            self.assertEqual(plan["devices"], list(probe.DEVICES))
            self.assertFalse(plan["api_contacted"])
            self.assertFalse(plan["fixture"]["executed"])
            self.assertFalse(output.exists())

    def test_token_requires_owned_regular_mode600_and_never_follows_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("synthetic-test-secret\n")
            path.chmod(0o600)
            self.assertEqual(probe.read_token(path), "synthetic-test-secret")
            path.chmod(0o640)
            with self.assertRaisesRegex(ValueError, "mode-600"):
                probe.read_token(path)
            alias = Path(directory) / "alias"
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                probe.read_token(alias)

    def test_actual_official_fixture_is_only_checkpoint_bytes_and_identity_is_entrypoint_bound(self):
        payload = probe.binary_payload(self.nonce)
        self.assertEqual(probe.sha(probe.decoded_files(payload)["main.mpy"]), probe.MPY_SHA)
        self.assertNotIn("main.py", payload["files"])
        other = {**payload, "entrypoint": "main.py"}
        self.assertNotEqual(probe.package_identity(payload), probe.package_identity(other))
        response = self.checkpoint(payload)
        self.assertEqual(probe.verify_checkpoint(response, payload)["entrypoint"], "main.mpy")
        response["files"]["main.mpy"]["data"] = "AA=="
        with self.assertRaisesRegex(ValueError, "original bytes"):
            probe.verify_checkpoint(response, payload)

    def test_source_a_establishes_nonce_and_b_asserts_same_vm_real_pir_loop(self):
        for phase in ("A", "B"):
            package = probe.source_package(self.nonce, phase, {"white": 1, "yellow": 2})
            source = package["files"]["main.py"]["data"]
            compile(source, "main.py", "exec")
            self.assertIn("from unit import PIRUnit", source)
            self.assertIn("motion=bool(unit.get_status())", source)
            self.assertIn("M5.update()", source)
            self.assertIn("time.sleep_ms(200)", source)
            self.assertEqual("sys.path.append" in source, phase == "A")
            self.assertNotIn("import main", source)
            self.assertIn("screen.height()//2+16", source)
            self.assertNotIn("fillRect(4,4", source)

    def test_marker_positions_stay_inside_round_and_rectangular_profiles(self):
        for width, height in ((320, 240), (128, 128), (135, 240), (466, 466)):
            points = probe.marker_positions(width, height)
            self.assertEqual(points["phase"], (width // 2, height // 2))
            self.assertEqual(points["motion"], (width // 2, height // 2 + 20))
            for x, y in points.values():
                self.assertLess((x - width / 2) ** 2 + (y - height / 2) ** 2, (min(width, height) / 2 - 4) ** 2)
        # Negative control: the old StopWatch corner oracle was outside the
        # circular panel and could never prove its white motion rectangle.
        self.assertGreater((8 - 233) ** 2 + (8 - 233) ** 2, 233 ** 2)

    def test_parser_requires_current_start_ready_types_and_fresh_higher_sequence(self):
        text = self.window()
        self.assertEqual(probe.parse_sample(text, self.execution, self.nonce, "A")["sequence"], 3)
        self.assertIsNone(probe.parse_sample(text, "c" * 32, self.nonce, "A"))
        self.assertIsNone(probe.parse_sample(text, self.execution, self.nonce, "B"))
        self.assertIsNone(probe.parse_sample(text, self.execution, self.nonce, "A", fresh="", minimum=0))
        self.assertIsNone(probe.parse_sample(text, self.execution, self.nonce, "A", fresh=text, minimum=3))
        self.assertIsNone(probe.parse_sample(text, self.execution, self.nonce, "A", motion=False))
        bad = {"kind": "sample", "nonce": self.nonce, "phase": "A", "sequence": True, "motion": 1}
        with self.assertRaisesRegex(ValueError, "invalid guest sample"):
            probe.parse_sample(self.window(row=bad), self.execution, self.nonce, "A")

    def test_wrong_409_and_changed_old_execution_fail_closed(self):
        probe.assert_rejection({"error": {"code": probe.ERROR_CODE}})
        for body in ({}, {"error": None}, {"error": "other"}, {"error": {"code": "other"}}):
            with self.assertRaises(ValueError):
                probe.assert_rejection(body)
        old = {"program": {"execution_id": self.execution, "state": "running"}}
        disk = {"program.json": {"sha256": "a"}}
        probe.no_execution_changed(old, copy.deepcopy(old), disk, copy.deepcopy(disk))
        for after, after_disk in (({"program": {"execution_id": "c" * 32}}, disk), (old, {**disk, "programs/new.json": {}})):
            with self.assertRaises(ValueError):
                probe.no_execution_changed(old, after, disk, after_disk)

    def test_client_uses_finite_timeout_and_logs_no_authorization(self):
        class Response(io.BytesIO):
            status = 409
            headers = {"X-Request-ID": "a" * 32, "Set-Cookie": "never-log", "Content-Type": "application/json"}
        opener = mock.Mock()
        opener.open.return_value = Response(probe.canonical({"error": {"code": probe.ERROR_CODE}}))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            client = probe.Client("http://127.0.0.1:8787", "synthetic-secret", folder, opener=opener)
            value, headers = client.request("program-revisions", "POST", {"safe": True}, expected=409)
            self.assertEqual(value["error"]["code"], probe.ERROR_CODE)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
            self.assertNotIn("set-cookie", headers)
            all_bytes = b"".join(path.read_bytes() for path in folder.iterdir())
            self.assertNotIn(b"synthetic-secret", all_bytes)
            self.assertNotIn(b"Authorization", all_bytes)

    def test_client_rejects_remote_ports_and_redirects_without_contact(self):
        for url in ("https://127.0.0.1:8787", "http://example.com:8787", "http://127.0.0.1:8000", "http://secret@localhost:8787", "http://localhost:8787/path"):
            with self.assertRaises(ValueError):
                probe.Client(url, "synthetic", Path("unused"))
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, None, {}, "http://example.com"))

    def test_unknown_preview_replays_same_key_only_for_cleanup(self):
        owned = {"creation_outcome": "unknown", "create_body": {"device_id": "cores3"}, "create_key": "original-key"}
        client = mock.Mock()
        client.json.return_value = {"preview_id": "a" * 32, "owner_epoch": "b" * 32}
        probe.recover_preview(owned, client)
        client.json.assert_called_once_with("previews", "POST", {"device_id": "cores3"}, "original-key")
        self.assertTrue(owned["creation_recovered_for_cleanup"])

    def test_unknown_ordinary_creation_is_never_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(state_dir=Path(directory), expected_runtime_sha256=probe.EXPECTED_RUNTIME)
            lane = probe.Lane(mock.Mock(), args, "cores3", "session", Path(directory))
            lane.owned["creation_outcome"] = "unknown"
            result = lane.cleanup()
            self.assertEqual(result["status"], "UNCONFIRMED")
            self.assertTrue(result["unknown_ordinary_creation_not_retried"])
            lane.client.json.assert_not_called()

    def test_owned_preview_identity_cannot_change_during_cleanup_recovery(self):
        owned = {"preview_id": "a" * 32, "owner_epoch": "b" * 32, "session_id": "c" * 32}
        for receipt in ({"preview_id": "d" * 32, "owner_epoch": "b" * 32},
                        {"preview_id": "a" * 32, "owner_epoch": "d" * 32},
                        {"preview_id": "a" * 32, "owner_epoch": "b" * 32, "session_id": "d" * 32}):
            with self.assertRaises(ValueError):
                probe.remember_preview(copy.deepcopy(owned), receipt)

    def test_zip_failure_does_not_skip_owned_preview_close(self):
        with tempfile.TemporaryDirectory() as directory:
            client = mock.Mock()
            args = SimpleNamespace(state_dir=Path(directory), expected_runtime_sha256=probe.EXPECTED_RUNTIME)
            lane = probe.Lane(client, args, "cores3", "preview", Path(directory))
            preview = {"preview_id": "a" * 32, "owner_epoch": "b" * 32, "session_id": "c" * 32}
            lane.owned.update(preview, pid=1234)
            lane.session = {"pid": 1234}
            client.json.side_effect = [preview, RuntimeError("ZIP fixture failure"), {}, {**preview, "state": "closed"}, RuntimeError("read fixture failure")]
            result = lane.cleanup()
            self.assertEqual(result["status"], "UNCONFIRMED")
            self.assertTrue(any(call.args[:2] == ("previews/" + "a" * 32 + "/close", "POST") for call in client.json.call_args_list))
            self.assertEqual(result["errors"][0]["step"], "evidence-before-stop")

    def test_zip_failure_does_not_skip_owned_session_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            client = mock.Mock()
            args = SimpleNamespace(state_dir=Path(directory), expected_runtime_sha256=probe.EXPECTED_RUNTIME)
            lane = probe.Lane(client, args, "cores3", "session", Path(directory))
            lane.owned.update(session_id="a" * 32, pid=1234)
            lane.session = {"pid": 1234}
            client.json.side_effect = [RuntimeError("ZIP fixture failure"), {}, RuntimeError("read fixture failure")]
            result = lane.cleanup()
            self.assertEqual(result["status"], "UNCONFIRMED")
            self.assertTrue(any(call.args[:2] == ("sessions/" + "a" * 32 + "?purge=0", "DELETE") for call in client.json.call_args_list))
            self.assertEqual(result["errors"][0]["step"], "evidence-before-stop")


if __name__ == "__main__":
    unittest.main()
