"""Opt-in custom guest: observe frozen Haptic/SoftTimer; never repair them."""
import io
import sys
import time

import M5
import driver.haptic as haptic_module
import driver.soft_timer as soft_timer_module
from driver.haptic import Haptic
from driver.soft_timer import SoftTimer, SoftTimerScheduler
from io_drivers.buzzer import BuzzerUnit
from probe_config import WHITE, YELLOW, TRACE_SCHEDULER
from probe_logging import emit


def exception_record(label, error):
    emit("BUZZER_DIAG_EXCEPTION", label, type(error).__name__, repr(error))
    trace = io.StringIO()
    sys.print_exception(error, trace)
    for line in trace.getvalue().splitlines():
        emit("BUZZER_DIAG_TRACE", label, repr(line))


def invoke(label, callback):
    emit("BUZZER_DIAG_CALL", label)
    try:
        callback()
    except Exception as error:
        exception_record(label, error)
        emit("BUZZER_DIAG_RETURN", label, "raised")
        return False
    emit("BUZZER_DIAG_RETURN", label, "returned")
    return True


emit("BUZZER_DIAG_START", "custom-guest-buzzer-once-diagnostic-v1",
     "trace-scheduler", int(TRACE_SCHEDULER))
M5.begin()
screen = M5.Display
screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Buzzer once diagnostic")


def show(text):
    screen.fillRect(0, 40, 320, 180, 0xFFFFFF)
    screen.setCursor(6, 44)
    screen.print(text)


# The packaged BuzzerUnit wrapper is an unchanged official source copy.
# driver.haptic and driver.soft_timer are imported from the actual base image;
# neither module is included in this guest's VFS.
unit = BuzzerUnit((WHITE, YELLOW))
scheduler = SoftTimerScheduler()
emit("BUZZER_DIAG_IMPLEMENTATION", repr(sys.implementation))
emit("BUZZER_DIAG_MODULES", repr(haptic_module), repr(soft_timer_module))
emit("BUZZER_DIAG_IDENTITY", "cb-is-haptic", int(BuzzerUnit._cb is Haptic._cb),
     "once-is-haptic", int(BuzzerUnit.once is Haptic.once),
     "callback", repr(unit._cb))

if TRACE_SCHEDULER:
    # Separate image, explicit instrumentation: preserve the real loop and
    # callback, record its exception over the same UART as probe_logging, then
    # re-raise. This can change startup timing and is not the natural run.
    original_scheduler_loop = SoftTimerScheduler._cb

    def traced_scheduler_loop(self):
        emit("BUZZER_DIAG_THREAD_ENTER", time.ticks_ms(),
             "run-flag", getattr(self, "_run", "missing"))
        try:
            original_scheduler_loop(self)
        except Exception as error:
            exception_record("scheduler-thread", error)
            raise
        finally:
            emit("BUZZER_DIAG_THREAD_EXIT", time.ticks_ms(),
                 "run-flag", getattr(self, "_run", "missing"))

    SoftTimerScheduler._cb = traced_scheduler_loop
    emit("BUZZER_DIAG_INSTRUMENTED", "scheduler-loop-entry-only")


def snapshot(phase):
    try:
        frequency = unit._pwm.freq()
        duty = unit._pwm.duty_u16()
    except Exception as error:
        exception_record("pwm-getter", error)
        frequency, duty = "unavailable", "unavailable"
    now = time.ticks_ms()
    next_time = getattr(unit._timer, "next_time", None)
    next_delta = time.ticks_diff(next_time, now) if next_time is not None else "missing"
    emit("BUZZER_DIAG_STATE", phase, "tick", now,
         "freq", frequency, "duty-u16", duty,
         "timer-dead", getattr(unit._timer, "dead", "missing"),
         "next-delta-ms", next_delta,
         "run-flag", getattr(scheduler, "_run", "missing"),
         "registered", len(getattr(scheduler, "_tims", ())))


