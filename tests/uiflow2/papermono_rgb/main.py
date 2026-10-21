import M5
import time
from M5 import *
from machine import I2C, Pin
from m5pm1 import M5PM1
from driver.m5ioe1 import M5IOE1


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK)
d.setTextSize(1)
d.setCursor(20, 20)
d.print("PaperMono RGB")

ok = False
detail = "init"
try:
    M5.Led.setAllColor(0x00FF00)
    M5.Led.display()
    i2c = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
    pmic = M5PM1(i2c, addr=0x6E)
    ioe = M5IOE1(i2c, 0x4F)
    red_en = (pmic.read_reg(0x06) >> 4) & 1
    green = ioe.read_pin(8)
    blue = ioe.read_pin(9)
    green_pwm, _, green_enabled = ioe._pwm_reg_value(1)
    detail = "r=%d g=%d b=%d pwm=%d" % (
        red_en, green, blue, green_pwm,
    )
    if red_en != 0 or green != 1 or blue != 0 or not green_enabled or green_pwm == 0:
        raise RuntimeError(detail)
    ok = True
except Exception as exc:
    detail = repr(exc)[:52]

d.fillRect(0, 0, 400, 10, d.COLOR.BLACK if ok else d.COLOR.WHITE)
d.setCursor(20, 60)
d.print(detail)
d.setCursor(20, 90)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
