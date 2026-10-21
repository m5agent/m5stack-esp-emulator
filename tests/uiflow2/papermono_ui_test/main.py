# PaperMono local UI and touch test for QEMU
import M5
import time

touches = 0
last_touch = (-1, -1)


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.WHITE)
    d.drawRect(8, 8, 463, 783, d.COLOR.BLACK)
    d.setTextColor(d.COLOR.BLACK)
    d.setTextSize(3)
    d.setCursor(32, 35)
    d.print("PaperMono")
    d.setTextSize(1)
    d.setCursor(34, 80)
    d.print("UIFlow2 QEMU 480x800")
    d.setTextSize(4)
    d.setCursor(34, 180)
    d.print("touches: %d" % touches)
    d.setTextSize(2)
    d.setCursor(34, 300)
    d.print("last: %d,%d" % last_touch)
    d.fillRect(80, 600, 320, 100, d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(3)
    d.setCursor(170, 635)
    d.print("TOUCH")


print("PAPERMONO_MAIN_START")
M5.begin()
print("PAPERMONO_BOARD", M5.getBoard())
print("PAPERMONO_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
draw_ui()

was_pressed = False
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    if pressed:
        x = M5.Touch.getX()
        y = M5.Touch.getY()
        if not was_pressed:
            touches += 1
            last_touch = (x, y)
            print("PAPERMONO_TOUCH", x, y, touches)
            draw_ui()
    was_pressed = pressed
    time.sleep(0.05)