def observe(phase, duration):
    show(phase + "\ncustom diagnostic guest")
    start = time.ticks_ms()
    last = start - 250
    while time.ticks_diff(time.ticks_ms(), start) < duration:
        M5.update()
        now = time.ticks_ms()
        if time.ticks_diff(now, last) >= 250:
            snapshot(phase)
            last = now
        time.sleep_ms(25)
    snapshot(phase)


emit("BUZZER_DIAG_READY")
observe("idle-baseline", 1000)

# First functional phase: no timer/callback replacement and no extra timer.
# Its completion marker is not a PASS. The host must correlate all snapshots
# with fresh live QOM GETs before subsequent manual operations occur.
emit("BUZZER_DIAG_NATURAL_START", time.ticks_ms(), 2000, 50, 2000)
unit.once(freq=2000, duty=50, duration=2000)
emit("BUZZER_DIAG_NATURAL_RETURN", time.ticks_ms(),
     "callback-is-unit", int(unit._timer.callback == unit._cb),
     "callback", repr(unit._timer.callback))
observe("natural-once", 3500)
emit("BUZZER_DIAG_NATURAL_END", time.ticks_ms())

# Inspect the actual asynchronous scheduler after the natural phase. A true
# _run attribute is only a flag, never proof that its thread is still alive.
async_records = []
async_timer = None


def async_callback(*args):
    same_timer = len(args) == 1 and args[0] is async_timer
    async_records.append((len(args), same_timer))
    emit("BUZZER_DIAG_ASYNC_CALLBACK", "argc", len(args),
         "same-timer", int(same_timer), "tick", time.ticks_ms())


async_timer = SoftTimer(mode=SoftTimer.ONE_SHOT, period=500, callback=async_callback)
observe("async-sentinel-after-natural", 1500)
emit("BUZZER_DIAG_ASYNC_RESULT", "calls", len(async_records),
     "records", repr(async_records), "dead", getattr(async_timer, "dead", "missing"),
     "run-flag", getattr(scheduler, "_run", "missing"))


class DetachedTimer:
    # Deliberately not registered with the scheduler: manual calls below are
    # labeled independently and cannot satisfy the natural once phase.
    def __init__(self, callback):
        self.callback = callback
        self.next_time = time.ticks_ms() - 1000
        self.period = 2000
        self.mode = SoftTimer.ONE_SHOT
        self.dead = False


manual_records = []


def manual_callback(*args):
    manual_records.append((len(args), len(args) == 1 and args[0] is manual_timer))
    emit("BUZZER_DIAG_MANUAL_CALLBACK", "argc", len(args),
         "same-timer", int(len(args) == 1 and args[0] is manual_timer))


manual_timer = DetachedTimer(manual_callback)
invoke("manual-scheduler-callback-argc", lambda: scheduler.update(manual_timer))
emit("BUZZER_DIAG_MANUAL_RESULT", "calls", len(manual_records),
     "records", repr(manual_records), "dead", manual_timer.dead)

unit.set_duty(25)
observe("manual-haptic-before", 1000)
haptic_timer = DetachedTimer(unit._cb)
invoke("manual-scheduler-original-haptic", lambda: scheduler.update(haptic_timer))
emit("BUZZER_DIAG_HAPTIC_UPDATE_RESULT", "dead", haptic_timer.dead)
observe("manual-haptic-after", 1500)

invoke("original-bound-cb-with-timer", lambda: unit._cb(haptic_timer))
observe("direct-cb-with-timer-after", 1000)
invoke("original-bound-cb-no-args", unit._cb)
observe("direct-cb-no-args-after", 1500)

unit.turn_off()
observe("explicit-turn-off-final", 1000)
show("Diagnostic complete\nInspect serial + live QOM\nNo PASS inherited")
emit("BUZZER_DIAG_DONE", "execution-ended-no-functional-verdict")
while True:
    M5.update()
    time.sleep_ms(50)
