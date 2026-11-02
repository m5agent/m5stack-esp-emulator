"""Guest probes for the twelve Units of the eighth research batch.

Runs the reference firmware's frozen original UIFlow2 drivers on real SoC
controllers; no host value is placed in a driver return path. Fixtures are
session-initial Unit inputs (UART responders / NMEA lines / ADC comparator).
Known boundaries are recorded honestly instead of faked: mini-can has no CAN
Unit attachment lane in the Unit runtime, and MIC has no public Unit driver so
the probe uses machine.ADC/machine.Pin directly (explicit driver gap).
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "BATCH8_PROBE_READY"


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


print("BATCH8_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch8 Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "pahub-v21":
    from unit import PAHUBUnit

    try:
        i2c = make_bus()
        hub = PAHUBUnit(i2c, address=0x70, channel=0)
    except Exception as error:
        emit_exception("PAHUB_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("PAHUB_READ0", i2c.readfrom(0x70, 1)[0])
        hub.select_channel(3)
        print("PAHUB_SEL3", i2c.readfrom(0x70, 1)[0])
        hub.select_channel(5)
        print("PAHUB_SEL5", i2c.readfrom(0x70, 1)[0])
        hub.release_channel(3)
        print("PAHUB_REL3", i2c.readfrom(0x70, 1)[0])
        show(screen, "pahub-v21")
    except Exception as error:
        emit_exception("PAHUB_ERROR", error)
    print("PAHUB_END")

elif CASE in ("gps-v11", "gps-sma"):
    from unit import GPSUnit

    try:
        unit = GPSUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("GPS_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(1500)
    try:
        print("GPS_TIME", unit.gps_time)
        print("GPS_DATE", unit.gps_date)
        print("GPS_LAT", unit.latitude, unit.latitude_decimal)
        print("GPS_LON", unit.longitude, unit.longitude_decimal)
        print("GPS_SAT", unit.satellite_num)
        print("GPS_ALT", unit.altitude)
        print("GPS_SPEED", unit.speed_kph, unit.course)
        # The frozen driver hard-codes 9600; the product page says 115200. The
        # guest cannot expose the configured baud, so both facts are recorded.
        print("GPS_BAUD_CAVEAT driver-9600-page-115200-unresolved")
        show(screen, CASE)
    except Exception as error:
        emit_exception("GPS_ERROR", error)
    print("GPS_END")

elif CASE == "lcd":
    from unit import LCDUnit

    display = None
    i2c = make_bus()
    try:
        print("LCD_SCAN", i2c.scan())
    except Exception as error:
        emit_exception("LCD_SCAN_ERROR", error)
    try:
        unit = LCDUnit(i2c=i2c, address=0x3D)
        display = getattr(unit, "display", unit)
        print("LCD_ADDR_EXPLICIT 0x3D")
    except Exception as error:
        emit_exception("LCD_INIT_ERROR", error)
        try:
            direct = M5.addDisplay(i2c, 0x3D, {"unit_lcd": True})
            print("LCD_DIRECT", "none" if direct is None else "display")
        except Exception as direct_error:
            emit_exception("LCD_DIRECT_ERROR", direct_error)
    print(MARKER, CASE)
    wait_ms(400)
    if display is not None:
        try:
            display.fillScreen(0x1234)
            print("LCD_FILL_SCREEN")
            display.fillRect(10, 20, 30, 40, 0x5678)
            print("LCD_FILL_RECT")
            wait_ms(400)
            show(screen, "lcd")
        except Exception as error:
            emit_exception("LCD_ERROR", error)
    print("LCD_END")

elif CASE in ("oled", "mini-oled", "glass2"):
    classes = {"oled": "OLEDUnit", "mini-oled": "MiniOLEDUnit", "glass2": "Glass2Unit"}
    module = __import__("unit")
    cls = getattr(module, classes[CASE])
    display = None
    i2c = make_bus()
    try:
        print("DISP_SCAN", i2c.scan())
    except Exception as error:
        emit_exception("DISP_SCAN_ERROR", error)
    try:
        # The frozen reference-firmware oled/minioled driver defaults to 0x3C
        # while the batch8 model follows the public driver address 0x3D, so the
        # explicit address is used for those two. Glass2's frozen default 0x3C
        # already matches its model address.
        if CASE == "glass2":
            unit = cls(i2c=i2c)
            print("DISP_ADDR_DEFAULT 0x3C")
        else:
            unit = cls(i2c=i2c, address=0x3D)
            print("DISP_ADDR_EXPLICIT 0x3D")
        display = getattr(unit, "display", unit)
    except Exception as error:
        emit_exception("DISP_INIT_ERROR", error)
        # The frozen reference-firmware driver defaults to 0x3C, while the
        # batch8 model follows the public driver default 0x3D; record a direct
        # composition call at the model address as separate evidence.
        try:
            direct = M5.addDisplay(i2c, 0x3D, {"unit_" + CASE.replace("-", "_"): True})
            print("DISP_DIRECT", "none" if direct is None else "display")
        except Exception as direct_error:
            emit_exception("DISP_DIRECT_ERROR", direct_error)
    print(MARKER, CASE)
    wait_ms(400)
    if display is not None:
        try:
            display.fillScreen(0x00)
            print("DISP_CLEAR")
            display.fillRect(4, 6, 32, 16, 0x01)
            print("DISP_RECT")
            wait_ms(400)
            show(screen, CASE)
        except Exception as error:
            emit_exception("DISP_ERROR", error)
    print("DISP_END")

elif CASE == "nbiot-cn":
    from unit import NBIOTUnit

    try:
        unit = NBIOTUnit(1, (WHITE, YELLOW))
        print("NBIOT_READY")
    except Exception as error:
        emit_exception("NBIOT_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    try:
        print("NBIOT_IMEI", unit.get_imei_number())
    except Exception as error:
        emit_exception("NBIOT_IMEI_ERROR", error)
    print("NBIOT_END")

elif CASE == "lora-e220-920":
    from unit import LoRaE220JPUnit

    try:
        unit = LoRaE220JPUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("LR920_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        ok = unit.setup(own_address=0x1234, own_channel=5, encryption_key=0xABCD)
        print("LR920_SETUP", int(bool(ok)))
        unit.send(0x4321, 7, b"HELLO")
        print("LR920_SENT")
        show(screen, "lora-e220-920")
    except Exception as error:
        emit_exception("LR920_ERROR", error)
    print("LR920_END")

elif CASE == "lorawan-us915":
    from unit import LoRaWANUnit

    try:
        unit = LoRaWANUnit(1, (WHITE, YELLOW))
        print("LW915_READY")
    except Exception as error:
        emit_exception("LW915_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(500)
    for label, method in (("LW915_DEVADDR", "get_DevAddr"),
                          ("LW915_DEVEUI", "get_DevEui"),
                          ("LW915_APPEUI", "get_AppEui")):
        try:
            print(label, getattr(unit, method)())
        except Exception as error:
            emit_exception(label + "_ERROR", error)
    print("LW915_END")

elif CASE == "mini-can":
    try:
        from unit import CANUnit

        unit = CANUnit(1, (WHITE, YELLOW))
    except Exception as error:
        # CAN frames need the m5can/TWAI attachment lane, which the Unit
        # runtime does not provide; record the exact guest-side failure.
        emit_exception("CAN_INIT_ERROR", error)
        print("CAN_END")
    else:
        print(MARKER, CASE)
        wait_ms(300)
        try:
            unit.send_data(0x123, b"\x01\x02\x03\x04\x05\x06\x07\x08")
            print("CAN_SENT")
        except Exception as error:
            emit_exception("CAN_SEND_ERROR", error)
        print("CAN_END")

elif CASE == "mic":
    from machine import ADC, Pin

    try:
        adc = ADC(Pin(WHITE))
        comparator = Pin(YELLOW, Pin.IN)
    except Exception as error:
        emit_exception("MIC_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("MIC_ADC_RAW", adc.read_u16())
    except Exception as error:
        emit_exception("MIC_ADC_ERROR", error)
    try:
        print("MIC_ADC_UV", adc.read_uv())
    except Exception as error:
        emit_exception("MIC_ADC_UV_ERROR", error)
    try:
        print("MIC_LEVEL", comparator.value())
        show(screen, "mic")
    except Exception as error:
        emit_exception("MIC_ERROR", error)
    print("MIC_END")

else:
    raise ValueError("unknown batch8 probe case")

while True:
    M5.update()
    time.sleep_ms(200)
