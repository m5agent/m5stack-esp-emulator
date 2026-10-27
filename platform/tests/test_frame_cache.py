"""Deterministic capture sharing/lifecycle tests; no service or guest process."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from frame_cache import CaptureResult, FrameCache, FrameGenerationChanged


class FrameCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.cache = FrameCache(monotonic=lambda: self.now, utcnow=lambda: "2026-10-26T01:02:03+00:00")
        self.calls = 0
        self.threads = []
        self.releases = []

    def tearDown(self):
        for release in self.releases:
            release.set()
        for thread in self.threads:
            thread.join(2)
            self.assertFalse(thread.is_alive(), "capture fixture left a thread running")

    def capture(self):
        self.calls += 1
        return CaptureResult(b"png-sample", 320, 240, nonblack_pixels=100, unique_colors=3)

    def background(self, operation):
        result = {}
        done = threading.Event()

        def run():
            try:
                result["value"] = operation()
            except BaseException as error:
                result["error"] = error
            finally:
                done.set()

        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()
        return result, done

    def barrier_capture(self, result=None, error=None):
        entered, release = threading.Event(), threading.Event()
        self.releases.append(release)

        def capture():
            self.calls += 1
            entered.set()
            if not release.wait(2):
                raise AssertionError("capture fixture not released")
            if error is not None:
                raise error
            return result or CaptureResult(b"delayed-png", 2, 3)

        return capture, entered, release

    def test_default_is_fresh_and_equal_content_keeps_distinct_capture_identity(self):
        a = self.cache.get(self.capture, generation=("session", 1))
        b = self.cache.get(self.capture, generation=("session", 1))
        self.assertEqual(self.calls, 2)
        self.assertEqual((a.capture_seq, b.capture_seq), (1, 2))
        self.assertEqual(a.sha256, b.sha256)
        self.assertEqual(a.sha256, hashlib.sha256(a.png).hexdigest())
        self.assertEqual(a.captured_at, "2026-10-26T01:02:03+00:00")

    def test_ttl_is_bounded_by_capture_completion_and_does_not_refresh_timestamp(self):
        def slow_source():
            self.now += 10
            return self.capture()

        a = self.cache.get(slow_source, generation=1, max_age_ms=125)
        self.now += 0.1
        b = self.cache.get(self.capture, generation=1, max_age_ms=125)
        self.assertIs(a, b)
        self.assertEqual(self.calls, 1)
        self.now += 0.026
        c = self.cache.get(self.capture, generation=1, max_age_ms=125)
        self.assertEqual(self.calls, 2)
        self.assertEqual(c.capture_seq, 2)

    def test_source_sample_time_prevents_slow_png_encoding_from_extending_ttl(self):
        def encoded_source():
            observed = self.now
            self.now += 1
            self.calls += 1
            return CaptureResult(b"slow-png", 1, 1, captured_monotonic=observed)

        a = self.cache.get(encoded_source, generation=1, max_age_ms=125)
        b = self.cache.get(self.capture, generation=1, max_age_ms=125)
        self.assertEqual(self.calls, 2)
        self.assertEqual((a.capture_seq, b.capture_seq), (1, 2))
        self.assertNotIn("captured_monotonic", a.as_dict())

    def test_persisted_source_does_not_reuse_a_foreign_monotonic_clock(self):
        self.cache.get(
            lambda: CaptureResult(b"old", 1, 1, "persisted", captured_monotonic=-1000),
            generation=1, max_age_ms=125,
        )
        self.cache.get(self.capture, generation=1, max_age_ms=125)
        self.assertEqual(self.calls, 0)

    def test_source_timestamp_and_persisted_unknown_time_are_preserved(self):
        old = "2020-01-02T00:00:00+00:00"
        a = self.cache.get(lambda: CaptureResult(b"old", 1, 1, "persisted", old), generation=1)
        b = self.cache.get(lambda: CaptureResult(b"legacy", 1, 1, "persisted"), generation=1)
        c = self.cache.get(lambda: CaptureResult(b"new", 1, 1, "live", old), generation=1)
        self.assertEqual(a.captured_at, old)
        self.assertIsNone(b.captured_at)
        self.assertEqual(c.captured_at, old)
        self.assertEqual(a.source, "persisted")

    def test_result_and_metrics_cannot_mutate_cached_png_or_metadata(self):
        source = bytearray(b"one")
        a = self.cache.get(lambda: CaptureResult(source, 1, 1), generation=1, max_age_ms=125)
        source[:] = b"two"
        metrics = a.as_dict()
        metrics["png"] = b"other"
        metrics["width"] = 200
        self.assertEqual(a.png, b"one")
        self.assertEqual(a.width, 1)
        with self.assertRaises(FrozenInstanceError):
            a.width = 200
        self.assertIs(self.cache.get(self.capture, generation=1, max_age_ms=125), a)

    def test_cache_preserves_capture_program_identity_without_relabelling_pixels(self):
        def source():
            return CaptureResult(
                b"one", 1, 1, execution_id="execution-A", revision_id="revision-A",
                program_state="running",
            )

        a = self.cache.get(source, generation="A", max_age_ms=125)
        b = self.cache.get(self.capture, generation="A", max_age_ms=125)
        self.assertIs(a, b)
        self.assertEqual(b.execution_id, "execution-A")
        self.assertEqual(b.as_dict()["revision_id"], "revision-A")
        self.assertEqual(b.program_state, "running")
        legacy = self.cache.get(lambda: CaptureResult(b"old", 1, 1, "persisted"), generation="B")
        self.assertIsNone(legacy.execution_id)
        self.assertIsNone(legacy.as_dict()["revision_id"])

    def test_generation_change_and_explicit_invalidation_prevent_reuse(self):
        a = self.cache.get(self.capture, generation=(1, "A"), max_age_ms=125)
        b = self.cache.get(self.capture, generation=(1, "B"), max_age_ms=125)
        self.cache.invalidate()
        c = self.cache.get(self.capture, generation=(1, "B"), max_age_ms=125)
        self.assertEqual(self.calls, 3)
        self.assertEqual([a.capture_seq, b.capture_seq, c.capture_seq], [1, 2, 3])

    def test_concurrent_preview_observers_share_one_capture(self):
        source, entered, release = self.barrier_capture()
        first, first_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125))
        self.assertTrue(entered.wait(1))
        checking = threading.Event()

        def current(value):
            checking.set()
            return value == 1

        second, second_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125, is_current=current))
        self.assertTrue(checking.wait(1))
        release.set()
        self.assertTrue(first_done.wait(1))
        self.assertTrue(second_done.wait(1))
        self.assertNotIn("error", first)
        self.assertNotIn("error", second)
        self.assertIs(first["value"], second["value"])
        self.assertEqual(self.calls, 1)

    def test_zero_age_waiter_does_its_own_capture(self):
        source, entered, release = self.barrier_capture()
        first, first_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125))
        self.assertTrue(entered.wait(1))
        second, second_done = self.background(lambda: self.cache.get(self.capture, generation=1))
        release.set()
        self.assertTrue(first_done.wait(1))
        self.assertTrue(second_done.wait(1))
        self.assertEqual(self.calls, 2)
        self.assertEqual((first["value"].capture_seq, second["value"].capture_seq), (1, 2))

    def test_capture_error_invalidates_old_success_and_later_request_can_retry(self):
        self.cache.get(self.capture, generation=1, max_age_ms=125)

        def fail():
            raise RuntimeError("QMP timed out")

        with self.assertRaisesRegex(RuntimeError, "QMP timed out"):
            self.cache.get(fail, generation=1)
        self.cache.get(self.capture, generation=1, max_age_ms=125)
        self.assertEqual(self.calls, 2, "capture failure must discard the prior fresh cache")

    def test_joined_observer_receives_capture_error_without_an_implicit_retry(self):
        source, entered, release = self.barrier_capture(error=RuntimeError("source failed"))
        first, first_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125))
        self.assertTrue(entered.wait(1))
        waiting = threading.Event()
        original_wait = self.cache._condition.wait

        def wait(timeout=None):
            waiting.set()
            return original_wait(timeout)

        self.cache._condition.wait = wait
        second, second_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125))
        self.assertTrue(waiting.wait(1))
        release.set()
        self.assertTrue(first_done.wait(1))
        self.assertTrue(second_done.wait(1))
        self.assertIsInstance(first.get("error"), RuntimeError)
        self.assertIsInstance(second.get("error"), RuntimeError)
        self.assertEqual(str(second["error"]), "source failed")
        self.assertEqual(self.calls, 1)

    def test_invalidation_during_capture_fences_owner_and_joined_observer(self):
        source, entered, release = self.barrier_capture()
        first, first_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125))
        self.assertTrue(entered.wait(1))
        waiting = threading.Event()
        original_wait = self.cache._condition.wait

        def wait(timeout=None):
            waiting.set()
            return original_wait(timeout)

        self.cache._condition.wait = wait
        second, second_done = self.background(lambda: self.cache.get(source, generation=1, max_age_ms=125))
        self.assertTrue(waiting.wait(1))
        self.cache.invalidate()
        release.set()
        self.assertTrue(first_done.wait(1))
        self.assertTrue(second_done.wait(1))
        self.assertIsInstance(first.get("error"), FrameGenerationChanged)
        self.assertIsInstance(second.get("error"), FrameGenerationChanged)
        a = self.cache.get(self.capture, generation=2, max_age_ms=125)
        self.assertEqual(a.generation, 2)

    def test_external_generation_change_during_capture_does_not_publish(self):
        current = [1]

        def source():
            current[0] = 2
            return self.capture()

        with self.assertRaises(FrameGenerationChanged):
            self.cache.get(source, generation=1, max_age_ms=125, is_current=lambda value: value == current[0])
        a = self.cache.get(self.capture, generation=2, max_age_ms=125)
        self.assertEqual(a.capture_seq, 1)
        self.assertEqual(self.calls, 2)

    def test_stale_generation_before_get_never_invokes_source(self):
        self.cache.invalidate()
        with self.assertRaises(FrameGenerationChanged):
            self.cache.get(self.capture, generation=1, is_current=lambda generation: generation == 2)
        self.assertEqual(self.calls, 0)

    def test_generation_change_between_initial_validation_and_cache_entry_is_rechecked(self):
        current = [1]
        checks = []

        def is_current(generation):
            checks.append(generation)
            answer = generation == current[0]
            if len(checks) == 1:
                current[0] = 2
                self.cache.invalidate()
            return answer

        with self.assertRaises(FrameGenerationChanged):
            self.cache.get(self.capture, generation=1, max_age_ms=125, is_current=is_current)
        self.assertGreaterEqual(len(checks), 2)
        self.assertEqual(self.calls, 0)

    def test_callbacks_run_without_cache_lock_and_can_invalidate(self):
        def current(generation):
            done = threading.Event()
            task = threading.Thread(target=lambda: (self.cache.invalidate(), done.set()), daemon=True)
            self.threads.append(task)
            task.start()
            if not done.wait(1):
                raise AssertionError("is_current was called with cache lock held")
            return False

        with self.assertRaises(FrameGenerationChanged):
            self.cache.get(self.capture, generation=1, is_current=current)
        source, entered, release = self.barrier_capture()
        first, first_done = self.background(lambda: self.cache.get(source, generation=1))
        self.assertTrue(entered.wait(1))
        self.cache.invalidate()
        release.set()
        self.assertTrue(first_done.wait(1))
        self.assertIsInstance(first.get("error"), FrameGenerationChanged)

    def test_separate_sessions_have_independent_capture_ownership(self):
        source, entered, release = self.barrier_capture()
        first, first_done = self.background(lambda: self.cache.get(source, generation=1))
        self.assertTrue(entered.wait(1))
        other = FrameCache()
        second, second_done = self.background(lambda: other.get(self.capture, generation=1))
        self.assertTrue(second_done.wait(1))
        self.assertIn("value", second)
        self.assertFalse(first_done.is_set())
        release.set()
        self.assertTrue(first_done.wait(1))

    def test_invalid_ttl_and_capture_inputs_fail_closed(self):
        for age in (-1, 1001, 10 ** 5000, float("nan"), float("inf"), True, "125", None):
            with self.subTest(age=age), self.assertRaises(ValueError):
                self.cache.get(self.capture, generation=1, max_age_ms=age)
        for result in ({}, CaptureResult(b"", 1, 1), CaptureResult(b"a", 0, 1), CaptureResult(b"a", True, 1), CaptureResult(b"a", 1, 1, source="cache"), CaptureResult(b"a", 1, 1, captured_monotonic=float("nan")), CaptureResult(b"a", 1, 1, captured_monotonic=True)):
            with self.subTest(result=result), self.assertRaises((TypeError, ValueError)):
                self.cache.get(lambda: result, generation=1)


if __name__ == "__main__":
    unittest.main()
