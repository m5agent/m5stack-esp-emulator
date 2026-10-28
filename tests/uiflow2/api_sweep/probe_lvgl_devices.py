"""Owned logical LVGL display/input API oracles, independent of board wiring.

The flush callback checks actual RGB565 draw bytes. Input samples intentionally
come from an owned LVGL read callback: this is logical LVGL state evidence,
not M5.Touch/controller/hardware input validation.
"""
import json


def check(target, method, action, oracle, description):
    try:
        value = action()
        ok = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target if target else "lvgl", "method": method,
            "status": "STATE_PASS" if ok else "FAIL", "oracle": description,
            "value": value if isinstance(value, (bool, int, float, str, list, tuple)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target if target else "lvgl", "method": method,
            "status": "FAIL", "oracle": description, "error": repr(error)}))


def display_tests(lv):
    d = check("", "display_create", lambda: lv.display_create(16, 12), lambda v: (v.get_horizontal_resolution(), v.get_vertical_resolution()) == (16, 12), "actual logical display constructor has the requested dimensions")
    other = lv.display_create(7, 9)
    d.set_user_data({"nonce": "DISPLAY"})
    check("display_t", "set_user_data", lambda: d.get_user_data().__cast__()["nonce"], lambda v: v == "DISPLAY", "owned callback dictionary nonce")
    check("display_t", "get_user_data", lambda: d.get_user_data().__cast__()["nonce"], lambda v: v == "DISPLAY", "native userdata points to retained dictionary")
    check("display_t", "set_driver_data", lambda: (d.set_driver_data({"nonce": "DRIVER"}), d.get_driver_data().__cast__()["nonce"])[1], lambda v: v == "DRIVER", "independent driver-data dictionary")
    check("display_t", "get_driver_data", lambda: d.get_driver_data().__cast__()["nonce"], lambda v: v == "DRIVER", "driver dictionary nonce")
    check("display_t", "set_default", lambda: (d.set_default(), lv.display_get_default().get_user_data().__cast__()["nonce"])[1], lambda v: v == "DISPLAY", "default display resolves exact dictionary nonce")
    check("", "display_get_default", lambda: lv.display_get_default().get_user_data().__cast__()["nonce"], lambda v: v == "DISPLAY", "module getter resolves exact owned default display dictionary")
    check("display_t", "get_next", lambda: other.get_next().get_user_data().__cast__()["nonce"], lambda v: v == "DISPLAY", "display list links second owned display to first")
    check("display_t", "set_resolution", lambda: (d.set_resolution(20, 16), d.get_horizontal_resolution(), d.get_vertical_resolution())[1:], lambda v: v == (20, 16), "resolution changes active native screen dimensions")
    check("display_t", "get_horizontal_resolution", d.get_horizontal_resolution, lambda v: v == 20, "logical width")
    check("display_t", "get_vertical_resolution", d.get_vertical_resolution, lambda v: v == 16, "logical height")
    check("display_t", "set_physical_resolution", lambda: (d.set_physical_resolution(40, 32), d.get_physical_horizontal_resolution(), d.get_physical_vertical_resolution())[1:], lambda v: v == (40, 32), "physical resolution metadata roundtrip; no physical measurement")
    check("display_t", "get_physical_horizontal_resolution", d.get_physical_horizontal_resolution, lambda v: v == 40, "physical width metadata")
    check("display_t", "get_physical_vertical_resolution", d.get_physical_vertical_resolution, lambda v: v == 32, "physical height metadata")
    check("display_t", "set_offset", lambda: (d.set_offset(3, 4), d.get_offset_x(), d.get_offset_y())[1:], lambda v: v == (3, 4), "offset pair retained")
    check("display_t", "get_offset_x", d.get_offset_x, lambda v: v == 3, "horizontal offset")
    check("display_t", "get_offset_y", d.get_offset_y, lambda v: v == 4, "vertical offset")
    check("display_t", "set_rotation", lambda: (d.set_rotation(lv.DISPLAY_ROTATION._90), d.get_rotation(), d.get_horizontal_resolution(), d.get_vertical_resolution())[1:], lambda v: v == (lv.DISPLAY_ROTATION._90, 16, 20), "90-degree rotation exchanges logical dimensions")
    check("display_t", "get_rotation", d.get_rotation, lambda v: v == lv.DISPLAY_ROTATION._90, "rotation enum")
    area = lv.area_t({"x1": 1, "y1": 2, "x2": 3, "y2": 5})
    check("display_t", "rotate_area", lambda: (d.rotate_area(area), (area.x1, area.y1, area.x2, area.y2))[1], lambda v: v == (2, 12, 5, 14), "independent 90-degree rectangle transform on original 20 by 16 display")
    d.set_rotation(lv.DISPLAY_ROTATION._0)
    d.set_offset(0, 0)
    d.set_resolution(16, 12)
    check("display_t", "set_dpi", lambda: (d.set_dpi(160), d.get_dpi())[1], lambda v: v == 160, "DPI metadata roundtrip")
    check("display_t", "get_dpi", d.get_dpi, lambda v: v == 160, "DPI getter")
    check("display_t", "dpx", lambda: d.dpx(37), lambda v: v == 37, "160-DPI reference keeps logical pixels unchanged")
    check("display_t", "set_color_format", lambda: (d.set_color_format(lv.COLOR_FORMAT.RGB565), d.get_color_format())[1], lambda v: v == lv.COLOR_FORMAT.RGB565, "RGB565 draw format")
    check("display_t", "get_color_format", d.get_color_format, lambda v: v == lv.COLOR_FORMAT.RGB565, "format getter")
    check("display_t", "set_tile_cnt", lambda: (d.set_tile_cnt(2), d.get_tile_cnt())[1], lambda v: v == 2, "render tile count roundtrip")
    check("display_t", "get_tile_cnt", d.get_tile_cnt, lambda v: v == 2, "tile-count getter")
    check("display_t", "set_antialiasing", lambda: (d.set_antialiasing(False), d.get_antialiasing())[1], lambda v: v is False, "disable antialiasing")
    check("display_t", "get_antialiasing", d.get_antialiasing, lambda v: v is False, "antialiasing getter")
    buf1, buf2 = bytearray(384), bytearray(384)
    check("display_t", "set_buffers", lambda: (d.set_buffers(buf1, None, 384, lv.DISPLAY_RENDER_MODE.PARTIAL), d.get_draw_buf_size(), d.is_double_buffered())[1:], lambda v: v == (384, False), "one actual owned RGB565 draw buffer")
    check("display_t", "set_buffers_with_stride", lambda: (d.set_buffers_with_stride(buf1, buf2, 384, 32, lv.DISPLAY_RENDER_MODE.PARTIAL), d.get_buf_active().header.stride, d.is_double_buffered())[1:], lambda v: v == (32, True), "explicit 32-byte stride and two owned buffers")
    first, second = lv.draw_buf_t(), lv.draw_buf_t()
    first.init(16, 12, lv.COLOR_FORMAT.RGB565, 32, buf1, 384)
    second.init(16, 12, lv.COLOR_FORMAT.RGB565, 32, buf2, 384)
    check("display_t", "set_draw_buffers", lambda: (d.set_draw_buffers(first, second), d.get_buf_active().header.w, d.get_buf_active().header.h)[1:], lambda v: v == (16, 12), "owned draw-buffer structs retain dimensions")
    check("display_t", "get_buf_active", lambda: (d.get_buf_active().data_size, d.get_buf_active().header.stride), lambda v: v == (384, 32), "active real draw-buffer metadata")
    check("display_t", "get_draw_buf_size", d.get_draw_buf_size, lambda v: v == 384, "exact allocated byte count")
    check("display_t", "get_invalidated_draw_buf_size", lambda: d.get_invalidated_draw_buf_size(8, 3), lambda v: v == 48, "eight RGB565 pixels by three rows")
    check("display_t", "is_double_buffered", d.is_double_buffered, bool, "two native buffer pointers present")
    check("display_t", "set_render_mode", lambda: (d.set_render_mode(lv.DISPLAY_RENDER_MODE.FULL), d.get_invalidated_draw_buf_size(1, 1))[1], lambda v: v == 384, "full mode expands small invalidation to full-frame byte size")
    d.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
    screen = d.get_screen_active()
    check("display_t", "get_screen_active", lambda: (screen.get_width(), screen.get_height()), lambda v: v == (16, 12), "active logical screen follows display resolution")
    check("display_t", "get_screen_prev", lambda: d.get_screen_prev() is None, bool, "fresh display has no previous screen")
    for method in ("get_layer_top", "get_layer_sys", "get_layer_bottom"):
        check("display_t", method, lambda method=method: (getattr(d, method)().get_width(), getattr(d, method)().get_height()), lambda v: v == (16, 12), "native display layer spans logical screen")
    theme = lv.theme_t()
    theme.user_data = {"nonce": "THEME"}
    check("display_t", "set_theme", lambda: (d.set_theme(theme), d.get_theme().user_data.__cast__()["nonce"])[1], lambda v: v == "THEME", "owned theme pointer roundtrip through userdata nonce")
    check("display_t", "get_theme", lambda: d.get_theme().user_data.__cast__()["nonce"], lambda v: v == "THEME", "theme getter nonce")
    event_tests(lv, d, "display_t", "delete_event")
    lv.tick_inc(43)
    check("display_t", "get_inactive_time", d.get_inactive_time, lambda v: v >= 43, "logical tick advances inactivity")
    check("display_t", "trigger_activity", lambda: (d.trigger_activity(), d.get_inactive_time())[1], lambda v: v == 0, "activity resets inactivity clock")
    check("display_t", "enable_invalidation", lambda: (d.enable_invalidation(False), d.is_invalidation_enabled())[1], lambda v: v is False, "explicit invalidation disable")
    check("display_t", "is_invalidation_enabled", d.is_invalidation_enabled, lambda v: v is False, "disabled predicate")
    d.enable_invalidation(True)
    timer = d.get_refr_timer()
    check("display_t", "get_refr_timer", lambda: timer is not None and timer.get_paused() is False, bool, "created display owns active refresh timer")
    captured, waits = [], []
    def flush(display, region, pixels):
        count = region.get_width() * region.get_height()
        data = bytes(pixels.__dereference__(count * 2))
        captured.append((region.x1, region.y1, region.x2, region.y2, count, data == b'\x00\xf8' * count, display.flush_is_last()))
        # Wait callback deliberately completes this pending logical transfer.
    def wait(display):
        waits.append(display.flushing)
        display.flush_ready()
    d.set_flush_cb(flush)
    d.set_flush_wait_cb(wait)
    screen.set_style_bg_color(lv.color_hex(0xff0000), 0)
    screen.set_style_bg_opa(lv.OPA.COVER, 0)
    screen.invalidate()
    lv.refr_now(d)
    # Force a second frame: it waits for the pending first frame then redraws.
    screen.invalidate()
    lv.refr_now(d)
    check("display_t", "set_flush_cb", lambda: captured, lambda v: len(v) >= 2 and all(row[5] for row in v), "actual logical rendering emits exact red RGB565 bytes")
    check("display_t", "set_flush_wait_cb", lambda: waits, lambda v: len(v) >= 1 and all(v), "pending logical transfer invokes actual wait callback")
    check("display_t", "flush_is_last", lambda: [row[6] for row in captured], lambda v: bool(v) and v[-1] is True, "last flush segment marker sampled inside callback")
    check("display_t", "flush_ready", lambda: (d.flush_ready(), d.flushing)[1], lambda v: v == 0, "completion clears pending native flush flag")
    check("display_t", "draw_dispatch_layer", lambda: d.draw_dispatch_layer(d.layer_head), lambda v: v is False, "finished render layer has no remaining dispatchable task")
    check("display_t", "delete_refr_timer", lambda: (d.delete_refr_timer(), d.get_refr_timer() is None)[1], bool, "refresh timer removed from owned display")
    other.delete()
    return d, (buf1, buf2, first, second, theme, captured, waits)


