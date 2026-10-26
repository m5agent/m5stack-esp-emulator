"""Preview integration against inert files/QMP callbacks, never a real guest."""
from dataclasses import replace
import http.client
import io
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest import mock
import zipfile

import device_service as module
from device_service import ServiceError
from serve import Handler
from test_device_program_runtime import _ProgramFixture


class FramePreviewTests(_ProgramFixture):
    def display_session(self):
        session = self.session(transport=None)
        session.spec = replace(session.spec, display={"width": 1, "height": 1})
        self.captures = 0

        def qmp(name, **kwargs):
            if name == "screendump":
                self.captures += 1
                Path(kwargs["filename"]).write_bytes(b"P6\n1 1\n255\n" + bytes((self.captures % 256, 2, 3)))
            return {}

        session._qmp_call = mock.Mock(side_effect=qmp)
        return session

    def test_default_capture_remains_fresh_and_preview_is_explicit(self):
        session = self.display_session()
        self.assertNotEqual(session.frame_png()[0], session.frame_png()[0])
        self.assertEqual(self.captures, 2)
        first = session.preview_frame(1000)
        self.assertEqual(first, session.preview_frame(1000))
        self.assertEqual(self.captures, 3)
        self.assertEqual(first["source"], "live")
        self.assertIsNotNone(first["captured_at"])
        self.assertNotIn("captured_monotonic", first)
        self.assertNotIn("captured_monotonic", json.loads(session.last_frame_meta_path.read_text()))

    def test_program_and_reset_invalidate_prior_sample(self):
        session = self.display_session()
        first = session.preview_frame(1000)
        session.program_transport = "uart-repl"
        self.console(session)
        self.run_stub()
        program = session.run_program({"source": "print('new')", "expected_execution_id": None})["program"]
        next_frame = session.preview_frame(1000)
        self.assertGreater(next_frame["capture_seq"], first["capture_seq"])
        self.assertEqual(next_frame["execution_id"], program["execution_id"])
        self.assertEqual(next_frame["revision_id"], program["revision_id"])
        session.reset()
        after_reset = session.preview_frame(1000)
        self.assertGreater(after_reset["capture_seq"], next_frame["capture_seq"])
        self.assertEqual(after_reset["program_state"], "interrupted")

    def test_stop_during_capture_does_not_publish_old_live_frame(self):
        session = self.display_session()
        entered, release = threading.Event(), threading.Event()
        original = session._qmp_call.side_effect

        def blocked(name, **kwargs):
            if name == "screendump" and not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(3))
            return original(name, **kwargs)

        session._qmp_call.side_effect = blocked
        capture_thread, capture_result = self.background(lambda: session.preview_frame(1000))
        self.assertTrue(entered.wait(2))
        stop_thread, stop_result = self.background(session.stop)
        self.assertTrue(session._stop_event.wait(2))
        release.set()
        capture_thread.join(3)
        stop_thread.join(3)
        self.assertFalse(capture_thread.is_alive())
        self.assertFalse(stop_thread.is_alive())
        self.assertIsInstance(capture_result.get("error"), ServiceError)
        self.assertEqual(capture_result["error"].code, "frame_generation_changed")
        self.assertEqual(stop_result["value"]["state"], "stopped")
        history = session.preview_frame(1000)
        meta = json.loads(session.last_frame_meta_path.read_text())
        self.assertEqual(history["source"], "persisted")
        self.assertEqual(history["captured_at"], meta["captured_at"])

    def test_legacy_history_keeps_unknown_capture_time_and_context(self):
        session = self.display_session()
        session.state = "stopped"
        session.last_frame_path.write_bytes(b"historical png")
        session.last_frame_meta_path.write_text('{"width":1,"height":1}')
        history = session.preview_frame(1000)
        self.assertEqual(history["source"], "persisted")
        self.assertIsNone(history["captured_at"])
        self.assertIsNone(history["execution_id"])
        self.assertEqual(self.captures, 0)

    def test_capture_error_never_returns_a_previous_success(self):
        session = self.display_session()
        session.preview_frame(1000)
        session._preview_frames.invalidate()
        session._qmp_call.side_effect = ServiceError("qmp_timeout", "timeout", 504)
        self.assert_service_error(lambda: session.preview_frame(1000), code="qmp_timeout", status=504)

    def test_internal_ttl_clock_is_absent_from_wait_and_evidence(self):
        session = self.display_session()
        result = session.wait_ready({"ready": {"frame_nonblank": True,
                                               "frame_min_bytes": 1, "frame_min_nonblack_pixels": 1}})
        self.assertTrue(result["ready"])
        self.assertNotIn("captured_monotonic", result["frame"])
        self.service.get_device = lambda device_id: {"device_id": device_id}
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"frames"}))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertNotIn("captured_monotonic", manifest["frame"])
            self.assertEqual(manifest["frame"]["source"], "live")

    def test_live_process_exit_changes_cache_identity(self):
        session = self.display_session()
        proc = SimpleNamespace(poll=mock.Mock(return_value=None))
        session._proc = proc
        session.preview_frame(1000)
        proc.poll.return_value = 1
        session._qmp_call.side_effect = ServiceError("session_not_running", "exited", 409)
        self.assert_service_error(lambda: session.preview_frame(1000), code="session_not_running")
        session._proc = None

    def test_non_qemu_preview_fails_without_hiding_legacy_capture(self):
        session = self.display_session()
        for runtime in ("tab5", "network"):
            session.runtime = runtime
            self.assert_service_error(lambda: session.preview_frame(125), code="frame_preview_not_available")
        session.runtime = "qemu"

    def test_http_conditional_preview_and_default_fresh_semantics(self):
        session = self.display_session()
        local = type("PreviewHandler", (Handler,), {"service": SimpleNamespace(get_session=lambda _: session),
                                                    "api_token": None, "previous_api_token": None,
                                                    "log_message": lambda *args: None})
        server = ThreadingHTTPServer(("127.0.0.1", 0), local)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def get(suffix="", headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request("GET", f"/api/v1/sessions/{session.id}/frame.png{suffix}", headers=headers or {})
                response = conn.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                conn.close()

        try:
            status, headers, png = get("?max_age_ms=1000")
            self.assertEqual(status, 200)
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertEqual(headers["X-Frame-Source"], "live")
            status, same, empty = get("?max_age_ms=1000", {"If-None-Match": 'W/' + headers["ETag"]})
            self.assertEqual(status, 304)
            self.assertEqual(empty, b"")
            self.assertEqual(same["X-Frame-Capture-Seq"], headers["X-Frame-Capture-Seq"])
            self.assertEqual(self.captures, 1)
            status, _, fresh = get("", {"If-None-Match": headers["ETag"]})
            self.assertEqual(status, 200)
            self.assertNotEqual(fresh, png)
            self.assertEqual(self.captures, 2)
            for age in ("-1", "1.5", "1001", "1&max_age_ms=2", "1" * 5000):
                status, _, body = get("?max_age_ms=" + age)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["error"]["code"], "invalid_frame_age")
            self.assertEqual(self.captures, 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)
