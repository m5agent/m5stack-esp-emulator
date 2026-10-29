import M5
import time

count = 0


def draw_counter():
    display = M5.Display
    display.fillRect(8, 50, 112, 30, 0x000000)
    display.setTextColor(0x00FF00, 0x000000)
    display.setTextSize(2)
    display.setCursor(8, 54)
    display.print("count:%d" % count)
    display.fillRect(1, 1, 8, 8, 0x00FF00 if count else 0xFF0000)


print("ATOMS3_MAIN_START")
M5.begin()
print("ATOMS3_M5_BEGIN_OK")
print("ATOMS3_BOARD", M5.getBoard())
print("ATOMS3_DISPLAY", M5.Display.width(), M5.Display.height())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
M5.Display.fillScreen(0x000000)
M5.Display.drawRect(3, 3, 121, 121, 0x0000FF)
M5.Display.setTextColor(0xFFFFFF, 0x000000)
M5.Display.setTextSize(2)
M5.Display.setCursor(8, 16)
M5.Display.print("AtomS3")
M5.Display.setTextSize(1)
M5.Display.setCursor(8, 104)
M5.Display.print("C123 / GPIO41")
draw_counter()

was_pressed = False
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed and not was_pressed:
        count += 1
        print("ATOMS3_BTN_A", count)
        draw_counter()
    elif was_pressed and not pressed:
        print("ATOMS3_BTN_A_RELEASED", count)
    was_pressed = pressed
    time.sleep_ms(20)
