import json
import time

import M5
from hardware.stackchan import StackChan


# The runner prepends RUN_NONCE. All values are original public driver reads.
# StackChan.get_touch() returns logical front/middle/back in reversed Si12T
# register order. A second original driver read detects its zero-on-error
# fallback; only coherent observations are emitted across input transitions.
M5.begin()
stackchan = StackChan(i2c=1, uart=1)
sequence = 0
previous = None
started = time.ticks_ms()
heartbeat = started


def emit(kind, raw, levels):
    global sequence
    sequence += 1
    print("M5_STACKCHAN_TOUCH " + json.dumps({
        "nonce": RUN_NONCE,
        "kind": kind,
        "seq": sequence,
        "guest_ms": time.ticks_ms(),
        "board": M5.getBoard(),
        "driver_levels": raw,
        "levels": levels,
    }))


while time.ticks_diff(time.ticks_ms(), started) < 120000:
    M5.update()
    raw = stackchan.touch.get_touch_status()
    if raw is None:
        raise OSError("Original Si12T I2C read failed")
    levels = stackchan.get_touch()
    if len(raw) != 3 or len(levels) != 3:
        raise ValueError("Original StackChan touch API shape mismatch")
    if any(value not in (0, 1, 2, 3) for value in raw + levels):
        raise ValueError("Original Si12T output level mismatch")
    # The input may transition between these two actual I2C transactions.
    if levels == list(reversed(raw)):
        if previous is None:
            emit("ready", raw, levels)
            previous = levels
        elif levels != previous:
            emit("state", raw, levels)
            previous = levels
        now = time.ticks_ms()
        if time.ticks_diff(now, heartbeat) >= 1000:
            emit("heartbeat", raw, levels)
            heartbeat = now
    time.sleep_ms(10)
