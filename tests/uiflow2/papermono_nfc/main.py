import M5
import time
from M5 import *
from hardware import NFC


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK)
d.setTextSize(1)
d.setCursor(20, 20)
d.print("PaperMono NFC")

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
    nfc.write(card, 8, b"TEST")
    page_data = nfc.read(card, 8)
    if page_data != b"TEST":
        raise RuntimeError("page mismatch")
    d.fillRect(0, 0, 480, 12, d.COLOR.BLACK)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(20, 160)
    d.print(repr(exc)[:52])

try:
    d.setCursor(20, 60)
    d.print("uid=%s" % uid)
    d.setCursor(20, 90)
    d.print("type=%s" % (card.type_name if card else "-"))
    d.setCursor(20, 120)
    d.print("page4=%s" % page4.hex())
    d.setCursor(20, 150)
    d.print("page8=%s" % page_data.hex())
except Exception:
    pass

d.setCursor(20, 190)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
