# NanoC6 has no display; verify the UIFlow2 runtime and board identity.
import M5
import time

print("NANOC6_MAIN_START")
M5.begin()
print("NANOC6_BOARD", M5.getBoard())
try:
    from hardware import IR
    ir = IR()
    ir.tx(0x56, 0xA3)
    print("NANOC6_IR_TX 0x56 0xA3")
except Exception as error:
    print("NANOC6_IR_ERR", repr(error))
print("NANOC6_LOOP")
while True:
    print("NANOC6_ALIVE")
    time.sleep(1)
