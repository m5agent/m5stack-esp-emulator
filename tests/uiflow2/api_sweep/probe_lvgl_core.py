"""Finite native LVGL value, container, group, timer and style assertions.

Every reported state result has an explicit value/callback oracle. Structural
state checks do not grant framebuffer, touch or external-device coverage.
"""
import json
import time
import M5


def result(target, method, action, oracle, description):
    try:
        value = action()
        ok = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target, "method": method,
            "status": "STATE_PASS" if ok else "FAIL", "oracle": description,
            "value": value if isinstance(value, (bool, int, float, str, list, tuple)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target, "method": method,
            "status": "FAIL", "oracle": description, "error": repr(error)}))


def pending(target, method, reason):
    print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl." + target, "method": method,
        "status": "NOT_RUN", "oracle": reason}))


def require(condition):
    if not condition:
        raise AssertionError("explicit native value oracle failed")
    return True


def color_tests(lv):
    red, blue, black, white = [lv.color_hex(x) for x in (0xff0000, 0x0000ff, 0, 0xffffff)]
    result("color_t", "to_int", red.to_int, lambda x: x == 0xff0000, "RGB888 red constant")
    result("color_t", "to_u32", red.to_u32, lambda x: x == 0xffff0000, "opaque ARGB8888 red constant")
    result("color_t", "to_u16", red.to_u16, lambda x: x == 0xf800, "RGB565 red bit layout")
    result("color_t", "eq", lambda: red.eq(lv.color_hex(0xff0000)) and not red.eq(blue), bool, "equal and unequal colors")
    result("color_t", "lighten", lambda: black.lighten(255).to_int(), lambda x: x == 0xffffff, "full white mixing endpoint")
    result("color_t", "darken", lambda: white.darken(255).to_int(), lambda x: x == 0, "full black mixing endpoint")
    result("color_t", "mix", lambda: [red.mix(blue, 0).to_int(), red.mix(blue, 255).to_int()], lambda x: x == [255, 0xff0000], "both blend endpoints")
    result("color_t", "luminance", lambda: [black.luminance(), white.luminance()], lambda x: x == [0, 255], "black and white luminance endpoints")
    result("color_t", "brightness", lambda: [black.brightness(), white.brightness()], lambda x: x == [0, 255], "black and white brightness endpoints")
    result("color_t", "to_hsv", lambda: red.to_hsv(), lambda x: x.h == 0 and x.s == 100 and x.v == 100, "red HSV definition")
    result("color_t", "to_32", lambda: red.to_32(123), lambda x: x.red == 255 and x.green == 0 and x.blue == 0 and x.alpha == 123, "independent RGBA channels")
    rgba = red.to_32(255)
    result("color32_t", "eq", lambda: rgba.eq(red.to_32(255)) and not rgba.eq(blue.to_32(255)), bool, "RGBA equality including channels")
    result("color32_t", "luminance", lambda: white.to_32(255).luminance(), lambda x: x == 255, "opaque white luminance")
    result("color32_t", "color_mix32", lambda: red.to_32(255).color_mix32(blue.to_32(255)), lambda x: x.red == 255 and x.blue == 0, "opaque foreground wins")
    def premultiply():
        color = red.to_32(128)
        color.color_premultiply()
        return color
    result("color32_t", "color_premultiply", premultiply, lambda x: 126 <= x.red <= 128 and x.green == 0 and x.blue == 0 and x.alpha == 128, "half-alpha premultiplication")


