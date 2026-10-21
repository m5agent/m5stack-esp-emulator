# UIFlow2 local UI test for M5Stack StopWatch QEMU
import M5
import time

touches = 0
last = "READY - tap the blue button"
last_color = None


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawCircle(233, 233, 228, d.COLOR.BLUE)

    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(110, 70)
    d.print("UIFlow2 UI")

    d.setTextSize(1)
    d.setCursor(150, 102)
    d.print("StopWatch QEMU")

    d.setTextSize(2)
    d.setTextColor(d.COLOR.GREEN)
    d.setCursor(160, 160)
    d.print("touches: %d" % touches)

    d.setTextSize(1)
    d.setTextColor(last_color if last_color is not None else d.COLOR.WHITE)
    d.setCursor(80, 196)
    d.print(last)

    d.fillCircle(233, 300, 68, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(3)
    d.setCursor(195, 285)
    d.print("TAP")


M5.begin()
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
draw_ui()

was_pressed = False
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    if pressed:
        x = M5.Touch.getX()
        y = M5.Touch.getY()
        if not was_pressed:
            if (x - 233) * (x - 233) + (y - 300) * (y - 300) <= 68 * 68:
                touches += 1
                last = "BUTTON OK count=%d" % touches
                last_color = M5.Display.COLOR.GREEN
            else:
                last = "TOUCH %d,%d" % (x, y)
                last_color = M5.Display.COLOR.YELLOW
            draw_ui()
        M5.Display.fillCircle(x, y, 10, last_color)
    was_pressed = pressed
    time.sleep(0.02)
