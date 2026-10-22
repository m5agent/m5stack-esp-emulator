#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from device_service import DeviceService
from serve import Handler


class DeviceServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = DeviceService(
            state_dir=Path(self.tmp.name),
            max_sessions=2,
            max_per_device=1,
        )

    def tearDown(self):
        self.service.close_all()
        self.tmp.cleanup()

    def test_catalog_enables_tab5_and_excludes_cardputer_zero(self):
        payload = self.service.list_devices()
        rows = {row["device_id"]: row for row in payload["devices"]}
        self.assertEqual(len(rows), 14)
        self.assertEqual(sum(row["creatable"] for row in rows.values()), 13)
        self.assertTrue(rows["tab5"]["supported"])
        self.assertTrue(rows["tab5"]["creatable"])
        self.assertEqual(rows["tab5"]["peripheral_status"], "partial")
        self.assertTrue(rows["tab5"]["warnings"])
        self.assertFalse(rows["tab5"]["features"]["qom"])
        self.assertFalse(rows["cardputer-zero"]["supported"])
        self.assertFalse(rows["tab5"]["features"]["network"])
        self.assertFalse(payload["network_enabled"])

    def test_merged_firmware_is_padded_to_device_flash(self):
        artifact = self.service.upload_artifact(b"\xe9" + b"X" * 1023)
        firmware = self.service.create_firmware(
            {
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            }
        )
        self.assertEqual(firmware["size"], 8 << 20)
        self.assertEqual(
            self.service.firmware.path(firmware["firmware_id"]).stat().st_size,
            8 << 20,
        )

    def test_segmented_firmware_rejects_overlap(self):
        artifact = self.service.upload_artifact(b"APP")
        with self.assertRaises(Exception) as context:
            self.service.create_firmware(
                {
                    "device_id": "sticks3",
                    "kind": "segmented",
                    "segments": [
                        {"offset": "0x10000", "artifact_id": artifact["artifact_id"]},
                        {"offset": "0x10001", "artifact_id": artifact["artifact_id"]},
                    ],
                }
            )
        self.assertEqual(getattr(context.exception, "code", None), "overlapping_segments")

    def test_capacity_reports_isolated_leases(self):
        capacity = self.service.capacity()
        self.assertEqual(capacity["max_sessions"], 2)
        self.assertEqual(capacity["max_per_device"], 1)
        self.assertEqual(capacity["modes"]["network"], "disabled")
        self.assertEqual(capacity["modes"]["tab5"], "enabled-partial")


class DeviceServiceHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = DeviceService(state_dir=Path(cls.tmp.name))
        Handler.service = cls.service
        Handler.api_token = None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.service.close_all()
        Handler.service = None
        cls.tmp.cleanup()

    def request(self, path, *, method="GET", data=None, headers=None):
        request = Request(self.base + path, method=method, data=data, headers=headers or {})
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)

    def test_v1_catalog_and_capacity(self):
        status, payload = self.request("/api/v1/devices")
        self.assertEqual(status, 200)
        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(len(payload["devices"]), 14)
        status, capacity = self.request("/api/v1/capacity")
        self.assertEqual(status, 200)
        self.assertEqual(capacity["modes"]["network"], "disabled")

    def test_openapi_is_served(self):
        with urlopen(self.base + "/api/v1/openapi.yaml", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"openapi: 3.1.0", response.read())

    def test_artifact_and_firmware_round_trip(self):
        status, artifact = self.request(
            "/api/v1/artifacts",
            method="POST",
            data=b"\xe9" + b"A" * 31,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": "probe.bin",
            },
        )
        self.assertEqual(status, 201)
        body = json.dumps(
            {
                "device_id": "sticks3",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            }
        ).encode()
        status, firmware = self.request(
            "/api/v1/firmware",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(firmware["device_id"], "sticks3")
        status, fetched = self.request(f"/api/v1/firmware/{firmware['firmware_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(fetched["sha256"], firmware["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