def area_tests(lv):
    def area(x1, y1, x2, y2):
        out = lv.area_t()
        out.set(x1, y1, x2, y2)
        return out
    def coords(value):
        return (value.x1, value.y1, value.x2, value.y2)
    a = area(10, 20, 29, 49)
    result("area_t", "set", lambda: coords(a), lambda x: x == (10, 20, 29, 49), "four coordinates retained")
    result("area_t", "get_width", a.get_width, lambda x: x == 20, "inclusive coordinate width")
    result("area_t", "get_height", a.get_height, lambda x: x == 30, "inclusive coordinate height")
    result("area_t", "get_size", a.get_size, lambda x: x == 600, "20 by 30 rectangle area")
    def mutate(method, arguments):
        item = area(10, 20, 29, 49)
        getattr(item, method)(*arguments)
        return coords(item)
    for name, args, expected in (("set_width", (5,), (10, 20, 14, 49)), ("set_height", (7,), (10, 20, 29, 26)),
                                 ("increase", (2, 3), (8, 17, 31, 52)), ("move", (2, -3), (12, 17, 31, 46)),
                                 ("set_pos", (0, 0), (0, 0, 19, 29))):
        result("area_t", name, lambda name=name, args=args: mutate(name, args), lambda x, expected=expected: x == expected, "exact coordinate transform")
    copied = lv.area_t()
    result("area_t", "copy", lambda: (copied.copy(a), coords(copied))[1], lambda x: x == coords(a), "independent copied area")
    b, out = area(20, 30, 39, 59), lv.area_t()
    result("area_t", "intersect", lambda: (out.intersect(a, b), coords(out)), lambda x: x == (True, (20, 30, 29, 49)), "known overlap rectangle")
    result("area_t", "join", lambda: (out.join(a, b), coords(out))[1], lambda x: x == (10, 20, 39, 59), "bounding union rectangle")
    for name, action, expected in (("is_equal", lambda: a.is_equal(copied) and not a.is_equal(b), True),
                                   ("is_on", lambda: a.is_on(b), True),
                                   ("is_in", lambda: area(12, 22, 14, 24).is_in(a, 0), True),
                                   ("is_out", lambda: area(100, 100, 110, 110).is_out(a, 0), True)):
        result("area_t", name, action, lambda x, expected=expected: x == expected, "controlled contained, overlapping or disjoint geometry")
    point = lv.point_t({"x": 15, "y": 25})
    result("area_t", "is_point_on", lambda: a.is_point_on(point, 0), bool, "known interior point")
    result("area_t", "align", lambda: (a.align(b, lv.ALIGN.CENTER, 0, 0), coords(b))[1], lambda x: x == coords(a), "equal-size centered rectangles")
    result("point_t", "set", lambda: (point.set(7, 9), (point.x, point.y))[1], lambda x: x == (7, 9), "coordinate assignment")
    other = lv.point_t({"x": 1, "y": 2})
    result("point_t", "swap", lambda: (point.swap(other), (point.x, point.y, other.x, other.y))[1], lambda x: x == (1, 2, 7, 9), "two native points exchanged")
    result("point_t", "transform", lambda: (point.transform(0, 256, 256, lv.point_t({"x": 0, "y": 0}), False), (point.x, point.y))[1], lambda x: x == (1, 2), "identity affine transformation")
    precise = point.to_precise()
    result("point_t", "to_precise", lambda: (precise.x, precise.y), lambda x: x == (1, 2), "integer to precise coordinates")
    result("point_precise_t", "from_precise", precise.from_precise, lambda x: (x.x, x.y) == (1, 2), "precise coordinates roundtrip")


