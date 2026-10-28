#!/usr/bin/env python3
"""Static server and leased device service for the multi-device simulator.

Serves the repository root so /devices, /platform and shared runtime assets resolve
consistently. Adds the read-only catalog plus the /api/v1 leased device API.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import signal
import ssl
import threading
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
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_CHUNK_BYTES,
    DeviceService,
    ServiceError,
)
from peripheral_inventory import build_inventory
from program_revisions import MAX_CONFIGURED_REVISIONS, MAX_REVISIONS
from program_packages import MAX_CONFIGURED_PACKAGES, MAX_PACKAGES
from runtime_interfaces import build_interfaces
from unit_runtime import UnitError, UnitRegistry
from transport_security import (
    TransportSecurityError,
    build_server_tls_context,
)
from worker_auth import (
    WorkerAuthError,
    is_worker_auth_path,
    read_master_token_file,
    worker_identity_matches,
)
from worker_discovery import (
    DEFAULT_DISCOVERY_GROUP,
    DEFAULT_DISCOVERY_INTERVAL,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_DISCOVERY_TTL,
    WorkerDiscoveryAnnouncer,
    WorkerDiscoveryError,
)

ROOT = Path(__file__).resolve().parents[2]
DEVICES = ROOT / "devices"


class ServiceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    class RequestDrainGate:
        def __init__(self) -> None:
            self._condition = threading.Condition()
            self._active = 0
            self._draining = False

        def enter(self) -> None:
            with self._condition:
                while self._draining:
                    self._condition.wait()
                self._active += 1

        def leave(self) -> None:
            with self._condition:
                if self._active <= 0:
                    raise RuntimeError("request drain gate is unbalanced")
                self._active -= 1
                if self._active == 0:
                    self._condition.notify_all()

        def begin_drain(self, timeout: float) -> bool:
            deadline = time.monotonic() + timeout
            with self._condition:
                if self._draining:
                    raise RuntimeError("request drain is already active")
                self._draining = True
                while self._active:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._draining = False
                        self._condition.notify_all()
                        return False
                    self._condition.wait(remaining)
                return True

        def finish_drain(self) -> None:
            with self._condition:
                self._draining = False
                self._condition.notify_all()

        @property
        def active(self) -> int:
            with self._condition:
                return self._active

        @property
        def draining(self) -> bool:
            with self._condition:
                return self._draining

    def __init__(
        self,
        server_address,
        handler,
        *,
        tls_context: ssl.SSLContext | None = None,
        reload_callback=None,
        reload_drain_timeout: float = 30,
    ):
        self.tls_context = tls_context
        self.reload_callback = reload_callback
        self.reload_drain_timeout = float(reload_drain_timeout)
        if self.reload_drain_timeout <= 0:
            raise ValueError("reload drain timeout must be positive")
        self.request_gate = self.RequestDrainGate()
        self._reload_security = threading.Event()
        self._security_lock = threading.RLock()
        super().__init__(server_address, handler)

    def get_request(self):
        sock, address = super().get_request()
        with self._security_lock:
            context = self.tls_context
        if context is None:
            return sock, address
        try:
            return context.wrap_socket(sock, server_side=True), address
        except ssl.SSLError:
            sock.close()
            raise

    def request_security_reload(self) -> None:
        self._reload_security.set()

    def process_request(self, request, client_address) -> None:
        self.request_gate.enter()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.request_gate.leave()
            raise

    def finish_request(self, request, client_address) -> None:
        try:
            super().finish_request(request, client_address)
        finally:
            self.request_gate.leave()

    def service_actions(self) -> None:
        super().service_actions()
        if not self._reload_security.is_set():
            return
        self._reload_security.clear()
        if self.reload_callback is None:
            return
        print("security configuration drain started", flush=True)
        if not self.request_gate.begin_drain(self.reload_drain_timeout):
            print(
                "security configuration reload canceled: "
                "request drain timed out",
                flush=True,
            )
            return
        try:
            try:
                context = self.reload_callback()
            except Exception as error:
                print(
                    f"security configuration reload failed: {error}",
                    flush=True,
                )
                return
            with self._security_lock:
                self.tls_context = context
            print("security configuration reloaded", flush=True)
        finally:
            self.request_gate.finish_drain()

    def server_close(self) -> None:
        self.request_gate.finish_drain()
        super().server_close()


class Handler(SimpleHTTPRequestHandler):
    service: DeviceService | None = None
    api_token: str | None = None
    previous_api_token: str | None = None

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
            (
                "Authorization, Content-Type, If-None-Match, X-Artifact-Name, "
                "X-Artifact-Type, X-Chunk-Offset, X-Chunk-SHA256, Idempotency-Key"
            ),
        )
        self.send_header(
            "Access-Control-Expose-Headers",
            "ETag, X-Frame-Width, X-Frame-Height, X-Frame-SHA256, "
            "X-Frame-Captured-At, X-Frame-Capture-Seq, X-Frame-Source, "
            "X-Frame-Execution-ID, X-Frame-Revision-ID, X-Frame-Program-State, "
            "X-Preview-ID, X-Run-ID",
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
                max_program_revisions=int(os.environ.get(
                    "M5_SERVICE_MAX_PROGRAM_REVISIONS", str(MAX_REVISIONS),
                )),
                max_program_packages=int(os.environ.get(
                    "M5_SERVICE_MAX_PROGRAM_PACKAGES", str(MAX_PACKAGES),
                )),
                api_token=os.environ.get("M5_SERVICE_API_TOKEN") or None,
            )
        return type(self).service

    def _authorized(self, path: str) -> bool:
        tokens = tuple(
            token
            for token in (
                type(self).api_token,
                type(self).previous_api_token,
            )
            if token
        )
        if not tokens or path in {
            "/api/v1/health",
            "/api/v1",
            "/api/v1/openapi.yaml",
        }:
            return True
        provided = self.headers.get("Authorization", "")
        return any(
            hmac.compare_digest(provided, f"Bearer {token}")
            for token in tokens
        )

    def _handle_v1(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        request_id = uuid.uuid4().hex
        self._cached_body: bytes | None = None
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
            verified_worker: dict[str, Any] | None = None
            if parts and parts[0] == "previews":
                self._handle_preview(method, parts, query, request_id)
                return
            if method in {"POST", "DELETE"} and len(parts) >= 2 and parts[0] == "sessions":
                read_actions = {"wait", "qom-snapshot", "flash-snapshot"}
                if method == "DELETE" or len(parts) < 3 or parts[2] not in read_actions:
                    target_session = service.get_session(parts[1])
                    if getattr(target_session, "management_binding", None) is not None:
                        target_session.require_management_handle()
            if (
                self.api_token or self.previous_api_token
            ) and is_worker_auth_path(method, path):
                verified_worker = service.verify_worker_request(
                    self.headers,
                    method,
                    path,
                    self._read_body(max_bytes=1024 * 1024),
                )

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
            elif method == "GET" and len(parts) == 2 and parts[0] == "program-revisions":
                response = service.get_program_revision(parts[1])
            elif method == "GET" and len(parts) == 3 and parts[0] == "program-revisions" and parts[2] == "files":
                response = service.get_program_revision_files(parts[1])
            elif method == "GET" and parts == ["units"]:
                try:
                    response = UnitRegistry().inventory(query.get("device_id", [None])[0])
                except UnitError as error:
                    raise ServiceError(error.code, error.message, error.status) from error
            elif method == "GET" and len(parts) == 2 and parts[0] == "units":
                try:
                    response = UnitRegistry().unit(parts[1])
                except UnitError as error:
                    raise ServiceError(error.code, error.message, error.status) from error
            elif method == "GET" and parts == ["storage"]:
                response = service.storage_stats()
            elif method == "GET" and parts == ["worker"]:
                response = service.worker_status()
            elif method == "GET" and parts == ["workers"]:
                response = service.list_remote_workers()
            elif method == "GET" and parts == ["jobs"]:
                response = service.list_remote_jobs(
                    status=query.get("status", [None])[0],
                    limit=int(query.get("limit", ["100"])[0]),
                )
            elif (
                method == "GET"
                and len(parts) == 2
                and parts[0] == "jobs"
            ):
                response = service.get_remote_job(parts[1])
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
            elif (
                method == "GET"
                and len(parts) == 2
                and parts[0] == "artifact-uploads"
            ):
                response = service.get_artifact_upload(parts[1])
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
                method == "GET" and len(parts) == 3
                and parts[0] == "sessions" and parts[2] == "units"
            ):
                response = service.get_session(parts[1]).unit_state()
            elif (
                method == "GET" and len(parts) == 3
                and parts[0] == "sessions" and parts[2] == "program"
            ):
                response = service.get_session(parts[1]).program_status()
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
                and parts[2] == "network"
            ):
                session = service.get_session(parts[1])
                network_evidence = getattr(session, "network_evidence", None)
                if network_evidence is None:
                    raise ServiceError(
                        "network_not_available",
                        "this session is not a network session",
                        409,
                    )
                response = network_evidence()
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
                stdout = _read_text_tail(session.stdout_path, limit)
                stderr = _read_text_tail(session.stderr_path, limit)
                response = {
                    **serial,
                    "runtime": getattr(session, "runtime", "qemu"),
                    "stdout": stdout,
                    "stderr": stderr,
                    "qemu_stdout": stdout,
                    "qemu_stderr": stderr,
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
                ages = query.get("max_age_ms", ["0"])
                if len(ages) != 1 or not 1 <= len(ages[0]) <= 4 or not ages[0].isascii() or not ages[0].isdigit() or not 0 <= int(ages[0]) <= 1000:
                    raise ServiceError("invalid_frame_age", "max_age_ms must be an integer between 0 and 1000", 400)
                max_age_ms = int(ages[0])
                if max_age_ms:
                    frame = session.preview_frame(max_age_ms)
                    frame_headers = {
                        "X-Request-ID": request_id,
                        "X-Frame-Width": str(frame["width"]),
                        "X-Frame-Height": str(frame["height"]),
                        "X-Frame-SHA256": frame["sha256"],
                        "X-Frame-Capture-Seq": str(frame["capture_seq"]),
                        "X-Frame-Source": frame["source"],
                        "ETag": '"' + frame["sha256"] + '"',
                    }
                    for field, header in (("captured_at", "X-Frame-Captured-At"),
                                          ("execution_id", "X-Frame-Execution-ID"),
                                          ("revision_id", "X-Frame-Revision-ID"),
                                          ("program_state", "X-Frame-Program-State")):
                        if frame.get(field) is not None:
                            frame_headers[header] = str(frame[field])
                    candidates = [value.strip().removeprefix("W/") for value in self.headers.get("If-None-Match", "").split(",")]
                    if frame_headers["ETag"] in candidates or "*" in candidates:
                        self.send_response(304)
                        for key, value in frame_headers.items():
                            self.send_header(key, value)
                        self.end_headers()
                    else:
                        self._send_bytes(frame["png"], "image/png", extra_headers=frame_headers)
                    return
                png, width, height = session.frame_png()
                self._send_bytes(
                    png,
                    "image/png",
                    extra_headers={
                        "X-Request-ID": request_id,
                        "X-Frame-Width": str(width),
                        "X-Frame-Height": str(height),
                        "X-Frame-SHA256": hashlib.sha256(png).hexdigest(),
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
            elif method == "POST" and parts == ["program-revisions"]:
                response = service.create_program_revision(self._read_json(max_bytes=2 * 1024 * 1024, reject_duplicate_keys=True))
                status = 201
                headers["Location"] = f"/api/v1/program-revisions/{response['revision']['revision_id']}"
            elif method == "POST" and parts == ["artifact-uploads"]:
                payload = self._read_json()
                expected_size = payload.get("expected_size")
                expected_sha256 = payload.get("expected_sha256")
                if not isinstance(expected_sha256, str):
                    raise ServiceError(
                        "invalid_upload",
                        "expected_sha256 is required",
                        400,
                    )
                response = service.begin_artifact_upload(
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                    name=str(payload.get("name") or ""),
                    content_type=str(payload.get("content_type") or ""),
                )
                status = 202
            elif (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "artifact-uploads"
                and parts[2] == "chunks"
            ):
                data = self._read_body(
                    max_bytes=MAX_ARTIFACT_CHUNK_BYTES
                )
                offset_header = self.headers.get("X-Chunk-Offset", "")
                chunk_sha256 = self.headers.get("X-Chunk-SHA256", "")
                try:
                    offset = int(offset_header, 0)
                except ValueError as error:
                    raise ServiceError(
                        "invalid_chunk_offset",
                        "X-Chunk-Offset must be an integer",
                        400,
                    ) from error
                response = service.append_artifact_upload(
                    parts[1],
                    offset=offset,
                    data=data,
                    sha256=chunk_sha256,
                )
                status = 202
            elif (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "artifact-uploads"
                and parts[2] == "complete"
            ):
                response = service.complete_artifact_upload(parts[1])
                status = 201
            elif method == "POST" and parts == ["artifacts"]:
                data = self._read_body(max_bytes=MAX_ARTIFACT_BYTES)
                response = service.upload_artifact(
                    data,
                    name=self.headers.get("X-Artifact-Name", ""),
                    content_type=self.headers.get(
                        "X-Artifact-Type",
                        self.headers.get("Content-Type", "application/octet-stream"),
                    ),
                )
                status = 201
            elif method == "POST" and parts == ["firmware", "import"]:
                response = service.import_firmware_package(self._read_json())
                status = 201
            elif method == "POST" and parts == ["firmware", "uiflow"]:
                response = service.create_uiflow_firmware(self._read_json())
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
            elif method == "POST" and parts == ["storage", "prune"]:
                include_cache = query.get("include_cache", ["1"])[0] not in {
                    "0",
                    "false",
                    "no",
                }
                response = service.prune_storage(include_cache=include_cache)
            elif method == "POST" and parts == ["worker", "drain"]:
                response = service.drain_worker()
            elif method == "POST" and parts == ["worker", "resume"]:
                response = service.resume_worker()
            elif method == "POST" and parts == ["workers"]:
                response = service.register_remote_worker(
                    self._read_json()
                )
                status = 201
            elif method == "POST" and parts == ["jobs"]:
                response = service.submit_remote_job(self._read_json())
                status = 201
            elif method == "POST" and parts == ["jobs", "claim"]:
                payload = self._read_json()
                self._require_worker_identity(payload, verified_worker)
                response = service.claim_remote_job(payload)
            elif (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "jobs"
            ):
                action = parts[2]
                payload = self._read_json(required=action != "cancel")
                if action == "heartbeat":
                    self._require_worker_identity(payload, verified_worker)
                    response = service.heartbeat_remote_job(
                        parts[1], payload
                    )
                elif action == "result":
                    self._require_worker_identity(payload, verified_worker)
                    response = service.record_remote_job_result(
                        parts[1], payload
                    )
                elif action == "cancel":
                    response = service.cancel_remote_job(
                        parts[1], payload
                    )
                else:
                    raise ServiceError(
                        "not_found",
                        "unknown remote job action",
                        404,
                    )
            elif (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "workers"
            ):
                payload = self._read_json()
                action = parts[2]
                if action == "heartbeat":
                    self._require_worker_identity(
                        payload,
                        verified_worker,
                        parts[1],
                    )
                    response = service.heartbeat_remote_worker(
                        parts[1], payload
                    )
                elif action == "drain":
                    self._require_worker_identity(
                        payload,
                        verified_worker,
                        parts[1],
                    )
                    response = service.drain_remote_worker(
                        parts[1], payload
                    )
                elif action == "stop":
                    self._require_worker_identity(
                        payload,
                        verified_worker,
                        parts[1],
                    )
                    response = service.stop_remote_worker(
                        parts[1], payload
                    )
                elif action == "results":
                    self._require_worker_identity(
                        payload,
                        verified_worker,
                        parts[1],
                    )
                    response = service.record_remote_worker_result(
                        parts[1], payload
                    )
                    status = 201
                else:
                    raise ServiceError(
                        "not_found",
                        "unknown remote worker action",
                        404,
                    )
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
                payload = self._read_json(required=False, max_bytes=2 * 1024 * 1024 if action == "program" else 1024 * 1024)
                if action == "input":
                    response = session.inject(payload)
                elif action == "program":
                    response = session.run_program(payload)
                elif action == "unit-input":
                    response = session.unit_input(payload)
                elif action == "qom":
                    response = session.qom_set(payload)
                elif action == "network-fault":
                    response = session.network_fault(payload)
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
                    ttl = payload.get("ttl_seconds", service.default_ttl)
                    if type(ttl) is not int or ttl < 30:
                        raise ServiceError("invalid_ttl", "ttl_seconds must be an integer >= 30", 400)
                    response = session.renew(ttl)
                elif action == "wait":
                    response = _wait_for_session(session, payload)
                elif action == "stop":
                    retain_flash = payload.get("retain_flash")
                    response = session.stop(
                        purge=bool(payload.get("purge", False)),
                        retain_flash=(
                            bool(retain_flash)
                            if retain_flash is not None
                            else None
                        ),
                    )
                else:
                    raise ServiceError("not_found", "unknown session action", 404)
            elif method == "DELETE" and len(parts) == 2 and parts[0] == "sessions":
                purge = query.get("purge", ["0"])[0] in {"1", "true", "yes"}
                retain_flash = query.get("retain_flash", [""])[0]
                response = service.delete_session(
                    parts[1],
                    purge=purge,
                    retain_flash=(
                        retain_flash.lower() in {"1", "true", "yes"}
                        if retain_flash
                        else None
                    ),
                )
            elif (
                method == "DELETE"
                and len(parts) == 2
                and parts[0] == "artifact-uploads"
            ):
                response = service.abort_artifact_upload(parts[1])
            elif method == "DELETE" and len(parts) == 2 and parts[0] == "artifacts":
                response = service.delete_artifact(parts[1])
            elif method == "DELETE" and parts == ["sessions"]:
                state = query.get("state", [""])[0]
                if state not in {"stopped", "failed", ""}:
                    raise ServiceError(
                        "invalid_state",
                        "bulk session deletion supports stopped/failed state only",
                        400,
                    )
                purge = query.get("purge", ["1"])[0] in {"1", "true", "yes"}
                retain_flash = query.get("retain_flash", [""])[0]
                response = service.clear_stopped(
                    purge=purge,
                    retain_flash=(
                        retain_flash.lower() in {"1", "true", "yes"}
                        if retain_flash
                        else None
                    ),
                )
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

    def _handle_preview(self, method, parts, query, request_id):
        """Authenticated local-control facade; the coordinator owns execution."""
        if not (type(self).api_token or type(self).previous_api_token):
            raise ServiceError("preview_auth_unavailable", "Preview requires a configured control Bearer token", 503)
        control = self._get_service().preview_control()
        owner = "local-control"
        headers = {"X-Request-ID": request_id}
        keys = self.headers.get_all("Idempotency-Key", [])
        if len(keys) > 1:
            raise ServiceError("invalid_idempotency_key", "only one Idempotency-Key header is accepted", 400)
        key = keys[0] if keys else ""
        status = 200
        def body():
            return self._read_json(max_bytes=1024 * 1024, reject_duplicate_keys=True)
        if parts == ["previews"] and method == "POST":
            response = control.create(body(), owner=owner, idempotency_key=key)
            status = 202
            headers["Location"] = f"/api/v1/previews/{response['preview_id']}"
        elif parts == ["previews"] and method == "GET":
            response = control.list(owner=owner)
        elif len(parts) == 2 and method == "GET":
            response = control.get(parts[1], owner=owner)
        elif len(parts) == 3 and parts[2] == "runs" and method == "POST":
            response = control.submit(parts[1], body(), owner=owner, idempotency_key=key)
            status = 202
            headers["Location"] = f"/api/v1/previews/{parts[1]}/runs/{response['run_id']}"
        elif len(parts) == 4 and parts[2] == "runs" and method == "GET":
            response = control.run(parts[1], parts[3], owner=owner)
        elif len(parts) == 5 and parts[2] == "runs" and parts[4] == "cancel" and method == "POST":
            response = control.cancel(parts[1], parts[3], body(), owner=owner)
            status = 202
        elif len(parts) == 3 and parts[2] in {"renew", "close", "input"} and method == "POST":
            response = getattr(control, parts[2])(parts[1], body(), owner=owner)
            if parts[2] == "close":
                status = 202
        elif len(parts) == 5 and parts[2] == "runs" and parts[4] == "frame.png" and method == "GET":
            values = query.get("max_age_ms", ["0"])
            if set(query) - {"max_age_ms"} or len(values) != 1 or not values[0].isascii() or not values[0].isdigit() or not 0 <= int(values[0]) <= 1000:
                raise ServiceError("invalid_frame_age", "max_age_ms must be an integer between 0 and 1000", 400)
            frame = control.frame(parts[1], parts[3], owner=owner, max_age_ms=int(values[0]))
            headers.update(frame["headers"])
            candidates = [value.strip().removeprefix("W/") for value in self.headers.get("If-None-Match", "").split(",")]
            if headers["ETag"] in candidates or "*" in candidates:
                self.send_response(304)
                for name, value in headers.items():
                    self.send_header(name, str(value))
                self.end_headers()
            else:
                self._send_bytes(frame["png"], "image/png", extra_headers=headers)
            return
        else:
            raise ServiceError("not_found", "unknown Preview action", 404)
        self._json(response, status, extra_headers=headers)

    def _read_body(self, max_bytes: int) -> bytes:
        cached = getattr(self, "_cached_body", None)
        if cached is not None:
            return cached
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
        body = self.rfile.read(length)
        self._cached_body = body
        return body

    def _require_worker_identity(
        self,
        payload: dict[str, Any],
        verified: dict[str, Any] | None,
        worker_id: str | None = None,
    ) -> None:
        if verified is None:
            return
        if worker_id is not None and str(verified.get("worker_id")) != worker_id:
            raise ServiceError(
                "worker_auth_identity_mismatch",
                "signed worker identity does not match the path",
                409,
            )
        if not worker_identity_matches(verified, payload):
            raise ServiceError(
                "worker_auth_identity_mismatch",
                "signed worker identity does not match the request body",
                409,
            )

    def _read_json(self, required: bool = True, *, max_bytes: int = 1024 * 1024,
                   reject_duplicate_keys: bool = False) -> dict:
        if not required and int(self.headers.get("Content-Length", "0") or "0") == 0:
            return {}
        raw = self._read_body(max_bytes=max_bytes)
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ServiceError("invalid_json", "duplicate JSON field", 400)
                result[key] = value
            return result
        try:
            payload = json.loads(raw, object_pairs_hook=unique_object if reject_duplicate_keys else None)
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
    wait_for_completion = bool(payload.get("wait_for_completion", False))
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = session.snapshot()
        if wait_for_completion and snapshot["state"] in {"stopped", "failed"}:
            if snapshot["state"] == "failed":
                raise ServiceError(
                    "session_failed",
                    snapshot.get("error") or "session failed",
                    409,
                )
            return snapshot
        if snapshot["state"] == "running" and not wait_for_completion:
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
    parser.add_argument(
        "--max-program-revisions",
        type=int,
        default=os.environ.get("M5_SERVICE_MAX_PROGRAM_REVISIONS", str(MAX_REVISIONS)),
        help="maximum retained immutable source revisions (1–4096; default 256)",
    )
    parser.add_argument(
        "--max-program-packages",
        type=int,
        default=os.environ.get("M5_SERVICE_MAX_PROGRAM_PACKAGES", str(MAX_PACKAGES)),
        help="maximum retained immutable program packages (1–4096; default 256)",
    )
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "--api-token",
        default=os.environ.get("M5_SERVICE_API_TOKEN"),
    )
    auth_group.add_argument(
        "--api-token-file",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_API_TOKEN_FILE"])
            if os.environ.get("M5_SERVICE_API_TOKEN_FILE")
            else None
        ),
    )
    parser.add_argument(
        "--api-token-previous-file",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_API_TOKEN_PREVIOUS_FILE"])
            if os.environ.get("M5_SERVICE_API_TOKEN_PREVIOUS_FILE")
            else None
        ),
    )
    parser.add_argument(
        "--tls-cert",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_TLS_CERT"])
            if os.environ.get("M5_SERVICE_TLS_CERT")
            else None
        ),
    )
    parser.add_argument(
        "--tls-key",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_TLS_KEY"])
            if os.environ.get("M5_SERVICE_TLS_KEY")
            else None
        ),
    )
    parser.add_argument(
        "--tls-client-ca",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_TLS_CLIENT_CA"])
            if os.environ.get("M5_SERVICE_TLS_CLIENT_CA")
            else None
        ),
    )
    parser.add_argument(
        "--tls-client-ca-previous",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_TLS_CLIENT_CA_PREVIOUS"])
            if os.environ.get("M5_SERVICE_TLS_CLIENT_CA_PREVIOUS")
            else None
        ),
    )
    parser.add_argument(
        "--worker-id",
        default=os.environ.get("M5_WORKER_ID"),
    )
    parser.add_argument(
        "--worker-state",
        type=Path,
        default=(
            Path(os.environ["M5_WORKER_STATE_PATH"])
            if os.environ.get("M5_WORKER_STATE_PATH")
            else None
        ),
    )
    parser.add_argument(
        "--worker-heartbeat-interval",
        type=float,
        default=float(os.environ.get("M5_WORKER_HEARTBEAT_INTERVAL", "5")),
    )
    parser.add_argument(
        "--worker-stale-after",
        type=float,
        default=float(os.environ.get("M5_WORKER_STALE_AFTER", "15")),
    )
    parser.add_argument(
        "--worker-discovery-group",
        default=os.environ.get(
            "M5_WORKER_DISCOVERY_GROUP",
            DEFAULT_DISCOVERY_GROUP,
        ),
    )
    parser.add_argument(
        "--worker-discovery-port",
        type=int,
        default=int(
            os.environ.get(
                "M5_WORKER_DISCOVERY_PORT",
                str(DEFAULT_DISCOVERY_PORT),
            )
        ),
    )
    parser.add_argument(
        "--worker-discovery-advertise-url",
        default=os.environ.get("M5_WORKER_DISCOVERY_ADVERTISE_URL"),
        help="HTTP(S) control-plane URL advertised to workers",
    )
    parser.add_argument(
        "--worker-discovery-interval",
        type=float,
        default=float(
            os.environ.get(
                "M5_WORKER_DISCOVERY_INTERVAL",
                str(DEFAULT_DISCOVERY_INTERVAL),
            )
        ),
    )
    parser.add_argument(
        "--worker-discovery-ttl",
        type=float,
        default=float(
            os.environ.get(
                "M5_WORKER_DISCOVERY_TTL",
                str(DEFAULT_DISCOVERY_TTL),
            )
        ),
    )
    parser.add_argument(
        "--security-reload-drain-timeout",
        type=float,
        default=float(
            os.environ.get("M5_SECURITY_RELOAD_DRAIN_TIMEOUT", "30")
        ),
    )
    args = parser.parse_args()
    if not 1 <= args.max_program_revisions <= MAX_CONFIGURED_REVISIONS:
        parser.error("--max-program-revisions must be between 1 and 4096")
    if not 1 <= args.max_program_packages <= MAX_CONFIGURED_PACKAGES:
        parser.error("--max-program-packages must be between 1 and 4096")
    if args.api_token and args.api_token_file:
        parser.error("--api-token and --api-token-file are mutually exclusive")
    if args.api_token_previous_file and not (
        args.api_token or args.api_token_file
    ):
        parser.error(
            "--api-token-previous-file requires an active API token"
        )
    if (args.tls_cert is None) != (args.tls_key is None):
        parser.error("--tls-cert and --tls-key must be provided together")
    if args.tls_client_ca is not None and args.tls_cert is None:
        parser.error("--tls-client-ca requires --tls-cert and --tls-key")
    if (
        args.tls_client_ca_previous is not None
        and args.tls_client_ca is None
    ):
        parser.error(
            "--tls-client-ca-previous requires --tls-client-ca"
        )
    if args.security_reload_drain_timeout <= 0:
        parser.error("--security-reload-drain-timeout must be positive")
    if args.worker_discovery_interval <= 0:
        parser.error("--worker-discovery-interval must be positive")
    if args.worker_discovery_ttl <= args.worker_discovery_interval:
        parser.error(
            "--worker-discovery-ttl must be longer than "
            "--worker-discovery-interval"
        )

    def load_api_token() -> str | None:
        if args.api_token_file is None:
            return args.api_token
        try:
            return read_master_token_file(args.api_token_file)
        except WorkerAuthError as error:
            raise TransportSecurityError(error.message) from error

    def load_previous_api_token(active_token: str | None) -> str | None:
        path = args.api_token_previous_file
        if path is None or not path.exists():
            return None
        try:
            token = read_master_token_file(path)
        except WorkerAuthError as error:
            raise TransportSecurityError(error.message) from error
        return token if token != active_token else None

    def load_tls_context() -> ssl.SSLContext | None:
        if args.tls_cert is None or args.tls_key is None:
            return None
        previous_ca = (
            args.tls_client_ca_previous
            if (
                args.tls_client_ca_previous is not None
                and args.tls_client_ca_previous.exists()
            )
            else None
        )
        return build_server_tls_context(
            args.tls_cert,
            args.tls_key,
            args.tls_client_ca,
            previous_ca,
        )

    try:
        initial_api_token = load_api_token()
        initial_previous_api_token = load_previous_api_token(
            initial_api_token
        )
        tls_context = load_tls_context()
    except (TransportSecurityError, WorkerAuthError) as error:
        parser.error(str(error))
    os.chdir(ROOT)
    mimetypes.add_type("application/wasm", ".wasm")
    service = DeviceService(
        state_dir=args.state_dir or DEFAULT_STATE_DIR,
        max_sessions=args.max_sessions,
        max_per_device=args.max_per_device,
        max_program_revisions=args.max_program_revisions,
        max_program_packages=args.max_program_packages,
        default_ttl=args.session_ttl,
        api_token=initial_api_token,
        previous_api_token=initial_previous_api_token,
        worker_id=args.worker_id,
        worker_state_path=args.worker_state,
        worker_heartbeat_interval=args.worker_heartbeat_interval,
        worker_stale_after=args.worker_stale_after,
    )
    Handler.service = service
    Handler.api_token = initial_api_token
    Handler.previous_api_token = initial_previous_api_token

    def reload_security():
        new_token = load_api_token()
        new_previous_token = load_previous_api_token(new_token)
        new_context = load_tls_context()
        service.set_api_tokens(new_token, new_previous_token)
        Handler.api_token = new_token
        Handler.previous_api_token = new_previous_token
        return new_context

    needs_reload = (
        args.api_token_file is not None
        or args.api_token_previous_file is not None
        or args.tls_cert is not None
        or args.tls_client_ca_previous is not None
    )
    server = ServiceHTTPServer(
        (args.bind, args.port),
        Handler,
        tls_context=tls_context,
        reload_callback=reload_security if needs_reload else None,
        reload_drain_timeout=args.security_reload_drain_timeout,
    )
    discovery_announcer = None
    if args.worker_discovery_advertise_url:
        if not initial_api_token:
            service.close_all()
            server.server_close()
            parser.error(
                "--worker-discovery-advertise-url requires an active API token"
            )
        try:
            discovery_announcer = WorkerDiscoveryAnnouncer(
                lambda: Handler.api_token,
                args.worker_discovery_advertise_url,
                group=args.worker_discovery_group,
                port=args.worker_discovery_port,
                interval=args.worker_discovery_interval,
                ttl_seconds=args.worker_discovery_ttl,
            )
        except WorkerDiscoveryError as error:
            service.close_all()
            server.server_close()
            parser.error(str(error))
    scheme = "https" if tls_context is not None else "http"
    print(
        "M5Stack simulated devices: "
        f"{scheme}://{args.bind}:{args.port}/platform/web/"
    )
    print(f"Device API: {scheme}://{args.bind}:{args.port}/api/devices")
    print(
        f"Peripheral API: {scheme}://{args.bind}:{args.port}/api/peripherals"
    )
    print(f"Leased service API: {scheme}://{args.bind}:{args.port}/api/v1")
    print(
        f"Storage usage: {scheme}://{args.bind}:{args.port}/api/v1/storage"
    )
    print(
        "Worker lifecycle: "
        f"{scheme}://{args.bind}:{args.port}/api/v1/worker"
    )
    print(
        "Peripheral interfaces: "
        f"{scheme}://{args.bind}:{args.port}/api/peripheral-interfaces"
    )
    if args.tls_client_ca is not None:
        print("TLS client certificate authentication: required")
    if discovery_announcer is not None:
        discovery_announcer.start()
        print(
            "Worker discovery: "
            f"{args.worker_discovery_group}:{args.worker_discovery_port} "
            f"-> {discovery_announcer.service_url}"
        )
    if needs_reload:
        print("Security configuration reload: SIGHUP")
    if hasattr(signal, "SIGHUP"):
        signal.signal(
            signal.SIGHUP,
            lambda _signum, _frame: server.request_security_reload(),
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if discovery_announcer is not None:
            discovery_announcer.close()
        service.close_all()
        server.server_close()


if __name__ == "__main__":
    main()
