"""All actual native camera module entry points, with explicit evidence levels."""
import json
import hashlib
import time
import M5


def emit(api, status, **details):
    details.update(api="camera." + api, status=status)
    print("VISION_API " + json.dumps(details))


def blob(kind, data):
    digest = hashlib.sha256(data).digest().hex()
    print("CAMERA_BLOB " + json.dumps({"kind": kind, "bytes": len(data), "sha256": digest}))
    if kind != "raw":
        for index in range(0, len(data), 2048):
            print("CAMERA_BLOB_CHUNK " + json.dumps({"kind": kind, "offset": index, "hex": data[index:index + 2048].hex()}))
    return digest


def run():
    try:
        import camera
    except ImportError as error:
        emit("module", "UNAVAILABLE_ON_DEVICE", error=repr(error))
        return
    M5.begin()
    print("CAMERA_INTERFACES_SCENE_READY")
    deadline = time.ticks_add(time.ticks_ms(), 2500)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)
    initialized = camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    if initialized is not True:
        emit("init", "FAIL", returned=initialized)
        return
    capture = camera.capture()
    emit("init", "PASS" if initialized and isinstance(capture, bytes) and len(capture) == 153600 else "FAIL", oracle="init followed by complete native QVGA capture")
    if not isinstance(capture, bytes):
        raise RuntimeError("native camera capture did not return bytes")
    blob("raw", capture)
    emit("capture", "OBSERVED", bytes=len(capture), sha256=hashlib.sha256(capture).digest().hex(), oracle="host must match complete raw frame against independent scene hash")
    before = time.ticks_ms()
    camera.skip_frames(2)
    after = camera.capture()
    emit("skip_frames", "OBSERVED", bytes=len(after) if isinstance(after, bytes) else 0,
         sha256=hashlib.sha256(after).digest().hex() if isinstance(after, bytes) else None,
         elapsed_ms=time.ticks_diff(time.ticks_ms(), before), oracle="discard two real controller frames then capture a complete third")
    for name, args, kind in (("capture_to_jpg", (80,), "jpg"), ("capture_to_bmp", (), "bmp")):
        try:
            data = getattr(camera, name)(*args)
            if not isinstance(data, bytes):
                raise RuntimeError("native converter did not return image bytes")
            digest = blob(kind, data)
            emit(name, "OBSERVED", bytes=len(data), sha256=digest, oracle="independent host image decoder and known scene pixels required")
        except Exception as error:
            emit(name, "FAIL", error=repr(error))
    frame = camera.snapshot()
    emit("snapshot", "OBSERVED", width=frame.width() if frame else 0, height=frame.height() if frame else 0,
         bytes=frame.size() if frame else 0, sha256=hashlib.sha256(frame.bytearray()).digest().hex() if frame else None,
         oracle="independent complete scene hash required")
    for setter, getter in (("set_hmirror", "get_hmirror"), ("set_vflip", "get_vflip")):
        for value in (False, True):
            getattr(camera, setter)(value)
            observed = getattr(camera, getter)()
            for method in (setter, getter):
                emit(method, "STATE_PASS" if observed is value else "FAIL", value=observed,
                     argument_domain="software status getter; sensor image orientation not established")
    camera.set_hmirror(False)
    camera.set_vflip(False)
    for name, arguments in (("contrast", (0,)), ("global_gain", (0,)), ("hmirror", (0,)), ("vflip", (0,)), ("colorbar", (0,))):
        try:
            returned = getattr(camera, name)(*arguments)
            emit(name, "CALL_OK" if returned else "FAIL", returned=returned,
                 oracle="native sensor driver command executed; register-to-pixel transform is a separate unvalidated model capability")
        except Exception as error:
            emit(name, "FAIL", error=repr(error))
    # Reconfiguration can tear down the native sensor. Keep it after unrelated
    # API observations and stop at the first failure instead of calling through
    # a NULL sensor pointer and obscuring the original SCCB failure.
    for name, arguments in (("pixformat", (camera.RGB565,)), ("framesize", (camera.QVGA,))):
        returned = getattr(camera, name)(*arguments)
        emit(name, "CALL_OK" if returned is True else "FAIL", returned=returned,
             argument_domain="QVGA RGB565; alternate formats/resolutions are not inherited")
        if returned is not True:
            return
        frame_bytes = camera.capture()
        emit("capture", "OBSERVED", phase="after-" + name,
             bytes=len(frame_bytes) if isinstance(frame_bytes, bytes) else 0,
             sha256=hashlib.sha256(frame_bytes).digest().hex() if isinstance(frame_bytes, bytes) else None,
             oracle="independent complete scene hash required after reconfiguration")
    deinitialized = camera.deinit()
    rejected = camera.capture()
    emit("deinit", "PASS" if deinitialized and rejected is False else "FAIL", capture_after_deinit=rejected,
         oracle="driver teardown prevents another controller frame acquisition")
    if deinitialized is not True:
        return
    reinitialized = camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    emit("init", "CALL_OK" if reinitialized is True else "FAIL", phase="reinit", returned=reinitialized)
    if reinitialized is not True:
        return
    recapture = camera.capture()
    emit("capture", "OBSERVED", phase="after-reinit",
         bytes=len(recapture) if isinstance(recapture, bytes) else 0,
         sha256=hashlib.sha256(recapture).digest().hex() if isinstance(recapture, bytes) else None,
         oracle="independent complete scene hash required after native init/deinit cycle")
    final_deinit = camera.deinit()
    final_rejected = camera.capture()
    emit("deinit", "PASS" if final_deinit is True and final_rejected is False else "FAIL", phase="final",
         capture_after_deinit=final_rejected, oracle="final teardown prevents controller capture")


try:
    run()
except Exception as error:
    emit("run", "ERROR", error=repr(error))
print("CAMERA_INTERFACES_DONE")
