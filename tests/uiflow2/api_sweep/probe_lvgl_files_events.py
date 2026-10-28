"""Native LVGL filesystem callbacks use actual guest VFS files and byte oracles."""
import json
import struct
import os


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


handles = []


def filesystem(lv):
    import fs_driver
    drv = lv.fs_drv_t()
    drv.init()
    check("fs_drv_t", "init", lambda: drv.letter, lambda x: x == 0, "new driver begins without assigned drive letter")
    fs_driver.fs_register(drv, "T", 0)
    # Keep callback-returned C handles alive for the native open/close lifetime.
    def open_file(driver, path, mode):
        item = fs_driver.fs_open_cb(driver, path, mode)
        handles.append(item)
        return item
    drv.open_cb = open_file
    def open_dir(driver, path):
        item = {"iterator": iter(os.ilistdir(path))}
        handles.append(item)
        return item
    def read_dir(driver, handle, output, length):
        try:
            entry = next(handle.__cast__()["iterator"])
            name = ("/" if entry[1] == 0x4000 else "") + entry[0]
        except StopIteration:
            name = ""
        data = name.encode()[:length - 1] + b"\x00"
        output.__dereference__(length)[:len(data)] = data
        return lv.FS_RES.OK
    drv.dir_open_cb, drv.dir_read_cb = open_dir, read_dir
    drv.dir_close_cb = lambda driver, handle: lv.FS_RES.OK
    check("fs_drv_t", "register", lambda: lv.fs_get_drv(ord("T")).letter, lambda x: x == ord("T"), "registered real guest filesystem callback driver")
    check("", "fs_get_drv", lambda: lv.fs_get_drv(ord("T")).letter, lambda x: x == ord("T"), "native registry resolves registered drive")
    check("", "fs_is_ready", lambda: lv.fs_is_ready(ord("T")), bool, "registered filesystem reports ready")
    letters = bytearray(32)
    check("", "fs_get_letters", lambda: lv.fs_get_letters(letters), lambda x: "T" in x, "registered letter is present in native drive inventory")
    native = lv.fs_file_t()
    path = "T:/flash/lvgl-roundtrip.txt"
    payload = b"LVGL real filesystem \x00\xff UTF8 \xe4\xb8\xad"
    check("fs_file_t", "open", lambda: native.open(path, lv.FS_MODE.WR), lambda x: x == lv.FS_RES.OK, "native open routes to guest Flash VFS")
    count = bytearray(4)
    check("fs_file_t", "write", lambda: (native.write(payload, len(payload), count), struct.unpack("I", count)[0]), lambda x: x == (lv.FS_RES.OK, len(payload)), "binary write reports exact byte count")
    check("fs_file_t", "tell", lambda: (native.tell(count), struct.unpack("I", count)[0]), lambda x: x == (lv.FS_RES.OK, len(payload)), "file cursor advances by exact payload length")
    check("fs_file_t", "close", native.close, lambda x: x == lv.FS_RES.OK, "native file closes successfully")
    with open("/flash/lvgl-roundtrip.txt", "rb") as stream:
        check("fs_file_t", "write.flash_bytes", stream.read, lambda x: x == payload, "independent native guest VFS read proves committed bytes")
    native.open(path, lv.FS_MODE.RD)
    check("fs_file_t", "seek", lambda: (native.seek(5, lv.FS_SEEK.SET), native.tell(count), struct.unpack("I", count)[0]), lambda x: x == (lv.FS_RES.OK, lv.FS_RES.OK, 5), "absolute seek updates native cursor")
    data = bytearray(len(payload) - 5)
    check("fs_file_t", "read", lambda: (native.read(data, len(data), count), bytes(data).hex(), struct.unpack("I", count)[0]), lambda x: x == (lv.FS_RES.OK, payload[5:].hex(), len(data)), "native filesystem reads exact binary suffix")
    native.close()
    directory = lv.fs_dir_t()
    check("fs_dir_t", "open", lambda: directory.open("T:/flash"), lambda x: x == lv.FS_RES.OK, "directory opens through registered native callbacks")
    names = []
    error = None
    try:
        for _ in range(32):
            name = bytearray(128)
            status = directory.read(name, len(name))
            value = bytes(name).split(b"\0")[0].decode()
            if not value:
                break
            names.append(value)
    except Exception as caught:
        error = repr(caught)
    check("fs_dir_t", "read", lambda: {"names": names, "error": error}, lambda x: x["error"] is None and "lvgl-roundtrip.txt" in x["names"] and "font-example.bin" in x["names"], "actual Flash directory entries include independently created files; mutable callback output required")
    check("fs_dir_t", "close", directory.close, lambda x: x == lv.FS_RES.OK, "native directory close result")


