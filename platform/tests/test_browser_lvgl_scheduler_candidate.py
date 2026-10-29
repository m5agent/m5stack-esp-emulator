"""Exercise the explicit guest Python candidate, not a simulated firmware PASS."""

import builtins
from pathlib import Path
import types
import unittest


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "tests/browser-qemu/cores3_lvgl_wallclock/candidate_lvgl_loop.py"


class CandidateEnvironment:
    def __init__(self, now=0, fire_on_create=False):
        self.now = now
        self.period = 1 << 16
        self.ticks = 0
        self.runs = 0
        self.fail = False
        self.on_task = None
        self.created = []
        self.lv = types.SimpleNamespace(_nesting=types.SimpleNamespace(value=0))
        self.lv.tick_inc = self.tick_inc
        self.lv.task_handler = self.task_handler
        self.time = types.SimpleNamespace(ticks_ms=lambda: self.now % self.period,
                                         ticks_diff=self.ticks_diff)
        owner = self

        class Timer:
            PERIODIC = 1

            def __init__(self, identifier, *, mode, period, callback):
                self.identifier, self.mode, self.period, self.callback = identifier, mode, period, callback
                self.stopped = False
                owner.created.append(self)
                if fire_on_create:
                    callback(self)

            def deinit(self):
                self.stopped = True

        modules = {"lvgl": self.lv, "time": self.time,
                   "m5utils": types.SimpleNamespace(Timer=Timer)}

        def load_module(name, *args, **kwargs):
            return modules[name]

        namespace = {"__builtins__": dict(vars(builtins), __import__=load_module)}
        exec(compile(CANDIDATE.read_text(), str(CANDIDATE), "exec"), namespace)
        self.event_loop = namespace["event_loop"]

    def ticks_diff(self, now, before):
        return (now - before + self.period // 2) % self.period - self.period // 2

    def tick_inc(self, elapsed):
        self.ticks += elapsed

    def task_handler(self):
        self.runs += 1
        if self.on_task:
            self.on_task()
        if self.fail:
            raise RuntimeError("owned-handler-failure")

    def fire(self, advance):
        self.now += advance
        self.created[-1].callback(self.created[-1])


class BrowserLvglSchedulerCandidateTests(unittest.TestCase):
    def test_delayed_callback_keeps_elapsed_ticks_and_uses_one_vm_callback(self):
        env = CandidateEnvironment()
        loop = env.event_loop()
        self.assertEqual(env.created[0].period, 30)
        env.fire(300)
        self.assertEqual((env.ticks, loop.tick_total, env.runs, loop.scheduled), (300, 300, 1, 0))
        env.fire(2)
        self.assertEqual((env.ticks, env.runs), (302, 2))

    def test_guest_ticks_wrap_and_nesting_do_not_discard_time(self):
        env = CandidateEnvironment(now=65520)
        loop = env.event_loop()
        env.lv._nesting.value = 1
        env.fire(36)
        self.assertEqual((env.ticks, env.runs, loop.nesting_skips), (36, 0, 1))
        env.lv._nesting.value = 0
        env.fire(30)
        self.assertEqual((env.ticks, env.runs, loop.scheduled), (66, 1, 0))

    def test_handler_exception_releases_counter_and_is_not_silenced(self):
        env = CandidateEnvironment()
        loop = env.event_loop()
        env.fail = True
        with self.assertRaisesRegex(RuntimeError, "owned-handler-failure"):
            env.fire(90)
        self.assertEqual((loop.scheduled, loop.exceptions, env.ticks), (0, 1, 90))
        env.fail = False
        env.fire(30)
        self.assertEqual((loop.scheduled, env.runs, env.ticks), (0, 2, 120))

    def test_initialization_is_ready_before_timer_can_fire(self):
        env = CandidateEnvironment(fire_on_create=True)
        loop = env.event_loop()
        self.assertEqual((env.runs, loop.scheduled), (1, 0))
        self.assertIs(loop, env.event_loop())
        self.assertEqual(len(env.created), 1)

    def test_owned_callback_after_deinit_cannot_touch_lvgl_or_new_loop(self):
        env = CandidateEnvironment()
        first = env.event_loop()
        old_callback = env.created[0].callback
        first.deinit()
        self.assertTrue(env.created[0].stopped)
        second = env.event_loop()
        env.now += 100
        old_callback(None)
        self.assertEqual((env.ticks, env.runs), (0, 0))
        self.assertIsNot(first, second)
        self.assertTrue(env.event_loop.is_initialized())

    def test_reentrant_handler_is_not_queued_or_run_twice(self):
        env = CandidateEnvironment()
        loop = env.event_loop()
        env.on_task = lambda: loop.timer_cb(None)
        env.fire(30)
        self.assertEqual((env.runs, loop.scheduled, loop.nesting_skips), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
