import json
import time

import M5


# The caller prepends BUTTON_SPECS, BUTTON_PM1_SETUP and RUN_NONCE. Observations
# below come from original public APIs after M5.update(), never requested input.
M5.begin()
pmic_setup = {}
if BUTTON_PM1_SETUP:
    from machine import I2C, Pin
    from driver.m5pm1 import M5PM1

    setup = BUTTON_PM1_SETUP
    assert M5.getBoard() == getattr(M5.BOARD, setup["board"])
    assert setup["click_window_ms"] == 500, "unsupported PM1 observer window"
    pm1_bus = I2C(setup["i2c"], scl=Pin(setup["scl"]), sda=Pin(setup["sda"]), freq=100000)
    pm1 = M5PM1(pm1_bus, addr=setup["addr"])
    before = pm1_bus.readfrom_mem(setup["addr"], 0x49, 1)[0]
    before4a = pm1_bus.readfrom_mem(setup["addr"], 0x4A, 1)[0]
    pm1.disable_single_click_reset()
    pm1.set_button_timing(M5PM1.BUTTON_TIMING_CLICK, setup["click_window_ms"])
    after = pm1_bus.readfrom_mem(setup["addr"], 0x49, 1)[0]
    after4a = pm1_bus.readfrom_mem(setup["addr"], 0x4A, 1)[0]
    assert after == ((before & ~0x07) | 0x05), "PM1 button-IRQ configuration mismatch"
    assert after4a == before4a, "PM1 unrelated button configuration changed"
    pmic_setup = {"applied": True, "api": "M5PM1.disable_single_click_reset+set_button_timing",
                  "cfg49_before": before, "cfg49_after": after,
                  "cfg4a_before": before4a, "cfg4a_after": after4a,
                  "click_window_ms": setup["click_window_ms"], "i2c": setup["i2c"],
                  "scl": setup["scl"], "sda": setup["sda"], "addr": setup["addr"]}
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
emit("ready", board=M5.getBoard(), states=previous, pmic_setup=pmic_setup)
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
