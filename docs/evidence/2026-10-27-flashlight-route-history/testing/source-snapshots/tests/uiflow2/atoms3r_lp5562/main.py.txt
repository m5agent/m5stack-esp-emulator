import M5
import time
from M5 import *
from machine import I2C, Pin


ADDR = 0x30

M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 8)
d.print("AtomS3R LP5562")

status = "init"
rgb = (0, 0, 0)
try:
    i2c = I2C(1, scl=Pin(0), sda=Pin(45), freq=100000)
    i2c.writeto_mem(ADDR, 0x00, b"\xC0")
    i2c.writeto_mem(ADDR, 0x01, b"\x01")
    i2c.writeto_mem(ADDR, 0x04, b"\x80")
    i2c.writeto_mem(ADDR, 0x03, b"\x40")
    i2c.writeto_mem(ADDR, 0x02, b"\x20")
    rgb = (
        i2c.readfrom_mem(ADDR, 0x04, 1)[0],
        i2c.readfrom_mem(ADDR, 0x03, 1)[0],
        i2c.readfrom_mem(ADDR, 0x02, 1)[0],
    )
    if rgb != (0x80, 0x40, 0x20):
        raise RuntimeError("PWM readback mismatch")
    d.fillRect(0, 0, 128, 8, d.COLOR.GREEN)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(6, 70)
    d.print(repr(exc)[:34])

d.setCursor(6, 32)
d.print("rgb=%d,%d,%d" % rgb)
d.setCursor(6, 50)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
