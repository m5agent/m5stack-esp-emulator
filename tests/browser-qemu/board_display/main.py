import json
import time

import M5
from browser_probe_config import DEVICE_ID, ROTATION, INPUT_MODE


count = 0
was_pressed = False
sequence = 0


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["device"] = DEVICE_ID
    fields["kind"] = kind
    fields["seq"] = sequence
    print("M5_BROWSER_PROBE " + json.dumps(fields))


def draw_count():
    d.fillRect(8, height // 2, width - 16, 30, 0x102030)
    d.setCursor(8, height // 2 + 6)
    d.setTextColor(0xFFFFFF)
    d.print("Count: %d" % count)
    if count:
        d.fillRect(2, 2, 8, 8, 0x00FF00)


emit("begin")
M5.begin()
d = M5.Display
d.setRotation(ROTATION)
d.setBrightness(255)
width, height = d.width(), d.height()
d.fillScreen(0x102030)
d.drawRect(1, 1, width - 2, height - 2, 0x2176FF)
d.fillRect(2, 2, 8, 8, 0xFF0000)
d.setTextSize(1)
d.setTextColor(0xFFFFFF)
d.setCursor(8, 20)
d.print(DEVICE_ID)
d.setCursor(8, 38)
d.print("C/QEMU browser")
draw_count()
emit("ready", board=M5.getBoard(), width=width, height=height, input=INPUT_MODE)
heartbeat = time.ticks_ms()
while True:
    M5.update()
    if INPUT_MODE == "touch":
        pressed = M5.Touch.getCount() > 0
        x, y = M5.Touch.getX(), M5.Touch.getY()
    else:
        pressed = M5.BtnA.isPressed()
        x, y = -1, -1
    if pressed != was_pressed:
        emit("pressed" if pressed else "released", x=x, y=y, count=count)
        if pressed:
            count += 1
            draw_count()
            emit("count", count=count)
        was_pressed = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
