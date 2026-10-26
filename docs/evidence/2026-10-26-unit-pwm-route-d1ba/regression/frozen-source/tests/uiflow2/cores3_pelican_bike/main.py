import M5
import struct
import time
from M5 import *


WIDTH = 320
HEIGHT = 240
FRAME_MS = 50
MAX_SPEED = 4
AUDIO_RATE = 48000

SKY_TOP = 0x83CDD0
SKY_MID = 0xBFE2CF
SKY_LOW = 0xF5D6A0
SUN = 0xFFC857
CLOUD = 0xEAF5EA
HILL = 0x75A88D
HILL_DARK = 0x41745F
ROAD = 0x26363D
ROAD_EDGE = 0x51646A
ROAD_LINE = 0xF5D28A
INK = 0x18323A
WHITE = 0xFFF8E7
WING = 0xC4D8D3
ORANGE = 0xF08A36
POUCH = 0xFFB657
RED = 0xDF5C50
TEAL = 0x2B8D87
MUTED = 0x60757A

BOB = (0, 1, 2, 1)
SINE64 = (
    0, 3212, 6393, 9512, 12539, 15446, 18204, 20787,
    23170, 25329, 27245, 28898, 30273, 31356, 32137, 32609,
    32767, 32609, 32137, 31356, 30273, 28898, 27245, 25329,
    23170, 20787, 18204, 15446, 12539, 9512, 6393, 3212,
    0, -3212, -6393, -9512, -12539, -15446, -18204, -20787,
    -23170, -25329, -27245, -28898, -30273, -31356, -32137, -32609,
    -32767, -32609, -32137, -31356, -30273, -28898, -27245, -25329,
    -23170, -20787, -18204, -15446, -12539, -9512, -6393, -3212,
)
DIRS = (
    (0, -1), (1, -1), (1, 0), (1, 1),
    (0, 1), (-1, 1), (-1, 0), (-1, -1),
)

canvas = None
phase = 0
paused = False
was_pressed = False
speed_level = 1
drag_active = False
bell_zone_active = False
touch_x = 0
touch_y = 0
touch_distance = 0
notice_text = ""
notice_until = 0
ring_started = 0
bell_audio_until = 0
speaker_ready = False
speaker_error = ""
bell_pcm = None
imu_error = ""
imu_ready = False
imu_source = "API"
imu_ax = 0.0
imu_ay = 0.0
imu_gz = 0.0


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def write_tone(raw, offset, frequency, duration_ms,
               start_amplitude, end_amplitude):
    sample_count = AUDIO_RATE * duration_ms // 1000
    phase = 0
    step = frequency * 64 * 65536 // AUDIO_RATE
    for index in range(sample_count):
        envelope = (
            start_amplitude
            - index * (start_amplitude - end_amplitude) // sample_count
        )
        value = SINE64[(phase >> 16) & 63] * envelope // 32767
        struct.pack_into("<h", raw, offset + index * 2, value)
        phase += step
    return offset + sample_count * 2


def make_bell_pcm():
    high_samples = AUDIO_RATE * 50 // 1000
    gap_samples = AUDIO_RATE * 10 // 1000
    low_samples = AUDIO_RATE * 60 // 1000
    raw = bytearray((high_samples + gap_samples + low_samples) * 2)
    offset = write_tone(raw, 0, 1000, 50, 7168, 4200)
    offset += gap_samples * 2
    write_tone(raw, offset, 800, 60, 6144, 2800)
    return raw


def thick_line(target, x0, y0, x1, y1, color, width=1):
    target.drawLine(x0, y0, x1, y1, color)
    if width >= 3:
        target.drawLine(x0 + 1, y0, x1 + 1, y1, color)
        target.drawLine(x0, y0 + 1, x1, y1 + 1, color)


def draw_cloud(target, x, y, ox):
    target.fillEllipse(x + ox + 13, y + 12, 15, 9, CLOUD)
    target.fillEllipse(x + ox + 30, y + 9, 18, 12, CLOUD)
    target.fillEllipse(x + ox + 49, y + 13, 14, 8, CLOUD)
    target.fillRoundRect(x + ox + 6, y + 12, 55, 10, 5, CLOUD)


