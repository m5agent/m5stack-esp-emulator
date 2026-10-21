import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK, d.COLOR.WHITE)
d.setTextSize(3)
d.setCursor(24, 36)
d.print("PaperColor audio")

status = "init"
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.setVolumePercentage(0.6)
    Speaker.tone(440, 1000)
    time.sleep_ms(300)
    if not Speaker.isRunning():
        raise RuntimeError("speaker stopped")
    d.fillRect(0, 0, 400, 12, d.COLOR.BLACK)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(24, 100)
    d.print(repr(exc))

d.setCursor(24, 76)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
