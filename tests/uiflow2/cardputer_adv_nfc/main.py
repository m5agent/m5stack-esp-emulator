import M5
import time
from M5 import *
from machine import Pin, SPI
from driver.st25r3916 import ST25R3916


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 8)
d.print("Cardputer-ADV NFC")

ok = False
detail = "init"
uid = "-"
page4 = b""
page8 = b""
try:
    Pin(3, Pin.OUT, value=1)
    spi = SPI(
        1,
        baudrate=2000000,
        polarity=0,
        phase=1,
        sck=Pin(40),
        mosi=Pin(14),
        miso=Pin(39),
    )
    chip = ST25R3916(
        spi=spi,
        cs=Pin(6, Pin.OUT, value=1),
        irq=Pin(4, Pin.IN),
    )
    raw = chip.read_reg8(0x3F)
    detail = "id=%02x" % raw
    if not chip.begin():
        raise RuntimeError("chip begin failed %02x" % raw)
    tag = chip.read_uid_once()
    uid_b, uid_len, atqa, sak = tag
    uid = uid_b.hex()
    page4 = chip.type2_read_page(4)
    if not chip.type2_write_page(8, b"TEST"):
        raise RuntimeError("page write failed")
    page8 = chip.type2_read_page(8)
    detail = "uid=%s" % uid
    if uid != "deadbeef" or page4 != b"M5N1" or page8 != b"TEST":
        raise RuntimeError("%s/%s/%s" % (uid, page4.hex(), page8.hex()))
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN)
    ok = True
except Exception as exc:
    detail = repr(exc)[:58]

d.drawRect(3, 3, 233, 128, d.COLOR.BLUE)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 42)
d.print(detail)
d.setCursor(8, 66)
d.print("p4=%s p8=%s" % (page4.hex(), page8.hex()))
d.setCursor(8, 90)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
