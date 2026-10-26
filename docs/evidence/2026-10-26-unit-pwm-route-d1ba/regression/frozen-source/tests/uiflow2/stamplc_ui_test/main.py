# StamPLC local UI and front-panel key test for QEMU
import M5
import time

count = 0


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(3, 3, 233, 128, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(12, 12)
    d.print("StamPLC")
    d.setTextColor(d.COLOR.GREEN)
    d.setCursor(12, 48)
    d.print("keys: %d" % count)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(12, 85)
    d.print("Press front-panel A")
    d.fillRect(12, 102, 216, 22, d.COLOR.BLUE)
    d.setCursor(59, 108)
    d.print("INDUSTRIAL TEST")
    if count:
        d.fillRect(1, 1, 4, 4, d.COLOR.GREEN)


print("STAMPLC_MAIN_START")
M5.begin()
print("STAMPLC_BOARD", M5.getBoard())
print("STAMPLC_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setBrightness(255)
draw_ui()

was = False
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed and not was:
        count += 1
        print("STAMPLC_BTN_A", count)
        draw_ui()
    was = pressed
    time.sleep(0.02)
