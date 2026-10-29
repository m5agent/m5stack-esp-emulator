#!/usr/bin/env python3
"""Persistent remote-worker job queue with bounded leases."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKER_QUEUE_SCHEMA_VERSION = 1
JOB_STATUSES = {"queued", "leased", "completed", "failed", "cancelled"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
RESULT_STATES = {"PASS", "PARTIAL", "FAIL", "REVIEW"}
DEFAULT_LEASE_SECONDS = 60.0
MAX_JOBS = 1024
MAX_LIST_LIMIT = 200
MAX_REQUEST_BYTES = 64 * 1024
MAX_CAPABILITY_BYTES = 4 * 1024
MAX_SUMMARY_BYTES = 8 * 1024
MAX_ATTEMPTS = 10


class WorkerQueueError(RuntimeError):
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
        raise WorkerQueueError(
            "invalid_job",
            f"{field} must be 1-{maximum} printable characters",
        )
    return value


def _json_object(
    value: Any,
    field: str,
    *,
    maximum_bytes: int,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerQueueError("invalid_job", f"{field} must be an object")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    except (TypeError, ValueError) as error:
        raise WorkerQueueError(
            "invalid_job",
            f"{field} must be JSON serializable",
        ) from error
    if len(encoded) > maximum_bytes:
        raise WorkerQueueError(
            "invalid_job",
            f"{field} exceeds {maximum_bytes} bytes",
        )
    return dict(value)


def _worker_identity(payload: dict[str, Any]) -> dict[str, Any]:
    generation = payload.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
    ):
        raise WorkerQueueError(
            "invalid_worker_identity",
            "generation must be a positive integer",
        )
    return {
        "worker_id": _bounded_string(
            payload.get("worker_id"),
            "worker_id",
        ),
        "instance_id": _bounded_string(
            payload.get("instance_id"),
            "instance_id",
        ),
        "generation": generation,
    }


def _identity_matches(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> bool:
    return all(
        expected.get(key) == actual.get(key)
        for key in (
            "worker_id",
            "instance_id",
            "generation",
        )
    )


def _capability_matches(
    available: dict[str, Any],
    required: dict[str, Any],
) -> bool:
    for key, expected in required.items():
        actual = available.get(key)
        if expected is True:
            if not actual:
                return False
        elif actual != expected:
            return False
    return True


class WorkerJobQueue:
    def __init__(
        self,
        state_path: Path,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = max(5.0, min(float(lease_seconds), 3600.0))
        self.clock = clock
        self._lock = threading.RLock()
        self.record = self._load()

    def _empty_record(self) -> dict[str, Any]:
        return {
            "schema_version": WORKER_QUEUE_SCHEMA_VERSION,
            "updated_at": _iso_now(self.clock()),
            "jobs": {},
            "idempotency": {},
            "claim_idempotency": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return self._empty_record()
        try:
            value = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise WorkerQueueError(
                "worker_queue_invalid",
                f"worker queue is unreadable: {error}",
                503,
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != WORKER_QUEUE_SCHEMA_VERSION
            or not isinstance(value.get("jobs"), dict)
            or not isinstance(value.get("idempotency"), dict)
        ):
            raise WorkerQueueError(
                "worker_queue_invalid",
                "worker queue schema is unsupported",
                503,
            )
        value.setdefault("claim_idempotency", {})
        if not isinstance(value.get("claim_idempotency"), dict):
            raise WorkerQueueError(
                "worker_queue_invalid",
                "worker queue schema is unsupported",
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

    def _job_snapshot(
        self,
        job: dict[str, Any],
        *,
        idempotent_replay: bool = False,
    ) -> dict[str, Any]:
        value = json.loads(json.dumps(job, ensure_ascii=False))
        value["idempotent_replay"] = idempotent_replay
        return value

    def _prune_terminal_locked(self) -> None:
        jobs = self.record["jobs"]
        if len(jobs) < MAX_JOBS:
            return
        terminal = sorted(
            (
                (str(job.get("updated_at", "")), str(job_id))
                for job_id, job in jobs.items()
                if isinstance(job, dict) and job.get("status") in TERMINAL_JOB_STATUSES
            )
        )
        if not terminal:
            raise WorkerQueueError(
                "worker_queue_capacity_exceeded",
                f"worker queue is limited to {MAX_JOBS} jobs",
                409,
            )
        remove_count = max(1, len(jobs) - MAX_JOBS + 1)
        removed = {job_id for _timestamp, job_id in terminal[:remove_count]}
        for job_id in removed:
            jobs.pop(job_id, None)
        idempotency = self.record["idempotency"]
        for key, entry in list(idempotency.items()):
            if not isinstance(entry, dict) or entry.get("job_id") in removed:
                idempotency.pop(key, None)
        claim_idempotency = self.record["claim_idempotency"]
        for key, entry in list(claim_idempotency.items()):
            if not isinstance(entry, dict) or entry.get("job_id") in removed:
                claim_idempotency.pop(key, None)

    def _release_expired_locked(
        self,
        job: dict[str, Any],
        now: float,
        reason: str,
    ) -> None:
        job["lease"] = None
        job["last_released_at"] = _iso_now(now)
        job["last_release_reason"] = reason
        if int(job.get("attempts", 0)) >= int(job.get("max_attempts", 1)):
            job["status"] = "failed"
            job["failure"] = {
                "reason": reason,
                "failed_at": _iso_now(now),
            }
        else:
            job["status"] = "queued"
        job["updated_at"] = _iso_now(now)

    def _reconcile_expired_locked(self, now: float) -> int:
        released = 0
        for job in self.record["jobs"].values():
            if not isinstance(job, dict) or job.get("status") != "leased":
                continue
            lease = job.get("lease")
            expires = (
                _parse_timestamp(lease.get("expires_at"))
                if isinstance(lease, dict)
                else None
            )
            if expires is not None and expires > now:
                continue
            self._release_expired_locked(job, now, "lease_expired")
            released += 1
        return released

    def _counts_locked(self) -> dict[str, int]:
        counts = {status: 0 for status in sorted(JOB_STATUSES)}
        for job in self.record["jobs"].values():
            if isinstance(job, dict):
                status = str(job.get("status"))
                if status in counts:
                    counts[status] += 1
        return counts

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = _json_object(
            payload.get("request"),
            "request",
            maximum_bytes=MAX_REQUEST_BYTES,
        )
        required = _json_object(
            payload.get("required_capabilities", {}),
            "required_capabilities",
            maximum_bytes=MAX_CAPABILITY_BYTES,
        )
        max_attempts = payload.get("max_attempts", 3)
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not 1 <= max_attempts <= MAX_ATTEMPTS
        ):
            raise WorkerQueueError(
                "invalid_job",
                f"max_attempts must be between 1 and {MAX_ATTEMPTS}",
            )
        label = payload.get("label")
        if label is not None:
            label = _bounded_string(label, "label", maximum=160)
        idempotency_key = payload.get("idempotency_key")
        if idempotency_key is not None:
            idempotency_key = _bounded_string(
                idempotency_key,
                "idempotency_key",
                maximum=160,
            )
        canonical = json.dumps(
            {
                "request": request,
                "required_capabilities": required,
                "max_attempts": max_attempts,
                "label": label,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        with self._lock:
            if idempotency_key is not None:
                existing = self.record["idempotency"].get(idempotency_key)
                if isinstance(existing, dict):
                    if existing.get("request_sha256") != digest:
                        raise WorkerQueueError(
                            "idempotency_conflict",
                            "idempotency_key was used for a different job",
                            409,
                        )
                    job = self.record["jobs"].get(existing.get("job_id"))
                    if isinstance(job, dict):
                        return self._job_snapshot(
                            job,
                            idempotent_replay=True,
                        )
            self._prune_terminal_locked()
            now = self.clock()
            job_id = f"job-{uuid.uuid4().hex[:20]}"
            job = {
                "job_id": job_id,
                "status": "queued",
                "label": label,
                "request": request,
                "request_sha256": digest,
                "required_capabilities": required,
                "max_attempts": max_attempts,
                "attempts": 0,
                "created_at": _iso_now(now),
                "updated_at": _iso_now(now),
                "lease": None,
                "last_worker": None,
                "last_released_at": None,
                "last_release_reason": None,
                "result": None,
                "failure": None,
            }
            self.record["jobs"][job_id] = job
            if idempotency_key is not None:
                self.record["idempotency"][idempotency_key] = {
                    "job_id": job_id,
                    "request_sha256": digest,
                    "created_at": _iso_now(now),
                }
            self._write_locked()
            return self._job_snapshot(job)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if status is not None and status not in JOB_STATUSES:
            raise WorkerQueueError(
                "invalid_job_status",
                "unknown job status",
            )
        if not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
            raise WorkerQueueError(
                "invalid_job_limit",
                f"limit must be between 1 and {MAX_LIST_LIMIT}",
            )
        with self._lock:
            if self._reconcile_expired_locked(self.clock()):
                self._write_locked()
            rows = [
                self._job_snapshot(job)
                for job in self.record["jobs"].values()
                if isinstance(job, dict)
                and (status is None or job.get("status") == status)
            ]
            rows.sort(
                key=lambda job: (
                    str(job.get("created_at", "")),
                    str(job.get("job_id", "")),
                ),
                reverse=True,
            )
            return {
                "schema_version": WORKER_QUEUE_SCHEMA_VERSION,
                "updated_at": self.record.get("updated_at"),
                "job_count": len(self.record["jobs"]),
                "counts": self._counts_locked(),
                "jobs": rows[:limit],
            }

    def get_job(self, job_id: str) -> dict[str, Any]:
        job_id = _bounded_string(job_id, "job_id")
        with self._lock:
            if self._reconcile_expired_locked(self.clock()):
                self._write_locked()
            job = self.record["jobs"].get(job_id)
            if not isinstance(job, dict):
                raise WorkerQueueError(
                    "job_not_found",
                    f"unknown job: {job_id}",
                    404,
                )
            return self._job_snapshot(job)

    def claim(
        self,
        payload: dict[str, Any],
        workers: Iterable[dict[str, Any]],
    ) -> dict[str, Any] | None:
        identity = _worker_identity(payload)
        worker = next(
            (
                row
                for row in workers
                if isinstance(row, dict)
                and row.get("worker_id") == identity["worker_id"]
            ),
            None,
        )
        if worker is None:
            raise WorkerQueueError(
                "worker_not_found",
                "worker is not registered",
                404,
            )
        registered_identity = {
            "worker_id": worker.get("worker_id"),
            "instance_id": worker.get("instance_id"),
            "generation": worker.get("generation"),
        }
        if not _identity_matches(identity, registered_identity):
            raise WorkerQueueError(
                "worker_identity_mismatch",
                "worker instance/generation does not match the directory",
                409,
            )
        requested_job_id = payload.get("job_id")
        if requested_job_id is not None:
            requested_job_id = _bounded_string(
                requested_job_id,
                "job_id",
            )
        claim_idempotency_key = payload.get("claim_idempotency_key")
        if claim_idempotency_key is not None:
            claim_idempotency_key = _bounded_string(
                claim_idempotency_key,
                "claim_idempotency_key",
                maximum=160,
            )
        claim_request_digest = (
            hashlib.sha256(
                json.dumps(
                    {
                        "identity": identity,
                        "job_id": requested_job_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            if claim_idempotency_key is not None
            else None
        )
        claim_key_digest = (
            hashlib.sha256(
                json.dumps(
                    {
                        "identity": identity,
                        "claim_idempotency_key": claim_idempotency_key,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            if claim_idempotency_key is not None
            else None
        )
        capabilities = worker.get("capabilities")
        if not isinstance(capabilities, dict):
            capabilities = {}
        with self._lock:
            now = self.clock()
            expired = self._reconcile_expired_locked(now)
            if expired:
                self._write_locked()
            if claim_key_digest is not None:
                existing_claim = self.record["claim_idempotency"].get(
                    claim_key_digest
                )
                if isinstance(existing_claim, dict):
                    if (
                        existing_claim.get("request_sha256")
                        != claim_request_digest
                    ):
                        raise WorkerQueueError(
                            "claim_idempotency_conflict",
                            "claim idempotency key was used for another request",
                            409,
                        )
                    existing_job = self.record["jobs"].get(
                        existing_claim.get("job_id")
                    )
                    existing_lease = (
                        existing_job.get("lease")
                        if isinstance(existing_job, dict)
                        else None
                    )
                    if (
                        isinstance(existing_job, dict)
                        and existing_job.get("status") == "leased"
                        and isinstance(existing_lease, dict)
                        and existing_lease.get("lease_id")
                        == existing_claim.get("lease_id")
                        and _identity_matches(identity, existing_lease)
                    ):
                        snapshot = self._job_snapshot(existing_job)
                        snapshot["claim_idempotent_replay"] = True
                        return snapshot
                    raise WorkerQueueError(
                        "claim_idempotency_stale",
                        "claim idempotency key no longer owns a live lease",
                        409,
                    )
            if not worker.get("accepting_leases"):
                raise WorkerQueueError(
                    "worker_not_accepting",
                    "worker is not accepting new jobs",
                    409,
                )
            candidates = sorted(
                (
                    job
                    for job in self.record["jobs"].values()
                    if isinstance(job, dict)
                    and job.get("status") == "queued"
                    and (
                        requested_job_id is None
                        or job.get("job_id") == requested_job_id
                    )
                    and _capability_matches(
                        capabilities,
                        (
                            job.get("required_capabilities")
                            if isinstance(
                                job.get("required_capabilities"),
                                dict,
                            )
                            else {}
                        ),
                    )
                ),
                key=lambda job: (
                    str(job.get("created_at", "")),
                    str(job.get("job_id", "")),
                ),
            )
            if not candidates:
                return None
            job = candidates[0]
            lease_id = f"lease-{uuid.uuid4().hex[:20]}"
            job["status"] = "leased"
            job["attempts"] = int(job.get("attempts", 0)) + 1
            job["last_worker"] = identity
            job["lease"] = {
                "lease_id": lease_id,
                **identity,
                "claimed_at": _iso_now(now),
                "heartbeat_at": _iso_now(now),
                "expires_at": _iso_now(now + self.lease_seconds),
            }
            job["updated_at"] = _iso_now(now)
            if claim_key_digest is not None:
                self.record["claim_idempotency"][claim_key_digest] = {
                    "job_id": job["job_id"],
                    "lease_id": lease_id,
                    "identity": identity,
                    "request_sha256": claim_request_digest,
                    "created_at": _iso_now(now),
                }
            self._write_locked()
            snapshot = self._job_snapshot(job)
            if claim_key_digest is not None:
                snapshot["claim_idempotent_replay"] = False
            return snapshot

    def _owned_lease(
        self,
        job_id: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], float]:
        job_id = _bounded_string(job_id, "job_id")
        identity = _worker_identity(payload)
        lease_id = _bounded_string(payload.get("lease_id"), "lease_id")
        now = self.clock()
        if self._reconcile_expired_locked(now):
            self._write_locked()
        job = self.record["jobs"].get(job_id)
        if not isinstance(job, dict):
            raise WorkerQueueError(
                "job_not_found",
                f"unknown job: {job_id}",
                404,
            )
        if job.get("status") != "leased":
            raise WorkerQueueError(
                "job_not_leased",
                f"job is {job.get('status')}",
                409,
            )
        lease = job.get("lease")
        if (
            not isinstance(lease, dict)
            or lease.get("lease_id") != lease_id
            or not _identity_matches(identity, lease)
        ):
            raise WorkerQueueError(
                "job_lease_mismatch",
                "worker identity or lease does not own this job",
                409,
            )
        return job, identity, now

    def heartbeat(
        self,
        job_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            job, _identity, now = self._owned_lease(job_id, payload)
            lease = job["lease"]
            lease["heartbeat_at"] = _iso_now(now)
            lease["expires_at"] = _iso_now(now + self.lease_seconds)
            job["updated_at"] = _iso_now(now)
            self._write_locked()
            return self._job_snapshot(job)

    def validate_lease(
        self,
        job_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Read-only ownership check used before accepting lease-bound evidence."""
        with self._lock:
            job, identity, now = self._owned_lease(job_id, payload)
            lease = job["lease"]
            assert isinstance(lease, dict)
            return {
                "job_id": job_id,
                "lease_id": lease["lease_id"],
                "worker": identity,
                "expires_at": lease["expires_at"],
                "validated_at": _iso_now(now),
            }

    def result(
        self,
        job_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        state = payload.get("state")
        if state not in RESULT_STATES:
            raise WorkerQueueError(
                "invalid_job_result",
                "state must be PASS, PARTIAL, FAIL or REVIEW",
            )
        evidence_sha256 = payload.get("evidence_sha256")
        if evidence_sha256 is not None and (
            not isinstance(evidence_sha256, str)
            or len(evidence_sha256) != 64
            or any(char not in "0123456789abcdef" for char in evidence_sha256)
        ):
            raise WorkerQueueError(
                "invalid_job_result",
                "evidence_sha256 must be a lowercase SHA256",
            )
        evidence_id = payload.get("evidence_id")
        if evidence_id is not None and (
            not isinstance(evidence_id, str)
            or len(evidence_id) != 64
            or any(char not in "0123456789abcdef" for char in evidence_id)
        ):
            raise WorkerQueueError(
                "invalid_job_result",
                "evidence_id must be a lowercase SHA256",
            )
        if evidence_id is not None and evidence_sha256 is None:
            raise WorkerQueueError(
                "invalid_job_result",
                "evidence_id requires evidence_sha256",
            )
        summary = _json_object(
            payload.get("summary", {}),
            "summary",
            maximum_bytes=MAX_SUMMARY_BYTES,
        )
        with self._lock:
            job, identity, now = self._owned_lease(job_id, payload)
            lease_id = str(job["lease"]["lease_id"])
            job["result"] = {
                "state": state,
                "lease_id": lease_id,
                "evidence_id": evidence_id,
                "evidence_sha256": evidence_sha256,
                "summary": summary,
                "worker": identity,
                "completed_at": _iso_now(now),
            }
            job["status"] = "failed" if state == "FAIL" else "completed"
            job["lease"] = None
            job["failure"] = (
                {
                    "reason": "worker_reported_fail",
                    "failed_at": _iso_now(now),
                }
                if state == "FAIL"
                else None
            )
            job["updated_at"] = _iso_now(now)
            self._write_locked()
            return self._job_snapshot(job)

    def cancel(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = _bounded_string(job_id, "job_id")
        reason = _bounded_string(
            payload.get("reason", "cancelled_by_operator"),
            "reason",
            maximum=256,
        )
        with self._lock:
            now = self.clock()
            if self._reconcile_expired_locked(now):
                self._write_locked()
            job = self.record["jobs"].get(job_id)
            if not isinstance(job, dict):
                raise WorkerQueueError(
                    "job_not_found",
                    f"unknown job: {job_id}",
                    404,
                )
            if job.get("status") in TERMINAL_JOB_STATUSES:
                return self._job_snapshot(job)
            job["status"] = "cancelled"
            job["lease"] = None
            job["failure"] = {
                "reason": reason,
                "failed_at": _iso_now(now),
            }
            job["updated_at"] = _iso_now(now)
            self._write_locked()
            return self._job_snapshot(job)

    def reconcile(
        self,
        workers: Iterable[dict[str, Any]],
    ) -> dict[str, int]:
        snapshots = {
            str(worker.get("worker_id")): worker
            for worker in workers
            if isinstance(worker, dict) and worker.get("worker_id")
        }
        released = 0
        with self._lock:
            now = self.clock()
            released += self._reconcile_expired_locked(now)
            for job in self.record["jobs"].values():
                if not isinstance(job, dict) or job.get("status") != "leased":
                    continue
                lease = job.get("lease")
                if not isinstance(lease, dict):
                    self._release_expired_locked(
                        job,
                        now,
                        "invalid_lease",
                    )
                    released += 1
                    continue
                worker = snapshots.get(str(lease.get("worker_id")))
                if worker is None:
                    reason = "worker_missing"
                elif worker.get("instance_id") != lease.get(
                    "instance_id"
                ) or worker.get("generation") != lease.get("generation"):
                    reason = "worker_generation_changed"
                elif worker.get("stale"):
                    reason = "worker_stale"
                elif worker.get("state") in {"stopped", "drained"}:
                    reason = f"worker_{worker.get('state')}"
                else:
                    continue
                self._release_expired_locked(job, now, reason)
                released += 1
            if released:
                self._write_locked()
            return {
                "released_jobs": released,
                **self._counts_locked(),
            }
