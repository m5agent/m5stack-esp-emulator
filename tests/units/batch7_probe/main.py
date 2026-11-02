"""Guest probes for the eight batch-7 Units with guest/Device Service evidence.

Runs the reference firmware's frozen original UIFlow2 drivers on real
controllers; no host value is placed in a driver return path. The Device
Service captures UART0 markers and QOM state. Fixtures are provided as
session-initial Unit inputs (or unit-input where the probe has a coordination
point). `can` is BLOCKED by the known CAN attachment gap and is not probed.
UART log has no RF/cellular claim: SIM7080G/GNSS/LoRaWAN are byte-layer only.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "BATCH7_PROBE_READY"


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


print("BATCH7_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch7 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "mini-tof-90":
    from unit import ToFUnit

    try:
        unit = ToFUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_TOF_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("I2C_TOF_RANGE", unit.get_range())
        print("I2C_TOF_DATA_READY", int(unit.get_data_ready()))
        # read_range()/continuous mode can block when the model reports no new
        # sample; the single get_range() read is the assertable data plane here.
        show(screen, "mini-tof-90")
    except Exception as error:
        emit_exception("I2C_TOF_ERROR", error)
    print("I2C_TOF_END")

elif CASE == "hbridge-v11":
    from unit import HbridgeUnit

    try:
        unit = HbridgeUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_HBRIDGE_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("I2C_HBRIDGE_ADC", unit.get_adc_value(raw=1, res=16),
              unit.get_adc_value(raw=1, res=8))
        print("I2C_HBRIDGE_CURRENT", unit.get_vin_current())
        unit.set_direction(1)
        unit.set_16bit_pwm(32768)
        unit.set_pwm_freq(1000)
        print("I2C_HBRIDGE_SET")
        print("I2C_HBRIDGE_STATUS", unit.get_device_status(0xfe),
              unit.get_device_status(0xff))
        show(screen, "hbridge-v11")
    except Exception as error:
        emit_exception("I2C_HBRIDGE_ERROR", error)
    print("I2C_HBRIDGE_END")

elif CASE == "cardkb-original":
    from unit import CardKBUnit

    try:
        unit = CardKBUnit(make_bus())
    except Exception as error:
        emit_exception("I2C_CARDKB_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        for _ in range(20):
            key = unit.get_key()
            if key is not None:
                print("I2C_CARDKB_KEY", key)
                break
            wait_ms(200)
        show(screen, "cardkb-original")
    except Exception as error:
        emit_exception("I2C_CARDKB_ERROR", error)
    print("I2C_CARDKB_END")

elif CASE == "env-ii":
    from unit import ENVUnit
    ENV_II = 2

    try:
        unit = ENVUnit(make_bus(), ENV_II)
    except Exception as error:
        emit_exception("I2C_ENV2_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("I2C_ENV2", unit.read_temperature(), unit.read_humidity(),
              unit.read_pressure())
        show(screen, "env-ii")
    except Exception as error:
        emit_exception("I2C_ENV2_ERROR", error)
    print("I2C_ENV2_END")

elif CASE == "hex":
    # Public UIFlow2 has no unit/hex.py; the executable reference path is the
    # generic RGBUnit/SK6812 driver with 37 LEDs (explicit driver-gap).
    from unit import RGBUnit

    try:
        unit = RGBUnit((WHITE, YELLOW), 37)
    except Exception as error:
        emit_exception("GPIO_HEX_INIT_ERROR", error)
        raise
    print("GPIO_HEX_DRIVER generic-SK6812-37")
    print(MARKER, CASE)
    wait_ms(300)
    try:
        unit.fill_color(0x112233)
        print("GPIO_HEX_WRITTEN")
        show(screen, "hex 37")
    except Exception as error:
        emit_exception("GPIO_HEX_WRITE_ERROR", error)
    wait_ms(300)
    print("GPIO_HEX_END")

elif CASE == "catm":
    from unit import CATMUnit

    try:
        unit = CATMUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_CATM_INIT_ERROR", error)
        raise
    print("UART_CATM_READY")
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("UART_CATM_IMEI", unit.get_imei_number())
        show(screen, "catm")
    except Exception as error:
        emit_exception("UART_CATM_ERROR", error)
    print("UART_CATM_END")

elif CASE == "catm-gnss":
    from unit import CATMGNSSUnit

    try:
        unit = CATMGNSSUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_CATMGNSS_INIT_ERROR", error)
        raise
    print("UART_CATMGNSS_READY")
    print(MARKER, CASE)
    wait_ms(400)
    try:
        print("UART_CATMGNSS_POWER", unit.get_check_gnss_power())
        unit.set_gnss_power_ctrl(1)
        print("UART_CATMGNSS_NMEA", unit.gnss_nmea_output_polling())
        show(screen, "catm-gnss")
    except Exception as error:
        emit_exception("UART_CATMGNSS_ERROR", error)
    print("UART_CATMGNSS_END")

elif CASE == "lorawan-cn470":
    # The frozen ASR650x ctor creates machine.UART(1, tx=..., rx=...) without a
    # baud argument and relies on a later init(). The QEMU UART TX matrix
    # capture only observes writes after a baud-configured UART instance exists,
    # so pre-configure the same pins/baud once as a documented guest-side
    # model-ordering workaround (still the official driver below).
    from machine import UART as MUART
    _uart_bootstrap = MUART(1, tx=YELLOW, rx=WHITE, baudrate=115200)

    from unit import LoRaWANUnit

    try:
        # The frozen ASR650x constructor sends AT+CWORKMODE=2 and expects OK.
        unit = LoRaWANUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UART_LORAWAN_INIT_ERROR", error)
        raise
    print("UART_LORAWAN_READY")
    print(MARKER, CASE)
    wait_ms(400)
    try:
        # Byte-layer only: the fixture responder intentionally does not model
        # LoRaWAN AT response parsing, so avoid get_work_mode/get_device_address
        # decoding. set_work_mode + send_data exercise the official driver's
        # CWORKMODE and DTRX byte frames.
        unit.set_work_mode(1)
        print("UART_LORAWAN_WORKMODE_SENT")
        unit.send_data("HELLO")
        print("UART_LORAWAN_SENT")
        show(screen, "lorawan-cn470")
    except Exception as error:
        emit_exception("UART_LORAWAN_ERROR", error)
    print("UART_LORAWAN_END")

else:
    raise ValueError("unknown batch7 probe case")

while True:
    M5.update()
    time.sleep_ms(200)
