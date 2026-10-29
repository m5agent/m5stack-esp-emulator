import json
import time

import M5
from browser_probe_config import DEVICE_ID, ROTATION, INPUT_MODE


count = 0
sequence = 0
was_pressed = False


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["device"] = DEVICE_ID
    fields["kind"] = kind
    fields["seq"] = sequence
    print("M5_BROWSER_PROBE " + json.dumps(fields))


def draw_page():
    started = time.ticks_ms()
    d.startWrite()
    try:
        d.fillScreen(0xFFFFFF)
        d.drawRect(2, 2, width - 4, height - 4, 0x000000)
        d.fillRect(16, 16, 16, 16, 0xFFFFFF if count else 0x000000)
        d.setTextColor(0x000000, 0xFFFFFF)
        d.setTextSize(2)
        d.setCursor(48, 18)
        d.print("PaperColor")
        d.setTextSize(1)
        d.setCursor(24, 64)
        d.print("Spectra 6 / original EPD driver")
        for index, color in enumerate((0x000000, 0xFFFFFF, 0xFFFF00,
                                       0xFF0000, 0x0000FF, 0x00FF00)):
            d.fillRect(24 + index * 56, 100, 48, 56, color)
        d.setTextSize(3)
        d.setCursor(24, 210)
        d.print("Count: %d" % count)
        for index in range(4):
            d.drawRect(24 + index * 48, 272, 34, 34, 0x000000)
            d.fillRect(26 + index * 48, 274, 30, 30,
                       0x000000 if (count >> index) & 1 else 0xFFFFFF)
        d.setTextSize(2)
        d.setCursor(24, 410)
        d.print("Press front button A")
        d.setTextSize(1)
        d.setCursor(24, 454)
        d.print("One complete EPD refresh per press")
    finally:
        # The exposed SDK API auto-displays EPD at the outermost endWrite.
        d.endWrite()
    return time.ticks_diff(time.ticks_ms(), started)


emit("begin")
if DEVICE_ID != "papercolor" or ROTATION != 0 or INPUT_MODE != "button":
    raise ValueError("PaperColor fixture configuration mismatch")
M5.begin()
d = M5.Display
d.setRotation(0)
width, height = d.width(), d.height()
if (width, height) != (400, 600) or not d.isEPD():
    raise ValueError("PaperColor EPD dimensions mismatch")
d.setEpdMode(d.EPDMode.EPD_QUALITY)
refresh_ms = draw_page()
emit("ready", board=M5.getBoard(), width=width, height=height,
     input=INPUT_MODE, epd=True, epd_mode=d.getEpdMode(), refresh_ms=refresh_ms)
heartbeat = time.ticks_ms()
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != was_pressed:
        if pressed:
            emit("pressed", x=-1, y=-1, count=count)
            count += 1
            refresh_ms = draw_page()
            emit("count", count=count, refresh_ms=refresh_ms)
        else:
            emit("released", x=-1, y=-1, count=count)
        was_pressed = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
