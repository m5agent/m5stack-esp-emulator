"""Owned native LVGL resources with byte, geometry and callback oracles.

The independent logical display/input fixtures test LVGL state and rendering
contracts. They do not establish a board panel or physical input result.
"""
import json
import struct


def report(target, method, action, oracle, description):
    try:
        value = action()
        passed = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl" + ("." + target if target else ""),
            "method": method, "status": "STATE_PASS" if passed else "FAIL", "oracle": description,
            "value": value if isinstance(value, (int, bool, str, list, tuple)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl" + ("." + target if target else ""),
            "method": method, "status": "FAIL", "oracle": description, "error": repr(error)}))


def buffers(lv):
    cf = lv.COLOR_FORMAT.ARGB8888
    stride = lv.draw_buf_width_to_stride(4, cf)
    report("", "draw_buf_width_to_stride", lambda: stride, lambda x: x == 16, "four ARGB8888 pixels occupy sixteen bytes")
    handlers = lv.draw_buf_get_handlers()
    report("", "draw_buf_get_handlers", lambda: handlers.width_to_stride_ex(4, cf), lambda x: x == 16, "default draw handlers compute exact stride")
    for name in ("draw_buf_get_font_handlers", "draw_buf_get_image_handlers"):
        report("", name, lambda name=name: getattr(lv, name)().width_to_stride_ex(4, cf), lambda x: x == 16, "resource-specific handlers compute exact stride")
    own_handlers = lv.draw_buf_handlers_t()
    own_handlers.init_with_default_handlers()
    report("draw_buf_handlers_t", "init_with_default_handlers", lambda: own_handlers.width_to_stride_ex(4, cf), lambda x: x == 16, "initialized handler set computes exact stride")
    report("draw_buf_handlers_t", "width_to_stride_ex", lambda: own_handlers.width_to_stride_ex(4, cf), lambda x: x == 16, "native width to stride callback")
    buf = lv.draw_buf_create(4, 3, cf, 0)
    report("", "draw_buf_create", lambda: (buf.header.w, buf.header.h, buf.header.stride), lambda x: x == (4, 3, 16), "owned draw buffer dimensions and stride")
    data = buf.data.__dereference__(48)
    data[:] = bytes(range(48))
    report("draw_buf_t", "goto_xy", lambda: bytes(buf.goto_xy(2, 1).__dereference__(4)).hex(), lambda x: x == bytes(range(24, 28)).hex(), "pixel address includes row stride and bytes per pixel")
    duplicate = buf.dup()
    report("draw_buf_t", "dup", lambda: bytes(duplicate.data.__dereference__(48)).hex(), lambda x: x == bytes(range(48)).hex(), "independent allocated draw buffer duplicates all bytes")
    area = lv.area_t({"x1": 1, "y1": 1, "x2": 2, "y2": 1})
    duplicate.clear(area)
    report("draw_buf_t", "clear", lambda: bytes(duplicate.data.__dereference__(48)).hex(), lambda x: x == (bytes(range(20)) + bytes(8) + bytes(range(28, 48))).hex(), "only selected two pixels cleared; adjacent bytes retained")
    report("draw_buf_t", "copy", lambda: (duplicate.copy(area, buf, area), bytes(duplicate.data.__dereference__(48)).hex())[1], lambda x: x == bytes(range(48)).hex(), "native rectangle copy restores exact source pixels")
    image = lv.image_dsc_t()
    buf.to_image(image)
    report("draw_buf_t", "to_image", lambda: (image.header.w, image.header.h, bytes(image.data.__dereference__(48)).hex()), lambda x: x == (4, 3, bytes(range(48)).hex()), "image descriptor references all buffer bytes and dimensions")
    borrowed = lv.draw_buf_t()
    borrowed.from_image(image)
    report("draw_buf_t", "from_image", lambda: (borrowed.header.w, borrowed.header.h, bytes(borrowed.data.__dereference__(48)).hex()), lambda x: x == (4, 3, bytes(range(48)).hex()), "borrowed image is mapped without changing bytes")
    flag = lv.image.FLAGS.PREMULTIPLIED
    report("draw_buf_t", "set_flag", lambda: (buf.set_flag(flag), buf.has_flag(flag))[1], bool, "selected native flag enabled")
    report("draw_buf_t", "has_flag", lambda: buf.has_flag(flag), bool, "flag query reflects enabled flag")
    report("draw_buf_t", "clear_flag", lambda: (buf.clear_flag(flag), buf.has_flag(flag))[1], lambda x: not x, "selected native flag cleared")
    for name in ("invalidate_cache", "flush_cache"):
        report("draw_buf_t", name, lambda name=name: (getattr(buf, name)(None), bytes(data).hex())[1], lambda x: x == bytes(range(48)).hex(), "cache operation preserves native pixel bytes")
    report("draw_buf_t", "reshape", lambda: buf.reshape(cf, 3, 4, 0), lambda x: x is not None and x.header.w == 3 and x.header.h == 4, "same-capacity reshape changes dimensions")
    report("draw_buf_t", "adjust_stride", lambda: (buf.adjust_stride(12), buf.header.stride), lambda x: x == (lv.RESULT.OK, 12), "explicit valid row stride")
    raw = bytearray(b"\xff\x00\x00\x80" * 4)
    initialized = lv.draw_buf_t()
    report("draw_buf_t", "init", lambda: (initialized.init(2, 2, cf, 8, raw, 16), initialized.header.w, initialized.header.h), lambda x: x == (lv.RESULT.OK, 2, 2), "caller-owned buffer initialized with exact capacity")
    initialized.set_flag(lv.image.FLAGS.MODIFIABLE)
    report("draw_buf_t", "premultiply", lambda: (initialized.premultiply(), list(raw[:4])), lambda x: x[0] == lv.RESULT.OK and x[1] == [127, 0, 0, 128], "half-alpha BGRA channel is premultiplied")
    buf.destroy()
    duplicate.destroy()
    print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl.draw_buf_t", "method": "destroy",
        "status": "CALL_OK", "oracle": "owned native buffer destructor called; allocator accounting is unsupported in LV_STDLIB_MICROPYTHON"}))
    extra = own_handlers.create_ex(2, 2, cf, 0)
    report("draw_buf_handlers_t", "create_ex", lambda: (extra.header.w, extra.header.h), lambda x: x == (2, 2), "custom handler set allocates requested dimensions")
    extra.data.__dereference__(16)[:] = b"0123456789abcdef"
    clone = own_handlers.dup_ex(extra)
    report("draw_buf_handlers_t", "dup_ex", lambda: bytes(clone.data.__dereference__(16)).decode(), lambda x: x == "0123456789abcdef", "handler-specific duplicate preserves sixteen bytes")
    extra.destroy()
    clone.destroy()


