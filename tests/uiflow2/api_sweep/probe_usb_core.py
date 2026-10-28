"""USB pure-library byte/callback contracts, separate from absent OTG host IO.

No endpoint transfer, host setup transaction or completion is synthesized.
Manual callback tests report local state only; formatter/buffer tests compare
actual owned bytes. Endpoint calls remain BLOCKED_MODEL without a real host.
"""
import json
import struct


def emit(api, status, **details):
    details.update(api=api, status=status)
    print("USB_API " + json.dumps(details))


def check(api, action, oracle, description, status="PASS"):
    try:
        value = action()
        ok = oracle(value)
        emit(api, status if ok else "FAIL", value=value, oracle=description,
             evaluation_scope="pure-library-byte-contract" if status == "PASS" else "local-callback-state-only")
        return value
    except Exception as error:
        emit(api, "FAIL", error=repr(error), oracle=description)


def reflect(path, obj):
    members = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        value = getattr(obj, name)
        members.append((name, type(value).__name__, callable(value)))
    print("USB_EXPORT " + json.dumps({"path": path, "members": members}))


def expected_error(api, action, kind, description):
    try:
        action()
        emit(api, "FAIL", oracle=description, error="required rejection did not occur")
    except Exception as error:
        emit(api, "EXPECTED_REJECTION" if isinstance(error, kind) else "FAIL", oracle=description, error=repr(error), evaluation_scope="documented-local-rejection-only")


def blocked(api, action):
    try:
        value = action()
        emit(api, "BLOCKED_MODEL", returned=value, reason="ESP32-S3 OTG device host enumeration, endpoint token/handshake and completion data plane are absent; this call is not a USB transfer receipt.")
    except Exception as error:
        emit(api, "BLOCKED_MODEL", error=repr(error), reason="No real OTG host configured this interface or endpoint; closed/unconfigured rejection cannot establish a positive transfer.")


def buffers(core):
    prefix = "usb.device.core.Buffer"
    b = core.Buffer(8)
    reflect(prefix, b)
    check(prefix, lambda: (b.readable(), b.writable()), lambda v: v == (0, 8), "owned eight-byte producer/consumer buffer starts empty")
    check(prefix + ".writable", b.writable, lambda v: v == 8, "empty buffer has eight writable bytes")
    view = b.pend_write(3)
    check(prefix + ".pend_write", lambda: (len(view), len(b.pend_write(3))), lambda v: v == (3, 3), "bounded repeated pending writes expose three actual owned bytes")
    view[:] = b"ABC"
    check(prefix + ".finish_write", lambda: (b.finish_write(3), bytes(b.pend_read()).decode())[1], lambda v: v == "ABC", "committed bytes become visible to consumer")
    check(prefix + ".readable", b.readable, lambda v: v == 3, "three committed bytes readable")
    check(prefix + ".pend_read", lambda: (bytes(b.pend_read()).decode(), bytes(b.pend_read()).decode()), lambda v: v == ("ABC", "ABC"), "repeated read views do not consume bytes")
    check(prefix + ".finish_read", lambda: (b.finish_read(1), bytes(b.pend_read()).decode())[1], lambda v: v == "BC", "partial read shifts remaining actual bytes")
    view = b.pend_write(4)
    view[:] = b"DEFG"
    b.finish_read(1)
    b.finish_write(4)
    check(prefix + ".finish_write", lambda: bytes(b.pend_read()).decode(), lambda v: v == "CDEFG", "consumer ran during pending write; slow-path compaction preserves exact order")
    check(prefix + ".write", lambda: (b.write(b"HIJKLM"), bytes(b.pend_read()).decode()), lambda v: v == (3, "CDEFGHIJ"), "normal write clips to real remaining capacity")
    output = bytearray(4)
    check(prefix + ".readinto", lambda: (b.readinto(output), bytes(output).decode(), bytes(b.pend_read()).decode()), lambda v: v == (4, "CDEF", "GHIJ"), "readinto returns actual byte count and consumes exactly those bytes")
    # These source asserts are caller preconditions and can be optimized out
    # by production firmware. Record invalid-input behavior separately rather
    # than claiming the normal method contract requires a runtime exception.
    for method in ("finish_read", "finish_write"):
        invalid = core.Buffer(8)
        invalid.write(b"ABC")
        if method == "finish_write":
            invalid.pend_write(2)
        try:
            getattr(invalid, method)(9)
            observed = {"rejected": False, "readable": invalid.readable()}
        except Exception as error:
            observed = {"rejected": True, "error": repr(error)}
        print("USB_BOUNDARY " + json.dumps({"api": prefix + "." + method, "input": 9,
            "observed": observed, "scope": "caller precondition violated; source asserts are not guaranteed runtime validation with optimized firmware"}))


