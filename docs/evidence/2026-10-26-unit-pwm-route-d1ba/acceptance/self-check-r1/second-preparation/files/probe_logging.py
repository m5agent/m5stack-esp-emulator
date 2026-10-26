from machine import UART

console = UART(0, baudrate=115200, tx=43, rx=44)


def emit(*parts):
    console.write(" ".join(str(part) for part in parts) + "\r\n")
