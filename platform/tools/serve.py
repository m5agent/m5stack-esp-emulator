#!/usr/bin/env python3
"""Static server for the multi-device simulator.

Serves the repository root so /devices, /platform and shared runtime assets resolve
consistently. Adds a small read-only device catalog API for the future device center.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEVICES = ROOT / "devices"


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/api/health"}:
            self._json({"ok": True, "service": "m5stack-device-simulator"})
            return
        if path == "/api/devices":
            self._send_file(DEVICES / "catalog.json")
            return
        if path.startswith("/api/devices/"):
            parts = [part for part in path.removeprefix("/api/devices/").split("/") if part]
            if len(parts) == 2:
                self._send_file(DEVICES / parts[0] / parts[1] / "device.json")
                return
            self._json({"error": "expected /api/devices/<chip-group>/<device>"}, 404)
            return
        super().do_GET()

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self._json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=8080)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    os.chdir(ROOT)
    mimetypes.add_type("application/wasm", ".wasm")
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"M5Stack simulated devices: http://{args.bind}:{args.port}/platform/web/")
    print(f"Device API: http://{args.bind}:{args.port}/api/devices")
    server.serve_forever()


if __name__ == "__main__":
    main()
