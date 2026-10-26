"""Retention roots and short deletion fences for managed Preview history.

Reading the ledger never initializes the coordinator or creates a database.
Allocation tokens fence deletion while composition is outside all service/DB
locks.  After allocation, retained records protect only their concrete roots.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Callable


@dataclass
class RetentionRoots:
    session_ids: set[str] = field(default_factory=set)
    firmware_ids: set[str] = field(default_factory=set)
    firmware_shas: set[str] = field(default_factory=set)
    artifact_ids: set[str] = field(default_factory=set)
    cache_barrier: bool = False
    history_barrier: bool = False
    reasons: set[str] = field(default_factory=set)
    # Expected control/firmware identity from immutable retained ledger records.
    # A readable JSON object with a missing root is not a successful scan.
    session_expectations: dict[str, dict] = field(default_factory=dict)

    def unavailable(self, reason: str) -> None:
        self.cache_barrier = self.history_barrier = True
        self.reasons.add(reason)

    def merge(self, other: "RetentionRoots") -> None:
        for name in ("session_ids", "firmware_ids", "firmware_shas", "artifact_ids", "reasons"):
            getattr(self, name).update(getattr(other, name))
        self.cache_barrier |= other.cache_barrier
        self.history_barrier |= other.history_barrier
        for session_id, expectation in other.session_expectations.items():
            existing = self.session_expectations.get(session_id)
            if existing is not None and existing != expectation:
                self.unavailable("session_identity_inconsistent")
            else:
                self.session_expectations[session_id] = dict(expectation)


@dataclass(frozen=True)
class RetentionDecision:
    protected: bool
    reason: str = ""


def _add(target: set[str], value) -> None:
    if isinstance(value, str) and value:
        target.add(value)


def _sha(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _uuid(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _binding(value) -> bool:
    return (isinstance(value, dict) and set(value) == {"preview_id", "owner_epoch", "expected_reference_sha256"}
            and _uuid(value["preview_id"]) and _uuid(value["owner_epoch"]) and _sha(value["expected_reference_sha256"]))


def add_session_roots(roots: RetentionRoots, record: dict, *, retained: bool = False) -> None:
    """Accept the persistent session schema or a corresponding host snapshot."""
    if not isinstance(record, dict):
        roots.unavailable("session_roots_unreadable")
        return
    binding = record.get("management_binding")
    strict = retained or binding is not None
    if strict and (not _uuid(record.get("session_id")) or not _sha(record.get("firmware_id"))
                   or not _sha(record.get("firmware_sha256")) or "source_artifacts" not in record
                   or record.get("firmware_id") != record.get("firmware_sha256")):
        roots.unavailable("session_roots_unreadable")
    if binding is not None:
        if not _binding(binding):
            roots.unavailable("session_binding_unreadable")
        else:
            roots.firmware_shas.add(binding["expected_reference_sha256"])
    _add(roots.session_ids, record.get("session_id"))
    _add(roots.firmware_ids, record.get("firmware_id"))
    _add(roots.firmware_shas, record.get("firmware_sha256"))
    artifacts = record.get("source_artifacts", [])
    if not isinstance(artifacts, list):
        roots.unavailable("session_roots_unreadable")
        return
    for artifact in artifacts:
        if not _sha(artifact):
            roots.unavailable("session_roots_unreadable")
        _add(roots.artifact_ids, artifact)
    provenance = record.get("firmware_provenance")
    if provenance is not None:
        if not isinstance(provenance, dict):
            roots.unavailable("session_provenance_unreadable")
        else:
            try:
                _source_roots(roots, provenance)
            except ValueError:
                roots.unavailable("session_provenance_unreadable")


def _source_roots(roots: RetentionRoots, value) -> None:
    if isinstance(value, dict):
        for field, target in (("artifact_id", roots.artifact_ids), ("firmware_id", roots.firmware_ids),
                              ("base_firmware_id", roots.firmware_ids),
                              ("base_sha256", roots.firmware_shas), ("firmware_sha256", roots.firmware_shas)):
            if field in value:
                if not _sha(value[field]):
                    raise ValueError("invalid declared provenance root")
                target.add(value[field])
        for child in value.values():
            if isinstance(child, (dict, list)):
                _source_roots(roots, child)
    elif isinstance(value, list):
        for child in value:
            _source_roots(roots, child)


class PreviewRetention:
    def __init__(self, state_dir: Path, *, live_roots: Callable[[], RetentionRoots] | None = None):
        self.state_dir = Path(state_dir)
        self.live_roots = live_roots
        self._lock = threading.RLock()
        self._allocations: set[object] = set()
        self._generation = 0

    def begin_allocation(self) -> object:
        token = object()
        with self._lock:
            self._allocations.add(token)
            self._generation += 1
        return token

    def end_allocation(self, token: object) -> None:
        # The caller must persist bound/known-failed/unknown before this point.
        # Pending/creating/unknown records retain a restart-safe cache barrier.
        with self._lock:
            if token not in self._allocations:
                raise ValueError("unknown allocation token")
            self._allocations.remove(token)
            self._generation += 1

    @contextmanager
    def allocation(self):
        token = self.begin_allocation()
        try:
            yield token
        finally:
            self.end_allocation(token)

    def _ledger_roots(self, roots: RetentionRoots) -> None:
        path = self.state_dir / "preview-state.sqlite"
        try:
            path.stat()
        except FileNotFoundError:
            return
        if path.is_symlink() or not path.is_file():
            raise ValueError("unreadable preview ledger")
        # mode=ro avoids silently replacing a lost database with an empty one.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as connection:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("unsupported preview ledger")
            for preview_id, raw in connection.execute("SELECT preview_id, record FROM previews"):
                preview = json.loads(raw)
                if not isinstance(preview, dict) or not isinstance(preview.get("session_request"), dict):
                    raise ValueError("invalid retained preview")
                if not _uuid(preview_id) or preview.get("preview_id") != preview_id or not _uuid(preview.get("owner_epoch")):
                    raise ValueError("invalid retained control identity")
                session_id = preview.get("session_id")
                if session_id is not None and not _uuid(session_id):
                    raise ValueError("invalid retained session identity")
                reference = preview["session_request"].get("reference_sha256")
                if not _sha(reference):
                    raise ValueError("missing retained reference root")
                _add(roots.session_ids, session_id)
                _add(roots.firmware_shas, preview["session_request"].get("reference_sha256"))
                allocation = preview.get("allocation_state")
                if allocation not in {"pending", "creating", "bound", "unknown", "failed"}:
                    raise ValueError("invalid retained allocation")
                if not session_id and allocation in {"pending", "creating", "unknown"}:
                    roots.cache_barrier = True
                    roots.reasons.add("preview_allocation_unbound")
                elif allocation == "bound" and not session_id:
                    raise ValueError("missing retained session")
                expectation = {"binding": {"preview_id": preview_id, "owner_epoch": preview["owner_epoch"],
                                            "expected_reference_sha256": reference}}
                if "session_identity" in preview:
                    identity = preview["session_identity"]
                    if (not isinstance(identity, dict) or not _uuid(identity.get("session_id"))
                            or identity["session_id"] != session_id or not _sha(identity.get("firmware_sha256"))):
                        raise ValueError("invalid retained session receipt")
                    if "firmware_id" in identity:
                        if not _sha(identity["firmware_id"]) or identity["firmware_id"] != identity["firmware_sha256"]:
                            raise ValueError("invalid retained firmware receipt")
                        roots.firmware_ids.add(identity["firmware_id"])
                        expectation["firmware_id"] = identity["firmware_id"]
                    roots.firmware_shas.add(identity["firmware_sha256"])
                    expectation["firmware_sha256"] = identity["firmware_sha256"]
                if session_id:
                    previous = roots.session_expectations.get(session_id)
                    if previous is not None and previous != expectation:
                        raise ValueError("inconsistent retained session ownership")
                    roots.session_expectations[session_id] = expectation

    def _disk_session_roots(self, roots: RetentionRoots) -> None:
        directory = self.state_dir / "sessions"
        try:
            directory.stat()
        except FileNotFoundError:
            if roots.session_ids:
                roots.unavailable("retained_sessions_missing")
            return
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("unreadable sessions directory")
        found = set()
        for path in directory.iterdir():
            if path.is_symlink():
                roots.unavailable("session_directory_unreadable")
                continue
            if not path.is_dir():
                continue
            try:
                record_path = path / "session.json"
                if record_path.is_symlink():
                    raise ValueError("session record symlink")
                record = json.loads(record_path.read_text(encoding="utf-8"))
                if not isinstance(record, dict) or record.get("session_id") != path.name:
                    raise ValueError("invalid session record")
            except (OSError, ValueError, UnicodeError):
                roots.unavailable("session_record_unreadable")
                continue
            found.add(path.name)
            if record.get("management_binding") is not None or path.name in roots.session_ids:
                add_session_roots(roots, record, retained=True)
                expected = roots.session_expectations.get(path.name)
                if expected is not None:
                    binding = record.get("management_binding")
                    if binding is not None and binding != expected["binding"]:
                        roots.unavailable("session_binding_inconsistent")
                    if "firmware_sha256" in expected and record.get("firmware_sha256") != expected["firmware_sha256"]:
                        roots.unavailable("session_identity_inconsistent")
                    if "firmware_id" in expected and record.get("firmware_id") != expected["firmware_id"]:
                        roots.unavailable("session_identity_inconsistent")
        if roots.session_ids - found:
            roots.unavailable("retained_session_record_missing")

    def snapshot(self) -> RetentionRoots:
        roots = RetentionRoots()
        try:
            self._ledger_roots(roots)
            # Live roots include ordinary sessions too, preserving their current
            # cache protection without marking their history retention-only.
            if self.live_roots is not None:
                roots.merge(self.live_roots())
            self._disk_session_roots(roots)
            visited = set()
            while (roots.firmware_ids | roots.firmware_shas) - visited:
                firmware_id = next(iter((roots.firmware_ids | roots.firmware_shas) - visited))
                visited.add(firmware_id)
                if Path(firmware_id).name != firmware_id or firmware_id in {".", ".."}:
                    raise ValueError("invalid retained firmware identity")
                path = self.state_dir / "firmware" / f"{firmware_id}.json"
                try:
                    path.stat()
                except FileNotFoundError:
                    # Reference IDs need not have a FirmwareStore record.
                    continue
                if path.is_symlink() or not path.is_file():
                    raise ValueError("unreadable retained firmware")
                record = json.loads(path.read_text(encoding="utf-8"))
                if (not isinstance(record, dict) or record.get("firmware_id") != firmware_id
                        or record.get("sha256") != firmware_id or not _sha(record.get("sha256"))
                        or not isinstance(record.get("source"), dict)):
                    raise ValueError("invalid retained firmware")
                _add(roots.firmware_shas, record.get("sha256"))
                _source_roots(roots, record.get("source"))
        except Exception:
            # A provider failure or corrupt shape must never become empty roots.
            roots.unavailable("retention_roots_unavailable")
        return roots

    @contextmanager
    def _guard(self):
        while True:
            with self._lock:
                generation = self._generation
            roots = self.snapshot()  # Disk/DB work never holds the deletion lock.
            with self._lock:
                if generation != self._generation:
                    continue
                if self._allocations:
                    roots.cache_barrier = True
                    roots.reasons.add("preview_allocation_in_flight")
                yield roots
                return

    @contextmanager
    def cache_deletion(self, kind: str, identity: str):
        with self._guard() as roots:
            protected = {
                "firmware": roots.firmware_ids | roots.firmware_shas,
                "artifact": roots.artifact_ids,
                "flash": roots.firmware_ids | roots.firmware_shas,
                "upload": set(),
            }
            if kind not in protected:
                raise ValueError("invalid cache kind")
            if roots.cache_barrier:
                yield RetentionDecision(True, "retention_barrier")
            else:
                yield RetentionDecision(identity in protected[kind], "retained_root" if identity in protected[kind] else "")

    @contextmanager
    def session_deletion(self, session_id: str, *, managed: bool = False, orphan: bool = False):
        with self._guard() as roots:
            if managed or session_id in roots.session_ids:
                yield RetentionDecision(True, "retained_managed_history")
            elif roots.history_barrier or (orphan and roots.cache_barrier):
                yield RetentionDecision(True, "retention_barrier")
            else:
                yield RetentionDecision(False)
