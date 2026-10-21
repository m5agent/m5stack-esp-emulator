import M5
from M5 import *
from machine import Pin, SPI


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK)
d.setTextSize(1)
d.setCursor(20, 20)
d.print("PaperMono SPI probe")

status = "init"
rx = b""
try:
    bus = SPI(
        2,
        sck=Pin(39),
        mosi=Pin(38),
        miso=Pin(40),
        baudrate=1000000,
    )
    cs = Pin(41, Pin.OUT, value=1)
    busy = Pin(21, Pin.IN)
    dio1 = Pin(5, Pin.IN)
    if busy():
        raise RuntimeError("SX1262 busy")
    def transfer(tx):
        rx = bytearray(len(tx))
        cs(0)
        bus.write_readinto(tx, rx)
        cs(1)
        return bytes(rx)

    rx1 = transfer(b"\x07\x00\x00")
    rx2 = transfer(b"\x12\xff\xff\xff")
    rx3 = transfer(b"\x9d\x01")
    rx4 = transfer(b"\x12\xff\xff\xff")
    rx = rx1 + rx2 + rx3 + rx4
    print("SPI probe rx1=", rx1.hex(), "rx2=", rx2.hex())
    print("SPI probe rx3=", rx3.hex(), "rx4=", rx4.hex())
    if rx1 != b"\x20\x20\x20" or rx2[0] != 0x20 or rx4[0] != 0x20:
        raise RuntimeError("status mismatch %s" % rx.hex())
    status = "ok"
except Exception as exc:
    status = "error"
    print("SPI probe error:", repr(exc))
    d.setCursor(20, 120)
    d.print(repr(exc)[:52])

d.setCursor(20, 60)
d.print("rx=%s" % bytes(rx))
d.setCursor(20, 90)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
