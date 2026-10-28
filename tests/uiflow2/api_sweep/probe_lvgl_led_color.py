"""Observe the native LED's private color through its actual rendered pixels."""
import json
import time
import M5
import m5ui
import lvgl as lv


try:
    M5.begin()
    m5ui.init()
    screen = lv.screen_active()
    screen.set_style_bg_color(lv.color_black(), 0)
    led = lv.led(screen)
    led.set_pos(20, 20)
    led.set_size(40, 40)
    led.set_style_radius(0, 0)
    led.set_style_border_width(0, 0)
    led.set_style_shadow_width(0, 0)
    led.set_style_bg_color(lv.color_white(), 0)
    led.set_style_bg_opa(lv.OPA.COVER, 0)
    led.set_style_bg_grad_dir(lv.GRAD_DIR.NONE, 0)
    led.set_color(lv.color_hex(0x38B8C8))
    led.on()
    stop = time.ticks_add(time.ticks_ms(), 300)
    while time.ticks_diff(stop, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "lvgl.led", "method": "set_color", "status": "CALL_OK",
        "oracle": "native setter called; its private color is checked by the separate framebuffer oracle",
    }))
    print("M5EMU_UI_FRAME_ORACLE " + json.dumps({
        "api_target": "lvgl.led", "method": "set_color", "tolerance": 8,
        "oracle": {"kind": "pixels", "points": [[30, 30, 0x38B8C8], [40, 40, 0x38B8C8], [50, 50, 0x38B8C8]]},
    }))
except Exception as error:
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "lvgl.led", "method": "set_color", "status": "FAIL",
        "error": repr(error), "oracle": "finite native LED color fixture must complete",
    }))
print("LVGL_LED_COLOR_DONE")
