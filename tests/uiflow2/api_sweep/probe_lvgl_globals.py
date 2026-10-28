"""Native LVGL module helpers with explicit byte/math/lifecycle oracles.

No display task or event loop runs during allocator tests. Allocated C buffers
remain owned until the matching native free; callbacks use None/dict according
to the generated binding convention.
"""
import json
import time


def check(method, action, oracle, description):
    try:
        value = action()
        passed = oracle(value)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": method,
            "status": "STATE_PASS" if passed else "FAIL", "oracle": description,
            "value": value if isinstance(value, (int, float, bool, str, list, tuple)) or value is None else repr(value)}))
        return value
    except Exception as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": method,
            "status": "FAIL", "oracle": description, "error": repr(error)}))


def memory(lv):
    data = bytearray(b"abcdefgh")
    check("memzero", lambda: (lv.memzero(data, 8), list(data))[1], lambda x: x == [0] * 8, "all destination bytes cleared")
    check("memset", lambda: (lv.memset(data, 0x5a, 8), bytes(data).decode())[1], lambda x: x == "ZZZZZZZZ", "all destination bytes filled")
    source = b"\x00\xffUTF8\xc3\xa9"
    check("memcpy", lambda: (lv.memcpy(data, source, 8), bytes(data).hex())[1], lambda x: x == source.hex(), "binary bytes copied including NUL and high bits")
    data[:] = b"abcdefgh"
    check("memmove", lambda: (lv.memmove(memoryview(data)[2:], data, 6), bytes(data).decode())[1], lambda x: x == "ababcdef", "overlapping forward memory move")
    check("memcmp", lambda: [lv.memcmp(b"abc", b"abc", 3), lv.memcmp(b"abc", b"abd", 3), lv.memcmp(b"abd", b"abc", 3)], lambda x: x[0] == 0 and x[1] < 0 and x[2] > 0, "equal and both lexical directions")
    for method, args in (("malloc", (8,)), ("calloc", (2, 4)), ("zalloc", (8,)), ("malloc_zeroed", (8,)), ("malloc_core", (8,))):
        allocation = getattr(lv, method)(*args)
        try:
            block = allocation.__dereference__(8)
            if method in ("calloc", "zalloc", "malloc_zeroed"):
                check(method, lambda: list(block), lambda x: x == [0] * 8, "zero-filled owned native allocation")
            else:
                block[:] = b"OWNEDBUF"
                check(method, lambda: bytes(allocation.__dereference__(8)).decode(), lambda x: x == "OWNEDBUF", "writable independently allocated C storage")
        finally:
            (lv.free_core if method == "malloc_core" else lv.free)(allocation)
    for method in ("realloc", "reallocf", "realloc_core"):
        allocation = (lv.malloc_core if method == "realloc_core" else lv.malloc)(4)
        allocation.__dereference__(4)[:] = b"KEEP"
        resized = getattr(lv, method)(allocation, 16)
        try:
            check(method, lambda: bytes(resized.__dereference__(4)).decode(), lambda x: x == "KEEP", "owned allocation grows without losing its prefix")
        finally:
            (lv.free_core if method == "realloc_core" else lv.free)(resized)
    for method in ("mem_test", "mem_test_core"):
        value = getattr(lv, method)()
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": method,
            "status": "BLOCKED_MODEL", "value": value,
            "oracle": "LV_STDLIB_MICROPYTHON implementation returns OK without checking allocator; consistency checking is unsupported"}))


def strings(lv):
    check("streq", lambda: [lv.streq("equal", "equal"), lv.streq("equal", "other")], lambda x: x == [True, False], "string equality and inequality")
    check("strlen", lambda: lv.strlen("中文"), lambda x: x == 6, "UTF8 byte length")
    check("strnlen", lambda: lv.strnlen("abcdef", 3), lambda x: x == 3, "bounded byte length")
    check("strcmp", lambda: [lv.strcmp("ab", "ab"), lv.strcmp("ab", "ac"), lv.strcmp("ac", "ab")], lambda x: x[0] == 0 and x[1] < 0 and x[2] > 0, "string comparison signs")
    check("strncmp", lambda: lv.strncmp("abcd", "abXY", 2), lambda x: x == 0, "comparison stops at requested byte count")
    for method in ("strlcpy", "strncpy", "strcpy"):
        destination = bytearray(16)
        if method == "strcpy":
            action = lambda: getattr(lv, method)(destination, "copy")
        else:
            action = lambda: getattr(lv, method)(destination, "copy", 16)
        check(method, lambda: (action(), bytes(destination[:5]).hex())[1], lambda x: x == b"copy\x00".hex(), "copied text and terminator in caller-owned buffer")
    for method in ("strcat", "strncat"):
        destination = bytearray(b"ab\x00" + b"\x00" * 13)
        action = lambda: lv.strcat(destination, "cd") if method == "strcat" else lv.strncat(destination, "cdef", 2)
        check(method, lambda: (action(), bytes(destination[:5]).hex())[1], lambda x: x == b"abcd\x00".hex(), "text appended after original terminator")
    destination = bytearray(5)
    check("strlcpy.truncation", lambda: (lv.strlcpy(destination, "abcdefgh", 5), bytes(destination).hex()), lambda x: x == (8, b"abcd\x00".hex()), "truncation is terminated and reports source length")
    check("strchr", lambda: lv.strchr("abc:def", ord(":")), lambda x: x == ":def", "first matching character returns suffix")


