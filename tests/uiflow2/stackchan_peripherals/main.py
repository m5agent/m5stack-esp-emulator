# StackChan IMU, AW9523, INA226 and IR probe.
import M5
import time
from M5 import *
from hardware import IR
from hardware.stackchan import StackChan
from machine import I2C, Pin
from driver.aw9523 import AW9523, Pin as ExpanderPin
from rtc_probe import check_pcf8563


log = None


def emit(*parts):
    message = " ".join(str(part) for part in parts)
    if log:
        log.write(message + "\n")
    print(message)


M5.begin()
try:
    from hardware import UART
    log = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log = None
emit("STACKCHAN_PERIPHERAL_MAIN_START")
for _ in range(30):
    M5.update()
    time.sleep_ms(10)

d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("StackChan peripherals")

checks = {}
try:
    rtc_i2c = I2C(1, scl=Pin(11), sda=Pin(12), freq=100000)
    rtc_value = check_pcf8563(rtc_i2c)
    checks["rtc"] = rtc_value == (2026, 10, 22, 6, 7, 8)
    emit("STACKCHAN_RTC", *rtc_value)
except Exception as error:
    checks["rtc"] = False
    emit("STACKCHAN_RTC_ERROR", repr(error))

ir_result = {"count": 0, "address": -1, "command": -1}


def ir_rx(data, address, control):
    ir_result["count"] += 1
    ir_result["address"] = address
    ir_result["command"] = data
    emit("STACKCHAN_IR_RX", address, data, control)


expected_accel = (0.25, -0.50, 0.75)
expected_gyro = (10.0, -20.0, 30.0)
imu_error = None
imu_raw = b""
imu_type = -1
accel = (0.0, 0.0, 0.0)
gyro = (0.0, 0.0, 0.0)
mag = (0.0, 0.0, 0.0)
touch_seen = 0
power = (0, 0, 0)

try:
    imu_type = Imu.getType()
    emit("STACKCHAN_IMU_TYPE", imu_type)
except Exception as error:
    emit("STACKCHAN_IMU_ERROR", repr(error))

# QOM injects physical values after firmware boot. Waiting here exercises the
# live sensor data path instead of mistaking M5Unified's boot-time gyro zero
# calibration for a broken BMI270 model.
deadline = time.ticks_add(time.ticks_ms(), 35000)
last_wait_emit = time.ticks_ms()
imu_ready = False
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    M5.update()
    if M5.Touch.getCount() > 0 and not touch_seen:
        touch_seen = 1
        emit("STACKCHAN_TOUCH", M5.Touch.getX(), M5.Touch.getY())
    try:
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        accel_ok = all(
            abs(accel[i] - expected_accel[i]) < 0.06 for i in range(3)
        )
        gyro_ok = all(
            abs(gyro[i] - expected_gyro[i]) < 1.0 for i in range(3)
        )
        imu_ready = accel_ok and gyro_ok
        if imu_ready and touch_seen:
            break
        now = time.ticks_ms()
        if time.ticks_diff(now, last_wait_emit) >= 2000:
            last_wait_emit = now
            emit(
                "STACKCHAN_IMU_WAIT %.2f %.2f %.2f %.1f %.1f %.1f"
                % (accel[0], accel[1], accel[2], gyro[0], gyro[1], gyro[2])
            )
    except Exception as error:
        imu_error = error
    time.sleep_ms(100)

try:
    stackchan = StackChan(i2c=1, uart=1)
except Exception as error:
    stackchan = None
    emit("STACKCHAN_INIT_ERROR", repr(error))

try:
    imu_raw = stackchan.i2c.readfrom_mem(0x69, 0x0C, 12)
    emit("STACKCHAN_IMU_RAW", bytes(imu_raw).hex())
    checks["imu"] = (
        imu_type == 6
        and all(abs(accel[i] - expected_accel[i]) < 0.06 for i in range(3))
        and all(abs(gyro[i] - expected_gyro[i]) < 1.0 for i in range(3))
        and len(imu_raw) == 12
        and any(imu_raw[6:])
    )
    emit("STACKCHAN_IMU_ACCEL %.2f %.2f %.2f" % accel)
    emit("STACKCHAN_IMU_GYRO %.1f %.1f %.1f" % gyro)
    if imu_error:
        emit("STACKCHAN_IMU_LAST_ERROR", repr(imu_error))
