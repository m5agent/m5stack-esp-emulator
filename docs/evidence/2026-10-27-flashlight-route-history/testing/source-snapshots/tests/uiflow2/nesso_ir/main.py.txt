import M5
import time
from M5 import *
from hardware import IR


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 12)
d.print("Nesso N1 IR TX")

ok = False
detail = "init"
try:
    IR().tx(0x56, 0xA3)
    detail = "addr=0x56 cmd=0xA3"
    ok = True
except Exception as exc:
    detail = repr(exc)[:52]

d.fillRect(0, 0, 240, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(8, 48)
d.print(detail)
d.setCursor(8, 76)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
