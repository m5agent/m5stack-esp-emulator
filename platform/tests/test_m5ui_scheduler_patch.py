"""Execute the pinned SDK event_loop class before and after patch 0026."""

import ast
import builtins
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "platform/tests/fixtures/m5ui_port_upstream"
PATCH = ROOT / "patches/uiflow2-api/0026-m5ui-single-vm-schedule.patch"


class SdkEnvironment:
    """Controlled interfaces; all event_loop logic comes from exact SDK source."""

    def __init__(self, source, *, now=0, immediate=False, fail_create=False):
        self.now = now
        self.ticks = 0
        self.runs = 0
        self.fail_handler = False
        self.on_task = None
        self.created = []
        self.queue = []
        self.queue_limit = 8
        self.lv = types.SimpleNamespace(
            _nesting=types.SimpleNamespace(value=0),
            tick_inc=self.tick_inc,
            task_handler=self.task_handler,
        )
        clock = types.SimpleNamespace(
            ticks_ms=lambda: self.now % 65536,
            ticks_diff=lambda now, before: (now - before + 32768) % 65536 - 32768,
        )
        owner = self

        class Timer:
            PERIODIC = 1

            def __init__(self, identifier, *, mode, period, callback):
                if fail_create:
                    raise RuntimeError("owned-timer-create-failure")
                self.identifier = identifier
                self.mode = mode
                self.period = period
                self.callback = callback
                self.stopped = False
                owner.created.append(self)
                if immediate:
                    callback(self)

            def deinit(self):
                self.stopped = True

        def load_module(name, *args, **kwargs):
            if name != "m5utils":
                raise AssertionError("unexpected SDK class import: " + name)
            return types.SimpleNamespace(Timer=Timer)

        # Exclude unrelated display/SDL initializers, retaining the complete
        # class AST without rewriting any method or substituting a test class.
        tree = ast.parse(source)
        event_loop = next(node for node in tree.body
                          if isinstance(node, ast.ClassDef) and node.name == "event_loop")
        code = ast.fix_missing_locations(ast.Module(body=[event_loop], type_ignores=[]))
        namespace = {
            "__builtins__": dict(vars(builtins), __import__=load_module),
            "lv": self.lv,
            "time": clock,
            "micropython": types.SimpleNamespace(schedule=self.schedule),
        }
        exec(compile(code, "<exact SDK port.py event_loop>", "exec"), namespace)
        self.event_loop = namespace["event_loop"]

    def tick_inc(self, elapsed):
        self.ticks += elapsed

    def task_handler(self):
        self.runs += 1
        if self.on_task:
            self.on_task()
        if self.fail_handler:
            raise RuntimeError("owned-handler-failure")

    def schedule(self, callback, argument):
        if len(self.queue) >= self.queue_limit:
            raise RuntimeError("schedule queue full")
        self.queue.append((callback, argument))

    def drain_one(self):
        callback, argument = self.queue.pop(0)
        callback(argument)

    def fire(self, elapsed):
        self.now += elapsed
        timer = self.created[-1]
        timer.callback(timer)


