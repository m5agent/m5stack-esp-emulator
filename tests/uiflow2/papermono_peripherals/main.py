import M5
import time
from M5 import *
from machine import RTC, SDCard


state = {
    "imu_type": -1,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "power": (0, 0, 0),
    "rtc": (0, 0, 0, 0, 0, 0),
    "sd": "pending",
    "touch": 0,
    "key": 0,
}


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.WHITE)
    d.setTextColor(d.COLOR.BLACK, d.COLOR.WHITE)
    d.setTextSize(3)
    d.setCursor(24, 36)
    d.print("PaperMono peripherals")
    d.setTextSize(2)
    d.setCursor(24, 110)
    d.print("IMU:%d  touch:%d key:%d" % (
        state["imu_type"], state["touch"], state["key"],
    ))
    d.setCursor(24, 150)
    d.print("acc %.2f %.2f %.2f" % state["accel"])
    d.setCursor(24, 190)
    d.print("gyr %.1f %.1f %.1f" % state["gyro"])
    d.setCursor(24, 230)
    d.print("bat:%d%% %dmV c:%d" % state["power"])
    d.setCursor(24, 270)
    d.print("rtc:%04d-%02d-%02d %02d:%02d:%02d" % state["rtc"])
    d.setCursor(24, 310)
    d.print("sd: %s" % state["sd"])


M5.begin()
try:
    state["imu_type"] = Imu.getType()
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
    rtc = RTC()
    rtc.datetime((2026, 10, 21, 3, 4, 5, 6, 0))
    state["rtc"] = rtc.datetime()[:6]
except Exception:
    pass
try:
    sd = SDCard(slot=1, width=4, freq=1000000)
    write_buf = bytearray(512)
    for i in range(len(write_buf)):
        write_buf[i] = (i * 3 + 0x5A) & 0xFF
    sd.writeblocks(100, write_buf)
    read_buf = bytearray(512)
    sd.readblocks(100, read_buf)
    state["sd"] = "rw ok" if bytes(read_buf) == bytes(write_buf) else "mismatch"
except Exception as error:
    state["sd"] = "ERR " + repr(error)[:40]
draw()

while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        state["key"] += 1
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
    time.sleep_ms(50)
