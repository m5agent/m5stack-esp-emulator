import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("StopWatch mic")

status = "init"
try:
    if not Mic.begin():
        raise RuntimeError("mic begin failed")
    data = bytearray(12800)
    if not Mic.record(data, 16000, False):
        raise RuntimeError("record failed")
    deadline = time.ticks_add(time.ticks_ms(), 2500)
    while Mic.isRecording() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(20)
    Mic.end()
    nonzero = sum(1 for value in data if value)
    peak = max(data) - min(data)
    if nonzero < 100 or peak < 10:
        raise RuntimeError("silent pcm %d/%d" % (nonzero, peak))
    d.fillRect(0, 0, 466, 8, d.COLOR.GREEN)
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
