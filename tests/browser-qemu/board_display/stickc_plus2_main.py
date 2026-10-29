import json
import time

import M5
from browser_probe_config import DEVICE_ID, ROTATION


sequence = 0
counts = [0, 0, 0]
was_pressed = [False, False, False]
labels = ("a", "b", "power")
gpios = (37, 39, 35)
colors = (0x00FF00, 0x0000FF, 0xFFFFFF)


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["device"] = DEVICE_ID
    fields["kind"] = kind
    fields["seq"] = sequence
    print("M5_BROWSER_PROBE " + json.dumps(fields))


def draw_button(index, pressed):
    y = 72 + index * 36
    display.fillRect(8, y, width - 16, 24, 0x102030)
    display.setCursor(8, y + 8)
    display.setTextColor(0xFFFFFF)
    display.print("%s: %d" % (labels[index], counts[index]))
    display.fillRect(width - 18, y + 8, 8, 8, colors[index] if pressed else 0x102030)
    if counts[0]:
        display.fillRect(2, 2, 8, 8, 0x00FF00)


emit("begin")
M5.begin()
display = M5.Display
display.setRotation(ROTATION)
display.setBrightness(255)
width, height = display.width(), display.height()
display.fillScreen(0x102030)
display.drawRect(1, 1, width - 2, height - 2, 0x2176FF)
display.fillRect(2, 2, 8, 8, 0xFF0000)
display.setTextSize(1)
display.setTextColor(0xFFFFFF)
display.setCursor(8, 20)
display.print(DEVICE_ID)
display.setCursor(8, 38)
display.print("C/QEMU browser")
buttons = (M5.BtnA, M5.BtnB, M5.BtnPWR)
for index in range(3):
    draw_button(index, False)
emit("ready", board=M5.getBoard(), width=width, height=height, input="button", buttons=labels)
heartbeat = time.ticks_ms()
while True:
    M5.update()
    for index in range(3):
        pressed = buttons[index].isPressed()
        if pressed != was_pressed[index]:
            kind = "pressed" if pressed else "released"
            if index:
                kind = "button-" + kind
            emit(kind, button=labels[index], gpio=gpios[index], pressed=pressed, count=counts[index])
            if pressed:
                counts[index] += 1
                emit("count" if not index else "button-count", button=labels[index], gpio=gpios[index], pressed=True, count=counts[index])
            draw_button(index, pressed)
            was_pressed[index] = pressed
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=counts[0], button_counts=counts)
        heartbeat = now
    time.sleep_ms(25)
