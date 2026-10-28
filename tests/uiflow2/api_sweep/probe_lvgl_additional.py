"""Native LVGL helper, subject, font and GIF fixtures with independent values.

Only owned resources are changed. Destructors without an allocator oracle are
CALL_OK; logical pixel buffers do not establish board or physical display PASS.
"""
import json
import struct


def emit(target, method, status, **details):
    print("M5EMU_UI_RESULT " + json.dumps(dict(api_target="lvgl" + ("." + target if target else ""), method=method, status=status, **details)))


def check(target, method, action, oracle, reason):
    try:
        value = action()
        emit(target, method, "STATE_PASS" if oracle(value) else "FAIL", oracle=reason,
             value=value if isinstance(value, (int, bool, str, tuple, list)) or value is None else repr(value))
        return value
    except Exception as error:
        emit(target, method, "FAIL", oracle=reason, error=repr(error))


def helpers(lv):
    check("", "version_major", lv.version_major, lambda v: v == 9, "compiled LVGL major version")
    check("", "version_minor", lv.version_minor, lambda v: v == 3, "compiled LVGL minor version")
    check("", "version_patch", lv.version_patch, lambda v: v == 0, "compiled LVGL patch version")
    check("", "version_info", lv.version_info, lambda v: isinstance(v, str), "compiled version suffix returned as string")
    for name, values, expected in (("text_is_break_char", (32, 65), (True, False)),
                                   ("text_is_a_word", (0x4e2d, 65), (True, False)),
                                   ("text_is_marker", (0x202a, 65), (True, False))):
        check("", name, lambda name=name, values=values: tuple(getattr(lv, name)(x) for x in values),
              lambda v, expected=expected: v == expected, "source-defined positive and negative Unicode classes")
    align, direction = bytearray(struct.pack("i", lv.TEXT_ALIGN.AUTO)), bytearray(struct.pack("i", lv.BASE_DIR.AUTO))
    check("", "bidi_calculate_align", lambda: (lv.bidi_calculate_align(align, direction, "ABC"), struct.unpack("i", align)[0], struct.unpack("i", direction)[0])[1:],
          lambda v: v == (lv.TEXT_ALIGN.LEFT, lv.BASE_DIR.AUTO), "LV_USE_BIDI=0 resolves AUTO alignment to left and leaves direction unchanged; bidi ordering unsupported")
    check("", "style_get_prop_group", lambda: lv.style_get_prop_group(lv.STYLE.WIDTH), lambda v: v == (lv.STYLE.WIDTH >> 2), "inline property group bit shift")
    check("", "style_prop_lookup_flags", lambda: lv.style_prop_lookup_flags(lv.STYLE.WIDTH), lambda v: v & 4, "width affects layout")
    check("", "style_prop_has_flag", lambda: lv.style_prop_has_flag(lv.STYLE.WIDTH, 4), bool, "layout property flag predicate")
    check("", "grid_fr", lambda: (lv.grid_fr(1), lv.grid_fr(3)), lambda v: v[1] - v[0] == 2, "fractional grid units preserve requested ratio encoding")
    a, b = lv.point_precise_t(), lv.point_precise_t()
    check("point_precise_t", "set", lambda: (a.set(3, 7), a.x, a.y)[1:], lambda v: v == (3, 7), "precise point coordinates")
    b.set(11, 13)
    check("point_precise_t", "swap", lambda: (a.swap(b), a.x, a.y, b.x, b.y)[1:], lambda v: v == (11, 13, 3, 7), "two precise points swap both coordinates")
    points = [lv.point_t({"x": 1, "y": 2}), lv.point_t({"x": 3, "y": 4})]
    pivot = lv.point_t({"x": 0, "y": 0})
    check("point_t", "array_transform", lambda: (points[0].array_transform(1, 0, 512, 512, pivot, True), points[0].x, points[0].y)[1:], lambda v: v == (2, 4), "identity-angle 2x scaling changes native array point")
    a1, a2 = lv.area_t({"x1": 0, "y1": 0, "x2": 9, "y2": 9}), lv.area_t({"x1": 2, "y1": 2, "x2": 7, "y2": 7})
    out = [lv.area_t() for _ in range(4)]
    check("area_t", "diff", lambda: lv.area_t.diff(out, a1, a2), lambda v: v == 4, "interior rectangle leaves four disjoint surrounding rectangles")
    c = lv.color16_t({"red": 31, "green": 63, "blue": 31})
    check("color16_t", "luminance", c.luminance, lambda v: v >= 248, "RGB565 white luminance endpoint")
    check("color16_t", "premultiply", lambda: (c.premultiply(0), c.red, c.green, c.blue)[1:], lambda v: v == (0, 0, 0), "zero opacity clears all RGB565 channels")
    path = lv.fs_path_ex_t()
    raw = bytearray(b"MEMORY PATH\x00\xff")
    check("fs_path_ex_t", "make_path_from_buffer", lambda: (path.make_path_from_buffer(ord("M"), raw, len(raw)), path.size, bytes(path.buffer.__dereference__(len(raw))).hex())[1:],
          lambda v: v == (len(raw), raw.hex()), "memory file path preserves exact binary buffer and length")
    state = bytearray(4)
    def command():
        result = []
        for c in "#ff0000 A#B":
            result.append(bool(lv.text_is_cmd(state, ord(c))))
        return result, struct.unpack("i", state)[0]
    check("", "text_is_cmd", command, lambda v: v == ([True] * 8 + [False, True, False], 0), "color command transitions WAIT/PAR/IN/WAIT and excludes text characters")
    key, ordered = b"b\x00", b"a\x00b\x00c\x00"
    check("", "utils_bsearch", lambda: bytes(lv.utils_bsearch(key, ordered, 3, 2, lv.strcmp).__dereference__(2)).hex(), lambda v: v == key.hex(), "native strcmp callback finds exact middle terminated record")


