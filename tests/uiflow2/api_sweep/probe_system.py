"""UIFlow2 system probes executed only inside the actual MicroPython guest."""
import time
import json


def system_result(api, action, verify):
    try:
        value = action()
        passed = verify(value)
        print("SYSTEM_API " + json.dumps({"api": api, "status": "PASS" if passed else "FAIL", "value": value}))
        return value
    except Exception as error:
        print("SYSTEM_API " + json.dumps({"api": api, "status": "ERROR", "error": repr(error)}))


def system_reflection():
    import sys
    print("SYSTEM_ENV " + json.dumps({"version": sys.version, "implementation": repr(sys.implementation)}))
    # Import only modules whose imports do not instantiate physical devices.
    for name in ("time", "os", "sys", "machine", "network", "bluetooth", "espnow", "esp32", "audio",
                 "socket", "select", "ssl", "requests2", "easysocket", "umqtt", "umqtt.simple", "umqtt.robust",
                 "modbus", "modbus.tcp", "modbus.rtu", "bleuart", "m5ble", "m5espnow", "ezdata"):
        try:
            target = __import__(name, None, None, ["*"])
            pending = [(name, target)]
            while pending:
                path, current = pending.pop(0)
                members = []
                names = set(dir(current))
                lazy = getattr(current, "_attrs", None)
                if isinstance(lazy, dict):
                    names.update(lazy)
                for member_name in sorted(names):
                    if member_name.startswith("_"):
                        continue
                    try:
                        member = getattr(current, member_name)
                        members.append([member_name, type(member).__name__, callable(member)])
                        if path == name and isinstance(member, type):
                            pending.append((path + "." + member_name, member))
                    except Exception as error:
                        members.append([member_name, "READ_ERROR", repr(error)])
                for offset in range(0, len(members), 100):
                    print("SYSTEM_EXPORT " + json.dumps({"path": path, "offset": offset, "count": len(members), "members": members[offset:offset + 100]}))
        except Exception as error:
            print("SYSTEM_EXPORT " + json.dumps({"path": name, "status": "ABSENT", "error": repr(error)}))
    print("SYSTEM_REFLECTION_DONE")


def clock_tests():
    system_result("time.gmtime", lambda: list(time.gmtime(0)), lambda value: value[:6] == [1970, 1, 1, 0, 0, 0])
    old_zone = None
    try:
        old_zone = time.timezone()
        time.timezone("GMT0")
        system_result("time.timezone", time.timezone, lambda value: value == "GMT0")
        epoch = (2026, 10, 27, 12, 34, 56, 1, 300)
        stamp = time.mktime(epoch)
        system_result("time.mktime", lambda: stamp, lambda value: value == 1793104496)
        system_result("time.localtime", lambda: list(time.localtime(stamp)), lambda value: value[:6] == list(epoch[:6]))
        time.timezone("GMT-8")
        system_result("time.timezone.localtime", lambda: list(time.localtime(stamp)), lambda value: value[:6] == [2026, 10, 27, 20, 34, 56])
    except Exception as error:
        print("SYSTEM_API " + json.dumps({"api": "time.timezone", "status": "ERROR", "error": repr(error)}))
    finally:
        if old_zone is not None:
            time.timezone(old_zone)
    for name, delay, minimum in (("sleep", .02, 20000), ("sleep_ms", 20, 20000), ("sleep_us", 500, 500)):
        start = time.ticks_us()
        getattr(time, name)(delay)
        system_result("time." + name, lambda start=start: time.ticks_diff(time.ticks_us(), start),
                      lambda value, minimum=minimum: minimum <= value < 2000000)
    for name in ("ticks_ms", "ticks_us", "ticks_cpu"):
        start = getattr(time, name)()
        time.sleep_ms(5)
        system_result("time." + name, lambda name=name, start=start: time.ticks_diff(getattr(time, name)(), start), lambda value: value > 0)
    start = time.ticks_ms()
    system_result("time.ticks_add", lambda: time.ticks_diff(time.ticks_add(start, 123), start), lambda value: value == 123)
    maximum = time.ticks_add(0, -1)
    system_result("time.ticks_diff", lambda: time.ticks_diff(0, maximum), lambda value: value == 1)
    before = time.time()
    time.sleep_ms(1100)
    system_result("time.time", lambda: time.time() - before, lambda value: 1 <= value <= 3)
    if hasattr(time, "time_ns"):
        before = time.time_ns()
        time.sleep_ms(20)
        system_result("time.time_ns", lambda: time.time_ns() - before, lambda value: 19000000 <= value < 2000000000)
    print("SYSTEM_CLOCK_DONE")


def filesystem_tests():
    import os
    import io
    root = "/flash/api-system-fixture"
    try:
        os.mkdir(root)
    except OSError:
        pass
    original = os.getcwd()
    try:
        os.chdir(root)
        system_result("os.getcwd", os.getcwd, lambda value: value == root)
        with open("roundtrip.bin", "wb") as handle:
            handle.write(b"\x00\xffUIFlow2\xe4\xb8\xad\xe6\x96\x87")
        with open("roundtrip.bin", "rb") as handle:
            data = handle.read()
        system_result("file.read_write", lambda: list(data), lambda value: bytes(value) == b"\x00\xffUIFlow2\xe4\xb8\xad\xe6\x96\x87")
        system_result("os.stat", lambda: list(os.stat("roundtrip.bin")), lambda value: value[6] == len(data))
        system_result("os.listdir", os.listdir, lambda value: "roundtrip.bin" in value)
        os.rename("roundtrip.bin", "renamed.bin")
        system_result("os.rename", os.listdir, lambda value: "renamed.bin" in value and "roundtrip.bin" not in value)
        os.sync()
        system_result("os.statvfs", lambda: list(os.statvfs(".")), lambda value: len(value) == 10 and value[0] > 0)
        os.remove("renamed.bin")
        system_result("os.remove", os.listdir, lambda value: "renamed.bin" not in value)
        stream = io.BytesIO(b"abcdef")
        stream.seek(2)
        target = bytearray(2)
        stream.readinto(target)
        system_result("io.BytesIO.seek_readinto", lambda: target.decode(), lambda value: value == "cd")
        stream.close()
    finally:
        os.chdir(original)
        os.rmdir(root)
    print("SYSTEM_FILESYSTEM_DONE")


def run_system(stage="local"):
    print("SYSTEM_STAGE_START", stage)
    if stage == "reflection":
        system_reflection()
    elif stage == "local":
        clock_tests()
        filesystem_tests()
    else:
        raise ValueError("unknown system probe stage")
    print("SYSTEM_STAGE_END", stage)
