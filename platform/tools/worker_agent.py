#!/usr/bin/env python3
"""HTTP-only remote worker executor for durable Device Service jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from transport_security import build_client_tls_context
from worker_auth import (
    WorkerAuthError,
    is_worker_auth_path,
    read_master_token_file,
    sign_worker_request,
)
from worker_discovery import (
    DEFAULT_DISCOVERY_GROUP,
    DEFAULT_DISCOVERY_PORT,
    WorkerDiscoveryError,
    discover_service,
    fetch_discovery_beacon,
)

WORKER_AGENT_STATE_VERSION = 1
DEFAULT_EVIDENCE_INCLUDE = (
    "manifest",
    "serial",
    "frames",
    "logs",
    "network",
    "qom",
)
TERMINAL_SESSION_STATES = {"stopped", "failed"}
CONTROL_RECONNECT_RETRY_SECONDS = 0.5


class WorkerAgentError(RuntimeError):
    """Raised when the worker cannot register, claim or report a job."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        transient: bool = False,
    ):
        super().__init__(message)
        self.status = status
        self.transient = transient


class WorkerLeaseLostError(WorkerAgentError):
    """Raised after job ownership loss fences the local runtime."""


def log_worker_event(message: str) -> None:
    print(message, flush=True)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def credential_file_fingerprint(paths: list[Path]) -> str:
    """Return a secret-free fingerprint of atomic credential file generations."""

    digest = hashlib.sha256()
    for index, path in enumerate(paths):
        digest.update(f"{index}:{path.name}\0".encode())
        try:
            stat = path.stat()
        except FileNotFoundError:
            digest.update(b"missing\0")
            continue
        digest.update(
            (
                f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:"
                f"{stat.st_mtime_ns}\0"
            ).encode()
        )
    return digest.hexdigest()


def load_credential_generation(path: Path) -> dict[str, Any]:
    """Load an immutable credential generation through one atomic pointer."""

    pointer = Path(path)
    try:
        payload = json.loads(pointer.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid credential generation file: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("credential generation file must contain an object")
    if payload.get("schema_version") != 1:
        raise ValueError("credential generation schema_version must be 1")
    generation = payload.get("generation")
    if not isinstance(generation, str) or not generation.strip():
        raise ValueError("credential generation must be a non-empty string")
    resolved: dict[str, Any] = {"generation": generation}
    for key in ("token_file", "ca_file", "client_cert", "client_key"):
        raw = payload.get(key)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"credential generation {key} must be a path")
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = pointer.parent / candidate
        resolved[key] = candidate
    return resolved


class CredentialReloader:
    """All-or-nothing file-generation reload used by worker requests."""

    def __init__(
        self,
        watched_paths: list[Path],
        *,
        load_token: Callable[[], str | None],
        load_ssl_context: Callable[[], ssl.SSLContext | None],
        receipt_dir: Path | None = None,
        logger: Callable[[str], None] = log_worker_event,
    ):
        if not watched_paths:
            raise ValueError("credential reloader requires watched files")
        self.watched_paths = [Path(path) for path in watched_paths]
        self._load_token = load_token
        self._load_ssl_context = load_ssl_context
        self.receipt_dir = Path(receipt_dir) if receipt_dir else None
        self._logger = logger
        self._lock = threading.Lock()
        self._fingerprint: str | None = None

    def mark_current(self) -> str:
        fingerprint = credential_file_fingerprint(self.watched_paths)
        with self._lock:
            self._fingerprint = fingerprint
        return fingerprint

    def _write_receipt(self, api: Api, fingerprint: str) -> None:
        if self.receipt_dir is None:
            return
        identity = api.worker_identity or {}
        worker_id = str(identity.get("worker_id") or "unknown")
        generation = int(identity.get("generation") or 0)
        worker_key = hashlib.sha256(worker_id.encode()).hexdigest()[:16]
        receipt = {
            "schema_version": 1,
            "worker_id": worker_id,
            "generation": generation,
            "reloaded_at": iso_now(),
            "credential_fingerprint": fingerprint,
        }
        atomic_write(
            self.receipt_dir
            / f"worker-{worker_key}-g{generation}.json",
            (json.dumps(receipt, indent=2) + "\n").encode(),
        )

    def apply(self, api: Api, *, force: bool = False) -> bool:
        candidate = credential_file_fingerprint(self.watched_paths)
        if not force and candidate == self._fingerprint:
            return False
        with self._lock:
            candidate = credential_file_fingerprint(self.watched_paths)
            if not force and candidate == self._fingerprint:
                return False
            try:
                token = self._load_token()
                ssl_context = self._load_ssl_context()
                api.configure_credentials(
                    token=token,
                    ssl_context=ssl_context,
                )
            except (Exception, SystemExit) as error:  # noqa: BLE001
                self._logger(f"worker credential reload failed: {error}")
                return False
            self._fingerprint = candidate
            try:
                self._write_receipt(api, candidate)
            except OSError as error:
                self._logger(f"worker credential receipt failed: {error}")
            self._logger(f"worker credentials reloaded fingerprint={candidate}")
            return True


