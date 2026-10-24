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


class WorkerAgentError(RuntimeError):
    """Raised when the worker cannot register, claim or report a job."""


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
    ):
        self.base_url = base_url.rstrip("/")
        self._lock = threading.RLock()
        self._token = token
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
                f"{path} returned HTTP {error.code}: {body[:1000]!r}"
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise WorkerAgentError(f"{path} request failed: {error}") from error

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
        work_dir: Path,
        identity: dict[str, Any],
        capabilities: dict[str, Any] | None = None,
        poll_seconds: float = 1.0,
        session_timeout: float = 120.0,
        heartbeat_interval: float = 15.0,
    ):
        self.api = api
        self.work_dir = Path(work_dir)
        self.worker_id = str(identity["worker_id"])
        self.instance_id = str(identity["instance_id"])
        self.generation = int(identity["generation"])
        self.capabilities = dict(capabilities or {})
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.session_timeout = max(5.0, float(session_timeout))
        self.heartbeat_interval = max(1.0, float(heartbeat_interval))
        self.registered = False
        if hasattr(self.api, "worker_identity"):
            self.api.worker_identity = self.identity

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "instance_id": self.instance_id,
            "generation": self.generation,
        }

    def register(self) -> dict[str, Any]:
        response = self.api.json(
            "/api/v1/workers",
            method="POST",
            payload={
                **self.identity,
                "stale_after_seconds": max(
                    10,
                    int(self.heartbeat_interval * 3),
                ),
                "endpoint": None,
                "capabilities": self.capabilities,
                "active_lease_ids": [],
            },
        )
        self.registered = True
        return response["worker"]

    def heartbeat_worker(
        self,
        active_lease_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        response = self.api.json(
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
            self.api.json(
                f"/api/v1/workers/{self.worker_id}/stop",
                method="POST",
                payload=self.identity,
            )
        finally:
            self.registered = False

    def claim(self) -> dict[str, Any] | None:
        response = self.api.json(
            "/api/v1/jobs/claim",
            method="POST",
            payload=self.identity,
        )
        job = response.get("job")
        return job if isinstance(job, dict) else None

    def heartbeat_job(
        self,
        job_id: str,
        lease_id: str,
    ) -> dict[str, Any]:
        response = self.api.json(
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
        response = self.api.json(
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

    def _wait_session(self, session_id: str) -> dict[str, Any]:
        deadline = time.time() + self.session_timeout
        latest: dict[str, Any] = {}
        while time.time() < deadline:
            latest = self.api.json(
                f"/api/v1/sessions/{session_id}",
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
            time.sleep(0.25)
        raise WorkerAgentError("session did not reach running before timeout")

    def _collect_evidence(
        self,
        job_id: str,
        session_id: str,
        include: list[str],
    ) -> tuple[bytes, str, Path]:
        query = urlencode({"include": ",".join(include)})
        status, evidence, _content_type = self.api.request(
            f"/api/v1/sessions/{session_id}/evidence?{query}",
            timeout=self.session_timeout,
        )
        if status != 200 or not evidence.startswith(b"PK\x03\x04"):
            raise WorkerAgentError("evidence endpoint did not return a ZIP")
        digest = hashlib.sha256(evidence).hexdigest()
        path = self.work_dir / job_id / "evidence.zip"
        atomic_write(path, evidence)
        return evidence, digest, path

    def execute_job(self, job: dict[str, Any]) -> dict[str, Any]:
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

        session_id: str | None = None
        evidence: bytes | None = None
        evidence_sha256: str | None = None
        evidence_path: Path | None = None
        summary: dict[str, Any] = {}
        state = "FAIL"
        try:
            created = self.api.json(
                "/api/v1/sessions",
                method="POST",
                payload=session_payload,
                timeout=60,
            )
            session_id = str(created["session_id"])
            running = self._wait_session(session_id)
            evidence, evidence_sha256, evidence_path = self._collect_evidence(
                job_id,
                session_id,
                include,
            )
            summary = {
                "device_id": running.get("device_id"),
                "runtime": running.get("runtime"),
                "state": running.get("state"),
                "evidence_bytes": len(evidence),
            }
            state = "PASS"
        except Exception as error:
            summary = {
                "error_type": type(error).__name__,
                "error": str(error)[:1000],
            }
            state = "FAIL"
        finally:
            if session_id is not None:
                try:
                    self.api.json(
                        f"/api/v1/sessions/{session_id}?purge=0",
                        method="DELETE",
                        payload={},
                        timeout=60,
                    )
                except Exception as error:
                    summary.setdefault("cleanup_error", str(error)[:1000])
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
        self.heartbeat_worker()
        job = self.claim()
        if job is None:
            return False
        job_id = str(job["job_id"])
        lease_id = str(job["lease"]["lease_id"])
        heartbeat_stop = threading.Event()
        heartbeat_error: list[str] = []

        def heartbeat_loop() -> None:
            while not heartbeat_stop.wait(self.heartbeat_interval):
                try:
                    self.heartbeat_job(job_id, lease_id)
                    self.heartbeat_worker([job_id])
                except Exception as error:
                    heartbeat_error.append(str(error))
                    heartbeat_stop.set()

        self.heartbeat_worker([job_id])
        heartbeat = threading.Thread(
            target=heartbeat_loop,
            name=f"m5-worker-job-{job_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            result = self.execute_job(job)
            if heartbeat_error:
                result["state"] = "FAIL"
                result["summary"]["heartbeat_error"] = heartbeat_error[-1]
            atomic_write(
                self.work_dir / job_id / "result.json",
                (json.dumps(result, indent=2) + "\n").encode(),
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
    parser.add_argument("--service-url", default="http://127.0.0.1:8787")
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
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    if args.max_jobs is not None and args.max_jobs < 1:
        raise SystemExit("--max-jobs must be positive")
    if args.token and args.token_file:
        raise SystemExit("--token and --token-file are mutually exclusive")
    capabilities = {
        "qemu": True,
        "pcap": True,
    }
    if args.capabilities_json:
        loaded = json.loads(args.capabilities_json)
        if not isinstance(loaded, dict):
            raise SystemExit("--capabilities-json must be an object")
        capabilities = loaded
    def load_token() -> str | None:
        if args.token_file is None:
            return args.token
        try:
            return read_master_token_file(args.token_file)
        except WorkerAuthError as error:
            raise SystemExit(str(error)) from error

    def load_ssl_context() -> ssl.SSLContext | None:
        tls_options = (args.ca_file, args.client_cert, args.client_key)
        if not (
            args.service_url.startswith("https://")
            or any(value is not None for value in tls_options)
        ):
            return None
        if not args.service_url.startswith("https://"):
            raise SystemExit("TLS options require an https:// service URL")
        if (args.client_cert is None) != (args.client_key is None):
            raise SystemExit(
                "--client-cert and --client-key must be provided together"
            )
        try:
            return build_client_tls_context(
                args.ca_file,
                args.client_cert,
                args.client_key,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error

    token = load_token()
    ssl_context = load_ssl_context()
    identity = initialize_identity(args.work_dir, args.worker_id)
    api = Api(args.service_url, token, ssl_context=ssl_context)
    agent = WorkerAgent(
        api,
        work_dir=args.work_dir,
        identity=identity,
        capabilities=capabilities,
        poll_seconds=args.poll_seconds,
        session_timeout=args.session_timeout,
        heartbeat_interval=args.heartbeat_interval,
    )

    def stop(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if args.token_file is not None or any(
        value is not None
        for value in (args.ca_file, args.client_cert, args.client_key)
    ):
        def reload_credentials(_signum: int, _frame: Any) -> None:
            try:
                new_token = load_token()
                new_context = load_ssl_context()
                api.configure_credentials(
                    token=new_token,
                    ssl_context=new_context,
                )
                print("worker credentials reloaded", flush=True)
            except (WorkerAgentError, SystemExit) as error:
                print(
                    f"worker credential reload failed: {error}",
                    flush=True,
                )

        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, reload_credentials)
    try:
        agent.run(once=args.once, max_jobs=args.max_jobs)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
