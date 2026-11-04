import json
import time

import M5


# The caller prepends BUTTON_SPECS, BUTTON_PM1_SETUP and RUN_NONCE. Observations
# below come from original public APIs after M5.update(), never requested input.
M5.begin()
pmic_setup = {}
if BUTTON_PM1_SETUP:
    from machine import I2C, Pin
    setup = BUTTON_PM1_SETUP
    assert M5.getBoard() == getattr(M5.BOARD, setup["board"])
    assert setup["click_window_ms"] == 500, "unsupported PM1 observer window"
    pm1_bus = I2C(setup["i2c"], scl=Pin(setup["scl"]), sda=Pin(setup["sda"]), freq=100000)
    configuration_api = setup["configuration_api"]
    if configuration_api == "m5pm1-python-driver":
        from driver.m5pm1 import M5PM1

        pm1 = M5PM1(pm1_bus, addr=setup["addr"])
    else:
        assert configuration_api == "machine-i2c-register-rmw", "unsupported PM1 configuration API"
    before = pm1_bus.readfrom_mem(setup["addr"], 0x49, 1)[0]
    before4a = pm1_bus.readfrom_mem(setup["addr"], 0x4A, 1)[0]
    if configuration_api == "m5pm1-python-driver":
        pm1.disable_single_click_reset()
        pm1.set_button_timing(M5PM1.BUTTON_TIMING_CLICK, setup["click_window_ms"])
        api = "M5PM1.disable_single_click_reset+set_button_timing"
    else:
        # Public guest I2C, using the same PM1 register contract: bit0 disables
        # single-click reset; bits2:1=2 select the 500ms recognition window.
        # IRQ42 remains exclusively consumed by the original M5.update path.
        pm1_bus.writeto_mem(setup["addr"], 0x49, bytes(((before & ~0x07) | 0x05,)))
        api = "machine.I2C.readfrom_mem+writeto_mem"
    after = pm1_bus.readfrom_mem(setup["addr"], 0x49, 1)[0]
    after4a = pm1_bus.readfrom_mem(setup["addr"], 0x4A, 1)[0]
    assert after == ((before & ~0x07) | 0x05), "PM1 button-IRQ configuration mismatch"
    assert after4a == before4a, "PM1 unrelated button configuration changed"
    pmic_setup = {"applied": True, "api": api, "configuration_api": configuration_api,
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
