"""Real SQLite ledger tests. No guest, UART, service or physical-device claim."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from preview_store import LOCAL_OWNER, PreviewStore, PreviewStoreError


class PreviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "state" / "preview-state.sqlite"
        self.store = PreviewStore(self.path)
        self.expiry = "2030-01-01T00:00:00+00:00"

    def create(self, key="create-1", request=None):
        return self.store.create(
            LOCAL_OWNER, key, request or {"device_id": "cores3", "ttl_seconds": 300},
            {"device_id": "cores3", "runtime": "qemu", "program_mode": "uiflow-live"}, self.expiry,
        )[0]

    def payload(self, preview, generation=None, revision="a", **changes):
        value = {
            "revision_id": revision * 64,
            "expected_generation": preview["generation"] if generation is None else generation,
            "expected_owner_epoch": preview["owner_epoch"],
        }
        value.update(changes)
        return value

    def admit(self, preview, key="run-1", generation=None, revision="a", **changes):
        return self.store.admit_run(LOCAL_OWNER, preview["preview_id"], key, self.payload(preview, generation, revision, **changes))[0]

    def get(self, preview, run):
        return self.store.get_run(LOCAL_OWNER, preview["preview_id"], run["run_id"])

    def assert_error(self, code, callable, *args, status=None, **kwargs):
        with self.assertRaises(PreviewStoreError) as caught:
            callable(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        return caught.exception

    def running(self, preview, run):
        def update(state):
            state["runs"][run["run_id"]]["state"] = "running"
            state["preview"]["state"] = "ready"
            state["preview"]["active_run_id"] = run["run_id"]
            return state
        return self.store.mutate(preview["preview_id"], update)

    def test_schema_durability_foreign_keys_and_truthful_limits(self):
        self.assertEqual(self.store.limits(), {
            "max_previews": 128, "max_runs_per_preview": 256,
            "retention_mode": "retention-only", "gc_enabled": False,
        })
        with self.store._transaction() as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], 2)
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO runs VALUES(?,?,?)", ("missing", "missing", "{}"))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_runtime_capability_is_separate_from_frozen_create_receipt(self):
        created = self.create()
        updated = {"schema_version": 1, "status": "unsupported", "mpy_entrypoint": False}
        self.store.mutate(created["preview_id"], lambda state: state["preview"].update(runtime_capabilities=updated))
        current = self.store.get_preview(LOCAL_OWNER, created["preview_id"])
        self.assertEqual(current["runtime_capabilities"], updated)
        self.assertEqual(current["session_request"], created["session_request"])
        self.assertEqual(self.create(), created)

    def test_concurrent_create_same_key_allocates_once_and_freezes_original_receipt(self):
        barrier = threading.Barrier(12)
        request = {"device_id": "cores3", "ttl_seconds": 300}

        def create(index):
            barrier.wait(timeout=5)
            return PreviewStore(self.path).create(
                LOCAL_OWNER, "same-create", dict(reversed(list(request.items()))) if index % 2 else request,
                {"derived": index}, self.expiry,
            )

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(create, range(12)))
        self.assertEqual(sum(not replayed for _, replayed in results), 1)
        receipt = results[0][0]
        self.assertTrue(all(value == receipt for value, _ in results))
        self.assertEqual(len(self.store.list_previews()), 1)
        self.assertRegex(receipt["preview_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(receipt["owner_epoch"], r"^[0-9a-f]{32}$")
        self.assertEqual(receipt["allocation_key"], f"preview:{receipt['preview_id']}:allocation:1")
        self.assertEqual(receipt["allocation_state"], "pending")
        self.assertEqual(self.store.create(LOCAL_OWNER, "same-create", request, None, "invalid"), (receipt, True))

    def test_concurrent_run_same_key_has_one_identity_generation_receipt_and_pin(self):
        preview = self.create()
        payload = self.payload(preview)
        barrier = threading.Barrier(12)

        def admit(_):
            barrier.wait(timeout=5)
            return PreviewStore(self.path).admit_run(LOCAL_OWNER, preview["preview_id"], "same-run", payload)

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(admit, range(12)))
        self.assertEqual(sum(not replayed for _, replayed in results), 1)
        run = results[0][0]
        self.assertTrue(all(value == run for value, _ in results))
        self.assertRegex(run["run_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(run["execution_id"], r"^[0-9a-f]{32}$")
        self.assertNotEqual(run["run_id"], run["execution_id"])
        current = self.store.get_preview(LOCAL_OWNER, preview["preview_id"])
        self.assertEqual(current["generation"], 1)
        self.assertEqual(current["desired_run_id"], run["run_id"])
        self.assertEqual(self.store.revision_pins(), [{
            "run_id": run["run_id"], "preview_id": preview["preview_id"],
            "owner": LOCAL_OWNER, "source_kind": "uiflow2-package", "revision_id": "a" * 64,
        }])

    def test_replay_precedes_generation_state_and_mutable_status_without_new_execution(self):
        preview = self.create()
        payload = self.payload(preview)
        first = self.admit(preview)
        second = self.admit(preview, "run-2", generation=1, revision="b")
        self.assertEqual(self.get(preview, first)["state"], "superseded")

        def close(state):
            state["preview"]["state"] = "closed"
            state["runs"][second["run_id"]]["state"] = "failed"
        self.store.mutate(preview["preview_id"], close)
        replay, replayed = self.store.admit_run(LOCAL_OWNER, preview["preview_id"], "run-1", payload)
        self.assertTrue(replayed)
        self.assertEqual(replay, first)
        self.assertEqual(replay["state"], "queued")
        self.assertEqual(self.store.lookup_replay(LOCAL_OWNER, f"preview:{preview['preview_id']}:runs", "run-1", payload), first)
        self.assertEqual(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["generation"], 2)
        self.assertEqual(len(self.store.revision_pins()), 2)
        self.assert_error("idempotency_conflict", self.store.lookup_replay, LOCAL_OWNER, f"preview:{preview['preview_id']}:runs", "run-1", {**payload, "expected_generation": 2}, status=409)
        self.assert_error("idempotency_conflict", self.store.admit_run, LOCAL_OWNER, preview["preview_id"], "run-1", {**payload, "revision_id": "c" * 64}, status=409)

    def test_generation_owner_epoch_and_body_owner_are_fenced_before_any_change(self):
        preview = self.create()
        first = self.admit(preview)
        for owner in (None, "another-principal"):
            with self.subTest(owner=owner):
                self.assert_error("preview_not_found", self.store.get_preview, owner, preview["preview_id"], status=404)
                self.assert_error("preview_not_found", self.store.get_run, owner, preview["preview_id"], first["run_id"], status=404)
                self.assert_error("preview_not_found", self.store.admit_run, owner, preview["preview_id"], "other", self.payload(preview), status=404)
                self.assert_error("preview_not_found", self.store.lookup_replay, owner, "create-preview", "create-1", preview["request"], status=404)
        self.assert_error("preview_generation_conflict", self.admit, preview, "stale", status=409)
        self.assert_error("preview_owner_conflict", self.admit, preview, "wrong-owner", generation=1, expected_owner_epoch="f" * 32, status=409)
        self.assert_error("preview_owner_conflict", self.store.cancel_run, LOCAL_OWNER, preview["preview_id"], first["run_id"], "f" * 32, status=409)
        self.assert_error("invalid_preview_request", self.admit, preview, "spoof-owner", generation=1, owner=LOCAL_OWNER, status=400)
        self.assertEqual(self.get(preview, first)["state"], "queued")
        self.assertEqual(len(self.store.revision_pins()), 1)

    def test_a_active_b_pending_c_latest_preserves_history_and_cancels_only_old_intent(self):
        preview = self.create()
        a = self.admit(preview)
        self.running(preview, a)
        b = self.admit(preview, "b", generation=1, revision="b")
        c = self.admit(preview, "c", generation=2, revision="c")
        self.assertEqual(self.get(preview, a)["state"], "cancelling")
        self.assertTrue(self.get(preview, a)["cancel_intent"])
        self.assertEqual(self.get(preview, b)["state"], "superseded")
        self.assertEqual(self.get(preview, b)["interrupt_ack"], "not-required")
        current = self.store.get_preview(LOCAL_OWNER, preview["preview_id"])
        self.assertEqual(current["active_run_id"], a["run_id"])
        self.assertEqual(current["desired_run_id"], c["run_id"])
        before = copy.deepcopy(self.get(preview, a))
        self.assertEqual(self.store.cancel_run(LOCAL_OWNER, preview["preview_id"], a["run_id"], preview["owner_epoch"]), before)
        self.assertEqual(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["desired_run_id"], c["run_id"])

    def test_transition_run_needs_real_ack_before_cancelled_and_cannot_late_start(self):
        preview = self.create()
        a = self.admit(preview)

        def preparing(state):
            state["runs"][a["run_id"]]["state"] = "preparing"
            state["preview"]["transition_run_id"] = a["run_id"]
        self.store.mutate(preview["preview_id"], preparing)
        b = self.admit(preview, "b", generation=1, revision="b")
        self.assertEqual(self.get(preview, a)["state"], "cancelling")
        self.assertEqual(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["transition_run_id"], a["run_id"])

        def late_start(state):
            state["runs"][a["run_id"]]["state"] = "running"
            state["preview"]["active_run_id"] = a["run_id"]
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], late_start, status=409)

        def false_ack(state):
            state["runs"][a["run_id"]]["state"] = "cancelled"
            state["preview"]["transition_run_id"] = None
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], false_ack, status=409)

        def confirmed(state):
            false_ack(state)
            state["runs"][a["run_id"]]["interrupt_ack"] = "confirmed"
            return state
        updated = self.store.mutate(preview["preview_id"], confirmed)
        self.assertEqual(updated["runs"][a["run_id"]]["state"], "cancelled")
        self.assertEqual(updated["preview"]["desired_run_id"], b["run_id"])
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], late_start, status=409)
        self.assertEqual(self.get(preview, a)["state"], "cancelled")

    def test_cancel_queued_is_immediate_idempotent_and_only_clears_matching_desired(self):
        preview = self.create()
        a = self.admit(preview)
        first = self.store.cancel_run(LOCAL_OWNER, preview["preview_id"], a["run_id"], preview["owner_epoch"])
        second = self.store.cancel_run(LOCAL_OWNER, preview["preview_id"], a["run_id"], preview["owner_epoch"])
        self.assertEqual(first, second)
        self.assertEqual(first["state"], "cancelled")
        self.assertEqual(first["interrupt_ack"], "not-required")
        self.assertIsNone(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["desired_run_id"])
        self.assertEqual(len(self.store.revision_pins()), 1)

    def test_mutation_immutability_cancel_monotonicity_and_callback_result_detachment(self):
        preview = self.create()
        run = self.admit(preview)
        for field, replacement in (("owner_epoch", "f" * 32), ("generation", 10), ("session_request", {}), ("allocation_key", "other")):
            with self.subTest(field=field):
                self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["preview"].__setitem__(field, replacement), status=409)
        for field, replacement in (("execution_id", "f" * 32), ("revision_id", "f" * 64), ("request", {})):
            with self.subTest(field=field):
                self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["runs"][run["run_id"]].__setitem__(field, replacement), status=409)
        self.store.cancel_run(LOCAL_OWNER, preview["preview_id"], run["run_id"], preview["owner_epoch"])
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["runs"][run["run_id"]].__setitem__("cancel_intent", False), status=409)
        result = self.store.mutate(preview["preview_id"], lambda state: state)
        result["preview"]["request"].clear()
        result["runs"][run["run_id"]]["request"].clear()
        self.assertTrue(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["request"])
        self.assertTrue(self.get(preview, run)["request"])

    def test_allocation_attempt_and_unknown_preview_survive_reopen_without_reallocation(self):
        preview = self.create()
        self.store.mutate(preview["preview_id"], lambda state: state["preview"].update(allocation_state="creating"))
        reopened = PreviewStore(self.path)
        recovered = reopened.get_preview(LOCAL_OWNER, preview["preview_id"])
        self.assertEqual(recovered["allocation_state"], "creating")
        self.assertEqual(recovered["allocation_key"], preview["allocation_key"])
        self.store.mutate(preview["preview_id"], lambda state: state["preview"].update(allocation_state="unknown", state="unknown"))
        self.assert_error("preview_closing", self.admit, preview, status=409)
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["preview"].update(allocation_state="creating"), status=409)
        self.assertEqual(len(reopened.list_previews()), 1)

    def test_callback_exception_rolls_back_all_changes_and_reopen_keeps_old_snapshot(self):
        preview = self.create()
        run = self.admit(preview)
        before_preview, before_run = self.store.get_preview(LOCAL_OWNER, preview["preview_id"]), self.get(preview, run)

        def broken(state):
            state["preview"]["state"] = "failed"
            state["runs"][run["run_id"]]["state"] = "failed"
            raise RuntimeError("interrupted in-memory worker")
        with self.assertRaisesRegex(RuntimeError, "in-memory"):
            self.store.mutate(preview["preview_id"], broken)
        reopened = PreviewStore(self.path)
        self.assertEqual(reopened.get_preview(LOCAL_OWNER, preview["preview_id"]), before_preview)
        self.assertEqual(reopened.get_run(LOCAL_OWNER, preview["preview_id"], run["run_id"]), before_run)

    def test_sql_failure_after_run_pointer_pin_writes_rolls_back_receipt_and_all_rows(self):
        preview = self.create()
        original = self.store._receipt

        def fail_after_receipt(*args, **kwargs):
            original(*args, **kwargs)
            raise sqlite3.OperationalError("injected disk failure")
        with mock.patch.object(self.store, "_receipt", side_effect=fail_after_receipt):
            self.assert_error("preview_storage_unavailable", self.admit, preview, status=503)
        reopened = PreviewStore(self.path)
        self.assertEqual(reopened.get_preview(LOCAL_OWNER, preview["preview_id"]), preview)
        self.assertEqual(reopened.revision_pins(), [])
        self.assertIsNone(reopened.lookup_replay(LOCAL_OWNER, f"preview:{preview['preview_id']}:runs", "run-1", self.payload(preview)))
        with reopened._transaction() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
        first = self.admit(preview)
        self.assertEqual(first["generation"], 1)

    def test_create_sql_failure_is_atomic_and_storage_faults_are_sanitized_503(self):
        with mock.patch.object(self.store, "_receipt", side_effect=sqlite3.OperationalError("private SQL path")):
            error = self.assert_error("preview_storage_unavailable", self.create, status=503)
        self.assertNotIn("private", error.message)
        self.assertEqual(self.store.list_previews(), [])
        with mock.patch("preview_store.sqlite3.connect", side_effect=sqlite3.DatabaseError("private SQL path")):
            self.assert_error("preview_storage_unavailable", self.store.list_previews, status=503)

    def test_retained_preview_limit_counts_closed_and_replay_still_succeeds_at_capacity(self):
        first = self.create()
        self.store.mutate(first["preview_id"], lambda state: state["preview"].update(state="closed"))
        for index in range(1, 128):
            self.create(f"create-{index + 1}")
        self.assertEqual(len(PreviewStore(self.path).list_previews()), 128)
        self.assert_error("preview_quota_exceeded", self.create, "overflow", status=429)
        self.assertEqual(self.create(), first)
        self.assertEqual(self.store.limits()["max_previews"], 128)

    def test_retained_run_limit_keeps_all_pins_receipts_and_terminal_history(self):
        preview = self.create()
        first = None
        for index in range(256):
            run = self.admit(preview, f"run-{index}", generation=index)
            if first is None:
                first = run
        self.assert_error("preview_quota_exceeded", self.admit, preview, "overflow", generation=256, status=429)
        self.assertEqual(len(self.store.revision_pins()), 256)
        reopened = PreviewStore(self.path)
        self.assertEqual(reopened.get_run(LOCAL_OWNER, preview["preview_id"], first["run_id"])["state"], "superseded")
        self.assertEqual(reopened.admit_run(LOCAL_OWNER, preview["preview_id"], "run-0", self.payload(preview)), (first, True))
        self.assertFalse(reopened.limits()["gc_enabled"])

    def test_raw_idempotency_keys_are_not_stored_and_external_results_are_detached(self):
        key = "a-unique-secret-idempotency-header-4674"
        request = {"device_id": "cores3", "nested": {"units": ["relay"]}}
        receipt, _ = self.store.create(LOCAL_OWNER, key, request, {"device_id": "cores3"}, self.expiry)
        original = copy.deepcopy(receipt)
        request["nested"]["units"].clear()
        receipt["nested"] = "caller-only"
        receipt["request"].clear()
        self.assertEqual(self.store.get_preview(LOCAL_OWNER, original["preview_id"]), original)
        replay = self.store.lookup_replay(LOCAL_OWNER, "create-preview", key, original["request"])
        replay["request"].clear()
        self.assertEqual(self.store.lookup_replay(LOCAL_OWNER, "create-preview", key, original["request"]), original)
        with self.store._transaction() as connection:
            dump = "\n".join(connection.iterdump())
        self.assertNotIn(key, dump)
        self.assertNotIn(key.encode(), self.path.read_bytes())

    def test_input_validation_rejects_keys_unknown_fields_nonfinite_timeout_and_invalid_identity(self):
        preview = self.create()
        for key in ("", "has space", "bad\tkey", "中文", "a" * 129, None):
            with self.subTest(key=key):
                self.assert_error("invalid_idempotency_key", self.admit, preview, key, status=400)
        for timeout in (True, 0, .5, 121, 10 ** 1000, float("inf"), float("nan"), "120"):
            with self.subTest(timeout=timeout):
                self.assert_error("invalid_preview_request", self.admit, preview, "invalid-timeout", timeout_seconds=timeout, status=400)
        for changes in ({"unknown": 1}, {"expected_generation": True}, {"revision_id": "f" * 63}, {"client_generation": ""}):
            with self.subTest(changes=changes):
                self.assert_error("invalid_preview_request", self.admit, preview, "invalid-fields", **changes, status=400)
        self.assert_error("preview_not_found", self.store.get_preview, LOCAL_OWNER, "not-id", status=404)
        self.assert_error("invalid_preview_request", self.store.lookup_replay, LOCAL_OWNER, "not-scope", "key", {}, status=400)
        self.assert_error("invalid_preview_request", self.admit, preview, "bad-unicode", client_generation="\ud800", status=400)
        self.assertEqual(self.store.revision_pins(), [])

    def test_reserved_queued_transition_cannot_skip_interrupt_confirmation(self):
        preview = self.create()
        run = self.admit(preview)
        self.store.mutate(preview["preview_id"], lambda state: state["preview"].update(transition_run_id=run["run_id"]))

        def fake_cancel(state):
            state["runs"][run["run_id"]].update(state="cancelled", cancel_intent=True, interrupt_ack="not-required")
            state["preview"]["transition_run_id"] = None
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], fake_cancel, status=409)
        cancelled = self.store.cancel_run(LOCAL_OWNER, preview["preview_id"], run["run_id"], preview["owner_epoch"])
        self.assertEqual(cancelled["state"], "cancelling")
        self.assertEqual(cancelled["interrupt_ack"], "unknown")

    def test_late_terminal_observation_can_be_recorded_without_reviving_execution(self):
        preview = self.create()
        run = self.admit(preview)
        self.store.cancel_run(LOCAL_OWNER, preview["preview_id"], run["run_id"], preview["owner_epoch"])

        def observe(state):
            state["runs"][run["run_id"]]["late_observation"] = {"marker": "START", "execution_id": run["execution_id"]}
            return state["runs"][run["run_id"]]
        result = self.store.mutate(preview["preview_id"], observe)
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["late_observation"]["marker"], "START")
        for terminal_state in ("running", "failed"):
            self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["runs"][run["run_id"]].update(state=terminal_state), status=409)
        self.assertIsNone(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["active_run_id"])

    def test_bound_session_receipt_is_stable_and_cross_preview_pointers_are_rejected(self):
        preview = self.create()
        other = self.create("other")
        run = self.admit(other)
        self.store.mutate(preview["preview_id"], lambda state: state["preview"].update(allocation_state="creating"))
        self.store.mutate(preview["preview_id"], lambda state: state["preview"].update(allocation_state="bound", session_id="a" * 32))
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["preview"].update(session_id="b" * 32), status=409)
        self.assert_error("preview_transition_conflict", self.store.mutate, preview["preview_id"], lambda state: state["preview"].update(desired_run_id=run["run_id"]), status=409)
        self.assertEqual(self.store.get_preview(LOCAL_OWNER, preview["preview_id"])["session_id"], "a" * 32)


if __name__ == "__main__":
    unittest.main()
