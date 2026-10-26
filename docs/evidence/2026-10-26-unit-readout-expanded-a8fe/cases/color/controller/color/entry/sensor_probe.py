import math
import time
import M5
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID, NO_FIXTURE
import probe_logging
from probe_logging import emit as print


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print("SENSOR_CHECK", name, "PASS")


def expect_nack(name, operation, write_length=None):
    try:
        acknowledged = operation()
    except OSError:
        check(name, True)
        return
    check(name, write_length is not None and acknowledged < write_length)


def pause(milliseconds):
    started = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), started) < milliseconds:
        M5.update()
        time.sleep_ms(5)


def read8(address, register):
    return bus.readfrom_mem(address, register, 1)[0]


def write8(address, register, value):
    return bus.writeto_mem(address, register, bytes([value]))


def read_word(register):
    bus.writeto(0x33, bytes([register >> 8, register & 255]), False)
    raw = bus.readfrom(0x33, 2)
    return (raw[0] << 8) | raw[1]


def write_word(register, value):
    return bus.writeto(0x33, bytes([register >> 8, register & 255, value >> 8, value & 255]))


def pec(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ (7 if value & 128 else 0)) & 255
    return value


print("SENSOR_PROBE_START", CASE)
M5.begin()
probe_logging.init()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Sensor: " + CASE)
bus = I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=400000)

if CASE == "color":
    from sensor_drivers.tcs3472 import TCS3472
    expect_nack("color_command_bit_required", lambda: bus.writeto(0x29, b"\x12"), 1)
    expect_nack("color_identity_read_only", lambda: bus.writeto(0x29, b"\x92\x00"), 2)
    unit = TCS3472(bus)
    unit.set_integration_time(614.4)
    unit.set_active(True)
    check("color_integration_not_ready", not (read8(0x29, 0x93) & 1))
    unit.set_integration_time(2.4)
    pause(10)
    limited = unit.get_color_raw()
    check("color_adc_saturation", limited == (1024, 1024, 1024, 1024))
    unit.set_integration_time(153.6)
elif CASE == "tof":
    from sensor_drivers.vl53l0x import VL53L0X
    write8(0x29, 0xBF, 0)
    check("tof_reset_identity_absent", read8(0x29, 0xC0) == 0)
    write8(0x29, 0xBF, 1)
    check("tof_reset_identity_restored", bus.readfrom_mem(0x29, 0xC0, 3) == b"\xee\xaa\x10")
    write8(0x29, 0, 1)
    check("tof_conversion_not_ready", read8(0x29, 0x13) & 7 == 0)
    pause(30)
    check("tof_conversion_ready", read8(0x29, 0x13) & 7 != 0)
    write8(0x29, 0x0B, 1)
    check("tof_interrupt_clear", read8(0x29, 0x13) & 7 == 0)
    unit = VL53L0X(bus, io_timeout_ms=3000)
    unit.set_address(0x2A)
    expect_nack("tof_old_address_nack", lambda: bus.readfrom_mem(0x29, 0xC0, 1))
    check("tof_new_address_identity", read8(0x2A, 0xC0) == 0xEE)
    unit.set_address(0x29)
elif CASE == "ncir":
    from sensor_drivers.mlx90614 import MLX90614
    expect_nack("ncir_eeprom_write_nack", lambda: bus.writeto(0x5A, b"\x24\x00\x00\x00"), 4)
    for register in (6, 7):
        raw = bus.readfrom_mem(0x5A, register, 3)
        check("ncir_pec_" + str(register), raw[2] == pec(bytes([0xB4, register, 0xB5]) + raw[:2]))
    unit = MLX90614(bus)
elif CASE == "heart":
    from sensor_drivers.heart import HeartUnit
    write8(0x57, 6, 0x40)
    pause(5)
    check("heart_reset_self_clear", read8(0x57, 6) & 0x40 == 0)
    check("heart_fifo_initially_empty", bus.readfrom_mem(0x57, 5, 4) == b"\x00\x00\x00\x00")
    write8(0x57, 7, 3)  # 50Hz, 16-bit pulse width.
    write8(0x57, 6, 3)
    pause(370)
    write8(0x57, 6, 0x83)  # Freeze the FIFO to inspect a complete sample.
    check("heart_fifo_overflow", read8(0x57, 3) > 0)
    before = read8(0x57, 4)
    raw = bus.readfrom_mem(0x57, 5, 4)
    check("heart_fifo_four_byte_advance", read8(0x57, 4) == (before + 1) & 15)
    check("heart_fifo_sample_order", raw == bytes([40000 >> 8, 40000 & 255, 35000 >> 8, 35000 & 255]))
    write8(0x57, 6, 0x40)
    pause(5)
    check("heart_reset_clears_fifo", bus.readfrom_mem(0x57, 2, 3) == b"\x00\x00\x00")
    write8(0x57, 6, 0x83)
    pause(80)
    check("heart_shutdown_stops_sampling", bus.readfrom_mem(0x57, 2, 3) == b"\x00\x00\x00")
    write8(0x57, 6, 0)
    unit = HeartUnit(bus)
    unit.set_pulse_width(unit.PULSE_WIDTH_1600US_ADC_16)
    unit.set_sampling_rate(unit.SAMPLING_RATE_100HZ)
    unit.start()
