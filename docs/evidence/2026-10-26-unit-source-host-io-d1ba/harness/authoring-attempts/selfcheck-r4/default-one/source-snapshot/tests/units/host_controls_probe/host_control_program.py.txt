import time
import io
import sys
from hardware import UART
import M5
from machine import I2C, Pin
from probe_config import (
    CASE, DEVICE_ID, WHITE, YELLOW, ROTATION, CANVAS_WIDTH, CANVAS_HEIGHT,
    INTERNAL_SDA, INTERNAL_SCL, INTERNAL_CONTROLLER, EXTERNAL_CONTROLLER, EXPECTED_ADDRESS,
)
from probe_logging import emit, console as log_uart
from host_control_layout import FONT_NAME, DISPLAY_PROFILES, value_lines, checked_layout, print_checked

internal = None
internal_reads = 0
last_internal_log = 0


def check_internal(phase):
    global internal_reads, last_internal_log
    identity = internal.readfrom_mem(0x68, 0x00, 1)[0]
    internal_reads += 1
    if identity != 0x24:
        raise RuntimeError("onboard BMI270 identity disappeared or leaked between buses")
    now = time.ticks_ms()
    if phase != "after_op" or time.ticks_diff(now, last_internal_log) >= 1500:
        emit("HOST_CONTROL_INTERNAL", phase, identity, internal_reads)
        last_internal_log = now