def event_tests(lv, obj, target, remove_method):
    data, calls = {"nonce": target}, []
    def callback(event):
        calls.append((event.get_code(), event.get_user_data().__cast__()["nonce"]))
    baseline = obj.get_event_count()
    check(target, "add_event_cb", lambda: (obj.add_event_cb(callback, lv.EVENT.VALUE_CHANGED, data), obj.get_event_count())[1], lambda v: v == baseline + 1, "event descriptor actually added")
    check(target, "get_event_count", obj.get_event_count, lambda v: v == baseline + 1, "one additional native descriptor")
    check(target, "get_event_dsc", lambda: obj.get_event_dsc(baseline).get_user_data().__cast__()["nonce"], lambda v: v == target, "descriptor resolves actual dictionary nonce")
    check(target, "send_event", lambda: (obj.send_event(lv.EVENT.VALUE_CHANGED, None), list(calls))[1], lambda v: v == [(lv.EVENT.VALUE_CHANGED, target)], "dispatch invokes registered Python callback")
    check(target, remove_method, lambda: (getattr(obj, remove_method)(baseline), obj.get_event_count()), lambda v: v == (True, baseline), "indexed event removal restores baseline")
    obj.add_event_cb(callback, lv.EVENT.VALUE_CHANGED, data)
    check(target, "remove_event_cb_with_user_data", lambda: (obj.remove_event_cb_with_user_data(callback, data), obj.get_event_count()), lambda v: v == (1, baseline), "callback-plus-dictionary matching removes descriptor")


