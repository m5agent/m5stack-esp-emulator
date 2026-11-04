import json
import time

import M5
from hardware import MatrixKeyboard


# The caller prepends RUN_NONCE and KEY_CODES. Expectations stay on the host.
# No private ISR, direct FIFO read, tick() or replacement Pin.irq handler.
M5.begin()
assert M5.getBoard() == M5.BOARD.M5CardputerADV, "wrong original guest board"
keyboard = MatrixKeyboard()
sequence = 0
callback_count = 0
previous = {}
heartbeat = time.ticks_ms()


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["kind"] = kind
    fields["nonce"] = RUN_NONCE
    fields["seq"] = sequence
    fields["guest_ms"] = time.ticks_ms()
    print("M5_CARDPUTER_KEYBOARD " + json.dumps(fields))


def sample_states():
    for code in KEY_CODES:
        pressed = keyboard.is_key_pressed(code)
        if pressed != previous[code]:
            previous[code] = pressed
            emit("state", code=code, pressed=pressed)


def key_event(active):
    global callback_count
    callback_count += 1
    codes = []
    while True:
        code = keyboard.get_key()
        if code is None:
            break
        codes.append(code)
    emit("callback", codes=codes, callback_count=callback_count,
         callback_type=type(active).__name__)
    sample_states()


try:
    for code in KEY_CODES:
        previous[code] = keyboard.is_key_pressed(code)
    keyboard.set_callback(key_event)
    emit("ready", board=M5.getBoard(), states=previous,
         pending=keyboard.is_pressed(), api="MatrixKeyboard.set_callback")
    while True:
        # On ADV is_key_pressed reads the state updated by the original IRQ
        # driver. It does not read the TCA8418 FIFO or scan GPIO keys.
        sample_states()
        now = time.ticks_ms()
        if time.ticks_diff(now, heartbeat) >= 1000:
            emit("heartbeat", pressed=[code for code in KEY_CODES if previous[code]],
                 callback_count=callback_count)
            heartbeat = now
        time.sleep_ms(10)
finally:
    keyboard.deinit()
    emit("deinit", callback_count=callback_count)
