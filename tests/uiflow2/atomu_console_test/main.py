# M5Stack AtomU (K117) device-local console probe.
#
# Covers the same virtual guest path: ROM/bootloader, M5.begin(), board
# identity 130, the single SK6812 on GPIO27 through RMT, the user button on
# GPIO39 driven by QMP key injection and the Grove I2C bus on G26/G32.
# No display exists on this board; the PDM microphone and IR are separate
# data planes and are not claimed by this probe.
import M5
import time
from M5 import *

print("ATOMU_MAIN_START")
M5.begin()
print("ATOMU_M5_BEGIN_OK")
print("ATOMU_BOARD", M5.getBoard())
print("ATOMU_DISPLAY none")

rgb = None
try:
    from hardware import RGB

    rgb = RGB(io=27, n=1, type="WS2812")
    rgb.set_brightness(100)
    rgb.fill_color(0x204060)
    print("ATOMU_RGB", 1, "204060")
except Exception as exc:
    print("ATOMU_RGB_ERROR", repr(exc))

try:
    from machine import I2C, Pin

    i2c = I2C(0, scl=Pin(26), sda=Pin(32), freq=100000)
    print("ATOMU_I2C_SCAN", [hex(addr) for addr in i2c.scan()])
except Exception as exc:
    print("ATOMU_I2C_ERROR", repr(exc))

print("ATOMU_PROBE_READY")
last = None
count = 0
deadline = time.ticks_add(time.ticks_ms(), 6000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    M5.update()
    pressed = int(M5.BtnA.isPressed())
    if pressed != last:
        if pressed:
            count += 1
        print("ATOMU_BUTTON_STATE", pressed, count)
        if rgb is not None:
            rgb.fill_color(0x40A020 if pressed else 0x204060)
            print("ATOMU_RGB", 1, "40A020" if pressed else "204060")
        last = pressed
    time.sleep_ms(20)
print("ATOMU_PROBE_DONE")
