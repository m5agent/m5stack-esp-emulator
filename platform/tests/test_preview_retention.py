"""Host-only deletion, restart and allocation-race tests; no guest is started."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from device_service import ArtifactStore, DeviceService, FirmwareStore, ServiceError
from preview_retention import PreviewRetention, RetentionRoots, add_session_roots
from preview_store import LOCAL_OWNER, PreviewStore
from storage_policy import StoragePolicy


OLD = "2020-01-01T00:00:00+00:00"
BASE = "b" * 64
SESSION_ID = "1" * 32


class _StoppedSession:
    def __init__(self, directory, session_id, *, managed=False, firmware_id="f" * 64, firmware_sha="f" * 64, artifacts=()):
        self.id, self.state = session_id, "stopped"
        self.dir = directory / "sessions" / session_id
        self.dir.mkdir(parents=True)
        self.management_binding = {"preview_id": "2" * 32, "owner_epoch": "3" * 32,
                                   "expected_reference_sha256": BASE} if managed else None
        self.firmware_id, self.firmware_sha = firmware_id, firmware_sha
        self.source_artifacts = list(artifacts)
        self.created_at = self.completed_at = OLD
        self.stop_calls = []
        self.persist()

    def persist(self):
        record = {"session_id": self.id, "firmware_id": self.firmware_id,
                  "firmware_sha256": self.firmware_sha, "source_artifacts": self.source_artifacts,
                  "management_binding": self.management_binding}
        (self.dir / "session.json").write_text(json.dumps(record), encoding="utf-8")
        (self.dir / "serial.log").write_text("host-only fixture", encoding="utf-8")

    def stop(self, *, purge=False, retain_flash=None):
        self.stop_calls.append((purge, retain_flash))
        if purge:
            shutil.rmtree(self.dir)
        return {"session_id": self.id, "state": self.state}


class PreviewRetentionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.retention = PreviewRetention(self.directory)

    def preview(self, *, allocation="pending", session_id=None, state="preparing"):
        store = PreviewStore(self.directory / "preview-state.sqlite")
        row, _ = store.create(LOCAL_OWNER, "create", {}, {"reference_sha256": BASE}, OLD)
        if allocation != "pending" or state != "preparing":
            def change(data):
                data["preview"].update(allocation_state="creating")
            store.mutate(row["preview_id"], change)
            if allocation != "creating":
                store.mutate(row["preview_id"], lambda data: data["preview"].update(
                    allocation_state=allocation, session_id=session_id, state=state))
        if session_id:
            path = self.directory / "sessions" / session_id / "session.json"
            if path.is_file():
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("management_binding") is not None:
                    record["management_binding"] = {"preview_id": row["preview_id"], "owner_epoch": row["owner_epoch"],
                                                    "expected_reference_sha256": BASE}
                    path.write_text(json.dumps(record), encoding="utf-8")
        return store, row

    def decision(self, kind, identity):
        with self.retention.cache_deletion(kind, identity) as decision:
            return decision

    def service(self, **policy):
        service = object.__new__(DeviceService)
        service.state_dir = self.directory
        service._lock = threading.RLock()
        service._sessions = {}
        service.storage_policy = StoragePolicy(
            min_free_bytes=0, cache_grace_seconds=policy.pop("cache_grace_seconds", 0),
            max_cache_bytes=policy.pop("max_cache_bytes", 0), **policy,
        )
        service.artifacts = ArtifactStore(self.directory / "artifacts")
        service.firmware = FirmwareStore(self.directory / "firmware", service.artifacts, {})
        return service

    def firmware(self, service, number, *, source_artifact=None):
        firmware_id = f"{number:064x}"
        sha = firmware_id
        record = {"firmware_id": firmware_id, "sha256": sha, "created_at": OLD,
                  "source": {"segments": [{"artifact_id": source_artifact}]} if source_artifact else {}}
        service.firmware._meta(firmware_id).write_text(json.dumps(record), encoding="utf-8")
        service.firmware._data(firmware_id).write_bytes(b"synthetic fixture")
        cache = self.directory / "flash-cache" / "fixture" / f"{sha}.bin"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"cache fixture")
        os.utime(cache, (0, 0))
        return firmware_id, sha, cache

    def old_artifact(self, service, data):
        record = service.artifacts.create(data)
        record["created_at"] = OLD
        service.artifacts._meta(record["artifact_id"]).write_text(json.dumps(record), encoding="utf-8")
        return record["artifact_id"]

    def test_unused_preview_preserves_cache_deletion_and_does_not_create_ledger(self):
        self.assertFalse(self.decision("artifact", "a" * 64).protected)
        self.assertFalse((self.directory / "preview-state.sqlite").exists())

    def test_pending_creating_unknown_allocations_survive_restart_as_barriers(self):
        for allocation in ("pending", "creating", "unknown"):
            with self.subTest(allocation=allocation):
                database = self.directory / "preview-state.sqlite"
                for path in self.directory.glob("preview-state.sqlite*"):
                    path.unlink()
                self.preview(allocation=allocation)
                restarted = PreviewRetention(self.directory)
                with restarted.cache_deletion("artifact", "a" * 64) as decision:
                    self.assertTrue(decision.protected)
                self.assertTrue(database.is_file())

    def test_known_failed_allocation_releases_global_cache_barrier(self):
        self.preview(allocation="failed", state="failed")
        self.assertFalse(self.decision("artifact", "a" * 64).protected)
        self.assertTrue(self.decision("flash", BASE).protected)

    def test_bound_closed_preview_keeps_exact_session_and_firmware_roots(self):
        service = self.service()
        artifact = self.old_artifact(service, b"source")
        firmware_id, sha, _ = self.firmware(service, 1, source_artifact=artifact)
        session = _StoppedSession(self.directory, SESSION_ID, managed=True, firmware_id=firmware_id, firmware_sha=sha)
        self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        self.assertTrue(self.decision("firmware", firmware_id).protected)
        self.assertTrue(self.decision("artifact", artifact).protected)
        self.assertTrue(self.decision("flash", BASE).protected)
        self.assertTrue(self.decision("flash", sha).protected)
        self.assertFalse(self.decision("firmware", "f" * 64).protected)
        with self.retention.session_deletion(session.id) as decision:
            self.assertEqual(decision.reason, "retained_managed_history")

    def test_managed_disk_orphan_is_protected_without_live_ledger(self):
        _StoppedSession(self.directory, SESSION_ID, managed=True, artifacts=("a" * 64,))
        self.assertTrue(self.decision("artifact", "a" * 64).protected)
        self.assertFalse(self.decision("artifact", "f" * 64).protected)
        with self.retention.session_deletion(SESSION_ID, orphan=True) as decision:
            self.assertTrue(decision.protected)

    def test_retained_session_without_live_or_disk_marker_is_still_protected(self):
        _StoppedSession(self.directory, SESSION_ID, artifacts=("a" * 64,))
        self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        self.assertTrue(self.decision("artifact", "a" * 64).protected)
        self.assertFalse(self.decision("artifact", "f" * 64).protected)
        with self.retention.session_deletion(SESSION_ID, orphan=True) as decision:
            self.assertEqual(decision.reason, "retained_managed_history")

    def test_missing_retained_session_record_preserves_all_cache_roots(self):
        self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        self.assertTrue(self.decision("artifact", "a" * 64).protected)

    def test_corrupt_ledger_is_not_treated_as_empty(self):
        (self.directory / "preview-state.sqlite").write_bytes(b"invalid sqlite")
        self.assertTrue(self.decision("artifact", "a" * 64).protected)
        with self.retention.session_deletion("ordinary") as decision:
            self.assertEqual(decision.reason, "retention_barrier")

    def test_valid_json_with_corrupt_retention_identity_is_fail_closed(self):
        store, row = self.preview(allocation="failed", state="failed")
        record = store.get_preview(LOCAL_OWNER, row["preview_id"])
        record.update(session_id=[SESSION_ID], allocation_state="bound")
        with sqlite3.connect(store.path) as connection:
            connection.execute("UPDATE previews SET record=?", (json.dumps(record),))
        self.assertTrue(self.decision("artifact", "a" * 64).protected)

    def test_session_read_or_directory_scan_failure_preserves_roots(self):
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        (session.dir / "session.json").write_text("{", encoding="utf-8")
        self.assertTrue(self.decision("artifact", "a" * 64).protected)
        with mock.patch.object(Path, "iterdir", side_effect=OSError("scan failure")):
            with self.retention.session_deletion(SESSION_ID, orphan=True) as decision:
                self.assertTrue(decision.protected)

    def test_roots_provider_failure_is_fail_closed(self):
        self.retention.live_roots = mock.Mock(side_effect=OSError("unavailable"))
        self.assertTrue(self.decision("firmware", "a" * 64).protected)

    def test_allocation_token_only_blocks_during_actual_unbound_window(self):
        with self.retention.allocation():
            self.assertTrue(self.decision("artifact", "a" * 64).protected)
            with self.retention.session_deletion("new", orphan=True) as decision:
                self.assertTrue(decision.protected)
        self.assertFalse(self.decision("artifact", "a" * 64).protected)

    def test_allocation_fences_delete_without_holding_lock_during_composition(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        def compose():
            with self.retention.allocation():
                entered.set()
                release.wait(2)
            finished.set()
        thread = threading.Thread(target=compose)
        thread.start()
        self.addCleanup(thread.join, 3)
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.decision("artifact", "a" * 64).protected)
            self.assertFalse(finished.is_set())
        finally:
            release.set()

    def test_begin_allocation_waits_until_actual_delete_finishes(self):
        attempted = threading.Event()
        allocated = threading.Event()
        def allocate():
            attempted.set()
            with self.retention.allocation():
                allocated.set()
        with self.retention.cache_deletion("artifact", "a" * 64) as decision:
            self.assertFalse(decision.protected)
            thread = threading.Thread(target=allocate)
            thread.start()
            self.assertTrue(attempted.wait(1))
            self.assertFalse(allocated.wait(0.05))
        thread.join(2)
        self.assertTrue(allocated.is_set())

    def test_stale_roots_snapshot_is_retried_after_allocate_and_bind(self):
        stale = threading.Event()
        release = threading.Event()
        calls = []
        artifact_id = "a" * 64
        def read_roots():
            calls.append(1)
            if len(calls) == 1:
                stale.set()
                release.wait(2)
                return RetentionRoots()
            return RetentionRoots(artifact_ids={artifact_id})
        self.retention.live_roots = read_roots
        outcomes = []
        thread = threading.Thread(target=lambda: outcomes.append(self.decision("artifact", artifact_id)))
        thread.start()
        try:
            self.assertTrue(stale.wait(1))
            with self.retention.allocation():
                pass  # A persisted binding appeared while the old read was in flight.
        finally:
            release.set()
            thread.join(2)
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(outcomes[0].protected)

    def test_bulk_clear_protects_managed_history_and_disk_orphans(self):
        service = self.service()
        managed = _StoppedSession(self.directory, SESSION_ID, managed=True)
        ordinary = _StoppedSession(self.directory, "4" * 32)
        orphan = _StoppedSession(self.directory, "5" * 32, managed=True)
        ordinary_orphan = _StoppedSession(self.directory, "6" * 32)
        service._sessions = {row.id: row for row in (managed, ordinary)}
        result = service.clear_stopped()
        self.assertEqual(result["cleared"], 1)
        self.assertEqual(result["protected_sessions"], [managed.id])
        self.assertEqual(result["orphaned_protected"], [orphan.id])
        self.assertEqual(result["orphaned_cleared"], 1)
        self.assertTrue(managed.dir.is_dir())
        self.assertTrue(orphan.dir.is_dir())
        self.assertFalse(ordinary_orphan.dir.exists())
        self.assertEqual(managed.stop_calls, [])

    def test_bulk_clear_preserves_unreadable_orphan_and_reports_skipped(self):
        service = self.service()
        orphan = self.directory / "sessions" / SESSION_ID
        orphan.mkdir(parents=True)
        (orphan / "session.json").write_text("{", encoding="utf-8")
        result = service.clear_stopped()
        self.assertEqual(result["orphaned_skipped"], [SESSION_ID])
        self.assertTrue(orphan.is_dir())

    def test_bulk_clear_does_not_follow_session_directory_symlinks(self):
        service = self.service()
        target = self.directory / "outside-sessions"
        target.mkdir()
        evidence = target / "retained"
        evidence.write_text("fixture", encoding="utf-8")
        sessions = self.directory / "sessions"
        sessions.mkdir()
        (sessions / SESSION_ID).symlink_to(target, target_is_directory=True)
        result = service.clear_stopped()
        self.assertEqual(result["orphaned_skipped"], [SESSION_ID])
        self.assertTrue(evidence.is_file())

    def test_direct_purge_rejects_managed_history_without_stopping_it(self):
        service = self.service()
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        service._sessions[session.id] = session
        with self.assertRaises(ServiceError) as caught:
            service.delete_session(session.id, purge=True)
        self.assertEqual(caught.exception.code, "retained_preview_history")
        self.assertEqual(session.stop_calls, [])
        self.assertIn(session.id, service._sessions)

    def test_retention_pressure_prunes_ordinary_history_beside_managed_history(self):
        service = self.service(history_ttl_seconds=0, max_history_sessions=1, max_history_bytes=1)
        managed = _StoppedSession(self.directory, SESSION_ID, managed=True)
        ordinary = _StoppedSession(self.directory, "4" * 32)
        service._sessions = {row.id: row for row in (managed, ordinary)}
        result = service.prune_storage(include_cache=False)
        self.assertEqual(result["pruned_sessions"], 1)
        self.assertEqual(result["protected_sessions"], [managed.id])
        self.assertTrue(managed.dir.is_dir())
        self.assertFalse(ordinary.dir.exists())

    def test_ttl_and_pressure_cache_passes_keep_roots_but_evict_unrelated_data(self):
        for grace in (0, 3600):
            with self.subTest(grace=grace):
                service = self.service(cache_grace_seconds=grace, max_cache_bytes=1)
                artifact = self.old_artifact(service, b"protected source")
                other_artifact = self.old_artifact(service, b"unreferenced source")
                firmware_id, sha, cache = self.firmware(service, 1, source_artifact=artifact)
                other_id, _, other_cache = self.firmware(service, 2, source_artifact=other_artifact)
                _StoppedSession(self.directory, SESSION_ID, managed=True, firmware_id=firmware_id, firmware_sha=sha,
                                artifacts=(artifact,))
                result = service._prune_firmware_caches(now=time.time())
                self.assertTrue(service.firmware._meta(firmware_id).is_file())
                self.assertTrue(service.artifacts._meta(artifact).is_file())
                self.assertTrue(cache.is_file())
                self.assertFalse(service.firmware._meta(other_id).exists())
                self.assertFalse(service.artifacts._meta(other_artifact).exists())
                self.assertFalse(other_cache.exists())
                self.assertFalse(result["retention_barrier"])
                shutil.rmtree(self.directory / "sessions")

    def test_manual_artifact_delete_uses_same_retained_root_and_allocation_guard(self):
        service = self.service()
        protected = self.old_artifact(service, b"retained")
        unrelated = self.old_artifact(service, b"unrelated")
        _StoppedSession(self.directory, SESSION_ID, managed=True, artifacts=(protected,))
        with self.assertRaises(ServiceError) as caught:
            service.delete_artifact(protected)
        self.assertEqual(caught.exception.code, "retained_preview_artifact")
        with service.preview_allocation_guard():
            with self.assertRaises(ServiceError):
                service.delete_artifact(unrelated)
        self.assertTrue(service.delete_artifact(unrelated)["deleted"])
        self.assertTrue(service.artifacts._meta(protected).is_file())

    def test_corrupt_ledger_keeps_history_and_manual_artifact_even_without_coordinator(self):
        service = self.service(history_ttl_seconds=1)
        ordinary = _StoppedSession(self.directory, SESSION_ID)
        service._sessions[ordinary.id] = ordinary
        artifact = self.old_artifact(service, b"unknown retained root")
        (self.directory / "preview-state.sqlite").write_bytes(b"corrupt ledger")
        result = service.prune_storage(include_cache=True)
        self.assertEqual(result["pruned_sessions"], 0)
        self.assertEqual(result["skipped_sessions"], [ordinary.id])
        self.assertTrue(result["cache"]["retention_barrier"])
        with self.assertRaises(ServiceError):
            service.delete_artifact(artifact)
        self.assertEqual(ordinary.stop_calls, [])

    def test_persisted_unbound_allocation_blocks_both_cache_eviction_passes(self):
        service = self.service(max_cache_bytes=1)
        artifact = self.old_artifact(service, b"in-flight source")
        firmware_id, _, cache = self.firmware(service, 1, source_artifact=artifact)
        self.preview(allocation="unknown")
        result = service._prune_firmware_caches(now=time.time())
        self.assertTrue(result["retention_barrier"])
        self.assertEqual(result["firmware_removed"], 0)
        self.assertTrue(service.firmware._meta(firmware_id).is_file())
        self.assertTrue(service.artifacts._meta(artifact).is_file())
        self.assertTrue(cache.is_file())

    def test_semantically_corrupt_retained_firmware_identity_blocks_cache_and_history(self):
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        path = session.dir / "session.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for field in ("firmware_id", "firmware_sha256", "source_artifacts"):
            invalid = (None, "", 123, [], "z" * 64, "A" * 64) if field != "source_artifacts" else (None, {}, [123], [""], ["z" * 64])
            for value in invalid:
                with self.subTest(field=field, value=value):
                    record = {**original, field: value}
                    path.write_text(json.dumps(record), encoding="utf-8")
                    roots = self.retention.snapshot()
                    self.assertTrue(roots.cache_barrier)
                    self.assertTrue(roots.history_barrier)
                    self.assertTrue(self.decision("firmware", "f" * 64).protected)
                    with self.retention.session_deletion("ordinary") as decision:
                        self.assertTrue(decision.protected)
            with self.subTest(field=field, value="missing"):
                record = dict(original)
                record.pop(field)
                path.write_text(json.dumps(record), encoding="utf-8")
                self.assertTrue(self.retention.snapshot().cache_barrier)
        path.write_text(json.dumps(original), encoding="utf-8")
        self.assertFalse(self.retention.snapshot().cache_barrier)
        self.assertFalse(self.decision("firmware", "9" * 64).protected)

    def test_declared_binding_and_nested_provenance_corruption_is_fail_closed(self):
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        path = session.dir / "session.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        bad_bindings = [[], {}, {**session.management_binding, "preview_id": None},
                        {**session.management_binding, "owner_epoch": ""},
                        {**session.management_binding, "expected_reference_sha256": ""},
                        {**session.management_binding, "expected_reference_sha256": "z" * 64}]
        bad_provenance = [[], "unknown", {"artifact_id": None}, {"metadata": {"base_sha256": ""}},
                          {"metadata": {"firmware_sha256": "z" * 64}}, {"metadata": {"segments": [{"artifact_id": 123}]}}]
        for field, values in (("management_binding", bad_bindings), ("firmware_provenance", bad_provenance)):
            for value in values:
                with self.subTest(field=field, value=value):
                    path.write_text(json.dumps({**original, field: value}), encoding="utf-8")
                    self.assertTrue(self.retention.snapshot().cache_barrier)
                    self.assertTrue(self.retention.snapshot().history_barrier)

    def test_nested_session_provenance_preserves_declared_roots_without_firmware_metadata(self):
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        path = session.dir / "session.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["firmware_provenance"] = {"kind": "uiflow", "artifact_id": "a" * 64,
                                         "metadata": {"base_sha256": "c" * 64, "firmware_sha256": "d" * 64}}
        path.write_text(json.dumps(record), encoding="utf-8")
        roots = self.retention.snapshot()
        self.assertFalse(roots.cache_barrier)
        self.assertIn("a" * 64, roots.artifact_ids)
        self.assertIn("c" * 64, roots.firmware_shas)
        self.assertFalse(self.decision("artifact", "9" * 64).protected)

    def test_corrupt_ledger_reference_and_session_identity_are_not_ignored(self):
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        store, row = self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        original = store.get_preview(LOCAL_OWNER, row["preview_id"])
        mutations = []
        for value in (None, "", "z" * 64, "A" * 64, 123):
            record = json.loads(json.dumps(original))
            record["session_request"]["reference_sha256"] = value
            mutations.append(record)
        for value in (None, [], {}, {"session_id": "9" * 32, "firmware_sha256": "d" * 64},
                      {"session_id": SESSION_ID, "firmware_sha256": None},
                      {"session_id": SESSION_ID, "firmware_sha256": "z" * 64},
                      {"session_id": SESSION_ID, "firmware_sha256": "9" * 64},
                      {"session_id": SESSION_ID, "firmware_sha256": session.firmware_sha, "firmware_id": "9" * 64}):
            mutations.append({**original, "session_identity": value})
        for index, record in enumerate(mutations):
            with self.subTest(index=index):
                with sqlite3.connect(store.path) as connection:
                    connection.execute("UPDATE previews SET record=?", (json.dumps(record),))
                self.assertTrue(self.retention.snapshot().cache_barrier)
                self.assertTrue(self.retention.snapshot().history_barrier)
        with sqlite3.connect(store.path) as connection:
            connection.execute("UPDATE previews SET record=?", (json.dumps({**original, "session_identity": {
                "session_id": SESSION_ID, "firmware_sha256": session.firmware_sha}}),))
        self.assertFalse(self.retention.snapshot().cache_barrier)

    def test_provenance_firmware_dependency_metadata_is_followed_once(self):
        service = self.service()
        child_artifact = self.old_artifact(service, b"child source")
        parent_id, parent_sha, _ = self.firmware(service, 1)
        child_id, _, _ = self.firmware(service, 2, source_artifact=child_artifact)
        path = service.firmware._meta(parent_id)
        record = json.loads(path.read_text(encoding="utf-8"))
        record["source"]["firmware_id"] = child_id
        path.write_text(json.dumps(record), encoding="utf-8")
        child_path = service.firmware._meta(child_id)
        child_record = json.loads(child_path.read_text(encoding="utf-8"))
        child_record["source"]["firmware_id"] = parent_id
        child_path.write_text(json.dumps(child_record), encoding="utf-8")
        _StoppedSession(self.directory, SESSION_ID, managed=True, firmware_id=parent_id, firmware_sha=parent_sha)
        roots = self.retention.snapshot()
        self.assertFalse(roots.cache_barrier)
        self.assertIn(child_id, roots.firmware_ids)
        self.assertIn(child_artifact, roots.artifact_ids)

    def test_retained_disk_binding_must_match_ledger_control_and_reference(self):
        session = _StoppedSession(self.directory, SESSION_ID, managed=True)
        self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        path = session.dir / "session.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for field, value in (("preview_id", "9" * 32), ("owner_epoch", "9" * 32), ("expected_reference_sha256", "9" * 64)):
            with self.subTest(field=field):
                record = json.loads(json.dumps(original))
                record["management_binding"][field] = value
                path.write_text(json.dumps(record), encoding="utf-8")
                self.assertTrue(self.retention.snapshot().cache_barrier)
        path.write_text(json.dumps(original), encoding="utf-8")
        self.assertFalse(self.retention.snapshot().cache_barrier)

    def test_retained_firmware_metadata_declared_roots_are_strict(self):
        service = self.service()
        firmware_id, sha, _ = self.firmware(service, 1)
        _StoppedSession(self.directory, SESSION_ID, managed=True, firmware_id=firmware_id, firmware_sha=sha)
        path = service.firmware._meta(firmware_id)
        original = json.loads(path.read_text(encoding="utf-8"))
        for field, value in (("firmware_id", None), ("firmware_id", "9" * 64), ("sha256", ""),
                             ("source", None), ("source", {"artifact_id": None}),
                             ("source", {"segments": [{"artifact_id": "z" * 64}]}),
                             ("source", {"metadata": {"base_sha256": ""}})):
            with self.subTest(field=field, value=value):
                path.write_text(json.dumps({**original, field: value}), encoding="utf-8")
                self.assertTrue(self.retention.snapshot().cache_barrier)
        path.write_text(json.dumps(original), encoding="utf-8")
        self.assertFalse(self.retention.snapshot().cache_barrier)

    def test_ordinary_live_legacy_empty_identity_does_not_create_unrelated_barrier(self):
        roots = RetentionRoots()
        add_session_roots(roots, {"firmware_id": None, "firmware_sha256": None,
                                  "source_artifacts": [], "management_binding": None})
        self.retention.live_roots = lambda: roots
        self.assertFalse(self.retention.snapshot().cache_barrier)
        self.assertFalse(self.decision("firmware", "9" * 64).protected)

    def test_content_addressed_session_id_sha_mismatch_is_fail_closed(self):
        service = self.service()
        firmware_id, sha, _ = self.firmware(service, 1)
        session = _StoppedSession(self.directory, SESSION_ID, managed=True, firmware_id=firmware_id, firmware_sha=sha)
        store, row = self.preview(allocation="bound", session_id=SESSION_ID, state="closed")
        store.mutate(row["preview_id"], lambda state: state["preview"].update(session_identity={
            "session_id": SESSION_ID, "firmware_sha256": sha}))
        record_path = session.dir / "session.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["firmware_id"] = "d" * 64
        record_path.write_text(json.dumps(record), encoding="utf-8")
        self.assertTrue(self.retention.snapshot().cache_barrier)
        self.assertTrue(self.decision("firmware", firmware_id).protected)

    def test_reference_sha_root_also_protects_content_addressed_metadata_and_source(self):
        service = self.service()
        artifact = self.old_artifact(service, b"reference source")
        metadata = {"firmware_id": BASE, "sha256": BASE, "source": {"artifact_id": artifact}}
        service.firmware._meta(BASE).write_text(json.dumps(metadata), encoding="utf-8")
        self.preview(allocation="failed", state="failed")
        self.assertFalse(self.retention.snapshot().cache_barrier)
        self.assertTrue(self.decision("firmware", BASE).protected)
        self.assertTrue(self.decision("artifact", artifact).protected)


if __name__ == "__main__":
    unittest.main()
