"""MicroPython disposable Timer/RTC/watchdog/power lifecycle experiments.

Prefix LIFECYCLE_CASE with the requested case before submitting this file via
run_guest.py. Flash stage markers must survive actual guest reset; host code
never sets the returned reset reason or substitutes callbacks/sensor values.
"""

import json
import time
import machine
import M5


def lifecycle_emit(api, status, **details):
    details.update(api=api, status=status)
    print("HARDWARE_LIFECYCLE " + json.dumps(details))


def lifecycle_wait(milliseconds):
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)


def lifecycle_marker(value=None):
    path = "/flash/api-lifecycle-stage.txt"
    if value is not None:
        with open(path, "w") as handle:
            handle.write(value)
        return value
    try:
        with open(path) as handle:
            return handle.read()
    except OSError:
        return "fresh"


def run_timer_lifecycle():
    hits = []
    timer = machine.Timer(0)
    timer.init(period=100, mode=machine.Timer.PERIODIC, callback=lambda item: hits.append(time.ticks_ms()))
    lifecycle_wait(30)
    first_value = timer.value()
    lifecycle_wait(30)
    second_value = timer.value()
    lifecycle_emit("machine.Timer.value", "API_ASSERTION_PASS" if 15 <= first_value <= 55 and first_value < second_value < 100 else "FAIL", first_ms=first_value, second_ms=second_value)
    lifecycle_wait(390)
    timer.deinit()
    observed = len(hits)
    lifecycle_wait(250)
    lifecycle_emit("machine.Timer.init", "API_ASSERTION_PASS" if 3 <= observed <= 6 else "FAIL", mode="periodic", hits=hits)
    lifecycle_emit("machine.Timer.deinit", "API_ASSERTION_PASS" if len(hits) == observed else "FAIL", before=observed, after=len(hits))
    hits = []
    timer.init(period=80, mode=machine.Timer.ONE_SHOT, callback=lambda item: hits.append(time.ticks_ms()))
    lifecycle_wait(300)
    timer.deinit()
    lifecycle_emit("machine.Timer.init", "API_ASSERTION_PASS" if len(hits) == 1 else "FAIL", mode="one-shot", hits=hits)


def run_rtc_lifecycle():
    rtc = machine.RTC()
    initial = rtc.datetime()
    target = (2026, 10, 27, 1, 12, 34, 50, 0)
    # ESP32 RTC.init() takes Y/M/D/hour/minute/second, unlike datetime()'s
    # Y/M/D/weekday/hour/minute/second tuple (official machine_rtc.c).
    rtc.init((2026, 10, 27, 12, 34, 50, 0, 0))
    actual = rtc.datetime()
    lifecycle_emit("machine.RTC.init", "API_ASSERTION_PASS" if tuple(actual[:7]) == target[:7] else "FAIL", target=target, actual=actual)
    memory = rtc.memory()
    rtc.memory(b"M5EMU_RTC_PUBLIC_API")
    lifecycle_emit("machine.RTC.memory", "API_ASSERTION_PASS" if rtc.memory() == b"M5EMU_RTC_PUBLIC_API" else "FAIL", bytes=len(rtc.memory()))
    lifecycle_wait(1100)
    actual = rtc.datetime()
    lifecycle_emit("machine.RTC.datetime", "API_ASSERTION_PASS" if actual[6] in (51, 52) else "FAIL", actual=actual)
    rtc.memory(memory)
    rtc.datetime(initial)


def run_wdt_lifecycle():
    stage = lifecycle_marker()
    cause = machine.reset_cause()
    wdt_cause = machine.WDT_RESET
    if stage == "await-wdt-reset":
        lifecycle_emit("machine.WDT", "API_ASSERTION_PASS" if cause == wdt_cause else "FAIL", flash_stage=stage, reset_cause=cause, expected_wdt_cause=wdt_cause)
        return
    if stage != "fresh":
        lifecycle_emit("machine.WDT.feed", "FAIL", flash_stage=stage, reset_cause=cause, detail="guest reset before the feed-survival stage completed")
        return
    lifecycle_marker("feeding-wdt")
    watchdog = machine.WDT(timeout=2000)
    started = time.ticks_ms()
    for _ in range(24):
        watchdog.feed()
        lifecycle_wait(250)
    lifecycle_emit("machine.WDT.feed", "API_ASSERTION_PASS", elapsed_ms=time.ticks_diff(time.ticks_ms(), started), reset_cause=cause)
    lifecycle_marker("await-wdt-reset")
    print("HARDWARE_WDT_EXPIRY_ARMED")
    lifecycle_wait(9000)
    lifecycle_emit("machine.WDT", "BLOCKED", detail="No guest watchdog reset after more than four configured timeout intervals", flash_stage=lifecycle_marker(), reset_cause=machine.reset_cause())


def run_power_lifecycle(kind):
    stage = lifecycle_marker()
    cause = machine.reset_cause()
    if stage == "await-power-reset":
        lifecycle_emit("M5.Power." + kind, "API_ASSERTION_PASS" if kind != "lightSleep" and cause == machine.DEEPSLEEP_RESET else "FAIL", flash_stage=stage, reset_cause=cause, expected_deepsleep_cause=machine.DEEPSLEEP_RESET)
        return
    lifecycle_marker("await-power-reset")
    print("HARDWARE_POWER_CALL_START", kind)
    started = time.ticks_ms()
    if kind == "timerSleep":
        M5.Power.timerSleep(2)
    elif kind == "powerOff":
        M5.Power.powerOff()
    else:
        getattr(M5.Power, kind)(2000000, False)
    elapsed = time.ticks_diff(time.ticks_ms(), started)
    if kind == "lightSleep":
        lifecycle_emit("M5.Power.lightSleep", "API_ASSERTION_PASS" if 1800 <= elapsed <= 6000 else "FAIL", elapsed_ms=elapsed, reset_cause=machine.reset_cause())
    else:
        lifecycle_emit("M5.Power." + kind, "FAIL", detail="power transition returned without a guest reset/power-off observation", elapsed_ms=elapsed)


M5.begin()
_case = globals().get("LIFECYCLE_CASE", "timer")
print("HARDWARE_LIFECYCLE_START", _case, lifecycle_marker(), machine.reset_cause())
try:
    if _case == "timer":
        run_timer_lifecycle()
    elif _case == "rtc":
        run_rtc_lifecycle()
    elif _case == "wdt":
        run_wdt_lifecycle()
    elif _case in ("lightSleep", "deepSleep", "timerSleep", "powerOff"):
        run_power_lifecycle(_case)
    else:
        raise ValueError(_case)
except Exception as _error:
    lifecycle_emit(_case, "ERROR", error=repr(_error))
print("HARDWARE_LIFECYCLE_DONE")
