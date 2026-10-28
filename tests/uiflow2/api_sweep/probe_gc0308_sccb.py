"""CoreS3 GC0308 identity across real init/framesize/deinit SCCB traffic.

This disposable-VM diagnostic reads the board's actual I2C1 sensor registers;
it does not manufacture camera IDs, replace the camera module or infer optical
behavior. QVGA capture is an observation; a separate scene oracle owns pixel
correctness.
"""
import hashlib
import json
import camera
import machine
import M5


def emit(phase, status, **details):
    details.update(phase=phase, status=status)
    print("GC0308_SCCB " + json.dumps(details))


def page_value(bus, page, register):
    bus.writeto_mem(0x21, 0xfe, bytes([page]))
    value = bus.readfrom_mem(0x21, register, 1)[0]
    bus.writeto_mem(0x21, 0xfe, b"\x00")
    return value


def observe_pid(bus, cycle, phase):
    pid = page_value(bus, 0, 0)
    emit(phase, "PASS" if pid == 0x9b else "FAIL", cycle=cycle,
         pid=pid, oracle="page-zero read-only product ID remains 0x9b")


def observe_capture(cycle, phase):
    raw = camera.capture()
    valid = isinstance(raw, bytes) and len(raw) == 153600
    emit(phase, "OBSERVED" if valid else "FAIL", cycle=cycle,
         bytes=len(raw) if isinstance(raw, bytes) else 0,
         sha256=hashlib.sha256(raw).digest().hex() if isinstance(raw, bytes) else None,
         scope="QVGA RGB565 length/hash observation only; independent pixel oracle required")


def run():
    M5.begin()
    # Same I2C1 pins and port used by the CoreS3's native camera SCCB driver.
    # Do not deinitialize this shared internal bus between camera lifecycles.
    bus = machine.I2C(1, scl=machine.Pin(11), sda=machine.Pin(12), freq=400000)
    for cycle in range(3):
        observe_pid(bus, cycle, "before-init-pid")
        initialized = camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
        emit("init", "PASS" if initialized is True else "FAIL", cycle=cycle, returned=initialized)
        if initialized is not True:
            return
        observe_pid(bus, cycle, "after-init-pid")
        page1 = page_value(bus, 1, 0)
        emit("page-one-default", "PASS" if page1 == 0xf5 else "FAIL", cycle=cycle,
             value=page1, oracle="official initialization table stores page-one register zero 0xf5 separately")
        if initialized:
            observe_capture(cycle, "after-init-capture")
            resized = camera.framesize(camera.QVGA)
            emit("framesize", "PASS" if resized is True else "FAIL", cycle=cycle,
                 returned=resized, argument_domain="QVGA RGB565; no alternate geometry claim")
            observe_pid(bus, cycle, "after-framesize-pid")
            if resized is not True:
                # Re-probe failure can leave the native sensor pointer NULL.
                # Preserve the first failure without invoking later setters.
                return
            observe_capture(cycle, "after-framesize-capture")
            deinitialized = camera.deinit()
            emit("deinit", "PASS" if deinitialized is True else "FAIL", cycle=cycle, returned=deinitialized)
        observe_pid(bus, cycle, "after-deinit-pid")
        M5.update()


try:
    run()
except Exception as error:
    emit("run", "FAIL", error=repr(error))
print("GC0308_SCCB_DONE")
