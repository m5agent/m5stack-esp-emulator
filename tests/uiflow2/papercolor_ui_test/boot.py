# Official UIFlow2 uses USB CDC for this board. Observe the unchanged
# guest probe through the real UART0 controller; this does not test USB.
from machine import UART
import os

_repl_uart = UART(0, baudrate=115200, timeout=0, timeout_char=0)
os.dupterm(_repl_uart, 0)
_repl_uart.irq(handler=os.dupterm_notify, trigger=UART.IRQ_RX)
_uiflow_run_main = True
print("PAPERCOLOR_BOOT_FLAG")