def draw_wheel(target, cx, cy, wheel_phase, ox):
    cx += ox
    target.fillCircle(cx, cy, 31, INK)
    target.fillCircle(cx, cy, 25, WHITE)
    target.fillCircle(cx, cy, 21, ROAD)
    target.drawCircle(cx, cy, 18, TEAL)
    for i in range(8):
        dx, dy = DIRS[(i + wheel_phase) % 8]
        target.drawLine(cx, cy, cx + dx * 17, cy + dy * 17, WHITE)
    target.fillCircle(cx, cy, 4, ROAD_LINE)


def draw_bike(target, wheel_phase, ox):
    rear_x, rear_y = 91 + ox, 193
    front_x, front_y = 238 + ox, 193
    crank_x, crank_y = 157 + ox, 193
    seat_x, seat_y = 139 + ox, 151
    head_x, head_y = 211 + ox, 151

    target.fillEllipse(165 + ox, 226, 101, 8, INK)
    draw_wheel(target, rear_x, rear_y, wheel_phase, 0)
    draw_wheel(target, front_x, front_y, wheel_phase, 0)

    frame_points = (
        (rear_x, rear_y, seat_x, seat_y),
        (seat_x, seat_y, crank_x, crank_y),
        (crank_x, crank_y, rear_x, rear_y),
        (seat_x, seat_y, head_x, head_y),
        (head_x, head_y, crank_x, crank_y),
        (head_x, head_y, front_x, front_y),
    )
    for x0, y0, x1, y1 in frame_points:
        thick_line(target, x0, y0, x1, y1, INK, 5)
        thick_line(target, x0, y0, x1, y1, TEAL, 3)

    thick_line(target, seat_x - 16, seat_y - 1, seat_x + 10, seat_y - 1, INK, 5)
    target.fillRoundRect(head_x - 8, head_y - 12, 19, 8, 3, INK)
    target.fillRoundRect(head_x - 7, head_y - 11, 17, 5, 2, TEAL)
    target.drawLine(head_x, head_y - 8, 226 + ox, 137, INK)
    target.drawLine(226 + ox, 137, 232 + ox, 141, INK)

    target.fillCircle(crank_x, crank_y, 12, INK)
    target.fillCircle(crank_x, crank_y, 9, ROAD_LINE)
    target.fillCircle(crank_x, crank_y, 3, INK)

    dx, dy = DIRS[wheel_phase % 8]
    pedal_x = crank_x + dx * 22
    pedal_y = crank_y + dy * 18
    opposite_x = crank_x - dx * 22
    opposite_y = crank_y - dy * 18
    thick_line(target, crank_x, crank_y, pedal_x, pedal_y, INK, 3)
    thick_line(target, crank_x, crank_y, opposite_x, opposite_y, INK, 3)
    target.fillRoundRect(pedal_x - 6, pedal_y - 2, 13, 5, 2, ORANGE)
    target.fillRoundRect(opposite_x - 6, opposite_y - 2, 13, 5, 2, ROAD_LINE)
    return pedal_x, pedal_y


