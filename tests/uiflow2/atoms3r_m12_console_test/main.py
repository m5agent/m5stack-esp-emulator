import M5
import time
from M5 import *

# FRAMESIZE enum values in the official esp32-camera build (sensor.h):
#   1 QQVGA 160x120, 6 QVGA 320x240, 10 VGA 640x480, 13 HD 1280x720.
GEOMETRY_CASES = (
    ("QQVGA", 1, 160, 120),
    ("VGA", 10, 640, 480),
    ("HD", 13, 1280, 720),
)
QVGA_SIZE = 6
STREAM_FRAMES = 5


def frame_sha256(frame):
    import hashlib
    import binascii
    return binascii.hexlify(hashlib.sha256(bytes(frame)).digest()).decode()


print("M12_MAIN_START")
M5.begin()
print("M12_M5_BEGIN_OK")
print("M12_BOARD", M5.getBoard())
display = M5.Display
display.fillScreen(0x000000)
display.setTextColor(0xFFFFFF, 0x000000)
display.setCursor(4, 8)
display.print("AtomS3R-M12 probe")
status = "blocked"
try:
    from machine import I2C, Pin
    bus = I2C(0, scl=Pin(9), sda=Pin(12), freq=100000)
    print("M12_I2C_SCAN", [hex(a) for a in bus.scan()])
    bus.writeto(0x3C, bytes([0x30, 0x0A]))
    pid_high = bus.readfrom(0x3C, 1)[0]
    bus.writeto(0x3C, bytes([0x30, 0x0B]))
    pid_low = bus.readfrom(0x3C, 1)[0]
    print("M12_PID %02x%02x" % (pid_high, pid_low))
except Exception as exc:
    print("M12_I2C_ERROR", repr(exc))

try:
    import camera

    # Baseline: module default (QVGA) single frame.
    init_result = camera.init()
    print("M12_INIT", init_result)
    buf = camera.capture()
    size = len(buf) if buf else 0
    print("M12_CAPTURE_BYTES", size)
    if size:
        print("M12_FRAME_FIRST64", bytes(buf[:64]).hex())
        print("M12_FRAME_SHA256", frame_sha256(buf))
    camera.deinit()

    geometry_ok = 0
    for name, index, width, height in GEOMETRY_CASES:
        camera.init(framesize=index)
        frame = camera.capture()
        frame_size = len(frame) if frame else 0
        digest = frame_sha256(frame) if frame else "-"
        expected = width * height * 2
        if frame_size == expected:
            geometry_ok += 1
        print("M12_GEOM", name, index, width, height, frame_size, digest)
        camera.deinit()
    print("M12_GEOMETRY_DONE", geometry_ok, len(GEOMETRY_CASES))

    # The host enables the LCD_CAM frame counter (QOM auto-increment) once it
    # observes M12_BASE_DONE, so streamed frames advance through the synthetic
    # scene instead of repeating one static frame.
    print("M12_BASE_DONE")
    time.sleep_ms(1500)

    camera.init(framesize=QVGA_SIZE)
    digests = []
    sizes_ok = 0
    for index in range(STREAM_FRAMES):
        frame = camera.capture()
        frame_size = len(frame) if frame else 0
        digest = frame_sha256(frame) if frame else "-"
        if frame_size == 320 * 240 * 2:
            sizes_ok += 1
        digests.append(digest)
        print("M12_STREAM_FRAME", index, frame_size, digest)
    camera.deinit()
    print("M12_STREAM_CAPTURED", len(digests))
    print("M12_STREAM_BYTES_OK", sizes_ok)
    print("M12_STREAM_DISTINCT", len(set(digests)))
    status = "ok"
except Exception as exc:
    print("M12_ERROR", repr(exc))
print("M12_STATUS", status)
display.setCursor(4, 28)
display.print("cam=%s" % status)
while True:
    M5.update()
    time.sleep_ms(100)