def run():
    global internal
    emit("HOST_CONTROL_START", DEVICE_ID, CASE)
    M5.begin()
    screen = M5.Display
    screen.setRotation(ROTATION)
    screen.setBrightness(255)
    screen.fillScreen(0xFFFFFF)
    screen.setTextColor(0x0282CB, 0xFFFFFF)
    emit("HOST_CONTROL_DEFAULT_FONT_HEIGHT", screen.fontHeight())
    profile = DISPLAY_PROFILES[DEVICE_ID]
    screen.setFont(screen.FONTS.Montserrat12)
    screen.setTextSize(profile["text_size"])
    layout = checked_layout(DEVICE_ID, CASE, screen.fontHeight(), screen.textWidth)
    emit("HOST_CONTROL_FONT", FONT_NAME, profile["text_size"], layout["font_height"])
    emit("HOST_CONTROL_LAYOUT", layout["x"], layout["y"], layout["width"], layout["body_y"],
         layout["line_height"], layout["body_rows"], layout["bottom"], len(layout["headers"]))
    emit("HOST_CONTROL_GEOMETRY", screen.width(), screen.height(), ROTATION)
    emit("HOST_CONTROL_BOARD", M5.getBoard())
    if (screen.width(), screen.height()) != (CANVAS_WIDTH, CANVAS_HEIGHT):
        raise RuntimeError("host canvas geometry differs from the explicit profile")
    for row, text in enumerate(layout["headers"]):
        print_checked(screen, layout, text, layout["y"] + row * layout["line_height"])
    internal = I2C(INTERNAL_CONTROLLER, scl=Pin(INTERNAL_SCL), sda=Pin(INTERNAL_SDA), freq=100000)
    check_internal("before")
    bus = I2C(EXTERNAL_CONTROLLER, scl=Pin(WHITE), sda=Pin(YELLOW), freq=100000)
    addresses = sorted(bus.scan())
    emit("CONTROL_I2C_SCAN", [hex(value) for value in addresses])
    emit("HOST_CONTROL_EXTERNAL_SCAN", *addresses)
    if addresses != [EXPECTED_ADDRESS]:
        raise RuntimeError("external controller must expose only the selected control Unit")

    if CASE == "joystick-v11":
        from control_drivers.joystick import JoystickUnit
        unit = JoystickUnit(bus)
    elif CASE == "encoder":
        from control_drivers.encoder import EncoderUnit
        unit = EncoderUnit(bus)
        unit.set_color(0, 0)
        unit.set_color(1, 0x112233)
        unit.set_color(2, 0x445566)
    elif CASE == "8encoder":
        from control_drivers.encoder8 import Encoder8Unit
        unit = Encoder8Unit(bus)
        unit.set_counter_value(2, -1234567)
        written = unit.get_counter_value(2)
        unit.reset_counter_value(2)
        reset = unit.get_counter_value(2)
        emit("CONTROL_ENCODER8_REGISTER_WRITE", written, reset)
        for channel in range(1, 9):
            unit.set_led_rgb(channel, channel * 0x010203)
        # The current official helper clamps its LED argument to eight even though
        # nine physical LEDs/register triplets exist. Exercise triplet nine directly.
        bus.writeto_mem(0x41, 0x88, bytes([0x19, 0x29, 0x39]))
        unit.set_i2c_address(0x42)
        emit("CONTROL_ENCODER8_ADDRESS", unit.get_device_status(0xFF))
    elif CASE == "cardkb":
        from control_drivers.cardkb import CardKBI2C
        unit = CardKBI2C(bus)
        emit("CONTROL_CARDKB_LEGACY", int(not unit._v2_report_mode))
    elif CASE == "rfid2":
        from control_drivers.mfrc522 import MFRC522
        unit = MFRC522(bus, 0x28)
        unit.pcd_init()
        crc = bytearray(2)
        crc_status = unit.pcd_calculate_crc(b"123456789", crc)
        emit("CONTROL_RFID_CRC_VECTOR", int(crc_status == unit.STATUS_OK), crc.hex())
    else:
        raise ValueError("unknown control Unit")

    check_internal("after_init")
    expected_after = 0x42 if CASE == "8encoder" else EXPECTED_ADDRESS
    addresses = sorted(bus.scan())
    emit("HOST_CONTROL_EXTERNAL_AFTER_INIT", *addresses)
    if addresses != [expected_after]:
        raise RuntimeError("external address changed unexpectedly or onboard bus leaked")
    emit("CONTROL_PROBE_READY", CASE)
    previous = None
    last_uid = None
    last_at = time.ticks_ms()
    while True:
        M5.update()
        if CASE == "joystick-v11":
            value = (unit.get_x_raw(), unit.get_y_raw(), int(unit.get_button_status()))
            marker = "CONTROL_JOYSTICK %d %d %d" % value
        elif CASE == "encoder":
            value = (unit._get_rotary_value(), int(unit.get_button_status()))
            marker = "CONTROL_ENCODER %d %d" % value
        elif CASE == "8encoder":
            counts = [unit.get_counter_value(i) for i in range(1, 9)]
            pressed = [int(unit.get_button_status(i)) for i in range(1, 9)]
            increments = [unit.get_increment_value(i) for i in range(1, 9)]
            switch = int(unit.get_switch_status())
            value = (counts, pressed, switch)
            marker = "CONTROL_ENCODER8 %s %s %d INC %s" % (counts, pressed, switch, increments)
        elif CASE == "cardkb":
            key = unit.get_key()
            if key is not None:
                emit("CONTROL_CARDKB_KEY", key)
                value = key
                marker = "CONTROL_CARDKB_LAST %d" % key
            else:
                check_internal("after_op")
                time.sleep_ms(10)
                continue
        else:
            # The vendored official UID container never assigns .size. Read
            # UID-size bits from the real ATQA response instead of patching the
            # driver or borrowing the host's injected uid-hex length.
            atqa = bytearray(2)
            request = unit.picc_request_a(atqa)
            present = request == unit.STATUS_OK or request == unit.STATUS_COLLISION
            if present and unit.picc_read_card_serial():
                uid_size = (4, 7, 10)[(atqa[0] >> 6) & 3]
                uid = bytes(unit._uid.uid[:uid_size])
                value = uid.hex()
                marker = "CONTROL_RFID_UID " + value
                if last_uid != uid:
                    emit(marker)
                    bad_crc, _, _ = unit.pcd_transceive_data(bytearray([0x30, 4, 0, 0]))
                    emit("CONTROL_RFID_BAD_CRC", int(bad_crc != unit.STATUS_OK))
                    bad = unit.pcd_authenticate(0x60, 4, bytes([0] * 6), unit._uid)
                    emit("CONTROL_RFID_BAD_KEY", int(bad != unit.STATUS_OK))
                    good = unit.pcd_authenticate(0x60, 4, bytes([0xFF] * 6), unit._uid)
                    wrong_sector = unit.mifare_read(8, bytearray(16))
                    emit("CONTROL_RFID_SECTOR_DENIED", int(wrong_sector != unit.STATUS_OK))
                    data = bytes([0x31 + i for i in range(16)])
                    write = unit.mifare_write(4, data)
                    read = bytearray(16)
                    status = unit.mifare_read(4, read)
                    emit("CONTROL_RFID_BLOCK", int(good == unit.STATUS_OK), int(write == unit.STATUS_OK), int(status == unit.STATUS_OK), read.hex())
                    unit.picc_halt_a()
                    unit.pcd_stop_crypto1()
                    denied = unit.mifare_read(4, bytearray(16))
                    emit("CONTROL_RFID_HALT_DENIED", int(denied != unit.STATUS_OK))
                    unit.pcd_antenna_off()
                    emit("CONTROL_RFID_ANTENNA_OFF", int(not unit.picc_is_new_card_present()))
                    unit.pcd_antenna_on()
                    last_uid = uid
            else:
                value = None
                marker = "CONTROL_RFID_NO_CARD"
        if value != previous or time.ticks_diff(time.ticks_ms(), last_at) > 2000:
            emit(marker)
            lines = value_lines(CASE, value)
            if len(lines) > layout["body_rows"]:
                raise RuntimeError("control readout has more rows than the host layout")
            screen.fillRect(layout["x"], layout["body_y"], layout["width"],
                            layout["body_rows"] * layout["line_height"], 0xFFFFFF)
            for row, text in enumerate(lines):
                print_checked(screen, layout, text, layout["body_y"] + row * layout["line_height"])
            previous = value
            last_at = time.ticks_ms()
        check_internal("after_op")
        time.sleep_ms(120)


try:
    run()
except Exception as error:
    emit("CONTROL_PROBE_ERROR", repr(error))
    trace = io.StringIO()
    sys.print_exception(error, trace)
    if log_uart is not None:
        log_uart.write(trace.getvalue().replace("\n", "\r\n"))
    raise
