"""Guest probes for the six Units of the sixth research batch (first half).

Runs the reference firmware's frozen original UIFlow2 drivers on real
controllers; no host value is placed in a driver return path. The Device
Service captures UART0 markers and QOM state. Fixtures are provided as
session-initial Unit inputs (or injected through unit-input where the probe has
a coordination point). ENV-Pro is special: the BME68x compensation inverse is
not modeled, so the probe only records chip/variant identity and raw field
bytes; guest-decoded temperature/humidity/pressure are printed as observation
and are NOT asserted as a PASS condition.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "BATCH6_PROBE_READY"


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


print("BATCH6_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch6 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "mini-scales":
    from unit import MiniScaleUnit

    try:
        unit = MiniScaleUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_MINISCALE_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("I2C_MINISCALE", unit.adc, unit.weight, int(unit.button))
        unit.tare()
        print("I2C_MINISCALE_TARE", unit.weight)
        unit.set_led(0x11, 0x22, 0x33)
        print("I2C_MINISCALE_LED_WRITTEN")
        unit.calibration(100.0, 1000, 200.0, 2000)
        unit.reset()
        unit.set_low_pass_filter(True)
        unit.set_average_filter_level(7)
        unit.set_ema_filter_alpha(42)
        wait_ms(300)
        print("I2C_MINISCALE_FILTERS", int(unit.get_low_pass_filter()),
              unit.get_average_filter_level(), unit.get_ema_filter_alpha())
        show(screen, "mini-scales")
    except Exception as error:
        emit_exception("I2C_MINISCALE_ERROR", error)
    print("I2C_MINISCALE_END")

elif CASE == "rgb-led-strip-50cm":
    from unit import RGBUnit

    try:
        unit = RGBUnit((WHITE, YELLOW), 30)
    except Exception as error:
        emit_exception("GPIO_RGB30_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.fill_color(0x112233)
        print("GPIO_RGB30_FILL")
        wait_ms(300)
        unit.set_color(5, 0x445566)
        print("GPIO_RGB30_INDEX")
        wait_ms(300)
        show(screen, "rgb strip 30")
    except Exception as error:
        emit_exception("GPIO_RGB30_WRITE_ERROR", error)
    print("GPIO_RGB30_END")

elif CASE == "op180":
    from unit import OPUnit

    try:
        unit = OPUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPIO_OP180_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    for _ in range(10):
        try:
            level = int(unit.pin.value())
            print("GPIO_OP180", level)
            show(screen, "op180=%d" % level)
        except Exception as error:
            emit_exception("GPIO_OP180_ERROR", error)
        wait_ms(200)
    print("GPIO_OP180_END")

elif CASE == "synth":
    from unit import SynthUnit

    try:
        unit = SynthUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_SYNTH_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.set_note_on(0, 60, 100)
        unit.set_note_off(0, 60)
        unit.set_instrument(0, 0, 40)
        unit.set_master_volume(100)
        print("UART_SYNTH_SENT")
        wait_ms(400)
        show(screen, "synth")
    except Exception as error:
        emit_exception("UART_SYNTH_ERROR", error)
    print("UART_SYNTH_END")

elif CASE == "mini-imu":
    from unit import IMUUnit

    try:
        unit = IMUUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_IMU_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        # IMUUnit defaults to m/s^2 and rad/s; switch to g and deg/s so the
        # probe records the catalog's accel-x-g / gyro-x-dps domain.
        unit.set_accel_unit(0)
        unit.set_gyro_unit(0)
        print("I2C_IMU_WHOAMI", unit.whoami())
        print("I2C_IMU_ACC", *unit.get_accelerometer())
        print("I2C_IMU_GYRO", *unit.get_gyroscope())
        print("I2C_IMU_TEMP", unit.temperature())
        print("I2C_IMU_RANGE0", unit._accel_so, unit._gyro_so)
        unit.set_accel_range(8)
        unit.set_gyro_range(1000)
        print("I2C_IMU_RANGE1", unit._accel_so, unit._gyro_so)
        print("I2C_IMU_ACC2", *unit.get_accelerometer())
        print("I2C_IMU_GYRO2", *unit.get_gyroscope())
        show(screen, "mini-imu")
    except Exception as error:
        emit_exception("I2C_IMU_ERROR", error)
    print("I2C_IMU_END")

elif CASE == "env-pro":
    from unit import ENVPROUnit

    try:
        unit = ENVPROUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_BME_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        # Identity + raw field bytes only. The BME68x compensation inverse is
        # not modeled, so decoded T/RH/P are observation-only.
        print("I2C_BME_ID", unit._read_byte(0xD0), unit._variant_id)
        raw = bytes(unit._read(0x1D, 10))
        print("I2C_BME_RAW", raw.hex())
        print("I2C_BME_STATUS", unit._read_byte(0x1D))
        try:
            print("I2C_BME_DECODED_OBSERVATION", unit.get_temperature(),
                  unit.get_humidity(), unit.get_pressure(), unit.get_gas_resistance())
        except Exception as observation_error:
            emit_exception("I2C_BME_DECODED_OBSERVATION_ERROR", observation_error)
        show(screen, "env-pro")
    except Exception as error:
        emit_exception("I2C_BME_ERROR", error)
    print("I2C_BME_END")

else:
    raise ValueError("unknown batch6 probe case")

while True:
    M5.update()
    time.sleep_ms(200)