def subjects(lv):
    first, second = bytearray(b"FIRST"), bytearray(b"SECOND")
    subject = lv.subject_t()
    check("subject_t", "init_pointer", lambda: (subject.init_pointer(first), bytes(subject.get_pointer().__dereference__(5)))[1], lambda v: v == b"FIRST", "pointer subject references first retained byte buffer")
    check("subject_t", "set_pointer", lambda: (subject.set_pointer(second), bytes(subject.get_pointer().__dereference__(6)))[1], lambda v: v == b"SECOND", "pointer setter updates current buffer")
    check("subject_t", "get_pointer", lambda: bytes(subject.get_pointer().__dereference__(6)), lambda v: v == b"SECOND", "current buffer bytes")
    check("subject_t", "get_previous_pointer", lambda: bytes(subject.get_previous_pointer().__dereference__(5)), lambda v: v == b"FIRST", "previous pointer remains distinct")
    one, two, group = lv.subject_t(), lv.subject_t(), lv.subject_t()
    one.init_int(17)
    two.init_int(23)
    check("subject_t", "init_group", lambda: (group.init_group([one, two], 2), group.get_group_element(0).get_int(), group.get_group_element(1).get_int())[1:], lambda v: v == (17, 23), "two native subject references remain ordered")
    check("subject_t", "get_group_element", lambda: group.get_group_element(1).get_int(), lambda v: v == 23, "second group subject value")
    obj = lv.obj(lv.screen_active())
    calls = []
    def observer_cb(observer, changed):
        calls.append(changed.get_int())
    observer = one.add_observer_obj(observer_cb, obj, None)
    calls[:] = []
    check("subject_t", "add_observer_obj", lambda: (one.set_int(19), list(calls))[1], lambda v: v == [19], "object-owned observer receives actual changed value")
    check("observer_t", "get_target_obj", lambda: observer.get_target_obj().is_valid(), bool, "observer resolves live owned object target")
    obj.remove_from_subject(one)
    calls[:] = []
    observer = one.add_observer_with_target(observer_cb, second, None)
    calls[:] = []
    check("subject_t", "add_observer_with_target", lambda: (one.set_int(29), list(calls))[1], lambda v: v == [29], "buffer-target observer receives actual changed value")
    check("observer_t", "get_target", lambda: bytes(observer.get_target().__dereference__(6)), lambda v: v == b"SECOND", "observer target is retained caller-owned buffer")
    observer.remove()
    for s in (subject, group, one, two):
        s.deinit()
    obj.delete()


