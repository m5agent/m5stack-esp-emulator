"""MicroPython default/candidate M5UI regression through the real LVGL renderer.

Upload the four-quadrant fixture.png with this file. Set M5UI_CANDIDATE=True
only when the three hash-pinned candidate modules accompany the same package.
Results for that lane must not be assigned to the reference frozen firmware.
"""
import time
import json
import os
import M5
import m5ui

M5.begin()
M5.Display.setBrightness(255)
_candidate = globals().get("M5UI_CANDIDATE", False)
if _candidate:
    from candidate_m5ui.canvas import M5Canvas
    from candidate_m5ui.image import M5Image
    from candidate_m5ui.spinbox import M5Spinbox
else:
    M5Canvas = m5ui.M5Canvas
    M5Image = m5ui.M5Image
    M5Spinbox = m5ui.M5Spinbox


def emit(kind, **values):
    values["candidate_source_override"] = _candidate
    print("M5EMU_UI_" + kind + " " + json.dumps(values))


def settle():
    for _ in range(20):
        M5.update()
        time.sleep_ms(20)


_rotation = globals().get("M5UI_ROTATION", 0)
m5ui.init()
M5.Display.setRotation(_rotation)
try:
    page = m5ui.M5Page(bg_c=0x0B1014)
    heading = m5ui.M5Label("M5UI source correction" if _candidate else "M5UI reference firmware", x=8, y=8, text_c=0xF3F7F8, parent=page)
    canvas = M5Canvas(x=10, y=40, w=140, h=140, bg_c=0x182128, parent=page)
    canvas.draw_triangle(10, 90, 65, 10, 120, 90, bg_c=0x38B8C8)
    settle()
    points = [[p.x, p.y] for p in canvas._triangle_dsc.p]
    color = canvas.get_px_color(65, 60)
    emit("RESULT", api_target="m5ui.M5Canvas", method="draw_triangle", status="STATE_PASS" if color == 0x38B8C8 and points == [[10, 90], [65, 10], [120, 90]] else "FAIL", native_points=points, pixel_color=color, oracle="native descriptor vertices and canvas pixel")
    emit("FRAME_ORACLE", method="draw_triangle", oracle={"kind": "pixels", "points": [[75, 100, 0x38B8C8]]}, tolerance=8)
    image = M5Image(os.getcwd() + "/fixture.png", x=200, y=55, parent=page)
    try:
        image.set_scale(1.5)
        sx, sy = image.get_scale_x(), image.get_scale_y()
        emit("RESULT", api_target="m5ui.M5Image", method="set_scale", status="STATE_PASS" if sx == 384 and sy == 384 else "FAIL", native_scale=[sx, sy], oracle="native 8.8 scale readback")
    except Exception as error:
        emit("RESULT", api_target="m5ui.M5Image", method="set_scale", status="FAIL", error=repr(error))
    emit("FRAME_ORACLE", method="set_scale", oracle={"kind": "pixels", "points": [[202, 57, 0xFF0000], [221, 57, 0x00FF00], [202, 76, 0x0000FF], [221, 76, 0xFFFF00]]}, tolerance=8)
    spin = M5Spinbox(x=165, y=125, w=150, h=60, value=20, min_value=0, max_value=100, parent=page)
    spin.set_step(5)
    step = spin._spinbox.get_step()
    spin._spinbox.increment()
    value = spin.get_value()
    emit("RESULT", api_target="m5ui.M5Spinbox", method="set_step", status="STATE_PASS" if step == 5 and value == 25 else "FAIL", native_step=step, value_after_increment=value, oracle="native spinbox increments by requested integer step")
    spin.set_digit_format(4, 2)
    spin.set_range(0, 50)
    spin.set_value(12.5)
    spin.set_step(0.1)
    spin._spinbox.increment()
    value = spin.get_value()
    emit("RESULT", api_target="m5ui.M5Spinbox", method="set_step", argument_domain="decimal", status="STATE_PASS" if abs(value - 12.6) < 0.001 else "FAIL", value_after_increment=value)
    emit("SCREEN_LOAD", status="BEGIN")
    page.screen_load()
    emit("SCREEN_LOAD", status="DONE")
    settle()
    emit("READY", status="AWAITING_FRAME", scope="three explicit M5UI source corrections")
    while True:
        M5.update()
        time.sleep_ms(20)
finally:
    m5ui.deinit()