def draw_pelican(target, bob, pedal_x, pedal_y, ox):
    body_y = 132 + bob
    head_x, head_y = 191 + ox, 92 + bob

    target.fillTriangle(
        108 + ox, 122 + bob, 78 + ox, 111 + bob, 101 + ox, 141 + bob, INK)
    target.fillTriangle(
        109 + ox, 126 + bob, 86 + ox, 117 + bob, 103 + ox, 139 + bob, WHITE)

    target.fillEllipse(151 + ox, body_y, 49, 34, INK)
    target.fillEllipse(151 + ox, body_y - 1, 45, 30, WHITE)
    target.fillEllipse(160 + ox, body_y + 1, 30, 20, INK)
    target.fillEllipse(160 + ox, body_y, 27, 17, WING)
    target.drawLine(138 + ox, body_y + 3, 181 + ox, body_y - 7, MUTED)
    target.drawLine(141 + ox, body_y + 9, 178 + ox, body_y - 1, MUTED)

    thick_line(target, 171 + ox, body_y - 16, head_x - 2, head_y + 13, INK, 5)
    thick_line(
        target, 171 + ox, body_y - 16, head_x - 2, head_y + 13, WHITE, 3)
    target.fillCircle(head_x, head_y, 18, INK)
    target.fillCircle(head_x, head_y, 15, WHITE)

    target.fillTriangle(
        head_x + 9, head_y - 4,
        head_x + 65, head_y + 5,
        head_x + 14, head_y + 12,
        ORANGE,
    )
    target.fillEllipse(head_x + 41, head_y + 13, 25, 12, POUCH)
    target.drawLine(head_x + 10, head_y + 1, head_x + 60, head_y + 6, INK)
    target.fillCircle(head_x + 5, head_y - 3, 2, INK)

    scarf_y = body_y - 18
    thick_line(target, 171 + ox, scarf_y, head_y + 10, head_y + 12, RED, 5)
    gyro_wave = clamp(abs(int(imu_gz)) // 20, 0, 2)
    wave = ((phase // 2) + gyro_wave) % 3
    target.drawLine(166 + ox, scarf_y, 151 + ox, scarf_y - 2 - wave, RED)
    target.drawLine(
        151 + ox, scarf_y - 2 - wave, 136 + ox, scarf_y + 3 + wave, RED)
    target.drawLine(
        136 + ox, scarf_y + 3 + wave, 121 + ox, scarf_y - 1 + wave, RED)

    target.fillRoundRect(head_x - 10, head_y - 24, 30, 9, 4, RED)
    target.fillRoundRect(head_x - 9, head_y - 23, 27, 5, 2, ORANGE)
    target.drawLine(head_x + 18, head_y - 17, head_x + 28, head_y - 15, INK)

    if ring_started and time.ticks_diff(time.ticks_ms(), ring_started) < 1200:
        target.fillCircle(head_x + 28, head_y - 24, 4, ORANGE)
        target.drawLine(head_x + 18, head_y - 28, head_x + 12, head_y - 34, RED)
        target.drawLine(head_x + 28, head_y - 36, head_x + 28, head_y - 43, RED)
        target.drawLine(head_x + 38, head_y - 28, head_x + 44, head_y - 34, RED)

    knee_x, knee_y = 137 + ox, 166 + bob
    thick_line(target, 137 + ox, body_y + 17, knee_x, knee_y, INK, 5)
    thick_line(target, knee_x, knee_y, pedal_x, pedal_y, INK, 5)
    thick_line(target, 137 + ox, body_y + 17, knee_x, knee_y, ORANGE, 3)
    thick_line(target, knee_x, knee_y, pedal_x, pedal_y, ORANGE, 3)


def draw_background(target, frame, ox):
    motion = 1 + speed_level // 2
    gyro_boost = clamp(int(abs(imu_gz)) // 12, 0, 4)
    target.fillScreen(SKY_LOW)
    target.fillRect(0, 0, target.width(), 88, SKY_TOP)
    target.fillRect(0, 88, target.width(), 54, SKY_MID)
    target.fillCircle(270 + ox, 52, 31, SUN)
    target.fillCircle(270 + ox, 52, 23, 0xFFE49A)

    cloud_a = 232 - (frame * motion // 2) % 360
    cloud_b = 34 + (frame * motion // 3) % 300
    draw_cloud(target, cloud_a, 35, ox)
    draw_cloud(target, cloud_b, 72, ox)

    target.fillEllipse(52 + ox, 172, 108, 45, HILL)
    target.fillEllipse(182 + ox, 174, 142, 54, HILL_DARK)
    target.fillEllipse(315 + ox, 169, 106, 46, HILL)

    target.fillRect(0, 178, target.width(), 62, ROAD)
    target.fillRect(0, 178, target.width(), 3, ROAD_EDGE)
    for x in range(-38, WIDTH + 40, 42):
        dash_x = (x - frame * (4 + speed_level * 2)) % 360 + ox
        if dash_x > -28:
            target.fillRoundRect(dash_x, 204, 22, 4, 2, ROAD_LINE)

    for i in range(3 + gyro_boost):
        x = 48 + i * 55 - (frame * (2 + gyro_boost)) % 65 + ox
        target.drawLine(x, 164 - i * 8, x + 18, 164 - i * 8, MUTED)


def draw_scene_half(target, bob, wheel_phase, ox):
    lean_px = clamp(int(imu_ax * 16), -12, 12)
    imu_bob = clamp(int(-imu_ay * 4), -4, 4)
    scene_bob = bob + imu_bob
    scene_ox = ox + lean_px

    draw_background(target, phase, ox)
    pedal_x, pedal_y = draw_bike(target, wheel_phase, scene_ox)
    draw_pelican(target, scene_bob, pedal_x, pedal_y, scene_ox)

    target.setFont(M5.Display.FONTS.Montserrat18)
    target.setTextColor(INK, SKY_TOP)
    target.drawString("PELICAN EXPRESS", 12 + ox, 10)
    target.setFont(M5.Display.FONTS.Montserrat12)
    target.setTextColor(MUTED, SKY_TOP)
    target.drawString(
        "PAUSED" if paused else "DRAG ROAD / HOLD BIRD",
        13 + ox,
        31,
    )

    target.fillRoundRect(246 + ox, 10, 62, 28, 8, INK)
    target.drawRoundRect(248 + ox, 12, 58, 24, 7, WHITE)
    if paused:
        target.fillTriangle(270 + ox, 17, 270 + ox, 31, 285 + ox, 24, ORANGE)
    else:
        target.fillRect(273 + ox, 17, 4, 14, WHITE)
        target.fillRect(281 + ox, 17, 4, 14, WHITE)

    target.fillRoundRect(10, 214, 118, 18, 6, INK)
    target.setTextColor(WHITE, INK)
    target.drawString("SPEED %d/%d" % (speed_level, MAX_SPEED), 19, 216)

    target.fillRoundRect(134, 214, 176, 18, 6, INK)
    if imu_error or not imu_ready:
        target.setTextColor(ORANGE, INK)
        target.drawString(imu_error or "IMU DISABLED", 143, 216)
    else:
        target.setTextColor(TEAL, INK)
        target.drawString(
            "IMU %s X %.2f GZ %.0f" % (imu_source, imu_ax, imu_gz),
            143,
            216,
        )
    target.fillCircle(
        302,
        223,
        3,
        TEAL if speaker_ready else RED,
    )

    now = time.ticks_ms()
    if notice_text and time.ticks_diff(now, notice_until) < 0:
        target.fillRoundRect(94, 49, 132, 19, 6, INK)
        target.setTextColor(ORANGE, INK)
        target.drawString(notice_text, 106, 51)

    if was_pressed:
        target.drawCircle(touch_x, touch_y, 9, INK)
        target.drawCircle(touch_x, touch_y, 7, ORANGE)
        target.drawLine(touch_x - 12, touch_y, touch_x - 4, touch_y, ORANGE)
        target.drawLine(touch_x + 4, touch_y, touch_x + 12, touch_y, ORANGE)
        target.drawLine(touch_x, touch_y - 12, touch_x, touch_y - 4, ORANGE)
        target.drawLine(touch_x, touch_y + 4, touch_x, touch_y + 12, ORANGE)


def draw_frame():
    bob = BOB[(phase // 3) % 4]
    wheel_phase = (phase + abs(int(imu_gz)) // 10) % 8
    draw_scene_half(canvas, bob, wheel_phase, 0)
    canvas.push(0, 0)


def sample_imu(now):
    global imu_ax, imu_ay, imu_gz, imu_error, imu_source
    if not imu_ready:
        return False
    try:
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        imu_ax = imu_ax * 0.4 + accel[0] * 0.6
        imu_ay = imu_ay * 0.4 + accel[1] * 0.6
        imu_gz = imu_gz * 0.4 + gyro[2] * 0.6
        imu_source = "API"
        imu_error = ""
        return True
    except Exception as error:
        imu_error = repr(error)[:18]
        return False


def handle_touch(now):
    global paused, was_pressed, speed_level, drag_active, bell_zone_active
    global touch_x, touch_y, touch_distance, notice_text, notice_until
    global ring_started, bell_audio_until
    global speaker_ready, speaker_error

    pressed = M5.Touch.getCount() > 0
    changed = False
    if pressed:
        touch_x = M5.Touch.getX()
        touch_y = M5.Touch.getY()
        detail = M5.Touch.getDetail(0)
        touch_distance = detail[2]

        if not was_pressed:
            if 242 <= touch_x <= 313 and 7 <= touch_y <= 41:
                paused = not paused
                notice_text = "PAUSE" if paused else "RUN"
                notice_until = time.ticks_add(now, 800)
                changed = True
            elif touch_y >= 165:
                drag_active = True
                changed = True
            elif 78 <= touch_x <= 270 and 72 <= touch_y <= 178:
                bell_zone_active = True

        if drag_active:
            new_speed = clamp(touch_x * (MAX_SPEED + 1) // WIDTH, 0, MAX_SPEED)
            if new_speed != speed_level:
                speed_level = new_speed
                changed = True

        if bell_zone_active and detail[9]:
            bell_zone_active = False
            ring_started = now
            try:
                Speaker.end()
                speaker_ready = Speaker.begin()
                if speaker_ready:
                    Speaker.setVolumePercentage(0.8)
                if speaker_ready:
                    Speaker.playRaw(
                        bell_pcm,
                        AUDIO_RATE,
                        False,
                        1,
                        0,
                        True,
                    )
                    bell_audio_until = time.ticks_add(now, 160)
                    speaker_error = ""
                    notice_text = "BELL AUDIO"
                else:
                    notice_text = "MUTE"
            except Exception as error:
                speaker_ready = False
                speaker_error = repr(error)[:18]
                notice_text = ("MUTE " + speaker_error)[:18]
            notice_until = time.ticks_add(now, 1200)
            changed = True
    else:
        if was_pressed:
            changed = True
        if was_pressed and drag_active:
            notice_text = "DRAG %d px" % touch_distance
            notice_until = time.ticks_add(now, 900)
        drag_active = False
        bell_zone_active = False

    was_pressed = pressed
    return changed


print("PELICAN_MAIN_START")
M5.begin()
M5.Display.setRotation(1)
M5.Display.setBrightness(255)
print("PELICAN_BOARD", M5.getBoard())
print("PELICAN_DISPLAY", M5.Display.width(), M5.Display.height())
print("PELICAN_SPEAKER_READY", speaker_ready)
try:
    imu_ready = Imu.isEnabled()
except Exception as error:
    imu_error = repr(error)[:18]
print("PELICAN_IMU_READY", imu_ready)

canvas = M5.Display.newCanvas(WIDTH, HEIGHT, 16, True)
print("PELICAN_CANVAS_OK", canvas.width(), canvas.height())
bell_pcm = make_bell_pcm()
draw_frame()
print("PELICAN_FIRST_FRAME", phase)

last_frame_ms = time.ticks_ms()
last_imu_ms = 0
while True:
    M5.update()
    now = time.ticks_ms()
    input_changed = handle_touch(now)

    if time.ticks_diff(now, last_imu_ms) >= 120:
        sample_imu(now)
        last_imu_ms = now

    bell_audio_active = (
        bell_audio_until and time.ticks_diff(now, bell_audio_until) < 0
    )
    if (not paused and not bell_audio_active
            and time.ticks_diff(now, last_frame_ms) >= FRAME_MS):
        phase += 1 + speed_level // 2
        draw_frame()
        last_frame_ms = now
    else:
        notice_expired = (
            notice_text and time.ticks_diff(now, notice_until) >= 0
        )
        ring_expired = (
            ring_started and time.ticks_diff(now, ring_started) >= 1200
        )
        if notice_expired:
            notice_text = ""
        if ring_expired:
            ring_started = 0
        if input_changed or notice_expired or (paused and ring_expired):
            draw_frame()
    time.sleep_ms(2)
