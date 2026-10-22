import M5
import time
from M5 import *
from machine import Pin, SoftI2C


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(8, 8)
d.print("Nesso N1 peripherals")

ok = False
detail = "init"
seen_power = set()


def sample_power():
    value = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    seen_power.add(value)
    return value


try:
    i2c = SoftI2C(scl=Pin(8), sda=Pin(10), freq=400000)
    e0 = 0x43
    e1 = 0x44

    # E1.P2 is EXT_PWR_EN; E0.P7 is LoRa reset.
    i2c.writeto_mem(e1, 0x03, b"\x04")
    i2c.writeto_mem(e1, 0x07, b"\x00")
    i2c.writeto_mem(e1, 0x05, b"\x04")
    i2c.writeto_mem(e0, 0x03, b"\x80")
    i2c.writeto_mem(e0, 0x07, b"\x00")
    i2c.writeto_mem(e0, 0x05, b"\x80")

    e1_out = i2c.readfrom_mem(e1, 0x05, 1)[0]
    e0_out = i2c.readfrom_mem(e0, 0x05, 1)[0]

    while M5.Touch.getCount() == 0:
        M5.update()
        sample_power()
        time.sleep_ms(10)
    # The runner sends touch first, then the button; wait for the button edge.
    time.sleep_ms(2000)

    buttons = i2c.readfrom_mem(e0, 0x0F, 1)[0]
    irq = i2c.readfrom_mem(e0, 0x13, 1)[0]
    level, voltage, charging = sample_power()
    detail = "e=%02x/%02x irq=%02x mv=%d lv=%d chg=%d L%d H%d" % (
        e1_out, e0_out, irq, voltage, level, charging,
        int((64, 3300, 0) in seen_power),
        int((100, 4300, 1) in seen_power),
    )
    if (e1_out != 0x04 or e0_out != 0x80 or not (irq & 0x01)
            or level != 100 or voltage != 4300 or charging != 1):
        raise RuntimeError(detail)
    if ((0, 3300, 0) not in seen_power
            or (100, 4300, 1) not in seen_power):
        raise RuntimeError(detail)
    ok = True
except Exception as exc:
    detail = repr(exc)[:58]

d.fillRect(0, 0, 240, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(8, 45)
d.print(detail)
d.setCursor(8, 72)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
