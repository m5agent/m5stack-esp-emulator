import M5
import time
from M5 import *


presses = 0
log_uart = None
state = {
    "type": -1,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "mag": (0.0, 0.0, 0.0),
}


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


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
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
emit("ATOMS3R_PERIPHERAL_MAIN")
try:
    state["type"] = Imu.getType()
    emit("ATOMS3R_IMU_TYPE", state["type"])
except Exception:
    state["type"] = -1
    emit("ATOMS3R_IMU_TYPE_ERR")
draw()

last_imu = None
while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        presses += 1
        emit("ATOMS3R_BTN", presses)
        changed = True
    state["accel"] = Imu.getAccel()
    state["gyro"] = Imu.getGyro()
    state["mag"] = Imu.getMag()
    sample = (state["accel"], state["gyro"], state["mag"])
    if sample != last_imu:
        last_imu = sample
        emit("ATOMS3R_ACCEL", "%.2f" % state["accel"][0],
             "%.2f" % state["accel"][1], "%.2f" % state["accel"][2])
        emit("ATOMS3R_GYRO", "%.2f" % state["gyro"][0],
             "%.2f" % state["gyro"][1], "%.2f" % state["gyro"][2])
        emit("ATOMS3R_MAG", "%.2f" % state["mag"][0],
             "%.2f" % state["mag"][1], "%.2f" % state["mag"][2])
        changed = True
    if changed:
        draw()
    time.sleep_ms(100)
