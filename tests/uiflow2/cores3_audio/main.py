import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("CoreS3 audio")

status = "init"
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.setVolumePercentage(0.6)
    Speaker.tone(440, 1000)
    time.sleep_ms(300)
    if not Speaker.isRunning():
        raise RuntimeError("speaker stopped")
    d.fillRect(0, 0, 320, 8, d.COLOR.GREEN)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(6, 80)
    d.print(repr(exc))

d.setCursor(6, 36)
d.print("status=%s" % status)
from hardware import UART
_evidence_uart = UART(0, baudrate=115200, tx=43, rx=44)
_evidence_uart.write("CORES3_AUDIO_DRAW_COMPLETE " + status + "\n")

while True:
    M5.update()
    time.sleep_ms(100)
