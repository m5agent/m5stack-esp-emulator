"""One native camera conversion/borrow lane followed by a scheduling boundary.

The fixture selects raw, jpg, bmp or snapshot. Real LCD_CAM register values
are recorded; no sensor/frame values are synthesized in the guest.
"""
import hashlib
import json
import time
import camera
import machine
import M5
from camera_case_config import CASE


def emit(phase, **details):
    details.update(case=CASE, phase=phase)
    print("CAMERA_PHASE " + json.dumps(details))


def registers(phase):
    emit(phase, cam_ctrl=machine.mem32[0x60041004],
         cam_ctrl1=machine.mem32[0x60041008], cam_rgb=machine.mem32[0x6004100c])


try:
    M5.begin()
    print("CAMERA_PHASE_SCENE_READY")
    time.sleep_ms(2500)
    initialized = camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    emit("init", returned=initialized)
    if initialized is not True:
        raise RuntimeError("native camera initialization failed")
    registers("registers-before")
    if CASE == "raw":
        value = camera.capture()
    elif CASE == "jpg":
        value = camera.capture_to_jpg(80)
    elif CASE == "bmp":
        value = camera.capture_to_bmp()
    elif CASE == "snapshot":
        borrowed = camera.snapshot()
        value = borrowed.bytearray()
    else:
        raise ValueError("unknown native camera phase")
    emit("native-result", bytes=len(value), sha256=hashlib.sha256(value).digest().hex())
    # Force an immediate scheduler check so a conversion stack failure is
    # attributed to this single lane, before an unrelated camera operation.
    M5.update()
    time.sleep_ms(50)
    emit("scheduled-after-native")
    resized = camera.framesize(camera.QVGA)
    emit("framesize", returned=resized)
    if resized is not True:
        raise RuntimeError("native camera framesize re-probe failed")
    registers("registers-after")
    raw = camera.capture()
    emit("capture-after-framesize", bytes=len(raw) if isinstance(raw, bytes) else 0,
         sha256=hashlib.sha256(raw).digest().hex() if isinstance(raw, bytes) else None)
    deinitialized = camera.deinit()
    emit("deinit", returned=deinitialized, capture_after_deinit=camera.capture())
except Exception as error:
    emit("exception", error=repr(error))
print("CAMERA_PHASE_DONE")
