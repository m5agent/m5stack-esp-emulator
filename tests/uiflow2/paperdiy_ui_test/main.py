# UIFlow2 guest probe for the A/B GPIO inputs and ET047TC1 framebuffer.
import M5
import time

M5.begin()
display = M5.Display
display.setRotation(0)
display.fillScreen(display.COLOR.WHITE)
display.fillRect(16, 60, 120, 36, display.COLOR.BLACK)
print("PAPERDIY_READY", display.width(), display.height())
seen_a = False
seen_b = False

while True:
    M5.update()
    if not seen_a and M5.BtnA.isPressed():
        seen_a = True
        print("PAPERDIY_KEY_A")
        display.fillRect(16, 16, 32, 32, display.COLOR.BLACK)
    if not seen_b and M5.BtnB.isPressed():
        seen_b = True
        print("PAPERDIY_KEY_B")
        display.fillRect(60, 16, 32, 32, display.COLOR.BLACK)
    time.sleep_ms(20)
