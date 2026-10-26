import M5
import time
from M5 import *


M5.begin()
log = None
try:
    from hardware import UART
    log = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log = None
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK, d.COLOR.WHITE)
d.setTextSize(2)
d.setCursor(24, 36)
d.print("PaperMono buzzer")

status = "init"
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.setVolume(255)
    Speaker.tone(3500, 15000)
    time.sleep_ms(250)
    if not Speaker.isRunning():
        raise RuntimeError("buzzer stopped")
    status = "ok 3500Hz"
    d.fillRect(0, 0, 480, 12, d.COLOR.BLACK)
except Exception as error:
    status = repr(error)[:58]
    d.fillRect(0, 0, 480, 12, d.COLOR.BLACK)

if log:
    log.write("PAPERMONO_BUZZER %s\n" % status)
d.setCursor(24, 100)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
