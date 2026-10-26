# Core2 local UI and touch test for QEMU
import M5
import time

touches = 0
last_touch = (-1, -1)


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(4, 4, 311, 231, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(3)
    d.setCursor(18, 18)
    d.print("Core2")
    d.setTextSize(1)
    d.setCursor(20, 55)
    d.print("UIFlow2 QEMU 320x240")
    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(2)
    d.setCursor(20, 88)
    d.print("touches: %d" % touches)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(20, 125)
    d.print("last: %d,%d" % last_touch)
    d.fillRect(55, 153, 210, 60, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(111, 171)
    d.print("TOUCH")
    if touches:
        d.fillRect(1, 1, 4, 4, d.COLOR.GREEN)


print("CORE2_MAIN_START")
M5.begin()
print("CORE2_BOARD", M5.getBoard())
print("CORE2_DISPLAY", M5.Display.width(), M5.Display.height())
print("CORE2_SET_ROTATION")
# ILI9342 uses offset_rotation=3; rotation 1 is landscape 320x240.
M5.Display.setRotation(1)
print("CORE2_SET_BRIGHTNESS")
M5.Display.setBrightness(255)
print("CORE2_DRAW")
draw_ui()
print("CORE2_LOOP")

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
            print("CORE2_TOUCH", x, y, touches)
            draw_ui()
    was_pressed = pressed
    time.sleep(0.02)
