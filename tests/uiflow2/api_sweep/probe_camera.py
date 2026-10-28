"""CoreS3 QVGA capture/borrow/return recipe with real host scene injection.

The host sets the LCD_CAM frame seed at READY markers through Device Service.
Guest pixels and hashes are observations; an independent host oracle decides
whether complete RGB565 frames crossed the SCCB/LCD_CAM/GDMA path correctly.
"""

import camera
import hashlib
import json
import time
import M5


def camera_wait(milliseconds):
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)


def camera_emit(api, status, value):
    print("HARDWARE_API " + json.dumps({"api": api, "status": status, "value": value}))


def capture_pattern(phase, index):
    print("HARDWARE_CAMERA_PATTERN_CAPTURE", phase, index)
    image = camera.snapshot()
    if image is None:
        camera_emit("camera.snapshot.pattern", "ERROR", {"phase": phase, "index": index, "image": None})
        return None
    raw = image.bytearray()
    camera_emit("camera.snapshot.pattern", "OBSERVED", {"phase": phase, "index": index,
                "bytes": len(raw), "width": image.width(), "height": image.height(),
                "sha256": hashlib.sha256(raw).digest().hex()})
    return image


def run_camera_patterns():
    M5.begin()
    print("HARDWARE_CAMERA_PATTERN_A_READY")
    camera_wait(2500)
    camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    image = None
    for index, delay in enumerate((0, 100, 2500, 100)):
        camera_wait(delay)
        image = capture_pattern("A", index)
    print("HARDWARE_CAMERA_PATTERN_B_READY")
    camera_wait(1500)
    # A snapshot borrows one frame until the next snapshot returns it. Drain
    # pre-injection queued frames before asserting the new controller scene.
    for _ in range(3):
        camera.snapshot()
        camera_wait(100)
    for index, delay in enumerate((0, 100, 2500, 100)):
        camera_wait(delay)
        image = capture_pattern("B", index)
    if image is not None:
        M5.Display.show(image, 0, 0, 320, 240)
    print("HARDWARE_CAMERA_PATTERNS_DONE")
