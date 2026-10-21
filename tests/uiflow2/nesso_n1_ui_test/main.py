# Arduino Nesso N1 UI and touch test for the ESP32-C6 virtual host.
import M5
import time

touches = 0
last_touch = (-1, -1)


def draw_ui():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(2, 2, 130, 235, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(10, 12)
    d.print("Nesso N1")
    d.setTextSize(1)
    d.setCursor(10, 42)
    d.print("UIFlow2 QEMU 135x240")
    d.setTextColor(d.COLOR.GREEN)
    d.setTextSize(2)
    d.setCursor(10, 78)
    d.print("touches: %d" % touches)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(10, 112)
    d.print("last: %d,%d" % last_touch)
    d.fillRect(18, 150, 99, 54, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(38, 168)
    d.print("TOUCH")


print("NESSO_N1_MAIN_START")
M5.begin()
print("NESSO_N1_BOARD", M5.getBoard())
print("NESSO_N1_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
draw_ui()
print("NESSO_N1_LOOP")

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
            print("NESSO_N1_TOUCH", x, y, touches)
            draw_ui()
    was_pressed = pressed
    time.sleep(0.02)
