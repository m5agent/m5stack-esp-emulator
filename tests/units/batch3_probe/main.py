"""Guest probes for the twelve Units of the third research batch.

Runs the reference UIFlow2 firmware's frozen original drivers on real
controllers; no host value is written into a driver return path. The Device
Service captures UART0 markers and QOM state, and injects external fixture
values through unit-input. Branches are defensive: a known frozen-driver bug is
reported as a marker instead of hiding it, so the evidence can record a real
blocked path.
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


print("BATCH3_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch3 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "rfid":
    from unit import RFIDUnit

    try:
        unit = RFIDUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_RFID_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(8):
        try:
            present = unit.is_new_card_present()
            uid = unit.read_card_uid()
            print("I2C_RFID", int(present), "" if uid is None else bytes(uid).hex())
            try:
                block = unit.read(1)
                print("I2C_RFID_BLOCK", "" if block is None else bytes(block).hex())
            except Exception as error:
                print("I2C_RFID_BLOCK_ERROR", repr(error))
            show(screen, "rfid")
        except Exception as error:
            emit_exception("I2C_RFID_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("I2C_RFID_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "tube-pressure":
    from unit import TubePressureUnit

    try:
        unit = TubePressureUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("ADC_TUBE_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(8):
        try:
            # read_uv()/get_pressure()/get_voltage() need the S3 ADC calibration
            # fixture, which is NOT applied in this batch; only the raw ADC path
            # is exercised. Report the unsupported conversion honestly.
            try:
                print("ADC_TUBE_PRESSURE", round(unit.get_pressure(), 3))
            except OSError as error:
                print("ADC_TUBE_PRESSURE_UNSUPPORTED", repr(error))
            try:
                print("ADC_TUBE_VOLTAGE", round(unit.get_voltage(), 3))
            except OSError as error:
                print("ADC_TUBE_VOLTAGE_UNSUPPORTED", repr(error))
            print("ADC_TUBE_RAW", unit.get_analog_value(16), unit.get_analog_value(12))
            show(screen, "tube")
        except Exception as error:
            emit_exception("ADC_TUBE_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("ADC_TUBE_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "laser-rx":
    from unit import LaserRXUnit

    try:
        unit = LaserRXUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPIO_LASER_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(10):
        try:
            print("GPIO_LASER", int(unit.value()))
            show(screen, "laser")
        except Exception as error:
            emit_exception("GPIO_LASER_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("GPIO_LASER_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "extio":
    from unit import EXTIOUnit

    try:
        unit = EXTIOUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_EXTIO_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    wait_ms(800)  # let the service inject the input-levels fixture first
    try:
        print("I2C_EXTIO_READ", unit.digit_read_port())
        unit.set_port_mode(unit.OUT)
        unit.digit_write_port(0xA5)
        print("I2C_EXTIO_WRITE", 0xA5)
        print("I2C_EXTIO_READBACK", unit.digit_read_port())
        unit.digit_write_port(0x00)
        print("I2C_EXTIO_WRITE", 0x00)
        unit.set_port_mode(unit.IN)
        print("I2C_EXTIO_READ", unit.digit_read_port())
        for _ in range(6):
            M5.update()
            time.sleep_ms(150)
    except Exception as error:
        emit_exception("I2C_EXTIO_ERROR", error)
    print("I2C_EXTIO_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "dac2":
    from unit import DAC2Unit

    try:
        unit = DAC2Unit(make_bus())
    except Exception as error:
        emit_exception("I2C_DAC2_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    try:
        unit.set_dacoutput_voltage_range(unit.RANGE_5V)
        unit.set_voltage(1.0, unit.CHANNEL_1)
        print("I2C_DAC2_CH1", 1.0)
        unit.set_voltage(2.0, unit.CHANNEL_0)
        print("I2C_DAC2_CH0", 2.0)
        unit.set_voltage_both(1.0, 2.0)
        print("I2C_DAC2_BOTH", 1.0, 2.0)
        unit.set_dacoutput_voltage_range(unit.RANGE_10V)
        unit.set_voltage(10.0, unit.CHANNEL_BOTH)
        print("I2C_DAC2_RANGE1", 10.0)
    except Exception as error:
        emit_exception("I2C_DAC2_ERROR", error)
    print("I2C_DAC2_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "scales":
    from unit import ScalesUnit

    try:
        unit = ScalesUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_SCALES_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    wait_ms(600)
    for _ in range(6):
        try:
            print("I2C_SCALES", unit.get_scale_value(0), unit.get_scale_value(1))
            show(screen, "scales")
        except Exception as error:
            emit_exception("I2C_SCALES_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.set_rgb_led(0x112233)
        print("I2C_SCALES_RGB", unit.get_rgb_led())
        unit.set_rgbled_sync(1)
        print("I2C_SCALES_SYNC", unit.get_rgbled_sync())
        unit.set_raw_offset(123)
        unit.set_calibration_zero()
        print("I2C_SCALES_CAL_ZERO")
        unit.set_calibration_load(1000)
        print("I2C_SCALES_CAL_LOAD", 1000)
        print("I2C_SCALES_FW", unit.get_device_inform(0xFE))
    except Exception as error:
        emit_exception("I2C_SCALES_CONFIG_ERROR", error)
    print("I2C_SCALES_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "vmeter":
    from unit import VoltmeterUnit

    try:
        unit = VoltmeterUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_VMETER_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(6):
        try:
            print("I2C_VMETER", round(unit.get_voltage(), 4), int(unit.get_adc_raw()),
                  unit.get_gain(), unit.get_data_rate())
            show(screen, "vmeter")
        except Exception as error:
            emit_exception("I2C_VMETER_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        print("I2C_VMETER_CAL", unit.read_calibration(unit.get_gain()))
        # Frozen module constants are module-level (PGA_256 etc.), not class
        # attributes; use the documented numeric values instead.
        unit.set_gain(5)          # PGA_256
        unit.set_data_rate(4)     # RATE_128
        unit.set_operation_mode(1)  # MODE_SINGLESHOT
        print("I2C_VMETER_CONFIG", unit.get_gain(), unit.get_data_rate(),
              unit.get_operation_mode())
        unit.save_calibration(5, 1000, 1000)
        print("I2C_VMETER_EEPROM_WRITE", 1)
    except Exception as error:
        print("I2C_VMETER_EEPROM_WRITE_REJECTED", repr(error))
    print("I2C_VMETER_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "adc":
    from unit import ADCUnit

    try:
        unit = ADCUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_ADC_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(6):
        try:
            print("I2C_ADC", int(unit.get_value()), unit.get_raw_value().hex()
                  if hasattr(unit.get_raw_value(), "hex") else
                  bytes(unit.get_raw_value()).hex(), round(unit.get_voltage(), 4),
                  unit.get_gain(), unit.get_data_rate(), unit.get_operating_mode())
            show(screen, "adc")
        except Exception as error:
            emit_exception("I2C_ADC_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.set_gain(2)
        unit.set_data_rate(16)
        unit.set_operating_mode(unit.SINGLE)
        try:
            converted = unit.get_value()
        except TypeError:
            converted = "None(single-shot SC bit set)"
        print("I2C_ADC_CONFIG", unit.get_gain(), unit.get_data_rate(),
              unit.get_operating_mode(), converted)
    except Exception as error:
        emit_exception("I2C_ADC_CONFIG_ERROR", error)
    print("I2C_ADC_END")
    while True:
        M5.update()
        time.sleep_ms(200)

# ---------------------------------------------------------------------------
# C-class branches: the frozen firmware's drivers have documented bugs/API
# rewrites, so every step is attempted defensively and failures are reported.
# ---------------------------------------------------------------------------

elif CASE == "env-iv":
    from driver.bmp280 import BMP280

    try:
        from unit import ENVUnit, ENV_IV
    except Exception as error:
        ENV_IV = 4
        emit_exception("I2C_ENV4_IMPORT_FALLBACK", error)
    print("BATCH3_PROBE_READY", CASE)
    try:
        from driver.sht4x import SHT4x as SHT4xDriver

        sht = SHT4xDriver(make_bus(), 0x44)
        print("I2C_SHT4X_INIT_OK")
    except Exception as error:
        sht = None
        emit_exception("I2C_SHT4X_INIT_ERROR", error)
    if sht is not None:
        for name in ("serial_number", "get_serial_number", "measure",
                     "get_temperature", "get_humidity", "temperature",
                     "relative_humidity"):
            try:
                attribute = getattr(sht, name)
                if callable(attribute):
                    print("I2C_SHT4X_CALL", name, attribute())
                else:
                    print("I2C_SHT4X_ATTR", name, attribute)
            except Exception as error:
                print("I2C_SHT4X_ATTR_ERROR", name, repr(error))
        for _ in range(4):
            try:
                print("I2C_SHT4X_MEASURE", sht.measure())
            except Exception as error:
                print("I2C_SHT4X_MEASURE_ERROR", repr(error))
            M5.update()
            time.sleep_ms(200)
    try:
        bmp = BMP280(make_bus())
        for _ in range(6):
            temperature, pressure = bmp.measure()
            print("I2C_ENV4_BMP280", round(pressure / 100, 3), round(temperature, 3))
            M5.update()
            time.sleep_ms(300)
    except Exception as error:
        emit_exception("I2C_ENV4_BMP280_ERROR", error)
    try:
        env = ENVUnit(make_bus(), 4)
        print("I2C_ENV4_INIT_OK")
        for _ in range(6):
            print("I2C_ENV4", round(env.read_temperature(), 3),
                  round(env.read_humidity(), 3), round(env.read_pressure(), 3))
            M5.update()
            time.sleep_ms(300)
    except Exception as error:
        emit_exception("I2C_ENV4_ERROR", error)
    print("I2C_ENV4_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "co2":
    from unit import CO2Unit

    try:
        unit = CO2Unit(make_bus())
    except Exception as error:
        emit_exception("I2C_CO2_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    def maybe_await(value):
        if value is not None and type(value).__name__ == "coroutine":
            try:
                import uasyncio as asyncio
                return asyncio.run(value)
            except Exception as error:
                return "AWAIT_ERROR:" + repr(error)
        return value

    for name in ("get_serial_number", "is_data_ready", "data_isready",
                 "get_sensor_measurement", "get_temperature_offset",
                 "get_sensor_altitude", "data_isready"):
        try:
            print("I2C_CO2_CALL", name, maybe_await(getattr(unit, name)()))
        except Exception as error:
            print("I2C_CO2_CALL_ERROR", name, repr(error))
    for name in ("set_start_periodic_measurement", "set_continuous_start_measurement"):
        try:
            print("I2C_CO2_START", name, maybe_await(getattr(unit, name)()))
        except Exception as error:
            print("I2C_CO2_START_ERROR", name, repr(error))
    for _ in range(6):
        try:
            print("I2C_CO2_READY", int(bool(maybe_await(unit.is_data_ready()))))
            measurement = maybe_await(unit.get_sensor_measurement())
            if measurement is not None:
                print("I2C_CO2_MEASUREMENT", measurement)
            for attr in ("co2", "humidity", "temperature"):
                try:
                    print("I2C_CO2_ATTR", attr, getattr(unit, attr))
                except Exception as error:
                    print("I2C_CO2_ATTR_ERROR", attr, repr(error))
        except Exception as error:
            print("I2C_CO2_ERROR", repr(error))
        M5.update()
        time.sleep_ms(400)
    for name in ("set_stop_periodic_measurement", "set_continuous_stop_measurement"):
        try:
            print("I2C_CO2_STOP", name, maybe_await(getattr(unit, name)()))
        except Exception as error:
            print("I2C_CO2_STOP_ERROR", name, repr(error))
    print("I2C_CO2_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "pbhub":
    from unit import PBHUBUnit

    try:
        unit = PBHUBUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_PBHUB_INIT_ERROR", error)
        raise
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(6):
        try:
            print("I2C_PBHUB", int(unit.digital_read(0, 0)), int(unit.digital_read(0, 1)),
                  unit.analog_read(0))
            show(screen, "pbhub")
        except Exception as error:
            emit_exception("I2C_PBHUB_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.digital_write(0, 0, 1)
        unit.digital_write(0, 1, 0)
        print("I2C_PBHUB_DIGITAL", 1, 0)
        unit.pwm_write(0, 0, 50)
        print("I2C_PBHUB_PWM", 50)
        unit.set_rgb_led_num(0, 1)
        unit.set_rgb_color(0, 0, 1, 0xFF0000)
        unit.set_rgb_brightness(0, 128)
        print("I2C_PBHUB_RGB", 1, 0xFF0000, 128)
        for name, args in (("read_status", (0xFE,)), ("read_status", (0xFF,)),
                           ("get_rgb_mode", ())):
            try:
                print("I2C_PBHUB_CALL", name, args, getattr(unit, name)(*args))
            except Exception as error:
                print("I2C_PBHUB_CALL_ERROR", name, repr(error))
        try:
            unit.set_rgb_mode(1)
            print("I2C_PBHUB_RGB_MODE", unit.get_rgb_mode())
        except Exception as error:
            print("I2C_PBHUB_RGB_MODE_ERROR", repr(error))
    except Exception as error:
        emit_exception("I2C_PBHUB_CONFIG_ERROR", error)
    print("I2C_PBHUB_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "ultrasonic-io":
    print("GPIO_ULTRA_STEP_IMPORT")
    try:
        from unit import ULTRASONIC_IOUnit
        print("GPIO_ULTRA_STEP_IMPORT_PACKAGE")
    except Exception as error:
        emit_exception("GPIO_ULTRA_IMPORT_PACKAGE_ERROR", error)
        from unit.ultrasonic_io import ULTRASONIC_IOUnit
        print("GPIO_ULTRA_STEP_IMPORT_MODULE")
    print("GPIO_ULTRA_STEP_CONSTRUCT")
    try:
        unit = ULTRASONIC_IOUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPIO_ULTRA_INIT_ERROR", error)
        raise
    print("GPIO_ULTRA_STEP_CONSTRUCTED")
    print("BATCH3_PROBE_READY", CASE)
    for _ in range(10):
        try:
            echo = unit.tx_pulse_rx_echo()
            print("GPIO_ULTRA_ECHO", echo)
            if echo is None:
                print("GPIO_ULTRA_TIMEOUT")
            else:
                print("GPIO_ULTRA", unit.get_target_distance(1), unit.get_target_distance(2))
            show(screen, "ultra")
        except Exception as error:
            print("GPIO_ULTRA_ERROR", repr(error))
        M5.update()
        time.sleep_ms(200)
    try:
        # Second path: a 1000us echo timeout is smaller than the model's
        # distance-derived 5820us pulse, so machine.time_pulse_us must report
        # the guest-side timeout instead of a distance.
        fast = ULTRASONIC_IOUnit((WHITE, YELLOW), echo_timeout_us=1000)
        print("GPIO_ULTRA_FAST_TIMEOUT", fast.get_target_distance(1))
    except Exception as error:
        print("GPIO_ULTRA_FAST_ERROR", repr(error))
    print("GPIO_ULTRA_END")
    while True:
        M5.update()
        time.sleep_ms(200)

else:
    raise ValueError("unknown batch3 probe case")