elif CASE == "tvoc":
    from sensor_drivers.sgp30 import SGP30, generate_crc
    expect_nack("tvoc_iaq_before_init_nack", lambda: bus.writeto(0x58, b"\x20\x08"), 2)
    unit = SGP30(bus, measure_test=True)
    warmup = unit.measure_iaq()
    check("tvoc_initialization_fixed_output", tuple(warmup) == (400, 0))
    bus.writeto(0x58, b"\x20\x32")
    expect_nack("tvoc_busy_read_nack", lambda: bus.readfrom(0x58, 3))
    pause(230)
    raw = bus.readfrom(0x58, 3)
    check("tvoc_response_crc", raw[:2] == b"\xd4\x00" and generate_crc(raw[:2]) == raw[2])
    expect_nack("tvoc_response_consumed", lambda: bus.readfrom(0x58, 3))
    bad_crc = generate_crc(b"\x00\x01") ^ 255
    command = b"\x20\x61\x00\x01" + bytes([bad_crc])
    expect_nack("tvoc_bad_argument_crc_nack", lambda: bus.writeto(0x58, command), len(command))
    pause(15)
    expect_nack("tvoc_unknown_command_nack", lambda: bus.writeto(0x58, b"\x12\x34"), 2)
    # Keep the datasheet's real 15-second initialization period.
    for second in range(16):
        M5.update()
        print("SENSOR_TVOC_WARMUP", second)
        pause(1000)
elif CASE == "ultrasonic-i2c":
    from sensor_drivers.ultrasonic_i2c import UltrasoundI2CUnit
    expect_nack("ultrasonic_unknown_command_nack", lambda: bus.writeto(0x57, b"\x02"), 1)
    bus.writeto(0x57, b"\x01")
    expect_nack("ultrasonic_conversion_not_ready", lambda: bus.readfrom(0x57, 3))
    pause(60)
    raw = bus.readfrom(0x57, 3)
    check("ultrasonic_uint24_units", (raw[0] << 16 | raw[1] << 8 | raw[2]) == 1000000)
    unit = UltrasoundI2CUnit(bus)
elif CASE == "thermal":
    if NO_FIXTURE:
        expect_nack("thermal_missing_fixture_nack", lambda: bus.readfrom(0x33, 2))
        print("SENSOR_PROBE_READY", CASE)
        while True:
            M5.update()
            time.sleep_ms(100)
    from sensor_drivers.mlx90640 import MLX90640
    expect_nack("thermal_eeprom_write_nack", lambda: bus.writeto(0x33, b"\x24\x00\x00\x00"), 4)
    write_word(0x800D, 0x1801)
    check("thermal_control_readback", read_word(0x800D) == 0x1801)
    old_page = read_word(0x8000) & 1
    write_word(0x8000, 0x0030)
    check("thermal_conversion_not_ready", read_word(0x8000) & 8 == 0)
    pause(2100)
    ready = read_word(0x8000)
    check("thermal_subpage_progression", bool(ready & 8) and (ready & 1) != old_page)
    unit = MLX90640(bus)
    unit.refresh_rate = unit.RefreshRate.REFRESH_2_HZ
    check("thermal_fixture_control_restored", read_word(0x800D) == 0x1901)
else:
    raise ValueError("unknown sensor case")

print("SENSOR_PROBE_READY", CASE)
previous = None
while True:
    M5.update()
    if CASE == "color":
        values = unit.get_color_raw()
        marker = "SENSOR_COLOR %d %d %d %d" % values
    elif CASE == "tof":
        values = (unit.get_range(), unit.get_distance())
        marker = "SENSOR_TOF %d %.3f" % values
    elif CASE == "ncir":
        values = (unit.get_ambient_temperature(), unit.get_object_temperature())
        marker = "SENSOR_NCIR %.4f %.4f" % values
    elif CASE == "heart":
        values = (unit.get_ir(), unit.get_red())
        marker = "SENSOR_HEART %d %d" % values
    elif CASE == "tvoc":
        iaq = unit.measure_iaq()
        raw = unit.measure_raw()
        values = (iaq[0], iaq[1], raw[0], raw[1])
        marker = "SENSOR_TVOC %d %d %d %d" % values
    elif CASE == "ultrasonic-i2c":
        values = (unit.get_target_distance(1), unit.get_target_distance(2))
        marker = "SENSOR_ULTRASONIC %.3f %.3f" % values
    else:
        values = unit.get_frame()
        finite = sum(1 for value in values if math.isfinite(value))
        check("thermal_768_finite", len(values) == 768 and finite == 768)
        print("SENSOR_THERMAL", len(values), finite, min(values), max(values), sum(values) / len(values))
        for index in (0, 1, 31, 32, 127, 255, 384, 511, 767):
            print("SENSOR_THERMAL_PIXEL", index, values[index])
        for y in range(24):
            for x in range(32):
                ratio = min(1, max(0, (values[y * 32 + x] - 27) / 8))
                color = (int(255 * ratio) << 16) | int(255 * (1 - ratio))
                screen.fillRect(80 + x * 5, 65 + y * 5, 5, 5, color)
        time.sleep_ms(500)
        continue
    print(marker)
    if values != previous:
        screen.fillRect(0, 38, screen.width(), 120, 0xFFFFFF)
        screen.setCursor(6, 42)
        screen.print(marker.replace(" ", "\n", 1))
        previous = values
    time.sleep_ms(1000 if CASE == "tvoc" else 150)
