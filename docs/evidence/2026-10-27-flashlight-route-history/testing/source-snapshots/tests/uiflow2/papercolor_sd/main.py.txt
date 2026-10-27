import M5
from M5 import *
from machine import Pin, SDCard


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK, d.COLOR.WHITE)
d.setTextSize(3)
d.setCursor(24, 36)
d.print("PaperColor SD")

status = "init"
try:
    sd = SDCard(
        slot=2,
        width=1,
        sck=Pin(15),
        mosi=Pin(13),
        miso=Pin(14),
        cs=Pin(47),
        freq=1000000,
    )
    write_buf = bytearray(512)
    for i in range(len(write_buf)):
        write_buf[i] = (i * 7 + 0x31) & 0xFF
    if not sd.writeblocks(100, write_buf):
        raise RuntimeError("writeblocks failed")
    read_buf = bytearray(512)
    if not sd.readblocks(100, read_buf):
        raise RuntimeError("readblocks failed")
    if bytes(read_buf) != bytes(write_buf):
        raise RuntimeError("SD data mismatch")
    d.fillRect(0, 0, 400, 12, d.COLOR.BLACK)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(24, 100)
    d.print(repr(exc))

d.setCursor(24, 76)
d.print("status=%s" % status)

while True:
    M5.update()
