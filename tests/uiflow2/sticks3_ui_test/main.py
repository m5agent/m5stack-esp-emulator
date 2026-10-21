# StickS3 local UI test for QEMU
import M5
import time

count = 0


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(8, 12)
    d.print("StickS3")
    d.setTextSize(1)
    d.setCursor(8, 42)
    d.print("UIFlow2 QEMU")
    d.drawRect(4, 4, 127, 232, d.COLOR.BLUE)
    d.fillRect(8, 150, 119, 56, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(20, 166)
    d.print("BTN A")
    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(2)
    d.setCursor(8, 90)
    d.print("count: %d" % count)


print("STICKS3_MAIN_START")
M5.begin()
print("STICKS3_M5_BEGIN_OK")
print("STICKS3_BOARD", M5.getBoard())
print("STICKS3_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
draw()

was = False
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed and not was:
        count += 1
        print("STICKS3_BTN_A", count)
        draw()
    was = pressed
    time.sleep(0.02)
