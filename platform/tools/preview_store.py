"""Durable local Preview/Run intent ledger; no guest or revision-file I/O.

This store deliberately retains every preview, run, receipt and revision pin.
It is not a tenant authorization service or a revision garbage collector.
Callbacks passed to mutate must do bounded, pure in-memory work only.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable
import uuid


MAX_PREVIEWS = 128
MAX_RUNS_PER_PREVIEW = 256
LOCAL_OWNER = "local-control"
SOURCE_KIND = "uiflow2-package"
_UUID = re.compile(r"[0-9a-f]{32}\Z")
_REVISION = re.compile(r"[0-9a-f]{64}\Z")
_KEY = re.compile(r"[\x21-\x7e]{1,128}\Z")
_SCOPE = re.compile(r"(?:create-preview|preview:[0-9a-f]{32}:runs)\Z")
_RUN_FIELDS = {
    "revision_id", "expected_generation", "expected_owner_epoch",
    "client_generation", "timeout_seconds",
}
_TERMINAL = frozenset({"completed", "failed", "cancelled", "superseded", "interrupted"})
_RUN_STATES = _TERMINAL | {"queued", "preparing", "starting", "running", "unknown", "cancelling"}
_PREVIEW_STATES = frozenset({"preparing", "ready", "closing", "closed", "failed", "unknown"})
_PREVIEW_IMMUTABLE = frozenset({
    "preview_id", "owner", "owner_epoch", "created_at", "request",
    "session_request", "limits", "allocation_key",
})
_RUN_IMMUTABLE = frozenset({
    "preview_id", "run_id", "execution_id", "revision_id", "source_kind",
    "generation", "request", "created_at", "client_generation", "timeout_seconds",
    "execution_mode", "cleanup_mode",
})
_ALLOCATION_TRANSITIONS = {
    "pending": {"pending", "creating", "failed", "unknown"},
    "creating": {"creating", "bound", "failed", "unknown"},
    "bound": {"bound"},
    "unknown": {"unknown"},
    "failed": {"failed"},
}


class PreviewStoreError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _request(value: Any) -> dict:
    if not isinstance(value, dict) or "owner" in value:
        raise PreviewStoreError("invalid_preview_request", "request must be an object without owner")
    try:
        # A JSON round trip rejects non-JSON objects and detaches nested inputs.
        return json.loads(_canonical(value).encode("utf-8"))
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise PreviewStoreError("invalid_preview_request", "request must contain finite JSON values") from error


def _fingerprint(request: dict) -> str:
    return hashlib.sha256(_canonical(request).encode("utf-8")).hexdigest()


def _key_hash(key: Any) -> str:
    if not isinstance(key, str) or _KEY.fullmatch(key) is None:
        raise PreviewStoreError("invalid_idempotency_key", "Idempotency-Key must be 1..128 printable ASCII characters without whitespace")
    return hashlib.sha256(key.encode("ascii")).hexdigest()


def _owner(owner: Any) -> None:
    if owner != LOCAL_OWNER:
        raise PreviewStoreError("preview_not_found", "preview does not exist", 404)


def _identity(value: Any, *, run: bool = False) -> None:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        code = "preview_run_not_found" if run else "preview_not_found"
        raise PreviewStoreError(code, "run does not exist" if run else "preview does not exist", 404)


def _transition_error(message: str) -> None:
    raise PreviewStoreError("preview_transition_conflict", message, 409)


class PreviewStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise OSError("database must not be a symlink")
            with self._transaction(write=True, initialize=True) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise sqlite3.DatabaseError("unsupported preview schema")
                for statement in (
                    "CREATE TABLE IF NOT EXISTS previews (preview_id TEXT PRIMARY KEY, owner TEXT NOT NULL, record TEXT NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, preview_id TEXT NOT NULL REFERENCES previews(preview_id), record TEXT NOT NULL, UNIQUE(preview_id, run_id))",
                    "CREATE TABLE IF NOT EXISTS idempotency (owner TEXT NOT NULL, scope TEXT NOT NULL, key_hash TEXT NOT NULL, request_hash TEXT NOT NULL, receipt TEXT NOT NULL, preview_id TEXT NOT NULL REFERENCES previews(preview_id), run_id TEXT REFERENCES runs(run_id), PRIMARY KEY(owner, scope, key_hash))",
                    "CREATE TABLE IF NOT EXISTS revision_pins (run_id TEXT PRIMARY KEY REFERENCES runs(run_id), preview_id TEXT NOT NULL REFERENCES previews(preview_id), owner TEXT NOT NULL, source_kind TEXT NOT NULL, revision_id TEXT NOT NULL)",
                    "CREATE INDEX IF NOT EXISTS runs_by_preview ON runs(preview_id)",
                    "PRAGMA user_version=1",
                ):
                    connection.execute(statement)
            self.path.chmod(0o600)
        except (sqlite3.Error, OSError) as error:
            raise self._storage_error() from error

    @staticmethod
    def limits() -> dict:
        return {
            "max_previews": MAX_PREVIEWS,
            "max_runs_per_preview": MAX_RUNS_PER_PREVIEW,
            "retention_mode": "retention-only",
            "gc_enabled": False,
        }

    @staticmethod
    def _storage_error() -> PreviewStoreError:
        return PreviewStoreError("preview_storage_unavailable", "preview storage is unavailable", 503)

    @contextmanager
    def _transaction(self, *, write: bool = False, initialize: bool = False):
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=2.0, isolation_level=None)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            if initialize:
                mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if mode.lower() != "wal":
                    raise sqlite3.DatabaseError("WAL unavailable")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException as error:
            if connection is not None:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            if isinstance(error, (sqlite3.Error, OSError)):
                raise self._storage_error() from error
            raise
        finally:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error as error:
                    raise self._storage_error() from error

    def _decode(self, text: str) -> dict:
        try:
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("record is not an object")
            return value
        except (ValueError, TypeError, UnicodeError, RecursionError) as error:
            raise self._storage_error() from error

    def _preview(self, connection, preview_id: str, owner: str | None = None) -> dict:
        row = connection.execute("SELECT owner, record FROM previews WHERE preview_id=?", (preview_id,)).fetchone()
        if row is None or (owner is not None and row[0] != owner):
            raise PreviewStoreError("preview_not_found", "preview does not exist", 404)
        record = self._decode(row[1])
        if record.get("preview_id") != preview_id or record.get("owner") != row[0]:
            raise self._storage_error()
        return record

    def _runs(self, connection, preview_id: str) -> dict[str, dict]:
        records = {}
        for run_id, record in connection.execute("SELECT run_id, record FROM runs WHERE preview_id=?", (preview_id,)):
            run = self._decode(record)
            if run.get("run_id") != run_id or run.get("preview_id") != preview_id:
                raise self._storage_error()
            records[run_id] = run
        return records

    def _replay(self, connection, owner: str, scope: str, key_hash: str, fingerprint: str) -> dict | None:
        row = connection.execute(
            "SELECT request_hash, receipt FROM idempotency WHERE owner=? AND scope=? AND key_hash=?",
            (owner, scope, key_hash),
        ).fetchone()
        if row is None:
            return None
        if row[0] != fingerprint:
            raise PreviewStoreError("idempotency_conflict", "Idempotency-Key was already used with another request", 409)
        return self._decode(row[1])

    def lookup_replay(self, owner: str, scope: str, key: str, request: dict) -> dict | None:
        _owner(owner)
        if not isinstance(scope, str) or _SCOPE.fullmatch(scope) is None:
            raise PreviewStoreError("invalid_preview_request", "invalid idempotency scope")
        key_hash, fingerprint = _key_hash(key), _fingerprint(_request(request))
        with self._transaction() as connection:
            return copy.deepcopy(self._replay(connection, owner, scope, key_hash, fingerprint))

    def _receipt(self, connection, owner, scope, key_hash, fingerprint, receipt):
        connection.execute(
            "INSERT INTO idempotency(owner, scope, key_hash, request_hash, receipt, preview_id, run_id) VALUES(?,?,?,?,?,?,?)",
            (owner, scope, key_hash, fingerprint, _canonical(receipt), receipt["preview_id"], receipt.get("run_id")),
        )

    def create(self, owner: str, key: str, request: dict, session_request: dict, expires_at: str) -> tuple[dict, bool]:
        _owner(owner)
        request = _request(request)
        key_hash, fingerprint = _key_hash(key), _fingerprint(request)
        with self._transaction(write=True) as connection:
            replay = self._replay(connection, owner, "create-preview", key_hash, fingerprint)
            if replay is not None:
                return copy.deepcopy(replay), True
            session_request = _request(session_request)
            try:
                if not isinstance(expires_at, str) or datetime.fromisoformat(expires_at).tzinfo is None:
                    raise ValueError("timezone required")
            except (ValueError, TypeError) as error:
                raise PreviewStoreError("invalid_preview_request", "expires_at must be an ISO8601 timestamp with a timezone") from error
            count = connection.execute("SELECT COUNT(*) FROM previews").fetchone()[0]
            if count >= MAX_PREVIEWS:
                raise PreviewStoreError("preview_quota_exceeded", "retained preview limit is 128", 429)
            preview_id, timestamp = uuid.uuid4().hex, _now()
            preview = {
                "preview_id": preview_id, "owner": owner, "owner_epoch": uuid.uuid4().hex,
                "generation": 0, "state": "preparing", "request": request,
                "session_request": session_request, "session_id": None,
                "allocation_state": "pending", "allocation_key": f"preview:{preview_id}:allocation:1",
                "expires_at": expires_at, "desired_run_id": None, "transition_run_id": None,
                "active_run_id": None, "created_at": timestamp, "updated_at": timestamp,
                "error": None, "limits": self.limits(), "capabilities": {},
                "runtime_capabilities": {"schema_version": 1, "status": "unknown", "mpy_entrypoint": False},
            }
            connection.execute("INSERT INTO previews(preview_id, owner, record) VALUES(?,?,?)", (preview_id, owner, _canonical(preview)))
            self._receipt(connection, owner, "create-preview", key_hash, fingerprint, preview)
            return copy.deepcopy(preview), False

    def get_preview(self, owner: str, preview_id: str) -> dict:
        _owner(owner)
        _identity(preview_id)
        with self._transaction() as connection:
            return copy.deepcopy(self._preview(connection, preview_id, owner))

    def get_run(self, owner: str, preview_id: str, run_id: str) -> dict:
        _owner(owner)
        _identity(preview_id)
        _identity(run_id, run=True)
        with self._transaction() as connection:
            self._preview(connection, preview_id, owner)
            row = connection.execute("SELECT record FROM runs WHERE preview_id=? AND run_id=?", (preview_id, run_id)).fetchone()
            if row is None:
                raise PreviewStoreError("preview_run_not_found", "run does not exist", 404)
            run = self._decode(row[0])
            if run.get("run_id") != run_id or run.get("preview_id") != preview_id:
                raise self._storage_error()
            return copy.deepcopy(run)

    def list_previews(self, owner: str | None = None) -> list[dict]:
        if owner is not None:
            _owner(owner)
        with self._transaction() as connection:
            query, arguments = "SELECT preview_id FROM previews", ()
            if owner is not None:
                query += " WHERE owner=?"
                arguments = (owner,)
            values = [self._preview(connection, row[0], owner) for row in connection.execute(query, arguments)]
            return copy.deepcopy(sorted(values, key=lambda value: (value["created_at"], value["preview_id"])))

    @staticmethod
    def _epoch(preview: dict, epoch: str) -> None:
        if epoch != preview["owner_epoch"]:
            raise PreviewStoreError("preview_owner_conflict", "preview owner epoch differs", 409)

    @staticmethod
    def _run_payload(payload: dict) -> None:
        if set(payload) - _RUN_FIELDS or not {"revision_id", "expected_generation", "expected_owner_epoch"} <= payload.keys():
            raise PreviewStoreError("invalid_preview_request", "run requires revision_id, expected_generation and expected_owner_epoch")
        if not isinstance(payload["revision_id"], str) or _REVISION.fullmatch(payload["revision_id"]) is None:
            raise PreviewStoreError("invalid_preview_request", "revision_id must be a lowercase SHA256")
        if type(payload["expected_generation"]) is not int or payload["expected_generation"] < 0:
            raise PreviewStoreError("invalid_preview_request", "expected_generation must be a nonnegative integer")
        if not isinstance(payload["expected_owner_epoch"], str) or _UUID.fullmatch(payload["expected_owner_epoch"]) is None:
            raise PreviewStoreError("invalid_preview_request", "expected_owner_epoch must be the issued owner epoch")
        timeout = payload.get("timeout_seconds", 120)
        if type(timeout) not in (int, float) or not 1 <= timeout <= 120 or not math.isfinite(timeout):
            raise PreviewStoreError("invalid_preview_request", "timeout_seconds must be finite and between 1 and 120")
        if "client_generation" in payload:
            value = payload["client_generation"]
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
                raise PreviewStoreError("invalid_preview_request", "client_generation must be a nonempty string of at most 256 UTF-8 bytes")

    def admit_run(self, owner: str, preview_id: str, key: str, payload: dict) -> tuple[dict, bool]:
        _owner(owner)
        _identity(preview_id)
        payload = _request(payload)
        key_hash, fingerprint = _key_hash(key), _fingerprint(payload)
        scope = f"preview:{preview_id}:runs"
        with self._transaction(write=True) as connection:
            preview = self._preview(connection, preview_id, owner)
            replay = self._replay(connection, owner, scope, key_hash, fingerprint)
            if replay is not None:
                return copy.deepcopy(replay), True
            self._run_payload(payload)
            self._epoch(preview, payload["expected_owner_epoch"])
            if payload["expected_generation"] != preview["generation"]:
                raise PreviewStoreError("preview_generation_conflict", "preview generation differs", 409)
            if preview["state"] not in {"preparing", "ready"}:
                raise PreviewStoreError("preview_closing", "preview is not accepting new runs", 409)
            runs = self._runs(connection, preview_id)
            if len(runs) >= MAX_RUNS_PER_PREVIEW:
                raise PreviewStoreError("preview_quota_exceeded", "retained run limit is 256 per preview", 429)
            previous = copy.deepcopy({"preview": preview, "runs": runs})
            timestamp = _now()
            for old in runs.values():
                if old["state"] in _TERMINAL:
                    continue
                old["cancel_intent"] = True
                untouched = old["state"] == "queued" and old["run_id"] not in {
                    preview["active_run_id"], preview["transition_run_id"],
                }
                old["state"] = "superseded" if untouched else "cancelling"
                if untouched:
                    old["interrupt_ack"] = "not-required"
                old["updated_at"] = timestamp
            preview["generation"] += 1
            run_id = uuid.uuid4().hex
            run = {
                "preview_id": preview_id, "run_id": run_id, "execution_id": uuid.uuid4().hex,
                "revision_id": payload["revision_id"], "source_kind": SOURCE_KIND,
                "generation": preview["generation"], "state": "queued", "request": payload,
                "client_generation": payload.get("client_generation"),
                "timeout_seconds": payload.get("timeout_seconds", 120),
                "cancel_intent": False, "interrupt_ack": "unknown", "application_ready": "unknown",
                "execution_mode": "same-guest-uart-repl", "cleanup_mode": "interrupt-only",
                "error": None, "created_at": timestamp, "updated_at": timestamp,
            }
            preview["desired_run_id"], preview["updated_at"] = run_id, timestamp
            for old_id, old in runs.items():
                if old != previous["runs"][old_id]:
                    connection.execute("UPDATE runs SET record=? WHERE run_id=?", (_canonical(old), old_id))
            connection.execute("INSERT INTO runs(run_id, preview_id, record) VALUES(?,?,?)", (run_id, preview_id, _canonical(run)))
            connection.execute("UPDATE previews SET record=? WHERE preview_id=?", (_canonical(preview), preview_id))
            connection.execute("INSERT INTO revision_pins(run_id, preview_id, owner, source_kind, revision_id) VALUES(?,?,?,?,?)", (run_id, preview_id, owner, SOURCE_KIND, run["revision_id"]))
            self._receipt(connection, owner, scope, key_hash, fingerprint, run)
            return copy.deepcopy(run), False

    def cancel_run(self, owner: str, preview_id: str, run_id: str, epoch: str) -> dict:
        _owner(owner)
        _identity(preview_id)
        _identity(run_id, run=True)

        def cancel(state):
            preview, runs = state["preview"], state["runs"]
            if preview["owner"] != owner:
                raise PreviewStoreError("preview_not_found", "preview does not exist", 404)
            self._epoch(preview, epoch)
            if run_id not in runs:
                raise PreviewStoreError("preview_run_not_found", "run does not exist", 404)
            run = runs[run_id]
            if run["state"] in _TERMINAL or run["state"] == "cancelling":
                return run
            untouched = run["state"] == "queued" and run_id not in {preview["active_run_id"], preview["transition_run_id"]}
            run["cancel_intent"] = True
            run["state"] = "cancelled" if untouched else "cancelling"
            if untouched:
                run["interrupt_ack"] = "not-required"
                if preview["desired_run_id"] == run_id:
                    preview["desired_run_id"] = None
            return run

        return self.mutate(preview_id, cancel)

    @staticmethod
    def _validate_state(before: dict, after: dict) -> None:
        if set(after) != {"preview", "runs"} or not isinstance(after["preview"], dict) or not isinstance(after["runs"], dict):
            _transition_error("mutation must preserve the preview/runs snapshot")
        old_preview, preview = before["preview"], after["preview"]
        old_runs, runs = before["runs"], after["runs"]
        if set(runs) != set(old_runs):
            _transition_error("mutation cannot create or delete runs")
        for field in _PREVIEW_IMMUTABLE | {"generation"}:
            if field not in preview or preview[field] != old_preview[field]:
                _transition_error(f"mutation cannot change preview {field}")
        if not isinstance(preview.get("state"), str) or preview["state"] not in _PREVIEW_STATES:
            _transition_error("invalid preview state")
        if old_preview["state"] == "closed" and preview["state"] != "closed":
            _transition_error("closed preview cannot be reopened")
        old_allocation = old_preview["allocation_state"]
        if not isinstance(preview.get("allocation_state"), str) or preview["allocation_state"] not in _ALLOCATION_TRANSITIONS[old_allocation]:
            _transition_error("invalid allocation state transition")
        if old_preview["session_id"] is not None and preview.get("session_id") != old_preview["session_id"]:
            _transition_error("bound preview cannot change session")
        if preview.get("allocation_state") == "bound" and (not isinstance(preview.get("session_id"), str) or not preview["session_id"]):
            _transition_error("bound allocation requires a session receipt")
        for run_id, run in runs.items():
            old = old_runs[run_id]
            if not isinstance(run, dict):
                _transition_error("run must remain an object")
            for field in _RUN_IMMUTABLE:
                if field not in run or run[field] != old[field]:
                    _transition_error(f"mutation cannot change run {field}")
            state = run.get("state")
            if not isinstance(state, str) or state not in _RUN_STATES or type(run.get("cancel_intent")) is not bool:
                _transition_error("invalid run state or cancel intent")
            if old["cancel_intent"] and not run["cancel_intent"]:
                _transition_error("cancel intent cannot be cleared")
            if old["state"] in _TERMINAL and state != old["state"]:
                _transition_error("terminal run cannot be revived")
            if old["state"] == "cancelling" and state not in {"cancelling", "cancelled", "interrupted"}:
                _transition_error("cancelling run cannot be revived")
            if run["cancel_intent"] and state in {"queued", "preparing", "starting", "running"}:
                _transition_error("cancelled intent cannot acquire execution")
            if state in {"cancelled", "superseded"} and not run["cancel_intent"]:
                _transition_error("cancelled or superseded run requires cancel intent")
            if state == "cancelled" and run.get("interrupt_ack") not in ("confirmed", "not-required"):
                _transition_error("cancelled run requires interrupt acknowledgement")
            if state == "cancelled" and run.get("interrupt_ack") == "not-required" and old["state"] != "cancelled":
                if old["state"] != "queued" or run_id in {old_preview["active_run_id"], old_preview["transition_run_id"]}:
                    _transition_error("started run requires a real interrupt acknowledgement")
        for field in ("desired_run_id", "transition_run_id", "active_run_id"):
            if field not in preview or (preview[field] is not None and (not isinstance(preview[field], str) or preview[field] not in runs)):
                _transition_error(f"invalid {field}")
        transition = preview["transition_run_id"]
        if transition is not None and runs[transition]["state"] in _TERMINAL:
            _transition_error("transition must reference an unfinished run")
        active = preview["active_run_id"]
        if active is not None:
            run = runs[active]
            remains_cancelling = active == old_preview["active_run_id"] and run["state"] == "cancelling"
            if not remains_cancelling and (run["state"] not in {"running", "completed"} or run["cancel_intent"]):
                _transition_error("active must reference a confirmed uncancelled execution")
        if preview["state"] == "closed" and (active is not None or transition is not None):
            _transition_error("closed preview must release active and transition")
        try:
            _canonical(after).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError) as error:
            raise PreviewStoreError("preview_transition_conflict", "mutation must contain finite JSON values", 409) from error

    def mutate(self, preview_id: str, callback: Callable[[dict], Any]) -> Any:
        _identity(preview_id)
        with self._transaction(write=True) as connection:
            state = {"preview": self._preview(connection, preview_id), "runs": self._runs(connection, preview_id)}
            before = copy.deepcopy(state)
            result = callback(state)
            self._validate_state(before, state)
            timestamp = _now()
            changed = False
            for run_id, run in state["runs"].items():
                if run != before["runs"][run_id]:
                    run["updated_at"] = timestamp
                    connection.execute("UPDATE runs SET record=? WHERE run_id=?", (_canonical(run), run_id))
                    changed = True
            if state["preview"] != before["preview"] or changed:
                state["preview"]["updated_at"] = timestamp
                connection.execute("UPDATE previews SET record=? WHERE preview_id=?", (_canonical(state["preview"]), preview_id))
            return copy.deepcopy(result)

    def revision_pins(self) -> list[dict]:
        with self._transaction() as connection:
            columns = ("run_id", "preview_id", "owner", "source_kind", "revision_id")
            rows = connection.execute("SELECT run_id, preview_id, owner, source_kind, revision_id FROM revision_pins ORDER BY run_id")
            return [dict(zip(columns, row)) for row in rows]
