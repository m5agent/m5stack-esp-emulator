import M5
import time
from M5 import *
from machine import I2C, Pin
from driver.m5ioe1 import M5IOE1


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(20, 20)
d.print("StopWatch vibration")

status = "init"
duty_on = 0
duty_off = 0
enabled_on = False
enabled_off = True
try:
    Power.setVibration(128)
    i2c = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
    ioe = M5IOE1(i2c, 0x4F)
    duty_on, _, enabled_on = ioe._pwm_reg_value(0)
    Power.setVibration(0)
    duty_off, _, enabled_off = ioe._pwm_reg_value(0)
    if duty_on == 0 or not enabled_on or enabled_off:
        raise RuntimeError("PWM readback mismatch")
    d.fillRect(0, 0, 466, 10, d.COLOR.GREEN)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(20, 180)
    d.print(repr(exc)[:52])

d.setCursor(20, 70)
d.print("on=%d en=%d" % (duty_on, enabled_on))
d.setCursor(20, 100)
d.print("off=%d en=%d" % (duty_off, enabled_off))
d.setCursor(20, 140)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
