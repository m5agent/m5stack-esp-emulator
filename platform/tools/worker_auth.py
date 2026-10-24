#!/usr/bin/env python3
"""Worker-specific HMAC authentication and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

WORKER_AUTH_VERSION = "m5-worker-v1"
WORKER_TIMESTAMP_TOLERANCE = 90
WORKER_NONCE_TTL = WORKER_TIMESTAMP_TOLERANCE * 2
MAX_REPLAY_ENTRIES = 4096
MAX_MASTER_TOKEN_BYTES = 4096
WORKER_SIGNATURE_HEADERS = {
    "worker_id": "X-M5-Worker-Id",
    "instance_id": "X-M5-Worker-Instance",
    "generation": "X-M5-Worker-Generation",
    "timestamp": "X-M5-Worker-Timestamp",
    "nonce": "X-M5-Worker-Nonce",
    "signature": "X-M5-Worker-Signature",
}
WORKER_AUTH_PATH = re.compile(
    r"^/api/v1/(?:"
    r"jobs/claim|"
    r"jobs/[^/]+/(?:heartbeat|result)|"
    r"workers/[^/]+/(?:heartbeat|drain|stop|results)"
    r")$"
)


class WorkerAuthError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 401):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def read_master_token_file(path: str | Path) -> str:
    """Read a master token without persisting or logging its value."""

    token_path = Path(path)
    if not token_path.is_file():
        raise WorkerAuthError(
            "worker_token_file_missing",
            f"API token file does not exist: {token_path}",
        )
    data = token_path.read_bytes()
    if not data or len(data) > MAX_MASTER_TOKEN_BYTES:
        raise WorkerAuthError(
            "worker_token_file_invalid",
            f"API token file must contain 1-{MAX_MASTER_TOKEN_BYTES} bytes",
        )
    try:
        token = data.decode("utf-8").rstrip("\r\n")
    except UnicodeDecodeError as error:
        raise WorkerAuthError(
            "worker_token_file_invalid",
            "API token file must be UTF-8 text",
        ) from error
    if not token or "\x00" in token:
        raise WorkerAuthError(
            "worker_token_file_invalid",
            "API token file contains an empty or invalid token",
        )
    return token


def is_worker_auth_path(method: str, path: str) -> bool:
    return method == "POST" and bool(WORKER_AUTH_PATH.fullmatch(path))


def worker_identity_matches(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> bool:
    return all(
        expected.get(key) == actual.get(key)
        for key in ("worker_id", "instance_id", "generation")
    )


def _worker_key(
    master_token: str,
    identity: dict[str, Any],
) -> bytes:
    worker_id = str(identity.get("worker_id") or "")
    instance_id = str(identity.get("instance_id") or "")
    generation = identity.get("generation")
    if (
        not master_token
        or not worker_id
        or not instance_id
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 1
    ):
        raise WorkerAuthError(
            "invalid_worker_identity",
            "worker identity is incomplete",
        )
    message = (f"{WORKER_AUTH_VERSION}:{worker_id}:{instance_id}:{generation}").encode()
    return hmac.new(
        master_token.encode(),
        message,
        hashlib.sha256,
    ).digest()


def _canonical_request(
    method: str,
    path: str,
    body: bytes,
    timestamp: str,
    nonce: str,
) -> bytes:
    body_sha256 = hashlib.sha256(body).hexdigest()
    return "\n".join(
        (
            WORKER_AUTH_VERSION,
            method.upper(),
            path,
            timestamp,
            nonce,
            body_sha256,
        )
    ).encode()


def sign_worker_request(
    master_token: str,
    identity: dict[str, Any],
    method: str,
    path: str,
    body: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    timestamp_value = str(int(time.time()) if timestamp is None else timestamp)
    nonce_value = nonce or secrets.token_hex(16)
    canonical = _canonical_request(
        method,
        path,
        body,
        timestamp_value,
        nonce_value,
    )
    signature = hmac.new(
        _worker_key(master_token, identity),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    return {
        WORKER_SIGNATURE_HEADERS["worker_id"]: str(identity["worker_id"]),
        WORKER_SIGNATURE_HEADERS["instance_id"]: str(identity["instance_id"]),
        WORKER_SIGNATURE_HEADERS["generation"]: str(identity["generation"]),
        WORKER_SIGNATURE_HEADERS["timestamp"]: timestamp_value,
        WORKER_SIGNATURE_HEADERS["nonce"]: nonce_value,
        WORKER_SIGNATURE_HEADERS["signature"]: signature,
    }


class WorkerAuthVerifier:
    def __init__(
        self,
        master_token: str | None,
        *,
        previous_master_token: str | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.master_token = master_token or ""
        self.previous_master_token = previous_master_token or ""
        self.master_tokens = tuple(
            dict.fromkeys(
                token
                for token in (self.master_token, self.previous_master_token)
                if token
            )
        )
        self.clock = clock
        self._lock = threading.RLock()
        self._nonces: dict[tuple[str, str, str], float] = {}

    def _prune_locked(self, now: float) -> None:
        expired = [key for key, expires in self._nonces.items() if expires <= now]
        for key in expired:
            self._nonces.pop(key, None)
        if len(self._nonces) <= MAX_REPLAY_ENTRIES:
            return
        oldest = sorted(
            self._nonces.items(),
            key=lambda item: item[1],
        )
        for key, _expires in oldest[: len(self._nonces) - MAX_REPLAY_ENTRIES]:
            self._nonces.pop(key, None)

    def verify(
        self,
        headers: Any,
        method: str,
        path: str,
        body: bytes,
    ) -> dict[str, Any]:
        if not self.master_tokens:
            raise WorkerAuthError(
                "worker_auth_not_configured",
                "worker authentication requires an API token",
                503,
            )
        if not is_worker_auth_path(method, path):
            raise WorkerAuthError(
                "worker_auth_not_required",
                "path does not require worker authentication",
            )
        worker_id = str(headers.get(WORKER_SIGNATURE_HEADERS["worker_id"], ""))
        instance_id = str(headers.get(WORKER_SIGNATURE_HEADERS["instance_id"], ""))
        generation_raw = str(headers.get(WORKER_SIGNATURE_HEADERS["generation"], ""))
        timestamp_raw = str(headers.get(WORKER_SIGNATURE_HEADERS["timestamp"], ""))
        nonce = str(headers.get(WORKER_SIGNATURE_HEADERS["nonce"], ""))
        signature = str(headers.get(WORKER_SIGNATURE_HEADERS["signature"], ""))
        try:
            generation = int(generation_raw)
            timestamp = int(timestamp_raw)
        except ValueError as error:
            raise WorkerAuthError(
                "worker_auth_invalid",
                "worker auth generation/timestamp is invalid",
            ) from error
        if (
            not worker_id
            or len(worker_id) > 128
            or not instance_id
            or len(instance_id) > 128
            or generation < 1
            or not re.fullmatch(r"[0-9a-f]{24,128}", nonce)
            or not re.fullmatch(r"[0-9a-f]{64}", signature)
        ):
            raise WorkerAuthError(
                "worker_auth_invalid",
                "worker auth headers are incomplete or malformed",
            )
        now = self.clock()
        if abs(now - timestamp) > WORKER_TIMESTAMP_TOLERANCE:
            raise WorkerAuthError(
                "worker_auth_expired",
                "worker auth timestamp is outside the allowed window",
            )
        identity = {
            "worker_id": worker_id,
            "instance_id": instance_id,
            "generation": generation,
        }
        canonical = _canonical_request(
            method,
            path,
            body,
            timestamp_raw,
            nonce,
        )
        expected_signatures = [
            hmac.new(
                _worker_key(token, identity),
                canonical,
                hashlib.sha256,
            ).hexdigest()
            for token in self.master_tokens
        ]
        if not any(
            hmac.compare_digest(expected, signature)
            for expected in expected_signatures
        ):
            raise WorkerAuthError(
                "worker_auth_invalid",
                "worker request signature is invalid",
            )
        replay_key = (worker_id, instance_id, nonce)
        with self._lock:
            self._prune_locked(now)
            if replay_key in self._nonces:
                raise WorkerAuthError(
                    "worker_auth_replay",
                    "worker request nonce was already used",
                    409,
                )
            self._nonces[replay_key] = now + WORKER_NONCE_TTL
        return identity
