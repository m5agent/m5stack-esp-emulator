# AtomS3R local UI test for QEMU
import M5
import time

count = 0


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(3, 3, 121, 121, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(8, 12)
    d.print("AtomS3R")
    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(2)
    d.setCursor(8, 54)
    d.print("count:%d" % count)
    d.fillRect(8, 92, 111, 27, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(13, 101)
    d.print("BTN A REDRAW")


print("ATOMS3R_MAIN_START")
M5.begin()
print("ATOMS3R_M5_BEGIN_OK")
print("ATOMS3R_BOARD", M5.getBoard())
print("ATOMS3R_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
draw()

was = False
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed and not was:
        count += 1
        print("ATOMS3R_BTN_A", count)
        draw()
    was = pressed
    time.sleep(0.02)
