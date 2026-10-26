#!/usr/bin/env python3
"""Offline demonstration of the exact downloaded Haptic/SoftTimer sources.

No real PWM, threads, clock, network, Device Service, firmware, or QEMU is used.
The upstream source files are loaded unchanged, with fake dependency modules.
"""

import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True

BASE = Path(__file__).resolve().parent
SOURCE_PATHS = {
    "soft_timer": BASE / "soft_timer-50e4407-verified.py",
    "haptic": BASE / "haptic-50e4407-verified.py",
}
EXPECTED_SHA256 = {
    "soft_timer": "5d8e81fae4fd41754f174671e4259572ba90535aa7d0ea28dc7f4afd5e788e83",
    "haptic": "a443d3d947c9821208d3eac4835e0ef8e475c5cc54e0619ef159971b78e70148",
}


class FakePWM:
    def __init__(self, pin, *, freq, duty_u16):
        self.pin = pin
        self.frequency = freq
        self.duty = duty_u16
        self.calls = [["construct", pin, freq, duty_u16]]

    def init(self, *, freq, duty_u16):
        self.frequency = freq
        self.duty = duty_u16
        self.calls.append(["init", freq, duty_u16])

    def duty_u16(self, value=None):
        if value is None:
            return self.duty
        self.duty = value
        self.calls.append(["duty_u16", value])

    def freq(self, value=None):
        if value is None:
            return self.frequency
        self.frequency = value
        self.calls.append(["freq", value])

    def deinit(self):
        self.calls.append(["deinit"])


@contextlib.contextmanager
def substitute_modules(replacements):
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in replacements}
    sys.modules.update(replacements)
    try:
        yield
    finally:
        for name, module in previous.items():
            if module is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_exact(name):
    full_name = f"exact_driver.{name}"
    spec = importlib.util.spec_from_file_location(full_name, SOURCE_PATHS[name])
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    source_sha = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in SOURCE_PATHS.items()
    }
    assert source_sha == EXPECTED_SHA256
    clock_ms = [0]
    thread_requests = []
    sleep_requests = []

    fake_machine = types.ModuleType("machine")
    fake_machine.PWM = FakePWM
    fake_time = types.ModuleType("time")
    fake_time.ticks_ms = lambda: clock_ms[0]
    fake_time.sleep_ms = lambda value: sleep_requests.append(value)
    fake_thread = types.ModuleType("_thread")

    def request_thread(function, arguments):
        thread_requests.append({
            "function": function.__qualname__,
            "argument_count": len(arguments),
            "started": False,
        })
        return len(thread_requests)

    fake_thread.start_new_thread = request_thread
    package = types.ModuleType("exact_driver")
    package.__path__ = []
    replacements = {
        "machine": fake_machine,
        "time": fake_time,
        "_thread": fake_thread,
        "exact_driver": package,
        "exact_driver.soft_timer": None,
        "exact_driver.haptic": None,
    }

    with substitute_modules(replacements):
        soft_timer = load_exact("soft_timer")
        haptic_module = load_exact("haptic")
        haptic = haptic_module.Haptic(pin=2, freq=4000)
        haptic.once(freq=2000, duty=50, duration=2000)
        scheduler = soft_timer.SoftTimerScheduler()
        timer = haptic._timer
        pwm = haptic._pwm
        before = {
            "clock_ms": clock_ms[0],
            "timer_next_time": timer.next_time,
            "timer_dead": timer.dead,
            "scheduler_run": scheduler._run,
            "frequency_hz": pwm.frequency,
            "duty_u16": pwm.duty,
            "pwm_calls": list(pwm.calls),
        }
        assert before["duty_u16"] == 32767

        clock_ms[0] = 2000
        scheduler.update(timer)
        at_exact_deadline = {
            "clock_ms": clock_ms[0],
            "timer_dead": timer.dead,
            "duty_u16": pwm.duty,
            "exception": None,
        }
        assert timer.dead is False and pwm.duty == 32767

        clock_ms[0] = 2001
        exception = None
        try:
            scheduler.update(timer)
        except TypeError as exc:
            exception = {"type": type(exc).__name__, "message": str(exc)}
        assert exception is not None
        after_due_update = {
            "clock_ms": clock_ms[0],
            "timer_next_time": timer.next_time,
            "timer_dead": timer.dead,
            "scheduler_run": scheduler._run,
            "frequency_hz": pwm.frequency,
            "duty_u16": pwm.duty,
            "pwm_calls": list(pwm.calls),
            "exception": exception,
        }
        assert timer.dead is True
        assert scheduler._run is True
        assert pwm.duty == 32767
        assert len(pwm.calls) == 2

        haptic._cb()
        direct_callback = {
            "duty_u16": pwm.duty,
            "pwm_calls": list(pwm.calls),
        }
        assert pwm.duty == 0
        assert pwm.calls[-1] == ["duty_u16", 0]
        assert len(thread_requests) == 1
        assert not sleep_requests
        result = {
            "classification": "exact-source-offline-demonstration",
            "python_version": sys.version.split()[0],
            "source_sha256": source_sha,
            "before_due": before,
            "at_exact_deadline": at_exact_deadline,
            "after_due_update": after_due_update,
            "direct_callback": direct_callback,
            "thread_requests": thread_requests,
            "actual_threads_started": 0,
            "real_pwm_operations": 0,
            "real_sleeps": 0,
            "network_requests": 0,
            "device_service_api_contacted": False,
            "firmware_or_qemu_executed": False,
            "limits": [
                "CPython with fake PWM/time/thread modules; not MicroPython firmware execution.",
                "The actual frozen module bytes in the targeted firmware are not bound by this demonstration.",
                "The scheduler background thread was not run; real thread termination is not observed.",
            ],
            "assertions_passed": True,
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
