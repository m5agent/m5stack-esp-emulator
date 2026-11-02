import M5
import time
from M5 import *

print("CAM_MAIN_START")
M5.begin()
print("CAM_M5_BEGIN_OK")
print("CAM_BOARD", M5.getBoard())
display = M5.Display
display.fillScreen(0x000000)
display.setTextColor(0xFFFFFF, 0x000000)
display.setCursor(4, 8)
display.print("AtomS3R-CAM probe")
status = "blocked"
try:
    from machine import I2C, Pin
    bus = I2C(0, scl=Pin(9), sda=Pin(12), freq=100000)
    print("CAM_I2C_SCAN", [hex(a) for a in bus.scan()])
    bus.writeto_mem(0x21, 0xfe, b"\x00")
    print("CAM_PID", bus.readfrom_mem(0x21, 0x00, 2).hex())
except Exception as exc:
    print("CAM_I2C_ERROR", repr(exc))


def frame_digest(frame):
    try:
        import hashlib
        return "sha256", hashlib.sha256(frame).hexdigest()
    except Exception:
        pass
    fnv = 2166136261
    for value in frame:
        fnv = ((fnv ^ value) * 16777619) & 0xFFFFFFFF
    return "fnv1a", "%08x" % fnv


try:
    import camera
    init_result = camera.init()
    print("CAM_INIT_RESULT", init_result)
    buf = camera.capture()
    size = len(buf) if buf else 0
    print("CAM_CAPTURE_BYTES", size)
    if size:
        print("CAM_FRAME_FIRST64", bytes(buf[:64]).hex())
        algo, digest = frame_digest(buf)
        print("CAM_FRAME_DIGEST", algo, digest)
        print("CAM_FRAME_SUM", sum(buf) & 0xFFFFFFFF)
        status = "ok"
except Exception as exc:
    print("CAM_ERROR", repr(exc))
    status = "blocked"
print("CAM_STATUS", status)
display.setCursor(4, 28)
display.print("cam=%s" % status)
while True:
    M5.update()
    time.sleep_ms(100)