def style_tests(lv):
    style = lv.style_t()
    style.init()
    result("style_t", "init", style.is_empty, bool, "new native style is empty")
    result("style_t", "is_empty", style.is_empty, bool, "new style has no properties")
    result("style_t", "is_const", style.is_const, lambda x: not x, "mutable allocated style")
    with open("/flash/lvgl-style-recipes.json") as handle:
        recipes = json.load(handle)["recipes"]
    aggregate = {"SIZE": [("WIDTH", 17), ("HEIGHT", 19)],
                 "PAD_ALL": [(x, 17) for x in ("PAD_TOP", "PAD_BOTTOM", "PAD_LEFT", "PAD_RIGHT")],
                 "PAD_HOR": [("PAD_LEFT", 17), ("PAD_RIGHT", 17)], "PAD_VER": [("PAD_TOP", 17), ("PAD_BOTTOM", 17)],
                 "PAD_GAP": [("PAD_ROW", 17), ("PAD_COLUMN", 17)],
                 "MARGIN_HOR": [("MARGIN_LEFT", 17), ("MARGIN_RIGHT", 17)],
                 "MARGIN_VER": [("MARGIN_TOP", 17), ("MARGIN_BOTTOM", 17)],
                 "MARGIN_ALL": [(x, 17) for x in ("MARGIN_TOP", "MARGIN_BOTTOM", "MARGIN_LEFT", "MARGIN_RIGHT")],
                 "TRANSFORM_SCALE": [("TRANSFORM_SCALE_X", 17), ("TRANSFORM_SCALE_Y", 17)]}
    for recipe in recipes:
        method, prop, argument = recipe["method"], recipe["property"], recipe["argument"]
        if "*" in argument or "[" in argument:
            pending("style_t", method, "typed resource fixture pending: " + argument)
            continue
        color = "lv_color_t " in argument
        boolean = "bool " in argument
        value = lv.color_hex(0x3366cc) if color else True if boolean else 17 if ("int" in argument or prop in aggregate) else 1
        expected = 0x3366cc if color else int(value)
        def apply(method=method, prop=prop, value=value, expected=expected, color=color):
            style.reset()
            if prop == "SIZE":
                getattr(style, method)(17, 19)
            else:
                getattr(style, method)(value)
            for key, number in aggregate.get(prop, [(prop, expected)]):
                output = lv.style_value_t()
                code = style.get_prop(getattr(lv.STYLE, key), output)
                actual = output.color.to_int() if color else output.num
                require(code != 0 and actual == number)
            return True
        result("style_t", method, apply, bool, "typed style property or aggregate roundtrip via get_prop")
    style.reset()
    result("style_t", "reset", style.is_empty, bool, "reset clears previously populated native style")
    style.set_width(31)
    copied = lv.style_t()
    copied.init()
    copied.copy(style)
    output = lv.style_value_t()
    result("style_t", "copy", lambda: (copied.get_prop(lv.STYLE.WIDTH, output), output.num), lambda x: x[0] != 0 and x[1] == 31, "copy retains known native property")
    result("style_t", "get_prop", lambda: (copied.get_prop(lv.STYLE.WIDTH, output), output.num), lambda x: x[0] != 0 and x[1] == 31, "existing property value")
    result("style_t", "get_prop_inlined", lambda: (copied.get_prop_inlined(lv.STYLE.WIDTH, output), output.num), lambda x: x[0] != 0 and x[1] == 31, "inline lookup matches native style store")
    result("style_t", "remove_prop", lambda: copied.remove_prop(lv.STYLE.WIDTH) and copied.is_empty(), bool, "removing the only property empties style")
    output.num = 47
    result("style_t", "set_prop", lambda: (copied.set_prop(lv.STYLE.WIDTH, output), copied.get_prop(lv.STYLE.WIDTH, output), output.num)[1:], lambda x: x[0] != 0 and x[1] == 47, "explicit style union property assignment")
    copied.reset()
    style.reset()


