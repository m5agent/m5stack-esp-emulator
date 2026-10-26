import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("PaperColor RGB")

status = "init"
try:
    count = Led.getCount()
    if count < 2:
        raise RuntimeError("led count %d" % count)
    Led.setBrightness(255)
    Led.setColor(0, 0xFF0000)
    Led.setColor(1, 0x00FF00)
    Led.display()
    time.sleep_ms(200)
    d.fillRect(0, 0, 400, 8, d.COLOR.GREEN)
    status = "ok count=%d red,green" % count
except Exception as exc:
    status = "error: " + repr(exc)

d.setCursor(6, 34)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
