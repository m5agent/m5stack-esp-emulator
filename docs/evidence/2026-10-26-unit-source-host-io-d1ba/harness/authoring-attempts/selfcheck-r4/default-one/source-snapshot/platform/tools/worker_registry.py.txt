#!/usr/bin/env python3
"""Persistent lifecycle state for one local simulator worker."""
from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


WORKER_SCHEMA_VERSION = 1
WORKER_STATES = {
    "starting",
    "ready",
    "draining",
    "drained",
    "stopped",
}
MAX_ABANDONED_LEASES = 100
MAX_RECENT_RESULTS = 32


class WorkerRegistryError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 503):
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


class WorkerRegistry:
    def __init__(
        self,
        state_path: Path,
        *,
        worker_id: str | None = None,
        heartbeat_interval: float = 5.0,
        stale_after: float = 15.0,
        capabilities: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        if worker_id is not None and (
            not worker_id
            or len(worker_id) > 128
            or any(ord(char) < 32 for char in worker_id)
        ):
            raise WorkerRegistryError(
                "invalid_worker_id",
                "worker_id must be 1-128 printable characters",
                400,
            )
        self.lock_path = self.state_path.with_suffix(
            f"{self.state_path.suffix}.lock"
        )
        self.requested_worker_id = worker_id
        self.heartbeat_interval = max(0.1, float(heartbeat_interval))
        self.stale_after = max(
            self.heartbeat_interval * 2,
            float(stale_after),
        )
        self.capabilities = dict(capabilities or {})
        self.clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._lock_file = None
        self.record: dict[str, Any] = {}
        self.started = False

    def _load_existing(self) -> dict[str, Any] | None:
        if not self.state_path.is_file():
            return None
        try:
            value = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise WorkerRegistryError(
                "worker_state_invalid",
                f"worker state is unreadable: {error}",
            ) from error
        if not isinstance(value, dict):
            raise WorkerRegistryError(
                "worker_state_invalid",
                "worker state must be a JSON object",
            )
        if value.get("schema_version") != WORKER_SCHEMA_VERSION:
            raise WorkerRegistryError(
                "worker_state_invalid",
                "worker state schema_version is unsupported",
            )
        if value.get("state") not in WORKER_STATES:
            raise WorkerRegistryError(
                "worker_state_invalid",
                "worker state value is unsupported",
            )
        if not isinstance(value.get("worker_id"), str) or not value["worker_id"]:
            raise WorkerRegistryError(
                "worker_state_invalid",
                "worker state has no worker_id",
            )
        return value

    def _acquire_lock(self) -> None:
        lock_file = self.lock_path.open("a+")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            lock_file.close()
            raise WorkerRegistryError(
                "worker_state_locked",
                "another worker process owns this state directory",
                409,
            ) from error
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"{os.getpid()}\n")
        lock_file.flush()
        os.fsync(lock_file.fileno())
        self._lock_file = lock_file

    def _release_lock(self) -> None:
        if self._lock_file is None:
            return
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self._lock_file.close()
            self._lock_file = None

    def _write_locked(self) -> None:
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary.write_text(
                json.dumps(self.record, ensure_ascii=False, indent=2) + "\n"
            )
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _tick_locked(self, now: float) -> None:
        if self.record.get("state") != "draining":
            return
        if self.record.get("active_leases"):
            return
        self.record["state"] = "drained"
        self.record["drained_at"] = _iso_now(now)
        self._write_locked()

    def start(self) -> dict:
        with self._lock:
            if self.started:
                return self.snapshot()
            self._acquire_lock()
            try:
                previous = self._load_existing()
                now = self.clock()
                previous_active = (
                    previous.get("active_leases", {})
                    if isinstance(previous, dict)
                    and isinstance(previous.get("active_leases"), dict)
                    else {}
                )
                abandoned = (
                    list(previous.get("abandoned_leases", []))
                    if isinstance(previous, dict)
                    and isinstance(previous.get("abandoned_leases"), list)
                    else []
                )
                for lease_id, lease in previous_active.items():
                    abandoned.append(
                        {
                            "lease_id": str(lease_id),
                            "reserved_at": (
                                lease.get("reserved_at")
                                if isinstance(lease, dict)
                                else None
                            ),
                            "abandoned_at": _iso_now(now),
                            "reason": "worker process restarted",
                        }
                    )
                recent_results = (
                    list(previous.get("recent_results", []))
                    if isinstance(previous, dict)
                    and isinstance(previous.get("recent_results"), list)
                    else []
                )
                worker_id = (
                    self.requested_worker_id
                    or (
                        previous.get("worker_id")
                        if isinstance(previous, dict)
                        else None
                    )
                    or f"worker-{uuid.uuid4().hex[:16]}"
                )
                generation = (
                    int(previous.get("generation", 0)) + 1
                    if isinstance(previous, dict)
                    else 1
                )
                instance_id = uuid.uuid4().hex
                self.record = {
                    "schema_version": WORKER_SCHEMA_VERSION,
                    "worker_id": worker_id,
                    "instance_id": instance_id,
                    "generation": generation,
                    "state": "starting",
                    "pid": os.getpid(),
                    "platform": sys.platform,
                    "started_at": _iso_now(now),
                    "heartbeat_at": _iso_now(now),
                    "heartbeat_interval_seconds": self.heartbeat_interval,
                    "stale_after_seconds": self.stale_after,
                    "drained_at": None,
                    "stopped_at": None,
                    "previous_instance_id": (
                        previous.get("instance_id")
                        if isinstance(previous, dict)
                        else None
                    ),
                    "previous_state": (
                        previous.get("state")
                        if isinstance(previous, dict)
                        else None
                    ),
                    "previous_generation": (
                        previous.get("generation")
                        if isinstance(previous, dict)
                        else None
                    ),
                    "capabilities": self.capabilities,
                    "active_leases": {},
                    "abandoned_leases": abandoned[-MAX_ABANDONED_LEASES:],
                    "recent_results": recent_results[-MAX_RECENT_RESULTS:],
                }
                self.record["state"] = "ready"
                self._write_locked()
                self.started = True
                self._stop.clear()
                self._heartbeat_thread = threading.Thread(
                    target=self._heartbeat_loop,
                    name=f"m5-worker-heartbeat-{worker_id}",
                    daemon=True,
                )
                self._heartbeat_thread.start()
                return self.snapshot()
            except Exception:
                self._release_lock()
                raise

    @property
    def worker_id(self) -> str:
        with self._lock:
            return str(self.record.get("worker_id", ""))

    @property
    def generation(self) -> int:
        with self._lock:
            return int(self.record.get("generation", 0))

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_interval):
            with self._lock:
                if (
                    not self.started
                    or self.record.get("state") in {"stopped"}
                ):
                    return
                now = self.clock()
                self.record["heartbeat_at"] = _iso_now(now)
                self._tick_locked(now)
                self._write_locked()

    def snapshot(self) -> dict:
        with self._lock:
            if not self.record:
                raise WorkerRegistryError(
                    "worker_not_started",
                    "worker has not started",
                )
            now = self.clock()
            self._tick_locked(now)
            heartbeat = _parse_timestamp(self.record.get("heartbeat_at"))
            age = (
                max(0.0, now - heartbeat)
                if heartbeat is not None
                else None
            )
            state = str(self.record.get("state"))
            stale = (
                state not in {"stopped"}
                and (age is None or age > self.stale_after)
            )
            active = self.record.get("active_leases", {})
            return {
                **self.record,
                "active_lease_count": len(active) if isinstance(active, dict) else 0,
                "active_lease_ids": (
                    sorted(active)
                    if isinstance(active, dict)
                    else []
                ),
                "heartbeat_age_seconds": (
                    round(age, 3) if age is not None else None
                ),
                "stale": stale,
                "accepting_leases": state == "ready" and not stale,
            }

    def reserve_lease(
        self,
        lease_id: str,
        *,
        owner: str | None = None,
    ) -> dict:
        if not isinstance(lease_id, str) or not lease_id:
            raise WorkerRegistryError(
                "invalid_worker_lease",
                "lease_id is required",
                400,
            )
        with self._lock:
            now = self.clock()
            self._tick_locked(now)
            heartbeat = _parse_timestamp(self.record.get("heartbeat_at"))
            heartbeat_age = (
                max(0.0, now - heartbeat)
                if heartbeat is not None
                else None
            )
            if (
                self.record.get("state") != "ready"
                or heartbeat_age is None
                or heartbeat_age > self.stale_after
            ):
                raise WorkerRegistryError(
                    "worker_not_accepting",
                    (
                        f"worker is not accepting leases "
                        f"(state={self.record.get('state')}, "
                        f"stale={heartbeat_age is None or heartbeat_age > self.stale_after})"
                    ),
                    503,
                )
            active = self.record.setdefault("active_leases", {})
            if lease_id in active:
                return dict(active[lease_id])
            active[lease_id] = {
                "lease_id": lease_id,
                "owner": owner,
                "reserved_at": _iso_now(now),
            }
            self.record["heartbeat_at"] = _iso_now(now)
            self._write_locked()
            return dict(active[lease_id])

    def release_lease(
        self,
        lease_id: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> dict | None:
        with self._lock:
            now = self.clock()
            active = self.record.setdefault("active_leases", {})
            lease = active.pop(lease_id, None)
            if result is not None:
                recent = self.record.setdefault("recent_results", [])
                recent.append(
                    {
                        "lease_id": lease_id,
                        "completed_at": _iso_now(now),
                        **result,
                    }
                )
                del recent[:-MAX_RECENT_RESULTS]
            self.record["heartbeat_at"] = _iso_now(now)
            self._tick_locked(now)
            self._write_locked()
            return dict(lease) if isinstance(lease, dict) else None

    def drain(self) -> dict:
        with self._lock:
            state = self.record.get("state")
            if state == "stopped":
                raise WorkerRegistryError(
                    "worker_stopped",
                    "stopped worker cannot drain",
                    409,
                )
            now = self.clock()
            self.record["state"] = "draining"
            self.record["heartbeat_at"] = _iso_now(now)
            self._tick_locked(now)
            self._write_locked()
            return self.snapshot()

    def resume(self) -> dict:
        with self._lock:
            if self.record.get("state") == "stopped":
                raise WorkerRegistryError(
                    "worker_stopped",
                    "stopped worker cannot resume",
                    409,
                )
            now = self.clock()
            self.record["state"] = "ready"
            self.record["drained_at"] = None
            self.record["heartbeat_at"] = _iso_now(now)
            self._write_locked()
            return self.snapshot()

    def close(self) -> dict:
        with self._lock:
            if not self.record:
                self._release_lock()
                return {}
            self._stop.set()
            thread = self._heartbeat_thread
            self._heartbeat_thread = None
            now = self.clock()
            self.record["state"] = "stopped"
            self.record["stopped_at"] = _iso_now(now)
            self.record["heartbeat_at"] = _iso_now(now)
            self._write_locked()
            snapshot = self.snapshot()
            self.started = False
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.heartbeat_interval * 2))
        self._release_lock()
        return snapshot
