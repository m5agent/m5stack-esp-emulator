"""Guest probes for the twelve Units of the fourth research batch.

Runs the reference UIFlow2 firmware's frozen original drivers on real
controllers; no host value is written into a driver return path. The Device
Service captures UART0 markers and QOM state, and injects external fixtures
through unit-input / QOM. Branches are defensive: known frozen-driver and
boundary conditions are reported as markers instead of hiding them.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "BATCH4_PROBE_READY"


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


print("BATCH4_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch4 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "co2l":
    from unit import CO2LUnit

    try:
        unit = CO2LUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_CO2L_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(800)
    for _ in range(3):
        try:
            unit.get_sensor_measurement()
            print("I2C_CO2L", unit.co2, unit.humidity, unit.temperature)
            print("I2C_CO2L_READY", int(unit.is_data_ready()))
            show(screen, "CO2L=%s RH=%s" % (unit.co2, unit.humidity))
        except Exception as error:
            emit_exception("I2C_CO2L_READ_ERROR", error)
        wait_ms(200)
    try:
        # The frozen SCD4x driver rejects get_serial_number() while a periodic
        # measurement is running, so stop it first (a real protocol path).
        unit.set_stop_periodic_measurement()
        wait_ms(200)
        print("I2C_CO2L_SERIAL", unit.get_serial_number())
    except Exception as error:
        emit_exception("I2C_CO2L_SERIAL_ERROR", error)
    print("I2C_CO2L_END")

elif CASE == "rs485-iso":
    try:
        from unit import RS485Unit

        try:
            unit = RS485Unit(1, (WHITE, YELLOW))
        except TypeError as error:
            # Frozen RS485Unit wrapper calls its uSerial base with an incompatible
            # argument list on this firmware; use the official uSerial driver the
            # wrapper inherits from, on the same pins.
            emit_exception("UART_RS485_WRAPPER_FALLBACK", error)
            from driver.modbus.master.uSerial import uSerial

            base = uSerial(1, YELLOW, WHITE)
            unit = base._mdbus_uart
            print("UART_RS485_DRIVER uSerial._mdbus_uart")
    except Exception as error:
        emit_exception("UART_RS485_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        unit.write(b"HELLO")
        print("UART_RS485_TX", b"HELLO".hex())
    except Exception as error:
        emit_exception("UART_RS485_TX_ERROR", error)
    received = b""
    for _ in range(30):
        try:
            count = unit.any()
            if count:
                data = unit.read(count)
                if data:
                    received += data
                    print("UART_RS485_RX", bytes(data).hex())
                    if len(received) >= 6:
                        break
        except Exception as error:
            emit_exception("UART_RS485_RX_ERROR", error)
            break
        wait_ms(100)
    print("UART_RS485_RX_TOTAL", bytes(received).hex())
    print("UART_RS485_END")

elif CASE == "laser-tx":
    from unit import LaserTXUnit

    try:
        unit = LaserTXUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPIO_LASER_TX_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    for level in (1, 0, 1, 0):
        try:
            unit.value(level)
            print("GPIO_LASER_TX_LEVEL", level)
            show(screen, "laser=%d" % level)
        except Exception as error:
            emit_exception("GPIO_LASER_TX_WRITE_ERROR", error)
        wait_ms(250)
    print("GPIO_LASER_TX_END")

elif CASE == "neco":
    from unit import NECOUnit

    try:
        # The product page documents 35 LEDs; the frozen driver defaults to 70.
        unit = NECOUnit((WHITE, YELLOW), 35)
    except Exception as error:
        emit_exception("GPIO_NECO_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.set_color_from(0, 4, 0x112233)
        print("GPIO_NECO_RGB", 0x112233)
        show(screen, "neco rgb")
    except Exception as error:
        emit_exception("GPIO_NECO_RGB_ERROR", error)
    wait_ms(300)
    print("GPIO_NECO_END")

elif CASE == "midi":
    from unit import MIDIUnit

    try:
        unit = MIDIUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_MIDI_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.set_note_on(0, 60, 100)
        unit.set_note_off(0, 60)
        unit.set_instrument(0, 0, 5)
        print("UART_MIDI_SENT", "903c64803c00b00000c005")
        show(screen, "midi sent")
    except Exception as error:
        emit_exception("UART_MIDI_WRITE_ERROR", error)
    wait_ms(300)
    print("UART_MIDI_END")

elif CASE == "tof4m":
    from unit import TOF4MUnit

    try:
        unit = TOF4MUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_TOF4M_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("I2C_TOF4M_MODEL", unit.get_model_info)
        unit.set_continuous_start_measurement()
        unit.clear_interrupt()
        wait_ms(300)
        print("I2C_TOF4M_READY", int(unit.get_data_ready))
        distance = unit.get_distance
        print("I2C_TOF4M_DIST", distance)
        print("I2C_TOF4M_BUDGET", unit.get_measurement_timing_budget)
        show(screen, "tof=%s" % distance)
    except Exception as error:
        emit_exception("I2C_TOF4M_READ_ERROR", error)
    print("I2C_TOF4M_END")

elif CASE == "weight":
    from unit import WeightUnit

    try:
        unit = WeightUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPIO_WEIGHT_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        raw = unit.get_raw_weight
        print("GPIO_WEIGHT_RAW", raw)
        print("GPIO_WEIGHT_READY", int(unit.is_ready_wait()))
        show(screen, "weight raw=%s" % raw)
    except Exception as error:
        emit_exception("GPIO_WEIGHT_READ_ERROR", error)
    print("GPIO_WEIGHT_END")

elif CASE == "bldc-driver":
    from unit import BLDCDriverUnit

    try:
        unit = BLDCDriverUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_BLDC_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        unit.set_mode(1)
        print("I2C_BLDC_MODE", unit.get_current_mode)
        unit.set_direction(1)
        print("I2C_BLDC_DIR", unit.get_motor_current_direction)
        unit.set_motor_model(1)
        print("I2C_BLDC_MODEL", unit.get_motor_current_model)
        unit.set_pole_pairs(11)
        print("I2C_BLDC_POLES", unit.get_motor_pole_pairs)
        unit.set_open_loop_pwm(1000)
        print("I2C_BLDC_PWM", unit.get_open_loop_pwm)
        unit.set_rpm_float(1500.0)
        print("I2C_BLDC_RPM", unit.get_rpm_float, unit.get_read_back_rpm_float)
        unit.set_pid_value(10, 20, 30)
        print("I2C_BLDC_PID", unit.get_pid_value)
        unit.save_data_in_flash()
        print("I2C_BLDC_STATUS", unit.get_motor_status)
        print("I2C_BLDC_SPEC", unit.get_device_spec(0xFE), unit.get_device_spec(0xFF))
        show(screen, "bldc rpm=%s" % unit.get_read_back_rpm_float)
    except Exception as error:
        emit_exception("I2C_BLDC_READ_ERROR", error)
    print("I2C_BLDC_END")

elif CASE == "ac-measure":
    try:
        try:
            from unit import AC_MEASUREUnit
        except Exception as import_error:
            emit_exception("I2C_ACMEASURE_PACKAGE_IMPORT_FALLBACK", import_error)
            from unit.ac_measure import AC_MEASUREUnit

        unit = AC_MEASUREUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_ACMEASURE_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("I2C_ACMEASURE_V", unit.get_voltage_str())
        print("I2C_ACMEASURE_I", unit.get_current_str())
        print("I2C_ACMEASURE_P", unit.get_active_power_str())
        print("I2C_ACMEASURE_S", unit.get_apparent_power_str())
        print("I2C_ACMEASURE_PF", unit.get_power_factor_str())
        print("I2C_ACMEASURE_KWH", unit.get_kwh_str())
        print(
            "I2C_ACMEASURE_BYTE",
            unit.get_voltage_byte(),
            unit.get_current_byte(),
            unit.get_active_power_byte(),
            unit.get_apparent_power_byte(),
            unit.get_power_factor_byte(),
            unit.get_kwh_byte(),
        )
        unit.set_voltage_coeff(12)
        unit.set_current_coeff(34)
        unit.set_save_coeff()
        print("I2C_ACMEASURE_COEFF", unit.get_voltage_coeff(), unit.get_current_coeff())
        print("I2C_ACMEASURE_READY", int(unit.get_data_ready()))
        show(screen, "acm V=%s" % unit.get_voltage_str())
    except Exception as error:
        emit_exception("I2C_ACMEASURE_READ_ERROR", error)
    print("I2C_ACMEASURE_END")

elif CASE == "dds":
    from unit import DDSUnit

    try:
        unit = DDSUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_DDS_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        unit.set_freq(0, 1000)
        unit.set_phase(0, 90)
        unit.set_mode(DDSUnit.WAVE_SINE)
        unit.set_ctrl(0x80)
        print("I2C_DDS_MODE", unit.i2c.readfrom_mem(0x31, 0x20, 1).hex())
        print("I2C_DDS_FREQ", unit.i2c.readfrom_mem(0x31, 0x30, 4).hex())
        print("I2C_DDS_PHASE", unit.i2c.readfrom_mem(0x31, 0x34, 2).hex())
        print("I2C_DDS_WAVE", unit.i2c.readfrom_mem(0x31, 0x21, 1).hex())
        show(screen, "dds 1000Hz")
    except Exception as error:
        emit_exception("I2C_DDS_READ_ERROR", error)
    print("I2C_DDS_END")

elif CASE == "gps":
    from unit import GPSUnit

    try:
        unit = GPSUnit(1, (WHITE, YELLOW))
        unit.set_time_zone(0)
    except Exception as error:
        emit_exception("UART_GPS_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    for _ in range(25):
        try:
            print(
                "GPS_STATE",
                unit.gps_time,
                unit.latitude,
                unit.longitude,
                unit.altitude,
                unit.satellite_num,
                unit.pos_quality,
                unit.gps_date,
                unit.course,
                unit.speed_knot,
                unit.speed_kph,
            )
            show(screen, "gps " + unit.gps_time)
        except Exception as error:
            emit_exception("UART_GPS_READ_ERROR", error)
        wait_ms(200)
    print("UART_GPS_END")

elif CASE == "uhf-rfid":
    from unit import UHFRFIDUnit

    try:
        unit = UHFRFIDUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_UHF_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(900)
    for attempt in range(2):
        try:
            epc = unit.inventory()
            if isinstance(epc, (bytes, bytearray, memoryview)):
                text = bytes(epc).hex()
            elif isinstance(epc, str):
                text = epc
            else:
                text = "" if epc is None else str(epc)
            print("UART_UHF_EPC", text)
            show(screen, "uhf epc")
        except Exception as error:
            emit_exception("UART_UHF_READ_ERROR", error)
        wait_ms(500)
    print("UART_UHF_END")

else:
    raise ValueError("unknown batch4 probe case")

while True:
    M5.update()
    time.sleep_ms(200)
