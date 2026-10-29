import json
import time

import M5
import lvgl as lv
import m5ui
import m5ui.port as m5ui_port
import candidate_lvgl_loop
import sys

# Explicit candidate binding: original M5UI display/touch initialization stays in use.
sys.modules["_m5emu_lvgl_loop_candidate"] = candidate_lvgl_loop
m5ui_port.event_loop = candidate_lvgl_loop.event_loop
from unit import PIRUnit


FIXTURE = "cores3-wasm-lvgl-wallclock-v1"
clicks = 0
sequence = 0
previous_pir = None
page = None
count_label = None
pir_label = None
button = None
pir = None


def emit(kind, **fields):
    global sequence
    sequence += 1
    fields["fixture"] = FIXTURE
    fields["kind"] = kind
    fields["seq"] = sequence
    print("CORES3_WASM " + json.dumps(fields))


def button_event(event):
    global clicks
    if event.code == lv.EVENT.PRESSED:
        emit("touch_pressed", clicks=clicks)
    elif event.code == lv.EVENT.RELEASED:
        emit("touch_released", clicks=clicks)
    elif event.code == lv.EVENT.CLICKED:
        clicks += 1
        count_label.set_text("Clicks: " + str(clicks))
        button.set_btn_text("Count " + str(clicks))
        emit("touch_clicked", clicks=clicks)


emit("begin")
M5.begin()
M5.Display.setRotation(1)
M5.Display.setBrightness(255)
emit("m5_ready", board=M5.getBoard(), width=M5.Display.width(), height=M5.Display.height())
m5ui.init()
emit("lvgl_ready", scheduler_candidate=candidate_lvgl_loop.CANDIDATE)

page = m5ui.M5Page(bg_c=0x102030)
title = m5ui.M5Label("CoreS3 WASM / LVGL", x=20, y=18, text_c=0xFFFFFF,
    font=lv.font_montserrat_18, parent=page)
count_label = m5ui.M5Label("Clicks: 0", x=20, y=60, text_c=0xFFFFFF,
    font=lv.font_montserrat_24, parent=page)
pir_label = m5ui.M5Label("PIR: pending", x=20, y=100, text_c=0xFFFFFF,
    font=lv.font_montserrat_18, parent=page)
button = m5ui.M5Button(text="Count 0", x=40, y=152, w=240, h=64,
    bg_c=0x2176FF, text_c=0xFFFFFF, font=lv.font_montserrat_24, parent=page)
button.add_event_cb(button_event, lv.EVENT.ALL, None)

pir = PIRUnit((1, 2))
page.screen_load()
emit("ready", width=M5.Display.width(), height=M5.Display.height(), white_gpio=1,
    yellow_gpio=2, button_center=[160, 184])
loop = candidate_lvgl_loop.event_loop.get_instance()
animation_label = m5ui.M5Label("*", x=20, y=130, text_c=0xFFCC44,
    font=lv.font_montserrat_18, parent=page)
clock_samples = 0


def elapsed_animation(timer):
    global clock_samples
    clock_samples += 1
    elapsed = time.ticks_diff(time.ticks_ms(), loop.started_ms)
    animation_label.set_x(20 + (elapsed // 10) % 260)


animation_timer = lv.timer_create(elapsed_animation, 100, None)
last_heartbeat = time.ticks_ms()
while True:
    M5.update()
    motion = int(pir.get_status())
    if motion != previous_pir:
        pir_label.set_text("PIR: MOTION" if motion else "PIR: CLEAR")
        emit("pir", value=motion, clicks=clicks)
        previous_pir = motion
    now = time.ticks_ms()
    if time.ticks_diff(now, last_heartbeat) >= 2000:
        emit("heartbeat", guest_ms=now, clicks=clicks, pir=motion,
            lv_ms=lv.tick_get(), tick_total=loop.tick_total,
            elapsed_ms=time.ticks_diff(now, loop.started_ms),
            timer_callbacks=loop.timer_callbacks, task_runs=loop.task_runs,
            scheduled=loop.scheduled, scheduler_errors=loop.exceptions,
            nesting_skips=loop.nesting_skips, animation_samples=clock_samples,
            scheduler_candidate=candidate_lvgl_loop.CANDIDATE)
        last_heartbeat = now
    time.sleep_ms(25)
