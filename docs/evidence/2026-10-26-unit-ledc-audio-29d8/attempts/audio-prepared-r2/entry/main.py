import io
import sys
from machine import UART

try:
    import mmio_program
except Exception as error:
    trace = io.StringIO()
    sys.print_exception(error, trace)
    UART(0, baudrate=115200, tx=43, rx=44).write("LEDC_DIAG_FAIL " + trace.getvalue() + "\r\n")
    raise
