import M5
import time
from M5 import *
from machine import Pin, UART
from driver.scs_servo import Scscl


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("StackChan servo")

status = "init"
try:
    uart = UART(1, baudrate=1000000, tx=Pin(6), rx=Pin(7))
    servo = Scscl(uart, end=1, level=1)
    if servo.ping(1) != 1 or servo.ping(2) != 2:
        raise RuntimeError("servo ping failed")
    if not servo.enable_torque(1, 1) or not servo.enable_torque(2, 1):
        raise RuntimeError("servo torque failed")
    if not servo.write_pos(1, 500, 100, 0):
        raise RuntimeError("servo X write failed")
    if not servo.write_pos(2, 300, 100, 0):
        raise RuntimeError("servo Y write failed")
    time.sleep_ms(50)
    x = servo.read_pos(1)
    y = servo.read_pos(2)
    if x != 500 or y != 300:
        raise RuntimeError("servo readback %d/%d" % (x, y))
    d.fillRect(0, 0, 320, 8, d.COLOR.GREEN)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(6, 80)
    d.print(repr(exc))

d.setCursor(6, 36)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
