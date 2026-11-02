"""Guest probes for the twelve Units of the fifth research batch.

Runs the reference UIFlow2 firmware's frozen original drivers on real
controllers; no host value is written into a driver return path. The Device
Service captures UART0 markers and QOM state; external fixtures are provided
as session-initial unit inputs (or injected through unit-input where the probe
has a coordination point). Known model/driver boundaries are reported as
markers instead of hidden.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "BATCH5_PROBE_READY"


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


print("BATCH5_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch5 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "pbhub-v11":
    from unit import PBHUBUnit

    try:
        unit = PBHUBUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_PBHUB_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("I2C_PBHUB_FW", unit.read_status(0xFE))
        print("I2C_PBHUB_READ", int(unit.digital_read(0, 0)),
              int(unit.digital_read(0, 1)), int(unit.analog_read(0)))
        unit.digital_write(0, 0, 1)
        unit.pwm_write(0, 0, 50)
        unit.set_rgb_led_num(0, 1)
        unit.set_rgb_color(0, 0, 1, 0xFF0000)
        unit.set_rgb_brightness(0, 100)
        print("I2C_PBHUB_WRITTEN")
        show(screen, "pbhub v11")
    except Exception as error:
        emit_exception("I2C_PBHUB_ERROR", error)
    print("I2C_PBHUB_END")

elif CASE == "op90":
    from unit import OPUnit

    try:
        unit = OPUnit((WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPIO_OP90_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    for _ in range(10):
        try:
            level = int(unit.pin.value())
            print("GPIO_OP90", level)
            show(screen, "op90=%d" % level)
        except Exception as error:
            emit_exception("GPIO_OP90_ERROR", error)
        wait_ms(200)
    print("GPIO_OP90_END")

elif CASE == "rgb-led-10cm":
    from unit import RGBUnit

    try:
        unit = RGBUnit((WHITE, YELLOW), 15)
    except Exception as error:
        emit_exception("GPIO_RGB15_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.fill_color(0x112233)
        print("GPIO_RGB15_WRITTEN")
        show(screen, "rgb15")
    except Exception as error:
        emit_exception("GPIO_RGB15_WRITE_ERROR", error)
    wait_ms(300)
    print("GPIO_RGB15_END")

elif CASE == "neohex":
    # The public UIFlow2 source has no unit/neohex.py; the generic NeoPixel
    # driver is the only executable reference path (explicit driver gap).
    from driver.neopixel.ws2812 import WS2812

    try:
        unit = WS2812(YELLOW, 37)
    except Exception as error:
        emit_exception("GPIO_NEOHEX_INIT_ERROR", error)
        raise
    print("GPIO_NEOHEX_DRIVER ws2812")
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.fill_color(0x445566)
        print("GPIO_NEOHEX_WRITTEN")
        show(screen, "neohex")
    except Exception as error:
        emit_exception("GPIO_NEOHEX_WRITE_ERROR", error)
    wait_ms(300)
    print("GPIO_NEOHEX_END")

elif CASE == "8angle":
    from unit import Angle8Unit

    try:
        unit = Angle8Unit(make_bus())
    except Exception as error:
        emit_exception("I2C_ANGLE8_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        # Angle8Unit channels are 1..8 (the driver subtracts 1 before indexing).
        print("I2C_ANGLE8_ADC12", unit.get_adc12_raw(1), unit.get_adc12_raw(8))
        print("I2C_ANGLE8_ADC8", unit.get_adc8_raw(1), unit.get_adc8_raw(8))
        print("I2C_ANGLE8_SWITCH", int(unit.get_switch_status()))
        # Angle8Unit.set_led_rgb(channel) subtracts 1, so valid channels are 1..9.
        unit.set_led_rgb(1, 0x112233, 50)
        unit.set_led_rgb(2, 0x445566, 80)
        print("I2C_ANGLE8_RGB")
        show(screen, "8angle")
    except Exception as error:
        emit_exception("I2C_ANGLE8_ERROR", error)
    print("I2C_ANGLE8_END")

elif CASE == "kmeter-iso-v11":
    from unit import KMeterISOUnit

    try:
        unit = KMeterISOUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_KMETER_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        print("I2C_KMETER", unit.get_thermocouple_temperature(),
              unit.get_internal_temperature())
        print("I2C_KMETER_READY", int(unit.is_ready()))
        print("I2C_KMETER_FW", unit.get_device_info(0xFE))
        show(screen, "kmeter")
    except Exception as error:
        emit_exception("I2C_KMETER_ERROR", error)
    print("I2C_KMETER_END")

elif CASE == "pahub-v20":
    from unit import PAHUBUnit

    try:
        unit = PAHUBUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_PAHUB_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        for channel in (0, 3, 5):
            unit.select_channel(channel)
            print("I2C_PAHUB_SELECT", channel)
            wait_ms(1200)
        unit.release_channel(3)
        print("I2C_PAHUB_RELEASE", 3)
        wait_ms(1200)
        unit.release_channel(0)
        unit.release_channel(5)
        print("I2C_PAHUB_RELEASED")
        wait_ms(600)
        show(screen, "pahub")
    except Exception as error:
        emit_exception("I2C_PAHUB_ERROR", error)
    print("I2C_PAHUB_END")

elif CASE == "rtc":
    from unit import RTC8563Unit

    def fields(unit):
        return [unit.get_date_time(select) for select in (6, 5, 4, 2, 1, 0)]

    try:
        unit = RTC8563Unit(make_bus())
    except Exception as error:
        emit_exception("I2C_RTC_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("RTC_T1", *fields(unit))
        wait_ms(1200)
        print("RTC_T2", *fields(unit))
        print("RTC_PHASE1")
        # The runner switches running=false at RTC_PHASE1 so guest writes land
        # in the BCD registers instead of being overwritten by the virtual clock.
        wait_ms(1500)
        unit.set_date_time(seconds=0, minutes=0, hours=12, day=0,
                           date=2, month=3, year=26)
        wait_ms(300)
        print("RTC_WRITTEN", *fields(unit))
        show(screen, "rtc")
    except Exception as error:
        emit_exception("I2C_RTC_ERROR", error)
    print("I2C_RTC_END")

elif CASE == "tmos-pir":
    from unit import TMOSUnit

    try:
        unit = TMOSUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_TMOS_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        unit.refresh_state()
        print("I2C_TMOS_STATE", int(unit.get_presence_state()),
              int(unit.get_motion_state()), int(unit.get_tamb_shock_state()))
        print("I2C_TMOS_RAW", unit.get_tobject_raw_value(),
              unit.get_tambient_raw_value(), unit.get_presence_value(),
              unit.get_motion_value())
        print("I2C_TMOS_TEMP", unit.get_temperature_data())
        print("I2C_TMOS_ODR", unit.get_tmos_odr(), unit.get_gain_mode())
        show(screen, "tmos")
    except Exception as error:
        emit_exception("I2C_TMOS_ERROR", error)
    print("I2C_TMOS_END")

elif CASE == "lora-e220-433":
    from unit import LoRaE220433Unit

    try:
        unit = LoRaE220433Unit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_LORA_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(600)
    try:
        ok = unit.setup(own_address=0x1234, own_channel=5, encryption_key=0xABCD)
        print("UART_LORA_SETUP", int(bool(ok)))
        config = unit.read_command_format()
        print("UART_LORA_CONFIG", config)
        unit.send(0x4321, 7, b"HELLO")
        print("UART_LORA_SENT")
        wait_ms(300)
        print("UART_LORA_AVAILABLE", unit.available_data())
        show(screen, "lora")
    except Exception as error:
        emit_exception("UART_LORA_ERROR", error)
    print("UART_LORA_END")

elif CASE == "zigbee":
    from unit import ZigbeeUnit

    try:
        unit = ZigbeeUnit(1, (WHITE, YELLOW), verbose=False)
    except Exception as error:
        emit_exception("UART_ZIGBEE_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(600)
    try:
        unit.p2p_transmission(0x1234, b"HELLO")
        print("UART_ZIGBEE_SENT")
        wait_ms(500)
        data = unit._uart.read()
        print("UART_ZIGBEE_RX", "" if data is None else bytes(data).hex())
        show(screen, "zigbee")
    except Exception as error:
        emit_exception("UART_ZIGBEE_ERROR", error)
    print("UART_ZIGBEE_END")

elif CASE == "nbiot2":
    from unit import NBIOT2Unit

    try:
        # The constructor performs three AT readiness probes and ATE0; the
        # session-initial responses-hex fixtures answer each command.
        unit = NBIOT2Unit(1, (WHITE, YELLOW))
        print("UART_NBIOT_READY")
    except Exception as error:
        emit_exception("UART_NBIOT_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    print("UART_NBIOT_END")

else:
    raise ValueError("unknown batch5 probe case")

while True:
    M5.update()
    time.sleep_ms(200)
