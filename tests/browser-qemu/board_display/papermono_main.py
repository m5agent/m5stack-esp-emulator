import json
import time

import M5
from browser_probe_config import DEVICE_ID, ROTATION, INPUT_MODE


count = 0
sequence = 0
was_pressed = False
x, y = -1, -1


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
        d.print("PaperMono")
        d.setTextSize(1)
        d.setCursor(24, 64)
        d.print("SSD1677 / original four-gray EPD driver")
        for index, color in enumerate((0x000000, 0x555555, 0xAAAAAA, 0xFFFFFF)):
            d.fillRect(24 + index * 108, 100, 96, 64, color)
        d.setTextSize(3)
        d.setCursor(24, 210)
        d.print("Count: %d" % count)
        for index in range(4):
            d.drawRect(24 + index * 48, 272, 34, 34, 0x000000)
            d.fillRect(26 + index * 48, 274, 30, 30,
                       0x000000 if (count >> index) & 1 else 0xFFFFFF)
        d.drawRect(80, 600, 320, 100, 0x000000)
        d.setTextSize(3)
        d.setCursor(176, 634)
        d.print("TOUCH")
        d.setTextSize(1)
        d.setCursor(24, 730)
        d.print("One complete EPD refresh per accepted touch")
    finally:
        # The exposed SDK API auto-displays EPD at the outermost endWrite.
        d.endWrite()
    return time.ticks_diff(time.ticks_ms(), started)


emit("begin")
if DEVICE_ID != "papermono" or ROTATION != 0 or INPUT_MODE != "touch":
    raise ValueError("PaperMono fixture configuration mismatch")
M5.begin()
d = M5.Display
d.setRotation(0)
width, height = d.width(), d.height()
if (width, height) != (480, 800) or not d.isEPD():
    raise ValueError("PaperMono EPD dimensions mismatch")
# Require the official API; no low-level replacement or coordinate fabrication.
if not hasattr(M5.Touch, "getTouchPointRaw"):
    raise ValueError("PaperMono official raw touch API is not exported")
d.setEpdMode(d.EPDMode.EPD_QUALITY)
refresh_ms = draw_page()
emit("ready", board=M5.getBoard(), width=width, height=height,
     input=INPUT_MODE, epd=True, epd_mode=d.getEpdMode(), refresh_ms=refresh_ms,
     coordinate_source="official-raw-point",
     logical_touch_status="known-sdk-calibration-gap")
heartbeat = time.ticks_ms()
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    logical_x, logical_y = M5.Touch.getX(), M5.Touch.getY()
    if pressed != was_pressed:
        if pressed:
            # This public getter returns the original FT point from M5.update.
            # Stock logical getX/getY calibration remains a separate SDK gap.
            point = M5.Touch.getTouchPointRaw(0)
            if not isinstance(point, tuple) or len(point) != 4:
                raise ValueError("PaperMono official raw touch tuple mismatch")
            x, y, size, touch_id = point
            if not (0 <= x < width and 0 <= y < height and size > 0):
                raise ValueError("PaperMono official raw touch range mismatch")
            emit("pressed", x=x, y=y, count=count, size=size, touch_id=touch_id,
                 logical_x=logical_x, logical_y=logical_y,
                 coordinate_source="official-raw-point", coordinates_cached=False)
            if 80 <= x < 400 and 600 <= y < 700:
                count += 1
                refresh_ms = draw_page()
                emit("count", count=count, refresh_ms=refresh_ms,
                     coordinate_source="official-raw-point")
            else:
                emit("ignored", x=x, y=y, count=count,
                     coordinate_source="official-raw-point")
        else:
            emit("released", x=x, y=y, count=count, logical_x=logical_x,
                 logical_y=logical_y, coordinate_source="official-raw-point",
                 coordinates_cached=True)
        was_pressed = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
