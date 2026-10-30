import json
import _thread
import time

import M5
from browser_probe_config import DEVICE_ID, ROTATION, INPUT_MODE
from hardware.stackchan import StackChan


if DEVICE_ID != "stackchan":
    raise ValueError("StackChan motion fixture configuration mismatch")

# Virtual assembly reference, matching the explicit browser profile, not a
# claim about a physical unit's NVS zero. Original SCS APIs move raw positions;
# the firmware's saved zero calibration is never rewritten by this demo.
YAW_HOME = 460
PITCH_HOME = 620
POSES = ((-45, 20), (45, 20), (0, 75), (0, 0))
MOVE_MS = 700
HOLD_MS = 1600
stackchan = None
servo = None
body_levels = None
body_sensor_ok = True
motion_events = []
motion_lock = _thread.allocate_lock()
motion_events_dropped = 0
last_body_read = 0
readback = [None, None]
drawn_fields = [list("      "), list("    "), list("    ")]
indicator_dirty = False
last_input_at = 0
max_input_gap = 0


count = 0
was_pressed = False
sequence = 0


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["device"] = DEVICE_ID
    fields["kind"] = kind
    fields["seq"] = sequence
    print("M5_BROWSER_PROBE " + json.dumps(fields))


def draw_dynamic():
    global indicator_dirty
    # One character per pass bounds SPI work as well as UART work. The
    # previous whole telemetry strip delayed input by over a second in WASM.
    fields = ((80, height // 2 + 6, "%-6d" % count),
              (32, 66, "%4d" % readback[0] if readback[0] is not None else "    "),
              (184, 66, "%4d" % readback[1] if readback[1] is not None else "    "))
    for field, (x, y, text) in enumerate(fields):
        if len(text) > len(drawn_fields[field]):
            drawn_fields[field].extend([" "] * (len(text) - len(drawn_fields[field])))
        for digit, char in enumerate(text):
            if char != drawn_fields[field][digit]:
                d.fillRect(x + digit * 12, y, 12, 16, 0x102030)
                d.setCursor(x + digit * 12, y)
                d.print(char)
                drawn_fields[field][digit] = char
                return
    if indicator_dirty:
        d.fillRect(2, 2, 8, 8, 0x00FF00)
        indicator_dirty = False


def poll_input():
    global was_pressed, count, indicator_dirty
    global last_input_at, max_input_gap
    now = time.ticks_ms()
    if last_input_at:
        max_input_gap = max(max_input_gap, time.ticks_diff(now, last_input_at))
    last_input_at = now
    M5.update()
    if INPUT_MODE == "touch":
        pressed = M5.Touch.getCount() > 0
        x, y = M5.Touch.getX(), M5.Touch.getY()
    else:
        pressed = M5.BtnA.isPressed()
        x, y = -1, -1
    if pressed != was_pressed:
        emit("pressed" if pressed else "released", x=x, y=y, count=count)
        if pressed:
            count += 1
            indicator_dirty = indicator_dirty or count == 1
            emit("count", count=count)
        was_pressed = pressed


def motion_error(error):
    global servo
    servo = None
    emit("servo-error", error=repr(error))
    if stackchan is not None:
        try:
            stackchan.set_servo_power(enable=False, settle_ms=0)
        except Exception:
            pass


def setup_motion():
    global stackchan, servo
    try:
        stackchan = StackChan(i2c=1, uart=1)
        stackchan.set_servo_power(enable=True, settle_ms=500)
        # Restore position mode through the original driver after an earlier
        # PWM example; no host-side angle or actuator state is injected.
        if not stackchan.ensure_servo_x_mode(0):
            raise RuntimeError("servo position mode failed")
        if not stackchan.set_servo_torque(stackchan.SERVO_ID_X, enable=True):
            raise RuntimeError("servo X torque failed")
        if not stackchan.set_servo_torque(stackchan.SERVO_ID_Y, enable=True):
            raise RuntimeError("servo Y torque failed")
        servo = stackchan.servo
        if servo.ping(1) != 1 or servo.ping(2) != 2:
            raise RuntimeError("servo ping failed")
        emit("servo-ready", yaw_raw=servo.read_pos(1), pitch_raw=servo.read_pos(2),
             motion="uart1-scs-position", nominal_home=[YAW_HOME, PITCH_HOME])
    except Exception as error:
        motion_error(error)


def post_motion(kind, **fields):
    global motion_events_dropped
    # Only owned event payloads cross the short queue lock. No UART, I2C,
    # display, print or sleep is called with the lock held.
    motion_lock.acquire()
    try:
        if len(motion_events) >= 8:
            motion_events.pop(0)
            motion_events_dropped += 1
        motion_events.append((kind, fields))
    finally:
        motion_lock.release()


def take_motion():
    if not motion_lock.acquire(0):
        return None
    try:
        return motion_events.pop(0) if motion_events else None
    finally:
        motion_lock.release()


def motion_worker():
    # Runtime worker owns only the original UART SCS APIs. M5.update, Si12T,
    # display and power I2C remain exclusively in the foreground thread.
    motor = servo
    worker_pose = 0
    moved_at = read_at = 0
    try:
        post_motion("servo-worker-ready", implementation="_thread", io="uart1-scs-only")
        while True:
            now = time.ticks_ms()
            if not moved_at or time.ticks_diff(now, moved_at) >= HOLD_MS:
                yaw, pitch = POSES[worker_pose]
                yaw_raw = YAW_HOME + yaw * 16 // 5
                pitch_raw = PITCH_HOME + pitch * 16 // 5
                if not motor.write_pos(1, yaw_raw, MOVE_MS, 0):
                    raise RuntimeError("servo X write failed")
                if not motor.write_pos(2, pitch_raw, MOVE_MS, 0):
                    raise RuntimeError("servo Y write failed")
                post_motion("servo-command", pose=worker_pose, yaw_raw=yaw_raw,
                            pitch_raw=pitch_raw, move_ms=MOVE_MS)
                worker_pose = (worker_pose + 1) % len(POSES)
                moved_at = time.ticks_ms()
            if time.ticks_diff(now, read_at) >= 400:
                yaw_raw, pitch_raw = motor.read_pos(1), motor.read_pos(2)
                if yaw_raw < 0 or pitch_raw < 0:
                    raise RuntimeError("servo read failed")
                post_motion("servo-readback", yaw_raw=yaw_raw, pitch_raw=pitch_raw)
                read_at = time.ticks_ms()
            time.sleep_ms(5)
    except Exception as error:
        # Power-off uses I2C and is handled by the foreground, never here.
        post_motion("servo-error", error=repr(error))


def service_motion_event():
    event = take_motion()
    if event is None:
        return
    kind, fields = event
    if kind == "servo-error":
        motion_error(fields["error"])
    else:
        if kind == "servo-readback":
            readback[0], readback[1] = fields["yaw_raw"], fields["pitch_raw"]
        emit(kind, **fields)


def service_body_touch():
    global last_body_read, body_levels, body_sensor_ok
    if stackchan is None or not body_sensor_ok:
        return False
    now = time.ticks_ms()
    if time.ticks_diff(now, last_body_read) < 400:
        return False
    try:
        levels = stackchan.get_touch()
        if levels != body_levels:
            body_levels = levels
            emit("body-touch", levels=levels)
    except Exception as error:
        body_sensor_ok = False
        emit("body-touch-error", error=repr(error))
    last_body_read = time.ticks_ms()
    return True


emit("begin")
M5.begin()
d = M5.Display
d.setRotation(ROTATION)
d.setBrightness(255)
width, height = d.width(), d.height()
d.fillScreen(0x102030)
d.drawRect(1, 1, width - 2, height - 2, 0x2176FF)
d.fillRect(2, 2, 8, 8, 0xFF0000)
d.setTextSize(1)
d.setTextColor(0xFFFFFF, 0x102030)
d.setCursor(8, 20)
d.print(DEVICE_ID)
d.setCursor(8, 38)
d.print("C/QEMU browser")
d.setCursor(8, 66)
d.print("X:")
d.setCursor(160, 66)
d.print("Y:")
d.setCursor(8, height // 2 + 6)
d.print("Count:")
draw_dynamic()
setup_motion()
if servo is not None:
    try:
        _thread.start_new_thread(motion_worker, ())
    except Exception as error:
        motion_error(error)
emit("ready", board=M5.getBoard(), width=width, height=height, input=INPUT_MODE)
heartbeat = time.ticks_ms()
while True:
    poll_input()
    service_motion_event()
    poll_input()
    if not service_body_touch():
        draw_dynamic()
    poll_input()
    now = time.ticks_ms()
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count,
             max_input_gap_ms=max_input_gap,
             motion_events_dropped=motion_events_dropped)
        heartbeat = now
    time.sleep_ms(5)
