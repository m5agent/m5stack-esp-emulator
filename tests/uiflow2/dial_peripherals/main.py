# Bind serial events to one composed firmware/session with probe_config.NONCE.
import json
from builtins import print as serial_print
from probe_config import NONCE

sequence = 0

def print(*values):
    global sequence
    sequence += 1
    serial_print("M5EMU_DIAL " + json.dumps({"nonce": NONCE, "seq": sequence,
        "kind": values[0], "values": values[1:]}))

import M5
from hardware import Rotary, I2C, Pin
from unit import RTC8563Unit
import time
print("DIAL_MAIN_START")
M5.begin()
print("DIAL_M5_BEGIN_OK")
print("DIAL_BOARD", M5.getBoard())
print("DIAL_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
M5.Display.fillScreen(0x000000)
M5.Display.drawCircle(120, 120, 112, 0x0000FF)
M5.Display.setTextColor(0xFFFFFF, 0x000000)
M5.Display.setTextSize(2)
M5.Display.setCursor(70, 48)
M5.Display.print("M5Dial")
rtc = RTC8563Unit(I2C(0, sda=Pin(11), scl=Pin(12), freq=400000))
print("DIAL_RTC", tuple(rtc.get_date_time(i) for i in range(7)))
rtc_tick = time.ticks_ms()
rotary = Rotary()
old = None
count = 0
pressed_before = False
touch_before = None
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != pressed_before:
        if pressed:
            count += 1
        print("DIAL_BUTTON", int(pressed), count)
        M5.Display.fillRect(116, 202, 8, 8, 0x00FF00 if pressed else 0xFF0000)
        pressed_before = pressed
    value = rotary.get_rotary_value()
    if value != old:
        print("DIAL_ROTARY", value)
        M5.Display.fillRect(60, 100, 140, 28, 0x000000)
        M5.Display.setCursor(60, 104)
        M5.Display.print("rot:%d" % value)
        old = value
    touches = M5.Touch.getCount()
    touch = (touches, M5.Touch.getX(), M5.Touch.getY()) if touches else (0,)
    if touch != touch_before:
        print("DIAL_TOUCH", touch)
        if touches:
            M5.Display.fillCircle(touch[1], touch[2], 5, 0x00FFFF)
        touch_before = touch
    now = time.ticks_ms()
    if time.ticks_diff(now, rtc_tick) >= 1000:
        print("DIAL_RTC", tuple(rtc.get_date_time(i) for i in range(7)))
        rtc_tick = now
    time.sleep_ms(20)
