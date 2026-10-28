"""Fourteen independent native object-namespace recipes on stock firmware.

Every target gets its own owned resources and result. A typed argument rejected
by the target binding is recorded for that method only. Opaque matrix backing
is retained; returned transform bytes are copied before reset can free them.
"""
import json
import struct
import lvgl as lv

METHODS = (
    "dump_tree", "set_transform", "reset_transform", "get_transform",
    "class_create_obj", "class_init_obj", "event_base", "is_valid", "redraw",
    "style_init", "style_deinit", "style_create_transition",
    "style_state_compare", "destruct",
)
stage = "setup"


def emit(method, status, oracle, value=None):
    print("M5EMU_UI_RESULT " + json.dumps({
        "api_target": "lvgl.obj", "method": method, "status": status,
        "oracle": oracle, "value": value,
    }))


def invoke(function, *args):
    global stage
    stage = "target"
    result = function(*args)
    stage = "oracle"
    return result


def assertion(ok, oracle, value):
    return "STATE_PASS" if ok else "FAIL", oracle, value


def remove(obj):
    if obj is not None:
        try:
            obj.delete()
        except Exception as error:
            print("OBJ_NAMESPACE_CLEANUP_ERROR " + repr(error))


def make(parent=None):
    obj = lv.obj(screen if parent is None else parent)
    obj.remove_style_all()
    obj.set_pos(0, 0)
    obj.set_size(8, 8)
    obj.update_layout()
    return obj


def dump_tree():
    parent = make()
    try:
        first, second = make(parent), make(parent)
        make(first)
        print("OBJ_NAMESPACE_TREE_BEGIN")
        result = invoke(lv.obj.dump_tree, parent)
        print("OBJ_NAMESPACE_TREE_END")
        shape = [parent.get_child_count(), first.get_child_count(), second.get_child_count()]
        if result is not None or shape != [2, 1, 0]:
            return assertion(False, "native dump must preserve the complete owned 2/1/0 hierarchy", shape)
        return "CALL_OK", "native dump was called on the exact owned 2/1/0 tree; log formatting/output requires an enabled native logger and is not granted a functional PASS", shape
    finally:
        remove(parent)


def matrix_fixture():
    values = (1.0, 0.0, 7.0, 0.0, 1.0, 9.0, 0.0, 0.0, 1.0)
    backing = bytearray(struct.pack("9f", *values))
    return lv.matrix_t.__cast__(backing), backing, values


def transform(method):
    obj = make()
    try:
        matrix, backing, expected = matrix_fixture()
        if method == "set_transform":
            invoke(lv.obj.set_transform, obj, matrix)
        else:
            obj.set_transform(matrix)
        if method == "get_transform":
            current = invoke(lv.obj.get_transform, obj)
        else:
            current = obj.get_transform()
        # Copy before reset/delete: current is owned by the native object.
        before = tuple(struct.unpack("9f", current.__dereference__(36))) if current is not None else None
        if method == "reset_transform":
            invoke(lv.obj.reset_transform, obj)
            after = obj.get_transform()
        else:
            after = current
        if before is None:
            return "BLOCKED_BUILD_CONFIG", "legal typed affine matrix is not adopted and native get_transform remains NULL; this matches the official LV_DRAW_TRANSFORM_USE_MATRIX-disabled path, so no transform PASS is granted", {"matrix_bytes": len(backing), "before": None, "after": None if after is None else repr(after)}
        if method == "reset_transform":
            return assertion(before == expected and after is None, "native reset removes the previously verified owned 3x3 affine matrix", {"before": before, "after_null": after is None})
        return assertion(before == expected, "native object returns the exact independent 3x3 affine coefficients before any freeing operation", before)
    finally:
        remove(obj)


def class_create_obj():
    parent = make()
    try:
        cls = parent.get_class()
        child = invoke(lv.obj.class_create_obj, cls, parent)
        actual = [child is not None, parent.get_child_count(), child.get_parent() == parent,
                  child.get_class() == cls]
        # Finish construction only after the raw allocation oracle is captured.
        child.class_init_obj()
        return assertion(actual == [True, 1, True, True], "exact typed native class allocates one child attached to the requested owned parent", actual)
    finally:
        remove(parent)


