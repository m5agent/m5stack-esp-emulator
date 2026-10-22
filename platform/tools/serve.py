#!/usr/bin/env python3
"""Static server and leased device service for the multi-device simulator.

Serves the repository root so /devices, /platform and shared runtime assets resolve
consistently. Adds the read-only catalog plus the /api/v1 leased device API.
"""
from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from device_service import (
    DEFAULT_MAX_PER_DEVICE,
    DEFAULT_MAX_SESSIONS,
    DEFAULT_STATE_DIR,
    DeviceService,
    ServiceError,
)
from peripheral_inventory import build_inventory
from runtime_interfaces import build_interfaces

ROOT = Path(__file__).resolve().parents[2]
DEVICES = ROOT / "devices"


class ServiceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(SimpleHTTPRequestHandler):
    service: DeviceService | None = None
    api_token: str | None = None

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, X-Artifact-Name, X-Artifact-Type",
        )
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/v1"):
            self._handle_v1("GET", path, parse_qs(parsed.query))
            return
        if (
            path.startswith("/api/")
            and path != "/api/health"
            and not self._authorized(path)
        ):
            self._json(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "valid Bearer token required",
                    }
                },
                401,
            )
            return
        if path in {"/health", "/api/health"}:
            self._json({"ok": True, "service": "m5stack-device-simulator"})
            return
        if path == "/api/devices":
            self._send_file(DEVICES / "catalog.json")
            return
        if path in {"/api/peripherals", "/api/peripheral-inventory"}:
            self._json(build_inventory())
            return
        if path.startswith("/api/peripherals/"):
            parts = [
                part
                for part in path.removeprefix("/api/peripherals/").split("/")
                if part
            ]
            if len(parts) == 1:
                devices = {
                    row["id"]: row
                    for row in build_inventory()["devices"]
                }
                if parts[0] in devices:
                    self._json(devices[parts[0]])
                    return
                self._json({"error": "unknown device"}, 404)
                return
            self._json({"error": "expected /api/peripherals/<device>"}, 404)
            return
        if path in {"/api/peripheral-interfaces", "/api/runtime-interfaces"}:
            self._json(build_interfaces())
            return
        if path.startswith("/api/peripheral-interfaces/"):
            model_id = path.removeprefix("/api/peripheral-interfaces/")
            model = build_interfaces()["models"].get(model_id)
            if model is None:
                self._json({"error": "unknown model"}, 404)
                return
            self._json(model)
            return
        if path.startswith("/api/devices/"):
            parts = [part for part in path.removeprefix("/api/devices/").split("/") if part]
            if len(parts) == 2:
                self._send_file(DEVICES / parts[0] / parts[1] / "device.json")
                return
            self._json({"error": "expected /api/devices/<chip-group>/<device>"}, 404)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/v1"):
            self._json({"error": "not found"}, 404)
            return
        self._handle_v1("POST", parsed.path, parse_qs(parsed.query))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/v1"):
            self._json({"error": "not found"}, 404)
            return
        self._handle_v1("DELETE", parsed.path, parse_qs(parsed.query))

    def _get_service(self) -> DeviceService:
        if self.service is None:
            type(self).service = DeviceService(
                max_sessions=int(
                    os.environ.get(
                        "M5_SERVICE_MAX_SESSIONS", str(DEFAULT_MAX_SESSIONS)
                    )
                ),
                max_per_device=int(
                    os.environ.get(
                        "M5_SERVICE_MAX_PER_DEVICE", str(DEFAULT_MAX_PER_DEVICE)
                    )
                ),
                default_ttl=int(os.environ.get("M5_SERVICE_DEFAULT_TTL", "1800")),
                api_token=os.environ.get("M5_SERVICE_API_TOKEN") or None,
            )
        return type(self).service

    def _authorized(self, path: str) -> bool:
        token = type(self).api_token
        if not token or path in {"/api/v1/health", "/api/v1", "/api/v1/openapi.yaml"}:
            return True
        provided = self.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        return hmac.compare_digest(provided, expected)

    def _handle_v1(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        request_id = uuid.uuid4().hex
        if not self._authorized(path):
            self._json(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "valid Bearer token required",
                    }
                },
                401,
                extra_headers={"X-Request-ID": request_id},
            )
            return
        try:
            service = self._get_service()
            parts = [
                part
                for part in path.removeprefix("/api/v1").split("/")
                if part
            ]
            response: Any
            status = 200
            headers = {"X-Request-ID": request_id}

            if method == "GET" and (not parts or parts == ["health"]):
                response = {
                    "ok": True,
                    "service": "m5stack-device-service",
                    "api_version": "v1",
                    "capacity": service.capacity(),
                }
            elif method == "GET" and parts == ["devices"]:
                include = query.get("include_unsupported", ["1"])[0] != "0"
                response = service.list_devices(include_unsupported=include)
            elif method == "GET" and len(parts) == 2 and parts[0] == "devices":
                response = service.get_device(parts[1])
            elif method == "GET" and parts == ["capacity"]:
                response = service.capacity()
            elif method == "GET" and parts == ["openapi.yaml"]:
                spec = ROOT / "docs/device-service.openapi.yaml"
                if not spec.is_file():
                    raise ServiceError("not_found", "OpenAPI document is missing", 404)
                self._send_bytes(
                    spec.read_bytes(),
                    "application/yaml; charset=utf-8",
                    extra_headers={"X-Request-ID": request_id},
                )
                return
            elif method == "GET" and parts == ["artifacts"]:
                response = {"artifacts": service.artifacts.list()}
            elif method == "GET" and len(parts) == 2 and parts[0] == "artifacts":
                response = service.artifacts.get(parts[1])
            elif method == "GET" and len(parts) == 2 and parts[0] == "firmware":
                response = service.firmware.get(parts[1])
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "firmware"
                and parts[2] == "analysis"
            ):
                response = service.firmware.get_analysis(parts[1])
            elif method == "GET" and parts == ["sessions"]:
                include_stopped = query.get("include_stopped", ["1"])[0] not in {
                    "0",
                    "false",
                    "no",
                }
                response = service.list_sessions(include_stopped=include_stopped)
            elif method == "GET" and len(parts) == 2 and parts[0] == "sessions":
                response = service.get_session(parts[1]).snapshot()
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "events"
            ):
                response = service.session_events(parts[1])
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "flash"
            ):
                session = service.get_session(parts[1])
                output_format = query.get("format", ["sha256"])[0]
                data, metadata = session.flash_get(output_format)
                if data is not None:
                    self._send_bytes(
                        data,
                        "application/octet-stream",
                        extra_headers={
                            "X-Request-ID": request_id,
                            "X-Flash-SHA256": metadata["sha256"],
                        },
                    )
                    return
                response = metadata
            elif (
                method == "GET"
                and len(parts) == 4
                and parts[0] == "sessions"
                and parts[2] == "flash"
                and parts[3] == "diff"
            ):
                session = service.get_session(parts[1])
                response = session.flash_diff(
                    query.get("before", [""])[0],
                    query.get("after", [""])[0],
                )
            elif (
                method == "GET"
                and len(parts) == 4
                and parts[0] == "sessions"
                and parts[2] == "qom"
                and parts[3] == "list"
            ):
                session = service.get_session(parts[1])
                response = session.qom_list(query.get("path", ["/machine"])[0])
            elif (
                method == "GET"
                and len(parts) == 4
                and parts[0] == "sessions"
                and parts[2] == "qom"
                and parts[3] == "diff"
            ):
                session = service.get_session(parts[1])
                response = session.qom_diff(
                    query.get("before", [""])[0],
                    query.get("after", [""])[0],
                )
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "device-state"
            ):
                session = service.get_session(parts[1])
                response = session.device_state()
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "serial"
            ):
                session = service.get_session(parts[1])
                offset = int(query.get("offset", ["0"])[0])
                limit = int(query.get("limit", ["65536"])[0])
                response = session.serial_read(offset=offset, limit=limit)
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "logs"
            ):
                session = service.get_session(parts[1])
                offset = int(query.get("offset", ["0"])[0])
                limit = int(query.get("limit", ["65536"])[0])
                serial = session.serial_read(offset=offset, limit=limit)
                response = {
                    **serial,
                    "qemu_stdout": _read_text_tail(session.stdout_path, limit),
                    "qemu_stderr": _read_text_tail(session.stderr_path, limit),
                }
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "evidence"
            ):
                session = service.get_session(parts[1])
                include = {
                    item.strip()
                    for item in query.get(
                        "include",
                        ["manifest,serial,frames,logs,qom"],
                    )[0].split(",")
                    if item.strip()
                }
                self._send_bytes(
                    session.evidence_bundle(include),
                    "application/zip",
                    extra_headers={
                        "X-Request-ID": request_id,
                        "Content-Disposition": (
                            f'attachment; filename="m5-evidence-{session.id}.zip"'
                        ),
                    },
                )
                return
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] in {"frame", "frame.png"}
            ):
                session = service.get_session(parts[1])
                png, width, height = session.frame_png()
                self._send_bytes(
                    png,
                    "image/png",
                    extra_headers={
                        "X-Request-ID": request_id,
                        "X-Frame-Width": str(width),
                        "X-Frame-Height": str(height),
                    },
                )
                return
            elif (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "sessions"
                and parts[2] == "qom"
            ):
                session = service.get_session(parts[1])
                path_value = query.get("path", [""])[0]
                prop = query.get("property", [""])[0]
                if not path_value or not prop:
                    raise ServiceError(
                        "invalid_qom", "path and property query values are required", 400
                    )
                response = session.qom_get(path_value, prop)
            elif method == "POST" and parts == ["artifacts"]:
                data = self._read_body(max_bytes=32 * 1024 * 1024)
                response = service.upload_artifact(
                    data,
                    name=self.headers.get("X-Artifact-Name", ""),
                    content_type=self.headers.get(
                        "X-Artifact-Type",
                        self.headers.get("Content-Type", "application/octet-stream"),
                    ),
                )
                status = 201
            elif method == "POST" and parts == ["firmware"]:
                response = service.create_firmware(self._read_json())
                status = 201
            elif method == "POST" and parts == ["firmware", "analyze"]:
                payload = self._read_json()
                firmware_id = payload.get("firmware_id")
                if not isinstance(firmware_id, str):
                    raise ServiceError(
                        "invalid_request", "firmware_id is required", 400
                    )
                response = service.firmware.analyze(firmware_id)
            elif method == "POST" and parts == ["sessions"]:
                response = service.create_session(self._read_json())
                status = 202
            elif (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "sessions"
            ):
                session = service.get_session(parts[1])
                action = parts[2]
                payload = self._read_json(required=False)
                if action == "input":
                    response = session.inject(payload)
                elif action == "qom":
                    response = session.qom_set(payload)
                elif action == "qom-snapshot":
                    response = session.qom_snapshot(
                        path=payload.get("path", "/machine"),
                        depth=int(payload.get("depth", 2)),
                        max_nodes=int(payload.get("max_nodes", 500)),
                    )
                elif action == "flash-snapshot":
                    response = session.flash_snapshot()
                elif action == "reset":
                    response = session.reset()
                elif action == "renew":
                    ttl = int(payload.get("ttl_seconds", service.default_ttl))
                    response = session.renew(ttl)
                elif action == "wait":
                    response = _wait_for_session(session, payload)
                elif action == "stop":
                    response = session.stop(purge=bool(payload.get("purge", False)))
                else:
                    raise ServiceError("not_found", "unknown session action", 404)
            elif method == "DELETE" and len(parts) == 2 and parts[0] == "sessions":
                purge = query.get("purge", ["0"])[0] in {"1", "true", "yes"}
                response = service.delete_session(parts[1], purge=purge)
            elif method == "DELETE" and len(parts) == 2 and parts[0] == "artifacts":
                response = service.artifacts.delete(parts[1])
            elif method == "DELETE" and parts == ["sessions"]:
                state = query.get("state", [""])[0]
                if state not in {"stopped", "failed", ""}:
                    raise ServiceError(
                        "invalid_state",
                        "bulk session deletion supports stopped/failed state only",
                        400,
                    )
                purge = query.get("purge", ["1"])[0] in {"1", "true", "yes"}
                response = service.clear_stopped(purge=purge)
            else:
                raise ServiceError("not_found", "not found", 404)

            self._json(response, status, extra_headers=headers)
        except ServiceError as error:
            headers = {"X-Request-ID": request_id}
            if error.code in {
                "capacity_exhausted",
                "device_capacity_exhausted",
            }:
                headers["Retry-After"] = "2"
            self._json(
                error.payload(),
                error.status,
                extra_headers=headers,
            )
        except (ValueError, TypeError, KeyError) as error:
            self._json(
                {
                    "error": {
                        "code": "invalid_request",
                        "message": str(error),
                    }
                },
                400,
                extra_headers={"X-Request-ID": request_id},
            )
        except Exception as error:
            self._json(
                {
                    "error": {
                        "code": "internal_error",
                        "message": str(error),
                    }
                },
                500,
                extra_headers={"X-Request-ID": request_id},
            )

    def _read_body(self, max_bytes: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ServiceError("invalid_content_length", "invalid Content-Length", 400) from error
        if length <= 0:
            raise ServiceError("empty_body", "request body is required", 400)
        if length > max_bytes:
            raise ServiceError(
                "body_too_large", f"request body exceeds {max_bytes} bytes", 413
            )
        return self.rfile.read(length)

    def _read_json(self, required: bool = True) -> dict:
        if not required and int(self.headers.get("Content-Length", "0") or "0") == 0:
            return {}
        raw = self._read_body(max_bytes=1024 * 1024)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ServiceError("invalid_json", "request body must be valid JSON", 400) from error
        if not isinstance(payload, dict):
            raise ServiceError("invalid_json", "request body must be a JSON object", 400)
        if required and not payload:
            raise ServiceError("invalid_json", "request body must not be empty", 400)
        return payload

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

    def _send_bytes(
        self, data: bytes, content_type: str, extra_headers: dict[str, str] | None = None
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(
        self,
        payload: Any,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)


def _read_text_tail(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    return data[-limit:].decode("utf-8", errors="replace")


def _wait_for_session(session, payload: dict) -> dict:
    if payload.get("ready") or payload.get("serial_markers") or payload.get("frame_nonblank"):
        return session.wait_ready(payload)
    marker = payload.get("ready_marker")
    timeout = float(payload.get("timeout_seconds", 30))
    if marker:
        return session.wait_for_marker(str(marker), timeout)
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = session.snapshot()
        if snapshot["state"] == "running":
            return snapshot
        if snapshot["state"] == "failed":
            raise ServiceError(
                "session_failed", snapshot.get("error") or "session failed", 409
            )
        time.sleep(0.1)
    raise ServiceError("ready_timeout", "session did not become ready", 408)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", nargs="?", type=int, default=8787)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=int(
            os.environ.get("M5_SERVICE_MAX_SESSIONS", str(DEFAULT_MAX_SESSIONS))
        ),
    )
    parser.add_argument(
        "--max-per-device",
        type=int,
        default=int(
            os.environ.get("M5_SERVICE_MAX_PER_DEVICE", str(DEFAULT_MAX_PER_DEVICE))
        ),
    )
    parser.add_argument("--session-ttl", type=int, default=1800)
    parser.add_argument("--api-token", default=os.environ.get("M5_SERVICE_API_TOKEN"))
    args = parser.parse_args()
    os.chdir(ROOT)
    mimetypes.add_type("application/wasm", ".wasm")
    service = DeviceService(
        state_dir=args.state_dir or DEFAULT_STATE_DIR,
        max_sessions=args.max_sessions,
        max_per_device=args.max_per_device,
        default_ttl=args.session_ttl,
        api_token=args.api_token,
    )
    Handler.service = service
    Handler.api_token = args.api_token
    server = ServiceHTTPServer((args.bind, args.port), Handler)
    print(f"M5Stack simulated devices: http://{args.bind}:{args.port}/platform/web/")
    print(f"Device API: http://{args.bind}:{args.port}/api/devices")
    print(f"Peripheral API: http://{args.bind}:{args.port}/api/peripherals")
    print(f"Leased service API: http://{args.bind}:{args.port}/api/v1")
    print(
        "Peripheral interfaces: "
        f"http://{args.bind}:{args.port}/api/peripheral-interfaces"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.close_all()
        server.server_close()


if __name__ == "__main__":
    main()
