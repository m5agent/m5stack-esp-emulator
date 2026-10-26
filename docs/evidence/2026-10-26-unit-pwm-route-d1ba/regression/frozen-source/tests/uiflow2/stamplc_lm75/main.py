import M5
import time
from M5 import *
from machine import I2C, Pin


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(4, 4)
d.print("StamPLC LM75")

status = "init"
try:
    i2c = I2C(0, scl=Pin(15), sda=Pin(13), freq=100000)
    raw = i2c.readfrom_mem(0x48, 0x00, 2)
    value = (raw[0] << 8) | raw[1]
    temp = (value >> 5) / 8.0
    if raw[0] != 0x25 or raw[1] != 0x80 or abs(temp - 37.5) > 0.01:
        raise RuntimeError("raw=%r temp=%.3f" % (raw, temp))
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN)
    status = "ok %.1fC raw=%02x%02x" % (temp, raw[0], raw[1])
except Exception as exc:
    status = "error: " + repr(exc)

d.setCursor(4, 24)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
