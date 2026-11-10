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
pressed_codes = set()
pending = []
heartbeat = time.ticks_ms()


def record(kind, guest_ms, **fields):
    fields["kind"] = kind
    fields["guest_ms"] = guest_ms
    pending.append(fields)


def flush_events():
    global pending, sequence
    if not pending:
        return
    batch, pending = pending, []
    for fields in batch:
        sequence += 1
        fields["nonce"] = RUN_NONCE
        fields["seq"] = sequence
        print("M5_CARDPUTER_KEYBOARD " + json.dumps(fields))


def sample_state(code):
    pressed = keyboard.is_key_pressed(code)
    if pressed != (code in pressed_codes):
        if pressed:
            pressed_codes.add(code)
        else:
            pressed_codes.discard(code)
        record("state", time.ticks_ms(), code=code, pressed=pressed)


def sample_active_states():
    if pressed_codes:
        for code in tuple(pressed_codes):
            sample_state(code)


def key_event(active):
    global callback_count
    # The original ADV driver queues every press code with its callback.
    # Sample its current public state immediately. A code can still be
    # queued when the driver's event batch has already released the key.
    callback_count += 1
    codes = []
    record("callback", time.ticks_ms(), codes=codes, callback_count=callback_count,
           callback_type=type(active).__name__)
    while True:
        code = keyboard.get_key()
        if code is None:
            break
        codes.append(code)
        sample_state(code)


try:
    initial_states = {code: keyboard.is_key_pressed(code) for code in KEY_CODES}
    keyboard.set_callback(key_event)
    record("ready", time.ticks_ms(), board=M5.getBoard(), states=initial_states,
           pending=keyboard.is_pressed(), api="MatrixKeyboard.set_callback")
    flush_events()
    while True:
        # On ADV is_key_pressed reads the state updated by the original IRQ
        # driver. It does not read the TCA8418 FIFO or scan GPIO keys.
        sample_active_states()
        now = time.ticks_ms()
        if time.ticks_diff(now, heartbeat) >= 1000:
            record("heartbeat", now, pressed=sorted(pressed_codes),
                   callback_count=callback_count)
            heartbeat = now
        flush_events()
        time.sleep_ms(10)
finally:
    keyboard.deinit()
    record("deinit", time.ticks_ms(), callback_count=callback_count)
    flush_events()
