import json
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
pose = 0
last_move = 0
last_read = 0
body_levels = None


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


def draw_count():
    d.fillRect(8, height // 2, width - 16, 30, 0x102030)
    d.setCursor(8, height // 2 + 6)
    d.setTextColor(0xFFFFFF)
    d.print("Count: %d" % count)
    if count:
        d.fillRect(2, 2, 8, 8, 0x00FF00)


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


def update_motion(now):
    global pose, last_move, last_read, body_levels
    if servo is None:
        return
    try:
        if not last_move or time.ticks_diff(now, last_move) >= HOLD_MS:
            yaw, pitch = POSES[pose]
            yaw_raw = YAW_HOME + yaw * 16 // 5
            pitch_raw = PITCH_HOME + pitch * 16 // 5
            if not servo.write_pos(1, yaw_raw, MOVE_MS, 0):
                raise RuntimeError("servo X write failed")
            if not servo.write_pos(2, pitch_raw, MOVE_MS, 0):
                raise RuntimeError("servo Y write failed")
            emit("servo-command", pose=pose, yaw_raw=yaw_raw, pitch_raw=pitch_raw,
                 move_ms=MOVE_MS)
            pose = (pose + 1) % len(POSES)
            last_move = now
        if time.ticks_diff(now, last_read) >= 400:
            yaw_raw, pitch_raw = servo.read_pos(1), servo.read_pos(2)
            if yaw_raw < 0 or pitch_raw < 0:
                raise RuntimeError("servo read failed")
            emit("servo-readback", yaw_raw=yaw_raw, pitch_raw=pitch_raw)
            d.fillRect(8, 62, width - 16, 24, 0x102030)
            d.setCursor(8, 66)
            d.setTextColor(0xFFFFFF)
            d.print("UART1 X:%d Y:%d" % (yaw_raw, pitch_raw))
            levels = stackchan.get_touch()
            if levels != body_levels:
                body_levels = levels
                emit("body-touch", levels=levels)
            last_read = now
    except Exception as error:
        motion_error(error)


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
d.setTextColor(0xFFFFFF)
d.setCursor(8, 20)
d.print(DEVICE_ID)
d.setCursor(8, 38)
d.print("C/QEMU browser")
draw_count()
setup_motion()
emit("ready", board=M5.getBoard(), width=width, height=height, input=INPUT_MODE)
heartbeat = time.ticks_ms()
while True:
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
            draw_count()
            emit("count", count=count)
        was_pressed = pressed
    now = time.ticks_ms()
    update_motion(now)
    if time.ticks_diff(now, heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, count=count)
        heartbeat = now
    time.sleep_ms(25)
