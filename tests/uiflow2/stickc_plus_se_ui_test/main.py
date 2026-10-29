import M5
import time
print("STICKC_PLUS_SE_MAIN_START")
M5.begin()
print("CLASSIC_BOARD", M5.getBoard())
M5.Display.setRotation(0)
M5.Display.setBrightness(255)
M5.Display.fillScreen(0)
M5.Display.fillRect(2, 2, 8, 8, 0xFF0000)
print("CLASSIC_DISPLAY", M5.Display.width(), M5.Display.height())
last = False
count = 0
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != last:
        if pressed:
            count += 1
        print("CLASSIC_BUTTON", int(pressed), count)
        M5.Display.fillRect(2, 2, 8, 8, 0x00FF00 if pressed else 0xFF0000)
        last = pressed
    time.sleep_ms(20)
