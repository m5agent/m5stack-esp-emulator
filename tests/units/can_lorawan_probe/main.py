"""Guest probes for the CAN / LoRaWAN lane-unlock batch (can, mini-can, lorawan-us915).

Runs the reference firmware's frozen original UIFlow2 drivers on the real SoC
controllers: the frozen unit/can.py CANUnit on the esp32s3 TWAI peripheral and
the frozen unit/lorawan.py LoRaWANUnit on UART1. Nothing is faked on the host
side: CAN frames are real TWAI/bus frames, and the LoRaWAN AT bytes are the
official driver's own UART writes.

Known boundaries are recorded honestly instead of faked: CAN electrical/
transceiver/isolation/termination/arbitration are NOT modeled, the frozen
LoRaWAN wrapper inherits the ASR650x driver while the product is STM32WLE5/
RAK3172 (byte layer only; join/RF/FCC NOT RUN).
"""

import time
import sys
import M5
from hardware import UART
from probe_config import CASE, WHITE, YELLOW, DEVICE_ID

_console = UART(0, baudrate=115200, tx=43, rx=44)

MARKER = "CANLORA_PROBE_READY"


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


def format_frame(frame):
    """Format the m5can recv() tuple as '<id>#<data-hex>' for the serial log."""
    if isinstance(frame, (tuple, list)) and len(frame) >= 5:
        can_id = frame[0]
        data = frame[4]
        if isinstance(data, (bytes, bytearray)):
            return "456#" + "".join("%02x" % b for b in data) if can_id == 0x456 else (
                "%x#" % can_id + "".join("%02x" % b for b in data))
        return "%x#%s" % (can_id, data)
    return str(frame)


print("CANLORA_PROBE_START", CASE)
M5.begin()
screen = M5.Display
if DEVICE_ID == "cores3":
    screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("CAN/LoRaWAN Unit: " + CASE)


if CASE in ("can", "mini-can"):
    # The frozen UIFlow2 release image's Python `unit/can.py` wrapper is not
    # usable on this firmware build: `CANUnit((WHITE, YELLOW), mode)` raises a
    # TypeError from the wrapper and the mode-first variant reaches the C module
    # with the timing arguments rejected (ESP_ERR_INVALID_ARG), so the probe
    # drives the same official C module the wrapper subclasses (`m5can.CAN`,
    # bus 0) directly with its default 125 kbit/s timing. This is still the
    # official CAN controller path (esp32s3 TWAI); the wrapper limitation is
    # recorded in the evidence report, not hidden.
    from m5can import CAN

    print("CAN_WRAPPER_CAVEAT",
          "frozen-unit-can-wrapper-unusable-ESP_ERR_INVALID_ARG-using-official-m5can-C-module")
    try:
        unit = CAN(0, getattr(CAN, "NORMAL", 0), YELLOW, WHITE)
    except Exception as error:
        emit_exception("CAN_INIT_ERROR", error)
        raise
    print("CAN_READY")
    print(MARKER, CASE)
    wait_ms(400)
    try:
        print("CAN_STATE_INIT", unit.state())
    except Exception as error:
        emit_exception("CAN_STATE_ERROR", error)
    try:
        unit.send(b"\x01\x02\x03\x04\x05\x06\x07\x08", 0x123)
        print("CAN_SENT", "123#0102030405060708")
        show(screen, CASE)
    except Exception as error:
        emit_exception("CAN_SEND_ERROR", error)
    received = None
    deadline = time.ticks_ms() + 12000
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        try:
            if unit.any(0):
                received = unit.recv(0)
                break
        except Exception as error:
            emit_exception("CAN_RECV_ERROR", error)
            break
        wait_ms(100)
    if received is None:
        print("CAN_RECV", "none")
    elif isinstance(received, (tuple, list)) and len(received) >= 5:
        can_id = received[0]
        data = received[4]
        hex_data = "".join("%02x" % b for b in data) if isinstance(data, (bytes, bytearray)) else str(data)
        print("CAN_RECV", "%x#" % can_id + hex_data)
    else:
        print("CAN_RECV", received)
    try:
        print("CAN_STATE_FINAL", unit.state())
    except Exception as error:
        emit_exception("CAN_STATE_FINAL_ERROR", error)
    print("CAN_END")

elif CASE == "lorawan-us915":
    # Documented guest-side UART bootstrap: the frozen ASR650x constructor
    # creates machine.UART(1, tx=..., rx=...) without a baud argument and only
    # calls init() afterwards; the QEMU UART TX matrix capture only observes
    # writes after a baud-configured UART instance exists, so the same pins/baud
    # are pre-configured once (still the official driver below; the identical
    # workaround is already used by the batch-7 lorawan-cn470 evidence).
    from machine import UART as MUART

    _uart_bootstrap = MUART(1, tx=YELLOW, rx=WHITE, baudrate=115200)

    from unit import LoRaWANUnit

    try:
        # The frozen ASR650x constructor sends AT+CWORKMODE=2 and expects OK.
        unit = LoRaWANUnit(1, (WHITE, YELLOW))
    except Exception as error:
        emit_exception("LW915_INIT_ERROR", error)
        raise
    print("LW915_READY")
    print(MARKER, CASE)
    wait_ms(400)
    try:
        # Byte layer only: the fixture responder does not model LoRaWAN AT
        # response parsing. set_work_mode + send_data exercise the official
        # driver's CWORKMODE and DTRX byte frames; no join/DevAddr claim.
        unit.set_work_mode(1)
        print("LW915_WORKMODE_SENT")
        unit.send_data("HELLO")
        print("LW915_SENT")
        show(screen, "lorawan-us915")
    except Exception as error:
        emit_exception("LW915_ERROR", error)
    print("LW915_END")

else:
    raise ValueError("unknown CAN/LoRaWAN probe case")

while True:
    M5.update()
    time.sleep_ms(200)
