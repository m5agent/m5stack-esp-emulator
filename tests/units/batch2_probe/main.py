"""Guest probes for the first six Units of the second research batch.

Runs the reference UIFlow2 firmware's frozen original Unit drivers on real
controllers (GPIO/ADC/RMT or I2C); no host value is written into a driver return
path. The Device Service captures UART0 markers and QOM state, and injects
external fixture values through unit-input.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)


def print(*parts):
    _console.write(" ".join(str(part) for part in parts) + "\n")


def emit_exception(prefix, error):
    import io

    trace = io.StringIO()
    sys.print_exception(error, trace)
    print(prefix, trace.getvalue().replace("\n", " | "))


def show(screen, text):
    screen.fillRect(0, 38, screen.width(), 150, 0xFFFFFF)
    screen.setCursor(6, 42)
    screen.print(str(text))


def wait_ms(duration):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration:
        M5.update()
        time.sleep_ms(10)


print("BATCH2_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch2 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


def frame_rgb(unit):
    """Convert the SK6812 buffer (G,R,B per LED) to RGB integers as the model sees them."""
    values = []
    for led in range(14):
        g = unit.buf[led * 3]
        r = unit.buf[led * 3 + 1]
        b = unit.buf[led * 3 + 2]
        values.append((r << 16) | (g << 8) | b)
    return values


if CASE == "joystick":
    from unit import JoystickUnit

    try:
        unit = JoystickUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_JOYSTICK_INIT_ERROR", error)
        raise
    print("BATCH2_PROBE_READY", CASE)
    for _ in range(8):
        try:
            print("I2C_JOYSTICK", unit.get_x_raw(), unit.get_y_raw(),
                  int(unit.get_button_status()))
            show(screen, "joystick")
        except Exception as error:
            emit_exception("I2C_JOYSTICK_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("I2C_JOYSTICK_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "watering":
    from unit import WateringUnit

    try:
        unit = WateringUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("I2C_WATERING_INIT_ERROR", error)
        raise
    print("BATCH2_PROBE_READY", CASE)
    for _ in range(5):
        try:
            raw = unit.get_raw()
            print("I2C_WATERING_RAW", raw)
            try:
                print("I2C_WATERING_VOLTAGE", round(unit.get_voltage(), 3))
            except OSError as error:
                print("I2C_WATERING_VOLTAGE_UNSUPPORTED", repr(error))
            show(screen, "raw=%d" % raw)
        except Exception as error:
            emit_exception("I2C_WATERING_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.on()
        print("I2C_WATERING_PUMP", 1)
        wait_ms(1200)
        unit.off()
        print("I2C_WATERING_PUMP", 0)
        wait_ms(1200)
        unit.set_pump(1)
        print("I2C_WATERING_PUMP", 1)
        wait_ms(800)
        unit.set_pump(0)
        print("I2C_WATERING_PUMP", 0)
    except Exception as error:
        emit_exception("I2C_WATERING_PUMP_ERROR", error)
    print("I2C_WATERING_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "fader":
    from unit import FaderUnit

    try:
        unit = FaderUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("I2C_FADER_INIT_ERROR", error)
        raise
    print("BATCH2_PROBE_READY", CASE)
    # The constructor already wrote a brightness frame (set_brightness(10)).
    for _ in range(4):
        try:
            raw = unit.get_raw()
            print("I2C_FADER_RAW", raw)
            try:
                print("I2C_FADER_VOLTAGE", round(unit.get_voltage(), 3))
            except OSError as error:
                print("I2C_FADER_VOLTAGE_UNSUPPORTED", repr(error))
            unit.update_color()
            print("I2C_FADER_FRAME", " ".join(str(value) for value in frame_rgb(unit)))
            show(screen, "raw=%d" % raw)
        except Exception as error:
            emit_exception("I2C_FADER_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(400)
    try:
        unit.update_brightness()
        print("I2C_FADER_FRAME", " ".join(str(value) for value in frame_rgb(unit)))
    except Exception as error:
        emit_exception("I2C_FADER_BRIGHTNESS_ERROR", error)
    print("I2C_FADER_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "dac":
    from unit import DACUnit

    try:
        unit = DACUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_DAC_INIT_ERROR", error)
        raise
    print("BATCH2_PROBE_READY", CASE)
    try:
        unit.set_raw_value(2048)
        print("I2C_DAC_RAW", unit.get_raw_value())
        unit.set_voltage(1.0)
        print("I2C_DAC_RAW", unit.get_raw_value())
        print("I2C_DAC_VOLTAGE", round(unit.get_voltage(), 4))
        unit.save_to_eeprom()
        print("I2C_DAC_EEPROM", unit.get_raw_value())
        unit.set_raw_value(1024)
        print("I2C_DAC_RAW", unit.get_raw_value())
        show(screen, "dac")
    except Exception as error:
        emit_exception("I2C_DAC_ERROR", error)
    print("I2C_DAC_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "bps":
    from unit import BPSUnit

    try:
        unit = BPSUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_BPS_INIT_ERROR", error)
        raise
    print("BATCH2_PROBE_READY", CASE)
    for _ in range(8):
        try:
            temperature = unit.get_temperature()
            pressure = unit.get_pressure()
            altitude = unit.get_altitude()
            print("I2C_BPS", temperature, pressure, altitude)
            show(screen, "t=%.2f" % temperature)
        except Exception as error:
            emit_exception("I2C_BPS_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("I2C_BPS_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "adc-v11":
    from unit import ADCV11Unit
    from driver.ads1110 import GAIN_TWO, MODE_SINGLE, SPS_60

    try:
        unit = ADCV11Unit(make_bus())
    except Exception as error:
        emit_exception("I2C_ADC11_INIT_ERROR", error)
        raise
    print("BATCH2_PROBE_READY", CASE)
    for _ in range(6):
        try:
            raw = unit.get_adc_raw_value()
            print("I2C_ADC11_RAW", raw)
            print("I2C_ADC11_VOLTAGE", round(unit.get_voltage(), 4))
            show(screen, "adc=%d" % raw)
        except Exception as error:
            emit_exception("I2C_ADC11_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.set_gain(GAIN_TWO)
        print("I2C_ADC11_GAIN", unit.get_adc_raw_value())
        unit.set_sample_rate(SPS_60)
        print("I2C_ADC11_RATE", unit.get_adc_raw_value())
        unit.set_mode(MODE_SINGLE)
        unit.start_single_conversion()
        print("I2C_ADC11_SINGLE", unit.get_adc_raw_value())
        print("I2C_ADC11_FINAL_VOLTAGE", round(unit.get_voltage(), 4))
    except Exception as error:
        emit_exception("I2C_ADC11_CONFIG_ERROR", error)
    print("I2C_ADC11_END")
    while True:
        M5.update()
        time.sleep_ms(200)

else:
    raise ValueError("unknown batch2 probe case")
