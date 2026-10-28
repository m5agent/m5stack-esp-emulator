"""Owned logical LVGL display, theme, snapshot and typed event API fixtures."""
import json
import struct
import uctypes


def check(target, method, action, oracle, reason):
    try:
        value = action()
        status = "STATE_PASS" if oracle(value) else "FAIL"
        row = dict(api_target="lvgl" + ("." + target if target else ""), method=method, status=status, oracle=reason)
        row["value"] = value if isinstance(value, (int, bool, str, tuple, list)) or value is None else repr(value)
    except Exception as error:
        row = dict(api_target="lvgl" + ("." + target if target else ""), method=method, status="FAIL", oracle=reason, error=repr(error))
    print("M5EMU_UI_RESULT " + json.dumps(row))
    return row.get("value")


def events(lv, obj):
    obj.set_width(17)
    obj.update_layout()
    event = lv.event_t({"original_target": obj, "current_target": obj, "code": lv.EVENT.VALUE_CHANGED})
    for method in ("get_target", "get_current_target", "get_target_obj", "get_current_target_obj"):
        def target_value(method=method):
            target = getattr(event, method)()
            if method in ("get_target", "get_current_target"):
                target = lv.obj.__cast__(target)
            return target.get_width()
        check("event_t", method, target_value, lambda v: v == 17, "native event returns actual retained object pointer")
    area = lv.area_t({"x1": 2, "y1": 3, "x2": 7, "y2": 11})
    for code, method in ((lv.EVENT.INVALIDATE_AREA, "get_invalidated_area"), (lv.EVENT.SIZE_CHANGED, "get_old_size")):
        event.code, event.param = code, area
        check("event_t", method, lambda method=method: getattr(event, method)().get_size(), lambda v: v == 54, "event-specific area parameter preserves exact rectangle")
    indev = lv.indev_create()
    indev.set_type(lv.INDEV_TYPE.KEYPAD)
    event.code, event.param = lv.EVENT.PRESSED, indev
    check("event_t", "get_indev", lambda: event.get_indev().get_type(), lambda v: v == lv.INDEV_TYPE.KEYPAD, "input event parameter resolves actual logical keypad")
    layer = lv.layer_t({"opa": 123})
    event.code, event.param = lv.EVENT.DRAW_MAIN, layer
    check("event_t", "get_layer", lambda: event.get_layer().opa, lambda v: v == 123, "draw event returns owned native layer with nonce opacity")
    anim = lv.anim_t()
    anim.init()
    anim.set_duration(321)
    event.code, event.param = lv.EVENT.SCROLL_BEGIN, anim
    check("event_t", "get_scroll_anim", lambda: event.get_scroll_anim().duration, lambda v: v == 321, "scroll-begin event returns actual native animation")
    extent = bytearray(struct.pack("i", 4))
    event.code, event.param = lv.EVENT.REFR_EXT_DRAW_SIZE, extent
    check("event_t", "set_ext_draw_size", lambda: (event.set_ext_draw_size(9), struct.unpack("i", extent)[0])[1], lambda v: v == 9, "extension update writes maximum into caller-owned integer")
    point = lv.point_t({"x": 13, "y": 17})
    event.code, event.param = lv.EVENT.GET_SELF_SIZE, point
    check("event_t", "get_self_size_info", lambda: (event.get_self_size_info().x, event.get_self_size_info().y), lambda v: v == (13, 17), "self-size event returns retained point")
    info = lv.hit_test_info_t({"point": point, "res": True})
    event.code, event.param = lv.EVENT.HIT_TEST, info
    check("event_t", "get_hit_test_info", lambda: (event.get_hit_test_info().point.x, event.get_hit_test_info().res), lambda v: v == (13, True), "hit-test event returns typed point/result parameter")
    # lv_cover_check_info_t is private/unexported: official 32-bit ABI contains
    # lv_cover_res_t (four bytes) followed by a retained lv_area_t pointer.
    cover = bytearray(struct.pack("II", lv.COVER_RES.COVER, uctypes.addressof(area.__dereference__(16))))
    event.code, event.param = lv.EVENT.COVER_CHECK, cover
    check("event_t", "get_cover_area", lambda: event.get_cover_area().get_size(), lambda v: v == 54, "private cover-info ABI points to exact retained area")
    check("event_t", "set_cover_res", lambda: (event.set_cover_res(lv.COVER_RES.MASKED), struct.unpack("II", cover)[0])[1], lambda v: v == lv.COVER_RES.MASKED, "cover result writes caller-owned native parameter")
    task = lv.draw_task_t({"type": lv.DRAW_TASK_TYPE.FILL})
    event.code, event.param = lv.EVENT.DRAW_TASK_ADDED, task
    check("event_t", "get_draw_task", lambda: event.get_draw_task().type, lambda v: v == lv.DRAW_TASK_TYPE.FILL, "task-added event preserves retained typed task")
    called = []
    def callback(e):
        called.append(e.get_code())
    desc = obj.add_event_cb(callback, lv.EVENT.VALUE_CHANGED, None)
    event.code, event.param = lv.EVENT.VALUE_CHANGED, None
    event.user_data = desc.get_user_data()
    check("event_dsc_t", "get_cb", lambda: (desc.get_cb()(event), called)[1], lambda v: v == [lv.EVENT.VALUE_CHANGED], "descriptor callback accessor invokes actual Python callback")
    obj.remove_event(obj.get_event_count() - 1)
    indev.delete()