def fonts_text(lv):
    font = lv.font_t(lv.font_get_default())
    report("", "font_get_default", font.get_line_height, lambda x: x > 0, "compiled default font has a positive line height")
    height = font.get_line_height()
    report("font_t", "get_line_height", lambda: height, lambda x: x == font.line_height, "public getter agrees with native descriptor")
    glyph = lv.font_glyph_dsc_t()
    report("font_t", "get_glyph_dsc", lambda: lv.font_t.get_glyph_dsc(font, glyph, ord("A"), 0), lambda x: x and glyph.box_w > 0 and glyph.box_h > 0 and glyph.adv_w > 0, "known printable glyph has actual dimensions and advance")
    width = font.get_glyph_width(ord("A"), 0)
    report("font_t", "get_glyph_width", lambda: width, lambda x: x > 0, "printable glyph advances the cursor")
    report("font_t", "get_glyph_dsc_fmt_txt", lambda: font.get_glyph_dsc_fmt_txt(glyph, ord("A"), 0), lambda x: x and glyph.box_w > 0, "formatted text font supplies actual A glyph")
    report("font_t", "set_kerning", lambda: (font.set_kerning(lv.FONT_KERNING.NONE), font.kerning)[1], lambda x: x == lv.FONT_KERNING.NONE, "kerning mode set in native descriptor")
    font.set_kerning(lv.FONT_KERNING.NORMAL)
    report("", "text_get_width", lambda: lv.text_get_width("AA", 2, font, 0), lambda x: x == 2 * width, "two equal glyph advances add without spacing")
    report("", "text_get_width_with_flags", lambda: lv.text_get_width_with_flags("AA", 2, font, 0, 0), lambda x: x == 2 * width, "plain flags preserve exact two-glyph width")
    size = lv.point_t()
    report("", "text_get_size", lambda: (lv.text_get_size(size, "A\nA", font, 0, 3, 1000, 0), size.x, size.y)[1:], lambda x: x == (width, 2 * height + 3), "two text lines include exactly one line-space")
    used = bytearray(4)
    report("", "text_get_next_line", lambda: (lv.text_get_next_line("AA\nB", 4, font, 0, 1000, used, 0), struct.unpack("i", used)[0]), lambda x: x[0] == 3 and x[1] == 2 * width, "newline byte index and independently measured line width")
    storage = bytearray(b"abcd\0" + bytes(15))
    report("", "text_ins", lambda: (lv.text_ins(storage, 2, "XY"), bytes(storage[:7]).hex())[1], lambda x: x == b"abXYcd\0".hex(), "text insertion shifts suffix and terminator")
    report("", "text_cut", lambda: (lv.text_cut(storage, 2, 2), bytes(storage[:5]).hex())[1], lambda x: x == b"abcd\0".hex(), "text deletion restores original content")
    letter, following, offset = bytearray(4), bytearray(4), bytearray(4)
    report("", "text_encoded_letter_next_2", lambda: (lv.text_encoded_letter_next_2("A中", letter, following, offset), struct.unpack("I", letter)[0], struct.unpack("I", following)[0], struct.unpack("I", offset)[0])[1:], lambda x: x == (65, 0x4e2d, 1), "UTF8 two-codepoint decoding and first next byte offset")
    for name, value, expected in (("fs_get_ext", "/folder/image.png", "png"), ("fs_get_last", "/folder/image.png", "image.png")):
        report("", name, lambda name=name, value=value: getattr(lv, name)(value), lambda x, expected=expected: x == expected, "known path component")
    path = bytearray(b"/folder/image.png\0")
    report("", "fs_up", lambda: (lv.fs_up(path), bytes(path).split(b"\0")[0].decode())[1], lambda x: x == "/folder", "parent directory edits caller-owned path")