def class_init_obj():
    parent = make()
    try:
        cls = parent.get_class()
        # Canonical class-instance alias supplies a fresh uninitialized object.
        child = cls.create_obj(parent)
        before = child.has_flag(lv.obj.FLAG.CLICKABLE)
        invoke(lv.obj.class_init_obj, child)
        actual = [before, child.has_flag(lv.obj.FLAG.CLICKABLE),
                  child.get_parent() == parent, parent.get_child_count()]
        return assertion(actual == [False, True, True, 1], "native base constructor changes the raw object's clickable flag and preserves the exact parent relation", actual)
    finally:
        remove(parent)


def event_base():
    parent = make()
    child = lv.button(parent)
    values, errors = [], []
    cls = child.get_class()

    def callback(event):
        try:
            code, target = event.get_code(), event.get_current_target()
            result = lv.obj.event_base(cls, event)
            values.append([code, target == child, result])
        except Exception as error:
            errors.append([isinstance(error, TypeError), repr(error)])

    try:
        child.add_event_cb(callback, lv.EVENT.CLICKED, None)
        child.send_event(lv.EVENT.CLICKED, None)
        if errors:
            return "UNSUPPORTED_BINDING" if errors[0][0] else "FAIL", "actual callback event and native button class were passed to the exact foreign-class object namespace helper", errors
        return assertion(values == [[lv.EVENT.CLICKED, True, lv.RESULT.OK]], "native base event handler returns OK for the exact button-class CLICKED event and original current target", values)
    finally:
        remove(parent)


def is_valid():
    obj = make()
    try:
        owned = invoke(lv.obj.is_valid, obj)
        try:
            null = invoke(lv.obj.is_valid, None)
        except TypeError as error:
            return "UNSUPPORTED_BINDING", "owned live object validation returned its native value, but the namespace binding rejects the C API's NULL negative case", {"owned": owned, "null_error": repr(error)}
        actual = [owned, null]
        return assertion(actual == [True, False], "native live-tree search accepts the owned object and rejects NULL", actual)
    finally:
        remove(obj)


def redraw():
    canvas, obj = None, None
    try:
        canvas = lv.canvas(screen)
        canvas.set_size(8, 8)
        raw = bytearray(8 * 8 * 4 + 16)
        raw[-16:] = b"REDRAW-GUARD-18!"
        canvas.set_buffer(raw, 8, 8, lv.COLOR_FORMAT.ARGB8888)
        canvas.fill_bg(lv.color_hex(0), 0)
        obj = make()
        obj.set_style_bg_color(lv.color_hex(0x336699), 0)
        obj.set_style_bg_opa(255, 0)
        obj.update_layout()
        layer = lv.layer_t()
        lv.refr_set_disp_refreshing(display)
        canvas.init_layer(layer)
        invoke(lv.obj.redraw, layer, obj)
        canvas.finish_layer(layer)
        expected = bytes([153, 102, 51, 255]) * 64
        pixels = bytes(raw[:256])
        actual = [pixels == expected, bytes(raw[256:]) == b"REDRAW-GUARD-18!", len(pixels)]
        return assertion(actual == [True, True, 256], "native foreign-layer redraw writes all 64 exact ARGB8888 pixels and preserves the separate buffer guard", actual)
    finally:
        lv.refr_set_disp_refreshing(None)
        remove(obj)
        remove(canvas)


def transition_recipe(target):
    obj = make()
    try:
        obj.set_style_width(11, 0)
        obj.set_style_width(37, lv.STATE.PRESSED)
        tr = lv.obj_style_transition_dsc_t()
        tr.time, tr.delay, tr.selector, tr.prop = 60, 0, 0, lv.STYLE.WIDTH
        native = lv.anim_t()
        native.init()
        tr.path_cb = native.path_cb
        tr.user_data = None
        count_before = lv.anim_count_running()
        if target:
            invoke(lv.obj.style_create_transition, obj, 0, 0, lv.STATE.PRESSED, tr)
        else:
            obj.style_create_transition(0, 0, lv.STATE.PRESSED, tr)
        count_active = lv.anim_count_running()
        widths = [obj.get_style_width(0)]
        for _ in range(8):
            lv.tick_inc(15)
            lv.timer_handler()
            widths.append(obj.get_style_width(0))
        actual = {"before": count_before, "active": count_active,
                  "after": lv.anim_count_running(), "widths": widths}
        ok = count_active == count_before + 1 and widths[0] == 11 and widths[-1] == 37 and any(11 < width < 37 for width in widths) and actual["after"] == count_before
        return ok, actual
    finally:
        remove(obj)


