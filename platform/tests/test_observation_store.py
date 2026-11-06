"""Observation ordering/retention and real DeviceSession cleanup integration.

Host contracts only: these tests do not execute firmware.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from device_service import DeviceService, DeviceSession
from observation_store import ObservationStore
from serve import Handler


def row(session_id="short", state="provisioning", **extra):
    return {"session_id": session_id, "device_id": "cores3", "state": state,
            "created_at": "2026-11-06T00:00:00Z", "completed_at": None,
            "firmware_sha256": "a" * 64, "serial_bytes": 0, **extra}


class ObservationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "observations.sqlite"
        self.store = ObservationStore(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_short_session_is_replayed_after_purge_and_restart(self):
        initial = self.store.snapshot()
        for state in ("provisioning", "booting", "stopped"):
            self.store.record(row(state=state))
        self.store.record(row(state="stopped", purged=True, serial_bytes=89))
        self.store.close()
        self.store = ObservationStore(self.path)
        events = self.store.events(journal_id=initial["journal_id"], after=initial["cursor"])
        self.assertFalse(events["resync"])
        self.assertEqual([event["session"]["state"] for event in events["events"]],
                         ["provisioning", "booting", "stopped", "stopped"])
        last = self.store.snapshot()
        self.assertFalse(last["active"])
        self.assertTrue(last["recent"][0]["purged"])
        self.assertIn("observed_at", last["recent"][0])

    def test_pagination_deduplication_and_epoch_fences(self):
        self.store.record(row())
        first = self.store.snapshot()
        self.store.record(row())
        self.assertEqual(self.store.snapshot()["cursor"], first["cursor"])
        self.store.record(row(state="running"))
        self.store.record(row(state="stopped"))
        page = self.store.events(journal_id=first["journal_id"], after=0, limit=2)
        self.assertTrue(page["has_more"])
        tail = self.store.events(journal_id=first["journal_id"], after=page["next_cursor"], limit=2)
        self.assertFalse(tail["has_more"])
        self.assertEqual(len(tail["events"]), 1)
        for epoch, after in (("old", 0), (first["journal_id"], 999)):
            self.assertTrue(self.store.events(journal_id=epoch, after=after)["resync"])
        with self.assertRaises(ValueError):
            self.store.events(journal_id=first["journal_id"], after=-1)

    def test_retention_pins_active_and_reports_cursor_gap(self):
        self.store.close()
        now = [0.0]
        self.store = ObservationStore(self.path, retention_seconds=10, max_recent=1,
                                      max_events=2, clock=lambda: now[0])
        self.store.record(row("active"))
        before = self.store.snapshot()
        self.store.record(row("old", "stopped"))
        self.store.record(row("new", "stopped"))
        self.assertEqual([r["session_id"] for r in self.store.snapshot()["recent"]], ["new"])
        self.assertTrue(self.store.events(journal_id=before["journal_id"], after=0)["resync"])
        now[0] = 20
        snapshot = self.store.snapshot()
        self.assertEqual([r["session_id"] for r in snapshot["active"]], ["active"])
        self.assertFalse(snapshot["recent"])

    def test_projection_contains_no_guest_content_and_purge_is_monotonic(self):
        self.store.record(row(state="stopped", purged=True, program={"source": "secret"},
                              serial="secret", runtime_env={"TOKEN": "secret"},
                              units=[{"id": "u", "unit_id": "pir", "port_id": "grove", "visual_port": "PORTA", "values": {"secret": 1}}]))
        units = self.store.snapshot()["recent"][0]["units"]
        self.assertEqual(units, [{"id": "u", "unit_id": "pir", "port_id": "grove", "visual_port": "PORTA"}])
        self.store.record(row(state="stopped", purged=False, last_frame_available=True))
        item = self.store.snapshot()["recent"][0]
        self.assertNotIn("secret", json.dumps(item))
        self.assertTrue(item["purged"])
        self.assertFalse(item["last_frame_available"])

    def test_atomic_snapshot_watermark_during_writes(self):
        failures = []
        def writer():
            for index in range(50):
                if not self.store.record(row(str(index))):
                    failures.append(index)
        thread = threading.Thread(target=writer)
        thread.start()
        while thread.is_alive():
            snapshot = self.store.snapshot()
            events = self.store.events(journal_id=snapshot["journal_id"], after=0, limit=500)
            seen = {event["session"]["session_id"] for event in events["events"]
                    if event["seq"] <= snapshot["cursor"]}
            self.assertEqual(seen, {item["session_id"] for item in snapshot["active"]})
        thread.join()
        self.assertFalse(failures)

    def test_database_failure_is_visible_and_restart_changes_epoch(self):
        epoch = self.store.snapshot()["journal_id"]
        self.store._connection.close()
        self.assertFalse(self.store.record(row()))
        self.assertEqual(self.store.snapshot()["status"]["state"], "degraded")
        self.store._connection = None
        self.store = ObservationStore(self.path)
        snapshot = self.store.snapshot()
        self.assertTrue(snapshot["status"]["gap_possible"])
        self.assertNotEqual(snapshot["journal_id"], epoch)
        self.assertTrue(self.store.events(journal_id=epoch, after=0)["resync"])


class ObservationServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = DeviceService(state_dir=self.root)

    def tearDown(self):
        self.service.close_all()
        self.tmp.cleanup()

    def session(self, session_id="session-test"):
        session = DeviceSession(self.service, session_id=session_id,
            spec=self.service.specs["cores3"], firmware_id="reference", firmware_path=self.root / "firmware.bin",
            firmware_sha="a" * 64, firmware_source="test", source_artifacts=[], ttl_seconds=600,
            ready_marker=None, ready_timeout=1, ready_conditions=None)
        self.service._sessions[session.id] = session
        session._observation_registered = True
        self.service._observe_session(session)
        return session

    def test_stop_purge_without_observer_keeps_metadata_and_no_contents(self):
        before = self.service.observatory_snapshot()
        session = self.session()
        session._set_state("booting")
        session.serial0.write_text("private guest serial\n")
        result = self.service.delete_session(session.id, purge=True)
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(session.dir.exists())
        replay = self.service.observatory_events(journal_id=before["journal_id"], after=before["cursor"])
        self.assertGreaterEqual(len(replay["events"]), 3)
        terminal = replay["events"][-1]["session"]
        self.assertTrue(terminal["purged"])
        self.assertEqual(terminal["serial_bytes"], len("private guest serial\n"))
        self.assertNotIn("private guest serial", json.dumps(replay))

    def test_bulk_and_orphan_purge_keep_display_traces(self):
        one = self.session("one")
        one.stop()
        orphan = self.session("orphan")
        orphan.stop()
        self.service._sessions.pop(orphan.id)
        self.service.clear_stopped(purge=True)
        records = self.service.observatory_snapshot()["recent"]
        self.assertEqual({item["session_id"] for item in records}, {"one", "orphan"})
        self.assertTrue(all(item["purged"] for item in records))

    def test_direct_purge_poll_cannot_erase_final_serial_count(self):
        session = self.session()
        session.serial0.write_text("three")
        session.stop(purge=True)
        # Direct session owners may purge before the service janitor removes
        # the in-memory object, so the next snapshot sees missing disk files.
        snapshot = self.service.observatory_snapshot()
        self.assertEqual(snapshot["recent"][0]["serial_bytes"], 5)
        self.assertTrue(snapshot["recent"][0]["purged"])

    def test_observation_failure_never_prevents_guest_stop_and_purge(self):
        session = self.session()
        with mock.patch.object(self.service._observations, "record", side_effect=sqlite3.DatabaseError("disk full")):
            result = self.service.delete_session(session.id, purge=True)
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(session.dir.exists())
        self.assertFalse(self.service.observatory_snapshot()["status"]["available"])

    def test_storage_retention_purge_keeps_terminal_trace(self):
        session = self.session()
        session.stop()
        self.service.storage_policy = replace(self.service.storage_policy, history_ttl_seconds=1)
        self.service.prune_storage(include_cache=False, now=10**12)
        self.assertFalse(session.dir.exists())
        self.assertTrue(self.service.observatory_snapshot()["recent"][0]["purged"])

    def test_job_counts_come_from_full_queue_counts_not_limited_rows(self):
        with mock.patch.object(self.service.worker_queue, "list_jobs", return_value={
            "jobs": [{"status": "queued"}], "job_count": 501,
            "counts": {"queued": 350, "leased": 101, "completed": 50},
        }):
            jobs = self.service.observatory_snapshot()["jobs"]
        self.assertEqual(jobs["job_count"], 501)
        self.assertEqual(jobs["counts"]["queued"], 350)
        self.assertEqual(jobs["counts"]["running"], 101)

    def test_recovery_does_not_restart_missing_guest_or_lose_purged_record(self):
        session = self.session()
        self.service.delete_session(session.id, purge=True)
        self.service._observations.record(row("missing", "running"))
        self.service.close_all()
        self.service = DeviceService(state_dir=self.root)
        snapshot = self.service.observatory_snapshot()
        self.assertFalse(snapshot["active"])
        indexed = {item["session_id"]: item for item in snapshot["recent"]}
        self.assertTrue(indexed[session.id]["purged"])
        self.assertEqual(indexed["missing"]["state"], "unknown")
        self.assertFalse(self.service._sessions)

    def test_http_observer_auth_validation_and_read_only_routes(self):
        service = self.service
        class TestHandler(Handler):
            api_token = "observer-test"
            previous_api_token = "old-observer-test"
            def log_message(self, *args):
                pass
        TestHandler.service = service
        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/api/v1/observatory/snapshot"
            with self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 401)
            for token in ("observer-test", "old-observer-test"):
                with urlopen(Request(url, headers={"Authorization": f"Bearer {token}"})) as response:
                    snapshot = json.load(response)
                    self.assertIn("server_time", snapshot)
                    self.assertIn("jobs", snapshot)
            events_url = url.replace("snapshot", "events")
            with urlopen(Request(events_url + f"?journal_id={snapshot['journal_id']}&after={snapshot['cursor']}",
                                 headers={"Authorization": "Bearer observer-test"})) as response:
                self.assertFalse(json.load(response)["resync"])
            for alias in ("/observatory", "/observatory/", "/observatory.html"):
                with urlopen(f"http://127.0.0.1:{server.server_port}{alias}") as response:
                    self.assertEqual(response.read(), (ROOT / "platform/web/observatory.html").read_bytes())
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(events_url + "?after=bad", headers={"Authorization": "Bearer observer-test"}))
            self.assertEqual(error.exception.code, 400)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(url, data=b"{}", headers={"Authorization": "Bearer observer-test", "Content-Type": "application/json"}))
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
