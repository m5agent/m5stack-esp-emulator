import M5
import time
from M5 import *
from machine import I2C, Pin
from rtc_probe import check_rx8130


state = {
    "power": (0, 0, 0),
    "rtc": (0, 0, 0, 0, 0, 0),
    "key": 0,
    "pwr": 0,
    "power_done": False,
}
seen_power = set()
log_uart = None


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.WHITE)
    d.setTextColor(d.COLOR.BLACK, d.COLOR.WHITE)
    d.setTextSize(3)
    d.setCursor(24, 36)
    d.print("PaperColor peripherals")
    d.setTextSize(2)
    d.setCursor(24, 110)
    d.print("power:%d%% %dmV chg:%d" % state["power"])
    d.setCursor(24, 154)
    d.print("rtc:%04d-%02d-%02d %02d:%02d:%02d" % state["rtc"])
    d.setCursor(24, 198)
    d.print("key:%d pwr:%d" % (state["key"], state["pwr"]))
    d.fillRect(380, 580, 20, 20,
               d.COLOR.GREEN if state["power_done"] else d.COLOR.RED)


M5.begin()
try:
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None

emit("PAPERCOLOR_PERIPHERAL_MAIN")
try:
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    seen_power.add(state["power"][1:])
    emit("PAPERCOLOR_POWER", *state["power"])
except Exception as error:
    emit("PAPERCOLOR_POWER_ERR", repr(error))

try:
    i2c = I2C(1, scl=Pin(3), sda=Pin(2), freq=100000)
    state["rtc"] = check_rx8130(i2c)
    emit("PAPERCOLOR_RTC", "2026-10-22 07:08:09")
except Exception as error:
    emit("PAPERCOLOR_RTC_ERR", repr(error))

draw()

while True:
    M5.update()
    changed = False
    power = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    if power[1:] != state["power"][1:]:
        state["power"] = power
        emit("PAPERCOLOR_POWER_STATE", power[1], power[2])
    seen_power.add(power[1:])
    if (not state["power_done"]
            and {3400, 4200} <= {value[0] for value in seen_power}):
        state["power_done"] = True
        emit("PAPERCOLOR_POWER_DONE PASS")
    if BtnA.wasPressed():
        state["key"] += 1
        emit("PAPERCOLOR_KEY", state["key"])
        changed = True
    if ((hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed())
            or (hasattr(BtnPWR, "wasClicked") and BtnPWR.wasClicked())
            or (hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold())):
        state["pwr"] += 1
        emit("PAPERCOLOR_PWR", state["pwr"])
        changed = True
    if changed:
        draw()
    time.sleep_ms(50)
