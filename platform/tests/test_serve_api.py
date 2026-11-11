#!/usr/bin/env python3
import functools
import hashlib
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
DEVICE_IDS = {row["id"] for row in json.loads((ROOT / "devices/catalog.source.json").read_text())["devices"]}
PERIPHERAL_MODELS = json.loads((ROOT / "platform/peripherals/catalog.json").read_text())["models"]
sys.path.insert(0, str(ROOT / "platform/tools"))
from serve import BrowserSite, Handler
from device_service import DeviceService


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


class ServeBrowserSiteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / "source"
        self.export = root / "export"
        paths = {
            "coi-serviceworker.js", "platform/web/index.html",
            "platform/web/site-config.json", "platform/web/browser-profiles.json",
            "platform/web/qemu-browser-profiles.json", "platform/web/uiflow-workbench-profiles.json",
            "platform/runtime/littlefs/manifest.json", "platform/runtime/littlefs/littlefs.mjs",
            "platform/runtime/littlefs/littlefs.wasm",
        }
        for directory, target in (("qemu", "xtensa"), ("qemu-c61", "riscv32")):
            prefix = f"platform/runtime/{directory}/"
            paths.add(prefix + "runtime.json")
            paths.update(prefix + f"qemu-system-{target}{suffix}" for suffix in (".js", ".worker.js", ".wasm"))
        config = {
            "browser_board_execution": True,
            "browser_runtime_engine": "qemu-wasm",
            "publication_eligible": True,
            "service_url": "",
        }
        rows = []
        for name in sorted(paths):
            asset = self.export / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(config).encode() if name.endswith("site-config.json") else name.encode()
            asset.write_bytes(content)
            rows.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        manifest = {
            "kind": "m5stack-public-site",
            "schema_version": 1,
            "base_path": "/",
            "firmware_bundled": False,
            "publication_eligible": True,
            "candidate_profiles": [],
            "assets": rows,
        }
        data = json.dumps(manifest).encode()
        (self.export / "public-site-manifest.json").write_bytes(data)
        self.manifest_sha = hashlib.sha256(data).hexdigest()
        self.wasm = "platform/runtime/qemu-c61/qemu-system-riscv32.wasm"
        for name, content in (
            ("platform/web/sessions.html", b"session console"),
            ("platform/web/index.html", b"source index"),
            (self.wasm, b"stale runtime"),
        ):
            asset = self.source / name
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(content)

    def test_browser_overlay_and_device_service_share_the_same_origin(self):
        site = BrowserSite(self.export, self.manifest_sha)

        class RouteHandler(Handler):
            browser_site = site

            def _handle_v1(self, method, path, query):
                self._json({"path": path})

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(RouteHandler, directory=str(self.source))
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"
        for name, content in (
            ("/", b"platform/web/index.html"),
            ("/platform/web/", b"platform/web/index.html"),
            ("/sessions", b"session console"),
            ("/" + self.wasm, self.wasm.encode()),
        ):
            with self.subTest(name=name), urlopen(origin + name, timeout=5) as response:
                self.assertEqual(response.read(), content)
        with urlopen(origin + "/platform/web/site-config.json", timeout=5) as response:
            config = json.load(response)
            self.assertEqual(config["service_url"], origin)
            self.assertEqual(config["browser_runtime_engine"], "qemu-wasm")
        with urlopen(origin + "/api/v1/devices", timeout=5) as response:
            self.assertEqual(json.load(response), {"path": "/api/v1/devices"})
        (self.export / self.wasm).unlink()
        with self.assertRaises(HTTPError) as error:
            urlopen(origin + "/" + self.wasm, timeout=5)
        self.assertEqual(error.exception.code, 404)

    def test_activation_rejects_a_changed_or_missing_browser_asset(self):
        asset = self.export / self.wasm
        asset.write_bytes(b"x" * asset.stat().st_size)
        with self.assertRaisesRegex(ValueError, "asset SHA-256 mismatch"):
            BrowserSite(self.export, self.manifest_sha)
        asset.unlink()
        with self.assertRaisesRegex(ValueError, "asset unavailable"):
            BrowserSite(self.export, self.manifest_sha)


class ServePeripheralApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A /api/v1 read initializes the service before dispatching the catalog
        # route. Never acquire the user's default worker-state directory or
        # reuse a Handler service left behind by another HTTP test.
        cls.tmp = tempfile.TemporaryDirectory()
        cls.service = DeviceService(state_dir=Path(cls.tmp.name))

        class InventoryHandler(Handler):
            service = cls.service
            api_token = None
            previous_api_token = None

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), InventoryHandler)
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
        cls.service.close_all()
        cls.tmp.cleanup()

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
        self.assertEqual({row["id"] for row in payload["devices"]}, DEVICE_IDS)
        self.assertEqual(payload["runtime_coverage"]["covered_models"],
                         sum(model["status"] == "simulated" for model in PERIPHERAL_MODELS.values()))
        self.assertEqual(
            sum(row["complete"] for row in payload["devices"]),
            13,
        )

    def test_runtime_interfaces_api(self):
        payload = self.get_json("/api/peripheral-interfaces")
        self.assertEqual(set(payload["models"]), set(PERIPHERAL_MODELS))
        self.assertEqual(payload["model_count"], len(PERIPHERAL_MODELS))
        self.assertEqual(payload["device_count"], len(DEVICE_IDS))
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
