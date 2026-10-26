import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(4, 4)
d.print("StamPLC buzzer")

status = "init"
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.tone(3500, 250)
    time.sleep_ms(300)
    if not Speaker.isRunning():
        raise RuntimeError("buzzer stopped")
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN)
    status = "ok 3500Hz"
except Exception as exc:
    status = "error: " + repr(exc)

d.setCursor(4, 24)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
