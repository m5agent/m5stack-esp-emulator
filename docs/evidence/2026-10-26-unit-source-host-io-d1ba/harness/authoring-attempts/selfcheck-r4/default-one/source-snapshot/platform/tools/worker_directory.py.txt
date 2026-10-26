#!/usr/bin/env python3
"""Persistent directory of remote simulator workers."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

WORKER_DIRECTORY_SCHEMA_VERSION = 1
WORKER_STATES = {"ready", "draining", "drained", "stopped"}
MAX_WORKERS = 128
MAX_ACTIVE_LEASES = 128
MAX_RECENT_RESULTS = 32
MAX_CAPABILITY_BYTES = 16 * 1024


class WorkerDirectoryError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _iso_now(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _bounded_string(
    value: Any,
    field: str,
    *,
    maximum: int = 128,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(char) < 32 for char in value)
    ):
        raise WorkerDirectoryError(
            "invalid_worker",
            f"{field} must be 1-{maximum} printable characters",
        )
    return value


def _lease_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_ACTIVE_LEASES:
        raise WorkerDirectoryError(
            "invalid_worker",
            f"active_lease_ids must be a list of at most {MAX_ACTIVE_LEASES} items",
        )
    result = []
    for item in value:
        lease_id = _bounded_string(item, "active_lease_ids[]")
        if lease_id not in result:
            result.append(lease_id)
    return sorted(result)


def _validate_endpoint(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str) or len(value) > 512:
        raise WorkerDirectoryError(
            "invalid_worker",
            "endpoint must be an HTTP(S) URL or null",
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise WorkerDirectoryError(
            "invalid_worker",
            "endpoint must be an HTTP(S) URL without credentials, query or fragment",
        )
    return value


def _validate_capabilities(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorkerDirectoryError(
            "invalid_worker",
            "capabilities must be an object",
        )
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise WorkerDirectoryError(
            "invalid_worker",
            "capabilities must be JSON serializable",
        ) from error
    if len(encoded.encode()) > MAX_CAPABILITY_BYTES:
        raise WorkerDirectoryError(
            "invalid_worker",
            f"capabilities exceeds {MAX_CAPABILITY_BYTES} bytes",
        )
    return value


class WorkerDirectory:
    def __init__(
        self,
        state_path: Path,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.RLock()
        self.record = self._load()

    def _empty_record(self) -> dict[str, Any]:
        return {
            "schema_version": WORKER_DIRECTORY_SCHEMA_VERSION,
            "updated_at": _iso_now(self.clock()),
            "workers": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return self._empty_record()
        try:
            value = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise WorkerDirectoryError(
                "worker_directory_invalid",
                f"worker directory is unreadable: {error}",
                503,
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != WORKER_DIRECTORY_SCHEMA_VERSION
            or not isinstance(value.get("workers"), dict)
        ):
            raise WorkerDirectoryError(
                "worker_directory_invalid",
                "worker directory schema is unsupported",
                503,
            )
        return value

    def _write_locked(self) -> None:
        self.record["updated_at"] = _iso_now(self.clock())
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps(self.record, ensure_ascii=False, indent=2) + "\n"
            )
            temporary.chmod(0o600)
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _snapshot_worker(
        self,
        worker: dict[str, Any],
        now: float,
    ) -> dict[str, Any]:
        heartbeat = _parse_timestamp(worker.get("heartbeat_at"))
        age = (
            max(0.0, now - heartbeat)
            if heartbeat is not None
            else None
        )
        stale_after = float(worker.get("stale_after_seconds", 15))
        state = str(worker.get("state", "ready"))
        stale = state != "stopped" and (
            age is None or age > stale_after
        )
        leases = (
            worker.get("active_lease_ids", [])
            if isinstance(worker.get("active_lease_ids"), list)
            else []
        )
        return {
            **worker,
            "active_lease_count": len(leases),
            "heartbeat_age_seconds": (
                round(age, 3) if age is not None else None
            ),
            "stale": stale,
            "accepting_leases": state == "ready" and not stale,
        }

    def list_workers(self) -> dict[str, Any]:
        with self._lock:
            now = self.clock()
            workers = [
                self._snapshot_worker(worker, now)
                for worker in self.record["workers"].values()
                if isinstance(worker, dict)
            ]
            workers.sort(key=lambda row: str(row.get("worker_id", "")))
            return {
                "schema_version": WORKER_DIRECTORY_SCHEMA_VERSION,
                "updated_at": self.record.get("updated_at"),
                "worker_count": len(workers),
                "accepting_count": sum(
                    1 for worker in workers if worker["accepting_leases"]
                ),
                "stale_count": sum(
                    1 for worker in workers if worker["stale"]
                ),
                "active_lease_count": sum(
                    worker["active_lease_count"] for worker in workers
                ),
                "workers": workers,
            }

    def register(self, payload: dict) -> dict:
        worker_id = _bounded_string(payload.get("worker_id"), "worker_id")
        instance_id = _bounded_string(
            payload.get("instance_id"), "instance_id"
        )
        generation = payload.get("generation")
        if (
            not isinstance(generation, int)
            or isinstance(generation, bool)
            or generation < 1
        ):
            raise WorkerDirectoryError(
                "invalid_worker",
                "generation must be a positive integer",
            )
        stale_after = payload.get("stale_after_seconds", 15)
        if (
            not isinstance(stale_after, (int, float))
            or isinstance(stale_after, bool)
            or not 2 <= float(stale_after) <= 300
        ):
            raise WorkerDirectoryError(
                "invalid_worker",
                "stale_after_seconds must be between 2 and 300",
            )
        active_lease_ids = _lease_ids(payload.get("active_lease_ids"))
        endpoint = _validate_endpoint(payload.get("endpoint"))
        capabilities = _validate_capabilities(payload.get("capabilities"))
        with self._lock:
            workers = self.record["workers"]
            if len(workers) >= MAX_WORKERS and worker_id not in workers:
                raise WorkerDirectoryError(
                    "worker_capacity_exceeded",
                    f"worker directory is limited to {MAX_WORKERS} entries",
                    409,
                )
            now = self.clock()
            previous = workers.get(worker_id)
            if isinstance(previous, dict):
                previous_snapshot = self._snapshot_worker(previous, now)
                same_instance = (
                    previous.get("instance_id") == instance_id
                    and previous.get("generation") == generation
                )
                if same_instance:
                    if previous.get("state") == "stopped":
                        raise WorkerDirectoryError(
                            "worker_generation_conflict",
                            "a stopped worker requires a higher generation",
                            409,
                        )
                    previous["heartbeat_at"] = _iso_now(now)
                    previous["stale_after_seconds"] = float(stale_after)
                    self._write_locked()
                    return self._snapshot_worker(previous, now)
                if (
                    not previous_snapshot["stale"]
                    and previous.get("state") != "stopped"
                ):
                    raise WorkerDirectoryError(
                        "worker_instance_conflict",
                        "worker_id is owned by a live instance/generation",
                        409,
                    )
                if (
                    generation <= int(previous.get("generation", 0))
                ):
                    raise WorkerDirectoryError(
                        "worker_generation_conflict",
                        "a stopped/stale worker requires a higher generation",
                        409,
                    )
            record = {
                "worker_id": worker_id,
                "instance_id": instance_id,
                "generation": generation,
                "state": "ready",
                "endpoint": endpoint,
                "capabilities": capabilities,
                "active_lease_ids": active_lease_ids,
                "stale_after_seconds": float(stale_after),
                "registered_at": (
                    previous.get("registered_at")
                    if isinstance(previous, dict)
                    else _iso_now(now)
                ),
                "heartbeat_at": _iso_now(now),
                "drained_at": None,
                "stopped_at": None,
                "recent_results": (
                    previous.get("recent_results", [])
                    if isinstance(previous, dict)
                    and isinstance(previous.get("recent_results"), list)
                    else []
                )[-MAX_RECENT_RESULTS:],
            }
            workers[worker_id] = record
            self._write_locked()
            return self._snapshot_worker(record, now)

    def _owned_worker(
        self,
        worker_id: str,
        payload: dict,
        *,
        allow_stopped: bool = False,
    ) -> tuple[str, dict[str, Any], dict[str, Any], float]:
        worker_id = _bounded_string(worker_id, "worker_id")
        instance_id = _bounded_string(
            payload.get("instance_id"), "instance_id"
        )
        generation = payload.get("generation")
        if (
            not isinstance(generation, int)
            or isinstance(generation, bool)
            or generation < 1
        ):
            raise WorkerDirectoryError(
                "invalid_worker",
                "generation must be a positive integer",
            )
        worker = self.record["workers"].get(worker_id)
        if not isinstance(worker, dict):
            raise WorkerDirectoryError(
                "worker_not_found",
                f"unknown worker: {worker_id}",
                404,
            )
        if (
            worker.get("instance_id") != instance_id
            or worker.get("generation") != generation
        ):
            raise WorkerDirectoryError(
                "worker_identity_mismatch",
                "worker instance/generation does not match the directory",
                409,
            )
        now = self.clock()
        snapshot = self._snapshot_worker(worker, now)
        if snapshot["state"] == "stopped" and not allow_stopped:
            raise WorkerDirectoryError(
                "worker_stopped",
                "stopped worker requires a higher generation",
                409,
            )
        return worker_id, worker, snapshot, now

    def heartbeat(self, worker_id: str, payload: dict) -> dict:
        with self._lock:
            _worker_id, worker, _snapshot, now = self._owned_worker(
                worker_id, payload
            )
            state = payload.get("state", worker.get("state", "ready"))
            if state not in {"ready", "draining", "drained"}:
                raise WorkerDirectoryError(
                    "invalid_worker",
                    "heartbeat state must be ready, draining or drained",
                )
            worker["heartbeat_at"] = _iso_now(now)
            worker["state"] = state
            if "active_lease_ids" in payload:
                worker["active_lease_ids"] = _lease_ids(
                    payload.get("active_lease_ids")
                )
            if "capabilities" in payload:
                worker["capabilities"] = _validate_capabilities(
                    payload.get("capabilities")
                )
            if state == "drained":
                worker["drained_at"] = worker["heartbeat_at"]
            elif state == "ready":
                worker["drained_at"] = None
            self._write_locked()
            return self._snapshot_worker(worker, now)

    def drain(self, worker_id: str, payload: dict) -> dict:
        with self._lock:
            _worker_id, worker, _snapshot, now = self._owned_worker(
                worker_id, payload
            )
            worker["state"] = (
                "drained"
                if not worker.get("active_lease_ids")
                else "draining"
            )
            worker["heartbeat_at"] = _iso_now(now)
            worker["drained_at"] = (
                worker["heartbeat_at"]
                if worker["state"] == "drained"
                else None
            )
            self._write_locked()
            return self._snapshot_worker(worker, now)

    def stop(self, worker_id: str, payload: dict) -> dict:
        with self._lock:
            _worker_id, worker, _snapshot, now = self._owned_worker(
                worker_id, payload, allow_stopped=True
            )
            if worker.get("state") == "stopped":
                return self._snapshot_worker(worker, now)
            worker["state"] = "stopped"
            worker["heartbeat_at"] = _iso_now(now)
            worker["stopped_at"] = worker["heartbeat_at"]
            self._write_locked()
            return self._snapshot_worker(worker, now)

    def record_result(self, worker_id: str, payload: dict) -> dict:
        lease_id = _bounded_string(payload.get("lease_id"), "lease_id")
        state = payload.get("state")
        if not isinstance(state, str) or not state or len(state) > 64:
            raise WorkerDirectoryError(
                "invalid_worker_result",
                "result state must be a non-empty string",
            )
        evidence_sha256 = payload.get("evidence_sha256")
        if evidence_sha256 is not None and (
            not isinstance(evidence_sha256, str)
            or len(evidence_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in evidence_sha256
            )
        ):
            raise WorkerDirectoryError(
                "invalid_worker_result",
                "evidence_sha256 must be a lowercase SHA256",
            )
        with self._lock:
            _worker_id, worker, _snapshot, now = self._owned_worker(
                worker_id, payload
            )
            recent = worker.setdefault("recent_results", [])
            recent.append(
                {
                    "lease_id": lease_id,
                    "state": state,
                    "evidence_sha256": evidence_sha256,
                    "completed_at": _iso_now(now),
                }
            )
            del recent[:-MAX_RECENT_RESULTS]
            worker["heartbeat_at"] = _iso_now(now)
            self._write_locked()
            return dict(recent[-1])
