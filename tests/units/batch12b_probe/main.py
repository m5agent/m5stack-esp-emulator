"""Batch-12b guest probes for the seven planned I2C Units with existing models.

No official Unit driver exists for these products (driver-gap), so the probe
uses raw machine.I2C register transactions. The BMM350 branch reads size+2
bytes and drops the first two dummy bytes exactly as Bosch datasheet section
9.2.3 (and the frozen Python driver) requires.
"""
import time
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)
MARKER = "BATCH12B_PROBE_READY"


def print(*parts):
    _console.write(" ".join(str(x) for x in parts) + "\n")


def wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        M5.update()
        time.sleep_ms(10)


def show(screen, text):
    screen.setCursor(6, 42)
    screen.print(str(text))


def u16be(data):
    return (data[0] << 8) | data[1]


def s16be(data):
    value = u16be(data)
    return value - 0x10000 if value & 0x8000 else value


def s24le(data):
    value = data[0] | (data[1] << 8) | (data[2] << 16)
    return value - 0x1000000 if value & 0x800000 else value


def s32le(data):
    value = data[0] | (data[1] << 8) | (data[2] << 16) | (data[3] << 24)
    return value - 0x100000000 if value & 0x80000000 else value


print("BATCH12B_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch12b Unit: " + CASE)

i2c = I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=400000)
try:
    print("BATCH12B_SCAN", i2c.scan())
except Exception as error:
    print("BATCH12B_SCAN_ERROR", repr(error))

if CASE == "bmm350":
    ADDR = 0x14
    print("BMM350_DRIVER machine.I2C raw driver-gap")
    print(MARKER, CASE)
    wait_ms(300)
    try:
        # Datasheet section 9.2.3: n-byte read returns n+2 bytes, first 2 dummy.
        raw = i2c.readfrom_mem(ADDR, 0x00, 3)
        print("BMM350_CHIP_RAW", raw.hex())
        print("BMM350_CHIP_ID", raw[2])
        raw = i2c.readfrom_mem(ADDR, 0x31, 5)
        print("BMM350_X_RAW", s24le(raw[2:5]))
        raw = i2c.readfrom_mem(ADDR, 0x34, 5)
        print("BMM350_Y_RAW", s24le(raw[2:5]))
        raw = i2c.readfrom_mem(ADDR, 0x37, 5)
        print("BMM350_Z_RAW", s24le(raw[2:5]))
        raw = i2c.readfrom_mem(ADDR, 0x3A, 5)
        print("BMM350_TEMP_RAW", s24le(raw[2:5]))
        raw = i2c.readfrom_mem(ADDR, 0x55, 3)
        print("BMM350_OTP_STATUS", raw[2])
        show(screen, "bmm350")
    except Exception as error:
        print("BMM350_ERROR", repr(error))
    wait_ms(300)
    print("BMM350_END")

elif CASE in ("ina226-10a", "ina226-1a"):
    ADDR = 0x41
    print("INA226_DRIVER machine.I2C raw driver-gap")
    print(MARKER, CASE)
    wait_ms(300)
    try:
        manufacturer = u16be(i2c.readfrom_mem(ADDR, 0xFE, 2))
        die = u16be(i2c.readfrom_mem(ADDR, 0xFF, 2))
        print("INA226_MANUFACTURER", manufacturer)
        print("INA226_DIE", die)
        configuration = u16be(i2c.readfrom_mem(ADDR, 0x00, 2))
        calibration = u16be(i2c.readfrom_mem(ADDR, 0x05, 2))
        print("INA226_CONFIG", configuration)
        print("INA226_CAL", calibration)
        print("INA226_SHUNT_RAW", s16be(i2c.readfrom_mem(ADDR, 0x01, 2)))
        print("INA226_BUS_RAW", u16be(i2c.readfrom_mem(ADDR, 0x02, 2)))
        print("INA226_CURRENT_RAW", s16be(i2c.readfrom_mem(ADDR, 0x04, 2)))
        print("INA226_POWER_RAW", s16be(i2c.readfrom_mem(ADDR, 0x03, 2)))
        # Calibration is writable; write the documented default back and read it.
        cal_bytes = bytes([(calibration >> 8) & 0xFF, calibration & 0xFF])
        i2c.writeto_mem(ADDR, 0x05, cal_bytes)
        print("INA226_CAL_RB", u16be(i2c.readfrom_mem(ADDR, 0x05, 2)))
        show(screen, CASE)
    except Exception as error:
        print("INA226_ERROR", repr(error))
    wait_ms(300)
    print("INA226_END")

elif CASE in ("roller485", "roller485-lite", "rollercan", "rollercan-lite"):
    ADDR = 0x64
    print("ROLLER_DRIVER machine.I2C raw driver-gap")
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("ROLLER_PRODUCT_ID", i2c.readfrom_mem(ADDR, 0xF4, 1)[0])
        print("ROLLER_FW", i2c.readfrom_mem(ADDR, 0xFE, 1)[0])
        print("ROLLER_I2C_ADDR", i2c.readfrom_mem(ADDR, 0xFF, 1)[0])
        print("ROLLER_MODE", i2c.readfrom_mem(ADDR, 0x01, 1)[0])
        print("ROLLER_STATE", i2c.readfrom_mem(ADDR, 0x0C, 1)[0])
        print("ROLLER_ERROR", i2c.readfrom_mem(ADDR, 0x0D, 1)[0])
        print("ROLLER_ENCODER", s32le(i2c.readfrom_mem(ADDR, 0x3C, 4)))
        print("ROLLER_VIN_RAW", s32le(i2c.readfrom_mem(ADDR, 0x34, 4)))
        print("ROLLER_TEMP_RAW", s32le(i2c.readfrom_mem(ADDR, 0x38, 4)))
        print("ROLLER_ACTUAL_SPEED_RAW", s32le(i2c.readfrom_mem(ADDR, 0x60, 4)))
        print("ROLLER_ACTUAL_POS_RAW", s32le(i2c.readfrom_mem(ADDR, 0x90, 4)))
        print("ROLLER_CURRENT_RAW", s32le(i2c.readfrom_mem(ADDR, 0xC0, 4)))
        print("ROLLER_TARGET_SPEED_RAW", s32le(i2c.readfrom_mem(ADDR, 0x40, 4)))
        # Write path: speed mode, 1500.00 rpm target, 90.00 deg legacy position.
        i2c.writeto_mem(ADDR, 0x01, bytes([2]))
        i2c.writeto_mem(ADDR, 0x40, (150000).to_bytes(4, "little"))
        i2c.writeto_mem(ADDR, 0x80, (9000).to_bytes(4, "little"))
        i2c.writeto_mem(ADDR, 0xF0, b"\x01")
        print("ROLLER_MODE_RB", i2c.readfrom_mem(ADDR, 0x01, 1)[0])
        print("ROLLER_TARGET_SPEED_RB", s32le(i2c.readfrom_mem(ADDR, 0x40, 4)))
        print("ROLLER_TARGET_POS_RB", s32le(i2c.readfrom_mem(ADDR, 0x80, 4)))
        show(screen, CASE)
    except Exception as error:
        print("ROLLER_ERROR", repr(error))
    wait_ms(300)
    print("ROLLER_END")

else:
    raise ValueError("unknown batch12b case")

while True:
    M5.update()
    time.sleep_ms(200)
