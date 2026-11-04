from machine import UART
import os

_repl_uart = UART(0, baudrate=115200, timeout=0, timeout_char=0)
os.dupterm(_repl_uart, 0)
_repl_uart.irq(handler=os.dupterm_notify, trigger=UART.IRQ_RX)
_uiflow_run_main = True
