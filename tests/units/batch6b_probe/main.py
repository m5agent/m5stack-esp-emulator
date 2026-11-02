"""Guest probes for the second half of the sixth research batch.

Runs the reference firmware's frozen original UIFlow2 drivers on real
controllers; no host value is placed in a driver return path. Fixtures are
session-initial Unit inputs. unit-id is expected to be BLOCKED: the ATECC
driver wakes the chip by writing to I2C address 0x00, which a slave model bound
to 0x35 cannot receive; the probe records the failure honestly. dmx is expected
to be BLOCKED when the cdriver.esp_dmx C module cannot be imported/executed.
"""

import time
import sys
import M5
from hardware import UART
from machine import I2C, Pin
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "BATCH6B_PROBE_READY"


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


print("BATCH6B_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Batch6B Unit: " + CASE)


def make_bus():
    return I2C(0, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)


if CASE == "unit-id":
    from unit import IDUnit

    try:
        unit = IDUnit(make_bus())
    except Exception as error:
        emit_exception("ID_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    # The ATECC driver wakes the chip with a write to I2C address 0x00. A slave
    # model bound to 0x35 cannot answer that; record the exact failure instead
    # of faking a revision/serial value.
    try:
        print("ID_REVISION", unit.get_revision_number())
    except Exception as error:
        emit_exception("ID_REVISION_ERROR", error)
    try:
        print("ID_SERIAL", unit.get_serial_number())
    except Exception as error:
        emit_exception("ID_SERIAL_ERROR", error)
    try:
        print("ID_RANDOM", unit.randint(0, 100))
    except Exception as error:
        emit_exception("ID_RANDOM_ERROR", error)
    show(screen, "unit-id")
    print("ID_END")

elif CASE == "thermal2":
    from unit import Thermal2Unit

    try:
        unit = Thermal2Unit(make_bus())
    except Exception as error:
        emit_exception("T2_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        print("T2_DETAIL", unit.get_device_detail(0), unit.get_device_detail(1))
        print("T2_ADDR", unit.get_i2c_addr(0))
        print("T2_ALARM", unit.get_temp_alarm_status)
        print("T2_BUTTON", int(unit.get_button_state(0x1F)))
        print("T2_MEASURE", unit.get_temp_measure(0), unit.get_temp_measure(1),
              unit.get_temp_measure(2))
        print("T2_DIFF_POS", unit.get_temp_differential(0, 0),
              unit.get_temp_differential(1, 0))
        buffer = unit.get_temp_data_buffer
        print("T2_BUFFER_LEN", len(buffer))
        print("T2_BUFFER_HEAD", buffer[0], buffer[1], buffer[32], buffer[383])
        show(screen, "thermal2")
    except Exception as error:
        emit_exception("T2_ERROR", error)
    print("T2_END")

elif CASE == "qrcode":
    from unit import QRCodeUnit

    try:
        unit = QRCodeUnit(i2c=make_bus())
    except Exception as error:
        emit_exception("QR_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("QR_STATUS", unit.get_qrcode_data_status())
        print("QR_LEN", unit.get_qrcode_data_length())
        print("QR_DATA", unit.get_qrcode_data(decode=True))
        print("QR_MODE", unit.get_trigger_mode())
        print("QR_BUTTON", int(unit.get_trigger_button_status()))
        print("QR_FW", unit.get_device_info())
        unit.clear_qrcode_data_status()
        print("QR_CLEARED", unit.get_qrcode_data_status())
        show(screen, "qrcode")
    except Exception as error:
        emit_exception("QR_ERROR", error)
    print("QR_END")

elif CASE == "uwb":
    from unit import UWBUnit

    try:
        unit = UWBUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("UWB_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(400)
    try:
        print("UWB_CONTINUOUS", int(unit.continuous_op))
        print("UWB_DISTANCE", unit.get_distance_measure)
        show(screen, "uwb")
    except Exception as error:
        emit_exception("UWB_ERROR", error)
    print("UWB_END")

elif CASE == "dmx":
    try:
        from unit import DMX512Unit

        unit = DMX512Unit(1, (WHITE, YELLOW))
    except Exception as error:
        # The driver delegates to cdriver.esp_dmx; if that C module is missing or
        # cannot run in the reference firmware we record the exact failure.
        emit_exception("DMX_INIT_ERROR", error)
        print("DMX_END")
    else:
        print(MARKER, CASE)
        wait_ms(300)
        try:
            unit.write_data(1, 255)
            print("DMX_WRITE", 1, 255)
            show(screen, "dmx")
        except Exception as error:
            emit_exception("DMX_WRITE_ERROR", error)
        print("DMX_END")

elif CASE == "finger":
    from unit import FingerUnit

    try:
        unit = FingerUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("FINGER_INIT_ERROR", error)
        raise
    print(MARKER, CASE)
    wait_ms(300)
    try:
        print("FINGER_VERSION", unit.get_version())
        print("FINGER_USER_COUNT", unit.get_user_count())
        print("FINGER_USER_CAPACITY", unit.get_user_capacity())
        show(screen, "finger")
    except Exception as error:
        emit_exception("FINGER_ERROR", error)
    print("FINGER_END")

else:
    raise ValueError("unknown batch6b probe case")

while True:
    M5.update()
    time.sleep_ms(200)
