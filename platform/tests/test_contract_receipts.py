"""Receipt failures must not block owned guest teardown or change identities."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2/api_sweep"))
from run_contract_with_receipts import ReceiptClient, retained_serial_prefix
from run_device_api import Client


class ContractReceiptTests(unittest.TestCase):
    def test_history_serial_keeps_crlf_and_rejects_changed_or_empty_prefix(self):
        archived = b"boot\r\nsample\r\n"
        self.assertTrue(retained_serial_prefix(archived, "boot\r\nsample\r\nstop\r\n"))
        self.assertFalse(retained_serial_prefix(archived, "boot\r\nchanged\r\n"))
        self.assertFalse(retained_serial_prefix(b"", "anything"))

    def client(self):
        client = object.__new__(ReceiptClient)
        client.owned = {"owned"}
        client.previews = {"preview": "owned"}
        client.receipts = {}
        client.receipt_errors = []
        return client

    def test_failed_receipt_does_not_prevent_session_stop_or_preview_close(self):
        for method, path in (("DELETE", "/sessions/owned?purge=0"),
                             ("POST", "/previews/preview/close")):
            with self.subTest(path=path):
                client = self.client()
                response = ({"status": 200}, {"session_id": "owned", "state": "stopped"})
                with mock.patch.object(client, "prepare_stop", side_effect=RuntimeError("missing proof")), \
                     mock.patch.object(Client, "call", return_value=response) as dispatch:
                    self.assertEqual(client.call(method, path), response)
                dispatch.assert_called_once_with(method, path)
                self.assertEqual(client.receipt_errors, ["missing proof"])

    def test_zip_must_match_the_frozen_guest_before_accepting_evidence(self):
        client = self.client()
        client.receipts["owned"] = {"firmware_sha256": "a" * 64, "pid": 7, "evidence": []}
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"session": {
                "session_id": "owned", "state": "running", "pid": 7, "firmware_sha256": "b" * 64,
            }}))
        with mock.patch.object(client, "observe"), mock.patch.object(client, "verify_runtime") as verify:
            with self.assertRaisesRegex(RuntimeError, "ZIP changed the guest identity"):
                client.evidence("owned", archive_bytes.getvalue(), "c" * 64)
            verify.assert_not_called()
        self.assertEqual(client.receipts["owned"]["evidence"], [])


if __name__ == "__main__":
    unittest.main()
