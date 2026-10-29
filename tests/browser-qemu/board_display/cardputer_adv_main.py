import json
import time

import M5
import machine
from hardware import KeyboardI2C
from browser_probe_config import DEVICE_ID, ROTATION, INPUT_MODE


count = 0
sequence = 0
pressed_keys = {}


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["device"] = DEVICE_ID
    fields["kind"] = kind
    fields["seq"] = sequence
    print("M5_BROWSER_PROBE " + json.dumps(fields))


def draw_count():
    d.fillRect(8, height // 2, width - 16, 30, 0x102030)
    d.setCursor(8, height // 2 + 6)
    d.setTextColor(0xFFFFFF)
    d.print("Count: %d" % count)
    if count:
        d.fillRect(2, 2, 8, 8, 0x00FF00)


def draw_key_state(keycode, pressed):
    d.fillRect(width - 12, 2, 8, 8, 0xFFCC44 if pressed else 0x2176FF)
    d.fillRect(8, height - 24, width - 16, 16, 0x102030)
    d.setTextColor(0xFFFFFF)
    d.setCursor(8, height - 22)
    d.print("Key:%s %s" % (keycode if keycode is not None else "--",
                          "DOWN" if pressed else "UP"))


emit("begin")
if DEVICE_ID != "cardputer-adv" or INPUT_MODE != "keyboard":
    raise ValueError("Cardputer-ADV keyboard probe configuration mismatch")
M5.begin()
d = M5.Display
d.setRotation(ROTATION)
d.setBrightness(255)
width, height = d.width(), d.height()
d.fillScreen(0x102030)
d.drawRect(1, 1, width - 2, height - 2, 0x2176FF)
d.fillRect(2, 2, 8, 8, 0xFF0000)
d.setTextSize(1)
d.setTextColor(0xFFFFFF)
d.setCursor(8, 20)
d.print(DEVICE_ID)
d.setCursor(8, 38)
d.print("TCA8418 / keyboard")
draw_count()
draw_key_state(None, False)

i2c = machine.I2C(1, scl=machine.Pin(9), sda=machine.Pin(8), freq=400000)
intr = machine.Pin(11, mode=machine.Pin.IN, pull=None)
keyboard = KeyboardI2C(i2c, intr_pin=intr, mode=KeyboardI2C.ASCII_MODE)
emit("ready", board=M5.getBoard(), width=width, height=height,
     input=INPUT_MODE, controller="tca8418",
     address=0x34, receive_mode="official-driver-fifo-poll")
heartbeat = time.ticks_ms()
while True:
    M5.update()
    # Poll the original driver IRQ handler over guest I2C. GPIO IRQ delivery is
    # a separate boundary; no host/UART values are substituted for FIFO data.
    keyboard._irq_handler(intr)
    while keyboard._keyevents:
        event = keyboard._keyevents.pop(0)
        keycode = event.keycode
        emit("pressed", keycode=keycode, row=event.row, col=event.col,
             count=count, driver_pressed=keyboard.is_key_pressed(keycode))
        pressed_keys[keycode] = (event.row, event.col)
        count += 1
        draw_count()
        draw_key_state(keycode, True)
        emit("count", count=count, keycode=keycode,
             row=event.row, col=event.col, driver_state=event.state)
    # ASCII callbacks retain presses only. The same official decoder updates
    # is_key_pressed() from both FIFO edges, so release is not inferred by time.
    for keycode in tuple(pressed_keys):
        if not keyboard.is_key_pressed(keycode):
            row, col = pressed_keys.pop(keycode)
            draw_key_state(keycode, False)
            emit("released", keycode=keycode, row=row, col=col,
                 count=count, driver_pressed=False)
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count,
             pressed_keycodes=list(pressed_keys))
        heartbeat = now
    time.sleep_ms(20)
