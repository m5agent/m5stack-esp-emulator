import M5
import time
from M5 import *
from hardware import CAN


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(4, 4)
d.print("StamPLC CAN")

status = "init"
try:
    can = CAN(
        id=0,
        port=(43, 42),
        mode=CAN.NO_ACKNOWLEDGE,
        baudrate=125000,
    )
    payload = b"M5CAN!"
    can.send(payload, 0x123)
    deadline = time.ticks_add(time.ticks_ms(), 2000)
    while not can.any(0) and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(10)
    if not can.any(0):
        raise RuntimeError("CAN RX timeout")
    message = can.recv(0, timeout=1000)
    received = bytes(message[4])
    if message[0] != 0x123 or received != payload:
        raise RuntimeError("CAN mismatch %s %r" % (message[0], received))
    can.deinit()
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN)
    status = "ok id=0x123 data=%s" % received.decode()
except Exception as exc:
    status = "error: " + repr(exc)

d.setCursor(4, 24)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
