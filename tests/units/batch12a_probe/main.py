"""Raw machine.I2C guest probes for the seven driver-gap batch-12a Units.

No official Unit driver exists for these products, so the probe talks to the
Unit register file directly over the SoC I2C controller (the same evidence
category as the earlier raw-byte responder probes). Only register/byte-level
behavior is asserted; mechanical/electrical/optical/physics semantics are NOT
modeled or claimed.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)
MARKER = "BATCH12A_PROBE_READY"


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


def wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        M5.update()
        time.sleep_ms(10)


print("BATCH12A_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch12a Unit: " + CASE)


def make_bus(freq=100000):
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=freq)


if CASE in ("byteswitch", "bytebutton"):
    addr = 0x46 if CASE == "byteswitch" else 0x47
    i2c = make_bus()
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("BU_SCAN", i2c.scan())
        print("BU_BITMAP", i2c.readfrom_mem(addr, 0x00, 1)[0])
        print("BU_CH0", i2c.readfrom_mem(addr, 0x60, 1)[0])
        print("BU_CH7", i2c.readfrom_mem(addr, 0x67, 1)[0])
        print("BU_FW", i2c.readfrom_mem(addr, 0xFE, 1)[0])
        i2c.writeto_mem(addr, 0x11, bytes([0x42]))
        i2c.writeto_mem(addr, 0x19, bytes([1]))
        i2c.writeto_mem(addr, 0x20, bytes([0x11, 0x22, 0x33]))
        i2c.writeto_mem(addr, 0xF0, bytes([1]))
        i2c.writeto_mem(addr, 0xF1, bytes([1]))
        wait_ms(200)
        print("BU_BRIGHTNESS_READBACK", i2c.readfrom_mem(addr, 0x11, 1)[0])
        print("BU_MODE_READBACK", i2c.readfrom_mem(addr, 0x19, 1)[0])
        print("BU_RGB_READBACK", i2c.readfrom_mem(addr, 0x20, 3).hex())
        print("BU_IRQ_READBACK", i2c.readfrom_mem(addr, 0xF1, 1)[0])
        show(screen, CASE)
    except Exception as error:
        emit_exception("BU_ERROR", error)
    print("BU_END")

elif CASE == "step16":
    addr = 0x48
    i2c = make_bus()
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("ST_SCAN", i2c.scan())
        print("ST_POSITION", i2c.readfrom_mem(addr, 0x00, 1)[0])
        print("ST_LED_DEFAULT", i2c.readfrom_mem(addr, 0x10, 1)[0],
              i2c.readfrom_mem(addr, 0x20, 1)[0])
        i2c.writeto_mem(addr, 0x30, bytes([0]))
        i2c.writeto_mem(addr, 0x20, bytes([42]))
        i2c.writeto_mem(addr, 0x50, bytes([0x12, 0x34, 0x56]))
        i2c.writeto_mem(addr, 0xF0, bytes([2]))
        wait_ms(200)
        print("ST_DIRECTION_READBACK", i2c.readfrom_mem(addr, 0x30, 1)[0])
        print("ST_BRIGHTNESS_READBACK", i2c.readfrom_mem(addr, 0x20, 1)[0])
        print("ST_RGB_READBACK", i2c.readfrom_mem(addr, 0x50, 3).hex())
        print("ST_FW", i2c.readfrom_mem(addr, 0xFE, 1)[0])
        show(screen, "step16")
    except Exception as error:
        emit_exception("ST_ERROR", error)
    print("ST_END")

elif CASE == "timerpwr":
    addr = 0x56
    i2c = make_bus()
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("TP_SCAN", i2c.scan())
        print("TP_BUTTONS", i2c.readfrom_mem(addr, 0x10, 2).hex())
        print("TP_BATTERY_RAW", i2c.readfrom_mem(addr, 0x70, 4).hex())
        print("TP_BATTERY_I_RAW", i2c.readfrom_mem(addr, 0x74, 4).hex())
        print("TP_USB_V_RAW", i2c.readfrom_mem(addr, 0x60, 4).hex())
        print("TP_CHARGING", i2c.readfrom_mem(addr, 0x90, 1)[0])
        i2c.writeto_mem(addr, 0x00, bytes([1]))
        i2c.writeto_mem(addr, 0x01, bytes([0]))
        i2c.writeto_mem(addr, 0x30, bytes([12, 34, 0]))
        i2c.writeto_mem(addr, 0x41, bytes([1]))
        wait_ms(200)
        print("TP_GROVE_OUT_READBACK", i2c.readfrom_mem(addr, 0x00, 1)[0])
        print("TP_BACKLIGHT_READBACK", i2c.readfrom_mem(addr, 0x01, 1)[0])
        print("TP_SCHEDULE_READBACK", i2c.readfrom_mem(addr, 0x30, 3).hex())
        show(screen, "timerpwr")
    except Exception as error:
        emit_exception("TP_ERROR", error)
    print("TP_END")

elif CASE == "mq":
    addr = 0x11
    i2c = make_bus()
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("MQ_SCAN", i2c.scan())
        print("MQ_VALID", i2c.readfrom_mem(addr, 0x40, 1)[0])
        print("MQ_ADC8", i2c.readfrom_mem(addr, 0x20, 1)[0])
        print("MQ_ADC12_RAW", i2c.readfrom_mem(addr, 0x30, 2).hex())
        print("MQ_NTC_OHM_RAW", i2c.readfrom_mem(addr, 0x70, 2).hex())
        print("MQ_REF_RAW", i2c.readfrom_mem(addr, 0x80, 2).hex())
        i2c.writeto_mem(addr, 0x00, bytes([1]))
        i2c.writeto_mem(addr, 0x01, bytes([1]))
        i2c.writeto_mem(addr, 0x10, bytes([60]))
        wait_ms(200)
        print("MQ_MODE_READBACK", i2c.readfrom_mem(addr, 0x00, 1)[0])
        print("MQ_LED_READBACK", i2c.readfrom_mem(addr, 0x01, 1)[0])
        print("MQ_HEAT_READBACK", i2c.readfrom_mem(addr, 0x10, 1)[0])
        print("MQ_FW", i2c.readfrom_mem(addr, 0xFE, 1)[0])
        show(screen, "mq")
    except Exception as error:
        emit_exception("MQ_ERROR", error)
    print("MQ_END")

elif CASE == "8servos2-i2c":
    addr = 0x28  # rotary fixture 3 -> 0x25 + 3
    i2c = make_bus()
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("SV_SCAN", i2c.scan())
        print("SV_MODES", i2c.readfrom_mem(addr, 0x00, 8).hex())
        print("SV_UID", i2c.readfrom_mem(addr, 0xE0, 12).hex())
        print("SV_FW", i2c.readfrom_mem(addr, 0xFE, 1)[0])
        i2c.writeto_mem(addr, 0x00, bytes([2]))
        i2c.writeto_mem(addr, 0x50, bytes([10, 11, 12, 13, 14, 15, 16, 17]))
        i2c.writeto_mem(addr, 0x70, bytes([50, 51, 52, 53, 54, 55, 56, 57]))
        i2c.writeto_mem(addr, 0x80, bytes([1, 2, 3, 4]))
        wait_ms(200)
        print("SV_MODE_READBACK", i2c.readfrom_mem(addr, 0x00, 1)[0])
        print("SV_SERVO_READBACK", i2c.readfrom_mem(addr, 0x50, 8).hex())
        print("SV_PWM_READBACK", i2c.readfrom_mem(addr, 0x70, 8).hex())
        print("SV_RGB_READBACK", i2c.readfrom_mem(addr, 0x80, 4).hex())
        show(screen, "8servos2")
    except Exception as error:
        emit_exception("SV_ERROR", error)
    print("SV_END")

elif CASE == "cardkb2":
    addr = 0x5F
    i2c = make_bus()
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("CK_SCAN", i2c.scan())
        print("CK_KEY", hex(i2c.readfrom(addr, 1)[0]))
        i2c.writeto(addr, bytes([0xF1]))
        wait_ms(50)
        print("CK_FW", i2c.readfrom(addr, 1)[0])
        print("CK_FW_REG", i2c.readfrom_mem(addr, 0xFE, 1)[0])
        show(screen, "cardkb2")
    except Exception as error:
        emit_exception("CK_ERROR", error)
    print("CK_END")

else:
    raise ValueError("unknown batch12a probe case")

while True:
    M5.update()
    time.sleep_ms(200)
