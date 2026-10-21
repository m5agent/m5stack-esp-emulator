import M5
import time
from M5 import *
from machine import I2C, Pin
from rtc_probe import check_rx8130
from stamplc import StamPLC


relay_count = 0
plc = None
ina = None
power = (0.0, 0.0)
rtc_value = (0, 0, 0, 0, 0, 0)
log_uart = None


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


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
    d.setCursor(4, 104)
    d.print("rtc:%04d-%02d-%02d %02d:%02d:%02d" % rtc_value)


M5.begin()
try:
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
plc = StamPLC()
plc.led.red.on()
plc.relay[1].off()
emit("STAMPLC_PERIPHERAL_MAIN")
try:
    rtc_i2c = I2C(1, scl=Pin(15), sda=Pin(13), freq=400000)
    rtc_value = check_rx8130(rtc_i2c)
    emit("STAMPLC_RTC", "2026-10-22 07:08:09")
except Exception as error:
    emit("STAMPLC_RTC_ERR", repr(error))
try:
    from hardware import I2C, Pin
    from unit import INA226Unit
    ina = INA226Unit(I2C(1, scl=Pin(15), sda=Pin(13), freq=400000),
                     address=0x40, type="1A")
except Exception:
    ina = None
    emit("STAMPLC_INA_INIT_ERR")
draw()

last_inputs = None
last_rgb = None
while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        relay_count += 1
        plc.relay[1].toggle()
        emit("STAMPLC_RELAY", int(bool(plc.relay[1].value())),
             "PRESS", relay_count)
        changed = True
    inputs = tuple(plc.input[i].value() for i in (1, 2, 3, 4))
    if inputs != last_inputs:
        last_inputs = inputs
        emit("STAMPLC_INPUTS", *inputs)
        changed = True
    if ina:
        try:
            value = (ina.read_bus_voltage(), ina.read_current())
            if value != power:
                power = value
                emit("STAMPLC_INA", "%.2f" % value[0], "%.3f" % value[1])
                changed = True
        except Exception:
            pass
    rgb = (plc.led.red.value(), plc.led.green.value(), plc.led.blue.value())
    if rgb != last_rgb:
        last_rgb = rgb
        emit("STAMPLC_RGB", *rgb)
        changed = True
    if changed:
        draw()
    time.sleep_ms(50)
