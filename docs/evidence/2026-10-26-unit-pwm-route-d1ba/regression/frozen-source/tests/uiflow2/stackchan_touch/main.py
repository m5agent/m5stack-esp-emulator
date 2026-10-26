import M5
import time
from M5 import *
from machine import I2C, Pin
from driver.si12t import Si12T


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(10, 10)
d.print("StackChan Si12T touch")

i2c = I2C(1, scl=Pin(11), sda=Pin(12), freq=100000)
touch = Si12T(i2c)
last = None
state = [0, 0, 0]

while True:
    value = touch.get_touch_status()
    if value is not None and value != last:
        last = value
        state = value
        d.fillRect(0, 0, 320, 8,
                   d.COLOR.GREEN if any(state) else d.COLOR.BLACK)
        d.fillRect(0, 40, 320, 80, d.COLOR.BLACK)
        d.setCursor(10, 48)
        d.print("points=%s" % state)
        d.setCursor(10, 72)
        d.print("raw=0x%02x" % touch.touch_result)
    M5.update()
    time.sleep_ms(50)
