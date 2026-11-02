# Atom Echo (C008-C) console probe: the UIFlow2 image keeps the REPL on
# UART0, which QEMU serial0 observes, so no dupterm redirection is needed.
_uiflow_run_main = True
print("ATOMECHO_BOOT_FLAG")