except Exception as error:
    checks["imu"] = False
    emit("STACKCHAN_IMU_ERROR", repr(error))

try:
    mag = Imu.getMag()
    expected_mag = (118.9, 77.3, -356.8)
    checks["mag"] = (
        abs(mag[0] - expected_mag[0]) < 2.0
        and abs(mag[1] - expected_mag[1]) < 2.0
        and abs(mag[2] - expected_mag[2]) < 3.0
    )
    emit("STACKCHAN_MAG %.1f %.1f %.1f" % mag)
except Exception as error:
    checks["mag"] = False
    emit("STACKCHAN_MAG_ERROR", repr(error))

try:
    power = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    checks["power"] = power == (87, 4000, 1)
    emit("STACKCHAN_PMIC_POWER", *power)
except Exception as error:
    checks["power"] = False
    emit("STACKCHAN_PMIC_POWER_ERROR", repr(error))

checks["touch"] = bool(touch_seen)

try:
    expander = AW9523(stackchan.i2c, 0x58)
    out = ExpanderPin(0, ExpanderPin.OUT, 1)
    inp = ExpanderPin(12, ExpanderPin.IN)
    output_value = out.value()
    input_value = inp.value()
    checks["aw9523"] = output_value == 1 and input_value == 0
    emit("STACKCHAN_AW9523", output_value, input_value)
except Exception as error:
    checks["aw9523"] = False
    emit("STACKCHAN_AW9523_ERROR", repr(error))

try:
    voltage = stackchan.get_battery_voltage()
    current = stackchan.get_battery_current()
    power = stackchan.get_battery_power()
    checks["ina226"] = (
        abs(voltage - 4.0) < 0.05
        and abs(current - 0.25) < 0.02
        and abs(power - 1.0) < 0.1
    )
    emit("STACKCHAN_POWER %.2f %.2f %.2f" % (voltage, current, power))
except Exception as error:
    checks["ina226"] = False
    emit("STACKCHAN_POWER_ERROR", repr(error))

try:
    light = M5.Als.getLightSensorData()
    proximity = M5.Als.getProximitySensorData()
    checks["als"] = light == 640 and proximity == 321
    emit("STACKCHAN_ALS", light, proximity)
except Exception as error:
    checks["als"] = False
    emit("STACKCHAN_ALS_ERROR", repr(error))

try:
    ir = IR()
    ir.rx_cb(ir_rx)
    ir.tx(0x56, 0xA3)
    emit("STACKCHAN_IR_TX 0x56 0xA3")
except Exception as error:
    emit("STACKCHAN_IR_ERROR", repr(error))

deadline = time.ticks_add(time.ticks_ms(), 5000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    M5.update()
    if ir_result["count"]:
        break
    time.sleep_ms(20)
checks["ir"] = (
    ir_result["count"] > 0
    and ir_result["address"] == 0x56
    and ir_result["command"] == 0xA3
)

ok = all(checks.values())
emit("STACKCHAN_CHECKS", int(checks.get("imu", False)),
     int(checks.get("mag", False)),
     int(checks.get("power", False)),
     int(checks.get("touch", False)),
     int(checks.get("aw9523", False)),
     int(checks.get("ina226", False)),
     int(checks.get("als", False)),
     int(checks.get("rtc", False)),
     int(checks.get("ir", False)))
d.fillRect(0, 0, 320, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(6, 36)
d.print("imu=%d aw=%d ina=%d als=%d rtc=%d ir=%d" % (
    int(checks.get("imu", False)),
    int(checks.get("aw9523", False)),
    int(checks.get("ina226", False)),
    int(checks.get("als", False)),
    int(checks.get("rtc", False)),
    int(checks.get("ir", False)),
))
d.setCursor(6, 62)
d.print("PASS" if ok else "FAIL")
emit("STACKCHAN_PERIPHERAL_DONE", "PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
