# Tab5 UIFlow2 UI and touch test for the ESP32-P4 virtual host.
import M5
import time

touches = 0
status = "Tap the blue target"
status_color = None


def draw_ui():
    d = M5.Display
    width = d.width()
    height = d.height()
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(8, 8, width - 16, height - 16, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(6)
    d.setCursor(42, 42)
    d.print("Tab5")
    d.setTextSize(2)
    d.setCursor(46, 108)
    d.print("UIFlow2 ESP32-P4 emulator %dx%d" % (width, height))

    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(4)
    d.setCursor(46, 180)
    d.print("touches: %d" % touches)

    d.setTextColor(status_color if status_color is not None else d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(46, 270)
    d.print(status)

    d.fillRect(390, 430, 500, 180, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(6)
    d.setCursor(565, 495)
    d.print("TAP")


print("TAB5_MAIN_START")
M5.begin()
print("TAB5_BOARD", M5.getBoard())
M5.Display.setRotation(1)
print("TAB5_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setBrightness(255)
draw_ui()
print("TAB5_UI_DRAWN", M5.Display.width(), M5.Display.height())

was_pressed = False
while True:
    M5.update()
    pressed = M5.Touch.getCount() > 0
    if pressed:
        x = M5.Touch.getX()
        y = M5.Touch.getY()
        if not was_pressed:
            if 390 <= x <= 890 and 430 <= y <= 610:
                touches += 1
                status = "TOUCH OK count=%d" % touches
                status_color = M5.Display.COLOR.GREEN
            else:
                status = "TOUCH %d,%d" % (x, y)
                status_color = M5.Display.COLOR.YELLOW
            print("TAB5_TOUCH", x, y, touches)
            draw_ui()
            print("TAB5_DRAW_AFTER_TOUCH", touches)
    was_pressed = pressed
    time.sleep(0.02)
