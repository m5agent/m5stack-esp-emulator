"""Probe native USB-device exports and local state without fabricating a host.

Local transformation/state checks are separate from USB transfer results.
The board's MAX3421E external host model does not provide an ESP32-S3 OTG
device host, enumeration or endpoint-completion oracle.
"""
import json


def emit(api, status, **details):
    details.update(api=api, status=status)
    print("USB_API " + json.dumps(details))


def reflect(path, obj):
    print("USB_EXPORT " + json.dumps({"path": path, "members": [x for x in dir(obj) if not x.startswith("_")]}))


def run():
    import machine
    import usb.device
    from usb.device.keyboard import Keyboard, char_to_hid_key
    from usb.device.mouse import Mouse
    reflect("machine.USBDevice", machine.USBDevice)
    device = usb.device.get()
    reflect("usb.device.get.result", device)
    emit("usb.device.get", "STATE_PASS" if device is usb.device.get() else "FAIL", oracle="documented singleton identity")
    mappings = [("a", (False, 4)), ("A", (True, 4)), ("1", (False, 30)), ("!", (True, 30)), (" ", (False, 44))]
    for char, expected in mappings:
        actual = char_to_hid_key(char)
        emit("usb.device.keyboard.char_to_hid_key", "PASS" if actual == expected else "FAIL", char=char, value=actual, expected=expected, oracle="USB HID keyboard usage table")
    for name, cls in (("Keyboard", Keyboard), ("Mouse", Mouse)):
        prefix = "usb.device." + name.lower() + "." + name
        try:
            obj = cls()
            reflect(prefix, obj)
            opened = obj.is_open()
            emit(prefix, "BLOCKED_MODEL", is_open=opened, reason="no emulated USB OTG device host/enumeration fixture; construction is not transfer PASS")
            if name == "Keyboard":
                obj.set_modifiers(left_shift=True, right_alt=True)
                emit(prefix + ".set_modifiers", "STATE_PASS" if obj._modifiers == 66 else "FAIL", value=obj._modifiers, required_data_plane="host interrupt-IN report")
                obj.set_keys(4, 5)
                emit(prefix + ".set_keys", "STATE_PASS" if obj._keypresses == [4, 5, 0, 0, 0, 0] else "FAIL", value=obj._keypresses, required_data_plane="host interrupt-IN report")
                methods = [("send_report", lambda: obj.send_report(timeout_ms=50)),
                           ("send_keys", lambda: obj.send_keys([4], timeout_ms=50)),
                           ("send_key", lambda: obj.send_key(4)),
                           ("input", lambda: obj.input("aA")),
                           ("send_keypresses", lambda: obj.send_keypresses("a"))]
            else:
                obj.set_axes(x=200, y=-200)
                emit(prefix + ".set_axes", "STATE_PASS" if (obj.x, obj.y) == (127, -127) else "FAIL", value=[obj.x, obj.y], required_data_plane="host relative-axis report")
                obj.set_wheel(-200)
                emit(prefix + ".set_wheel", "STATE_PASS" if obj.w == -127 else "FAIL", value=obj.w, required_data_plane="host wheel report")
                obj.set_buttons(b1=True, b2=True, fw=True)
                emit(prefix + ".set_buttons", "STATE_PASS" if (obj.b1, obj.b2, obj.b3, obj.fw, obj.bw) == (1, 1, 0, 1, 0) else "FAIL", value=[obj.b1, obj.b2, obj.b3, obj.fw, obj.bw], required_data_plane="host button report")
                methods = [("send_report", obj.send_report), ("move", lambda: obj.move(5, -5)),
                           ("scroll", lambda: obj.scroll(1)), ("click", lambda: obj.click()),
                           ("click_left", obj.click_left), ("click_right", obj.click_right),
                           ("click_middle", obj.click_middle), ("click_forward", obj.click_forward),
                           ("click_backward", obj.click_backward)]
            for method, action in methods:
                try:
                    result = action()
                    emit(prefix + "." + method, "BLOCKED_MODEL", returned=result, is_open=obj.is_open(), reason="no host enumeration/endpoint receipt; successful call cannot prove transfer")
                except Exception as error:
                    emit(prefix + "." + method, "BLOCKED_MODEL", error=repr(error), reason="USB OTG device host/endpoint model required")
        except Exception as error:
            emit(prefix, "ERROR", error=repr(error))


try:
    run()
except Exception as error:
    emit("usb.device", "ERROR", error=repr(error))
print("USB_DEVICE_API_DONE")
