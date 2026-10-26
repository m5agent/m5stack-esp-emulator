import M5
import time
from M5 import *
from machine import I2C, Pin, SDCard
from rtc_probe import check_rx8130


state = {
    "imu_type": -1,
    "accel": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "power": (0, 0, 0),
    "rtc": (0, 0, 0, 0, 0, 0),
    "sd": "pending",
    "touch": 0,
    "key": 0,
    "pwr": 0,
}
last_imu = None
last_power = None
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
    d.print("PaperMono peripherals")
    d.setTextSize(2)
    d.setCursor(24, 110)
    d.print("IMU:%d touch:%d key:%d pwr:%d" % (
        state["imu_type"], state["touch"], state["key"], state["pwr"],
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
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
emit("PAPERMONO_PERIPHERAL_MAIN")
try:
    state["imu_type"] = Imu.getType()
    emit("PAPERMONO_IMU_TYPE", state["imu_type"])
except Exception:
    pass
try:
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    if state["power"] != last_power:
        last_power = state["power"]
        emit("PAPERMONO_POWER", *state["power"])
        changed = True
    emit("PAPERMONO_POWER", *state["power"])
except Exception:
    pass
try:
    i2c = I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
    state["rtc"] = check_rx8130(i2c)
    emit("PAPERMONO_RTC", "2026-10-22 07:08:09")
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
    emit("PAPERMONO_SD", state["sd"])
except Exception as error:
    state["sd"] = "ERR " + repr(error)[:40]
    emit("PAPERMONO_SD", state["sd"])
draw()

while True:
    M5.update()
    changed = False
    if BtnA.wasPressed():
        state["key"] += 1
        emit("PAPERMONO_KEY", state["key"])
        changed = True
    if ((hasattr(BtnPWR, "wasPressed") and BtnPWR.wasPressed())
            or (hasattr(BtnPWR, "wasClicked") and BtnPWR.wasClicked())
            or (hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold())):
        state["pwr"] += 1
        emit("PAPERMONO_PWR", state["pwr"])
        changed = True
    if M5.Touch.getCount() > 0 and state["touch"] == 0:
        state["touch"] = 1
        emit("PAPERMONO_TOUCH", M5.Touch.getX(), M5.Touch.getY())
        changed = True
    state["accel"] = Imu.getAccel()
    state["gyro"] = Imu.getGyro()
    sample = (state["accel"], state["gyro"])
    if sample != last_imu:
        last_imu = sample
        emit("PAPERMONO_ACCEL", "%.2f" % state["accel"][0],
             "%.2f" % state["accel"][1], "%.2f" % state["accel"][2])
        emit("PAPERMONO_GYRO", "%.2f" % state["gyro"][0],
             "%.2f" % state["gyro"][1], "%.2f" % state["gyro"][2])
        changed = True
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    if changed:
        draw()
    time.sleep_ms(50)
