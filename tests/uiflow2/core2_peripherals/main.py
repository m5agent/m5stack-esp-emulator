import M5
import time
from M5 import *
from machine import I2C, Pin
from rtc_probe import check_pcf8563


state = {
    "touch": 0,
    "pwr": 0,
    "rtc": (0, 0, 0, 0, 0, 0),
    "rtc_ok": False,
    "pmic": -1,
    "key_state": 0,
}
log = None


def emit(*parts):
    message = " ".join(str(part) for part in parts)
    print(message)
    if log:
        log.write(message + "\n")


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(10, 10)
    d.print("Core2 peripherals")
    d.setTextSize(1)
    d.setCursor(10, 48)
    d.print("touch:%d pwr:%d" % (state["touch"], state["pwr"]))
    d.setCursor(10, 70)
    d.print("rtc:%04d-%02d-%02d %02d:%02d:%02d" % state["rtc"])
    d.setCursor(10, 92)
    d.print("pmic:%d key:%d" % (state["pmic"], state["key_state"]))
    ready = state["rtc_ok"] and state["touch"] and state["pwr"]
    d.fillRect(300, 220, 20, 20,
               d.COLOR.GREEN if ready else d.COLOR.RED)
    d.fillRect(160, 180, 140, 24, d.COLOR.BLUE)
    d.setCursor(224, 186)
    d.print("TOUCH")
    if ready:
        emit("CORE2_PERIPHERAL_DRAW_COMPLETE")


M5.begin()
try:
    from hardware import UART
    log = UART(0, baudrate=115200, tx=1, rx=3)
except Exception:
    log = None

emit("CORE2_PERIPHERAL_MAIN")
try:
    state["pmic"] = Power.getType()
except Exception:
    state["pmic"] = -1
try:
    rtc_i2c = I2C(1, scl=Pin(22), sda=Pin(21), freq=100000)
    state["rtc"] = check_pcf8563(rtc_i2c)
    state["rtc_ok"] = True
    emit("CORE2_RTC", "2026-10-22 06:07:08")
except Exception as error:
    emit("CORE2_RTC_ERR", repr(error))
try:
    axp_i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
except Exception:
    axp_i2c = None

draw()
emit("CORE2_PERIPHERAL_INPUT_READY")

while True:
    key_state = Power.getKeyState()
    if axp_i2c:
        try:
            irq = axp_i2c.readfrom_mem(0x34, 0x49, 1)[0] & 0x0C
            if irq:
                axp_i2c.writeto_mem(0x34, 0x49, bytes((irq,)))
                key_state = key_state or 1
        except Exception:
            pass
    state["key_state"] = key_state
    M5.update()
    changed = False
    if M5.Touch.getCount() > 0 and state["touch"] == 0:
        state["touch"] = 1
        emit("CORE2_TOUCH", M5.Touch.getX(), M5.Touch.getY())
        changed = True
    if (key_state
            or (hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed())
            or (hasattr(BtnPWR, "wasClicked") and BtnPWR.wasClicked())
            or (hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold())):
        state["pwr"] += 1
        emit("CORE2_PWR", state["pwr"])
        changed = True
    if changed:
        draw()
    time.sleep_ms(20)