def fonts(lv):
    for method, argument in (("binfont_create", "T:/flash/font-example.bin"), ("binfont_create_from_buffer", None)):
        if argument is None:
            with open("/flash/font-example.bin", "rb") as stream:
                data = bytearray(stream.read())
            font = getattr(lv, method)(data, len(data))
        else:
            font = getattr(lv, method)(argument)
        check("", method, lambda: (font.get_line_height(), font.get_glyph_width(ord("A"), 0)), lambda x: x[0] > 0 and x[1] > 0, "official binary example font decodes printable glyph dimensions")
        lv.binfont_destroy(font)
        print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": "binfont_destroy",
            "status": "CALL_OK", "oracle": "owned binary font destructor called after actual glyph lookup; allocator accounting is unsupported"}))


def events(lv):
    items = lv.event_list_t()
    calls = []
    data = {"domain": "actual native callback"}
    callback = lambda event: calls.append(event.get_code())
    descriptor = items.add(callback, lv.EVENT.CLICKED, data)
    check("event_list_t", "add", items.get_count, lambda x: x == 1, "one actual native event descriptor registered")
    check("event_list_t", "get_count", items.get_count, lambda x: x == 1, "native event list cardinality")
    check("event_list_t", "get_dsc", lambda: items.get_dsc(0).get_user_data().__cast__(), lambda x: x is data, "descriptor resolves its exact Python user_data identity")
    check("event_dsc_t", "get_user_data", lambda: descriptor.get_user_data().__cast__(), lambda x: x is data, "native event descriptor retains caller data identity")
    event = lv.event_t()
    event.code = lv.EVENT.CLICKED
    check("event_list_t", "send", lambda: (items.send(event, False), list(calls)), lambda x: x == (lv.RESULT.OK, [lv.EVENT.CLICKED]), "native dispatch actually invokes registered filtered callback")
    check("event_t", "get_code", event.get_code, lambda x: x == lv.EVENT.CLICKED, "delivered event carries requested native event code")
    check("event_t", "get_user_data", lambda: event.get_user_data().__cast__(), lambda x: x is data, "event delivered exact descriptor user_data")
    parameter = bytearray(struct.pack("i", 42))
    event.param = parameter
    check("event_t", "get_param", lambda: bytes(event.get_param().__dereference__(4)).hex(), lambda x: x == parameter.hex(), "native event parameter points to caller-owned bytes")
    event.code = lv.EVENT.KEY
    check("event_t", "get_key", event.get_key, lambda x: x == 42, "KEY event decodes typed uint32 parameter")
    event.code = lv.EVENT.ROTARY
    check("event_t", "get_rotary_diff", event.get_rotary_diff, lambda x: x == 42, "ROTARY event decodes signed int32 parameter")
    check("event_t", "stop_processing", lambda: (lv.event_t.stop_processing(event), event.stop_processing)[1], lambda x: x == 1, "native event processing flag set")
    check("event_t", "stop_bubbling", lambda: (lv.event_t.stop_bubbling(event), event.stop_bubbling)[1], lambda x: x == 1, "native event bubbling flag set")
    first, second = lv.event_t(), lv.event_t()
    first.push()
    second.push()
    check("event_t", "push", lambda: lv.event_t.__cast__(second.prev) == first, bool, "nested native event stack links prior event")
    second.pop()
    third = lv.event_t()
    third.push()
    check("event_t", "pop", lambda: lv.event_t.__cast__(third.prev) == first, bool, "popping nested event restores actual previous head")
    third.pop()
    first.pop()
    check("event_list_t", "remove_dsc", lambda: (items.remove_dsc(descriptor), items.get_count()), lambda x: x == (True, 0), "exact native descriptor removed from list")
    items.add(callback, lv.EVENT.CLICKED, data)
    check("event_list_t", "remove", lambda: (items.remove(0), items.get_count()), lambda x: x == (True, 0), "indexed native descriptor removal")
    items.add(callback, lv.EVENT.CLICKED, data)
    check("event_list_t", "remove_all", lambda: (items.remove_all(), items.get_count())[1], lambda x: x == 0, "all native event descriptors released")


def run():
    import lvgl as lv
    lv.init()
    for name, action in (("filesystem", filesystem), ("fonts", fonts), ("events", events)):
        try:
            action(lv)
        except Exception as error:
            print("M5EMU_UI_RESULT " + json.dumps({"api_target": "lvgl", "method": name + "_fixture", "status": "NOT_RUN", "oracle": repr(error)}))
    lv.deinit()


try:
    run()
except Exception as error:
    print("LVGL_FILES_EVENTS_ERROR", repr(error))
print("LVGL_FILES_EVENTS_DONE")
