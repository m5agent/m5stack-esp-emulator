import M5
import time
from M5 import *


state = {
    "pwr": 0,
    "touch": 0,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "mag": (0.0, 0.0, 0.0),
    "type": -1,
    "power": (0, 0, 0),
    "rtc": (0, 0, 0, 0, 0, 0),
    "als": 0,
}
last_imu = None
last_print = 0
log_uart = None


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


def draw(message):
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(10, 10)
    d.print("CoreS3 peripheral")
    d.setTextSize(1)
    d.setCursor(10, 42)
    d.print(message)
    d.setCursor(10, 66)
    d.print("PWR:%d touch:%d" % (state["pwr"], state["touch"]))
    d.setCursor(10, 90)
    d.print("acc %.2f %.2f %.2f" % state["accel"])
    d.setCursor(10, 112)
    d.print("gyr %.1f %.1f %.1f" % state["gyro"])
    d.setCursor(10, 134)
    d.print("mag %.1f %.1f %.1f" % state["mag"])
    d.setCursor(10, 156)
    d.print("imu type:%d" % state["type"])
    d.setCursor(10, 176)
    d.print("bat:%d%% %dmV c:%d" % state["power"])
    d.setCursor(10, 196)
    d.print("rtc:%04d-%02d-%02d %02d:%02d:%02d" % state["rtc"])
    d.setCursor(10, 214)
    d.print("als:%d" % state["als"])
    d.fillRect(62, 224, 196, 14, d.COLOR.BLUE)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(150, 223)
    d.setTextSize(1)
    d.print("TOUCH")


M5.begin()
draw("waiting for input")
try:
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
emit("CORES3_PERIPHERAL_MAIN")
emit("CORES3_BOARD", M5.getBoard())

try:
    state["type"] = Imu.getType()
    emit("CORES3_IMU_TYPE", state["type"])
except Exception as error:
    emit("CORES3_IMU_TYPE_ERR", repr(error))
try:
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("CORES3_POWER", *state["power"])
except Exception as error:
    emit("CORES3_POWER_ERR", repr(error))
try:
    state["rtc"] = time.localtime()[:6]
except Exception as error:
    emit("CORES3_RTC_ERR", repr(error))

draw("waiting for input")
while True:
    M5.update()
    changed = False

    if ((hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed())
            or (hasattr(BtnPWR, "wasClicked") and BtnPWR.wasClicked())
            or (hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold())):
        state["pwr"] += 1
        emit("CORES3_BTN_PWR", state["pwr"])
        changed = True

    if M5.Touch.getCount() > 0:
        if state["touch"] == 0:
            state["touch"] = 1
            emit("CORES3_TOUCH", M5.Touch.getX(), M5.Touch.getY())
            changed = True

    accel = Imu.getAccel()
    gyro = Imu.getGyro()
    state["accel"] = accel
    state["gyro"] = gyro
    try:
        mag = Imu.getMag()
        if mag != state["mag"]:
            state["mag"] = mag
            emit("CORES3_MAG", "%.3f" % mag[0], "%.3f" % mag[1], "%.3f" % mag[2])
            changed = True
    except Exception as error:
        if last_imu != "mag-error":
            last_imu = "mag-error"
            emit("CORES3_MAG_ERR", repr(error))

    now = time.ticks_ms()
    try:
        light = M5.Als.getLightSensorData()
        if light != state["als"]:
            state["als"] = light
            emit("CORES3_ALS", light)
            changed = True
    except Exception as error:
        emit("CORES3_ALS_ERR", repr(error))
    if last_imu != (accel, gyro) or time.ticks_diff(now, last_print) >= 1000:
        last_imu = (accel, gyro)
        last_print = now
        emit("CORES3_IMU", "%.3f" % accel[0], "%.3f" % accel[1], "%.3f" % accel[2],
             "%.3f" % gyro[0], "%.3f" % gyro[1], "%.3f" % gyro[2])
        changed = True

    if changed:
        draw("INPUT OK count=%d" % (state["pwr"] + state["touch"]))
    time.sleep_ms(20)
