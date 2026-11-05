#!/usr/bin/env python3
import json
import functools
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
from serve import Handler


class ServeWorkbenchRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        web = root / "platform/web"
        web.mkdir(parents=True)
        cls.index = b'<!doctype html><script src="/platform/web/public.js"></script>'
        cls.sessions = b'<!doctype html><main>existing session console</main>'
        (web / "index.html").write_bytes(cls.index)
        (web / "sessions.html").write_bytes(cls.sessions)
        (web / "public.js").write_bytes(b"export const canonical = true;\n")

        class RouteHandler(Handler):
            def _get_service(self):
                raise AssertionError("static aliases must not allocate or adopt a session")

            def _handle_v1(self, method, path, query):
                self._json({"method": method, "path": path, "query": query})

        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(RouteHandler, directory=str(root))
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.tmp.cleanup()

    def test_root_and_existing_workbench_urls_serve_one_canonical_page(self):
        for path in ("/", "/index.html", "/platform/web/", "/platform/web/index.html"):
            with self.subTest(path=path), urlopen(self.base + path, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "text/html")
                self.assertEqual(response.read(), self.index)
                self.assertIsNone(response.headers.get("Location"))

    def test_workbench_query_stays_on_requested_url_without_redirect(self):
        path = "/?device=cores3&mode=service&view=sessions"
        with urlopen(self.base + path, timeout=5) as response:
            self.assertEqual(response.url, self.base + path)
            self.assertEqual(response.read(), self.index)

    def test_legacy_session_urls_preserve_console_and_query_without_adoption(self):
        query = "?state=running&session=existing-session"
        for path in ("/sessions", "/sessions/", "/sessions.html", "/platform/web/sessions.html"):
            with self.subTest(path=path), urlopen(self.base + path + query, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.url, self.base + path + query)
                self.assertEqual(response.read(), self.sessions)
                self.assertIsNone(response.headers.get("Location"))

    def test_head_uses_the_same_aliases_without_sending_html_body(self):
        for path, expected in (("/", self.index), ("/index.html", self.index),
                               ("/sessions", self.sessions), ("/sessions.html", self.sessions)):
            request = Request(self.base + path, method="HEAD")
            with self.subTest(path=path), urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(int(response.headers["Content-Length"]), len(expected))
                self.assertEqual(response.read(), b"")

    def test_workbench_assets_and_api_routes_are_not_rewritten(self):
        with urlopen(self.base + "/platform/web/public.js", timeout=5) as response:
            self.assertEqual(response.read(), b"export const canonical = true;\n")
        with urlopen(self.base + "/api/v1/sessions?state=running", timeout=5) as response:
            self.assertEqual(json.load(response), {
                "method": "GET", "path": "/api/v1/sessions", "query": {"state": ["running"]},
            })

    def test_unknown_page_does_not_fall_back_to_workbench(self):
        for path in ("/session", "/index.htm", "/sessions/not-a-route"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.base + path, timeout=5)
            self.assertEqual(error.exception.code, 404)


class ServePeripheralApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path: str):
        with urlopen(self.base + path, timeout=5) as response:
            return json.load(response)

    def test_stackchan_inventory_is_complete(self):
        row = self.get_json("/api/peripherals/stackchan")
        self.assertTrue(row["complete"])
        self.assertEqual(row["peripheral_status"], "simulated")
        self.assertEqual(len(row["components"]), 20)
        self.assertIn(
            "stackchan-peripherals",
            row["runtime_cases"]["matrix"],
        )

    def test_tab5_inventory_preserves_blockers(self):
        row = self.get_json("/api/peripherals/tab5")
        self.assertFalse(row["complete"])
        self.assertIn("sc2356", row["blocked_models"])
        self.assertIn("es8388", row["blocked_models"])
        self.assertNotIn("rs485", row["blocked_models"])
        self.assertEqual(
            row["completion_exemption"]["review_by"],
            "2026-12-31",
        )
        self.assertIn(
            "tab5-hosted-peripherals",
            row["runtime_cases"]["external"],
        )

    def test_all_peripherals_inventory(self):
        payload = self.get_json("/api/peripherals")
        self.assertEqual(len(payload["devices"]), 33)
        self.assertEqual(payload["runtime_coverage"]["covered_models"], 63)
        self.assertEqual(
            sum(row["complete"] for row in payload["devices"]),
            13,
        )

    def test_runtime_interfaces_api(self):
        payload = self.get_json("/api/peripheral-interfaces")
        self.assertEqual(payload["model_count"], 76)
        self.assertEqual(payload["device_count"], 33)
        bmi270 = payload["models"]["bmi270"]
        self.assertTrue(bmi270["interfaces"])
        self.assertIn("sticks3-peripherals", bmi270["evidence_cases"])

    def test_single_model_runtime_interfaces_api(self):
        payload = self.get_json("/api/peripheral-interfaces/bmi270")
        self.assertEqual(payload["kind"], "imu")
        self.assertTrue(payload["interfaces"])

    def test_external_unit_inventory_is_separate_from_board_models(self):
        payload = self.get_json("/api/v1/units?device_id=cores3")
        self.assertEqual(len(payload["units"]), 160)
        self.assertEqual([host["device_id"] for host in payload["hosts"]], ["cores3"])
        port = next(port for port in payload["hosts"][0]["ports"] if port["id"] == "port-a")
        self.assertEqual(port["pins"], {"yellow": 2, "white": 1})
        self.assertEqual(port["visual_port"], "grove")

    def test_unit_protocol_description_does_not_claim_guest_execution(self):
        payload = self.get_json("/api/v1/units/env-iii")
        self.assertEqual(payload["interface"]["address_7bit"], [0x44, 0x70])
        self.assertIn(payload["runtime"]["status"], {"developing", "implemented", "validated"})
        if payload["runtime"]["status"] != "validated":
            self.assertTrue(payload["runtime"]["blocker"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
