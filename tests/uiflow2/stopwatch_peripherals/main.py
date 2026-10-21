import M5
import time
from M5 import *
from machine import I2C, Pin
from rtc_probe import check_rx8130


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
last_imu = None
last_power = None
log_uart = None


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


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
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
emit("STOPWATCH_PERIPHERAL_MAIN")
try:
    state["type"] = Imu.getType()
    emit("STOPWATCH_IMU_TYPE", state["type"])
except Exception:
    pass
try:
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("STOPWATCH_POWER", *state["power"])
except Exception:
    pass
try:
    rtc_i2c = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
    state["rtc"] = check_rx8130(rtc_i2c)
    emit("STOPWATCH_RTC", "2026-10-22 07:08:09")
except Exception:
    pass
draw()

while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        state["a"] += 1
        emit("STOPWATCH_BTN_A", state["a"])
        changed = True
    if BtnB.wasPressed():
        state["b"] += 1
        emit("STOPWATCH_BTN_B", state["b"])
        changed = True
    if ((hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed())
            or (hasattr(BtnPWR, "wasClicked") and BtnPWR.wasClicked())
            or (hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold())):
        state["pwr"] += 1
        emit("STOPWATCH_BTN_PWR", state["pwr"])
        changed = True
    if M5.Touch.getCount() > 0 and state["touch"] == 0:
        state["touch"] = 1
        emit("STOPWATCH_TOUCH", M5.Touch.getX(), M5.Touch.getY())
        changed = True
    state["accel"] = Imu.getAccel()
    state["gyro"] = Imu.getGyro()
    sample = (state["accel"], state["gyro"])
    if sample != last_imu:
        last_imu = sample
        emit("STOPWATCH_ACCEL", "%.2f" % state["accel"][0],
             "%.2f" % state["accel"][1], "%.2f" % state["accel"][2])
        emit("STOPWATCH_GYRO", "%.2f" % state["gyro"][0],
             "%.2f" % state["gyro"][1], "%.2f" % state["gyro"][2])
        changed = True
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    if state["power"] != last_power:
        last_power = state["power"]
        emit("STOPWATCH_POWER", *state["power"])
        changed = True
    if changed:
        draw()
    time.sleep_ms(20)
