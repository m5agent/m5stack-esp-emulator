"""Durable recovery of Reviewer session creates, serialized by the service lock."""
from __future__ import annotations

from contextlib import suppress
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any

from device_service_errors import ServiceError


PROTOCOL = "review-v1"
MAX_FUTURE_SECONDS = 600
MAX_ENTRIES = 4096
KEY = re.compile(r"review-v1:([1-9][0-9]{0,9}):([0-9a-f]{32})")
NONCE = re.compile(r"[0-9a-f]{32}")
DIGEST = re.compile(r"[0-9a-f]{64}")


def review_expiration(key: str | None) -> int | None:
    if not isinstance(key, str) or not key.startswith(PROTOCOL + ":"):
        return None
    match = KEY.fullmatch(key)
    if not match:
        raise ServiceError("invalid_idempotency_key", "invalid review-v1 session create key", 400)
    return int(match[1])


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def _is_expiration(value: Any) -> bool:
    return type(value) is int and 1 <= value <= 9_999_999_999


def parse_reconcile(payload: dict) -> tuple[str, str, int]:
    if not isinstance(payload, dict) or set(payload) != {"key_sha256", "request_sha256", "expires_at", "nonce"}:
        raise ServiceError("invalid_request", "expected key_sha256, request_sha256, expires_at and nonce", 400)
    key_hash, request_hash = payload["key_sha256"], payload["request_sha256"]
    expires_at, nonce = payload["expires_at"], payload["nonce"]
    if (not _is_digest(key_hash) or not _is_digest(request_hash) or not _is_expiration(expires_at)
            or not isinstance(nonce, str) or NONCE.fullmatch(nonce) is None):
        raise ServiceError("invalid_request", "invalid review-v1 request identity", 400)
    if sha256(f"{PROTOCOL}:{expires_at}:{nonce}".encode()).hexdigest() != key_hash:
        raise ServiceError("session_idempotency_conflict", "review key identity differs", 409)
    return key_hash, request_hash, expires_at


class SessionCreateRecovery:
    """Persist only correlation digests. All operations run under DeviceService._lock."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self._entries = self._load()
        except (OSError, ValueError):
            # Ordinary session idempotency uses a separate store. A corrupt
            # recovery journal must never be interpreted as empty or replaced.
            self._entries = None

    def _load(self) -> dict[str, dict]:
        if self.path.is_symlink():
            raise ValueError("recovery journal cannot be a symlink")
        try:
            data = json.loads(self.path.read_bytes())
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("invalid recovery journal")
        entries = data.get("entries")
        if not isinstance(entries, dict) or len(entries) > MAX_ENTRIES:
            raise ValueError("invalid recovery entries")
        for key_hash, entry in entries.items():
            if (not _is_digest(key_hash) or not isinstance(entry, dict)
                    or set(entry) != {"request_sha256", "expires_at", "session_id", "sealed"}
                    or not _is_digest(entry.get("request_sha256")) or not _is_expiration(entry.get("expires_at"))
                    or type(entry.get("sealed")) is not bool):
                raise ValueError("invalid recovery entry")
            sid = entry["session_id"]
            if ((sid is None and not entry["sealed"])
                    or (sid is not None and (not isinstance(sid, str) or NONCE.fullmatch(sid) is None))):
                raise ValueError("invalid recovery session binding")
        return entries

    def _matched(self, key_hash: str, request_hash: str, expires_at: int) -> dict | None:
        if self._entries is None:
            raise ServiceError("session_create_recovery_unavailable", "session create journal unavailable", 503)
        if expires_at > time.time() + MAX_FUTURE_SECONDS:
            raise ServiceError("invalid_request", "review-v1 expiry must be at most 600 seconds ahead", 400)
        entry = self._entries.get(key_hash)
        if entry is not None and (entry["request_sha256"], entry["expires_at"]) != (request_hash, expires_at):
            raise ServiceError("session_idempotency_conflict", "review key was used with a different request", 409)
        return entry

    @staticmethod
    def _require_unexpired(expires_at: int) -> None:
        if expires_at <= time.time():
            raise ServiceError("session_create_expired", "review-v1 session create key has expired", 410)

    def replay(self, key_hash: str, request_hash: str, expires_at: int) -> str | None:
        entry = self._matched(key_hash, request_hash, expires_at)
        self._require_unexpired(expires_at)
        if entry is None:
            return None
        if entry["sealed"]:
            raise ServiceError("session_create_reconciled", "review-v1 session create is sealed", 409)
        return entry["session_id"]

    def _save(self, key_hash: str, entry: dict, live_ids: set[str]) -> None:
        assert self._entries is not None
        entries = dict(self._entries)
        if key_hash not in entries and len(entries) >= MAX_ENTRIES:
            now = time.time()
            entries = {key: value for key, value in entries.items()
                       if value["expires_at"] > now or value["session_id"] in live_ids}
            if len(entries) >= MAX_ENTRIES:
                raise ServiceError("session_create_recovery_full", "session create journal has no free entries", 503)
        entries[key_hash] = entry
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", delete=False) as target:
                temporary = Path(target.name)
                json.dump({"schema_version": 1, "entries": entries}, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise ServiceError("session_create_recovery_unavailable", "unable to persist session create recovery", 503) from error
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)
        self._entries = entries

    def bind(self, key_hash: str, request_hash: str, expires_at: int, session_id: str,
             live_ids: set[str]) -> None:
        self._save(key_hash, {"request_sha256": request_hash, "expires_at": expires_at,
                             "session_id": session_id, "sealed": False}, live_ids)

    def reconcile(self, key_hash: str, request_hash: str, expires_at: int, live_ids: set[str]) -> str | None:
        entry = self._matched(key_hash, request_hash, expires_at)
        if entry is None:
            self._require_unexpired(expires_at)
            entry = {"request_sha256": request_hash, "expires_at": expires_at,
                     "session_id": None, "sealed": False}
        if not entry["sealed"]:
            self._save(key_hash, {**entry, "sealed": True}, live_ids)
        return entry["session_id"]
