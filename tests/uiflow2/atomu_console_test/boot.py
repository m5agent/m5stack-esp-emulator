# AtomU (K117) console probe: the UIFlow2 image keeps the REPL on UART0,
# which QEMU serial0 observes, so no dupterm redirection is needed.
_uiflow_run_main = True
print("ATOMU_BOOT_FLAG")
