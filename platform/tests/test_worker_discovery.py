#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from worker_discovery import (  # noqa: E402
    DEFAULT_DISCOVERY_GROUP,
    WorkerDiscoveryAnnouncer,
    WorkerDiscoveryError,
    build_discovery_beacon,
    discover_service,
    fetch_discovery_beacon,
    verify_discovery_beacon,
)
from worker_discovery_seed import (
    DEFAULT_SEED_PATH,
    DiscoverySeedHandler,
    DiscoverySeedServer,
)


class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:1/redirected")
        self.end_headers()

    def log_message(self, format, *args):
        pass


class WorkerDiscoveryTests(unittest.TestCase):
    def test_signed_beacon_contains_no_secret(self):
        token = "synthetic-discovery-master-token"
        beacon = build_discovery_beacon(
            token,
            "http://control.example:8787/",
            port=18788,
            ttl_seconds=5,
            now=1000,
        )
        encoded = json.dumps(beacon)
        verified = verify_discovery_beacon(
            encoded.encode(),
            token,
            port=18788,
            now=1002,
        )

        self.assertEqual(
            verified["service_url"],
            "http://control.example:8787",
        )
        self.assertNotIn(token, encoded)
        self.assertEqual(len(verified["signature"]), 64)

    def test_invalid_signature_group_and_expiry_are_rejected(self):
        beacon = build_discovery_beacon(
            "correct-token",
            "https://control.example",
            port=18789,
            ttl_seconds=3,
            now=2000,
        )
        encoded = json.dumps(beacon).encode()

        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "signature is invalid",
        ):
            verify_discovery_beacon(
                encoded,
                "wrong-token",
                port=18789,
                now=2001,
            )
        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "identity does not match",
        ):
            verify_discovery_beacon(
                encoded,
                "correct-token",
                group="239.255.77.78",
                port=18789,
                now=2001,
            )
        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "expired",
        ):
            verify_discovery_beacon(
                encoded,
                "correct-token",
                port=18789,
                now=2004,
            )

    def test_service_url_and_packet_size_are_bounded(self):
        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "without credentials",
        ):
            build_discovery_beacon(
                "token",
                "https://user:password@control.example",
            )
        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "empty or too large",
        ):
            verify_discovery_beacon(
                b"x" * 4097,
                "token",
            )

    def test_authenticated_multicast_announcement_is_discovered(self):
        token = "synthetic-discovery-live-token"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        announcer = WorkerDiscoveryAnnouncer(
            lambda: token,
            "http://127.0.0.1:18787",
            group=DEFAULT_DISCOVERY_GROUP,
            port=port,
            interval=0.1,
            ttl_seconds=2,
        )
        announcer.start()
        try:
            discovered = discover_service(
                token,
                group=DEFAULT_DISCOVERY_GROUP,
                port=port,
                timeout=5,
            )
        finally:
            announcer.close()

        self.assertEqual(
            discovered["service_url"],
            "http://127.0.0.1:18787",
        )
        self.assertEqual(discovered["port"], port)
        self.assertTrue(discovered["expires_at"] > time.time() - 1)

    def test_unicast_seed_beacon_is_fetched_and_verified(self):
        token = "synthetic-seed-live-token"
        server = DiscoverySeedServer(
            ("127.0.0.1", 0),
            DiscoverySeedHandler,
        )
        server.token_provider = lambda: token
        server.service_url = "https://control.example:8787"
        server.discovery_group = DEFAULT_DISCOVERY_GROUP
        server.discovery_port = 18790
        server.ttl_seconds = 5
        server.seed_path = DEFAULT_SEED_PATH
        thread = threading.Thread(
            target=server.serve_forever,
            name="test-discovery-seed",
            daemon=True,
        )
        thread.start()
        try:
            port = int(server.server_address[1])
            discovered = fetch_discovery_beacon(
                f"http://127.0.0.1:{port}{DEFAULT_SEED_PATH}",
                token,
                port=18790,
                timeout=2,
            )
            with self.assertRaisesRegex(
                WorkerDiscoveryError,
                "signature is invalid",
            ):
                fetch_discovery_beacon(
                    f"http://127.0.0.1:{port}{DEFAULT_SEED_PATH}",
                    "wrong-token",
                    port=18790,
                    timeout=2,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(
            discovered["service_url"],
            "https://control.example:8787",
        )
        self.assertEqual(discovered["transport"], "unicast-seed")
        self.assertEqual(discovered["source"], "127.0.0.1")
        self.assertNotIn(token, json.dumps(discovered))

    def test_unicast_seed_rejects_redirects(self):
        redirect = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            RedirectHandler,
        )
        thread = threading.Thread(
            target=redirect.serve_forever,
            name="test-discovery-redirect",
            daemon=True,
        )
        thread.start()
        try:
            port = int(redirect.server_address[1])
            with self.assertRaisesRegex(
                WorkerDiscoveryError,
                "returned HTTP 302",
            ):
                fetch_discovery_beacon(
                    f"http://127.0.0.1:{port}{DEFAULT_SEED_PATH}",
                    "synthetic-token",
                    port=18790,
                    timeout=2,
                )
        finally:
            redirect.shutdown()
            redirect.server_close()
            thread.join(timeout=2)

    def test_unicast_seed_url_is_credential_free(self):
        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "without credentials",
        ):
            fetch_discovery_beacon(
                "https://user:password@seed.example/beacon",
                "synthetic-token",
                timeout=2,
            )
        with self.assertRaisesRegex(
            WorkerDiscoveryError,
            "non-empty master token",
        ):
            fetch_discovery_beacon(
                "https://seed.example/beacon",
                "",
                timeout=2,
            )


if __name__ == "__main__":
    unittest.main()
