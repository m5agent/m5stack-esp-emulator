# NanoC6 has no display; verify the UIFlow2 runtime and board identity.
import M5
import time

print("NANOC6_MAIN_START")
M5.begin()
print("NANOC6_BOARD", M5.getBoard())
print("NANOC6_LOOP")
while True:
    print("NANOC6_ALIVE")
    time.sleep(1)
