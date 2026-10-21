import M5
import time
from M5 import *


presses = 0
state = {
    "type": -1,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "mag": (0.0, 0.0, 0.0),
}


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(1)
    d.setCursor(4, 4)
    d.print("AtomS3R IMU")
    d.setCursor(4, 22)
    d.print("type:%d btn:%d" % (state["type"], presses))
    d.setCursor(4, 40)
    d.print("a %.2f %.2f %.2f" % state["accel"])
    d.setCursor(4, 56)
    d.print("g %.1f %.1f %.1f" % state["gyro"])
    d.setCursor(4, 72)
    d.print("m %.1f %.1f %.1f" % state["mag"])


M5.begin()
try:
    state["type"] = Imu.getType()
except Exception:
    state["type"] = -1
draw()

while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        presses += 1
        changed = True
    state["accel"] = Imu.getAccel()
    state["gyro"] = Imu.getGyro()
    state["mag"] = Imu.getMag()
    if changed:
        draw()
    time.sleep_ms(100)
