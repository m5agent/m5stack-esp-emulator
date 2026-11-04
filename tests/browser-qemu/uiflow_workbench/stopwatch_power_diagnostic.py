"""Opt-in diagnostic source; never grants default-button acceptance.

Caller supplies RUN_NONCE, POWER_MODE (button/power/registers) and POWER_CONFIG
(default/irq500ms). Each mode must use a fresh exact-image browser VM.
"""
import json
import time

import M5
from machine import I2C, Pin


assert POWER_MODE in ("metadata", "button", "power", "registers")
assert POWER_CONFIG in ("default", "irq500ms")
M5.begin()
assert M5.getBoard() == M5.BOARD.M5StopWatch
bus = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
sequence = 0


def read(reg):
    return bus.readfrom_mem(0x6E, reg, 1)[0]


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields.update(kind=kind, nonce=RUN_NONCE, seq=sequence,
                  guest_ms=time.ticks_ms(), mode=POWER_MODE, config=POWER_CONFIG)
    print("M5_STOPWATCH_POWER_DIAGNOSTIC " + json.dumps(fields))


before = {"cfg49": read(0x49), "cfg4a": read(0x4A), "irq42": read(0x42)}
if POWER_CONFIG == "irq500ms":
    # Real PM1 BTN_CFG1: disable single-click reset (bit0=1), select the
    # documented 500ms recognition window (bits2:1=2). Preserve other bits.
    value = (before["cfg49"] & ~0x07) | 0x05
    bus.writeto_mem(0x6E, 0x49, bytes((value,)))
    assert read(0x49) == value
emit("ready", before=before, after={"cfg49": read(0x49), "cfg4a": read(0x4A)},
     battery_mv=M5.Power.getBatteryVoltage(), is_charging=M5.Power.isCharging(),
     power_type=M5.Power.getType() if hasattr(M5.Power, "getType") else None)
started = heartbeat = time.ticks_ms()
previous = None
while time.ticks_diff(time.ticks_ms(), started) < 15000:
    if POWER_MODE == "button":
        # The original public owner consumes Power.getKeyState internally.
        # Never call that consuming API separately in this mode.
        M5.update()
        state = M5.BtnPWR.isPressed()
        if state != previous:
            emit("button-state", pressed=state)
            previous = state
        for method in ("wasPressed", "wasReleased", "wasClicked", "wasHold"):
            if getattr(M5.BtnPWR, method)():
                emit("button-event", method=method)
    elif POWER_MODE == "power":
        # Exclusive public consumer: no M5.update or BtnPWR observation.
        value = M5.Power.getKeyState()
        if value:
            emit("power-key-state", value=value)
    elif POWER_MODE == "registers":
        # Raw, real guest I2C observation only. Register0x48 clears its edge
        # latch on read, so this mode must not share either public consumer.
        state = (read(0x42), read(0x48))
        if state != previous:
            emit("register-state", irq42=state[0], status48=state[1])
            previous = state
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 1000:
        emit("heartbeat")
        heartbeat = now
    time.sleep_ms(10)
emit("finished")
