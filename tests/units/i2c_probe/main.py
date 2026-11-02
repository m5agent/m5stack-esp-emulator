"""Guest probes for the first B-class Unit batch (dlight/accel/4relay/weight-i2c).

Runs the reference UIFlow2 firmware's frozen original I2C Unit drivers on a real
I2C controller; no host value is written into a driver return path. The Device
Service captures UART0 markers and QOM state, and injects external fixture
values through unit-input.
"""

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


print("I2C_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("I2C Unit: " + CASE)


def show(text):
    screen.fillRect(0, 38, screen.width(), 150, 0xFFFFFF)
    screen.setCursor(6, 42)
    screen.print(str(text))


def wait_ms(duration):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration:
        M5.update()
        time.sleep_ms(10)


def emit_exception(prefix, error):
    """Report a guest driver exception over the captured UART, not USB CDC."""
    import io

    trace = io.StringIO()
    sys.print_exception(error, trace)
    print(prefix, trace.getvalue().replace("\n", " | "))


bus = I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)
print("I2C_PROBE_SCAN", [hex(value) for value in bus.scan()])

if CASE == "4relay":
    from unit import Relay4Unit

    try:
        unit = Relay4Unit(bus, 0x26)
    except Exception as error:
        emit_exception("I2C_RELAY_INIT_ERROR", error)
        raise
    print("I2C_PROBE_READY", CASE)
    print("I2C_RELAY_MODE0", unit.get_mode())
    show("mode=" + str(unit.get_mode()))
    unit.set_mode(1)
    print("I2C_RELAY_MODE1", unit.get_mode())
    wait_ms(600)
    unit.set_mode(0)
    unit.set_relay_state(1, 1)
    print("I2C_RELAY_STATE 1 1", unit.get_relay_state(1))
    show("relay1=1")
    wait_ms(800)
    unit.set_led_state(1, 1)
    print("I2C_LED_STATE 1 1", unit.get_led_state(1))
    wait_ms(800)
    unit.set_relay_state(1, 0)
    print("I2C_RELAY_STATE 1 0", unit.get_relay_state(1))
    wait_ms(600)
    unit.set_led_state(1, 0)
    print("I2C_LED_STATE 1 0", unit.get_led_state(1))
    wait_ms(600)
    unit.set_relay_all(1)
    relays = [unit.get_relay_state(channel) for channel in range(1, 5)]
    leds = [unit.get_led_state(channel) for channel in range(1, 5)]
    print("I2C_RELAY_ALL 1", "".join(str(int(v)) for v in relays),
          "".join(str(int(v)) for v in leds))
    show("relay_all(1)")
    wait_ms(800)
    unit.set_relay_all(0)
    relays = [unit.get_relay_state(channel) for channel in range(1, 5)]
    leds = [unit.get_led_state(channel) for channel in range(1, 5)]
    print("I2C_RELAY_ALL 0", "".join(str(int(v)) for v in relays),
          "".join(str(int(v)) for v in leds))
    wait_ms(600)
    unit.set_relay_state(2, 1)
    print("I2C_RELAY_STATE 2 1", unit.get_relay_state(2))
    relays = [unit.get_relay_state(channel) for channel in range(1, 5)]
    leds = [unit.get_led_state(channel) for channel in range(1, 5)]
    print("I2C_RELAY_FINAL", "".join(str(int(v)) for v in relays),
          "".join(str(int(v)) for v in leds))
    show("relay2=1")
    print("I2C_RELAY_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "dlight":
    from unit import DLightUnit

    try:
        unit = DLightUnit(bus, 0x23)
    except Exception as error:
        emit_exception("I2C_DLIGHT_INIT_ERROR", error)
        raise
    print("I2C_PROBE_READY", CASE)
    print("I2C_DLIGHT_LOOP")
    while True:
        try:
            lux = unit.get_lux()
            print("I2C_DLIGHT_LUX", round(lux, 4))
            show("lux=%.1f" % lux)
        except Exception as error:
            emit_exception("I2C_DLIGHT_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(250)

elif CASE == "accel":
    from unit import AccelUnit

    try:
        unit = AccelUnit(bus, 0x53)
    except Exception as error:
        emit_exception("I2C_ACCEL_INIT_ERROR", error)
        raise
    print("I2C_PROBE_READY", CASE)
    print("I2C_ACCEL_LOOP")
    while True:
        try:
            values = unit.get_accel()
            x, y, z = values[0], values[1], values[2]
            print("I2C_ACCEL", round(x, 6), round(y, 6), round(z, 6))
            show("a=%.2f,%.2f,%.2f" % (x, y, z))
        except Exception as error:
            emit_exception("I2C_ACCEL_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(250)

elif CASE == "weight-i2c":
    from unit import WeightI2CUnit

    try:
        unit = WeightI2CUnit(bus, 0x26)
    except Exception as error:
        emit_exception("I2C_WEIGHT_INIT_ERROR", error)
        raise
    print("I2C_PROBE_READY", CASE)
    print("I2C_WEIGHT_LOOP")
    for _ in range(8):
        try:
            # The frozen official driver exposes get_adc_raw/get_weight_float/
            # get_weight_int/get_weight_str as properties, not methods.
            adc = unit.get_adc_raw
            weight = unit.get_weight_float
            weight_int = unit.get_weight_int
            weight_str = unit.get_weight_str
            print("I2C_WEIGHT", int(adc), round(weight, 6), int(weight_int), repr(weight_str))
            show("w=%.3f" % weight)
        except Exception as error:
            emit_exception("I2C_WEIGHT_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(250)
    try:
        unit.set_calibration(0.0, 0, 100.0, 100000)
        unit.set_reset_offset()
        unit.set_lowpass_filter(1)
        unit.set_average_filter_level(10)
        unit.set_ema_filter_alpha(20)
        print("I2C_WEIGHT_CAL", int(unit.get_lowpass_filter),
              int(unit.get_average_filter_level), int(unit.get_ema_filter_alpha))
    except Exception as error:
        emit_exception("I2C_WEIGHT_CAL_ERROR", error)
    try:
        print("I2C_WEIGHT_SPEC", int(unit.get_device_spec(0xFE)),
              int(unit.get_device_spec(0xFF)))
    except Exception as error:
        emit_exception("I2C_WEIGHT_SPEC_ERROR", error)
    print("I2C_WEIGHT_END")
    while True:
        M5.update()
        time.sleep_ms(200)

else:
    raise ValueError("unknown i2c probe case")
