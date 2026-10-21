import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(2)
d.setCursor(8, 8)
d.print("Cardputer-ADV")
d.setTextSize(1)
d.setCursor(8, 40)
d.print("BMI270 IMU")

expected_accel = (0.25, -0.50, 0.75)
expected_gyro = (10.0, -20.0, 30.0)
detail = "waiting"
ok = False
last_state = None


def draw_state():
    d.fillScreen(d.COLOR.BLACK)
    d.drawRect(3, 3, 233, 128, d.COLOR.BLUE)
    d.fillRect(0, 0, 240, 8, d.COLOR.GREEN if ok else d.COLOR.RED)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(8, 8)
    d.print("Cardputer-ADV")
    d.setTextSize(1)
    d.setCursor(8, 40)
    d.print("BMI270 IMU")
    d.setCursor(8, 60)
    d.print(detail)
    d.setCursor(8, 90)
    d.print("PASS" if ok else "FAIL")


while True:
    M5.update()
    try:
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        accel_ok = all(
            abs(accel[i] - expected_accel[i]) < 0.05 for i in range(3)
        )
        gyro_ok = all(
            abs(gyro[i] - expected_gyro[i]) < 1.0 for i in range(3)
        )
        now_ok = accel_ok and gyro_ok
        detail = "a %.2f %.2f %.2f g %.1f %.1f %.1f" % (
            accel[0], accel[1], accel[2],
            gyro[0], gyro[1], gyro[2],
        )
        if now_ok and not ok:
            print("CARDPUTER_ADV_IMU_ACCEL", *accel)
            print("CARDPUTER_ADV_IMU_GYRO", *gyro)
        ok = now_ok
    except Exception as exc:
        detail = repr(exc)[:58]

    state = (ok, detail)
    if state != last_state:
        last_state = state
        draw_state()
    time.sleep_ms(100)
