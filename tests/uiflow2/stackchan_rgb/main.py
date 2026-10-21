import M5
import time
from M5 import *
from machine import I2C, Pin
from driver.m5ioe1 import M5IOE1, RGB


REG_LED_RAM_START = 0x30

M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(10, 10)
d.print("StackChan RGB")

status = "init"
raw0 = 0
raw11 = 0
try:
    i2c = I2C(1, scl=Pin(11), sda=Pin(12), freq=100000)
    ioe = M5IOE1(i2c, 0x6F)
    rgb = RGB(ioe, io=14, n=12)
    rgb.fill_color(0xFF0000)
    raw0 = ioe.read_reg16(REG_LED_RAM_START)
    raw11 = ioe.read_reg16(REG_LED_RAM_START + 11 * 2)
    if raw0 != 0xF800 or raw11 != 0xF800:
        raise RuntimeError("LED RAM mismatch")
    d.fillRect(0, 0, 320, 8, d.COLOR.GREEN)
    status = "ok"
except Exception as exc:
    d.setCursor(10, 150)
    d.print(repr(exc)[:40])

d.setCursor(10, 50)
d.print("led0=0x%04x" % raw0)
d.setCursor(10, 80)
d.print("led11=0x%04x" % raw11)
d.setCursor(10, 110)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
