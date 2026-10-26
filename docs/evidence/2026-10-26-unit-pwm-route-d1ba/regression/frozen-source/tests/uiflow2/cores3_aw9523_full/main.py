import M5
import time
from M5 import *
from machine import I2C, Pin
from driver.aw9523 import AW9523, Pin as ExpanderPin


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(10, 10)
d.print("CoreS3 AW9523 full")

ok = False
detail = "init"
try:
    i2c = I2C(1, scl=Pin(12), sda=Pin(11), freq=400000)
    expander = AW9523(i2c, 0x58)

    out = ExpanderPin(0, ExpanderPin.OUT, 1)
    inp = ExpanderPin(12, ExpanderPin.IN)
    output_readback = out.value()
    injected_input = inp.value()

    if output_readback != 1 or injected_input != 1:
        raise RuntimeError("AW9523 state mismatch")

    # The QOM injection happens before the touch event, so read after it.
    while M5.Touch.getCount() == 0:
        M5.update()
        time.sleep_ms(10)
    injected_input = inp.value()
    detail = "out=%d in=%d" % (output_readback, injected_input)
    if injected_input != 0:
        raise RuntimeError("AW9523 injected input was not visible")
    ok = True
except Exception as exc:
    detail = repr(exc)[:52]

d.fillRect(0, 0, 320, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(10, 45)
d.print(detail)
d.setCursor(10, 70)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