@unittest.skipUnless(shutil.which("git"), "git required to apply exact SDK patch")
class M5uiSchedulerPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        work = Path(cls.temporary.name)
        upstream = json.loads((FIXTURE / "source.json").read_text())
        patch_manifest = json.loads(PATCH.with_suffix(".json").read_text())
        if upstream["upstream_commit"] != patch_manifest["upstream_commit"]:
            raise AssertionError("SDK patch and test source commits differ")
        for filename, metadata in upstream["files"].items():
            digest = hashlib.sha256((FIXTURE / filename).read_bytes()).hexdigest()
            if digest != metadata["sha256"]:
                raise AssertionError("modified upstream fixture: " + filename)
        before = (FIXTURE / "port.py").read_bytes()
        if hashlib.sha256(before).hexdigest() != patch_manifest["preimage_sha256"]:
            raise AssertionError("SDK patch preimage hash mismatch")
        source = work / patch_manifest["path"]
        source.parent.mkdir(parents=True)
        source.write_bytes(before)
        for arguments in (("--check",), (), ("--reverse", "--check")):
            subprocess.run(["git", "apply", *arguments, str(PATCH)], cwd=work,
                           check=True, capture_output=True)
        after = source.read_bytes()
        if hashlib.sha256(after).hexdigest() != patch_manifest["candidate_sha256"]:
            raise AssertionError("SDK patch candidate hash mismatch")
        cls.preimage = before.decode("utf-8")
        cls.candidate = after.decode("utf-8")

    def test_delayed_callback_keeps_elapsed_ticks_without_second_queue(self):
        env = SdkEnvironment(self.candidate)
        loop = env.event_loop()
        env.fire(300)
        self.assertEqual((env.ticks, env.runs, loop.scheduled, env.queue), (300, 1, 0, []))
        stock = SdkEnvironment(self.preimage)
        stock.event_loop()
        stock.fire(300)
        self.assertEqual((stock.ticks, stock.runs, len(stock.queue)), (30, 0, 1))
        stock.drain_one()
        self.assertEqual(stock.runs, 1)

    def test_clock_wrap_and_lvgl_nesting_preserve_elapsed_time(self):
        env = SdkEnvironment(self.candidate, now=65520)
        loop = env.event_loop()
        env.lv._nesting.value = 1
        env.fire(36)
        self.assertEqual((env.ticks, env.runs), (36, 0))
        env.lv._nesting.value = 0
        env.fire(30)
        self.assertEqual((env.ticks, env.runs, loop.scheduled), (66, 1, 0))

    def test_handler_exception_releases_guard_and_remains_visible(self):
        env = SdkEnvironment(self.candidate)
        loop = env.event_loop()
        env.fail_handler = True
        with self.assertRaisesRegex(RuntimeError, "owned-handler-failure"):
            env.fire(90)
        self.assertEqual(loop.scheduled, 0)
        env.fail_handler = False
        env.fire(30)
        self.assertEqual((env.ticks, env.runs), (120, 2))
        stock = SdkEnvironment(self.preimage)
        old = stock.event_loop()
        stock.fail_handler = True
        stock.fire(90)
        with self.assertRaisesRegex(RuntimeError, "owned-handler-failure"):
            stock.drain_one()
        self.assertEqual(old.scheduled, 1)

    def test_timer_can_fire_during_construction_and_state_is_observable(self):
        env = SdkEnvironment(self.candidate, immediate=True)
        self.assertFalse(env.event_loop.is_initialized())
        loop = env.event_loop()
        self.assertEqual((env.runs, loop.scheduled), (1, 0))
        self.assertIs(loop, env.event_loop())
        self.assertEqual(len(env.created), 1)
        self.assertTrue(env.event_loop.is_initialized())
        stock = SdkEnvironment(self.preimage, immediate=True)
        with self.assertRaises(AttributeError):
            stock.event_loop()

    def test_deinit_makes_owned_old_callback_inert_for_new_loop(self):
        env = SdkEnvironment(self.candidate)
        old = env.event_loop()
        callback = env.created[0].callback
        old.deinit()
        self.assertTrue(env.created[0].stopped)
        self.assertFalse(env.event_loop.is_initialized())
        new = env.event_loop()
        env.now += 100
        callback(None)
        self.assertEqual((env.ticks, env.runs, env.queue), (0, 0, []))
        self.assertIsNot(old, new)
        self.assertTrue(env.event_loop.is_initialized())
        stock = SdkEnvironment(self.preimage)
        old = stock.event_loop()
        callback = stock.created[0].callback
        old.deinit()
        callback(None)
        self.assertEqual((stock.ticks, len(stock.queue)), (30, 1))

    def test_reentrant_handler_is_neither_queued_nor_executed_twice(self):
        env = SdkEnvironment(self.candidate)
        loop = env.event_loop()
        env.on_task = lambda: loop.timer_cb(None)
        env.fire(30)
        self.assertEqual((env.runs, loop.scheduled, env.queue), (1, 0, []))

    def test_timer_creation_failure_does_not_publish_initialized_singleton(self):
        env = SdkEnvironment(self.candidate, fail_create=True)
        with self.assertRaisesRegex(RuntimeError, "owned-timer-create-failure"):
            env.event_loop()
        self.assertIsNone(env.event_loop._instance)
        self.assertFalse(env.event_loop.is_initialized())
        stock = SdkEnvironment(self.preimage, fail_create=True)
        with self.assertRaisesRegex(RuntimeError, "owned-timer-create-failure"):
            stock.event_loop()
        self.assertIsNotNone(stock.event_loop._instance)
        self.assertTrue(stock.event_loop._instance._initialized)

    def test_full_existing_vm_queue_does_not_require_second_enqueue(self):
        env = SdkEnvironment(self.candidate)
        loop = env.event_loop()
        env.queue = [(lambda unused: None, None)] * env.queue_limit
        env.fire(30)
        self.assertEqual((env.runs, loop.scheduled, len(env.queue)), (1, 0, env.queue_limit))
        stock = SdkEnvironment(self.preimage)
        stock.event_loop()
        stock.queue = [(lambda unused: None, None)] * stock.queue_limit
        with self.assertRaisesRegex(RuntimeError, "schedule queue full"):
            stock.fire(30)


if __name__ == "__main__":
    unittest.main()
