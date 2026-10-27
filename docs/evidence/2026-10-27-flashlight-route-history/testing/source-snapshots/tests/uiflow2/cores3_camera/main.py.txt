import M5
import time
import camera


status = "init"
detail = ""
image = None
input_count = 0
stage = "init"
log_uart = None
frame_changes = 0


def emit(*parts):
    if log_uart:
        log_uart.write(" ".join(str(part) for part in parts) + "\n")


def draw():
    d = M5.Display
    d.fillScreen(d.COLOR.BLACK)
    d.setTextColor(d.COLOR.WHITE)
    d.setTextSize(2)
    d.setCursor(10, 10)
    d.print("CoreS3 camera")
    d.setTextSize(1)
    d.setCursor(10, 44)
    d.print(status)
    d.setCursor(10, 64)
    d.print(detail)
    d.setCursor(10, 86)
    d.print("input:%d" % input_count)


print("CORES3_CAMERA_MAIN")
M5.begin()
try:
    from hardware import UART
    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
draw()
try:
    stage = "init"
    camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
    status = "init ok"
    draw()
    stage = "snapshot"
    image = camera.snapshot()
    if image is None:
        raise RuntimeError("snapshot returned None")
    detail = "%dx%d %d bytes" % (image.width(), image.height(), image.size())
    image.draw_string(8, 8, "M5 EMU", color=(0, 255, 0), scale=2)
    M5.Display.show(image, 0, 0)
    emit("CORES3_CAMERA_PASS", detail)
    status = "snapshot ok"
    if M5.getBoard() in (10, 17):
        previous = bytes(image.bytearray())
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (frame_changes < 1
               and time.ticks_diff(deadline, time.ticks_ms()) > 0):
            M5.update()
            next_image = camera.snapshot()
            if next_image is None:
                continue
            current = bytes(next_image.bytearray())
            if current != previous:
                frame_changes += 1
                previous = current
                image = next_image
                signature = current[:16].hex()
                emit("CORES3_CAMERA_FRAME_CHANGE",
                     frame_changes, next_image.size(), signature)
                image.draw_string(8, 8, "M5 EMU", color=(0, 255, 0), scale=2)
                M5.Display.show(image, 0, 0)
            time.sleep_ms(100)
        if frame_changes >= 1:
            emit("CORES3_CAMERA_FRAMESTREAM PASS", frame_changes)
        else:
            emit("CORES3_CAMERA_FRAMESTREAM FAIL", frame_changes)
except Exception as error:
    if stage == "snapshot":
        status = "camera partial"
        detail = "init ok; snapshot returned None"
    else:
        status = "camera error"
        detail = "init failed: " + repr(error)[:55]
    emit("CORES3_CAMERA_ERR", repr(error))

if image is None:
    draw()
else:
    d = M5.Display
    d.setTextColor(d.COLOR.WHITE, d.COLOR.BLACK)
    d.setTextSize(1)
    d.setCursor(8, 220)
    d.print(status + " " + detail)

while True:
    M5.update()
    changed = False
    if hasattr(BtnPWR, "wasHold") and BtnPWR.wasHold():
        input_count += 1
        changed = True
    if M5.Touch.getCount() > 0:
        if input_count == 0:
            input_count = 1
            changed = True
    if changed:
        draw()
    time.sleep_ms(20)