def themes(lv, display, obj):
    font = lv.font_get_default()
    theme = lv.theme_default_init(display, lv.color_hex(0x123456), lv.color_hex(0xabcdef), False, font)
    display.set_theme(theme)
    check("", "theme_default_init", lambda: theme.color_primary.to_int(), lambda v: v == 0x123456, "default theme retains exact primary color")
    check("", "theme_default_get", lambda: lv.theme_default_get().color_secondary.to_int(), lambda v: v == 0xabcdef, "singleton retains exact secondary color")
    check("", "theme_default_is_inited", lv.theme_default_is_inited, bool, "actual default theme initialized")
    check("", "theme_get_from_obj", lambda: lv.theme_get_from_obj(obj).color_primary.to_int(), lambda v: v == 0x123456, "object resolves display theme")
    for name in ("theme_get_font_small", "theme_get_font_normal", "theme_get_font_large"):
        check("", name, lambda name=name: getattr(lv, name)(obj).get_line_height(), lambda v: v == font.get_line_height(), "configured font line height returned by object theme")
    for name, expected in (("theme_get_color_primary", 0x123456), ("theme_get_color_secondary", 0xabcdef)):
        check("", name, lambda name=name: getattr(lv, name)(obj).to_int(), lambda v, expected=expected: v == expected, "object theme resolves exact configured color")
    child = lv.theme_t()
    check("theme_t", "set_parent", lambda: (child.set_parent(theme), lv.theme_t.__cast__(child.parent).color_primary.to_int())[1], lambda v: v == 0x123456, "custom theme links actual parent")
    calls = []
    def apply(current, target):
        calls.append(target.is_valid())
    child.set_apply_cb(apply)
    display.set_theme(child)
    check("theme_t", "set_apply_cb", lambda: (lv.theme_apply(obj), calls)[1], lambda v: v and all(v), "custom theme callback executes on native object")
    calls[:] = []
    check("", "theme_apply", lambda: (lv.theme_apply(obj), calls)[1], lambda v: v == [True], "explicit application invokes custom theme callback once")
    display.set_theme(theme)


def groups(lv, parent):
    count = lv.group_get_count()
    group = lv.group_create()
    check("", "group_create", group.get_obj_count, lambda v: v == 0, "new group starts empty")
    check("", "group_get_count", lv.group_get_count, lambda v: v == count + 1, "group registry increases exactly once")
    group.set_default()
    check("", "group_get_default", lambda: lv.group_get_default().get_obj_count(), lambda v: v == 0, "default resolves actual empty owned group")
    one, two = lv.obj(parent), lv.obj(parent)
    one.set_width(11)
    two.set_width(22)
    one.update_layout()
    two.update_layout()
    group.add_obj(one)
    group.add_obj(two)
    check("", "group_by_index", lambda: lv.group_by_index(count).get_obj_count(), lambda v: v == 2, "registry index resolves added group")
    check("", "group_focus_obj", lambda: (lv.group_focus_obj(two), group.get_focused().get_width())[1], lambda v: v == 22, "explicit focus changes actual focused object")
    check("", "group_swap_obj", lambda: (lv.group_swap_obj(one, two), group.get_obj_by_index(0).get_width())[1], lambda v: v == 22, "swap reverses native object order")
    check("", "group_remove_obj", lambda: (lv.group_remove_obj(one), group.get_obj_count())[1], lambda v: v == 1, "removal reduces actual membership")
    group.delete()


