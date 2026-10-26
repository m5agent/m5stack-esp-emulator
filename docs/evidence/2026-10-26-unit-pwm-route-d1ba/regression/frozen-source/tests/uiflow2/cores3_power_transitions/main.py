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

seen = []
last = None
deadline = time.ticks_add(time.ticks_ms(), 12000)

while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    M5.update()
    value = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    if value != last:
        last = value
        seen.append(value)
        if log:
            log.write("CORES3_POWER_TRANS %d %d %d\n" % value)
    if value == (93, 4200, 1):
        break
    time.sleep_ms(100)

ok = seen[:1] == [(87, 4000, 1)] and (64, 3600, 0) in seen and seen[-1] == (93, 4200, 1)
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(2)
d.setCursor(12, 18)
d.print("CoreS3 PMIC transitions")
d.setTextSize(1)
for index, value in enumerate(seen[-4:]):
    d.setCursor(12, 60 + index * 18)
    d.print("%d%% %dmV chg=%d" % value)
d.fillRect(300, 220, 20, 20, d.COLOR.GREEN if ok else d.COLOR.RED)
if log:
    log.write("CORES3_POWER_TRANS_DONE %s\n" % ("PASS" if ok else "FAIL"))

while True:
    M5.update()
    time.sleep_ms(100)
