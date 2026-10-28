"""Typed style resources, draw descriptor defaults and native utility oracles."""
import json
import struct


def check(target, method, action, oracle, reason):
    try:
        value = action()
        ok = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl" + ("." + target if target else ""), "method": method,
            "status": "STATE_PASS" if ok else "FAIL", "oracle": reason,
            "value": value if isinstance(value, (int, bool, str, tuple, list)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl" + ("." + target if target else ""), "method": method,
            "status": "FAIL", "oracle": reason, "error": repr(error)}))


def styles(lv):
    style = lv.style_t()
    style.init()
    grad = lv.grad_dsc_t()
    grad.horizontal_init()
    check("grad_dsc_t", "horizontal_init", lambda: grad.dir, lambda x: x == lv.GRAD_DIR.HOR, "horizontal gradient direction")
    check("grad_dsc_t", "vertical_init", lambda: (grad.vertical_init(), grad.dir)[1], lambda x: x == lv.GRAD_DIR.VER, "vertical gradient direction")
    colors = lv.color_t(2)
    colors[0] = lv.color_hex(0xff0000)
    colors[1] = lv.color_hex(0x0000ff)
    check("grad_dsc_t", "init_stops", lambda: (grad.init_stops(colors, bytes([255, 127]), bytes([0, 255]), 2), grad.stops_count, grad.stops[0].color.to_int(), grad.stops[1].color.to_int())[1:], lambda x: x == (2, 0xff0000, 255), "two typed RGB stops retained in descriptor")
    image = lv.image_dsc_t()
    image.header.w, image.header.h = 2, 2
    image.header.cf = lv.COLOR_FORMAT.RGB565
    image.header.stride = 4
    image.data_size = 8
    image_bytes = bytearray(b"\x00\xf8" * 4)
    image.data = image_bytes
    font = lv.font_get_default()
    filt = lv.color_filter_dsc_t()
    filt.init(lambda descriptor, color, opacity: color)
    check("color_filter_dsc_t", "init", lambda: filt.filter_cb(filt, lv.color_hex(0x123456), 255).to_int(), lambda x: x == 0x123456, "initialized native filter routes actual callback color")
    anim = lv.anim_t()
    anim.init()
    anim.set_duration(123)
    trans = lv.style_transition_dsc_t()
    props = struct.pack("ii", lv.STYLE.WIDTH, 0)
    trans.init(props, lv.anim_t.path_linear, 77, 13, None)
    check("style_transition_dsc_t", "init", lambda: (trans.time, trans.delay), lambda x: x == (77, 13), "transition descriptor retains duration and delay")
    tracks = struct.pack("iii", 20, 30, lv.GRID_TEMPLATE_LAST)
    resources = (("set_bg_grad", "BG_GRAD", grad), ("set_bg_image_src", "BG_IMAGE_SRC", image),
                 ("set_arc_image_src", "ARC_IMAGE_SRC", image), ("set_text_font", "TEXT_FONT", font),
                 ("set_color_filter_dsc", "COLOR_FILTER_DSC", filt), ("set_anim", "ANIM", anim),
                 ("set_transition", "TRANSITION", trans), ("set_bitmap_mask_src", "BITMAP_MASK_SRC", image),
                 ("set_grid_column_dsc_array", "GRID_COLUMN_DSC_ARRAY", tracks), ("set_grid_row_dsc_array", "GRID_ROW_DSC_ARRAY", tracks))
    for method, prop, resource in resources:
        def roundtrip(method=method, prop=prop, resource=resource):
            getattr(style, method)(resource)
            out = lv.style_value_t()
            status = style.get_prop(getattr(lv.STYLE, prop), out)
            count = 8 if isinstance(resource, bytes) else len(resource.__dereference__())
            expected = resource[:count] if isinstance(resource, bytes) else bytes(resource.__dereference__())
            return status != 0 and bytes(out.ptr.__dereference__(count)) == expected
        check("style_t", method, roundtrip, bool, "typed resource pointer roundtrip compares native descriptor bytes")
    style.reset()


def descriptors(lv):
    cases = (("draw_rect_dsc_t", "bg_opa", 255), ("draw_label_dsc_t", "opa", 255),
             ("draw_image_dsc_t", "opa", 255), ("draw_line_dsc_t", "opa", 255),
             ("draw_arc_dsc_t", "opa", 255), ("draw_fill_dsc_t", "opa", 255),
             ("draw_border_dsc_t", "opa", 255), ("draw_box_shadow_dsc_t", "opa", 255),
             ("draw_letter_dsc_t", "opa", 255), ("draw_glyph_dsc_t", "opa", 0),
             ("draw_triangle_dsc_t", "bg_opa", 255), ("draw_mask_rect_dsc_t", "radius", 0))
    for name, field, expected in cases:
        def initialize(name=name, field=field):
            d = getattr(lv, name)()
            d.init()
            return getattr(d, field)
        check(name, "init", initialize, lambda x, expected=expected: x == expected, "native descriptor documented default field")
    monitor = lv.mem_monitor_t()
    for method in ("monitor", "core"):
        getattr(monitor, method)()
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl.mem_monitor_t", "method": method,
            "status": "BLOCKED_MODEL", "value": [monitor.total_size, monitor.free_size],
            "oracle": "LV_STDLIB_MICROPYTHON intentionally does not implement allocator accounting"}))