def animations(lv):
    a = lv.anim_t()
    a.init()
    report("anim_t", "init", lambda: (a.start_value, a.end_value), lambda x: x == (0, 100), "native animation default endpoints")
    state = {"samples": [], "started": 0, "completed": 0, "deleted": 0}
    a.set_user_data(state)
    report("anim_t", "set_user_data", lambda: a.get_user_data().__cast__() is state, bool, "Python dict lifetime bound to native animation")
    report("anim_t", "get_user_data", lambda: a.get_user_data().__cast__() is state, bool, "native user-data pointer returns same Python object")
    for name, value, field in (("set_duration", 100, "duration"), ("set_delay", 20, "act_time"), ("set_reverse_duration", 30, "reverse_duration"),
                               ("set_reverse_time", 40, "reverse_duration"), ("set_reverse_delay", 10, "reverse_delay"),
                               ("set_repeat_count", 2, "repeat_cnt"), ("set_repeat_delay", 5, "repeat_delay"), ("set_early_apply", False, "early_apply")):
        expected = -value if name == "set_delay" else value
        report("anim_t", name, lambda name=name, value=value, field=field: (getattr(a, name)(value), getattr(a, field))[1], lambda x, expected=expected: x == expected, "native animation field changes to supplied value")
    report("anim_t", "set_values", lambda: (a.set_values(10, 90), a.start_value, a.end_value)[1:], lambda x: x == (10, 90), "native animation endpoint pair")
    for name, expected in (("get_delay", 20), ("get_time", 100), ("get_repeat_count", 2)):
        report("anim_t", name, lambda name=name: getattr(a, name)(), lambda x, expected=expected: x == expected, "configured animation value through public getter")
    report("anim_t", "pause", lambda: (a.pause(), lv.anim_t.is_paused(a))[1], bool, "native animation enters paused state")
    report("anim_t", "is_paused", lambda: lv.anim_t.is_paused(a), bool, "paused state query")
    report("anim_t", "resume", lambda: (a.resume(), lv.anim_t.is_paused(a))[1], lambda x: not x, "resume clears paused state")
    report("anim_t", "pause_for", lambda: (a.pause_for(50), lv.anim_t.is_paused(a))[1], bool, "finite pause enters paused state")
    a.resume()
    a.set_duration(100)
    a.act_time = 50
    for name in ("path_linear", "path_ease_in", "path_ease_out", "path_ease_in_out", "path_overshoot", "path_bounce", "path_step"):
        def endpoints(name=name):
            a.act_time = 0
            first = getattr(a, name)()
            a.act_time = 100
            last = getattr(a, name)()
            return first, last
        report("anim_t", name, endpoints, lambda x: x == (10, 90), "path interpolation reaches exact start/end values")
    a.set_bezier3_param(0, 0, 1024, 1024)
    a.act_time = 50
    report("anim_t", "set_bezier3_param", a.path_custom_bezier3, lambda x: abs(x - 50) <= 1, "symmetric custom cubic path reaches midpoint")
    report("anim_t", "path_custom_bezier3", a.path_custom_bezier3, lambda x: abs(x - 50) <= 1, "custom cubic interpolation midpoint")
    a.set_delay(0)
    a.set_reverse_duration(0)
    a.set_reverse_delay(0)
    a.set_repeat_delay(0)
    a.set_repeat_count(0)
    a.set_early_apply(True)
    def execute(animation, value):
        state["samples"].append(value)
    a.set_custom_exec_cb(execute)
    a.set_start_cb(lambda animation: state.__setitem__("started", state["started"] + 1))
    a.set_completed_cb(lambda animation: state.__setitem__("completed", state["completed"] + 1))
    a.set_deleted_cb(lambda animation: state.__setitem__("deleted", state["deleted"] + 1))
    a.set_path_cb(lv.anim_t.path_linear)
    running = a.start()
    report("anim_t", "start", lambda: (lv.anim_count_running(), list(state["samples"])), lambda x: x[0] == 1 and 10 in x[1], "owned running copy applies initial endpoint")
    report("anim_t", "set_custom_exec_cb", lambda: list(state["samples"]), lambda x: 10 in x, "native animation invoked registered Python execution callback")
    for _ in range(6):
        lv.tick_inc(25)
        lv.timer_handler()
    report("anim_t", "set_path_cb", lambda: list(state["samples"]), lambda x: 90 in x and all(10 <= v <= 90 for v in x), "linear path reaches end and remains within endpoints")
    for method, field in (("set_start_cb", "started"), ("set_completed_cb", "completed"), ("set_deleted_cb", "deleted")):
        report("anim_t", method, lambda field=field: state[field], lambda x: x == 1, "native animation lifecycle invokes registered callback exactly once")
    report("", "anim_count_running", lv.anim_count_running, lambda x: x == 0, "completed owned animation is removed")
    timeline = lv.anim_timeline_create()
    a.set_deleted_cb(None)
    a.set_completed_cb(None)
    a.set_start_cb(None)
    timeline.add(50, a)
    report("anim_timeline_t", "add", timeline.get_playtime, lambda x: x == 150, "timeline length includes fifty millisecond offset")
    report("anim_timeline_t", "get_playtime", timeline.get_playtime, lambda x: x == 150, "timeline endpoint matches offset plus duration")
    for setter, getter, value in (("set_reverse", "get_reverse", True), ("set_repeat_count", "get_repeat_count", 2), ("set_repeat_delay", "get_repeat_delay", 17)):
        report("anim_timeline_t", setter, lambda setter=setter, getter=getter, value=value: (getattr(timeline, setter)(value), getattr(timeline, getter)())[1], lambda x, value=value: x == value, "timeline configuration roundtrip")
        report("anim_timeline_t", getter, lambda getter=getter: getattr(timeline, getter)(), lambda x, value=value: x == value, "current timeline configuration")
    report("anim_timeline_t", "set_progress", lambda: (timeline.set_progress(65535), state["samples"][-1])[1], lambda x: x == 90, "seeking timeline to end applies final endpoint")
    report("anim_timeline_t", "get_progress", timeline.get_progress, lambda x: x == 65535, "timeline progress retains end position")
    report("anim_timeline_t", "start", timeline.start, lambda x: x == 150, "timeline returns configured total play time")
    timeline.pause()
    frozen = len(state["samples"])
    lv.tick_inc(200)
    lv.timer_handler()
    report("anim_timeline_t", "pause", lambda: len(state["samples"]), lambda x: x == frozen, "paused timeline produces no further execution callbacks")
    timeline.delete()
    report("anim_timeline_t", "delete", lv.anim_count_running, lambda x: x == 0, "deleting owned timeline leaves no running animations")


def run():
    import lvgl as lv
    lv.init()
    for stage, action in (("buffers", buffers), ("fonts_text", fonts_text), ("animations", animations)):
        try:
            action(lv)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": stage + "_fixture", "status": "NOT_RUN", "oracle": repr(error)}))
    lv.deinit()


try:
    run()
except Exception as error:
    print("LVGL_RESOURCES_ERROR", repr(error))
print("LVGL_RESOURCES_DONE")
