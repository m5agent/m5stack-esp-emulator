import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

# UIFlow2's print console can be USB CDC. The service captures the guest UART.
_console = UART(0, baudrate=115200, tx=43, rx=44)


def print(*parts):
    _console.write(" ".join(str(part) for part in parts) + "\n")


print("UNIT_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Unit: " + CASE)

if CASE == "button":
    from unit import ButtonUnit
    unit = ButtonUnit((WHITE, YELLOW), True, type=2)
    signal = Pin(WHITE, Pin.IN, Pin.PULL_UP)
elif CASE == "relay":
    from unit import RelayUnit
    unit = RelayUnit((WHITE, YELLOW))
elif CASE == "env-iii":
    from unit import ENVUnit
    bus = I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)
    unit = ENVUnit(i2c=bus, type=3)
else:
    raise ValueError("unknown Unit probe case")

print("UNIT_PROBE_READY", CASE)
previous = None
sequence = 0
last_at = time.ticks_ms()
while True:
    M5.update()
    if CASE == "button":
        value = signal.value()
        text = "raw=" + str(value)
        marker = "UNIT_BUTTON " + str(value)
    elif CASE == "relay":
        if sequence % 2:
            unit.off()
        else:
            unit.on()
        value = bool(unit.get_status())
        text = "on=" + str(value)
        marker = "UNIT_RELAY " + str(int(value))
    else:
        temperature = unit.read_temperature()
        humidity = unit.read_humidity()
        pressure = unit.read_pressure() * 100
        value = (round(temperature, 1), round(humidity, 1), round(pressure, 1))
        text = "T %.1f C\nRH %.1f %%\nP %.1f Pa" % value
        marker = "UNIT_ENV %.3f %.3f %.3f" % (temperature, humidity, pressure)
    if value != previous or time.ticks_diff(time.ticks_ms(), last_at) > 3000:
        print(marker)
        screen.fillRect(0, 38, screen.width(), 150, 0xFFFFFF)
        screen.setCursor(6, 42)
        screen.print(text)
        previous = value
        last_at = time.ticks_ms()
    sequence += 1
    time.sleep_ms(700 if CASE == "relay" else 150)
