import json
import time

import M5
from browser_probe_config import DEVICE_ID, INPUT_MODE, ROTATION


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields.update(device=DEVICE_ID, kind=kind, seq=sequence)
    print("M5_BROWSER_PROBE " + json.dumps(fields))


sequence = 0
count = 0
was_pressed = False
touch = DEVICE_ID == "papers3"
if DEVICE_ID not in ("paperdiy", "papers3") or INPUT_MODE != ("touch" if touch else "button") or ROTATION != 0:
    raise ValueError("ET047TC1 fixture configuration mismatch")

emit("begin")
M5.begin()
d = M5.Display
d.setRotation(ROTATION)
width, height = d.width(), d.height()
if (width, height) != (540, 960) or not d.isEPD():
    raise ValueError("ET047TC1 display identity mismatch")
d.fillScreen(0xFFFFFF)
d.fillRect(16, 16, 16, 16, 0x000000)
d.setTextColor(0x000000, 0xFFFFFF)
d.setTextSize(3)
d.setCursor(24, 210)
d.print("Count: 0")
emit("ready", board=M5.getBoard(), width=width, height=height, input=INPUT_MODE)
heartbeat = time.ticks_ms()
x, y = -1, -1

while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0 if touch else M5.BtnA.isPressed()
    if pressed != was_pressed:
        if pressed:
            if touch:
                x, y = M5.Touch.getX(), M5.Touch.getY()
            emit("pressed", x=x, y=y, count=count)
            count += 1
            d.fillRect(16, 16, 16, 16, 0xFFFFFF if count % 2 else 0x000000)
            d.setCursor(24, 210)
            d.print("Count: %d" % count)
            emit("count", x=x, y=y, count=count)
        else:
            emit("released", x=x, y=y, count=count)
        was_pressed = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
