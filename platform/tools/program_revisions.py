"""Immutable, complete UIFlow Python snapshots, independent of firmware images.

The revision ID hashes canonical UTF-8 JSON containing source_kind, entrypoint
and the full caller files mapping. source_sha256 hashes only that files mapping,
matching uiflow_source's caller-source identity. Generated boot.py is excluded.
No caller code is compiled or executed. The v1 entrypoint is limited to main.py.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
import uuid

from uiflow_source import MAX_SOURCE_BYTES, UIFlowSourceError, _source_files


MAX_REVISIONS = 256
MAX_CONFIGURED_REVISIONS = 4096
MAX_REVISION_BYTES = MAX_SOURCE_BYTES
MAX_RECORD_BYTES = 2 * MAX_REVISION_BYTES
SOURCE_KIND = "uiflow2-python"
_REVISION_ID = re.compile(r"[0-9a-f]{64}\Z")
_PAYLOAD_FIELDS = {"source_kind", "entrypoint", "files"}
_METADATA_FIELDS = {
    "revision_id", "source_kind", "entrypoint", "source_sha256", "files",
    "total_source_bytes", "created_at",
}
_RECORD_FIELDS = {"schema_version", "source", "metadata", "metadata_sha256"}


class RevisionError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source(payload: Any) -> tuple[dict, dict]:
    if not isinstance(payload, dict) or set(payload) - _PAYLOAD_FIELDS:
        raise RevisionError("invalid_program_revision", "only source_kind, entrypoint and files are accepted")
    source_kind = payload.get("source_kind", SOURCE_KIND)
    if source_kind != SOURCE_KIND:
        raise RevisionError("unsupported_program_source_kind", "only uiflow2-python source is supported", 409)
    entrypoint = payload.get("entrypoint", "main.py")
    if entrypoint != "main.py":
        raise RevisionError("unsupported_program_entrypoint", "only main.py is supported", 409)
    try:
        encoded, rows = _source_files(payload.get("files"))
    except UIFlowSourceError as error:
        raise RevisionError(error.code, error.message, error.status) from error
    caller_rows = [
        {key: row[key] for key in ("path", "size", "sha256")}
        for row in rows if row["origin"] == "caller"
    ]
    files = {row["path"]: encoded[row["path"]].decode("utf-8") for row in caller_rows}
    source = {"source_kind": source_kind, "entrypoint": entrypoint, "files": files}
    canonical_source = _canonical(source)
    if len(canonical_source) > MAX_REVISION_BYTES:
        raise RevisionError(
            "program_revision_too_large", "canonical revision JSON is limited to 1048576 UTF-8 bytes", 413,
        )
    metadata = {
        "revision_id": _sha(canonical_source),
        "source_kind": source_kind,
        "entrypoint": entrypoint,
        "source_sha256": _sha(_canonical(files)),
        "files": caller_rows,
        "total_source_bytes": sum(row["size"] for row in caller_rows),
    }
    return source, metadata


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


class ProgramRevisionStore:
    def __init__(self, root: Path, *, max_count: int = MAX_REVISIONS):
        if type(max_count) is not int or not 1 <= max_count <= MAX_CONFIGURED_REVISIONS:
            raise RevisionError("invalid_revision_quota", "max_count must be between 1 and 4096")
        self.root = Path(root)
        self.max_count = max_count
        self._lock = threading.RLock()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RevisionError("program_revision_storage_error", "revision storage is unavailable", 503) from error

    @contextmanager
    def _locked(self, *, exclusive: bool):
        with self._lock:
            try:
                descriptor = os.open(self.root / ".revisions.lock", os.O_RDWR | os.O_CREAT, 0o600)
                lock_file = os.fdopen(descriptor, "a+b")
            except OSError as error:
                raise RevisionError("program_revision_storage_error", "revision storage lock is unavailable", 503) from error
            with lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                except OSError as error:
                    raise RevisionError("program_revision_storage_error", "revision storage lock is unavailable", 503) from error
                # Closing this descriptor releases the lock, also on errors.
                yield

    def _path(self, revision_id: str) -> Path:
        if not isinstance(revision_id, str) or _REVISION_ID.fullmatch(revision_id) is None:
            raise RevisionError("unknown_program_revision", "invalid program revision ID", 404)
        return self.root / f"{revision_id}.json"

    def _read(self, revision_id: str) -> tuple[dict, dict]:
        path = self._path(revision_id)
        try:
            if path.is_symlink():
                raise ValueError("revision must be a regular file")
            with path.open("rb") as source_file:
                data = source_file.read(MAX_RECORD_BYTES + 1)
            if len(data) > MAX_RECORD_BYTES:
                raise ValueError("revision record exceeds its bound")
            record = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
                raise ValueError("invalid revision envelope")
            if type(record["schema_version"]) is not int or record["schema_version"] != 1:
                raise ValueError("invalid revision schema")
            metadata = record["metadata"]
            if not isinstance(metadata, dict) or set(metadata) != _METADATA_FIELDS:
                raise ValueError("invalid revision metadata")
            if _sha(_canonical(metadata)) != record["metadata_sha256"]:
                raise ValueError("revision metadata checksum differs")
            if not isinstance(record["source"], dict) or set(record["source"]) != _PAYLOAD_FIELDS:
                raise ValueError("invalid revision source fields")
            source, derived = _source(record["source"])
            if derived["revision_id"] != revision_id:
                raise ValueError("revision content hash differs")
            created_at = metadata["created_at"]
            if not isinstance(created_at, str) or datetime.fromisoformat(created_at).tzinfo is None:
                raise ValueError("invalid revision timestamp")
            if _canonical(metadata) != _canonical({**derived, "created_at": created_at}):
                raise ValueError("revision metadata differs from source")
            return source, metadata
        except FileNotFoundError as error:
            raise RevisionError("unknown_program_revision", "program revision does not exist", 404) from error
        except (ValueError, UnicodeError, TypeError, KeyError, RecursionError) as error:
            raise RevisionError("program_revision_corrupt", "program revision failed integrity validation", 500) from error
        except OSError as error:
            raise RevisionError("program_revision_storage_error", "program revision could not be read", 503) from error

    def _publish(self, path: Path, record: dict) -> None:
        temporary = self.root / f".{path.stem}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                temporary.chmod(0o600)
                output.write(_canonical(record) + b"\n")
                output.flush()
                os.fsync(output.fileno())
            # Linking a complete file is atomic and cannot overwrite an existing
            # revision, even if another publisher did not honor our lock.
            os.link(temporary, path)
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def create(self, payload: dict) -> dict:
        source, metadata = _source(payload)
        revision_id = metadata["revision_id"]
        path = self._path(revision_id)
        with self._locked(exclusive=True):
            if path.exists() or path.is_symlink():
                stored_source, stored_metadata = self._read(revision_id)
                if stored_source != source:
                    raise RevisionError("program_revision_corrupt", "program revision content differs", 500)
                return stored_metadata
            count = sum(
                1 for candidate in self.root.glob("*.json")
                if _REVISION_ID.fullmatch(candidate.stem)
            )
            if count >= self.max_count:
                raise RevisionError("program_revision_quota_exceeded", "program revision count limit reached", 429)
            metadata["created_at"] = datetime.now(timezone.utc).isoformat()
            record = {
                "schema_version": 1, "source": source, "metadata": metadata,
                "metadata_sha256": _sha(_canonical(metadata)),
            }
            try:
                self._publish(path, record)
            except FileExistsError:
                stored_source, stored_metadata = self._read(revision_id)
                if stored_source != source:
                    raise RevisionError("program_revision_corrupt", "program revision content differs", 500)
                return stored_metadata
            except OSError as error:
                raise RevisionError("program_revision_storage_error", "program revision could not be stored", 503) from error
            return metadata

    def get(self, revision_id: str) -> dict:
        self._path(revision_id)
        with self._locked(exclusive=False):
            return self._read(revision_id)[1]

    def source(self, revision_id: str) -> dict:
        self._path(revision_id)
        with self._locked(exclusive=False):
            source = self._read(revision_id)[0]
            return {"files": source["files"], "entrypoint": source["entrypoint"]}