def utilities(lv):
    check("", "color32_make", lambda: lv.color32_make(1, 2, 3, 4), lambda x: (x.red, x.green, x.blue, x.alpha) == (1, 2, 3, 4), "independent four-byte color channels")
    check("", "color_16_16_mix", lambda: [lv.color_16_16_mix(0xf800, 0x1f, n) for n in (0, 255)], lambda x: x == [0x1f, 0xf800], "RGB565 blend endpoints")
    check("", "color24_luminance", lambda: [lv.color24_luminance(bytes([n] * 3)) for n in (0, 255)], lambda x: x == [0, 255], "black/white byte-array luminance")
    check("", "palette_main", lambda: lv.palette_main(lv.PALETTE.RED).to_int(), lambda x: x == 0xf44336, "Material Red500 palette value")
    check("", "palette_lighten", lambda: lv.palette_lighten(lv.PALETTE.RED, 1).to_int(), lambda x: x == 0xef5350, "Material Red400 palette value")
    check("", "palette_darken", lambda: lv.palette_darken(lv.PALETTE.RED, 1).to_int(), lambda x: x == 0xe53935, "Material Red600 palette value")
    for name in ("strdup", "strndup"):
        args = ("duplicate",) if name == "strdup" else ("duplicate", 3)
        expected = "duplicate" if name == "strdup" else "dup"
        check("", name, lambda name=name, args=args: getattr(lv, name)(*args), lambda x, expected=expected: x == expected, "native allocated string copies requested bytes")
    pixels = bytearray(b"\x00\xf8\xe0\x07\x1f\x00")
    check("", "draw_sw_rgb565_swap", lambda: (lv.draw_sw_rgb565_swap(pixels, 3), pixels.hex())[1], lambda x: x == "f80007e0001f", "three RGB565 words byte-swapped in place")
    bits = bytearray(b"\x00\x55\xff")
    check("", "draw_sw_i1_invert", lambda: (lv.draw_sw_i1_invert(bits, 3), bits.hex())[1], lambda x: x == "ffaa00", "one-bit pixel inversion across all bits")
    source, destination = bytes([0x80]), bytearray(32)
    check("", "draw_sw_i1_to_argb8888", lambda: (lv.draw_sw_i1_to_argb8888(source, destination, 8, 1, 1, 32, -16777216, -1), destination.hex())[1], lambda x: x == (b"\xff" * 4 + b"\x00\x00\x00\xff" * 7).hex(), "known bit pattern expands to independent ARGB pixel bytes")
    source, destination = bytes(range(8)), bytearray(8)
    check("", "draw_sw_rotate", lambda: (lv.draw_sw_rotate(source, destination, 2, 2, 4, 4, lv.DISPLAY_ROTATION._180, lv.COLOR_FORMAT.RGB565), destination.hex())[1], lambda x: x == bytes([6, 7, 4, 5, 2, 3, 0, 1]).hex(), "two by two RGB565 pixels rotate 180 degrees")
    count = lv.style_get_num_custom_props()
    prop = lv.style_register_prop(0)
    check("", "style_register_prop", lambda: prop, lambda x: x > 0 and lv.style_get_num_custom_props() == count + 1, "custom property allocation increases actual registry")
    check("", "style_get_num_custom_props", lv.style_get_num_custom_props, lambda x: x == count + 1, "custom property registry cardinality")
    check("", "style_prop_get_default", lambda: lv.style_prop_get_default(lv.STYLE.OPA).num, lambda x: x == 255, "opacity default is fully opaque")
    for name, args, expected in (("clamp_width", (40, 10, 30, 100), 30), ("clamp_height", (5, 10, 30, 100), 10)):
        check("", name, lambda name=name, args=args: getattr(lv, name)(*args), lambda x, expected=expected: x == expected, "explicit min/max dimension clamp")
    ident = lv.event_register_id()
    check("", "event_register_id", lambda: lv.event_register_id(), lambda x: x == ident + 1, "consecutive custom event IDs are distinct and increasing")
    check("", "event_code_get_name", lambda: lv.event_code_get_name(lv.EVENT.CLICKED), lambda x: "CLICKED" in x, "known native event has its symbolic name")


def classes(lv):
    display = lv.display_create(32, 32)
    screen = display.get_screen_active()
    parent = lv.obj(screen)
    cls = parent.get_class()
    child = cls.create_obj(parent)
    child.class_init_obj()
    child.set_size(7, 9)
    child.update_layout()
    check("obj_class_t", "create_obj", lambda: (child.get_parent() == parent, child.get_width(), child.get_height()), lambda x: x == (True, 7, 9), "class-created initialized object has supplied parent and geometry")
    event_codes = []
    def event_callback(event):
        event_codes.append(cls.event_base(event))
    child.add_event_cb(event_callback, lv.EVENT.CLICKED, None)
    child.send_event(lv.EVENT.CLICKED, None)
    check("obj_class_t", "event_base", lambda: list(event_codes), lambda x: x == [lv.RESULT.OK], "real child event passes through its native base class handler")
    display.delete()


def run():
    import lvgl as lv
    lv.init()
    for name, action in (("styles", styles), ("descriptors", descriptors), ("utilities", utilities), ("classes", classes)):
        try:
            action(lv)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": name + "_fixture", "status": "NOT_RUN", "oracle": repr(error)}))
    lv.deinit()


try:
    run()
except Exception as error:
    print("LVGL_DESCRIPTORS_ERROR", repr(error))
print("LVGL_DESCRIPTORS_DONE")
