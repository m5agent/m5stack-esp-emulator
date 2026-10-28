"""Isolate one even-aligned StopWatch drawPixel transaction for host tracing."""
import time

import M5


M5.begin()
M5.Display.setBrightness(255)
M5.Display.setRotation(0)
M5.Display.drawPixel(76, 146, 0x38B8C8)
for _ in range(50):
    M5.update()
    time.sleep_ms(20)
print("DRAW_PIXEL_TRACE_DONE")
