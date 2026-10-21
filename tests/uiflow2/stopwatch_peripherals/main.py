import M5
import time
from M5 import *


state = {
    "a": 0,
    "b": 0,
    "pwr": 0,
    "touch": 0,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "type": -1,
    "power": (0, 0, 0),
    "rtc": (0, 0, 0, 0, 0, 0),
}


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(64, 74)
    d.print("StopWatch")
    d.setTextSize(1)
    d.setCursor(48, 126)
    d.print("A:%d B:%d P:%d T:%d" % (
        state["a"], state["b"], state["pwr"], state["touch"],
    ))
    d.setCursor(48, 158)
    d.print("imu:%d" % state["type"])
    d.setCursor(48, 190)
    d.print("a %.2f %.2f %.2f" % state["accel"])
    d.setCursor(48, 220)
    d.print("g %.1f %.1f %.1f" % state["gyro"])
    d.setCursor(48, 262)
    d.print("bat:%d%% %dmV c:%d" % state["power"])
    d.setCursor(48, 294)
    d.print("rtc:%04d-%02d-%02d" % state["rtc"][:3])
    d.setCursor(48, 326)
    d.print("%02d:%02d:%02d" % state["rtc"][3:6])
    d.drawCircle(233, 233, 210, d.COLOR.BLUE)


M5.begin()
try:
    state["type"] = Imu.getType()
except Exception:
    pass
try:
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
except Exception:
    pass
try:
    from machine import RTC
    rtc = RTC()
    rtc.datetime((2026, 10, 21, 2, 12, 34, 56, 0))
    state["rtc"] = rtc.datetime()[:6]
except Exception:
    pass
draw()

while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        state["a"] += 1
        changed = True
    if BtnB.wasPressed():
        state["b"] += 1
        changed = True
    if hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed():
        state["pwr"] += 1
        changed = True
    if M5.Touch.getCount() > 0 and state["touch"] == 0:
        state["touch"] = 1
        changed = True
    state["accel"] = Imu.getAccel()
    state["gyro"] = Imu.getGyro()
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    if changed:
        draw()
    time.sleep_ms(20)
