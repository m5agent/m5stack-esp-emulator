import json
import time

import M5
from browser_probe_config import DEVICE_ID, INPUT_MODE, ROTATION


sequence = 0


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields.update(device=DEVICE_ID, kind=kind, seq=sequence)
    print("M5_BROWSER_PROBE " + json.dumps(fields))


if DEVICE_ID != "corematrix" or INPUT_MODE != "button" or ROTATION != 0:
    raise ValueError("CoreMatrix fixture configuration mismatch")

M5.begin()
display = M5.Lcd
display.setRotation(ROTATION)
display.setBrightness(255)
width, height = display.width(), display.height()
if M5.getBoard() != 152 or (width, height) != (16, 16):
    raise ValueError("CoreMatrix board or display mismatch")

display.clear(0)
display.fillRect(2, 2, 4, 4, 0xFFFFFF)
emit("ready", board=M5.getBoard(), width=width, height=height, input=INPUT_MODE)
was_pressed = False
count = 0
heartbeat = time.ticks_ms()

while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != was_pressed:
        emit("pressed" if pressed else "released", count=count)
        if pressed:
            count += 1
            display.fillRect(2, 2, 4, 4, 0)
            display.fillRect(8, 9, 4, 3, 0xFFFFFF)
            emit("count", count=count)
        was_pressed = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
