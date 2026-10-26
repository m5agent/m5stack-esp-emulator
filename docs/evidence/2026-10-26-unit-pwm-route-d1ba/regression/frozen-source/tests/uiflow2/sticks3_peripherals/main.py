import M5
import time
from M5 import *


state = {
    "a": 0,
    "b": 0,
    "pwr": 0,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "type": -1,
    "enabled": False,
    "power": (0, 0, 0),
}
last_imu = None
last_print = 0
log_uart = None


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(6, 8)
    d.print("StickS3")
    d.setTextSize(1)
    d.setCursor(6, 34)
    d.print("A:%d B:%d P:%d" % (state["a"], state["b"], state["pwr"]))
    d.setCursor(6, 56)
    d.print("acc %.2f %.2f %.2f" % state["accel"])
    d.setCursor(6, 76)
    d.print("gyr %.1f %.1f %.1f" % state["gyro"])
    d.setCursor(6, 96)
    d.print("imu type:%d en:%d" % (state["type"], state["enabled"]))
    d.setCursor(6, 116)
    d.print("bat:%d%% %dmV c:%d" % state["power"])
    d.drawRect(3, 3, 129, 234, d.COLOR.BLUE)


M5.begin()
draw()
try:
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
emit("STICKS3_PERIPHERAL_MAIN")
emit("STICKS3_BOARD", M5.getBoard())

try:
    state["type"] = Imu.getType()
    state["enabled"] = Imu.isEnabled()
    emit("STICKS3_IMU_TYPE", state["type"])
except Exception as error:
    emit("STICKS3_IMU_TYPE_ERR", repr(error))

try:
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("STICKS3_BATTERY", *state["power"])
except Exception as error:
    emit("STICKS3_POWER_ERR", repr(error))

draw()
while True:
    M5.update()
    changed = False

    if BtnA.wasPressed():
        state["a"] += 1
        emit("STICKS3_BTN_A", state["a"])
        changed = True
    if BtnB.wasPressed():
        state["b"] += 1
        emit("STICKS3_BTN_B", state["b"])
        changed = True
    if ((hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed())
            or (hasattr(BtnPWR, "wasClicked") and BtnPWR.wasClicked())
            or (hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold())):
        state["pwr"] += 1
        emit("STICKS3_BTN_PWR", state["pwr"])
        changed = True

    accel = Imu.getAccel()
    gyro = Imu.getGyro()
    state["accel"] = accel
    state["gyro"] = gyro
    now = time.ticks_ms()
    if last_imu != (accel, gyro) or time.ticks_diff(now, last_print) >= 1000:
        last_imu = (accel, gyro)
        last_print = now
        emit("STICKS3_IMU", "%.3f" % accel[0], "%.3f" % accel[1], "%.3f" % accel[2],
             "%.3f" % gyro[0], "%.3f" % gyro[1], "%.3f" % gyro[2])
        changed = True

    if changed:
        draw()
    time.sleep_ms(20)