def descriptors(core):
    prefix = "usb.device.core.Descriptor"
    d = core.Descriptor(bytearray(64))
    reflect(prefix, d)
    check(prefix, lambda: (d.o, len(d.b)), lambda v: v == (0, 64), "descriptor writes into supplied bounded buffer")
    check(prefix + ".pack", lambda: (d.pack("<H", 0x1234), list(d.b[:2]), d.o)[1:], lambda v: v == ([0x34, 0x12], 2), "explicit little-endian field bytes")
    check(prefix + ".pack_into", lambda: (d.pack_into("BB", 0, 9, 4), list(d.b[:2]), d.o)[1:], lambda v: v == ([9, 4], 2), "overwrite keeps high-water offset")
    check(prefix + ".extend", lambda: (d.extend(b"XYZ"), list(d.b[:5]), d.o)[1:], lambda v: v == ([9, 4, 88, 89, 90], 5), "append exact bytes at current offset")
    def formatted(method, args):
        descriptor = core.Descriptor(bytearray(32))
        getattr(descriptor, method)(*args)
        return list(descriptor.b[:descriptor.o])
    check(prefix + ".interface", lambda: formatted("interface", (2, 1, 3, 1, 2, 5)), lambda v: v == [9, 4, 2, 0, 1, 3, 1, 2, 5], "USB 2.0 standard interface descriptor fields")
    check(prefix + ".endpoint", lambda: formatted("endpoint", (0x83, "interrupt", 64, 8)), lambda v: v == [7, 5, 0x83, 3, 64, 0, 8], "USB standard interrupt endpoint address, packet size and interval")
    check(prefix + ".interface_assoc", lambda: formatted("interface_assoc", (2, 3, 4, 5, 6, 7)), lambda v: v == [8, 11, 2, 3, 4, 5, 6, 7], "USB interface association descriptor field order")
    dummy = core.Descriptor(None)
    dummy.interface(2, 1)
    dummy.endpoint(0x83, "interrupt", 64, 8)
    check(prefix + ".pack", lambda: dummy.o, lambda v: v == 16, "dummy descriptor computes exact interface-plus-endpoint length without backing storage")


def request(bm, code, value=0, length=0):
    return struct.pack("<BBHHH", bm, code, value, 2, length)


