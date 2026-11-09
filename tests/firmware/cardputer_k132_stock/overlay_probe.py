# Cardputer K132's stock GPIO keyboard driver and board display.
import time

import M5
from hardware import Keyboard

M5.begin()
display = M5.Display
display.setRotation(0)
display.fillScreen(0x101820)
keyboard = Keyboard()
print("K132_DISPLAY", display.width(), display.height())
previous = None
while True:
    M5.update()
    keyboard.update_key_list()
    keys = tuple((point.x, point.y) for point in keyboard.key_list())
    if keys != previous:
        keyboard.update_keys_state()
        state = keyboard.keys_state()
        print("K132_MATRIX", keys, state.word, state.fn, state.shift)
        if state.word == ["a"]:
            display.fillRect(0, 0, 8, 8, 0x00FF00)
        previous = keys
    time.sleep_ms(10)
