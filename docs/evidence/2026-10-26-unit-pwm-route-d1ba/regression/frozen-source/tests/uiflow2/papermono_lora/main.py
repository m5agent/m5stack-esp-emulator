import M5
import time
from M5 import *
import machine
from lora import SX1262


_RealSPI = machine.SPI


class SmallTransferSPI:
    """Keep CS asserted while avoiding the IDF >4-byte bus-lock path."""

    def __init__(self, *args, **kwargs):
        self._spi = _RealSPI(*args, **kwargs)

    def write_readinto(self, src, dst):
        src = memoryview(src)
        dst = memoryview(dst)
        for offset in range(0, len(src), 4):
            end = min(offset + 4, len(src))
            self._spi.write_readinto(src[offset:end], dst[offset:end])

    def write(self, src):
        src = memoryview(src)
        for offset in range(0, len(src), 4):
            self._spi.write(src[offset:min(offset + 4, len(src))])

    def readinto(self, dst, fill=0):
        dst = memoryview(dst)
        for offset in range(0, len(dst), 4):
            self._spi.readinto(dst[offset:min(offset + 4, len(dst))], fill)

    def __getattr__(self, name):
        return getattr(self._spi, name)


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.WHITE)
d.setTextColor(d.COLOR.BLACK)
d.setTextSize(1)
d.setCursor(20, 20)
d.print("PaperMono LoRa")

status = "init"
packet = b""
try:
    i2c = machine.I2C(1, scl=machine.Pin(48), sda=machine.Pin(47),
                      freq=100000)
    for reg, mask, enabled in (
        (0x16, 0x30, False),
        (0x10, 0x04, True),
        (0x13, 0x04, False),
        (0x11, 0x04, True),
    ):
        value = i2c.readfrom_mem(0x6E, reg, 1)[0]
        value = value | mask if enabled else value & ~mask
        i2c.writeto_mem(0x6E, reg, bytes((value,)))

    spi = SmallTransferSPI(
        2,
        sck=machine.Pin(39),
        mosi=machine.Pin(38),
        miso=machine.Pin(40),
    )
    radio = SX1262(
        spi=spi,
        cs=machine.Pin(41),
        busy=machine.Pin(21),
        dio1=machine.Pin(5),
        dio3_tcxo_millivolts=3300,
        lora_cfg={
            "freq_khz": 868000,
            "sf": 7,
            "bw": "125",
            "coding_rate": 5,
            "syncword": 0x12,
            "preamble_len": 12,
            "output_power": 10,
        },
    )
    radio.send("M5LORA")
    radio.start_recv()
    rx = radio.recv(timeout_ms=2000)
    packet = bytes(rx) if rx else b""
    if packet != b"M5LORA":
        raise RuntimeError("loopback mismatch")
    d.fillRect(0, 0, 480, 12, d.COLOR.BLACK)
    status = "ok"
except Exception as exc:
    status = "error"
    d.setCursor(20, 120)
    d.print(repr(exc))

d.setCursor(20, 60)
d.print("packet=%s" % packet)
d.setCursor(20, 90)
d.print("status=%s" % status)

while True:
    M5.update()
    time.sleep_ms(100)