def snapshot(lv, obj):
    obj.remove_style_all()
    obj.set_size(4, 3)
    obj.set_style_bg_color(lv.color_hex(0xff0000), 0)
    obj.set_style_bg_opa(lv.OPA.COVER, 0)
    obj.update_layout()
    cf = lv.COLOR_FORMAT.RGB565
    buf = lv.snapshot_take(obj, cf)
    def pixels(b):
        return (b.header.w, b.header.h, bytes(b.data.__dereference__(b.header.stride * b.header.h)).hex())
    expected = (4, 3, (b"\x00\xf8" * 12).hex())
    check("", "snapshot_take", lambda: pixels(buf), lambda v: v == expected, "logical renderer produces exact twelve red RGB565 pixels")
    buf.destroy()
    buf = lv.snapshot_create_draw_buf(obj, cf)
    check("", "snapshot_create_draw_buf", lambda: (buf.header.w, buf.header.h), lambda v: v == (4, 3), "new snapshot buffer has object geometry")
    check("", "snapshot_reshape_draw_buf", lambda: lv.snapshot_reshape_draw_buf(obj, buf), lambda v: v == lv.RESULT.OK, "owned buffer fits same object dimensions")
    check("", "snapshot_take_to_draw_buf", lambda: (lv.snapshot_take_to_draw_buf(obj, cf, buf), pixels(buf)), lambda v: v == (lv.RESULT.OK, expected), "render-to-buffer returns exact RGB565 scene bytes")
    buf.destroy()
    raw = bytearray(24)
    desc = lv.image_dsc_t()
    check("", "snapshot_take_to_buf", lambda: (lv.snapshot_take_to_buf(obj, cf, desc, raw, len(raw)), bytes(raw).hex()), lambda v: v == (lv.RESULT.OK, expected[2]), "caller-owned binary snapshot has exact independent scene pixels")
    owned = lv.snapshot_take(obj, cf)
    lv.snapshot_free(lv.image_dsc_t.__cast__(owned))
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl", method="snapshot_free", status="CALL_OK", oracle="deprecated snapshot destructor frees actual owned draw buffer once; allocator accounting unsupported")))


def globals_ui(lv, display, screen, obj, captured):
    check("", "display_create", lambda: (display.get_horizontal_resolution(), display.get_vertical_resolution()), lambda v: v == (32, 24), "owned logical display has exact requested dimensions")
    check("", "display_get_default", lambda: lv.display_get_default().get_user_data().__cast__()["id"], lambda v: v == "DISPLAY", "default resolves actual owned display")
    other = lv.obj(None)
    check("", "screen_load", lambda: (lv.screen_load(other), display.get_screen_active() is other)[1], bool, "explicit screen becomes active")
    check("", "screen_active", lambda: lv.screen_active() is other, bool, "global active-screen getter resolves loaded screen")
    check("", "screen_load_anim", lambda: (lv.screen_load_anim(screen, lv.SCR_LOAD_ANIM.NONE, 0, 0, False), lv.screen_active() is screen)[1], bool, "zero-duration screen load switches back immediately")
    for name in ("layer_top", "layer_sys", "layer_bottom"):
        check("", name, lambda name=name: getattr(lv, name)().is_valid(), bool, "logical display owns live overlay/background layer")
    display.set_dpi(160)
    check("", "dpx", lambda: lv.dpx(10), lambda v: v == 10, "160 DPI preserves 10 density-independent pixels")
    lv.refr_set_disp_refreshing(display)
    check("", "refr_set_disp_refreshing", lambda: lv.refr_get_disp_refreshing().get_user_data().__cast__()["id"], lambda v: v == "DISPLAY", "refresh registry tracks actual owned display")
    check("", "refr_get_disp_refreshing", lambda: lv.refr_get_disp_refreshing().get_user_data().__cast__()["id"], lambda v: v == "DISPLAY", "refresh getter resolves retained display nonce")
    lv.refr_set_disp_refreshing(None)
    lv.refr_now(display)
    display.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)
    seen = []
    def invalidated(e):
        seen.append(e.get_invalidated_area().get_size())
    display.add_event_cb(invalidated, lv.EVENT.INVALIDATE_AREA, None)
    area = lv.area_t({"x1": 1, "y1": 1, "x2": 3, "y2": 3})
    check("", "inv_area", lambda: (lv.inv_area(display, area), list(seen))[1], lambda v: v and v[-1] == 9, "native invalidation dispatch carries exact requested area")
    screen.invalidate()
    check("", "refr_now", lambda: (lv.refr_now(display), len(captured))[1], lambda v: v > 0, "explicit refresh delivers actual logical pixel flush")
    before = len(captured)
    screen.invalidate()
    check("", "display_refr_timer", lambda: (lv.display_refr_timer(display.get_refr_timer()), len(captured))[1], lambda v: v > before, "native display timer renders invalidated logical frame")
    obj.add_flag(lv.obj.FLAG.CLICKABLE)
    obj.set_pos(0, 0)
    obj.update_layout()
    point = lv.point_t({"x": 1, "y": 1})
    check("", "indev_search_obj", lambda: lv.indev_search_obj(screen, point).is_valid(), bool, "native hit search finds live object at explicit logical point")
    distance = lv.point_t({"x": 123, "y": 456})
    check("", "indev_scroll_get_snap_dist", lambda: (lv.indev_scroll_get_snap_dist(obj, distance), distance.x, distance.y)[1:], lambda v: v == ((1 << 29) - 1, (1 << 29) - 1), "no snap-enabled children return documented LV_COORD_MAX sentinels")
    indev = lv.indev_create()
    indev.set_type(lv.INDEV_TYPE.POINTER)
    indev.set_display(display)
    calls = []
    def read(device, data):
        calls.append((lv.indev_active() is not None, lv.indev_get_active_obj() is None))
        data.point.x, data.point.y = 1, 1
        data.state = lv.INDEV_STATE.RELEASED
    indev.set_read_cb(read)
    check("", "indev_create", indev.get_type, lambda v: v == lv.INDEV_TYPE.POINTER, "owned logical pointer created and configured")
    check("", "indev_read_timer_cb", lambda: (lv.indev_read_timer_cb(indev.get_read_timer()), len(calls))[1], lambda v: v == 1, "native timer calls actual logical read callback")
    check("", "indev_active", lambda: calls[0][0], bool, "active logical indev is available inside its read callback")
    check("", "indev_get_active_obj", lambda: calls[0][1], bool, "initial released pointer has no active pressed object")
    indev.delete()


