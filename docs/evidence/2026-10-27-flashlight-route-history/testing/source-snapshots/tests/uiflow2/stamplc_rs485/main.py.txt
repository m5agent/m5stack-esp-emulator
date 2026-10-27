import M5
import time
from M5 import *
from hardware import PWR485


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(4, 4)
d.print("StamPLC RS485")

status = "init"
try:
    uart = PWR485(
        2,
        baudrate=115200,
        bits=8,
        parity=None,
        stop=1,
        tx=0,
        rx=39,
        rts=46,
        mode=PWR485.MODE_RS485_HALF_DUPLEX,
    )
    payload = b"M5RS485"
    uart.write(payload)
    deadline = time.ticks_add(time.ticks_ms(), 2000)
    while not uart.any() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(10)
    received = uart.read()
    if received != payload:
        raise RuntimeError("RS485 mismatch %r" % (received,))
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN)
    status = "ok data=%s" % received.decode()
except Exception as exc:
    status = "error: " + repr(exc)

d.setCursor(4, 24)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