def input_tests(lv, display):
    p = check("", "indev_create", lv.indev_create, lambda v: v.get_type() == 0, "actual logical input constructor starts with native NONE type")
    p.set_user_data({"nonce": "POINTER"})
    check("indev_t", "set_user_data", lambda: p.get_user_data().__cast__()["nonce"], lambda v: v == "POINTER", "owned pointer callback dictionary")
    check("indev_t", "get_user_data", lambda: p.get_user_data().__cast__()["nonce"], lambda v: v == "POINTER", "pointer dictionary nonce")
    check("indev_t", "set_driver_data", lambda: (p.set_driver_data({"nonce": "INPUT_DRIVER"}), p.get_driver_data().__cast__()["nonce"])[1], lambda v: v == "INPUT_DRIVER", "separate native driver dictionary")
    check("indev_t", "get_driver_data", lambda: p.get_driver_data().__cast__()["nonce"], lambda v: v == "INPUT_DRIVER", "input driver nonce")
    check("indev_t", "set_type", lambda: (p.set_type(lv.INDEV_TYPE.POINTER), p.get_type())[1], lambda v: v == lv.INDEV_TYPE.POINTER, "logical pointer type")
    check("indev_t", "get_type", p.get_type, lambda v: v == lv.INDEV_TYPE.POINTER, "input type getter")
    check("indev_t", "set_display", lambda: (p.set_display(display), p.get_display().get_user_data().__cast__()["nonce"])[1], lambda v: v == "DISPLAY", "input binds owned logical display")
    check("indev_t", "get_display", lambda: p.get_display().get_user_data().__cast__()["nonce"], lambda v: v == "DISPLAY", "display binding nonce")
    for method, field, value in (("set_long_press_time", "long_press_time", 321), ("set_long_press_repeat_time", "long_press_repeat_time", 123), ("set_scroll_limit", "scroll_limit", 3), ("set_scroll_throw", "scroll_throw", 20)):
        check("indev_t", method, lambda method=method, field=field, value=value: (getattr(p, method)(value), getattr(p, field))[1], lambda v, value=value: v == value, "setter updates native input configuration field")
    check("indev_t", "set_mode", lambda: (p.set_mode(lv.INDEV_MODE.EVENT), p.get_mode())[1], lambda v: v == lv.INDEV_MODE.EVENT, "event-driven read mode")
    check("indev_t", "get_mode", p.get_mode, lambda v: v == lv.INDEV_MODE.EVENT, "mode getter")
    calls, sample = [], {"x": 4, "y": 5, "pressed": False}
    def read(device, data):
        assert device.get_user_data().__cast__()["nonce"] == "POINTER"
        data.point.x = sample["x"]
        data.point.y = sample["y"]
        data.state = lv.INDEV_STATE.PRESSED if sample["pressed"] else lv.INDEV_STATE.RELEASED
        calls.append((sample["x"], sample["y"], sample["pressed"]))
    p.set_read_cb(read)
    sample["pressed"] = True
    p.read()
    check("indev_t", "set_read_cb", lambda: list(calls), lambda v: v == [(4, 5, True)], "registered callback supplies actual logical pointer sample")
    def invoke_read_getter():
        item = lv.indev_data_t()
        p.get_read_cb()(p, item)
        return item.point.x, item.point.y, item.state
    check("indev_t", "get_read_cb", invoke_read_getter, lambda v: v == (4, 5, lv.INDEV_STATE.PRESSED), "returned native callback wrapper invokes original Python read and populates output")
    check("indev_t", "get_state", p.get_state, lambda v: v == lv.INDEV_STATE.PRESSED, "native input state reflects pressed callback sample")
    point = lv.point_t()
    check("indev_t", "get_point", lambda: (p.get_point(point), (point.x, point.y))[1], lambda v: v == (4, 5), "logical point propagated through native read pipeline")
    sample.update(x=8, y=6)
    check("indev_t", "read", lambda: (p.read(), len(calls))[1], lambda v: v == 3, "explicit read invokes callback again after getter call")
    check("indev_t", "get_vect", lambda: (p.get_vect(point), (point.x, point.y))[1], lambda v: v == (4, 1), "successive logical samples produce independent motion vector")
    check("indev_t", "get_press_moved", p.get_press_moved, bool, "motion exceeds configured press displacement")
    cursor = lv.obj(display.get_screen_active())
    cursor.set_size(2, 2)
    check("indev_t", "set_cursor", lambda: (p.set_cursor(cursor), p.get_cursor() == cursor)[1], bool, "cursor object assigned and parented to system layer")
    check("indev_t", "get_cursor", lambda: p.get_cursor() == cursor, bool, "cursor object identity")
    def disabled_read():
        p.enable(False)
        before = len(calls)
        p.read()
        return before, len(calls)
    check("indev_t", "enable", disabled_read, lambda v: v == (3, 3), "disabled input skips callback")
    p.enable(True)
    check("indev_t", "stop_processing", lambda: (p.stop_processing(), p.stop_processing_query)[1], lambda v: v == 1, "explicit native stop-processing flag")
    lv.tick_inc(50)
    check("indev_t", "reset_long_press", lambda: (p.reset_long_press(), p.long_pr_sent, p.pr_timestamp, p.longpr_rep_timestamp)[1:], lambda v: v[0] == 0 and v[1] == v[2] and v[1] >= 50, "long-press clock reset to current logical tick")
    check("indev_t", "wait_release", lambda: (p.wait_release(), p.wait_until_release)[1], lambda v: v == 1, "wait-release state set")
    sample["pressed"] = False
    p.read()
    check("indev_t", "reset", lambda: (p.reset(None), p.reset_query)[1], lambda v: v == 1, "reset marks native input processing state for reset")
    p.read()
    check("indev_t", "get_gesture_dir", p.get_gesture_dir, lambda v: v == lv.DIR.NONE, "short logical movement has no gesture direction")
    check("indev_t", "get_scroll_dir", p.get_scroll_dir, lambda v: v == lv.DIR.NONE, "non-scrollable screen has no active scroll direction")
    check("indev_t", "get_scroll_obj", lambda: p.get_scroll_obj() is None, bool, "no active scroll target after release/reset")
    check("indev_t", "scroll_handler", lambda: (p.scroll_handler(), p.get_scroll_obj() is None)[1], bool, "zero-vector scroll handler preserves no target")
    check("indev_t", "scroll_throw_handler", lambda: (p.scroll_throw_handler(), p.get_scroll_obj() is None)[1], bool, "no-target throw handler leaves no scroll object")
    check("indev_t", "scroll_throw_predict", lambda: p.scroll_throw_predict(lv.DIR.VER), lambda v: v == 0, "released stationary input predicts no inertial displacement")
    check("indev_t", "find_scroll_obj", lambda: p.find_scroll_obj() is None, bool, "stationary input has no scroll candidate")
    # A fresh independent click proves the short-click counter path.
    sample.update(x=8, y=7, pressed=True)
    p.read()
    sample["pressed"] = False
    p.read()
    check("indev_t", "get_short_click_streak", p.get_short_click_streak, lambda v: v == 1, "one complete logical press/release increments click streak")
    check("indev_t", "get_read_timer", lambda: p.get_read_timer() is not None, bool, "created input owns read timer")
    event_tests(lv, p, "indev_t", "remove_event")
    keypad = lv.indev_create()
    keypad.set_type(lv.INDEV_TYPE.KEYPAD)
    keypad.set_display(display)
    keypad.set_mode(lv.INDEV_MODE.EVENT)
    group = check("", "group_create", lv.group_create, lambda v: v.get_obj_count() == 0, "actual native focus-group constructor starts empty")
    original_group = lv.group_get_default()
    group.set_default()
    check("", "group_get_default", lambda: lv.group_get_default() == group, bool, "module default-group getter returns exact owned group")
    if original_group is not None:
        original_group.set_default()
    a, b = lv.button(display.get_screen_active()), lv.button(display.get_screen_active())
    group.add_obj(a)
    group.add_obj(b)
    check("indev_t", "set_group", lambda: (keypad.set_group(group), keypad.get_group() == group)[1], bool, "keypad bound to owned focus group")
    check("indev_t", "get_group", lambda: keypad.get_group() == group, bool, "focus group identity")
    def key_read(device, data):
        data.key = lv.KEY.NEXT
        data.state = lv.INDEV_STATE.PRESSED
    keypad.set_read_cb(key_read)
    keypad.read()
    check("indev_t", "get_key", keypad.get_key, lambda v: v == lv.KEY.NEXT, "native keypad stores supplied NEXT event")
    check("indev_t", "get_next", lambda: keypad.get_next().get_user_data().__cast__()["nonce"], lambda v: v == "POINTER", "input registry links most recent device to prior owned pointer")
    button = lv.indev_create()
    button.set_type(lv.INDEV_TYPE.BUTTON)
    button.set_display(display)
    button.set_mode(lv.INDEV_MODE.EVENT)
    locations = [lv.point_t({"x": 2, "y": 3}), lv.point_t({"x": 11, "y": 9})]
    button.set_button_points(locations)
    def button_read(device, data):
        data.btn_id = 1
        data.state = lv.INDEV_STATE.PRESSED
    button.set_read_cb(button_read)
    button.read()
    check("indev_t", "set_button_points", lambda: (button.get_point(point), (point.x, point.y))[1], lambda v: v == (11, 9), "button ID maps through actual native point table")
    button.delete()
    keypad.delete()
    group.delete()
    a.delete()
    b.delete()
    sentinel = lv.indev_create()
    sentinel.enable(False)
    check("indev_t", "delete", lambda: (p.delete(), sentinel.get_next() is None)[1], bool, "deleting pointer removes it from live sentinel's registry link")
    sentinel.delete()
    cursor.delete()


def run():
    try:
        import lvgl as lv
    except ImportError as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": "logical_devices", "status": "UNAVAILABLE_ON_DEVICE", "oracle": repr(error)}))
        return
    lv.init()
    display = None
    try:
        display, owned = display_tests(lv)
        input_tests(lv, display)
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl.display_t", "method": "fixture", "status": "FAIL", "oracle": "owned logical display/input setup", "error": repr(error)}))
    if display is not None:
        sentinel = lv.display_create(1, 1)
        check("display_t", "delete", lambda: (display.delete(), sentinel.get_next() is None)[1], bool, "deleting owned display removes it from live sentinel's registry link")
        sentinel.delete()
    lv.deinit()


run()
print("LVGL_DEVICES_DONE")
