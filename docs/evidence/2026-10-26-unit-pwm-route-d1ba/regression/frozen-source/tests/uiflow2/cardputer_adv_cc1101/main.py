import M5
import time
from M5 import *
from cap import CC1101Cap


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 8)
d.print("Cardputer-ADV CC1101")

ok = False
detail = "init"
packet = b""
try:
    radio = CC1101Cap(
        868000,
        2.4,
        25.4,
        58.0,
        10,
        16,
        0x12,
        0xAD,
    )
    if not radio.send("M5CC1101"):
        raise RuntimeError("tx failed")
    rx = radio.recv(timeout_ms=1000)
    packet = bytes(rx.data) if rx else b""
    if packet != b"M5CC1101":
        raise RuntimeError("loopback mismatch %r" % packet)
    detail = "packet=%s" % packet
    ok = True
except Exception as exc:
    detail = repr(exc)[:58]

d.drawRect(3, 3, 233, 128, d.COLOR.BLUE)
d.fillRect(0, 0, 240, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(8, 42)
d.print(detail)
d.setCursor(8, 78)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
