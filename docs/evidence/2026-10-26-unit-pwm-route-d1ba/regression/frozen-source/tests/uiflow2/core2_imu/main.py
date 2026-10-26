import M5
import time
from M5 import *


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(6, 6)
d.print("Core2 IMU")
d.setCursor(6, 32)
d.print("waiting for sample")

status = "init"
last_values = None
while True:
    M5.update()
    try:
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        values = (
            round(accel[0], 2), round(accel[1], 2), round(accel[2], 2),
            round(gyro[0], 1), round(gyro[1], 1), round(gyro[2], 1),
        )
        if values != last_values:
            last_values = values
            status = "a=%.2f,%.2f,%.2f g=%.1f,%.1f,%.1f" % values
            print("CORE2_IMU_VALUES", status)
            d.fillRect(0, 28, 320, 20, d.COLOR.BLACK)
            d.setCursor(6, 32)
            d.print(status)
        if (abs(accel[0] - 0.25) <= 0.03
                and abs(accel[1] + 0.50) <= 0.03
                and abs(gyro[0] - 10.0) <= 1.0
                and abs(gyro[1] + 20.0) <= 1.0):
            status = "ok a=%.2f,%.2f g=%.1f,%.1f" % (
                accel[0], accel[1], gyro[0], gyro[1]
            )
            break
    except Exception as exc:
        status = "error: " + repr(exc)
        break
    time.sleep_ms(20)

d.fillRect(0, 0, 320, 8,
           d.COLOR.GREEN if status.startswith("ok") else d.COLOR.RED)
d.setCursor(6, 32)
d.print(status)

while True:
    M5.update()
    time.sleep_ms(100)
