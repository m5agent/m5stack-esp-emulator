#!/usr/bin/env python3
"""Content-addressed, lease-bound evidence storage for remote workers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MAX_EVIDENCE_BYTES = 96 * 1024 * 1024
MAX_EVIDENCE_RECORDS = 4096
MAX_EVIDENCE_STORE_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_EVIDENCE_RETENTION_SECONDS = 90 * 24 * 60 * 60
_EVIDENCE_ID = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceStoreError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        **details: Any,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                **self.details,
            }
        }


def _iso_now(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).isoformat()


def _bounded_identifier(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or any(ord(char) < 0x20 for char in value)
    ):
        raise EvidenceStoreError(
            "invalid_evidence_binding",
            f"{name} must be a non-empty printable identifier",
        )
    return value


def _identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceStoreError(
            "invalid_evidence_binding",
            "worker identity must be an object",
        )
    worker_id = _bounded_identifier(value.get("worker_id"), "worker_id")
    instance_id = _bounded_identifier(value.get("instance_id"), "instance_id")
    generation = value.get("generation")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
    ):
        raise EvidenceStoreError(
            "invalid_evidence_binding",
            "generation must be a positive integer",
        )
    return {
        "worker_id": worker_id,
        "instance_id": instance_id,
        "generation": generation,
    }


class EvidenceStore:
    """Store immutable ZIP evidence by job/lease ownership and content hash."""

    def __init__(
        self,
        root: Path,
        *,
        retention_seconds: float = DEFAULT_EVIDENCE_RETENTION_SECONDS,
        max_records: int = MAX_EVIDENCE_RECORDS,
        max_bytes: int = MAX_EVIDENCE_STORE_BYTES,
        clock: Callable[[], float] = time.time,
    ):
        self.root = Path(root)
        self.records_dir = self.root / "records"
        self.blobs_dir = self.root / "blobs"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        for directory in (self.root, self.records_dir, self.blobs_dir):
            directory.chmod(0o700)
        self.retention_seconds = max(0.0, float(retention_seconds))
        self.max_records = max(1, int(max_records))
        self.max_bytes = max(1, int(max_bytes))
        self.clock = clock
        self._lock = threading.RLock()

    @staticmethod
    def _evidence_id(
        job_id: str,
        lease_id: str,
        identity: dict[str, Any],
    ) -> str:
        payload = {
            "job_id": job_id,
            "lease_id": lease_id,
            "worker_id": identity["worker_id"],
            "instance_id": identity["instance_id"],
            "generation": identity["generation"],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _record_path(self, evidence_id: str) -> Path:
        if not _EVIDENCE_ID.fullmatch(evidence_id):
            raise EvidenceStoreError(
                "unknown_evidence",
                "invalid evidence id",
                404,
            )
        return self.records_dir / f"{evidence_id}.json"

    def _blob_path(self, sha256: str) -> Path:
        if not _SHA256.fullmatch(sha256):
            raise EvidenceStoreError(
                "invalid_evidence_state",
                "invalid evidence content digest",
                409,
            )
        return self.blobs_dir / f"{sha256}.zip"

    def _load(self, evidence_id: str) -> dict[str, Any]:
        path = self._record_path(evidence_id)
        if not path.is_file():
            raise EvidenceStoreError(
                "unknown_evidence",
                f"unknown evidence: {evidence_id}",
                404,
            )
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceStoreError(
                "invalid_evidence_state",
                f"evidence metadata is unreadable: {evidence_id}",
                409,
            ) from error
        if (
            not isinstance(record, dict)
            or record.get("schema_version") != 1
            or record.get("evidence_id") != evidence_id
            or not _SHA256.fullmatch(str(record.get("content_sha256") or ""))
            or not isinstance(record.get("size"), int)
            or record["size"] <= 0
            or not isinstance(record.get("job_id"), str)
            or not isinstance(record.get("lease_id"), str)
            or not isinstance(record.get("worker"), dict)
        ):
            raise EvidenceStoreError(
                "invalid_evidence_state",
                f"evidence metadata is invalid: {evidence_id}",
                409,
            )
        return record

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as sink:
                sink.write(data)
                sink.flush()
                os.fsync(sink.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _usage_locked(self) -> tuple[int, int]:
        records = 0
        total_bytes = 0
        for path in self.records_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                record = json.loads(path.read_text())
                size = int(record.get("size", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            records += 1
            total_bytes += max(0, size)
        return records, total_bytes

    def put(
        self,
        *,
        job_id: str,
        lease_id: str,
        identity: dict[str, Any],
        data: bytes,
        content_type: str = "application/zip",
    ) -> dict[str, Any]:
        job_id = _bounded_identifier(job_id, "job_id")
        lease_id = _bounded_identifier(lease_id, "lease_id")
        worker = _identity(identity)
        if content_type.split(";", 1)[0].strip().lower() != "application/zip":
            raise EvidenceStoreError(
                "unsupported_evidence_type",
                "evidence content type must be application/zip",
                415,
            )
        if not data or len(data) > MAX_EVIDENCE_BYTES:
            raise EvidenceStoreError(
                "evidence_too_large",
                f"evidence must be 1-{MAX_EVIDENCE_BYTES} bytes",
                413,
            )
        if not data.startswith(b"PK\x03\x04"):
            raise EvidenceStoreError(
                "invalid_evidence_archive",
                "evidence must be a ZIP archive",
                400,
            )
        content_sha256 = hashlib.sha256(data).hexdigest()
        evidence_id = self._evidence_id(job_id, lease_id, worker)
        record_path = self._record_path(evidence_id)
        blob_path = self._blob_path(content_sha256)
        with self._lock:
            if record_path.is_file():
                existing = self._load(evidence_id)
                if (
                    existing.get("content_sha256") != content_sha256
                    or existing.get("size") != len(data)
                ):
                    raise EvidenceStoreError(
                        "evidence_conflict",
                        "a different evidence bundle already exists for this lease",
                        409,
                    )
                return {**existing, "idempotent_replay": True}
            records, total_bytes = self._usage_locked()
            added_bytes = 0 if blob_path.is_file() else len(data)
            if records >= self.max_records:
                raise EvidenceStoreError(
                    "evidence_capacity_exhausted",
                    "evidence record capacity is exhausted",
                    507,
                    capacity=self.max_records,
                )
            if total_bytes + added_bytes > self.max_bytes:
                raise EvidenceStoreError(
                    "evidence_storage_exhausted",
                    "evidence byte capacity is exhausted",
                    507,
                    capacity_bytes=self.max_bytes,
                )
            now = self.clock()
            if not blob_path.is_file():
                self._atomic_write(blob_path, data)
            record = {
                "schema_version": 1,
                "evidence_id": evidence_id,
                "job_id": job_id,
                "lease_id": lease_id,
                "worker": worker,
                "content_sha256": content_sha256,
                "size": len(data),
                "content_type": "application/zip",
                "created_at": _iso_now(now),
            }
            self._atomic_write(
                record_path,
                (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode(),
            )
            return {**record, "idempotent_replay": False}

    def get(self, evidence_id: str) -> dict[str, Any]:
        with self._lock:
            return self._load(evidence_id)

    def content(self, evidence_id: str) -> tuple[bytes, dict[str, Any]]:
        with self._lock:
            record = self._load(evidence_id)
            blob = self._blob_path(record["content_sha256"])
            if not blob.is_file():
                raise EvidenceStoreError(
                    "evidence_content_missing",
                    "evidence metadata exists but content is missing",
                    409,
                )
            data = blob.read_bytes()
            if (
                len(data) != record["size"]
                or hashlib.sha256(data).hexdigest() != record["content_sha256"]
            ):
                raise EvidenceStoreError(
                    "evidence_content_mismatch",
                    "stored evidence content does not match its metadata",
                    409,
                )
            return data, record

    def require_for_result(
        self,
        *,
        job_id: str,
        lease_id: str,
        identity: dict[str, Any],
        evidence_sha256: str,
    ) -> dict[str, Any]:
        if not _SHA256.fullmatch(evidence_sha256):
            raise EvidenceStoreError(
                "invalid_job_result",
                "evidence_sha256 must be a lowercase SHA256",
            )
        worker = _identity(identity)
        evidence_id = self._evidence_id(job_id, lease_id, worker)
        with self._lock:
            record = self._load(evidence_id)
            if record.get("content_sha256") != evidence_sha256:
                raise EvidenceStoreError(
                    "evidence_hash_mismatch",
                    "job result evidence hash does not match stored evidence",
                    409,
                )
            return record

    def delete(self, evidence_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._load(evidence_id)
            self._record_path(evidence_id).unlink(missing_ok=True)
            digest = record["content_sha256"]
            referenced = any(
                candidate.get("content_sha256") == digest
                for candidate in (
                    self._try_load(path.stem)
                    for path in self.records_dir.glob("*.json")
                )
                if candidate is not None
            )
            if not referenced:
                self._blob_path(digest).unlink(missing_ok=True)
            return {"evidence_id": evidence_id, "deleted": True}

    def _try_load(self, evidence_id: str) -> dict[str, Any] | None:
        try:
            return self._load(evidence_id)
        except EvidenceStoreError:
            return None

    def prune(self, *, now: float | None = None) -> dict[str, int]:
        current = self.clock() if now is None else float(now)
        cutoff = current - self.retention_seconds
        removed_records = 0
        removed_blobs = 0
        bytes_removed = 0
        with self._lock:
            for path in list(self.records_dir.glob("*.json")):
                record = self._try_load(path.stem)
                if record is None:
                    continue
                try:
                    created_at = datetime.fromisoformat(
                        str(record["created_at"])
                    ).timestamp()
                except (KeyError, TypeError, ValueError):
                    try:
                        created_at = path.stat().st_mtime
                    except OSError:
                        continue
                if created_at >= cutoff:
                    continue
                try:
                    bytes_removed += path.stat().st_size
                    path.unlink()
                    removed_records += 1
                except OSError:
                    continue
            referenced = {
                record.get("content_sha256")
                for record in (
                    self._try_load(path.stem)
                    for path in self.records_dir.glob("*.json")
                )
                if record is not None
            }
            for path in list(self.blobs_dir.glob("*.zip")):
                if path.stem in referenced:
                    continue
                try:
                    size = path.stat().st_size
                    path.unlink()
                    removed_blobs += 1
                    bytes_removed += size
                except OSError:
                    continue
        return {
            "records_removed": removed_records,
            "blobs_removed": removed_blobs,
            "bytes_removed": bytes_removed,
        }

    def stats(self) -> dict[str, int]:
        with self._lock:
            records, declared_bytes = self._usage_locked()
            return {
                "entries": records,
                "bytes": declared_bytes,
                "max_entries": self.max_records,
                "max_bytes": self.max_bytes,
                "retention_seconds": int(self.retention_seconds),
            }
