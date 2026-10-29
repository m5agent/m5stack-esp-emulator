"""Explicit Python-only SDK candidate; display/input drivers remain unchanged.

The FreeRTOS m5utils.Timer still schedules this callback. It already runs in
MicroPython's VM, so a second micropython.schedule only adds queue pressure.
This candidate does not add C Timer callback coalescing or change VM clocks.
"""

import lvgl as lv
import time


CANDIDATE = "sdk-python-single-schedule-v1"


class event_loop:
    _instance = None
    _initialized = False

    def __new__(cls, freq=33, max_scheduled=2):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, freq=33, max_scheduled=2):
        if self._initialized:
            return
        if freq < 1 or freq > 1000 or max_scheduled < 1:
            raise ValueError("invalid LVGL event-loop frequency or queue limit")
        self.delay = 1000 // freq
        self.max_scheduled = max_scheduled
        self.scheduled = 0
        self.timer_callbacks = 0
        self.task_runs = 0
        self.exceptions = 0
        self.nesting_skips = 0
        self.tick_total = 0
        self.started_ms = time.ticks_ms()
        self.last_tick_ms = self.started_ms
        self._initialized = True
        import m5utils

        try:
            self.timer = m5utils.Timer(
                0, mode=m5utils.Timer.PERIODIC, period=self.delay, callback=self.timer_cb
            )
        except Exception:
            self._initialized = False
            event_loop._instance = None
            raise

    def timer_cb(self, timer):
        if not self._initialized:
            return
        self.timer_callbacks += 1
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self.last_tick_ms)
        # ticks_diff handles the guest's monotonic-clock wrap. Delayed or
        # dropped timer callbacks must not discard elapsed guest time.
        if elapsed > 0:
            lv.tick_inc(elapsed)
            self.tick_total += elapsed
            self.last_tick_ms = now
        self.task_handler(None)

    def task_handler(self, unused):
        if not self._initialized:
            return
        if self.scheduled or lv._nesting.value:
            self.nesting_skips += 1
            return
        self.scheduled = 1
        try:
            self.task_runs += 1
            lv.task_handler()
        except Exception:
            self.exceptions += 1
            print("CORES3_WALLCLOCK_SCHEDULER_ERROR")
            raise
        finally:
            self.scheduled = 0

    def deinit(self):
        self._initialized = False
        if hasattr(self, "timer"):
            self.timer.deinit()
        # Queued callbacks retain their owned instance and become no-ops.
        event_loop._initialized = False
        event_loop._instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def is_initialized(cls):
        return cls._instance is not None and cls._instance._initialized
