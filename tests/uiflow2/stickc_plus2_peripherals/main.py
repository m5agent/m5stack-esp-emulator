import M5
import time
from machine import I2C, Pin
from rtc_probe import check_pcf8563


print("STICKCPLUS2P_MAIN")
M5.begin()
print("STICKCPLUS2P_BOARD", M5.getBoard())
display = M5.Display
display.setRotation(0)
display.setBrightness(255)
display.fillScreen(0x000000)
display.setTextColor(0xFFFFFF, 0x000000)
display.setTextSize(1)
display.setCursor(4, 12)
display.print("Plus2 peripherals")
print("STICKCPLUS2P_DISPLAY", display.width(), display.height())

# Use the existing real classic I2C controller on the system SDA21/SCL22 bus.
# The shared probe writes the seven PCF8563 calendar registers at 0x51 and
# requires both exact readback and advancement after a guest timer delay.
rtc_i2c = I2C(1, scl=Pin(22), sda=Pin(21), freq=100000)
rtc_written = check_pcf8563(rtc_i2c)
print("STICKCPLUS2P_RTC_WRITTEN", rtc_written)
rtc_raw = rtc_i2c.readfrom_mem(0x51, 0x02, 7)
print("STICKCPLUS2P_RTC_ADVANCED_RAW", tuple(rtc_raw))
display.setCursor(4, 32)
display.print("RTC R/W + tick OK")

buttons = (M5.BtnA, M5.BtnB, M5.BtnPWR)
names = ("A", "B", "PWR")
counts = [0, 0, 0]
previous = [False, False, False]
last_sample = None
print("STICKCPLUS2P_READY")

while True:
    M5.update()
    for index in range(3):
        pressed = buttons[index].isPressed()
        if pressed != previous[index]:
            if pressed:
                counts[index] += 1
            display.fillRect(4, 64 + index * 20, 127, 18, 0x000000)
            display.setCursor(4, 66 + index * 20)
            display.print("%s %s count:%d" % (
                names[index], "DOWN" if pressed else "UP", counts[index]))
            previous[index] = pressed
            print("STICKCPLUS2P_BUTTON", names[index], int(pressed), counts[index])
    accel = M5.Imu.getAccel()
    gyro = M5.Imu.getGyro()
    sample = (accel, gyro)
    if sample != last_sample:
        print("STICKCPLUS2P_ACCEL", "%.4f %.4f %.4f" % accel)
        print("STICKCPLUS2P_GYRO", "%.4f %.4f %.4f" % gyro)
        display.fillRect(4, 144, 127, 60, 0x000000)
        display.setCursor(4, 146)
        display.print("a %.2f %.2f %.2f" % accel)
        display.setCursor(4, 168)
        display.print("g %.1f %.1f %.1f" % gyro)
        print("STICKCPLUS2P_DRAWN", "%.4f %.4f %.4f %.4f %.4f %.4f" % (accel + gyro))
        last_sample = sample
    time.sleep_ms(50)
