import M5
import struct
import time
from M5 import *


SAMPLE_RATE = 48000
FREQUENCY = 1000
DURATION_MS = 200
AMPLITUDE = 8192


M5.begin()
d = M5.Display
d.setRotation(1)
d.fillScreen(d.COLOR.BLACK)
d.setTextColor(d.COLOR.WHITE)
d.setTextSize(1)

status = "init"
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.setVolumePercentage(0.8)

    sample_count = SAMPLE_RATE * DURATION_MS // 1000
    period = SAMPLE_RATE // FREQUENCY
    half_period = period // 2
    raw = bytearray(sample_count * 2)
    for index in range(sample_count):
        value = AMPLITUDE if index % period < half_period else -AMPLITUDE
        struct.pack_into("<h", raw, index * 2, value)

    ok = Speaker.playRaw(
        raw,
        SAMPLE_RATE,
        False,
        1,
        0,
        True,
    )
    if not ok:
        raise RuntimeError("playRaw failed")
    status = "square=1000Hz raw=200ms"
except Exception as error:
    status = "error " + repr(error)[:36]

d.setCursor(8, 16)
d.print("CoreS3 audio fidelity")
d.setCursor(8, 40)
d.print(status)
d.setCursor(8, 58)
d.print("samples=%d" % (SAMPLE_RATE * DURATION_MS // 1000))

while True:
    M5.update()
    time.sleep_ms(100)
