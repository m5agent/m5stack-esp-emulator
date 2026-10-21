import M5
import time
from M5 import *
from machine import I2C, Pin


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("Core2 INA3221")

status = "init"
try:
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
    while True:
        chip_id = int.from_bytes(i2c.readfrom_mem(0x40, 0xFF, 2), "big")
        bus_raw = int.from_bytes(i2c.readfrom_mem(0x40, 0x02, 2), "big")
        shunt_raw = int.from_bytes(i2c.readfrom_mem(0x40, 0x01, 2), "big")
        if chip_id != 0x3220:
            raise RuntimeError("chip id %04x" % chip_id)
        if bus_raw == 600 and shunt_raw == 60:
            d.fillRect(0, 0, 320, 8, d.COLOR.GREEN)
            status = "ok id=%04x bus=%d shunt=%d" % (
                chip_id, bus_raw, shunt_raw
            )
            break
        d.fillRect(0, 28, 320, 18, d.COLOR.BLACK)
        d.setCursor(6, 36)
        d.print("waiting bus=%d shunt=%d" % (bus_raw, shunt_raw))
        time.sleep_ms(50)
except Exception as exc:
    status = "error: " + repr(exc)

d.setCursor(6, 36)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
