"""Observe real LVGL state and timer delivery around stock M5UI init/deinit."""
import time
import json
import M5
import m5ui
import m5ui.port as port
import lvgl as lv

M5.begin()
pulse = [0]


def emit(method, **data):
    data.update(method=method, api_target="m5ui")
    print("M5EMU_UI_RESULT " + json.dumps(data))


def on_tick(timer):
    pulse[0] += 1


def settle():
    for _ in range(20):
        M5.update()
        time.sleep_ms(20)


for cycle in range(2):
    m5ui.init()
    page = m5ui.M5Page(bg_c=0x0B1014)
    label = m5ui.M5Label("Lifecycle cycle " + str(cycle), x=30, y=80, parent=page)
    page.screen_load()
    pulse[0] = 0
    timer = lv.timer_create(on_tick, 30, None)
    settle()
    loop = port.event_loop._instance
    state = {"cycle": cycle, "native_initialized": lv.is_initialized(),
             "instance_initialized": loop is not None and loop._initialized,
             "class_helper_initialized": port.event_loop.is_initialized(),
             "callback_count": pulse[0],
             "display_size": [lv.display_get_default().get_horizontal_resolution(),
                              lv.display_get_default().get_vertical_resolution()]}
    ok = state["native_initialized"] and state["instance_initialized"] and pulse[0] > 0 and state["display_size"] == [320, 240]
    emit("init", status="STATE_PASS" if ok else "FAIL", oracle="native LVGL/display and actual timer delivery", **state)
    m5ui.deinit()
    before = pulse[0]
    settle()
    state = {"cycle": cycle, "native_initialized": lv.is_initialized(),
             "instance_released": port.event_loop._instance is None,
             "callback_count_at_return": before, "callback_count_after_wait": pulse[0]}
    ok = not state["native_initialized"] and state["instance_released"] and before == pulse[0]
    emit("deinit", status="STATE_PASS" if ok else "FAIL", oracle="native LVGL deinitialized and timer delivery stopped", **state)

m5ui.init()
try:
    page = m5ui.M5Page(bg_c=0x0B1014)
    label = m5ui.M5Label("Lifecycle restored", x=30, y=80, parent=page)
    page.screen_load()
    settle()
    print("M5UI_LIFECYCLE_OBSERVED_DONE")
    while True:
        M5.update()
        time.sleep_ms(20)
finally:
    m5ui.deinit()
