import M5
import sys
import time
from M5 import Widgets

try:
    print("CORE2_STARTUP:widgets:BEGIN")
    M5.begin()
    Widgets.setRotation(1)
    Widgets.setBrightness(100)
    Widgets.fillScreen(0x101418)
    title = Widgets.Label("START", 8, 4, 1.0, 0xFFFFFF, 0x101418, Widgets.FONTS.DejaVu24)
    page = Widgets.Label("1/4", 270, 10, 1.0, 0xAAAAAA, 0x101418, Widgets.FONTS.DejaVu18)
    names = []
    values = []
    for index in range(5):
        names.append(Widgets.Label("Sensor %d" % index, 8, 44 + index * 28, 1.0,
                                   0xFFFFFF, 0x101418, Widgets.FONTS.DejaVu18))
        values.append(Widgets.Label("offline", 200, 44 + index * 28, 1.0,
                                    0xAAAAAA, 0x101418, Widgets.FONTS.DejaVu18))
    print("CORE2_STARTUP:widgets:READY")
    for step in range(100):
        M5.update()
        time.sleep_ms(20)
    print("CORE2_STARTUP:widgets:DONE")
except Exception as error:
    print("CORE2_STARTUP:widgets:ERROR")
    sys.print_exception(error)
    raise
