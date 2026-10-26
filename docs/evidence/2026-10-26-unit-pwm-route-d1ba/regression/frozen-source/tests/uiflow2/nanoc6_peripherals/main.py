# NanoC6 onboard WS2812 and GPIO9 user-button probe.
import M5
import machine
import time
from hardware import RGB


print("NANOC6_PERIPHERAL_MAIN_START")
M5.begin()
print("NANOC6_BOARD", M5.getBoard())

rgb_power = machine.Pin(19, machine.Pin.OUT)
rgb_power.value(1)
print("NANOC6_RGBPWR_READ", rgb_power.value())
rgb = RGB()
rgb.set_brightness(100)
rgb.set_color(0, 0xFF0000)
print("NANOC6_RGB_SET 0xFF0000")

blue = machine.Pin(7, machine.Pin.OUT)
blue.value(1)
print("NANOC6_BLUE_ON")

button = machine.Pin(9, machine.Pin.IN, machine.Pin.PULL_UP)
print("NANOC6_BUTTON_READY")

pressed_seen = False
deadline = time.ticks_add(time.ticks_ms(), 15000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    value = button.value()
    if value == 0 and not pressed_seen:
        pressed_seen = True
        print("NANOC6_BUTTON_PRESS 1")
    elif pressed_seen and value == 1:
        print("NANOC6_BUTTON_RELEASE 0")
        blue.value(0)
        print("NANOC6_BLUE_OFF")
        break
    time.sleep_ms(20)
else:
    print("NANOC6_BUTTON_TIMEOUT")

print("NANOC6_PERIPHERAL_DONE")
while True:
    M5.update()
    time.sleep_ms(100)
