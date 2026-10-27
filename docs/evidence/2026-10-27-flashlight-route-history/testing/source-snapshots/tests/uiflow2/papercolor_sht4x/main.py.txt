import M5
from M5 import *
from hardware import SHT4X


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK, d.COLOR.WHITE)
d.setTextSize(3)
d.setCursor(24, 36)
d.print("PaperColor SHT4X")

status = "init"
try:
    sensor = SHT4X()
    temperature, humidity = sensor.measure()
    if abs(temperature - 25.0) > 1.0 or abs(humidity - 50.0) > 2.0:
        raise RuntimeError("SHT4X values %.2f/%.2f" % (temperature, humidity))
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
