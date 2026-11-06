"""Bounded local display journal, independent of disposable guest directories.

This is an observation index, not execution authority or an evidence archive.
Only an explicit metadata projection enters the journal; guest contents do not.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
import time
import uuid


ACTIVE_STATES = frozenset({"provisioning", "flashing", "booting", "running", "stopping"})
SESSION_FIELDS = frozenset({
    "session_id", "device_id", "state", "created_at", "completed_at", "firmware_id",
    "firmware_sha256", "runtime", "units", "display", "serial_bytes", "last_frame_available",
    "last_frame_captured_at", "device_state_supported", "management_binding", "purged",
    "interrupted", "restored",
})


def display_projection(value: dict) -> dict:
    """Never retain arbitrary events, runtime env, paths, source or guest bytes."""
    result = {key: value[key] for key in SESSION_FIELDS if key in value}
    result["purged"] = bool(result.get("purged", False))
    result["serial_bytes"] = max(0, int(result.get("serial_bytes", 0)))
    result["units"] = [
        {key: unit[key] for key in ("id", "unit_id", "port_id", "visual_port", "parent_id") if key in unit}
        for unit in value.get("units", []) if isinstance(unit, dict)
    ]
    if result["purged"]:
        result["last_frame_available"] = False
    return result


class ObservationStore:
    def __init__(self, path: Path, *, retention_seconds: float = 86400,
                 max_recent: int = 5000, max_events: int = 50000, clock=time.time):
        self.path = Path(path)
        self.retention_seconds = retention_seconds
        self.max_recent = max_recent
        self.max_events = max_events
        self.clock = clock
        self._lock = threading.RLock()
        self._connection = None
        self._failed = False
        self._gap_marker = self.path.with_suffix(".gap")
        self._gap_possible = self._gap_marker.exists()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, timeout=0.1, check_same_thread=False)
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, active INTEGER NOT NULL,
                    updated REAL NOT NULL, seq INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                    session_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS observation_events_time ON events(at);
            """)
            with self._connection:
                for key, value in (("journal_id", uuid.uuid4().hex), ("cursor", "0"), ("floor", "0")):
                    self._connection.execute("INSERT OR IGNORE INTO metadata VALUES (?, ?)", (key, value))
                if self._gap_possible:
                    self._connection.execute("UPDATE metadata SET value=? WHERE key='journal_id'", (uuid.uuid4().hex,))
        except (OSError, sqlite3.Error):
            self._failure()

    def _failure(self):
        self._failed = True
        self._gap_possible = True
        try:
            self._gap_marker.write_text("Observation history may be incomplete.\n")
        except OSError:
            pass

    def status(self) -> dict:
        return {"state": "degraded" if self._failed or self._gap_possible else "ok", "gap_possible": self._gap_possible,
                "available": not self._failed}

    def _meta(self, key):
        return self._connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()[0]

    def _prune(self, now):
        db = self._connection
        db.execute("DELETE FROM sessions WHERE active=0 AND updated<?", (now - self.retention_seconds,))
        db.execute("DELETE FROM sessions WHERE active=0 AND session_id NOT IN "
                   "(SELECT session_id FROM sessions WHERE active=0 ORDER BY updated DESC, seq DESC LIMIT ?)",
                   (self.max_recent,))
        removed = db.execute("SELECT MAX(seq) FROM events WHERE at<? OR seq NOT IN "
                             "(SELECT seq FROM events ORDER BY seq DESC LIMIT ?)",
                             (now - self.retention_seconds, self.max_events)).fetchone()[0]
        if removed is not None:
            db.execute("DELETE FROM events WHERE seq<=?", (removed,))
            db.execute("UPDATE metadata SET value=? WHERE key='floor'", (str(removed),))

    def record(self, session: dict) -> bool:
        """Synchronously commit metadata; storage failures never escape into a guest."""
        with self._lock:
            if self._connection is None or self._failed:
                return False
            try:
                projection = display_projection(session)
                encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                session_id = projection["session_id"]
                now = self.clock()
                with self._connection:
                    previous = self._connection.execute("SELECT payload FROM sessions WHERE session_id=?", (session_id,)).fetchone()
                    if previous is not None and json.loads(previous[0]).get("purged"):
                        # Session IDs are never reused. The pre-deletion final
                        # projection is immutable: later polls of a disposed
                        # object must not erase byte counts or revive a frame.
                        return True
                    if previous is None or display_projection(json.loads(previous[0])) != projection:
                        projection["observed_at"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
                        encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        cursor = self._connection.execute("INSERT INTO events(at,session_id,payload) VALUES (?,?,?)", (now, session_id, encoded)).lastrowid
                        self._connection.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)", (
                            session_id, int(projection.get("state") in ACTIVE_STATES and not projection["purged"]), now, cursor, encoded))
                        self._connection.execute("UPDATE metadata SET value=? WHERE key='cursor'", (str(cursor),))
                    self._prune(now)
                return True
            except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
                self._failure()
                return False

    def snapshot(self) -> dict:
        with self._lock:
            try:
                if self._connection is None or self._failed:
                    raise sqlite3.DatabaseError("observation index unavailable")
                with self._connection:
                    self._prune(self.clock())
                    journal_id = self._meta("journal_id")
                    cursor = int(self._meta("cursor"))
                    rows = self._connection.execute("SELECT active,payload FROM sessions ORDER BY seq DESC").fetchall()
                return {"journal_id": journal_id, "cursor": cursor, "status": self.status(),
                        "active": [json.loads(payload) for active, payload in rows if active],
                        "recent": [json.loads(payload) for active, payload in rows if not active]}
            except (sqlite3.Error, ValueError, TypeError):
                self._failure()
                return {"journal_id": None, "cursor": 0, "status": self.status(), "active": [], "recent": []}

    def events(self, *, journal_id: str, after: int, limit: int = 200) -> dict:
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("after must be nonnegative and limit must be between 1 and 500")
        with self._lock:
            result = {"journal_id": None, "events": [], "next_cursor": after,
                      "has_more": False, "resync": True, "status": self.status()}
            try:
                if self._connection is None or self._failed:
                    raise sqlite3.DatabaseError("observation index unavailable")
                with self._connection:
                    self._prune(self.clock())
                    epoch = self._meta("journal_id")
                    cursor, floor = int(self._meta("cursor")), int(self._meta("floor"))
                    result["journal_id"] = epoch
                    if journal_id != epoch or after < floor or after > cursor:
                        return result
                    rows = self._connection.execute("SELECT seq,payload FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, limit + 1)).fetchall()
                page = rows[:limit]
                return {**result, "events": [{"seq": seq, "kind": "session", "session": json.loads(payload)} for seq, payload in page],
                        "next_cursor": page[-1][0] if page else after, "has_more": len(rows) > limit,
                        "resync": False, "status": self.status()}
            except (sqlite3.Error, ValueError, TypeError):
                self._failure()
                return {**result, "status": self.status()}

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __del__(self):
        # Crash-handoff tests and discarded service instances can deliberately
        # release worker ownership without calling normal service shutdown.
        try:
            self.close()
        except Exception:
            pass
