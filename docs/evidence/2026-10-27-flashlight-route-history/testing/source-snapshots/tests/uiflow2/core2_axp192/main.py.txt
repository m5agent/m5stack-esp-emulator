import M5
import time
from M5 import *
from machine import Pin, SoftI2C


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(12, 12)
d.print("Core2 AXP192")

ok = False
detail = "init"
try:
    i2c = SoftI2C(scl=Pin(22), sda=Pin(21), freq=100000)
    while M5.Touch.getCount() == 0:
        M5.update()
        time.sleep_ms(10)
    chip_id = i2c.readfrom_mem(0x34, 0x03, 1)[0]
    status = i2c.readfrom_mem(0x34, 0x00, 1)[0]
    voltage_raw = i2c.readfrom_mem(0x34, 0x78, 2)
    current_raw = i2c.readfrom_mem(0x34, 0x7A, 2)
    voltage = (((voltage_raw[0] << 4) | voltage_raw[1])
               * 11 // 10)
    current = (((current_raw[0] << 5) | current_raw[1])
               // 2)
    detail = "id=%d st=%02x mv=%d ma=%d" % (
        chip_id, status, voltage, current,
    )
    if (chip_id != 0x03 or not (status & 0x04)
            or abs(voltage - 3899) > 1 or current != 300):
        raise RuntimeError(detail)
    ok = True
except Exception as exc:
    detail = repr(exc)[:58]

d.fillRect(0, 0, 320, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(12, 55)
d.print(detail)
d.setCursor(12, 85)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
