# The official Core-series UIFlow2 image keeps the REPL on UART0, which is
# the CH9102F USB-UART bridge on the Basic v2.7; QEMU serial0 observes it, so
# no dupterm redirection is needed.
_uiflow_run_main = True
print("BASIC27_BOOT_FLAG")
