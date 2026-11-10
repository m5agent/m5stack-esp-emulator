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


def sample_states(codes):
    for code in codes:
        pressed = keyboard.is_key_pressed(code)
        if pressed != previous[code]:
            previous[code] = pressed
            if pressed:
                pressed_codes.add(code)
            else:
                pressed_codes.discard(code)
            record("state", time.ticks_ms(), code=code, pressed=pressed)


def sample_active_states():
    if pressed_codes:
        sample_states(tuple(pressed_codes))


def key_event(active):
    global callback_count
    # Capture the public state before draining callbacks or writing to UART.
    # A queued key code alone does not prove that the press was observed.
    callback_count += 1
    codes = []
    record("callback", time.ticks_ms(), codes=codes, callback_count=callback_count,
           callback_type=type(active).__name__)
    sample_states(KEY_CODES)
    while True:
        code = keyboard.get_key()
        if code is None:
            break
        codes.append(code)


try:
    for code in KEY_CODES:
        previous[code] = keyboard.is_key_pressed(code)
    keyboard.set_callback(key_event)
    record("ready", time.ticks_ms(), board=M5.getBoard(), states=previous.copy(),
           pending=keyboard.is_pressed(), api="MatrixKeyboard.set_callback")
    flush_events()
    while True:
        # On ADV is_key_pressed reads the state updated by the original IRQ
        # driver. It does not read the TCA8418 FIFO or scan GPIO keys.
        sample_active_states()
        now = time.ticks_ms()
        if time.ticks_diff(now, heartbeat) >= 1000:
            # Audit every public state at callback entry and on heartbeats.
            # Between callbacks only a held key needs release observation.
            sample_states(KEY_CODES)
            record("heartbeat", now, pressed=[code for code in KEY_CODES if code in pressed_codes],
                   callback_count=callback_count)
            heartbeat = now
        flush_events()
        time.sleep_ms(10)
finally:
    keyboard.deinit()
    record("deinit", time.ticks_ms(), callback_count=callback_count)
    flush_events()
