# UIFlow2 guest probe for GT911 input and the ET047TC1 framebuffer.
import M5
import time

M5.begin()
display = M5.Display
display.setRotation(0)
display.fillScreen(display.COLOR.WHITE)
display.fillRect(16, 60, 120, 36, display.COLOR.BLACK)
print("PAPERS3_READY", display.width(), display.height())

while True:
    M5.update()
    if M5.Touch.getCount():
        print("PAPERS3_TOUCH", M5.Touch.getX(), M5.Touch.getY())
        display.fillRect(16, 16, 32, 32, display.COLOR.BLACK)
        break
    time.sleep_ms(20)

while True:
    M5.update()
    time.sleep_ms(20)