def style_init():
    # The preceding recipes have no live transitions. An empty-list init is safe.
    invoke(lv.obj.style_init)
    ok, actual = transition_recipe(False)
    return assertion(ok, "explicitly initialized native style manager schedules a real 11-to-37 width transition with interior samples and removes it on completion", actual)


def style_deinit():
    initial = lv.style_get_num_custom_props()
    first = lv.style_register_prop(0)
    second = lv.style_register_prop(0)
    count = lv.style_get_num_custom_props()
    invoke(lv.obj.style_deinit)
    # Registration restarts at the first custom ID only when deinit freed and
    # cleared the actual custom-property table. No stale property is attached.
    fresh = lv.style_register_prop(0)
    reset_count = lv.style_get_num_custom_props()
    lv.obj.style_init()
    actual = [initial, first, second, count, fresh, reset_count]
    return assertion(initial == 0 and second == first + 1 and count == 2 and fresh == first and reset_count == 1,
                     "native deinit clears the real custom-property registry; the next registration reuses its first ID and resets the count", actual)


def style_create_transition():
    ok, actual = transition_recipe(True)
    return assertion(ok, "exact typed internal transition descriptor schedules native work, passes interior widths and reaches the independent 37px target", actual)


def style_state_compare():
    obj = make()
    try:
        obj.set_style_width(11, 0)
        obj.set_style_width(37, lv.STATE.PRESSED)
        same = invoke(lv.obj.style_state_compare, obj, 0, 0)
        changed = invoke(lv.obj.style_state_compare, obj, 0, lv.STATE.PRESSED)
        return assertion([same, changed] == [0, 3], "native comparison returns exact SAME=0 and DIFF_LAYOUT=3 for an independent width-only pressed style", [same, changed])
    finally:
        remove(obj)


def destruct():
    parent = make()
    group = lv.group_create()
    try:
        # The exact registered base class avoids an unregistered subclass
        # wrapper dependency. Its raw object has no constructor-owned ID.
        obj = parent.get_class().create_obj(parent)
        obj.set_style_width(41, 0)
        hits = []
        obj.add_event_cb(lambda event: hits.append(event.get_code()), lv.EVENT.CLICKED, None)
        group.add_obj(obj)
        before = [obj.get_style_width(0), obj.get_event_count(), group.get_obj_count()]
        class_width = obj.get_class().width_def
        invoke(lv.obj.destruct, obj)
        local_value = lv.style_value_t()
        local_status = obj.get_local_style_prop(lv.STYLE.WIDTH, local_value, 0)
        after = [obj.get_event_count(), group.get_obj_count(), obj.get_group() is None,
                 local_status, obj.get_style_width(0), parent.get_child_count()]
        return assertion(before[0] == 41 and before[1] >= 1 and before[2] == 1 and after == [0, 0, True, 0, class_width, 1],
                         "native base destructor removes local WIDTH (typed NOT_FOUND), restores the class default, clears callbacks/group membership and leaves allocation/tree ownership to its caller", {"before": before, "after": after, "class_width": class_width})
    finally:
        remove(parent)
        group.delete()


lv.init()
display = lv.display_create(64, 64)
draw_buffer = bytearray(64 * 64 * 2)
display.set_color_format(lv.COLOR_FORMAT.RGB565)
display.set_buffers(draw_buffer, None, len(draw_buffer), lv.DISPLAY_RENDER_MODE.PARTIAL)
display.set_flush_cb(lambda actual_display, area, pixels: actual_display.flush_ready())
screen = display.get_screen_active()
for method in METHODS:
    stage = "setup"
    print("OBJ_NAMESPACE_BEGIN " + method)
    try:
        if method in ("set_transform", "reset_transform", "get_transform"):
            status, oracle, value = transform(method)
        else:
            status, oracle, value = globals()[method]()
        emit(method, status, oracle, value)
    except Exception as error:
        status = "UNSUPPORTED_BINDING" if stage == "target" and isinstance(error, TypeError) else "FAIL"
        emit(method, status, "independent legal typed recipe; failure phase=" + stage, repr(error))
display.delete()
lv.deinit()
print("LVGL_OBJ_NAMESPACE_STOCK_DONE")