def glyphs(lv):
    font = lv.font_t(lv.font_get_default())
    glyph = lv.font_glyph_dsc_t()
    assert lv.font_t.get_glyph_dsc(font, glyph, ord("A"), 0)
    draw = lv.draw_buf_create(glyph.box_w, glyph.box_h, lv.COLOR_FORMAT.A8, 0)
    for method in ("get_glyph_bitmap", "get_bitmap_fmt_txt"):
        check("font_glyph_dsc_t", method, lambda method=method: any(bytes(getattr(glyph, method)(draw).__dereference__(glyph.box_w * glyph.box_h))), bool,
              "printable A has nonzero native glyph bitmap bytes")
    glyph.release_draw_data()
    draw.destroy()
    emit("font_glyph_dsc_t", "release_draw_data", "CALL_OK", oracle="release called on actual glyph; allocator accounting unsupported")
    raw = bytearray(b"\x00\xf8" * 4)
    image = lv.image_dsc_t({"header": {"magic": 0x19, "cf": lv.COLOR_FORMAT.RGB565, "w": 2, "h": 2, "stride": 4}, "data_size": len(raw), "data": raw})
    calls = []
    def image_path(font, letter, following, offset, data):
        calls.append((letter, data.__cast__()["nonce"]))
        offset[0] = 2
        return image
    image_font = lv.imgfont_create(10, image_path, {"nonce": "IMAGE FONT"})
    image_glyph = lv.font_glyph_dsc_t()
    def glyph_image():
        valid = lv.font_t.get_glyph_dsc(image_font, image_glyph, ord("A"), 0)
        return valid, image_font.get_line_height(), image_glyph.box_w, image_glyph.box_h, image_glyph.ofs_y, list(calls)
    check("", "imgfont_create", glyph_image, lambda v: v == (True, 10, 2, 2, 2, [(65, "IMAGE FONT")]), "image-backed font invokes retained callback and decodes exact native image geometry")
    lv.imgfont_destroy(image_font)
    emit("", "imgfont_destroy", "CALL_OK", oracle="owned image font destroyed once; allocator accounting unsupported")


def gif(lv):
    import fs_driver
    driver = lv.fs_drv_t()
    fs_driver.fs_register(driver, "T", 0)
    # The official callback returns Python dictionaries; retain file handles.
    handles = []
    def opened(drv, path, mode):
        item = fs_driver.fs_open_cb(drv, path, mode)
        handles.append(item)
        return item
    driver.open_cb = opened
    with open("/flash/two-frame.gif", "rb") as f:
        data = f.read()
    memory = lv.gd_open_gif_data(data)
    check("", "gd_open_gif_data", lambda: (memory.width, memory.height), lambda v: v == (8, 8), "independently generated two-frame 8x8 GIF")
    for expected in ((255, 0, 0), (0, 0, 255)):
        check("gd_GIF", "get_frame", memory.get_frame, lambda v: v == 1, "next real GIF image frame is available")
        out = bytearray(memory.width * memory.height * 4)
        check("gd_GIF", "render_frame", lambda: (memory.render_frame(out), bytes(out))[1], lambda v, expected=expected: v == bytes((expected[2], expected[1], expected[0], 255)) * 64, "all independently generated frame BGRA8888 pixels match")
    check("gd_GIF", "rewind", lambda: (memory.rewind(), memory.get_frame())[1], lambda v: v == 1, "rewind makes first frame available again")
    memory.close_gif()
    emit("gd_GIF", "close_gif", "CALL_OK", oracle="owned decoded GIF closed; allocator accounting unsupported")
    file_gif = lv.gd_open_gif_file("T:/flash/two-frame.gif")
    check("", "gd_open_gif_file", lambda: (file_gif.width, file_gif.height, file_gif.get_frame()), lambda v: v == (8, 8, 1), "same GIF decoded through actual Flash filesystem callbacks")
    file_gif.close_gif()


def run():
    import M5
    import lvgl as lv
    import m5ui
    M5.begin()
    m5ui.init()
    for stage in (helpers, subjects, glyphs, gif):
        try:
            stage(lv)
        except Exception as error:
            emit("additional", stage.__name__, "FIXTURE_ERROR", error=repr(error))
    m5ui.deinit()


try:
    run()
except Exception as error:
    emit("additional", "run", "FIXTURE_ERROR", error=repr(error))
print("LVGL_ADDITIONAL_DONE")
