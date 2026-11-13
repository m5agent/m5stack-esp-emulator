"""Independent pixel oracles and same-capture HTTP/history orientation contracts."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import struct
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile
import zlib

from device_service import ServiceError
from frame_cache import CaptureResult, FrameCache
from frame_presentation import (FramePresentation, bind_presentation,
                                frame_representation, presentation_from_controller)
from run_profile_ui_test import write_rgb_png
from serve import Handler
from test_device_program_runtime import _ProgramFixture


def controller(**overrides):
    return {"schema_version": 1, "supported": True, "generation": 1,
            "madctl": 0, "apply_madctl": True, "glass_rotation": 0,
            "memory_width": 240, "memory_height": 320, "width": 2, "height": 3,
            "offset_x": 52, "offset_y": 40, **overrides}


def pixel_labels(png):
    # Fixtures use red byte as their asymmetric pixel label; decode service PNG.
    width, height = struct.unpack(">II", png[16:24])
    offset, compressed = 8, bytearray()
    while offset < len(png):
        size = struct.unpack(">I", png[offset:offset + 4])[0]
        if png[offset + 4:offset + 8] == b"IDAT":
            compressed.extend(png[offset + 8:offset + 8 + size])
        offset += size + 12
    raw = zlib.decompress(compressed)
    return [[raw[y * (width * 3 + 1) + 1 + x * 3] for x in range(width)]
            for y in range(height)]


class PresentationTests(unittest.TestCase):
    def test_driver_rotation_table_glass_mount_and_mirrors(self):
        # M5GFX Panel_LCD::getMadCtl rotations 0..3; extra RGB/refresh bits
        # must not change the axes. All four other MX/MY/MV states are mirrors.
        for madctl, angle in ((0x00, 0), (0x64, 270), (0xd4, 180), (0xb0, 90)):
            for glass in range(4):
                with self.subTest(madctl=madctl, glass=glass):
                    value = presentation_from_controller(controller(madctl=madctl | 8, glass_rotation=glass))
                    self.assertEqual(value.rotation_cw, (angle - 90 * glass) % 360)
                    self.assertFalse(value.mirrored)
        for madctl in (0x20, 0x40, 0x80, 0xe0):
            value = presentation_from_controller(controller(madctl=madctl))
            self.assertEqual(value.status, "mirrored")
            self.assertIsNone(value.rotation_cw)
        self.assertEqual(presentation_from_controller(controller(madctl=0xe0, apply_madctl=False)).rotation_cw, 0)
        for value in ({}, controller(supported=False), controller(madctl=True), "not-json"):
            self.assertEqual(presentation_from_controller(value).status, "unknown")

    def test_generation_guards_aba_and_frame_geometry(self):
        first = presentation_from_controller(controller())
        after = presentation_from_controller(controller(generation=3))
        self.assertEqual(bind_presentation(first, after, 2, 3).status, "unstable")
        self.assertEqual(bind_presentation(first, first, 3, 2).status, "unknown")
        self.assertEqual(bind_presentation(first, first, 2, 3), first)

    def test_cache_metadata_is_immutable_and_same_sample(self):
        value = presentation_from_controller(controller(madctl=0xa0))
        cache = FrameCache()
        first = cache.get(lambda: CaptureResult(b"png", 2, 3, presentation=value), generation=1, max_age_ms=1000)
        public = first.as_dict()
        public["presentation"]["controller"]["madctl"] = 0
        second = cache.get(lambda: self.fail("must reuse capture"), generation=1, max_age_ms=1000)
        self.assertEqual(second.presentation.rotation_cw, 90)
        self.assertEqual(second.as_dict()["presentation"]["controller"]["madctl"], 0xa0)


class FramePresentationIntegrationTests(_ProgramFixture):
    def test_discovers_c6_panel_observer_on_machine_child(self):
        session = self.session(transport=None)
        state = controller(madctl=0x6c, width=135, height=240)
        def qmp(name, **args):
            if name == "qom-get":
                self.assertEqual(args["path"], "/machine/nesso-panel")
                return {"return": json.dumps(state)}
            listing = {"/machine/unattached": [],
                       "/machine": [{"name": "nesso-panel", "type": "child<esp32c6.nesso-panel>"}],
                       "/machine/nesso-panel": [{"name": "frame-presentation", "type": "string"}]}
            return {"return": listing[args["path"]]}
        session._qmp_call = mock.Mock(side_effect=qmp)
        self.assertEqual(session._frame_presentation().rotation_cw, 270)
        self.assertEqual(session._frame_presentation().rotation_cw, 270)
        self.assertEqual(session._qmp_call.call_count, 5)

    def display(self, *, modern=True):
        session = self.session(transport=None)
        session.spec = replace(session.spec, display={"width": 2, "height": 3})
        self.state = controller(madctl=0xa0)
        self.capture_hook = None
        self.captures = 0
        def qmp(name, **args):
            if name == "qom-list":
                return {"return": ([{"name": "panel", "type": "child<m5.spi-panel>"}]
                        if args["path"] == "/machine/unattached" else
                        [{"name": "frame-presentation", "type": "string"}] if modern else [])}
            if name == "qom-get":
                return {"return": json.dumps(self.state)}
            if name == "screendump":
                self.captures += 1
                Path(args["filename"]).write_bytes(b"P6\n2 3\n255\n" + bytes(v for label in range(1, 7) for v in (label, 0, 0)))
                if self.capture_hook:
                    self.capture_hook()
            return {}
        session._qmp_call = mock.Mock(side_effect=qmp)
        return session

    @contextmanager
    def http(self, session):
        handler = type("OrientationHandler", (Handler,), {"service": SimpleNamespace(get_session=lambda _: session),
                       "api_token": None, "previous_api_token": None, "log_message": lambda *args: None})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def get(query="", headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                connection.request("GET", "/api/v1/sessions/test/frame.png" + query, headers=headers or {})
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()
        try:
            yield get
        finally:
            server.shutdown(); server.server_close(); thread.join(3)

    def test_asymmetric_pixels_four_rotations_and_default_unchanged(self):
        session = self.display()
        expected = {0: [[1, 2], [3, 4], [5, 6]], 90: [[5, 3, 1], [6, 4, 2]],
                    180: [[6, 5], [4, 3], [2, 1]], 270: [[2, 4, 6], [1, 3, 5]]}
        original = session.frame_metrics()["png"]
        for bits, angle in ((0, 0), (0xa0, 90), (0xc0, 180), (0x60, 270)):
            self.state["madctl"] = bits
            raw = session.frame_metrics()
            self.assertEqual(raw["png"], original)
            output = frame_representation(raw, "display")
            self.assertEqual(pixel_labels(output["png"]), expected[angle])
            self.assertEqual(output["raw_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(raw["presentation"]["rotation_cw"], angle)

    def test_http_same_raw_sample_derivative_and_orientation_only_304(self):
        session = self.display()
        with self.http(session) as get:
            status, headers, raw = get("?max_age_ms=1000")
            self.assertEqual(status, 200)
            self.assertEqual(headers["X-Frame-Rotation"], "90")
            self.assertEqual(headers["X-Frame-Coordinate-Space"], "panel")
            status, display_headers, oriented = get("?max_age_ms=1000&orient=display")
            self.assertEqual(status, 200)
            self.assertEqual(display_headers["X-Frame-Capture-Seq"], headers["X-Frame-Capture-Seq"])
            self.assertEqual(display_headers["X-Frame-Raw-SHA256"], headers["X-Frame-SHA256"])
            self.assertEqual(pixel_labels(oriented), [[5, 3, 1], [6, 4, 2]])
            self.assertEqual(self.captures, 1)
            self.state.update(madctl=0xc0, generation=2)
            session._preview_frames.invalidate()
            status, changed, body = get("?max_age_ms=1000", {"If-None-Match": headers["ETag"]})
            self.assertEqual((status, body), (304, b""))
            self.assertEqual(changed["X-Frame-Rotation"], "180")
            self.assertEqual(changed["ETag"], headers["ETag"])
            self.assertIn("X-Frame-Presentation", changed["Access-Control-Expose-Headers"])
            for query in ("?orient=bad", "?orient=", "?orient=display&orient=", "?orient=display&orient=panel"):
                status, _, _ = get(query)
                self.assertEqual(status, 400)
            self.assertEqual(self.captures, 2)

    def test_unstable_mirrored_legacy_and_no_display_fail_explicitly(self):
        session = self.display()
        def change(): self.state["generation"] += 2  # Includes A -> B -> A.
        self.capture_hook = change
        frame = session.frame_metrics()
        self.assertEqual(frame["presentation"]["status"], "unstable")
        self.assert_service_error(lambda: frame_representation(frame, "display"), code="frame_orientation_unavailable")
        self.capture_hook = None
        self.state["madctl"] = 0x20
        self.assert_service_error(lambda: frame_representation(session.frame_metrics(), "display"), code="frame_orientation_unavailable")
        session = self.display(modern=False)
        frame = session.frame_metrics()
        self.assertEqual(frame["presentation"]["status"], "unknown")
        self.assertEqual(frame_representation(frame)["png"], frame["png"])
        self.assert_service_error(lambda: frame_representation(frame, "display"), code="frame_orientation_unavailable")
        session.spec = replace(session.spec, display=None)
        self.assert_service_error(session.frame_metrics, code="display_not_available")

    def test_retained_metadata_and_evidence_bind_original_frame(self):
        session = self.display()
        frame = session.frame_metrics(force_persist=True)
        self.service.get_device = lambda device_id: {"device_id": device_id}
        with zipfile.ZipFile(io.BytesIO(session.evidence_bundle({"frames"}))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["frame"]["presentation"], frame["presentation"])
            self.assertEqual(archive.read("frames/current.png"), frame["png"])
        session.state = "stopped"
        self.state["madctl"] = 0
        history = session.preview_frame(1000)
        self.assertEqual(history["presentation"], frame["presentation"])
        self.assertEqual(frame_representation(history, "display")["width"], 3)
        legacy = dict(history, presentation=None)
        self.assertEqual(frame_representation(legacy)["presentation"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