def interfaces(core, hid_module, keyboard_module, mouse_module):
    classes = (("usb.device.core.Interface", core.Interface, False),
               ("usb.device.hid.HIDInterface", lambda: hid_module.HIDInterface(b"\x05\x01\x09\x02"), True),
               ("usb.device.keyboard.Keyboard", keyboard_module.Keyboard, True),
               ("usb.device.mouse.Mouse", mouse_module.Mouse, True))
    for prefix, constructor, is_hid in classes:
        try:
            obj = constructor()
            reflect(prefix, obj)
            check(prefix, lambda: obj.is_open(), lambda v: v is False, "construction leaves interface unenumerated", "STATE_PASS")
            check(prefix + ".num_itfs", obj.num_itfs, lambda v: v == 1, "declared one-interface descriptor count")
            check(prefix + ".num_eps", obj.num_eps, lambda v, is_hid=is_hid: v == (1 if is_hid else 0), "HID declares one interrupt endpoint; base declares none")
            check(prefix + ".is_open", obj.is_open, lambda v: v is False, "fresh interface has no actual host configuration", "STATE_PASS")
            check(prefix + ".on_open", lambda: (obj.on_open(), obj.is_open())[1], bool, "direct callback state transition only, without fabricating enumeration", "STATE_PASS")
            check(prefix + ".on_reset", lambda: (obj.on_reset(), obj.is_open())[1], lambda v: v is False, "direct reset callback clears local open state", "STATE_PASS")
            for method in ("on_device_control_xfer", "on_endpoint_control_xfer"):
                check(prefix + "." + method, lambda method=method: getattr(obj, method)(1, request(0x41, 0x7f)), lambda v: v is False, "default unsupported control callback declines request locally", "STATE_PASS")
            if not is_hid:
                expected_error(prefix + ".desc_cfg", lambda: obj.desc_cfg(core.Descriptor(None), 2, 3, []), NotImplementedError, "abstract base requires a concrete descriptor implementation")
                check(prefix + ".on_interface_control_xfer", lambda: obj.on_interface_control_xfer(1, request(0x41, 0x7f)), lambda v: v is False, "base interface delegates unsupported control requests", "STATE_PASS")
            else:
                strings = []
                d = core.Descriptor(bytearray(128))
                report_length = len(obj.report_descriptor)
                # Descriptor bytes are checked against USB/HID field layout,
                # while this callback is invoked directly rather than by a host.
                obj.desc_cfg(d, 2, 3, strings)
                check(prefix + ".desc_cfg", lambda: (d.o, list(d.b[:6]), list(d.b[18:25])), lambda v: v == (25, [9, 4, 2, 0, 1, 3], [7, 5, 0x83, 3, 8, 0, 8]), "concrete HID configuration emits exact interface and interrupt endpoint bytes")
                check(prefix + ".get_hid_descriptor", lambda: list(obj.get_hid_descriptor()), lambda v: v == [9, 0x21, 0x11, 1, 0, 1, 0x22, report_length & 255, report_length >> 8], "HID 1.11 report descriptor type and exact length")
                check(prefix + ".get_report", obj.get_report, lambda v: v is False, "default GET_REPORT implementation reports unsupported", "STATE_PASS")
                check(prefix + ".busy", obj.busy, lambda v: v is False, "closed interface has no pending configured interrupt transfer", "STATE_PASS")
                def control_values():
                    report = obj.on_interface_control_xfer(1, request(0x81, 6, 0x2200, report_length))
                    assert bytes(report) == bytes(obj.report_descriptor)
                    hid = obj.on_interface_control_xfer(1, request(0x81, 6, 0x2100, 9))
                    assert bytes(hid) == bytes(obj.get_hid_descriptor())
                    for code, value in ((10, 0x2500), (11, 1)):
                        assert obj.on_interface_control_xfer(1, request(0x21, code, value)) is True
                        obj.on_interface_control_xfer(3, request(0x21, code, value))
                    idle = obj.on_interface_control_xfer(1, request(0xa1, 2, 0, 1))
                    protocol = obj.on_interface_control_xfer(1, request(0xa1, 3, 0, 1))
                    unknown = obj.on_interface_control_xfer(1, request(0xc1, 0x7f))
                    return list(idle), list(protocol), unknown
                check(prefix + ".on_interface_control_xfer", control_values, lambda v: v == ([0x25], [1], False), "direct HID callbacks return exact descriptors, acknowledge idle/protocol updates and reject vendor request", "STATE_PASS")
                if prefix.endswith("Keyboard"):
                    check(prefix + ".on_set_report", lambda: obj.on_set_report(b"\x05", 0, 2), lambda v: v is None, "keyboard LED report callback accepts an explicit output byte locally", "STATE_PASS")
                    check(prefix + ".on_led_update", lambda: obj.on_led_update(5), lambda v: v is None, "default LED hook is a documented override point, no hardware LED claim", "STATE_PASS")
                else:
                    check(prefix + ".on_set_report", lambda: obj.on_set_report(b"\x05", 0, 2), lambda v: v is True, "base output-report callback permits local completion", "STATE_PASS")
                if prefix.endswith("HIDInterface"):
                    blocked(prefix + ".send_report", lambda: obj.send_report(b"USB", timeout_ms=5))
            for method, action in (("xfer_pending", lambda: obj.xfer_pending(0x83)),
                                   ("submit_xfer", lambda: obj.submit_xfer(0x83, b"USB")),
                                   ("stall", lambda: obj.stall(0x83, True))):
                blocked(prefix + "." + method, action)
        except Exception as error:
            emit(prefix, "FAIL", error=repr(error), oracle="construct exact stock USB interface")


