import M5
from hardware import RGB
import time
print("ATOMS3_LITE_MAIN_START")
M5.begin()
print("ATOMS3_LITE_M5_BEGIN_OK")
print("ATOMS3_LITE_BOARD", M5.getBoard())
rgb = RGB()
rgb.set_brightness(100)
rgb.set_color(0, 0x204060)
print("ATOMS3_LITE_RGB", 0x204060)
pressed_before = False
count = 0
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != pressed_before:
        if pressed:
            count += 1
        rgb.set_color(0, 0x40A020 if pressed else 0x204060)
        print("ATOMS3_LITE_BUTTON", int(pressed), count)
        pressed_before = pressed
    time.sleep_ms(20)
