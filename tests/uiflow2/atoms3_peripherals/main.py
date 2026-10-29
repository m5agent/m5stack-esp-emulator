import M5
import time


presses = 0
last_pressed = False
last_sample = None
rgb = None


def draw_sample(accel, gyro):
    display.fillRect(4, 30, 120, 40, 0x000000)
    display.setCursor(4, 32)
    display.print("a %.2f %.2f %.2f" % accel)
    display.setCursor(4, 48)
    display.print("g %.1f %.1f %.1f" % gyro)


def draw_button(pressed):
    display.fillRect(4, 80, 120, 28, 0x000000)
    display.setCursor(4, 84)
    display.print("A %s count:%d" % ("DOWN" if pressed else "UP", presses))
    display.fillRect(2, 2, 8, 8, 0x00FF00 if presses else 0xFF0000)


print("ATOMS3_PERIPHERAL_MAIN")
M5.begin()
print("ATOMS3_PERIPHERAL_BOARD", M5.getBoard())
display = M5.Display
display.setRotation(0)
display.setBrightness(255)
display.fillScreen(0x000000)
display.setTextColor(0xFFFFFF, 0x000000)
display.setTextSize(1)
display.setCursor(4, 16)
display.print("AtomS3 MPU6886")
print("ATOMS3_PERIPHERAL_DISPLAY", display.width(), display.height())
draw_button(False)

# The original AtomS3 firmware does not expose a default RGB() instance.
# Keep that observation separate from the explicitly wired GPIO35 RMT path.
try:
    from hardware import RGB

    default_rgb = RGB()
    print("ATOMS3_RGB_DEFAULT_NONE", default_rgb is None)
    rgb = RGB(io=35, n=1, type="WS2812")
    rgb.set_brightness(100)
    rgb.set_color(0, 0x204060)
    print("ATOMS3_RGB_EXPLICIT", "GPIO35", "204060")
except Exception as error:
    print("ATOMS3_RGB_ERROR", repr(error))

print("ATOMS3_PERIPHERAL_READY")
while True:
    M5.update()
    pressed = M5.BtnA.isPressed()
    if pressed != last_pressed:
        if pressed:
            presses += 1
        print("ATOMS3_PERIPHERAL_A_DOWN" if pressed else "ATOMS3_PERIPHERAL_A_UP", presses)
        draw_button(pressed)
        if rgb is not None:
            color = 0x406020 if pressed else 0x204060
            rgb.set_color(0, color)
            print("ATOMS3_RGB_BUTTON", "%06x" % color)
        last_pressed = pressed
    try:
        accel = M5.Imu.getAccel()
        gyro = M5.Imu.getGyro()
    except Exception as error:
        print("ATOMS3_IMU_ERROR", repr(error))
        raise
    sample = (accel, gyro)
    if sample != last_sample:
        print("ATOMS3_ACCEL", "%.4f %.4f %.4f" % accel)
        print("ATOMS3_GYRO", "%.4f %.4f %.4f" % gyro)
        draw_sample(accel, gyro)
        last_sample = sample
    time.sleep_ms(50)