def layout(lv, obj):
    calls = []
    def update(target, data):
        calls.append(data.__cast__()["id"])
    layout_id = lv.layout_register(update, {"id": "CUSTOM LAYOUT"})
    obj.set_layout(layout_id)
    obj.update_layout()
    check("", "layout_register", lambda: (lv.layout_apply(obj), list(calls))[1], lambda v: v and all(x == "CUSTOM LAYOUT" for x in v), "registered layout runs real callback with retained exact context")
    before = len(calls)
    check("", "layout_apply", lambda: (lv.layout_apply(obj), len(calls))[1], lambda v: v == before + 1, "explicit layout application runs callback once")
    for name, layout_id in (("flex_init", lv.LAYOUT.FLEX), ("grid_init", lv.LAYOUT.GRID)):
        getattr(lv, name)()
        obj.set_layout(layout_id)
        obj.update_layout()
        check("", name, lambda: obj.get_style_layout(0), lambda v, layout_id=layout_id: v == layout_id, "registered built-in layout is usable by native object")
    obj.set_layout(lv.LAYOUT.NONE)


def run():
    import lvgl as lv
    lv.init()
    display = lv.display_create(32, 24)
    display.set_user_data({"id": "DISPLAY"})
    display.set_default()
    display.set_color_format(lv.COLOR_FORMAT.RGB565)
    raw = bytearray(32 * 24 * 2)
    display.set_buffers(raw, None, len(raw), lv.DISPLAY_RENDER_MODE.FULL)
    captured = []
    def flush(d, a, p):
        captured.append(a.get_size())
        d.flush_ready()
    display.set_flush_cb(flush)
    screen = display.get_screen_active()
    obj = lv.obj(screen)
    for stage in (events, groups, snapshot):
        try:
            stage(lv, obj if stage != groups else screen)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.ui_helpers", method=stage.__name__, status="FIXTURE_ERROR", error=repr(error))))
    try:
        themes(lv, display, obj)
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.ui_helpers", method="themes", status="FIXTURE_ERROR", error=repr(error))))
    try:
        globals_ui(lv, display, screen, obj, captured)
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.ui_helpers", method="globals", status="FIXTURE_ERROR", error=repr(error))))
    try:
        layout(lv, obj)
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.ui_helpers", method="layout", status="FIXTURE_ERROR", error=repr(error))))
    display.set_theme(None)
    lv.theme_default_deinit()
    check("", "theme_default_deinit", lv.theme_default_is_inited, lambda v: v is False, "native theme teardown clears initialized state")
    display.delete()


try:
    run()
except Exception as error:
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl.ui_helpers", method="run", status="FIXTURE_ERROR", error=repr(error))))
print("LVGL_UI_HELPERS_DONE")
