"""Decode path/buffer and default/explicit-size image argument domains.

Run only inside a live package directory containing fixture.png, fixture.bmp
and fixture.jpg. The retained frame is reviewed by the host; this guest probe
does not synthesize image pixels.
"""
import json
import os

import M5


M5.begin()
M5.Lcd.setBrightness(255)
M5.Lcd.setRotation(0)
M5.Lcd.fillScreen(0x0B1014)

source_png = os.getcwd() + "/fixture.png"
source_bmp = os.getcwd() + "/fixture.bmp"
source_jpg = os.getcwd() + "/fixture.jpg"
png = "/flash/api-sweep-fixture.png"
bmp = "/flash/api-sweep-fixture.bmp"
jpg = "/flash/api-sweep-fixture.jpg"
for source, target in ((source_png, png), (source_bmp, bmp), (source_jpg, jpg)):
    with open(source, "rb") as stream:
        data = stream.read()
    with open(target, "wb") as stream:
        stream.write(data)
with open(png, "rb") as stream:
    png_data = stream.read()
with open(bmp, "rb") as stream:
    bmp_data = stream.read()
with open(jpg, "rb") as stream:
    jpg_data = stream.read()

width, height = M5.Lcd.width(), M5.Lcd.height()
left = max(4, (width - 4 * 24) // 2)
top = max(40, (height - 3 * 24) // 2)
tests = [
    ("drawPng.path.default", lambda x, y: M5.Lcd.drawPng(png, x, y)),
    ("drawPng.path.explicit", lambda x, y: M5.Lcd.drawPng(png, x, y, 16, 16, 0, 0)),
    ("drawPng.bytes", lambda x, y: M5.Lcd.drawPng(png_data, x, y, 16, 16, 0, 0)),
    ("drawImage.path.default", lambda x, y: M5.Lcd.drawImage(png, x, y)),
    ("drawImage.path.explicit", lambda x, y: M5.Lcd.drawImage(png, x, y, 16, 16, 0, 0)),
    ("drawImage.bytes", lambda x, y: M5.Lcd.drawImage(png_data, x, y, 16, 16, 0, 0)),
    ("drawBmp.path.default", lambda x, y: M5.Lcd.drawBmp(bmp, x, y)),
    ("drawBmp.path.explicit", lambda x, y: M5.Lcd.drawBmp(bmp, x, y, 16, 16, 0, 0)),
    ("drawBmp.bytes", lambda x, y: M5.Lcd.drawBmp(bmp_data, x, y, 16, 16, 0, 0)),
    ("drawJpg.path.default", lambda x, y: M5.Lcd.drawJpg(jpg, x, y)),
    ("drawJpg.path.explicit", lambda x, y: M5.Lcd.drawJpg(jpg, x, y, 16, 16, 0, 0)),
    ("drawJpg.bytes", lambda x, y: M5.Lcd.drawJpg(jpg_data, x, y, 16, 16, 0, 0)),
]
placements = []
for index, (name, action) in enumerate(tests):
    x = left + (index % 4) * 24
    y = top + (index // 4) * 24
    try:
        action(x, y)
        status = "CALLED"
    except Exception as error:
        status = "ERROR"
        name += ":" + repr(error)
    placements.append({"name": name, "x": x, "y": y, "status": status})

for _ in range(20):
    M5.update()
print("M5EMU_IMAGE_ARGUMENTS " + json.dumps({"width": width, "height": height, "placements": placements}))
print("IMAGE_ARGUMENT_DOMAINS_DONE")