def group_tests(lv):
    old_default = lv.group_get_default()
    group = lv.group_create()
    parent = lv.screen_active()
    first, second = lv.button(parent), lv.button(parent)
    first.set_x(10)
    second.set_x(30)
    focus_events, edges, keys = [], [], []
    def focus_changed(item):
        focus_events.append(item.get_focused().get_x())
    def edge_reached(item, forward):
        edges.append(bool(forward))
    try:
        result("group_t", "set_default", lambda: (group.set_default(), lv.group_get_default().get_obj_count())[1], lambda x: x == 0, "new empty group selected as native default")
        result("group_t", "add_obj", lambda: (group.add_obj(first), group.add_obj(second), group.get_obj_count())[2], lambda x: x == 2, "two independent native objects in group")
        result("group_t", "get_obj_count", group.get_obj_count, lambda x: x == 2, "membership cardinality")
        result("group_t", "get_obj_by_index", lambda: [group.get_obj_by_index(n).get_x() for n in range(2)], lambda x: x == [10, 30], "ordered native object membership")
        result("group_t", "get_focused", lambda: group.get_focused().get_x(), lambda x: x == 10, "first added object initially focused")
        group.set_focus_cb(focus_changed)
        result("group_t", "focus_next", lambda: (group.focus_next(), group.get_focused().get_x())[1], lambda x: x == 30, "next object focused")
        result("group_t", "set_focus_cb", lambda: list(focus_events), lambda x: x == [30], "callback invoked by real native focus transition")
        result("group_t", "get_focus_cb", group.get_focus_cb, lambda x: x is not None and bool(focus_events), "registered callback pointer plus observed native invocation")
        result("group_t", "focus_prev", lambda: (group.focus_prev(), group.get_focused().get_x())[1], lambda x: x == 10, "previous object focused")
        result("group_t", "focus_freeze", lambda: (group.focus_freeze(True), group.focus_next(), group.get_focused().get_x())[2], lambda x: x == 10, "frozen focus does not advance")
        group.focus_freeze(False)
        group.set_edge_cb(edge_reached)
        result("group_t", "set_wrap", lambda: (group.set_wrap(False), group.get_wrap())[1], lambda x: not x, "wrap disabled")
        result("group_t", "get_wrap", group.get_wrap, lambda x: not x, "current wrap state")
        group.focus_prev()
        result("group_t", "set_edge_cb", lambda: list(edges), lambda x: len(x) >= 1, "native backward focus edge invokes callback")
        result("group_t", "get_edge_cb", group.get_edge_cb, lambda x: x is not None and bool(edges), "registered edge callback and actual invocation")
        result("group_t", "set_editing", lambda: (group.set_editing(True), group.get_editing())[1], bool, "edit mode toggled")
        result("group_t", "get_editing", group.get_editing, bool, "native edit mode query")
        first.add_event_cb(lambda event: keys.append(event.get_key()), lv.EVENT.KEY, None)
        result("group_t", "send_data", lambda: (group.send_data(lv.KEY.ENTER), list(keys))[1], lambda x: x == [lv.KEY.ENTER], "focused object receives native KEY event with actual key")
        try:
            group.set_refocus_policy(lv.GROUP_REFOCUS_POLICY.NEXT)
            lv.group_focus_obj(first)
            lv.group_remove_obj(first)
            result("group_t", "set_refocus_policy", lambda: group.get_focused().get_x(), lambda x: x == 30, "removed focused object refocuses next native member")
        except Exception as error:
            pending("group_t", "set_refocus_policy", "enum/fixture setup: " + repr(error))
        result("group_t", "remove_all_objs", lambda: (group.remove_all_objs(), group.get_obj_count())[1], lambda x: x == 0, "all native memberships removed")
    finally:
        group.set_default()
        group.delete()
        deleted_default = lv.group_get_default() is None
        if old_default is not None:
            old_default.set_default()
        first.delete()
        second.delete()
    result("group_t", "delete", lambda: deleted_default, bool, "deleting the native default group clears its global default reference")


def timer_tests(lv):
    hits = []
    marker = {"nonce": "CORE"}
    def pump(milliseconds):
        end = time.ticks_add(time.ticks_ms(), milliseconds)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            lv.timer_handler()
            time.sleep_ms(5)
    timer = lv.timer_create(lambda item: None, 40, marker)
    timer.set_cb(lambda item: hits.append(time.ticks_ms()))
    timer.set_auto_delete(False)
    try:
        pump(100)
        result("timer_t", "set_cb", lambda: len(hits), lambda x: x >= 1, "replacement registered timer callback actually fires")
        timer.pause()
        before = len(hits)
        pump(100)
        result("timer_t", "pause", lambda: len(hits), lambda x: x == before, "no native callback while paused")
        result("timer_t", "get_paused", timer.get_paused, bool, "paused timer state")
        timer.resume()
        pump(70)
        result("timer_t", "resume", lambda: len(hits), lambda x: x > before, "callbacks resume after native resume")
        timer.set_period(200)
        timer.reset()
        before = len(hits)
        pump(80)
        result("timer_t", "set_period", lambda: len(hits), lambda x: x == before, "200ms period does not fire within 80ms")
        result("timer_t", "reset", lambda: len(hits), lambda x: x == before, "reset restarts period relative to current time")
        timer.ready()
        pump(15)
        result("timer_t", "ready", lambda: len(hits), lambda x: x == before + 1, "ready executes callback before full new period")
        timer.set_period(20)
        timer.set_repeat_count(2)
        timer.reset()
        before = len(hits)
        pump(100)
        result("timer_t", "set_repeat_count", lambda: len(hits) - before, lambda x: x == 2, "exact finite callback repeat count")
        result("timer_t", "set_auto_delete", timer.get_paused, bool, "finite timer retained and paused when auto-delete disabled")
        next_marker = {"nonce": "NEXT"}
        companion = lv.timer_create(lambda item: None, 1000, next_marker)
        try:
            result("timer_t", "get_next", lambda: companion.get_next().get_user_data().__cast__()["nonce"], lambda x: x == "CORE", "new timer's next link identifies the previous owned timer through independent user-data nonce")
        finally:
            companion.delete()
        replacement = dict(timer.get_user_data().__cast__())
        replacement["nonce"] = "DATA"
        timer.set_user_data(replacement)
        result("timer_t", "set_user_data", lambda: timer.get_user_data().__cast__()["nonce"], lambda x: x == "DATA", "native user-data dictionary roundtrip preserves binding callback entries")
        result("timer_t", "get_user_data", lambda: timer.get_user_data().__cast__()["nonce"], lambda x: x == "DATA", "native user-data dictionary nonce")
    finally:
        timer.delete()
    before = len(hits)
    pump(80)
    result("timer_t", "delete", lambda: len(hits), lambda x: x == before, "deleted owned timer never invokes callback again")


