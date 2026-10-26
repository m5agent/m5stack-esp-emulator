"""Storage retention policy for the leased Device Service."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    value = default if raw in {None, ""} else int(raw)
    return max(minimum, int(value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class StoragePolicy:
    """Bounded retention for session history and reusable firmware caches."""

    history_ttl_seconds: int = 7 * 24 * 60 * 60
    max_history_sessions: int = 100
    max_history_bytes: int = 2 * 1024**3
    max_cache_bytes: int = 4 * 1024**3
    cache_grace_seconds: int = 24 * 60 * 60
    min_free_bytes: int = 2 * 1024**3
    retain_session_flash: bool = False
    prune_interval_seconds: int = 30

    @classmethod
    def from_env(cls) -> "StoragePolicy":
        return cls(
            history_ttl_seconds=_env_int(
                "M5_SERVICE_HISTORY_TTL", cls.history_ttl_seconds
            ),
            max_history_sessions=_env_int(
                "M5_SERVICE_MAX_HISTORY_SESSIONS",
                cls.max_history_sessions,
            ),
            max_history_bytes=_env_int(
                "M5_SERVICE_MAX_HISTORY_BYTES",
                cls.max_history_bytes,
            ),
            max_cache_bytes=_env_int(
                "M5_SERVICE_MAX_CACHE_BYTES",
                cls.max_cache_bytes,
            ),
            cache_grace_seconds=_env_int(
                "M5_SERVICE_CACHE_GRACE",
                cls.cache_grace_seconds,
            ),
            min_free_bytes=_env_int(
                "M5_SERVICE_MIN_FREE_BYTES",
                cls.min_free_bytes,
            ),
            retain_session_flash=_env_bool(
                "M5_SERVICE_RETAIN_SESSION_FLASH",
                cls.retain_session_flash,
            ),
            prune_interval_seconds=_env_int(
                "M5_SERVICE_STORAGE_PRUNE_INTERVAL",
                cls.prune_interval_seconds,
                minimum=1,
            ),
        )

    def as_dict(self) -> dict:
        return {
            "history_ttl_seconds": self.history_ttl_seconds,
            "max_history_sessions": self.max_history_sessions,
            "max_history_bytes": self.max_history_bytes,
            "max_cache_bytes": self.max_cache_bytes,
            "cache_grace_seconds": self.cache_grace_seconds,
            "min_free_bytes": self.min_free_bytes,
            "retain_session_flash": self.retain_session_flash,
            "prune_interval_seconds": self.prune_interval_seconds,
        }


def directory_size_bytes(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total
