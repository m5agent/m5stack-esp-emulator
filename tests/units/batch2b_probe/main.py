"""Guest probes for the remaining six Units of the second research batch.

Runs the reference UIFlow2 firmware's frozen original Unit drivers on real
controllers; no host value is written into a driver return path. The Device
Service captures UART0 markers and QOM state, and injects external fixture
values through unit-input.
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


print("BATCH2B_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch2b Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "env":
    from unit import ENVUnit

    try:
        unit = ENVUnit(make_bus(), 1)  # ENV_I: DHT12 0x5C + BMP280 0x76
    except Exception as error:
        emit_exception("I2C_ENV_INIT_ERROR", error)
        raise
    print("BATCH2B_PROBE_READY", CASE)
    for _ in range(8):
        try:
            print("I2C_ENV", round(unit.read_temperature(), 3),
                  round(unit.read_humidity(), 3), round(unit.read_pressure(), 3))
            show(screen, "env")
        except Exception as error:
            emit_exception("I2C_ENV_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("I2C_ENV_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "ameter":
    from unit import AMeterUnit

    try:
        unit = AMeterUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_AMETER_INIT_ERROR", error)
        raise
    print("BATCH2B_PROBE_READY", CASE)
    for _ in range(6):
        try:
            print("I2C_AMETER", round(unit.get_current(), 4), int(unit.get_adc_raw()))
            show(screen, "ameter")
        except Exception as error:
            emit_exception("I2C_AMETER_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        print("I2C_AMETER_GAIN", unit.get_gain(), unit.get_data_rate(),
              unit.get_operation_mode())
    except Exception as error:
        emit_exception("I2C_AMETER_CONFIG_ERROR", error)
    try:
        # The product page warns not to write the factory calibration EEPROM;
        # the model must reject this write and count the attempt.
        unit.save_calibration(5, 1000, 1000)
        print("I2C_AMETER_EEPROM_WRITE", 1)
    except Exception as error:
        print("I2C_AMETER_EEPROM_WRITE_REJECTED", repr(error))
    print("I2C_AMETER_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "extencoder":
    from unit import ExtEncoderUnit

    try:
        unit = ExtEncoderUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_EXTENC_INIT_ERROR", error)
        raise
    print("BATCH2B_PROBE_READY", CASE)
    wait_ms(1000)  # let the service inject the counter fixture first
    for _ in range(6):
        try:
            print("I2C_EXTENC", unit.get_rotary_value(), int(unit.get_rotary_status()))
            show(screen, "extenc")
        except Exception as error:
            emit_exception("I2C_EXTENC_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        print("I2C_EXTENC_INCREMENTS", unit.get_rotary_increments())
        unit.set_perimeter(500)
        unit.set_pulse(20)
        unit.set_zero_mode(1)
        unit.set_zero_pulse_value(10)
        print("I2C_EXTENC_CONFIG", unit.get_perimeter(), unit.get_pulse(),
              unit.get_zero_mode(), unit.get_zero_pulse_value())
        unit.reset_rotary_value()
        wait_ms(300)
        print("I2C_EXTENC_RESET", unit.get_rotary_value())
        print("I2C_EXTENC_FW", unit.get_firmware_version())
    except Exception as error:
        emit_exception("I2C_EXTENC_CONFIG_ERROR", error)
    print("I2C_EXTENC_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "ain4-20ma":
    from unit import AIN4_20MAUnit

    try:
        unit = AIN4_20MAUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_AIN4_INIT_ERROR", error)
        raise
    print("BATCH2B_PROBE_READY", CASE)
    for _ in range(6):
        try:
            print("I2C_AIN4", int(unit.get_adc_raw_value()),
                  round(unit.get_current_value(), 3),
                  unit.get_firmware_version(), unit.get_i2c_address())
            show(screen, "ain4")
        except Exception as error:
            emit_exception("I2C_AIN4_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.set_cal_current(15)
        print("I2C_AIN4_CAL_DONE", 15)
    except Exception as error:
        emit_exception("I2C_AIN4_CAL_ERROR", error)
    print("I2C_AIN4_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "acssr":
    from unit import ACSSRUnit

    try:
        unit = ACSSRUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_ACSSR_INIT_ERROR", error)
        raise
    print("BATCH2B_PROBE_READY", CASE)
    try:
        # I2C transaction-plane only: this is a relay register level, NOT an AC
        # mains switching claim.
        unit.on()
        print("I2C_ACSSR_RELAY", int(unit.value()))
        wait_ms(700)
        unit.fill_color(0x112233)
        print("I2C_ACSSR_RGB", unit.get_firmware_version() and 0x112233)
        unit.off()
        print("I2C_ACSSR_RELAY", int(unit.value()))
        wait_ms(500)
        print("I2C_ACSSR_FW", unit.get_firmware_version())
    except Exception as error:
        emit_exception("I2C_ACSSR_ERROR", error)
    print("I2C_ACSSR_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "gesture":
    from unit import GestureUnit

    try:
        unit = GestureUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_GESTURE_INIT_ERROR", error)
        raise
    print("BATCH2B_PROBE_READY", CASE)
    for _ in range(10):
        try:
            print("I2C_GESTURE", int(unit.get_hand_gestures()))
            show(screen, "gesture")
        except Exception as error:
            emit_exception("I2C_GESTURE_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("I2C_GESTURE_END")
    while True:
        M5.update()
        time.sleep_ms(200)

else:
    raise ValueError("unknown batch2b probe case")
