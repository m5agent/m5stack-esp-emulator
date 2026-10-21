import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 8)
d.print("Nesso N1 buzzer")

status = "init"
ok = False
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.tone(3500, 250)
    time.sleep_ms(300)
    if not Speaker.isRunning():
        raise RuntimeError("buzzer stopped")
    status = "ok 3500Hz"
    ok = True
except Exception as exc:
    status = repr(exc)[:58]

d.drawRect(2, 2, 131, 236, d.COLOR.BLUE)
d.fillRect(0, 0, 240, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(8, 42)
d.print(status)
d.setCursor(8, 78)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
