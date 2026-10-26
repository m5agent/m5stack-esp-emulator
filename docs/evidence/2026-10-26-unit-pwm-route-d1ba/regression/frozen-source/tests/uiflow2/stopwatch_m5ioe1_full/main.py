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
d.setCursor(40, 60)
d.print("StopWatch M5IOE1 full")

ok = False
detail = "init"
try:
    i2c = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
    ioe = M5IOE1(i2c, 0x4F)

    ioe.set_pin_mode(1, 0)
    ioe.set_pin_pull(1, 1)
    ioe.set_pin_mode(8, 1)
    ioe.set_pin_drive(8, 0)
    ioe.set_pin_value(8, 1)
    output_readback = ioe.read_pin(8)

    while not BtnA.wasPressed():
        M5.update()
        time.sleep_ms(10)
    injected_input = ioe.read_pin(1)
    adc_raw = ioe.read_adc_raw(2)
    ioe.set_pwm_duty_u12(0, 2048)
    pwm_duty = ioe.get_pwm_duty_u12(0)
    detail = "out=%d in=%d adc=%d pwm=%d" % (
        output_readback, injected_input, adc_raw, pwm_duty,
    )
    if (output_readback != 1 or injected_input != 0
            or adc_raw <= 0 or pwm_duty != 2048):
        raise RuntimeError(detail)
    ok = True
except Exception as exc:
    detail = repr(exc)[:64]

d.fillRect(0, 0, 466, 10, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(42, 120)
d.print(detail)
d.setCursor(42, 160)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
