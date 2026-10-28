"""Observe RGB565 byte order and swap behavior for drawRawBuf."""
import json

import M5


M5.begin()
M5.Lcd.setBrightness(255)
M5.Lcd.setRotation(0)
M5.Lcd.fillScreen(0x0B1014)
width, height = M5.Lcd.width(), M5.Lcd.height()
left = max(4, (width - 4 * 24) // 2)
top = max(40, (height - 24) // 2)
cases = [
    ("f800.swap_false.pixels", bytearray([0xF8, 0x00] * 256), False, 256),
    ("00f8.swap_false.pixels", bytearray([0x00, 0xF8] * 256), False, 256),
    ("f800.swap_true.pixels", bytearray([0xF8, 0x00] * 256), True, 256),
    ("00f8.swap_true.pixels", bytearray([0x00, 0xF8] * 256), True, 256),
]
placements = []
for index, (name, data, swap, length) in enumerate(cases):
    x = left + index * 24
    y = top
    try:
        M5.Lcd.drawRawBuf(data, x, y, 16, 16, length, swap)
        status = "CALLED"
    except Exception as error:
        status = "ERROR"
        name += ":" + repr(error)
    placements.append({"name": name, "x": x, "y": y, "status": status})

for _ in range(20):
    M5.update()
print("M5EMU_RAW_BUFFER_ARGUMENTS " + json.dumps({"width": width, "height": height, "placements": placements}))
print("RAW_BUFFER_ARGUMENTS_DONE")
