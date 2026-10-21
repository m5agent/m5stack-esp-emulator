import M5
import time
import machine
from M5 import *
from lora import SX1262
from machine import Pin, SoftI2C


ok = False
detail = "init"
packet = b""
try:
    i2c = SoftI2C(scl=Pin(8), sda=Pin(10), freq=400000)

    # E1.P2 enables external power; E0.P5/P6/P7 drive the RF switch,
    # LNA enable and SX1262 reset rails.
    i2c.writeto_mem(0x44, 0x03, b"\xfb")
    i2c.writeto_mem(0x44, 0x07, b"\x00")
    i2c.writeto_mem(0x44, 0x05, b"\x04")
    i2c.writeto_mem(0x43, 0x03, b"\x1f")
    i2c.writeto_mem(0x43, 0x07, b"\x00")
    i2c.writeto_mem(0x43, 0x05, b"\x60")
    time.sleep_ms(120)
    i2c.writeto_mem(0x43, 0x05, b"\xe0")
    time.sleep_ms(20)

    e1_out = i2c.readfrom_mem(0x44, 0x05, 1)[0]
    e0_out = i2c.readfrom_mem(0x43, 0x05, 1)[0]
    if e1_out != 0x04 or e0_out != 0xe0:
        raise RuntimeError("radio rail mismatch")

    spi = machine.SoftSPI(
        baudrate=1000000,
        polarity=0,
        phase=0,
        sck=Pin(20),
        mosi=Pin(21),
        miso=Pin(22),
    )
    radio = SX1262(
        spi=spi,
        cs=Pin(23),
        busy=Pin(19),
        dio1=Pin(15),
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
    detail = "packet=%s" % packet
    ok = True
except Exception as exc:
    detail = repr(exc)[:58]

M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 8)
d.print("Nesso N1 SX1262")
d.drawRect(2, 2, 131, 236, d.COLOR.BLUE)
d.fillRect(0, 0, 240, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(8, 42)
d.print(detail)
d.setCursor(8, 78)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
