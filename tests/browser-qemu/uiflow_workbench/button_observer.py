import json
import time

import M5


# The caller prepends BUTTON_SPECS and RUN_NONCE to this source. All observations
# below come from original public APIs after M5.update(), never requested input.
M5.begin()
buttons = [(label, getattr(M5, owner)) for label, owner in BUTTON_SPECS]
sequence = 0
previous = {}
started = time.ticks_ms()
heartbeat = started


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["nonce"] = RUN_NONCE
    fields["kind"] = kind
    fields["seq"] = sequence
    fields["guest_ms"] = time.ticks_ms()
    print("M5_BUTTON_OBSERVER " + json.dumps(fields))


M5.update()
for label, button in buttons:
    previous[label] = button.isPressed()
emit("ready", board=M5.getBoard(), states=previous)
while time.ticks_diff(time.ticks_ms(), started) < 120000:
    M5.update()
    for label, button in buttons:
        pressed = button.isPressed()
        if pressed != previous[label]:
            emit("state", button=label, pressed=pressed)
            previous[label] = pressed
        for method in ("wasPressed", "wasReleased", "wasClicked", "wasHold"):
            if getattr(button, method)():
                emit("event", button=label, method=method)
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 1000:
        emit("heartbeat", states=previous)
        heartbeat = now
    time.sleep_ms(10)
emit("finished", states=previous)
