import M5
import time
from M5 import *

# FRAMESIZE enum values in the official esp32-camera build (sensor.h):
#   1 QQVGA 160x120, 5 240x240, 6 QVGA 320x240, 8 CIF 400x296, 10 VGA 640x480.
GEOMETRY_CASES = (
    ("QQVGA", 1, 160, 120),
    ("240X240", 5, 240, 240),
    ("CIF", 8, 400, 296),
    ("VGA", 10, 640, 480),
)
QVGA_SIZE = 6
STREAM_FRAMES = 5


def frame_sha256(frame):
    import hashlib
    import binascii
    return binascii.hexlify(hashlib.sha256(bytes(frame)).digest()).decode()


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

try:
    import camera

    # Baseline: the module default frame size (QVGA) keeps the original
    # single-frame oracle and is captured before any scene animation.
    init_result = camera.init()
    print("CAM_INIT_RESULT", init_result)
    buf = camera.capture()
    size = len(buf) if buf else 0
    print("CAM_CAPTURE_BYTES", size)
    if size:
        print("CAM_FRAME_FIRST64", bytes(buf[:64]).hex())
        print("CAM_FRAME_SHA256", frame_sha256(buf))
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
        print("CAM_GEOM", name, index, width, height, frame_size, digest)
        camera.deinit()
    print("CAM_GEOMETRY_DONE", geometry_ok, len(GEOMETRY_CASES))

    # The host enables the LCD_CAM frame counter (QOM auto-increment) once it
    # observes CAM_BASE_DONE, so the stream frames advance deterministically
    # through the synthetic scene instead of repeating one static frame.
    print("CAM_BASE_DONE")
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
        print("CAM_STREAM_FRAME", index, frame_size, digest)
    camera.deinit()
    print("CAM_STREAM_CAPTURED", len(digests))
    print("CAM_STREAM_BYTES_OK", sizes_ok)
    print("CAM_STREAM_DISTINCT", len(set(digests)))
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