def arithmetic(lv):
    for method, args, expected in (("sqr", (-7,), 49), ("trigo_sin", (90,), 32768), ("trigo_cos", (0,), 32768),
                                    ("sqrt32", (144,), 12), ("pow", (3, 4), 81), ("map", (25, 0, 100, 0, 200), 50),
                                    ("atan2", (0, 1), 0), ("bezier3", (0, 7, 10, 20, 31), 0),
                                    ("cubic_bezier", (512, 0, 0, 1024, 1024), 512)):
        check(method, lambda method=method, args=args: getattr(lv, method)(*args), lambda x, expected=expected: x == expected, "independent exact arithmetic value")
    root = lv.sqrt_res_t()
    check("sqrt", lambda: (lv.sqrt(144, root, 0x8000), root.i)[1], lambda x: x == 12, "integer square root stored in native result struct")
    sequence = []
    lv.rand_set_seed(20261027)
    for _ in range(4):
        sequence.append(lv.rand(10, 100))
    lv.rand_set_seed(20261027)
    repeated = [lv.rand(10, 100) for _ in range(4)]
    check("rand_set_seed", lambda: sequence == repeated, bool, "same seed reproduces native pseudorandom sequence")
    check("rand", lambda: sequence, lambda x: all(10 <= v <= 100 for v in x) and len(set(x)) > 1, "range and actual sequence variation")
    check("pct", lambda: lv.pct_to_px(lv.pct(25), 200), lambda x: x == 50, "25 percent encoded against 200px reference")
    check("pct_to_px", lambda: lv.pct_to_px(lv.pct(75), 200), lambda x: x == 150, "75 percent decoded against 200px reference")
    check("color_hex", lambda: lv.color_hex(0x123456).to_int(), lambda x: x == 0x123456, "hexadecimal RGB channels")
    check("color_make", lambda: lv.color_make(0x12, 0x34, 0x56).to_int(), lambda x: x == 0x123456, "three separate RGB channels")
    check("color_hex3", lambda: lv.color_hex3(0xf0a).to_int(), lambda x: x == 0xff00aa, "nibble RGB expansion")
    check("color_white", lambda: lv.color_white().to_int(), lambda x: x == 0xffffff, "white RGB constant")
    check("color_black", lambda: lv.color_black().to_int(), lambda x: x == 0, "black RGB constant")
    check("color_hsv_to_rgb", lambda: lv.color_hsv_to_rgb(0, 100, 100).to_int(), lambda x: x == 0xff0000, "full red HSV endpoint")
    check("color_rgb_to_hsv", lambda: lv.color_rgb_to_hsv(255, 0, 0), lambda x: (x.h, x.s, x.v) == (0, 100, 100), "red channels to HSV")
    check("color_format_get_bpp", lambda: lv.color_format_get_bpp(lv.COLOR_FORMAT.RGB565), lambda x: x == 16, "RGB565 has 16 bits per pixel")
    check("color_format_get_size", lambda: lv.color_format_get_size(lv.COLOR_FORMAT.ARGB8888), lambda x: x == 4, "ARGB8888 has 4 bytes per pixel")
    check("color_format_has_alpha", lambda: [lv.color_format_has_alpha(lv.COLOR_FORMAT.ARGB8888), lv.color_format_has_alpha(lv.COLOR_FORMAT.RGB565)], lambda x: x == [True, False], "alpha and opaque format distinction")


def clocks(lv):
    # These two global setters have no containing user_data in the generated
    # binding. They accept native function pointers, not Python callables.
    # Use compatible native signatures and independently observe the effect.
    lv.tick_set_cb(lv.anim_count_running)
    check("tick_set_cb", lv.tick_get, lambda x: x == 0, "native callback reports zero owned animations")
    check("tick_get", lv.tick_get, lambda x: x == 0, "native tick callback return value")
    lv.tick_set_cb(None)
    before = lv.tick_get()
    check("tick_inc", lambda: (lv.tick_inc(17), lv.tick_get() - before)[1], lambda x: x == 17, "native internal logical clock increments")
    check("tick_elaps", lambda: lv.tick_elaps(before), lambda x: x == 17, "elapsed internal logical ticks")
    lv.delay_set_cb(lv.tick_inc)
    before = lv.tick_get()
    lv.delay_ms(7)
    check("delay_set_cb", lambda: lv.tick_get() - before, lambda x: x == 7, "native delay callback increments logical clock by requested duration")
    check("delay_ms", lambda: lv.tick_get() - before, lambda x: x == 7, "native callback receives exactly seven milliseconds")
    lv.delay_set_cb(None)


def run():
    try:
        import lvgl as lv
    except ImportError as error:
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": "module_helpers", "status": "UNAVAILABLE_ON_DEVICE", "oracle": repr(error)}))
        return
    lv.init()
    check("init", lv.is_initialized, bool, "native LVGL initialized")
    check("is_initialized", lv.is_initialized, bool, "native initialization state")
    for name, action in (("memory", memory), ("strings", strings), ("math", arithmetic), ("clocks", clocks)):
        try:
            action(lv)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": name + "_fixture", "status": "NOT_RUN", "oracle": repr(error)}))
    lv.deinit()
    check("deinit", lv.is_initialized, lambda x: not x, "native LVGL no longer initialized after teardown")


try:
    run()
except Exception as error:
    print("LVGL_GLOBALS_ERROR", repr(error))
print("LVGL_GLOBALS_DONE")