def device_helpers(usb_device, hid_module):
    dev = usb_device.get()
    reflect("usb.device.get.result", dev)
    check("usb.device.get.result.active", lambda: (dev.active(False), dev.active())[1], lambda v: v is False, "native USB device deactivates within this disposable VM", "STATE_PASS")
    interface = hid_module.HIDInterface(b"\x05\x01\x09\x02")
    check("usb.device.get.result.config", lambda: (dev.config(interface, builtin_driver=False), len(dev._itfs), dev._itfs[0] is interface)[1:], lambda v: v == (1, True), "native config accepts actual assembled descriptor and retains interface mapping; no enumeration claim", "STATE_PASS")
    check("usb.device.get.result.init", lambda: (dev.init(interface, builtin_driver=False), dev.active(), interface.is_open())[1:], lambda v: v == (True, False), "init configures/activates native device while interface remains unenumerated", "STATE_PASS")
    dev.active(False)


def run():
    import usb.device as device
    import usb.device.core as core
    import usb.device.hid as hid
    import usb.device.keyboard as keyboard
    import usb.device.mouse as mouse
    for name, module in (("usb.device.core", core), ("usb.device.hid", hid), ("usb.device.keyboard", keyboard), ("usb.device.mouse", mouse)):
        reflect(name, module)
        if hasattr(module, "const"):
            check(name + ".const", lambda module=module: module.const(23), lambda v: v == 23, "exported const helper preserves integer literal")
    check("usb.device.core.split_bmRequestType", lambda: [core.split_bmRequestType(v) for v in (0, 0x21, 0x82, 0xff)], lambda v: v == [(0, 0, 0), (1, 1, 0), (2, 0, 1), (31, 3, 1)], "USB 2.0 recipient/type/direction bit fields")
    check("usb.device.core.get_ident", core.get_ident, lambda v: isinstance(v, int) and v != 0, "actual executing MicroPython task identity")
    check("usb.device.core.get", lambda: core.get() is device.get(), bool, "public getter alias resolves actual native-device singleton", "STATE_PASS")
    for api, obj, fields, expected in (("usb.device.hid.KeyCode", hid.KeyCode, ("A", "ENTER"), (4, 40)),
                                       ("usb.device.keyboard.LEDCode", keyboard.LEDCode, ("NUM_LOCK", "CAPS_LOCK"), (1, 2))):
        try:
            instance = obj()
            reflect(api, obj)
            check(api, lambda instance=instance, fields=fields: tuple(getattr(instance, key) for key in fields), lambda v, expected=expected: v == expected, "enum-class constructor exposes HID specification values", "STATE_PASS")
        except Exception as error:
            emit(api, "FAIL", error=repr(error), oracle="public HID enum values")
    buffers(core)
    descriptors(core)
    check("usb.device.hid.Descriptor", lambda: hid.Descriptor(bytearray(8)).o, lambda v: v == 0, "public imported descriptor constructor starts at offset zero")
    check("usb.device.hid.Interface", lambda: hid.Interface().num_eps(), lambda v: v == 0, "public imported base-interface constructor declares no endpoints", "STATE_PASS")
    interfaces(core, hid, keyboard, mouse)
    # Imported public aliases still construct the same genuine base class.
    for module, name in ((keyboard, "usb.device.keyboard.HIDInterface"), (mouse, "usb.device.mouse.HIDInterface")):
        check(name, lambda module=module: module.HIDInterface(b"\x05\x01").num_eps(), lambda v: v == 1, "exported HIDInterface alias constructs actual stock base", "STATE_PASS")
    device_helpers(device, hid)


try:
    run()
except Exception as error:
    emit("usb.device.core", "FAIL", error=repr(error), oracle="finite USB pure-library probe completion")
print("USB_CORE_API_DONE")
