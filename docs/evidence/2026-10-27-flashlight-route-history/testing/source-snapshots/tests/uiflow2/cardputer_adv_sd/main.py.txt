import M5
from M5 import *
from machine import Pin, SDCard


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("Cardputer-ADV SD")

status = "init"
try:
    sd = SDCard(
        slot=3,
        width=1,
        sck=Pin(40),
        mosi=Pin(14),
        miso=Pin(39),
        cs=Pin(12),
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
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(6, 60)
    d.print(repr(exc))

d.setCursor(6, 30)
d.print("status=%s" % status)

while True:
    M5.update()