def initialize_identity(work_dir: Path, worker_id: str) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path = work_dir / "agent-state.json"
    previous: dict[str, Any] = {}
    if state_path.is_file():
        try:
            loaded = json.loads(state_path.read_text())
            if isinstance(loaded, dict):
                previous = loaded
        except (OSError, json.JSONDecodeError):
            previous = {}
    generation = (
        int(previous.get("generation", 0)) + 1
        if previous.get("worker_id") == worker_id
        else 1
    )
    identity = {
        "schema_version": WORKER_AGENT_STATE_VERSION,
        "worker_id": worker_id,
        "instance_id": uuid.uuid4().hex,
        "generation": generation,
        "started_at": iso_now(),
    }
    atomic_write(
        state_path,
        (json.dumps(identity, indent=2) + "\n").encode(),
    )
    return identity


class Api:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        ssl_context: ssl.SSLContext | None = None,
        credential_reloader: Callable[[], Any] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._lock = threading.RLock()
        self._token = token
        self._credential_reloader = credential_reloader
        self.worker_identity: dict[str, Any] | None = None
        if not self.base_url.startswith(("http://", "https://")):
            raise WorkerAgentError("service URL must use http:// or https://")
        if self.base_url.startswith("http://") and ssl_context is not None:
            raise WorkerAgentError(
                "TLS client context requires an https:// service URL"
            )
        self._ssl_context = ssl_context

    @property
    def token(self) -> str | None:
        with self._lock:
            return self._token

    @property
    def ssl_context(self) -> ssl.SSLContext | None:
        with self._lock:
            return self._ssl_context

    def configure_credentials(
        self,
        *,
        token: str | None,
        ssl_context: ssl.SSLContext | None,
    ) -> None:
        if self.base_url.startswith("http://") and ssl_context is not None:
            raise WorkerAgentError(
                "TLS client context requires an https:// service URL"
            )
        with self._lock:
            self._token = token
            self._ssl_context = ssl_context

    def set_credential_reloader(
        self,
        reloader: Callable[[], Any] | None,
    ) -> None:
        with self._lock:
            self._credential_reloader = reloader

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> tuple[int, bytes, str]:
        headers: dict[str, str] = {}
        data = None
        with self._lock:
            credential_reloader = self._credential_reloader
        if credential_reloader is not None:
            credential_reloader()
        with self._lock:
            token = self._token
            ssl_context = self._ssl_context
            worker_identity = self.worker_identity
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
            if worker_identity is not None and is_worker_auth_path(method, path):
                headers.update(
                    sign_worker_request(
                        token,
                        worker_identity,
                        method,
                        path,
                        data or b"",
                    )
                )
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        request_options = (
            {"context": ssl_context}
            if ssl_context is not None
            else {}
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
                **request_options,
            ) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            body = error.read()
            raise WorkerAgentError(
                f"{path} returned HTTP {error.code}: {body[:1000]!r}",
                status=error.code,
                transient=error.code >= 500 or error.code == 429,
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise WorkerAgentError(
                f"{path} request failed: {error}",
                transient=True,
            ) from error

    def json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        status, body, _content_type = self.request(
            path,
            method=method,
            payload=payload,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise WorkerAgentError(f"{path} returned HTTP {status}")
        return json.loads(body)


class WorkerAgent:
    def __init__(
        self,
        api: Api,
        *,
        runtime_api: Api | None = None,
        work_dir: Path,
        identity: dict[str, Any],
        endpoint: str | None = None,
        capabilities: dict[str, Any] | None = None,
        poll_seconds: float = 1.0,
        session_timeout: float = 120.0,
        heartbeat_interval: float = 15.0,
        control_reconnect_timeout: float = 30.0,
        runtime_reconnect_timeout: float = 30.0,
    ):
        self.api = api
        self.runtime_api = runtime_api or api
        self.work_dir = Path(work_dir)
        self.worker_id = str(identity["worker_id"])
        self.instance_id = str(identity["instance_id"])
        self.generation = int(identity["generation"])
        self.endpoint = endpoint
        self.capabilities = dict(capabilities or {})
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.session_timeout = max(5.0, float(session_timeout))
        self.heartbeat_interval = max(1.0, float(heartbeat_interval))
        self.control_reconnect_timeout = max(
            0.0,
            float(control_reconnect_timeout),
        )
        self.runtime_reconnect_timeout = max(
            0.0,
            float(runtime_reconnect_timeout),
        )
        self.registered = False
        self._registration_lock = threading.RLock()
        self._control_retry_active = False
        if hasattr(self.api, "worker_identity"):
            self.api.worker_identity = self.identity

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "instance_id": self.instance_id,
            "generation": self.generation,
        }

    def _check_runtime_health(self) -> None:
        if self.runtime_api is self.api:
            return
        try:
            health = self.runtime_api.json("/api/health", timeout=10)
        except Exception as error:
            raise WorkerAgentError(
                f"worker runtime health failed: {error}"
            ) from error
        if not isinstance(health, dict) or health.get("ok") is not True:
            raise WorkerAgentError(
                "worker runtime health did not return ok=true"
            )

    def _register_once(self, *, timeout: float = 60) -> dict[str, Any]:
        with self._registration_lock:
            self._check_runtime_health()
            response = self.api.json(
                "/api/v1/workers",
                method="POST",
                payload={
                    **self.identity,
                    "stale_after_seconds": max(
                        10,
                        int(self.heartbeat_interval * 3),
                    ),
                    "endpoint": self.endpoint,
                    "capabilities": self.capabilities,
                    "active_lease_ids": [],
                },
                timeout=timeout,
            )
            self.registered = True
            return response["worker"]

    def _control_recovery(
        self,
        operation: Callable[[float], Any],
        *,
        recover_registration: bool,
    ) -> Any:
        deadline = time.monotonic() + self.control_reconnect_timeout
        retry_reported = False
        while True:
            try:
                remaining = max(0.05, deadline - time.monotonic())
                if recover_registration and not self.registered:
                    self._register_once(timeout=min(60.0, remaining))
                result = operation(min(60.0, remaining))
                if retry_reported:
                    self._control_retry_active = False
                    log_worker_event("worker control plane reconnected")
                return result
            except WorkerAgentError as error:
                if not error.transient:
                    raise
                self.registered = False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._control_retry_active = False
                    raise
                if not retry_reported:
                    retry_reported = True
                    self._control_retry_active = True
                    log_worker_event("worker control plane unavailable; retrying")
                time.sleep(min(CONTROL_RECONNECT_RETRY_SECONDS, remaining))

    def _control_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        return self._control_recovery(
            lambda request_timeout: self.api.json(
                path,
                method=method,
                payload=payload,
                timeout=min(timeout, request_timeout),
            ),
            recover_registration=True,
        )

    def _runtime_recovery(
        self,
        operation: Callable[[], Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        recovery_timeout = (
            self.runtime_reconnect_timeout
            if timeout is None
            else max(0.0, float(timeout))
        )
        deadline = time.monotonic() + recovery_timeout
        retry_reported = False
        while True:
            try:
                result = operation()
                if retry_reported:
                    log_worker_event("worker runtime service reconnected")
                return result
            except WorkerAgentError as error:
                if not error.transient:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                if not retry_reported:
                    retry_reported = True
                    log_worker_event(
                        "worker runtime service unavailable; retrying"
                    )
                time.sleep(min(CONTROL_RECONNECT_RETRY_SECONDS, remaining))

    def _runtime_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
        api: Api | None = None,
        reconnect_timeout: float | None = None,
    ) -> Any:
        runtime_api = api or self.runtime_api
        return self._runtime_recovery(
            lambda: runtime_api.json(
                path,
                method=method,
                payload=payload,
                timeout=timeout,
            ),
            timeout=reconnect_timeout,
        )

    def _runtime_request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
        api: Api | None = None,
        reconnect_timeout: float | None = None,
    ) -> tuple[int, bytes, str]:
        runtime_api = api or self.runtime_api
        return self._runtime_recovery(
            lambda: runtime_api.request(
                path,
                method=method,
                payload=payload,
                timeout=timeout,
            ),
            timeout=reconnect_timeout,
        )

    def register(self) -> dict[str, Any]:
        return self._control_recovery(
            lambda request_timeout: self._register_once(
                timeout=request_timeout
            ),
            recover_registration=False,
        )

    def heartbeat_worker(
        self,
        active_lease_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        response = self._control_json(
            f"/api/v1/workers/{self.worker_id}/heartbeat",
            method="POST",
            payload={
                **self.identity,
                "state": "ready",
                "capabilities": self.capabilities,
                "active_lease_ids": active_lease_ids or [],
            },
        )
        return response["worker"]

    def stop_worker(self) -> None:
        if not self.registered:
            return
        try:
            self._control_json(
                f"/api/v1/workers/{self.worker_id}/stop",
                method="POST",
                payload=self.identity,
            )
        finally:
            self.registered = False

    def claim(self) -> dict[str, Any] | None:
        claim_idempotency_key = (
            f"claim-{self.instance_id}-{uuid.uuid4().hex}"
        )
        response = self._control_json(
            "/api/v1/jobs/claim",
            method="POST",
            payload={
                **self.identity,
                "claim_idempotency_key": claim_idempotency_key,
            },
        )
        job = response.get("job")
        return job if isinstance(job, dict) else None

    def heartbeat_job(
        self,
        job_id: str,
        lease_id: str,
    ) -> dict[str, Any]:
        response = self._control_json(
            f"/api/v1/jobs/{job_id}/heartbeat",
            method="POST",
            payload={
                **self.identity,
                "lease_id": lease_id,
            },
        )
        return response["job"]

    def report_result(
        self,
        job_id: str,
        lease_id: str,
        *,
        state: str,
        evidence_sha256: str | None,
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._control_json(
            f"/api/v1/jobs/{job_id}/result",
            method="POST",
            payload={
                **self.identity,
                "lease_id": lease_id,
                "state": state,
                "evidence_sha256": evidence_sha256,
                "summary": summary,
            },
        )
        return response["job"]

    def _wait_session(
        self,
        session_id: str,
        *,
        api: Api | None = None,
        lease_fence: threading.Event | None = None,
    ) -> dict[str, Any]:
        runtime_api = api or self.api
        deadline = time.time() + self.session_timeout
        latest: dict[str, Any] = {}
        while time.time() < deadline:
            if lease_fence is not None and lease_fence.is_set():
                raise WorkerLeaseLostError(
                    "job lease ownership was lost before session readiness"
                )
            latest = self._runtime_json(
                f"/api/v1/sessions/{session_id}",
                api=runtime_api,
                reconnect_timeout=min(
                    self.runtime_reconnect_timeout,
                    max(0.0, deadline - time.time()),
                ),
            )
            state = latest.get("state")
            if state == "running":
                return latest
            if state in TERMINAL_SESSION_STATES:
                detail = latest.get("error")
                suffix = f": {detail}" if detail else ""
                raise WorkerAgentError(
                    f"session reached terminal state {state}{suffix}"
                )
            if lease_fence is None:
                time.sleep(0.25)
            elif lease_fence.wait(0.25):
                raise WorkerLeaseLostError(
                    "job lease ownership was lost before session readiness"
                )
        raise WorkerAgentError("session did not reach running before timeout")

    def _collect_evidence(
        self,
        job_id: str,
        session_id: str,
        include: list[str],
        *,
        api: Api | None = None,
        lease_fence: threading.Event | None = None,
    ) -> tuple[bytes, str, Path]:
        if lease_fence is not None and lease_fence.is_set():
            raise WorkerLeaseLostError(
                "job lease ownership was lost before evidence collection"
            )
        runtime_api = api or self.api
        query = urlencode({"include": ",".join(include)})
        status, evidence, _content_type = self._runtime_request(
            f"/api/v1/sessions/{session_id}/evidence?{query}",
            timeout=self.session_timeout,
            api=runtime_api,
        )
        if status != 200 or not evidence.startswith(b"PK\x03\x04"):
            raise WorkerAgentError("evidence endpoint did not return a ZIP")
        if lease_fence is not None and lease_fence.is_set():
            raise WorkerLeaseLostError(
                "job lease ownership was lost during evidence collection"
            )
        digest = hashlib.sha256(evidence).hexdigest()
        path = self.work_dir / job_id / "evidence.zip"
        atomic_write(path, evidence)
        return evidence, digest, path

    def execute_job(
        self,
        job: dict[str, Any],
        *,
        lease_fence: threading.Event | None = None,
    ) -> dict[str, Any]:
        job_id = str(job.get("job_id") or "")
        lease = job.get("lease")
        if not job_id or not isinstance(lease, dict):
            raise WorkerAgentError("claimed job has no job_id or lease")
        if not lease.get("lease_id"):
            raise WorkerAgentError("claimed job lease has no lease_id")
        request = job.get("request")
        if not isinstance(request, dict):
            raise WorkerAgentError("job request must be an object")
        session_payload = request.get("session")
        if not isinstance(session_payload, dict):
            raise WorkerAgentError("job request.session must be an object")
        session_payload = dict(session_payload)
        session_payload.setdefault(
            "idempotency_key",
            f"job-{job_id}:{lease['lease_id']}",
        )
        include = request.get(
            "evidence_include",
            list(DEFAULT_EVIDENCE_INCLUDE),
        )
        if (
            not isinstance(include, list)
            or not include
            or any(not isinstance(item, str) for item in include)
        ):
            raise WorkerAgentError(
                "job request.evidence_include must be a non-empty string list"
            )
        evidence_delay = request.get("evidence_delay_seconds", 0)
        if (
            isinstance(evidence_delay, bool)
            or not isinstance(evidence_delay, (int, float))
            or not 0 <= evidence_delay <= 300
        ):
            raise WorkerAgentError(
                "job request.evidence_delay_seconds must be from 0 to 300"
            )

        session_id: str | None = None
        evidence: bytes | None = None
        evidence_sha256: str | None = None
        evidence_path: Path | None = None
        execution_plane = (
            "worker-local"
            if self.runtime_api is not self.api
            else "control-service"
        )
        summary: dict[str, Any] = {
            "execution_plane": execution_plane,
            "evidence_delay_seconds": float(evidence_delay),
        }
        state = "FAIL"
        runtime_api = self.runtime_api
        try:
            if lease_fence is not None and lease_fence.is_set():
                raise WorkerLeaseLostError(
                    "job lease ownership was lost before session creation"
                )
            created = self._runtime_json(
                "/api/v1/sessions",
                method="POST",
                payload=session_payload,
                timeout=60,
                api=runtime_api,
            )
            session_id = str(created["session_id"])
            if lease_fence is not None and lease_fence.is_set():
                raise WorkerLeaseLostError(
                    "job lease ownership was lost during session creation"
                )
            running = self._wait_session(
                session_id,
                api=runtime_api,
                lease_fence=lease_fence,
            )
            if evidence_delay:
                if lease_fence is None:
                    time.sleep(float(evidence_delay))
                elif lease_fence.wait(float(evidence_delay)):
                    raise WorkerLeaseLostError(
                        "job lease ownership was lost before evidence collection"
                    )
            evidence, evidence_sha256, evidence_path = self._collect_evidence(
                job_id,
                session_id,
                include,
                api=runtime_api,
                lease_fence=lease_fence,
            )
            summary = {
                "device_id": running.get("device_id"),
                "runtime": running.get("runtime"),
                "state": running.get("state"),
                "evidence_bytes": len(evidence),
                "execution_plane": execution_plane,
                "evidence_delay_seconds": float(evidence_delay),
            }
            state = "PASS"
        except Exception as error:
            summary = {
                "execution_plane": execution_plane,
                "error_type": type(error).__name__,
                "error": str(error)[:1000],
            }
            if isinstance(error, WorkerLeaseLostError):
                summary["lease_fenced"] = True
            state = "FAIL"
        finally:
            if session_id is not None:
                try:
                    self._runtime_json(
                        f"/api/v1/sessions/{session_id}?purge=0",
                        method="DELETE",
                        payload={},
                        timeout=60,
                        api=runtime_api,
                    )
                except Exception as error:
                    summary.setdefault("cleanup_error", str(error)[:1000])
                    state = "FAIL"
            if lease_fence is not None and lease_fence.is_set():
                summary["lease_fenced"] = True
                state = "FAIL"

        if evidence_path is not None:
            summary["evidence_path"] = str(evidence_path.relative_to(self.work_dir))
        return {
            "state": state,
            "evidence_sha256": evidence_sha256,
            "summary": summary,
        }

    def work_once(self) -> bool:
        if not self.registered:
            self.register()
        else:
            self._check_runtime_health()
        self.heartbeat_worker()
        job = self.claim()
        if job is None:
            return False
        job_id = str(job["job_id"])
        lease_id = str(job["lease"]["lease_id"])
        heartbeat_stop = threading.Event()
        lease_fence = threading.Event()
        heartbeat_error: list[str] = []

        def heartbeat_loop() -> None:
            while not heartbeat_stop.wait(self.heartbeat_interval):
                try:
                    self.heartbeat_job(job_id, lease_id)
                    self.heartbeat_worker([job_id])
                except Exception as error:
                    heartbeat_error.append(str(error))
                    lease_fence.set()
                    heartbeat_stop.set()

        self.heartbeat_worker([job_id])
        heartbeat = threading.Thread(
            target=heartbeat_loop,
            name=f"m5-worker-job-{job_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            result = self.execute_job(job, lease_fence=lease_fence)
            if heartbeat_error:
                result["state"] = "FAIL"
                result["summary"]["heartbeat_error"] = heartbeat_error[-1]
            if lease_fence.is_set():
                result["state"] = "FAIL"
                result["summary"]["lease_fenced"] = True
            atomic_write(
                self.work_dir / job_id / "result.json",
                (json.dumps(result, indent=2) + "\n").encode(),
            )
            if lease_fence.is_set():
                raise WorkerLeaseLostError(
                    "job lease ownership was lost; runtime was stopped and "
                    "the stale result was not reported"
                )
            self.report_result(
                job_id,
                lease_id,
                state=str(result["state"]),
                evidence_sha256=(
                    result["evidence_sha256"]
                    if isinstance(result.get("evidence_sha256"), str)
                    else None
                ),
                summary=result["summary"],
            )
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2)
        self.heartbeat_worker()
        return True

    def run(
        self,
        *,
        once: bool = False,
        max_jobs: int | None = None,
    ) -> None:
        self.register()
        completed = 0
        try:
            while max_jobs is None or completed < max_jobs:
                if self.work_once():
                    completed += 1
                    if once:
                        break
                else:
                    if once:
                        break
                    time.sleep(self.poll_seconds)
        finally:
            self.stop_worker()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-url")
    parser.add_argument(
        "--discover-control",
        action="store_true",
        help="discover the central control URL from an authenticated multicast beacon",
    )
    parser.add_argument(
        "--discover-control-seed-url",
        default=os.environ.get("M5_WORKER_DISCOVERY_SEED_URL"),
        help=(
            "discover the central control URL from an authenticated unicast "
            "seed usable across subnets and NAT"
        ),
    )
    parser.add_argument(
        "--discover-control-group",
        default=os.environ.get(
            "M5_WORKER_DISCOVERY_GROUP",
            DEFAULT_DISCOVERY_GROUP,
        ),
    )
    parser.add_argument(
        "--discover-control-port",
        type=int,
        default=int(
            os.environ.get(
                "M5_WORKER_DISCOVERY_PORT",
                str(DEFAULT_DISCOVERY_PORT),
            )
        ),
    )
    parser.add_argument(
        "--discover-control-timeout",
        type=float,
        default=float(
            os.environ.get("M5_WORKER_DISCOVERY_TIMEOUT", "15")
        ),
    )
    parser.add_argument(
        "--runtime-service-url",
        default=os.environ.get("M5_RUNTIME_SERVICE_URL"),
        help=(
            "worker-local Device Service used for QEMU execution; defaults "
            "to --service-url for same-host compatibility"
        ),
    )
    parser.add_argument(
        "--advertise-endpoint",
        help=(
            "externally reachable worker HTTP(S) endpoint stored in the "
            "central worker directory"
        ),
    )
    auth_group = parser.add_mutually_exclusive_group()
    auth_group.add_argument(
        "--token",
        default=os.environ.get("M5_SERVICE_API_TOKEN"),
    )
    auth_group.add_argument(
        "--token-file",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_API_TOKEN_FILE"])
            if os.environ.get("M5_SERVICE_API_TOKEN_FILE")
            else None
        ),
    )
    parser.add_argument(
        "--runtime-token",
        default=os.environ.get("M5_RUNTIME_SERVICE_API_TOKEN"),
        help="token for --runtime-service-url; defaults to the control token",
    )
    parser.add_argument(
        "--ca-file",
        type=Path,
        default=(
            Path(os.environ["M5_WORKER_TLS_CA"])
            if os.environ.get("M5_WORKER_TLS_CA")
            else None
        ),
    )
    parser.add_argument(
        "--client-cert",
        type=Path,
        default=(
            Path(os.environ["M5_WORKER_TLS_CLIENT_CERT"])
            if os.environ.get("M5_WORKER_TLS_CLIENT_CERT")
            else None
        ),
    )
    parser.add_argument(
        "--client-key",
        type=Path,
        default=(
            Path(os.environ["M5_WORKER_TLS_CLIENT_KEY"])
            if os.environ.get("M5_WORKER_TLS_CLIENT_KEY")
            else None
        ),
    )
    parser.add_argument(
        "--credential-receipt-dir",
        type=Path,
        help=(
            "write a secret-free receipt after atomically reloading "
            "file-based credentials"
        ),
    )
    parser.add_argument(
        "--credential-generation-file",
        type=Path,
        help=(
            "JSON pointer to an immutable credential generation; the worker "
            "automatically reloads after an atomic pointer replacement"
        ),
    )
    parser.add_argument("--worker-id", default="local-executor")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(".work/worker-agent"),
    )
    parser.add_argument("--capabilities-json", default="")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--session-timeout", type=float, default=120.0)
    parser.add_argument("--heartbeat-interval", type=float, default=15.0)
    parser.add_argument(
        "--control-reconnect-timeout",
        type=float,
        default=float(
            os.environ.get("M5_WORKER_CONTROL_RECONNECT_TIMEOUT", "30")
        ),
    )
    parser.add_argument(
        "--runtime-reconnect-timeout",
        type=float,
        default=float(
            os.environ.get("M5_WORKER_RUNTIME_RECONNECT_TIMEOUT", "30")
        ),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    discovery_sources = sum(
        (
            bool(args.service_url),
            bool(args.discover_control),
            bool(args.discover_control_seed_url),
        )
    )
    if discovery_sources > 1:
        raise SystemExit(
            "--service-url, --discover-control and "
            "--discover-control-seed-url are mutually exclusive"
        )
    if args.discover_control_timeout <= 0:
        raise SystemExit("--discover-control-timeout must be positive")
    resolved_service_url = (
        args.service_url.rstrip("/")
        if args.service_url
        else "http://127.0.0.1:8787"
    )
    if args.advertise_endpoint is not None and not (
        args.advertise_endpoint.startswith("https://")
        or args.advertise_endpoint.startswith("http://")
    ):
        raise SystemExit("--advertise-endpoint must use http:// or https://")
    if args.max_jobs is not None and args.max_jobs < 1:
        raise SystemExit("--max-jobs must be positive")
    if args.control_reconnect_timeout < 0:
        raise SystemExit("--control-reconnect-timeout must be non-negative")
    if args.runtime_reconnect_timeout < 0:
        raise SystemExit("--runtime-reconnect-timeout must be non-negative")
    if args.token and args.token_file:
        raise SystemExit("--token and --token-file are mutually exclusive")
    direct_credential_paths = (
        args.token_file,
        args.ca_file,
        args.client_cert,
        args.client_key,
    )
    if args.credential_generation_file is not None and any(
        value is not None for value in direct_credential_paths
    ):
        raise SystemExit(
            "--credential-generation-file cannot be combined with direct "
            "token/TLS file options"
        )
    capabilities = {
        "qemu": True,
        "pcap": True,
    }
    if args.capabilities_json:
        loaded = json.loads(args.capabilities_json)
        if not isinstance(loaded, dict):
            raise SystemExit("--capabilities-json must be an object")
        capabilities = loaded
    if args.credential_generation_file is not None and (
        args.credential_receipt_dir is None
    ):
        raise SystemExit(
            "--credential-generation-file requires --credential-receipt-dir "
            "for auditable fleet migration"
        )

    def current_generation() -> dict[str, Any] | None:
        if args.credential_generation_file is None:
            return None
        try:
            return load_credential_generation(
                args.credential_generation_file
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error

    def load_token() -> str | None:
        generation = current_generation()
        token_file = (
            generation["token_file"]
            if generation is not None
            else args.token_file
        )
        if token_file is None:
            return args.token
        try:
            return read_master_token_file(token_file)
        except WorkerAuthError as error:
            raise SystemExit(str(error)) from error

    def load_ssl_context() -> ssl.SSLContext | None:
        generation = current_generation()
        ca_file = (
            generation["ca_file"]
            if generation is not None
            else args.ca_file
        )
        client_cert = (
            generation["client_cert"]
            if generation is not None
            else args.client_cert
        )
        client_key = (
            generation["client_key"]
            if generation is not None
            else args.client_key
        )
        tls_options = (ca_file, client_cert, client_key)
        runtime_service_url = (
            args.runtime_service_url.rstrip("/")
            if args.runtime_service_url
            else resolved_service_url
        )
        tls_required = (
            resolved_service_url.startswith("https://")
            or runtime_service_url.startswith("https://")
            or any(value is not None for value in tls_options)
        )
        if not tls_required:
            return None
        if not (
            resolved_service_url.startswith("https://")
            or runtime_service_url.startswith("https://")
        ):
            raise SystemExit("TLS options require an https:// service URL")
        if (client_cert is None) != (client_key is None):
            raise SystemExit(
                "--client-cert and --client-key must be provided together"
            )
        try:
            return build_client_tls_context(
                ca_file,
                client_cert,
                client_key,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error

    watched_paths = (
        [args.credential_generation_file]
        if args.credential_generation_file is not None
        else [
            path
            for path in direct_credential_paths
            if path is not None
        ]
    )
    if args.credential_receipt_dir is not None and (
        args.credential_generation_file is None
    ):
        raise SystemExit(
            "--credential-receipt-dir requires --credential-generation-file"
        )
    token = load_token()
    if args.discover_control:
        if not token:
            raise SystemExit(
                "--discover-control requires an API token or token file"
            )
        try:
            beacon = discover_service(
                token,
                group=args.discover_control_group,
                port=args.discover_control_port,
                timeout=args.discover_control_timeout,
            )
        except WorkerDiscoveryError as error:
            raise SystemExit(str(error)) from error
        resolved_service_url = str(beacon["service_url"]).rstrip("/")
        log_worker_event(
            "worker control service discovered: "
            f"{resolved_service_url}"
        )
    elif args.discover_control_seed_url:
        if not token:
            raise SystemExit(
                "--discover-control-seed-url requires an API token or token file"
            )
        seed_ssl_context = None
        if args.discover_control_seed_url.startswith("https://"):
            generation = current_generation()
            ca_file = (
                generation["ca_file"]
                if generation is not None
                else args.ca_file
            )
            try:
                seed_ssl_context = ssl.create_default_context(
                    cafile=str(ca_file) if ca_file is not None else None
                )
            except (OSError, ssl.SSLError) as error:
                raise SystemExit(
                    f"cannot configure discovery seed TLS trust: {error}"
                ) from error
        try:
            beacon = fetch_discovery_beacon(
                args.discover_control_seed_url,
                token,
                group=args.discover_control_group,
                port=args.discover_control_port,
                timeout=args.discover_control_timeout,
                ssl_context=seed_ssl_context,
            )
        except WorkerDiscoveryError as error:
            raise SystemExit(str(error)) from error
        resolved_service_url = str(beacon["service_url"]).rstrip("/")
        log_worker_event(
            "worker control service discovered via unicast seed: "
            f"{resolved_service_url}"
        )
    requested_runtime_url = (
        args.runtime_service_url.rstrip("/")
        if args.runtime_service_url
        else resolved_service_url
    )
    control_scheme = resolved_service_url.split("://", 1)[0]
    runtime_scheme = requested_runtime_url.split("://", 1)[0]
    if control_scheme != runtime_scheme:
        raise SystemExit(
            "control and runtime service URLs must use the same scheme"
        )
    ssl_context = load_ssl_context()
    identity = initialize_identity(args.work_dir, args.worker_id)
    api = Api(
        resolved_service_url,
        token,
        ssl_context=(
            ssl_context
            if resolved_service_url.startswith("https://")
            else None
        ),
    )
    runtime_service_url = (
        args.runtime_service_url.rstrip("/")
        if args.runtime_service_url
        else api.base_url
    )
    runtime_api = (
        api
        if runtime_service_url == api.base_url
        else Api(
            runtime_service_url,
            args.runtime_token or token,
            ssl_context=(
                ssl_context
                if runtime_service_url.startswith("https://")
                else None
            ),
        )
    )
    credential_reloader = (
        CredentialReloader(
            watched_paths,
            load_token=load_token,
            load_ssl_context=load_ssl_context,
            receipt_dir=args.credential_receipt_dir,
        )
        if watched_paths
        else None
    )
    if credential_reloader is not None:
        credential_reloader.mark_current()
        if args.credential_generation_file is not None:
            def apply_credentials(*, force: bool = False) -> bool:
                changed = credential_reloader.apply(api, force=force)
                if runtime_api is not api and args.runtime_token is None:
                    runtime_api.configure_credentials(
                        token=api.token,
                        ssl_context=(
                            api.ssl_context
                            if runtime_service_url.startswith("https://")
                            else None
                        ),
                    )
                return changed

            api.set_credential_reloader(apply_credentials)
            if runtime_api is not api and args.runtime_token is None:
                runtime_api.set_credential_reloader(apply_credentials)
    else:
        def apply_credentials(*, force: bool = False) -> bool:
            del force
            return False
    agent = WorkerAgent(
        api,
        runtime_api=runtime_api,
        work_dir=args.work_dir,
        identity=identity,
        endpoint=args.advertise_endpoint,
        capabilities=capabilities,
        poll_seconds=args.poll_seconds,
        session_timeout=args.session_timeout,
        heartbeat_interval=args.heartbeat_interval,
        control_reconnect_timeout=args.control_reconnect_timeout,
        runtime_reconnect_timeout=args.runtime_reconnect_timeout,
    )

    def stop(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if credential_reloader is not None:
        def reload_credentials(_signum: int, _frame: Any) -> None:
            apply_credentials(force=True)

        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, reload_credentials)
    try:
        agent.run(once=args.once, max_jobs=args.max_jobs)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
