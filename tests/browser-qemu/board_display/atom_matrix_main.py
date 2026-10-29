import json
import time

import M5
from hardware import RGB
from browser_probe_config import DEVICE_ID


sequence = 0
count = 0
was_pressed = False


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["device"] = DEVICE_ID
    fields["kind"] = kind
    fields["seq"] = sequence
    print("M5_BROWSER_PROBE " + json.dumps(fields))


emit("begin")
M5.begin()
rgb = RGB()
rgb.set_brightness(100)
rgb.fill_color(0x204060)
emit("ready", board=M5.getBoard(), input="button", output="ws2812-rmt-gpio27", leds=25)
heartbeat = time.ticks_ms()
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != was_pressed:
        emit("pressed" if pressed else "released", count=count)
        if pressed:
            count += 1
            rgb.fill_color(0x40A020)
            emit("count", count=count)
        else:
            rgb.fill_color(0x204060)
        was_pressed = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
