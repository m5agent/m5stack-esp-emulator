import M5
import time
from M5 import *
from stamplc import StamPLC


relay_count = 0
plc = None
ina = None
power = (0.0, 0.0)


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(4, 4)
    d.print("StamPLC IO")
    d.setCursor(4, 24)
    d.print("relay1:%d presses:%d" % (int(bool(plc.relay[1].value())), relay_count))
    d.setCursor(4, 44)
    d.print("in: %d %d %d %d" % (
        plc.input[1].value(), plc.input[2].value(),
        plc.input[3].value(), plc.input[4].value(),
    ))
    d.setCursor(4, 64)
    d.print("rgb:%d%d%d" % (
        plc.led.red.value(), plc.led.green.value(), plc.led.blue.value(),
    ))
    d.setCursor(4, 84)
    d.print("bus:%.2fV cur:%.3fA" % power)


M5.begin()
plc = StamPLC()
plc.led.red.on()
plc.relay[1].off()
try:
    from hardware import I2C, Pin
    from unit import INA226Unit
    ina = INA226Unit(I2C(1, scl=Pin(15), sda=Pin(13), freq=400000),
                     address=0x40, type="1A")
except Exception:
    ina = None
draw()

while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        relay_count += 1
        plc.relay[1].toggle()
        changed = True
    if ina:
        try:
            value = (ina.read_bus_voltage(), ina.read_current())
            if value != power:
                power = value
                changed = True
        except Exception:
            pass
    if changed:
        draw()
    time.sleep_ms(50)
