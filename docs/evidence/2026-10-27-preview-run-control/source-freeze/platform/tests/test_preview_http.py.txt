"""Loopback HTTP Preview facade/gates with a mock coordinator, never a guest.

The bulk-clear regression additionally invokes the real DeviceService method
against inert retained sessions. Nothing binds port 8787 or starts a device.
"""
from __future__ import annotations

import base64
import copy
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from device_service import DeviceService, ServiceError
from serve import Handler


PREVIEW_ID = "a" * 32
RUN_ID = "b" * 32
SESSION_ID = "c" * 32
EPOCH = "d" * 32
TOKEN = "synthetic-preview-http-current"
OLD_TOKEN = "synthetic-preview-http-previous"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf1cAAAAASUVORK5CYII=")
CONTROL_METHODS = ("create", "get", "list", "submit", "run", "cancel", "renew", "close", "input", "frame")
LEGACY_MUTATIONS = {
    "program": "run_program", "input": "inject", "unit-input": "unit_input",
    "qom": "qom_set", "reset": "reset", "renew": "renew", "stop": "stop",
    "network-fault": "network_fault",
}


class PreviewHttpTests(unittest.TestCase):
    def setUp(self):
        self.control = mock.Mock(spec=CONTROL_METHODS)
        self.control.create.return_value = {"preview_id": PREVIEW_ID, "state": "preparing"}
        self.control.get.return_value = {"preview_id": PREVIEW_ID, "state": "ready"}
        self.control.list.return_value = {"previews": [{"preview_id": PREVIEW_ID}]}
        self.control.submit.return_value = {"run_id": RUN_ID, "state": "queued"}
        self.control.run.return_value = {"run_id": RUN_ID, "state": "running"}
        self.control.cancel.return_value = {"run_id": RUN_ID, "state": "cancelling"}
        for method in ("renew", "close", "input"):
            getattr(self.control, method).return_value = {"action": method, "preview_id": PREVIEW_ID}
        self.frame_headers = {
            "ETag": f'"{PREVIEW_ID}:{RUN_ID}:synthetic-sample"',
            "X-Preview-ID": PREVIEW_ID, "X-Run-ID": RUN_ID,
            "X-Frame-Execution-ID": "e" * 32, "X-Frame-Revision-ID": "f" * 64,
            "X-Frame-Captured-At": "2026-10-27T00:00:00+00:00",
        }
        self.control.frame.return_value = {"headers": self.frame_headers, "png": PNG}
        self.session = self.inert_session(managed=True)
        self.service = SimpleNamespace(
            preview_control=mock.Mock(return_value=self.control),
            get_session=mock.Mock(return_value=self.session), default_ttl=1800,
            delete_session=mock.Mock(return_value={"state": "stopped"}),
        )

        class PreviewHandler(Handler):
            api_token = TOKEN
            previous_api_token = OLD_TOKEN

            def log_message(self, *args):
                pass

        PreviewHandler.service = self.service
        self.handler = PreviewHandler
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    @staticmethod
    def inert_session(*, managed):
        session = SimpleNamespace(
            id=SESSION_ID, state="running",
            firmware_id="7" * 64, firmware_sha="7" * 64, source_artifacts=[],
            management_binding={"preview_id": PREVIEW_ID, "owner_epoch": EPOCH, "expected_reference_sha256": "8" * 64} if managed else None,
            require_management_handle=mock.Mock(),
            snapshot=mock.Mock(return_value={"state": "running", "session_id": SESSION_ID}),
            wait_ready=mock.Mock(return_value={"ready": True}),
            qom_snapshot=mock.Mock(return_value={"snapshot_id": "qom-read"}),
            flash_snapshot=mock.Mock(return_value={"snapshot_id": "flash-read"}),
            program_status=mock.Mock(return_value={"program": None}),
            serial_read=mock.Mock(return_value={"text": "synthetic-host-log"}),
        )
        if managed:
            session.require_management_handle.side_effect = ServiceError("session_managed_by_preview", "managed by Preview", 409)
        for method in LEGACY_MUTATIONS.values():
            setattr(session, method, mock.Mock(return_value={"action": method}))
        return session

    def request(self, method, path, *, payload=None, raw=None, token=TOKEN, headers=None, body_length=None):
        request_headers = {"Content-Type": "application/json"}
        if token is not None:
            request_headers["Authorization"] = f"Bearer {token}"
        request_headers.update(headers or {})
        if payload is not None:
            raw = json.dumps(payload).encode("utf-8")
        if body_length is not None:
            request_headers["Content-Length"] = str(body_length)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=raw, headers=request_headers)
            response = connection.getresponse()
            data = response.read()
            result_headers = dict(response.getheaders())
            if method != "OPTIONS":
                self.assertRegex(result_headers.get("X-Request-ID", ""), r"^[0-9a-f]{32}$")
            if "application/json" in result_headers.get("Content-Type", ""):
                data = json.loads(data)
            return response.status, data, result_headers
        finally:
            connection.close()

    def assert_error(self, response, status, code):
        self.assertEqual(response[0], status, response[1])
        self.assertEqual(response[1]["error"]["code"], code)

    def assert_control_unused(self):
        for method in CONTROL_METHODS:
            getattr(self.control, method).assert_not_called()

    def test_preview_requires_configured_control_token_even_when_legacy_auth_is_open(self):
        self.handler.api_token = self.handler.previous_api_token = None
        for method, path, payload in (
            ("GET", "/api/v1/previews", None),
            ("POST", "/api/v1/previews", {"device_id": "cores3"}),
            ("GET", f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}/frame.png", None),
        ):
            with self.subTest(method=method, path=path):
                self.assert_error(self.request(method, path, payload=payload), 503, "preview_auth_unavailable")
        self.service.preview_control.assert_not_called()
        self.assert_control_unused()

    def test_missing_wrong_and_current_previous_tokens_map_only_to_local_control(self):
        for token in (None, "wrong-control-token"):
            with self.subTest(token=token):
                self.assert_error(self.request("GET", "/api/v1/previews", token=token), 401, "unauthorized")
        self.service.preview_control.assert_not_called()
        for token in (TOKEN, OLD_TOKEN):
            with self.subTest(token=token):
                self.assertEqual(self.request("GET", "/api/v1/previews", token=token)[0], 200)
        self.assertEqual(self.control.list.call_args_list, [mock.call(owner="local-control")] * 2)
        self.handler.api_token = None
        self.assertEqual(self.request("GET", "/api/v1/previews", token=OLD_TOKEN)[0], 200)

    def test_create_and_submit_forward_original_payload_key_owner_and_return_202_locations(self):
        create_payload = {"device_id": "cores3", "unknown": {"kept": True}, "owner": "untrusted-body"}
        status, body, headers = self.request("POST", "/api/v1/previews", payload=create_payload, headers={"Idempotency-Key": "create-key"})
        self.assertEqual((status, body), (202, self.control.create.return_value))
        self.assertEqual(headers["Location"], f"/api/v1/previews/{PREVIEW_ID}")
        self.control.create.assert_called_once_with(create_payload, owner="local-control", idempotency_key="create-key")
        submit_payload = {"revision_id": "f" * 64, "expected_owner_epoch": EPOCH, "expected_generation": 0, "unknown": [1, 2]}
        status, body, headers = self.request("POST", f"/api/v1/previews/{PREVIEW_ID}/runs", payload=submit_payload, headers={"Idempotency-Key": "run-key"})
        self.assertEqual((status, body), (202, self.control.submit.return_value))
        self.assertEqual(headers["Location"], f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}")
        self.control.submit.assert_called_once_with(PREVIEW_ID, submit_payload, owner="local-control", idempotency_key="run-key")
        self.service.get_session.assert_not_called()

    def test_missing_idempotency_key_is_forwarded_empty_for_coordinator_validation(self):
        self.control.create.side_effect = ServiceError("invalid_idempotency_key", "Idempotency-Key required", 400)
        payload = {"device_id": "cores3"}
        self.assert_error(self.request("POST", "/api/v1/previews", payload=payload), 400, "invalid_idempotency_key")
        self.control.create.assert_called_once_with(payload, owner="local-control", idempotency_key="")

    def test_duplicate_idempotency_headers_are_rejected_before_create_or_submit(self):
        raw = b'{"device_id":"cores3"}'
        for path in ("/api/v1/previews", f"/api/v1/previews/{PREVIEW_ID}/runs"):
            for values in (("first", "second"), ("same", "same")):
                with self.subTest(path=path, values=values):
                    connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
                    try:
                        connection.putrequest("POST", path)
                        connection.putheader("Authorization", f"Bearer {TOKEN}")
                        connection.putheader("Content-Type", "application/json")
                        for value in values:
                            connection.putheader("Idempotency-Key", value)
                        connection.putheader("Content-Length", str(len(raw)))
                        connection.endheaders(raw)
                        response = connection.getresponse()
                        body = json.loads(response.read())
                        self.assertEqual((response.status, body["error"]["code"]), (400, "invalid_idempotency_key"))
                    finally:
                        connection.close()
        self.assert_control_unused()

    def test_query_and_action_routes_forward_exact_target_payload_and_owner(self):
        for path, method, arguments in (
            ("/api/v1/previews", "list", ()),
            (f"/api/v1/previews/{PREVIEW_ID}", "get", (PREVIEW_ID,)),
            (f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}", "run", (PREVIEW_ID, RUN_ID)),
        ):
            with self.subTest(method=method):
                self.assertEqual(self.request("GET", path)[0], 200)
                getattr(self.control, method).assert_called_once_with(*arguments, owner="local-control")
        payload = {"expected_owner_epoch": EPOCH, "unknown": {"forward": "unchanged"}}
        for action, path, arguments, expected_status in (
            ("cancel", f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}/cancel", (PREVIEW_ID, RUN_ID, payload), 202),
            ("renew", f"/api/v1/previews/{PREVIEW_ID}/renew", (PREVIEW_ID, payload), 200),
            ("close", f"/api/v1/previews/{PREVIEW_ID}/close", (PREVIEW_ID, payload), 202),
            ("input", f"/api/v1/previews/{PREVIEW_ID}/input", (PREVIEW_ID, payload), 200),
        ):
            with self.subTest(action=action):
                self.assertEqual(self.request("POST", path, payload=payload)[0], expected_status)
                getattr(self.control, action).assert_called_once_with(*arguments, owner="local-control")

    def test_duplicate_json_is_rejected_at_every_preview_body_route_before_coordinator(self):
        paths = (
            "/api/v1/previews", f"/api/v1/previews/{PREVIEW_ID}/runs",
            f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}/cancel",
            *(f"/api/v1/previews/{PREVIEW_ID}/{action}" for action in ("renew", "close", "input")),
        )
        for path in paths:
            for raw in (b'{"value":1,"value":2}', b'{"nested":{"value":1,"value":2}}'):
                with self.subTest(path=path, raw=raw):
                    self.assert_error(self.request("POST", path, raw=raw), 400, "invalid_json")
        self.assert_control_unused()

    def test_preview_json_object_and_one_mib_body_limit_are_handler_boundaries(self):
        for raw in (b"[]", b"{}", b"null", b'{"bad":'):
            with self.subTest(raw=raw):
                self.assert_error(self.request("POST", "/api/v1/previews", raw=raw), 400, "invalid_json")
        self.assert_error(self.request("POST", "/api/v1/previews", body_length=1048577), 413, "body_too_large")
        self.assert_control_unused()
        raw = b'{"device_id":"cores3"}'
        self.assertEqual(self.request("POST", "/api/v1/previews", raw=raw + b" " * (1048576 - len(raw)))[0], 202)

    def test_frame_png_headers_and_etag_are_forwarded_and_cors_visible(self):
        path = f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}/frame.png"
        status, body, headers = self.request("GET", path)
        self.assertEqual((status, body, headers["Content-Type"]), (200, PNG, "image/png"))
        for name, value in self.frame_headers.items():
            self.assertEqual(headers[name], value)
        exposed = {value.strip() for value in headers["Access-Control-Expose-Headers"].split(",")}
        self.assertTrue({"X-Preview-ID", "X-Run-ID", "ETag"} <= exposed)
        self.control.frame.assert_called_once_with(PREVIEW_ID, RUN_ID, owner="local-control", max_age_ms=0)
        for condition in (self.frame_headers["ETag"], "W/" + self.frame_headers["ETag"], '"different", ' + self.frame_headers["ETag"], "*"):
            with self.subTest(condition=condition):
                self.control.frame.reset_mock()
                status, body, headers = self.request("GET", path + "?max_age_ms=1000", headers={"If-None-Match": condition})
                self.assertEqual((status, body), (304, b""))
                self.assertEqual(headers["X-Preview-ID"], PREVIEW_ID)
                self.assertEqual(headers["X-Run-ID"], RUN_ID)
                self.assertEqual(headers["ETag"], self.frame_headers["ETag"])
                self.control.frame.assert_called_once_with(PREVIEW_ID, RUN_ID, owner="local-control", max_age_ms=1000)

    def test_frame_identity_error_is_checked_before_conditional_304_and_invalid_age_never_captures(self):
        path = f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}/frame.png"
        self.control.frame.side_effect = ServiceError("preview_run_changed", "run changed during capture", 409)
        self.assert_error(self.request("GET", path, headers={"If-None-Match": "*"}), 409, "preview_run_changed")
        self.control.frame.reset_mock()
        for query in ("max_age_ms=-1", "max_age_ms=1001", "max_age_ms=1.0", "max_age_ms=1e2", "max_age_ms=%EF%BC%91", "max_age_ms=0&max_age_ms=1", "unknown=1"):
            with self.subTest(query=query):
                self.assert_error(self.request("GET", path + "?" + query), 400, "invalid_frame_age")
        self.control.frame.assert_not_called()

    def test_unknown_routes_and_coordinator_errors_keep_http_error_contract(self):
        for method, path in (
            ("DELETE", f"/api/v1/previews/{PREVIEW_ID}"),
            ("POST", f"/api/v1/previews/{PREVIEW_ID}/unknown"),
            ("GET", f"/api/v1/previews/{PREVIEW_ID}/runs/{RUN_ID}/unknown"),
        ):
            with self.subTest(method=method, path=path):
                self.assert_error(self.request(method, path, payload={"value": 1} if method == "POST" else None), 404, "not_found")
        self.assert_control_unused()
        self.control.get.side_effect = ServiceError("preview_storage_unavailable", "storage unavailable", 503)
        self.assert_error(self.request("GET", f"/api/v1/previews/{PREVIEW_ID}"), 503, "preview_storage_unavailable")

    def test_managed_legacy_mutations_and_delete_are_blocked_before_body_or_session_operation(self):
        binding = copy.deepcopy(self.session.management_binding)
        for action in LEGACY_MUTATIONS:
            with self.subTest(action=action):
                response = self.request("POST", f"/api/v1/sessions/{SESSION_ID}/{action}", raw=b'{"management_handle":{},"preview_id":"forged","owner_epoch":"forged"}')
                self.assert_error(response, 409, "session_managed_by_preview")
        self.assert_error(self.request("POST", f"/api/v1/sessions/{SESSION_ID}/program", raw=b'{"malformed":'), 409, "session_managed_by_preview")
        self.assert_error(self.request("DELETE", f"/api/v1/sessions/{SESSION_ID}?purge=1"), 409, "session_managed_by_preview")
        self.assertEqual(self.session.require_management_handle.call_args_list, [mock.call()] * 10)
        for method in LEGACY_MUTATIONS.values():
            getattr(self.session, method).assert_not_called()
        self.service.delete_session.assert_not_called()
        self.assertEqual(self.session.management_binding, binding)

    def test_managed_read_actions_preserve_binding_and_do_not_require_mutation_handle(self):
        binding = copy.deepcopy(self.session.management_binding)
        self.assertEqual(self.request("POST", f"/api/v1/sessions/{SESSION_ID}/wait", payload={"ready": True})[0], 200)
        self.session.wait_ready.assert_called_once_with({"ready": True})
        self.assertEqual(self.request("POST", f"/api/v1/sessions/{SESSION_ID}/qom-snapshot", payload={"path": "/machine", "depth": 3, "max_nodes": 12})[0], 200)
        self.session.qom_snapshot.assert_called_once_with(path="/machine", depth=3, max_nodes=12)
        self.assertEqual(self.request("POST", f"/api/v1/sessions/{SESSION_ID}/flash-snapshot")[0], 200)
        self.session.flash_snapshot.assert_called_once_with()
        self.assertEqual(self.request("GET", f"/api/v1/sessions/{SESSION_ID}/program")[0], 200)
        self.assertEqual(self.request("GET", f"/api/v1/sessions/{SESSION_ID}/serial")[0], 200)
        self.session.require_management_handle.assert_not_called()
        self.assertEqual(self.session.management_binding, binding)

    def test_unmanaged_legacy_mutations_delete_and_open_auth_remain_compatible(self):
        self.session = self.inert_session(managed=False)
        self.service.get_session.return_value = self.session
        payload = {"ttl_seconds": 60, "purge": False, "retain_flash": True}
        for action, method in LEGACY_MUTATIONS.items():
            with self.subTest(action=action):
                self.assertEqual(self.request("POST", f"/api/v1/sessions/{SESSION_ID}/{action}", payload=payload)[0], 200)
                getattr(self.session, method).assert_called_once()
        self.session.renew.assert_called_once_with(60)
        self.session.stop.assert_called_once_with(purge=False, retain_flash=True)
        self.assertEqual(self.request("DELETE", f"/api/v1/sessions/{SESSION_ID}?purge=1&retain_flash=1")[0], 200)
        self.service.delete_session.assert_called_once_with(SESSION_ID, purge=True, retain_flash=True)
        self.session.require_management_handle.assert_not_called()
        self.handler.api_token = self.handler.previous_api_token = None
        self.assertEqual(self.request("GET", f"/api/v1/sessions/{SESSION_ID}/program", token=None)[0], 200)

    def test_bulk_clear_retains_managed_history_using_real_service_method(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        service = object.__new__(DeviceService)
        service.state_dir = Path(temporary.name)
        service._lock = threading.RLock()
        managed = self.inert_session(managed=True)
        legacy = self.inert_session(managed=False)
        managed.state = legacy.state = "stopped"
        legacy.id = "9" * 32
        managed.dir = service.state_dir / "sessions" / managed.id
        legacy.dir = service.state_dir / "sessions" / legacy.id
        managed.dir.mkdir(parents=True)
        legacy.dir.mkdir(parents=True)
        for session in (managed, legacy):
            record = {"session_id": session.id, "firmware_id": "7" * 64, "firmware_sha256": "7" * 64, "source_artifacts": []}
            if session.management_binding is not None:
                record["management_binding"] = session.management_binding
            (session.dir / "session.json").write_text(json.dumps(record), encoding="utf-8")
        history = managed.dir / "retained-history.txt"
        history.write_text("synthetic retained evidence", encoding="utf-8")
        service._sessions = {managed.id: managed, legacy.id: legacy}
        self.handler.service = service
        response = self.request("DELETE", "/api/v1/sessions?state=stopped&purge=1")
        self.assertEqual(response[0], 200, response[1])
        managed.stop.assert_not_called()
        legacy.stop.assert_called_once()
        self.assertIn(managed.id, response[1]["protected_sessions"])
        self.assertEqual(response[1]["cleared"], 1)
        self.assertIs(service._sessions.get(managed.id), managed)
        self.assertNotIn(legacy.id, service._sessions)
        self.assertTrue(history.is_file())


if __name__ == "__main__":
    unittest.main()
