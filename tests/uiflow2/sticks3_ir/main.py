import M5
import time
from M5 import *
from hardware import IR


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 8)
d.print("StickS3 IR TX")

status = "init"
try:
    Power.setExtOutput(True)
    Speaker.setPA(False)
    ir = IR()
    ir.tx(0x56, 0xA3)
    status = "sent"
except Exception as exc:
    status = "error"
    d.setCursor(6, 84)
    d.print(repr(exc)[:38])

d.setCursor(6, 40)
d.print("addr=0x56 data=0xA3")
d.setCursor(6, 60)
d.print("status=%s" % status)

try:
    from hardware import UART
    log = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log = None
if log:
    log.write("STICKS3_IR status=%s\n" % status)

while True:
    M5.update()
    time.sleep_ms(50)
