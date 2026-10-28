"""Check standalone Python drawPixel calls on a framebuffer-backed panel."""
import json
import time

import M5


M5.begin()
M5.Display.setBrightness(255)
M5.Display.setRotation(0)
M5.Display.fillScreen(0x0B1014)
M5.Display.startWrite()
M5.Display.drawPixel(80, 150, 0xFF0000)
M5.Display.drawPixel(81, 151, 0x00FF00)
M5.Display.endWrite()
M5.Display.drawPixel(76, 146, 0x38B8C8)
M5.Display.drawPixel(77, 147, 0xF3F7F8)
for _ in range(50):
    M5.update()
    time.sleep_ms(20)
print("M5EMU_UI_FRAME_ORACLE " + json.dumps({
    "method": "drawPixel",
    "oracle": {
        "kind": "pixels",
        "points": [
            [76, 146, 0x38B8C8],
            [77, 147, 0xF3F7F8],
            [80, 150, 0xFF0000],
            [81, 151, 0x00FF00],
            [77, 146, 0x0B1014],
            [76, 147, 0x0B1014],
        ],
    },
    "tolerance": 8,
}))
print("DRAW_PIXEL_TRANSACTION_DONE")
