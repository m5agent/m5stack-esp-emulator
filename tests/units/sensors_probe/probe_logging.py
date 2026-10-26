from hardware import UART
from probe_config import DEVICE_ID

serial = None


def init():
    global serial
    if DEVICE_ID == "cores3":
        serial = UART(0, baudrate=115200, tx=43, rx=44)
    else:
        serial = UART(0, baudrate=115200)


def emit(*parts):
    serial.write(" ".join(str(part) for part in parts) + "\n")


init()
