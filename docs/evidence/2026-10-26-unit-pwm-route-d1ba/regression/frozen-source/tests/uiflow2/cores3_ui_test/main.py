# CoreS3 local UI and touch test for QEMU
import M5
import time

touches = 0
status = "Tap the blue target"
status_color = None


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(4, 4, 311, 231, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(3)
    d.setCursor(18, 18)
    d.print("CoreS3")
    d.setTextSize(1)
    d.setCursor(20, 55)
    d.print("UIFlow2 QEMU 320x240")
    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(2)
    d.setCursor(20, 88)
    d.print("touches: %d" % touches)
    d.setTextColor(status_color if status_color is not None else d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(20, 125)
    d.print(status)
    d.fillRect(55, 153, 210, 60, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(111, 171)
    d.print("TAP")
    if touches:
        d.fillRect(1, 1, 4, 4, d.COLOR.GREEN)


print("CORES3_MAIN_START")
M5.begin()
print("CORES3_BOARD", M5.getBoard())
print("CORES3_DISPLAY", M5.Display.width(), M5.Display.height())
# CoreS3's M5GFX panel uses offset_rotation=3, so rotation 1 is landscape 320x240.
M5.Display.setRotation(1)
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
            if 55 <= x <= 265 and 153 <= y <= 213:
                touches += 1
                status = "TOUCH OK count=%d" % touches
                status_color = M5.Display.COLOR.GREEN
            else:
                status = "TOUCH %d,%d" % (x, y)
                status_color = M5.Display.COLOR.YELLOW
            print("CORES3_TOUCH", x, y, touches)
            draw_ui()
        M5.Display.fillCircle(x, y, 8, status_color)
    was_pressed = pressed
    time.sleep(0.02)
