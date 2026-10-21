import M5
import time
from M5 import *
from stamplc import StamPLC


M5.begin()
d = M5.Display
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)
d.setCursor(4, 4)
d.print("StamPLC onboard IO")

plc = StamPLC()
status = "waiting"
ok = False
for _ in range(400):
    M5.update()
    relay_ok = False
    rgb_ok = False
    inputs = ()
    try:
        plc.relay[1].on()
        relay_ok = bool(plc.relay[1].value())
        plc.led.red.on()
        rgb_ok = plc.led.red.value()
        plc.led.red.off()
        inputs = tuple(plc.input[i].value() for i in range(1, 9))
        status = "r:%d rgb:%d in:%s" % (
            relay_ok, rgb_ok, "".join(str(value) for value in inputs)
        )
        if relay_ok and rgb_ok and all(inputs):
            ok = True
            status = "r:%d rgb:%d in:%s" % (
                relay_ok, rgb_ok,
                "".join(str(value) for value in inputs),
            )
            break
    except Exception as exc:
        status = "error: " + repr(exc)
        break
    d.fillRect(0, 28, 240, 36, d.COLOR.BLACK)
    d.setCursor(4, 32)
    d.print(status)
    time.sleep_ms(25)

plc.relay[1].off()
plc.led.red.off()
d.fillRect(0, 0, 240, 8,
           d.COLOR.GREEN if ok else d.COLOR.RED)
d.setCursor(4, 56)
d.print("PASS" if ok else "FAIL")

while True:
    M5.update()
    time.sleep_ms(100)
