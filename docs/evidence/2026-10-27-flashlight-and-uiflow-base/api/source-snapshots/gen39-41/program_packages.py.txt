"""Immutable files for same-guest MicroPython deployment, never host-executed.

Package identity covers the entrypoint and every path/content hash. Incoming
UTF-8 and base64 representations of the same bytes have the same identity.
The store owns canonical base64 bytes, independently of mutable upload caches.
Guest filesystem transfer and .mpy runtime compatibility are separate gates.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
from typing import Any
import unicodedata
import uuid


SOURCE_KIND = "uiflow2-package"
ENTRYPOINTS = ("main.py", "main.mpy")
MAX_PACKAGES = 256
MAX_PACKAGE_BYTES = 1024 * 1024
MAX_PACKAGE_FILES = 64
MAX_FILE_BYTES = 256 * 1024
MAX_PATH_BYTES = 192
MAX_PATH_DEPTH = 8
MAX_RECORD_BYTES = 2 * MAX_PACKAGE_BYTES
_REVISION_ID = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_FIELDS = {"source_kind", "entrypoint", "files"}
_METADATA_FIELDS = {
    "revision_id", "source_sha256", "source_kind", "entrypoint",
    "total_file_bytes", "files", "created_at",
}
_RECORD_FIELDS = {"schema_version", "source", "metadata", "metadata_sha256"}


class ProgramPackageError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _path_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _file_path(path: Any) -> str:
    if not isinstance(path, str):
        raise ProgramPackageError("invalid_program_package_path", "file paths must be strings")
    try:
        encoded = path.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ProgramPackageError("invalid_program_package_path", "file paths must be valid UTF-8") from error
    parts = path.split("/")
    if (
        not path or "\\" in path or ":" in path
        or any(unicodedata.category(char) == "Cc" for char in path)
        or any(part in {"", ".", ".."} for part in parts)
        or PurePosixPath(path).is_absolute()
        or PurePosixPath(path).as_posix() != path
        or unicodedata.normalize("NFC", path) != path
        or len(encoded) > MAX_PATH_BYTES
        or len(parts) > MAX_PATH_DEPTH
        or any(len(part.encode("utf-8")) > 255 for part in parts)
    ):
        raise ProgramPackageError(
            "invalid_program_package_path", "paths must be canonical relative UTF-8 POSIX paths"
        )
    if _path_key(parts[-1]) == "boot.py":
        raise ProgramPackageError(
            "reserved_program_package_path", "boot.py belongs to session initialization", 409
        )
    return path


def _decode_file(value: Any) -> bytes:
    if not isinstance(value, dict) or set(value) != {"encoding", "data"}:
        raise ProgramPackageError(
            "invalid_program_package_file", "file values require only encoding and string data"
        )
    encoding, data = value["encoding"], value["data"]
    if not isinstance(data, str) or encoding not in ("utf8", "base64"):
        raise ProgramPackageError(
            "invalid_program_package_file", "file encoding must be utf8 or base64 with string data"
        )
    if len(data) > (MAX_FILE_BYTES if encoding == "utf8" else 4 * ((MAX_FILE_BYTES + 2) // 3)):
        raise ProgramPackageError("program_package_too_large", "file exceeds 256 KiB decoded bytes", 413)
    try:
        if encoding == "utf8":
            decoded = data.encode("utf-8")
        else:
            decoded = base64.b64decode(data, validate=True)
            if base64.b64encode(decoded).decode("ascii") != data:
                raise ValueError("noncanonical base64")
    except (UnicodeError, binascii.Error, ValueError) as error:
        raise ProgramPackageError(
            "invalid_program_package_file", "file data must use strict UTF-8 or canonical base64"
        ) from error
    if len(decoded) > MAX_FILE_BYTES:
        raise ProgramPackageError("program_package_too_large", "file exceeds 256 KiB decoded bytes", 413)
    return decoded


def _kind(path: str, data: bytes) -> str:
    if path.endswith(".py"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProgramPackageError(
                "invalid_program_package_source", "Python files must contain valid UTF-8"
            ) from error
        if b"\x00" in data:
            raise ProgramPackageError("invalid_program_package_source", "Python files must not contain NUL bytes")
        return "python"
    if path.endswith(".mpy"):
        # Format/architecture compatibility belongs to the actual guest. This
        # is only a basic header check, never a claim that import will succeed.
        if len(data) < 4 or data[0] != ord("M") or data[2] & 0x80:
            raise ProgramPackageError("invalid_program_package_mpy", "invalid .mpy header")
        return "mpy"
    return "resource"


def _snapshot(payload: Any) -> tuple[dict, dict, dict[str, bytes]]:
    if not isinstance(payload, dict) or set(payload) - _SOURCE_FIELDS:
        raise ProgramPackageError("invalid_program_package", "only source_kind, entrypoint and files are accepted")
    if payload.get("source_kind", SOURCE_KIND) != SOURCE_KIND:
        raise ProgramPackageError("unsupported_program_source_kind", "source_kind must be uiflow2-package", 409)
    entrypoint = payload.get("entrypoint", "main.py")
    if entrypoint not in ENTRYPOINTS:
        raise ProgramPackageError("unsupported_program_entrypoint", "package entrypoint must be main.py or main.mpy", 409)
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ProgramPackageError("invalid_program_package", "files must be a non-empty object")
    if len(files) > MAX_PACKAGE_FILES:
        raise ProgramPackageError("program_package_too_large", "at most 64 package files are allowed", 413)
    encoded, seen, namespace, total = {}, set(), {}, 0
    for candidate, value in files.items():
        path = _file_path(candidate)
        key = _path_key(path)
        if key in seen:
            raise ProgramPackageError("program_package_path_conflict", "file paths collide after case normalization", 409)
        seen.add(key)
        parts = path.split("/")
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            prefix_key = _path_key(prefix)
            if prefix_key in namespace and namespace[prefix_key] != prefix:
                raise ProgramPackageError(
                    "program_package_path_conflict", "file or directory names collide after case normalization", 409
                )
            namespace[prefix_key] = prefix
        data = _decode_file(value)
        total += len(data)
        if total > MAX_PACKAGE_BYTES:
            raise ProgramPackageError("program_package_too_large", "package exceeds 1 MiB decoded bytes", 413)
        encoded[path] = data
    if entrypoint not in encoded:
        raise ProgramPackageError("invalid_program_package", "the selected root entrypoint file is required")
    if entrypoint == "main.mpy" and any(
        _path_key(path) == "main.py" or _path_key(path.split("/", 1)[0]) == "main"
        for path in encoded
    ):
        # The real importer searches a directory and then .py before .mpy.
        # Reject these alternatives rather than allowing caller-selected
        # bytecode to be silently replaced by another file at execution time.
        raise ProgramPackageError(
            "program_package_entrypoint_conflict", "main.mpy cannot coexist with main.py or a main path", 409
        )
    for path in encoded:
        if any(_path_key(str(parent)) in seen for parent in PurePosixPath(path).parents if str(parent) != "."):
            raise ProgramPackageError("program_package_path_conflict", "a file is also used as a parent directory", 409)
    rows = [
        {"path": path, "size": len(data), "sha256": _sha(data), "kind": _kind(path, data)}
        for path, data in sorted(encoded.items())
    ]
    hashes = {row["path"]: row["sha256"] for row in rows}
    identity = {"source_kind": SOURCE_KIND, "entrypoint": entrypoint, "files": hashes}
    source = {"source_kind": SOURCE_KIND, "entrypoint": entrypoint, "files": {
        path: {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")}
        for path, data in sorted(encoded.items())
    }}
    metadata = {
        "revision_id": _sha(_canonical(identity)), "source_sha256": _sha(_canonical(hashes)),
        "source_kind": SOURCE_KIND, "entrypoint": entrypoint, "total_file_bytes": total, "files": rows,
    }
    return source, metadata, encoded


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


class ProgramPackageStore:
    def __init__(self, root: Path, *, max_count: int = MAX_PACKAGES):
        if type(max_count) is not int or not 1 <= max_count <= MAX_PACKAGES:
            raise ProgramPackageError("invalid_package_quota", "max_count must be between 1 and 256")
        self.root = Path(root)
        self.max_count = max_count
        self._lock = threading.RLock()
        try:
            if self.root.is_symlink():
                raise OSError("package root must not be a symlink")
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ProgramPackageError("program_package_storage_error", "package storage is unavailable", 503) from error

    @contextmanager
    def _locked(self, *, exclusive: bool):
        with self._lock:
            try:
                descriptor = os.open(
                    self.root / ".packages.lock",
                    os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), 0o600,
                )
                try:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise OSError("package lock must be a regular file")
                    lock_file = os.fdopen(descriptor, "a+b")
                except BaseException:
                    os.close(descriptor)
                    raise
            except OSError as error:
                raise ProgramPackageError("program_package_storage_error", "package storage lock is unavailable", 503) from error
            with lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                except OSError as error:
                    raise ProgramPackageError("program_package_storage_error", "package storage lock is unavailable", 503) from error
                yield

    def _path(self, revision_id: str) -> Path:
        if not isinstance(revision_id, str) or _REVISION_ID.fullmatch(revision_id) is None:
            raise ProgramPackageError("unknown_program_package", "invalid package revision ID", 404)
        return self.root / f"{revision_id}.json"

    def _read(self, revision_id: str) -> tuple[dict, dict, dict[str, bytes]]:
        path = self._path(revision_id)
        try:
            if path.is_symlink():
                raise ValueError("package must not be a symlink")
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ValueError("package must be a regular file")
                source_file = os.fdopen(descriptor, "rb")
            except BaseException:
                os.close(descriptor)
                raise
            with source_file:
                data = source_file.read(MAX_RECORD_BYTES + 1)
            if len(data) > MAX_RECORD_BYTES:
                raise ValueError("package record exceeds its bound")
            record = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
                raise ValueError("invalid package envelope")
            if type(record["schema_version"]) is not int or record["schema_version"] != 1:
                raise ValueError("invalid package schema")
            metadata = record["metadata"]
            if not isinstance(metadata, dict) or set(metadata) != _METADATA_FIELDS:
                raise ValueError("invalid package metadata")
            if _sha(_canonical(metadata)) != record["metadata_sha256"]:
                raise ValueError("package metadata checksum differs")
            if not isinstance(record["source"], dict) or set(record["source"]) != _SOURCE_FIELDS:
                raise ValueError("invalid package source fields")
            source, derived, decoded = _snapshot(record["source"])
            if _canonical(source) != _canonical(record["source"]):
                raise ValueError("package bytes are not canonically encoded")
            if derived["revision_id"] != revision_id:
                raise ValueError("package content hash differs")
            created_at = metadata["created_at"]
            if not isinstance(created_at, str) or datetime.fromisoformat(created_at).tzinfo is None:
                raise ValueError("invalid package timestamp")
            if _canonical(metadata) != _canonical({**derived, "created_at": created_at}):
                raise ValueError("package metadata differs from content")
            return source, metadata, decoded
        except FileNotFoundError as error:
            raise ProgramPackageError("unknown_program_package", "package revision does not exist", 404) from error
        except (ValueError, UnicodeError, TypeError, KeyError, RecursionError) as error:
            raise ProgramPackageError("program_package_corrupt", "package failed integrity validation", 500) from error
        except OSError as error:
            raise ProgramPackageError("program_package_storage_error", "package could not be read", 503) from error

    def _publish(self, path: Path, record: dict) -> None:
        temporary = self.root / f".{path.stem}.{uuid.uuid4().hex}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(_canonical(record) + b"\n")
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, path)
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def create(self, payload: dict) -> dict:
        source, metadata, _ = _snapshot(payload)
        revision_id = metadata["revision_id"]
        path = self._path(revision_id)
        with self._locked(exclusive=True):
            try:
                exists = path.exists() or path.is_symlink()
            except OSError as error:
                raise ProgramPackageError("program_package_storage_error", "package could not be inspected", 503) from error
            if exists:
                stored_source, stored_metadata, _ = self._read(revision_id)
                if stored_source != source:
                    raise ProgramPackageError("program_package_corrupt", "package content differs", 500)
                return stored_metadata
            try:
                # Path.glob suppresses scandir errors on supported Python
                # versions; a failed enumeration must not bypass the quota.
                with os.scandir(self.root) as records:
                    count = sum(
                        1 for candidate in records
                        if candidate.name.endswith(".json") and _REVISION_ID.fullmatch(candidate.name[:-5])
                    )
            except OSError as error:
                raise ProgramPackageError("program_package_storage_error", "package quota could not be checked", 503) from error
            if count >= self.max_count:
                raise ProgramPackageError("program_package_quota_exceeded", "package count limit reached", 429)
            metadata["created_at"] = datetime.now(timezone.utc).isoformat()
            record = {"schema_version": 1, "source": source, "metadata": metadata,
                      "metadata_sha256": _sha(_canonical(metadata))}
            try:
                self._publish(path, record)
            except FileExistsError:
                stored_source, stored_metadata, _ = self._read(revision_id)
                if stored_source != source:
                    raise ProgramPackageError("program_package_corrupt", "package content differs", 500)
                return stored_metadata
            except OSError as error:
                raise ProgramPackageError("program_package_storage_error", "package could not be stored", 503) from error
            return self._read(revision_id)[1]

    def get(self, revision_id: str) -> dict:
        self._path(revision_id)
        with self._locked(exclusive=False):
            return self._read(revision_id)[1]

    def read_files(self, revision_id: str) -> dict[str, bytes]:
        self._path(revision_id)
        with self._locked(exclusive=False):
            return self._read(revision_id)[2]

    def source(self, revision_id: str) -> dict:
        self._path(revision_id)
        with self._locked(exclusive=False):
            source = self._read(revision_id)[0]
            return {"files": source["files"], "entrypoint": source["entrypoint"]}
