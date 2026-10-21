import M5
import time
from M5 import *
from hardware import NFC


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK)
d.setTextSize(1)
d.setCursor(10, 10)
d.print("StackChan NFC")

status = "init"
uid = "-"
page4 = b""
page_data = b""
try:
    nfc = NFC()
    card = nfc.detect()
    if card is None:
        raise RuntimeError("no tag")
    uid = card.uid_str
    page4 = nfc.read(card, 4)
    nfc.write(card, 12, b"CHAN")
    page_data = nfc.read(card, 12)
    if page_data != b"CHAN":
        raise RuntimeError("page mismatch")
    d.fillRect(0, 0, 320, 8, d.COLOR.BLACK)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(10, 150)
    d.print(repr(exc)[:38])

try:
    d.setCursor(10, 40)
    d.print("uid=%s" % uid)
    d.setCursor(10, 70)
    d.print("type=%s" % (card.type_name if card else "-"))
    d.setCursor(10, 100)
    d.print("page4=%s" % page4.hex())
    d.setCursor(10, 130)
    d.print("page12=%s" % page_data.hex())
except Exception:
    pass

d.setCursor(10, 180)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
