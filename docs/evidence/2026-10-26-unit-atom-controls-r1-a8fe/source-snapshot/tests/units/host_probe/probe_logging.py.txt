from hardware import UART
from probe_config import LOG_TX, LOG_RX

console = UART(0, baudrate=115200, tx=LOG_TX, rx=LOG_RX)


def emit(*parts):
    console.write(" ".join(str(part) for part in parts) + "\r\n")
