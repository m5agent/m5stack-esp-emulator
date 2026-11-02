"""Guest probes for the C-class Unit batch (ncir2/extio2/hbridge).

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

_console = UART(0, baudrate=115200, tx=43, rx=44)


def print(*parts):
    _console.write(" ".join(str(part) for part in parts) + "\n")


def emit_exception(prefix, error):
    import io

    trace = io.StringIO()
    sys.print_exception(error, trace)
    print(prefix, trace.getvalue().replace("\n", " | "))


def show(text):
    screen.fillRect(0, 38, screen.width(), 150, 0xFFFFFF)
    screen.setCursor(6, 42)
    screen.print(str(text))


def wait_ms(duration):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < duration:
        M5.update()
        time.sleep_ms(10)


print("CCLASS_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("C Unit: " + CASE)

bus = I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)
print("CCLASS_PROBE_SCAN", [hex(value) for value in bus.scan()])

if CASE == "ncir2":
    from unit import NCIR2Unit

    try:
        unit = NCIR2Unit(bus, 0x5A)
    except Exception as error:
        emit_exception("I2C_NCIR2_INIT_ERROR", error)
        raise
    print("CCLASS_PROBE_READY", CASE)
    for _ in range(6):
        try:
            temperature = unit.get_temperature_value
            chip = unit.get_chip_temperature
            emissivity = unit.get_emissivity_value
            pressed = unit.get_button_status
            print("I2C_NCIR2", round(temperature, 3), round(chip, 3),
                  round(emissivity, 4), int(pressed))
            show("t=%.2f" % temperature)
        except Exception as error:
            emit_exception("I2C_NCIR2_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.set_emissivity_value(0.5)
        print("I2C_NCIR2_EMISS", round(unit.get_emissivity_value, 4))
        unit.set_temperature_threshold(0x20, 5.0)
        unit.set_temperature_threshold(0x22, 40.0)
        print("I2C_NCIR2_THRESH",
              unit.get_temperature_threshold(0x20),
              unit.get_temperature_threshold(0x22))
        unit.set_temp_alarm_led(0x30, 0x112233)
        print("I2C_NCIR2_ALARM_RGB", unit.get_temp_alarm_led(0x30))
        unit.set_buzzer_freq(2000)
        unit.set_buzzer_duty(50)
        unit.set_buzzer_control(1)
        print("I2C_NCIR2_BUZZER", unit.get_buzzer_freq,
              unit.get_buzzer_duty, int(unit.get_buzzer_control))
        unit.set_rgb_led(0x0A0B0C)
        print("I2C_NCIR2_RGB", unit.get_rgb_led)
        unit.save_config_setting
        print("I2C_NCIR2_SPEC", unit.get_device_spec(0xFE), unit.get_device_spec(0xFF))
    except Exception as error:
        emit_exception("I2C_NCIR2_CONFIG_ERROR", error)
    print("I2C_NCIR2_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "extio2":
    from unit import EXTIO2Unit

    try:
        unit = EXTIO2Unit(bus, 0x45)
    except Exception as error:
        emit_exception("I2C_EXTIO2_INIT_ERROR", error)
        raise
    print("CCLASS_PROBE_READY", CASE)
    # Give the Device Service a window to inject the fixture values first.
    wait_ms(1200)
    # Modes follow the official driver: 0=IN, 1=OUT, 2=ANALOG, 3=SERVO, 4=NEOPIXEL.
    modes = [0, 1, 2, 3, 4, 0, 1, 2]
    try:
        for channel, mode in enumerate(modes):
            unit.set_config_mode(channel, mode)
        for channel in (0, 1, 5, 6):
            unit.write_output_pin(channel, 1)
        unit.write_servo_angle(3, 90)
        unit.write_servo_pulse(4, 1500)
        unit.write_rgb_led(2, 0x112233)
        unit.write_rgb_led(7, 0x445566)
        print("I2C_EXTIO2_MODES", [unit.get_config_mode(i) for i in range(8)])
        print("I2C_EXTIO2_SERVO", unit.read_servo_angle(3), unit.read_servo_pulse(4))
        print("I2C_EXTIO2_RGB", unit.read_rgb_led(2), unit.read_rgb_led(7))
        print("I2C_EXTIO2_FW", unit.read_fw_version(), unit.get_address())
    except Exception as error:
        emit_exception("I2C_EXTIO2_CONFIG_ERROR", error)
    for _ in range(6):
        try:
            print("I2C_EXTIO2_INPUTS", [unit.read_input_pin(i) for i in range(8)])
            print("I2C_EXTIO2_ADC8", [unit.read_adc8_pin(i) for i in range(8)])
            print("I2C_EXTIO2_ADC12", [unit.read_adc12_pin(i) for i in range(8)])
            print("I2C_EXTIO2_FW", unit.read_fw_version(), unit.get_address())
            show("extio2")
        except Exception as error:
            emit_exception("I2C_EXTIO2_READ_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    print("I2C_EXTIO2_END")
    while True:
        M5.update()
        time.sleep_ms(200)

elif CASE == "hbridge":
    from unit import HbridgeUnit

    try:
        unit = HbridgeUnit(bus, 0x20)
    except Exception as error:
        emit_exception("I2C_HBRIDGE_INIT_ERROR", error)
        raise
    print("CCLASS_PROBE_READY", CASE)
    for _ in range(5):
        try:
            unit.set_direction(1)
            unit.set_16bit_pwm(32767)
            unit.set_pwm_freq(500)
            direction = unit.get_driver_config(0x00)
            pwm16 = unit.get_driver_config(0x02)
            frequency = unit.get_driver_config(0x04)
            adc8 = unit.get_adc_value(raw=1, res=8)
            adc16 = unit.get_adc_value(raw=1, res=16)
            current = unit.get_vin_current()
            print("I2C_HBRIDGE", direction, pwm16, frequency,
                  adc8, adc16, round(current, 4))
            show("dir=%d" % direction)
        except Exception as error:
            emit_exception("I2C_HBRIDGE_ERROR", error)
            raise
        M5.update()
        time.sleep_ms(300)
    try:
        unit.set_direction(2)
        unit.set_8bit_pwm(128)
        print("I2C_HBRIDGE_FINAL", unit.get_driver_config(0x00),
              unit.get_driver_config(0x01))
        print("I2C_HBRIDGE_SPEC", unit.get_device_status(0xFE),
              unit.get_device_status(0xFF))
    except Exception as error:
        emit_exception("I2C_HBRIDGE_CONFIG_ERROR", error)
    print("I2C_HBRIDGE_END")
    while True:
        M5.update()
        time.sleep_ms(200)

else:
    raise ValueError("unknown cclass probe case")