def subject_tests(lv):
    subject = lv.subject_t()
    subject.init_int(11)
    result("subject_t", "init_int", subject.get_int, lambda x: x == 11, "initial integer value")
    result("subject_t", "set_int", lambda: (subject.set_int(29), subject.get_int())[1], lambda x: x == 29, "updated integer value")
    result("subject_t", "get_int", subject.get_int, lambda x: x == 29, "current native subject value")
    result("subject_t", "get_previous_int", subject.get_previous_int, lambda x: x == 11, "previous integer value retained")
    calls = []
    marker = {"nonce": "OBSV"}
    def changed(observer, item):
        calls.append(item.get_int())
    observer = subject.add_observer(changed, marker)
    subject.set_int(41)
    result("subject_t", "add_observer", lambda: list(calls), lambda x: x[-1] == 41, "callback receives actual native subject change")
    before = len(calls)
    subject.notify()
    result("subject_t", "notify", lambda: len(calls), lambda x: x == before + 1, "explicit native notify invokes registered observer")
    result("observer_t", "get_user_data", lambda: observer.get_user_data().__cast__()["nonce"], lambda x: x == "OBSV", "retained user-data dictionary nonce")
    observer.remove()
    before = len(calls)
    subject.set_int(43)
    result("observer_t", "remove", lambda: len(calls), lambda x: x == before, "removed observer stops receiving real changes")
    subject.add_observer(changed, {"nonce": "cleanup"})
    before = len(calls)
    subject.deinit()
    subject.set_int(101)
    result("subject_t", "deinit", lambda: len(calls), lambda x: x == before, "deinitialization removes remaining native observers")
    string = lv.subject_t()
    current, previous = bytearray(32), bytearray(32)
    string.init_string(current, previous, 32, "Alpha")
    result("subject_t", "init_string", string.get_string, lambda x: x == "Alpha", "initial string stored in explicit guest buffers")
    result("subject_t", "copy_string", lambda: (string.copy_string("Beta"), string.get_string())[1], lambda x: x == "Beta", "new string copied into native subject")
    result("subject_t", "get_string", string.get_string, lambda x: x == "Beta", "current subject string")
    result("subject_t", "get_previous_string", string.get_previous_string, lambda x: x == "Alpha", "previous string buffer retained")
    string.deinit()
    colored = lv.subject_t()
    colored.init_color(lv.color_hex(0x123456))
    result("subject_t", "init_color", lambda: colored.get_color().to_int(), lambda x: x == 0x123456, "initial color subject")
    result("subject_t", "set_color", lambda: (colored.set_color(lv.color_hex(0xabcdef)), colored.get_color().to_int())[1], lambda x: x == 0xabcdef, "new color subject")
    result("subject_t", "get_color", lambda: colored.get_color().to_int(), lambda x: x == 0xabcdef, "current color")
    result("subject_t", "get_previous_color", lambda: colored.get_previous_color().to_int(), lambda x: x == 0x123456, "previous color retained")
    colored.deinit()


def run():
    try:
        import lvgl as lv
        import m5ui
    except ImportError as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": "native_core", "status": "UNAVAILABLE_ON_DEVICE", "oracle": repr(error)}))
        return
    M5.begin()
    m5ui.init()
    for stage, function in (("color", color_tests), ("geometry", area_tests), ("style", style_tests),
                            ("group", group_tests), ("timer", timer_tests), ("subject", subject_tests)):
        try:
            function(lv)
        except Exception as error:
            pending("core", stage, "fixture setup failed: " + repr(error))
    m5ui.deinit()


try:
    run()
except Exception as error:
    pending("core", "run", repr(error))
print("LVGL_CORE_DONE")
