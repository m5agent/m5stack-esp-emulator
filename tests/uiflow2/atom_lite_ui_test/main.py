import M5
import time
print("ATOM_LITE_MAIN_START")
M5.begin()
print("CLASSIC_BOARD", M5.getBoard())
from hardware import RGB
rgb = RGB(io=27, n=1, type="WS2812")
rgb.set_brightness(100)
rgb.fill_color(0x204060)
print("CLASSIC_RGB", 1, "204060")
last = False
count = 0
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != last:
        if pressed:
            count += 1
        print("CLASSIC_BUTTON", int(pressed), count)
        rgb.fill_color(0x40A020 if pressed else 0x204060)
        last = pressed
    time.sleep_ms(20)
