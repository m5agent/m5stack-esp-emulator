"""MicroPython hardware API probes; call run_hardware() in a visible session.

CALL_OK records a guest API invocation, never a peripheral functional PASS.
The host joins serial output with same-session input/QOM/PCM/frame evidence.
Stages which alter bus ownership run separately from the UI and audio stages.
"""

import M5
import time
import machine
import json


def _hardware_emit(api, status, value=None, detail=None):
    item = {"api": api, "status": status}
    if value is not None:
        if isinstance(value, (str, int, float, bool, list, tuple, dict)):
            item["value"] = value
        else:
            item["value"] = str(value)
    if detail:
        item["detail"] = detail
    print("HARDWARE_API " + json.dumps(item))


def _hardware_call(api, action, verify=None):
    try:
        value = action()
        if verify is not None and not verify(value):
            _hardware_emit(api, "FAIL", value, "guest return did not match expected value")
        else:
            _hardware_emit(api, "CALL_OK" if verify is None else "API_ASSERTION_PASS", value)
        return value
    except Exception as exc:
        _hardware_emit(api, "ERROR", detail=repr(exc))
        return None


def _hardware_wait(milliseconds):
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)


def _hardware_resolve(path):
    parts = path.split(".")
    current = __import__(parts[0])
    walked = parts[0]
    for part in parts[1:]:
        call = part.endswith("()")
        if call:
            part = part[:-2]
        walked += "." + part
        try:
            current = getattr(current, part)
        except AttributeError:
            current = __import__(walked, None, None, [part])
        if call:
            current = current()
    return current


def reflect_hardware(paths):
    """Presence denominator only; methods are exercised by their recipes."""
    for path in paths:
        try:
            target = _hardware_resolve(path)
            value = {"type": type(target).__name__}
            if isinstance(target, (str, int, float, bool)):
                value["value"] = target
            _hardware_emit(path, "PRESENT", value)
        except Exception as exc:
            _hardware_emit(path, "ABSENT", detail=repr(exc))


def _hardware_read_only():
    _hardware_call("M5.getBoard", M5.getBoard)
    _hardware_call("M5.update", M5.update)
    for owner, names in (
        ("Imu", ("isEnabled", "getType", "getAccel", "getGyro", "getMag")),
        ("Power", ("getExtOutput", "getUsbOutput", "getBatteryLevel", "isCharging", "getBatteryVoltage", "getBatteryCurrent", "getVBUSVoltage", "getKeyState", "getType")),
        ("Als", ("getLightSensorData", "getProximitySensorData")),
        ("Touch", ("getX", "getY", "getCount", "getDetail", "getTouchPointRaw")),
        ("Speaker", ("isRunning", "isEnabled", "isPlaying", "getPlayingChannels", "getVolume", "getVolumePercentage")),
        ("Mic", ("isRunning", "isEnabled", "isRecording")),
    ):
        for name in names:
            _hardware_call("M5." + owner + "." + name, lambda owner=owner, name=name: getattr(getattr(M5, owner), name)())
    names = ("isHolding", "isPressed", "isReleased", "wasClicked", "wasDoubleClicked", "wasHold", "wasPressed", "wasReleased", "wasSingleClicked", "wasChangePressed", "lastChange", "wasDeciedClickCount", "getClickCount")
    for owner in ("BtnA", "BtnB", "BtnC", "BtnPWR", "BtnEXT"):
        for name in names:
            _hardware_call("M5." + owner + "." + name, lambda owner=owner, name=name: getattr(getattr(M5, owner), name)())
        for name in ("pressedFor", "releasedFor"):
            _hardware_call("M5." + owner + "." + name, lambda owner=owner, name=name: getattr(getattr(M5, owner), name)(100))
    for owner in ("Speaker", "Mic"):
        obj = getattr(M5, owner)
        cfg = _hardware_call("M5." + owner + ".config", obj.config)
        if cfg is not None:
            for name in dir(cfg):
                if not name.startswith("_"):
                    _hardware_call("M5." + owner + ".config." + name, lambda cfg=cfg, name=name: getattr(cfg, name))


def _hardware_sensors(expected):
    # Expected vectors must come from host QOM injection in this same session.
    M5.update()
    for name, key, tolerance in (("getAccel", "accel", 0.05), ("getGyro", "gyro", 1.0), ("getMag", "mag", 2.0)):
        values = expected.get(key)
        validator = None
        if values is not None:
            validator = lambda result, values=values, tolerance=tolerance: len(result) == 3 and all(abs(result[index] - values[index]) < tolerance for index in range(3))
        _hardware_call("M5.Imu." + name, getattr(M5.Imu, name), validator)
    _hardware_call("M5.Imu.isEnabled", M5.Imu.isEnabled, lambda value: bool(value))
    _hardware_call("M5.Imu.getType", M5.Imu.getType)
    for name, value in expected.get("power", {}).items():
        _hardware_call("M5.Power." + name, getattr(M5.Power, name), lambda result, value=value: abs(result - value) <= 2)
    for name, value in expected.get("als", {}).items():
        _hardware_call("M5.Als." + name, getattr(M5.Als, name), lambda result, value=value: result == value)


def _hardware_audio(milliseconds):
    # Keep the audio ownership sequence explicit; each playback also needs
    # corresponding controller PCM capture before the host marks it functional.
    import struct
    speaker = M5.Speaker
    M5.Mic.end()
    _hardware_call("M5.Speaker.begin", speaker.begin, lambda value: bool(value))
    original = speaker.getVolume()
    for name, action in (
        ("setPA", lambda: speaker.setPA(True)),
        ("setVolume", lambda: speaker.setVolume(96)),
        ("getVolume", speaker.getVolume),
        ("setVolumePercentage", lambda: speaker.setVolumePercentage(0.5)),
        ("getVolumePercentage", speaker.getVolumePercentage),
        ("setAllChannelVolume", lambda: speaker.setAllChannelVolume(80)),
        ("setChannelVolume", lambda: speaker.setChannelVolume(0, 90)),
        ("getChannelVolume", lambda: speaker.getChannelVolume(0)),
        ("isEnabled", speaker.isEnabled),
        ("isRunning", speaker.isRunning),
    ):
        _hardware_call("M5.Speaker." + name, action)
    _hardware_call("M5.Speaker.tone", lambda: speaker.tone(440, milliseconds))
    _hardware_call("M5.Speaker.isPlaying", speaker.isPlaying)
    _hardware_call("M5.Speaker.getPlayingChannels", speaker.getPlayingChannels)
    _hardware_wait(milliseconds + 100)
    _hardware_call("M5.Speaker.stop", speaker.stop)
    pcm = bytearray()
    for index in range(800):
        pcm.extend(struct.pack("<h", 8000 if (index // 10) % 2 else -8000))
    _hardware_call("M5.Speaker.playRaw", lambda: speaker.playRaw(pcm, 8000, False, 1, 0, True))
    _hardware_wait(200)
    wav = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1, 8000, 16000, 2, 16, b"data", len(pcm)) + pcm
    _hardware_call("M5.Speaker.playWav", lambda: speaker.playWav(wav))
    _hardware_wait(200)
    path = "/flash/api-sweep-hardware.wav"
    with open(path, "wb") as handle:
        handle.write(wav)
    _hardware_call("M5.Speaker.playWavFile", lambda: speaker.playWavFile(path))
    _hardware_wait(200)
    speaker.stop()
    speaker.setVolume(original)
    _hardware_call("M5.Speaker.end", speaker.end)


def _hardware_mic(expected):
    import hashlib
    M5.Speaker.stop()
    M5.Speaker.end()
    mic = M5.Mic
    original_config = None
    if "magnification" in expected:
        mic.end()
        original_config = mic.config()
        mic.config(magnification=expected["magnification"])
    _hardware_call("M5.Mic.setSampleRate", lambda: mic.setSampleRate(16000))
    _hardware_call("M5.Mic.begin", mic.begin, lambda value: bool(value))
    _hardware_call("M5.Mic.isEnabled", mic.isEnabled)
    _hardware_call("M5.Mic.isRunning", mic.isRunning)
    data = bytearray(3200)
    _hardware_call("M5.Mic.record", lambda: mic.record(data, 16000, False), lambda value: bool(value))
    _hardware_call("M5.Mic.isRecording", mic.isRecording)
    deadline = time.ticks_add(time.ticks_ms(), 3000)
    while mic.isRecording() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        _hardware_wait(10)
    _hardware_call("M5.Mic.isRecording", mic.isRecording, lambda value: not value)
    digest = hashlib.sha256(data).digest().hex()
    matched = expected.get("pcm_sha256") == digest
    _hardware_emit("M5.Mic.record.pcm", "API_ASSERTION_PASS" if matched else "OBSERVED", {"bytes": len(data), "sha256": digest, "nonzero": sum(1 for item in data if item), "recording": mic.isRecording()}, "Functional PASS requires a host signal oracle accounting for the official gain/DC/stereo conversion plus controller evidence")
    if expected.get("capture_hex"):
        _hardware_emit("M5.Mic.record.pcm_bytes", "OBSERVED", data.hex())
    if expected.get("record_wav"):
        path = "/flash/api-mic-record.wav"
        print("HARDWARE_MIC_WAV_CALL_START")
        _hardware_call("M5.Mic.recordWavFile", lambda: mic.recordWavFile(path=path, rate=16000, time=1, stereo=False))
        try:
            wav_hash = hashlib.sha256()
            wav_size = 0
            with open(path, "rb") as handle:
                while True:
                    chunk = handle.read(512)
                    if not chunk:
                        break
                    wav_hash.update(chunk)
                    wav_size += len(chunk)
            _hardware_emit("M5.Mic.recordWavFile.file", "OBSERVED", {"bytes": wav_size, "sha256": wav_hash.digest().hex()})
            if expected.get("capture_hex"):
                with open(path, "rb") as handle:
                    offset = 0
                    while True:
                        chunk = handle.read(512)
                        if not chunk:
                            break
                        _hardware_emit("M5.Mic.recordWavFile.wav_chunk", "OBSERVED", {"offset": offset, "hex": chunk.hex()})
                        offset += len(chunk)
        except Exception as error:
            _hardware_emit("M5.Mic.recordWavFile.file", "ERROR", detail=repr(error))
    _hardware_call("M5.Mic.end", mic.end)
    if original_config is not None:
        mic.config(original_config)


def _hardware_inputs(milliseconds):
    callback_events = []
    for owner in ("BtnA", "BtnB", "BtnC", "BtnPWR", "BtnEXT"):
        button = getattr(M5, owner)
        for event in ("WAS_CLICKED", "WAS_DOUBLECLICKED", "WAS_HOLD", "WAS_PRESSED", "WAS_RELEASED"):
            callback_type = getattr(button.CB_TYPE, event)
            callback = lambda state, owner=owner, event=event: callback_events.append((owner, event, state))
            _hardware_call("M5." + owner + ".setCallback." + event, lambda button=button, callback_type=callback_type, callback=callback: button.setCallback(type=callback_type, cb=callback))
    print("HARDWARE_INPUT_READY")
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    last = None
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        current = []
        for owner in ("BtnA", "BtnB", "BtnC", "BtnPWR", "BtnEXT"):
            button = getattr(M5, owner)
            for name in ("isHolding", "isPressed", "isReleased", "wasClicked", "wasDoubleClicked", "wasHold", "wasPressed", "wasReleased", "wasSingleClicked"):
                value = getattr(button, name)()
                if value:
                    current.append((owner, name))
        current.append(("touch", M5.Touch.getCount(), M5.Touch.getX(), M5.Touch.getY()))
        if current != last:
            _hardware_emit("M5.input.transitions", "OBSERVED", current)
            last = current
        time.sleep_ms(10)
    _hardware_emit("M5.Button.setCallback.events", "OBSERVED", callback_events)
    for name in ("getX", "getY", "getCount", "getDetail", "getTouchPointRaw"):
        _hardware_call("M5.Touch." + name, getattr(M5.Touch, name))
    for owner in ("BtnA", "BtnB", "BtnC", "BtnPWR", "BtnEXT"):
        button = getattr(M5, owner)
        for event in ("WAS_CLICKED", "WAS_DOUBLECLICKED", "WAS_HOLD", "WAS_PRESSED", "WAS_RELEASED"):
            _hardware_call("M5." + owner + ".removeCallback." + event, lambda button=button, event=event: button.removeCallback(type=getattr(button.CB_TYPE, event)))


def _hardware_keyboard(milliseconds):
    from hardware import KeyboardI2C
    i2c = machine.I2C(1, scl=machine.Pin(9), sda=machine.Pin(8), freq=400000)
    interrupt = machine.Pin(11, machine.Pin.IN, pull=None)
    keyboard = KeyboardI2C(i2c, intr_pin=interrupt, mode=KeyboardI2C.ASCII_MODE)
    events = []
    keyboard.set_keyevent_callback(lambda value: events.append(str(value)))
    _hardware_emit("hardware.KeyboardI2C", "CALL_OK")
    _hardware_emit("hardware.KeyboardI2C.set_keyevent_callback", "CALL_OK")
    print("HARDWARE_KEYBOARD_READY")
    _hardware_wait(milliseconds)
    _hardware_emit("hardware.KeyboardI2C.events", "OBSERVED", events, "Events must be paired with the same-session TCA8418 injection; no private-handler polling")
    _hardware_call("hardware.KeyboardI2C.is_key_pressed", lambda: keyboard.is_key_pressed(ord("a")))
    _hardware_call("hardware.KeyboardI2C.deinit", keyboard.deinit)
    hid_reports = []
    keyboard = KeyboardI2C(i2c, intr_pin=interrupt, mode=KeyboardI2C.HID_MODE)
    keyboard.set_hid_report_callback(lambda value: hid_reports.append(str(value)))
    _hardware_emit("hardware.KeyboardI2C.set_hid_report_callback", "CALL_OK")
    print("HARDWARE_KEYBOARD_HID_READY")
    _hardware_wait(milliseconds)
    _hardware_emit("hardware.KeyboardI2C.hid_reports", "OBSERVED", hid_reports)
    keyboard.deinit()


def _hardware_gpio(milliseconds, pin_number):
    # Caller provides a free, unmounted Grove pad; controller evidence is read
    # by the host before switching to the next phase.
    pin = machine.Pin(pin_number, machine.Pin.OUT, value=0)
    _hardware_emit("machine.Pin", "CALL_OK", pin_number)
    for name, action, expected in (("on", pin.on, 1), ("off", pin.off, 0), ("value", lambda: pin.value(1), 1)):
        _hardware_call("machine.Pin." + name, action)
        _hardware_call("machine.Pin.value.readback", pin.value, lambda result, expected=expected: result == expected)
        _hardware_wait(milliseconds)
    pin.init(machine.Pin.IN, machine.Pin.PULL_DOWN)
    _hardware_call("machine.Pin.init", pin.value, lambda result: result == 0)
    pin.init(machine.Pin.IN, machine.Pin.PULL_UP)
    _hardware_call("machine.Pin.pullup", pin.value, lambda result: result == 1)
    pwm = machine.PWM(machine.Pin(pin_number), freq=1000, duty_u16=16384)
    _hardware_emit("machine.PWM", "CALL_OK")
    for name in ("freq", "duty", "duty_u16", "duty_ns"):
        _hardware_call("machine.PWM." + name, getattr(pwm, name))
    print("HARDWARE_PWM_READY")
    _hardware_wait(milliseconds)
    _hardware_call("machine.PWM.freq.set", lambda: pwm.freq(500))
    _hardware_call("machine.PWM.duty_u16.set", lambda: pwm.duty_u16(32768))
    _hardware_wait(milliseconds)
    _hardware_call("machine.PWM.deinit", pwm.deinit)
    pin.init(machine.Pin.IN, pull=None)


def _hardware_power():
    power = M5.Power
    # This stage runs in a disposable virtual session: PMIC setters require
    # host register inspection. Methods unsupported by that PMIC stay explicit.
    for name, args in (
        ("setExtOutput", (True,)), ("getExtOutput", ()),
        ("setExtOutput", (False,)), ("getExtOutput", ()),
        ("setUsbOutput", (True,)), ("getUsbOutput", ()),
        ("setUsbOutput", (False,)), ("getUsbOutput", ()),
        ("setLed", (64,)), ("setLed", (0,)),
        ("setBatteryCharge", (True,)), ("setChargeCurrent", (100,)),
        ("setChargeVoltage", (4200,)), ("setBatteryCharge", (False,)),
        ("setVibration", (64,)), ("setVibration", (0,)),
    ):
        _hardware_call("M5.Power." + name, lambda name=name, args=args: getattr(power, name)(*args))
    for name in ("getExtVoltage", "getExtCurrent", "getPortVbus", "getPortCurrent"):
        _hardware_call("M5.Power." + name, lambda name=name: getattr(power, name)(power.PORT.A))
    _hardware_call("M5.Power.setExtPortBusConfig", lambda: power.setExtPortBusConfig(direction=0, output_enable=0, voltage=3000, current_limit=232))


def _hardware_rtc():
    rtc = machine.RTC()
    original = _hardware_call("machine.RTC.datetime.read", rtc.datetime)
    target = (2026, 10, 27, 1, 12, 34, 56, 0)
    _hardware_call("machine.RTC.datetime.write", lambda: rtc.datetime(target))
    _hardware_call("machine.RTC.datetime", rtc.datetime, lambda value: tuple(value[:7]) == target[:7])
    _hardware_wait(1100)
    _hardware_call("machine.RTC.elapsed", rtc.datetime, lambda value: value[6] in (57, 58))
    memory = _hardware_call("machine.RTC.memory.read", rtc.memory)
    _hardware_call("machine.RTC.memory.write", lambda: rtc.memory(b"UIFLOW_API_SWEEP"))
    _hardware_call("machine.RTC.memory", rtc.memory, lambda value: value == b"UIFLOW_API_SWEEP")
    if memory is not None:
        rtc.memory(memory)
    if original is not None:
        rtc.datetime(original)


def _hardware_camera():
    import camera
    _hardware_call("camera.init", lambda: camera.init(pixformat=camera.RGB565, framesize=camera.QQVGA))
    for axis in ("hmirror", "vflip"):
        setter, getter = getattr(camera, "set_" + axis), getattr(camera, "get_" + axis)
        for value in (False, True, False):
            _hardware_call("camera.set_" + axis, lambda setter=setter, value=value: setter(value))
            _hardware_call("camera.get_" + axis, getter, lambda result, value=value: result == value)
    image = _hardware_call("camera.snapshot", camera.snapshot)
    if image is not None:
        _hardware_call("camera.snapshot.width", image.width)
        _hardware_call("camera.snapshot.height", image.height)
        _hardware_call("camera.snapshot.display", lambda: M5.Display.show(image, 0, 0, 160, 120))
        print("HARDWARE_CAMERA_FRAME_READY")


def _hardware_ir_rgb(milliseconds):
    from hardware import IR, RGB
    ir = _hardware_call("hardware.IR", IR)
    if ir is not None:
        _hardware_call("hardware.IR.tx", lambda: ir.tx(0x12, 0x34))
        _hardware_call("hardware.IR.rx_cb", lambda: ir.rx_cb(lambda data, address, control: print("HARDWARE_IR_RX", data, address, control)))
    rgb = _hardware_call("hardware.RGB", RGB)
    if rgb is not None:
        _hardware_call("hardware.RGB.set_brightness", lambda: rgb.set_brightness(100))
        _hardware_call("hardware.RGB.color_to_rgb", lambda: rgb.color_to_rgb(0x123456), lambda value: tuple(value) == (0x12, 0x34, 0x56))
        _hardware_call("hardware.RGB.color_to_wrgb", lambda: rgb.color_to_wrgb(0x78123456))
        _hardware_call("hardware.RGB.set_color", lambda: rgb.set_color(0, 0x123456))
        _hardware_call("hardware.RGB.fill_color", lambda: rgb.fill_color(0x123456))
        for color in ((32, 0, 0), (0, 32, 0), (0, 0, 0)):
            _hardware_call("hardware.RGB.fill", lambda color=color: rgb.fill(color))
            _hardware_call("hardware.RGB.write", rgb.write)
            _hardware_call("hardware.RGB.getitem", lambda: rgb[0], lambda value, color=color: tuple(value) == color)
            _hardware_wait(milliseconds)


def _hardware_adc(pin_number, expected):
    adc = machine.ADC(machine.Pin(pin_number), atten=machine.ADC.ATTN_11DB)
    _hardware_emit("machine.ADC", "CALL_OK", pin_number)
    for name in ("read", "read_u16", "read_uv"):
        value = expected.get(name)
        validator = None if value is None else lambda result, value=value: abs(result - value) <= max(2, abs(value) * 0.02)
        _hardware_call("machine.ADC." + name, getattr(adc, name), validator)
    _hardware_call("machine.ADC.atten", lambda: adc.atten(machine.ADC.ATTN_11DB))
    _hardware_call("machine.ADC.width", lambda: adc.width(machine.ADC.WIDTH_12BIT))
    _hardware_call("machine.ADC.init", lambda: adc.init(atten=machine.ADC.ATTN_11DB))
    _hardware_call("machine.ADC.block", adc.block)


def _hardware_i2c(expected):
    # Address/register/data must refer to a host-mounted writable Unit register.
    # Example fixture: 8Servos setup/output bank, not a sensor identity register.
    address = expected["address"]
    register = expected["register"]
    payload = bytes(expected["payload"])
    controller = expected.get("controller", 0)
    scl = expected.get("scl", 1)
    sda = expected.get("sda", 2)
    i2c = machine.I2C(controller, scl=machine.Pin(scl), sda=machine.Pin(sda), freq=100000)
    _hardware_emit("machine.I2C", "CALL_OK")
    _hardware_call("machine.I2C.scan", i2c.scan, lambda values: address in values)
    original = i2c.readfrom_mem(address, register, len(payload))
    _hardware_call("machine.I2C.writeto_mem", lambda: i2c.writeto_mem(address, register, payload))
    _hardware_call("machine.I2C.readfrom_mem", lambda: i2c.readfrom_mem(address, register, len(payload)), lambda value: value == payload)
    buffer = bytearray(len(payload))
    _hardware_call("machine.I2C.readfrom_mem_into", lambda: i2c.readfrom_mem_into(address, register, buffer))
    _hardware_emit("machine.I2C.readfrom_mem_into.bytes", "API_ASSERTION_PASS" if buffer == payload else "FAIL", list(buffer))
    _hardware_call("machine.I2C.writeto", lambda: i2c.writeto(address, bytes((register,)) + payload))
    i2c.writeto(address, bytes((register,)), False)
    _hardware_call("machine.I2C.readfrom", lambda: i2c.readfrom(address, len(payload)), lambda value: value == payload)
    i2c.writeto(address, bytes((register,)), False)
    _hardware_call("machine.I2C.readfrom_into", lambda: i2c.readfrom_into(address, buffer))
    _hardware_call("machine.I2C.writevto", lambda: i2c.writevto(address, [bytes((register,)), payload]))
    _hardware_call("machine.I2C.init", lambda: i2c.init(scl=machine.Pin(scl), sda=machine.Pin(sda), freq=400000))
    i2c.writeto_mem(address, register, original)
    _hardware_call("machine.I2C.deinit", i2c.deinit)


def _hardware_spi(expected):
    # Cardputer-ADV SPI cap fixture: explicit addon pins and chip identity.
    power = machine.Pin(3, machine.Pin.OUT, value=1)
    bus = machine.SPI(1, baudrate=2000000, polarity=0, phase=1,
                      sck=machine.Pin(40), mosi=machine.Pin(14), miso=machine.Pin(39))
    select = machine.Pin(6, machine.Pin.OUT, value=1)
    chip_id = expected["chip_id"]
    _hardware_emit("machine.SPI", "CALL_OK")
    select(0)
    _hardware_call("machine.SPI.write", lambda: bus.write(b"\x7f"))
    _hardware_call("machine.SPI.read", lambda: bus.read(1), lambda value: value == bytes((chip_id,)))
    select(1)
    select(0)
    bus.write(b"\x7f")
    data = bytearray(1)
    _hardware_call("machine.SPI.readinto", lambda: bus.readinto(data))
    _hardware_emit("machine.SPI.readinto.bytes", "API_ASSERTION_PASS" if data == bytes((chip_id,)) else "FAIL", list(data))
    select(1)
    select(0)
    data = bytearray(2)
    _hardware_call("machine.SPI.write_readinto", lambda: bus.write_readinto(b"\x7f\x00", data))
    _hardware_emit("machine.SPI.write_readinto.bytes", "API_ASSERTION_PASS" if data[1] == chip_id else "FAIL", list(data))
    select(1)
    _hardware_call("machine.SPI.init", lambda: bus.init(baudrate=1000000, polarity=0, phase=1))
    _hardware_call("machine.SPI.deinit", bus.deinit)


def _hardware_config():
    for name in ("Speaker", "Mic"):
        owner = getattr(M5, name)
        owner.end()
        fields = [field for field in dir(owner.config()) if not field.startswith("_")]
        for field in fields:
            original = owner.config()
            candidate = owner.config()
            old = getattr(candidate, field)
            value = old
            if isinstance(old, bool):
                value = not old
            elif isinstance(old, int) and field == "sample_rate":
                value = 8000 if old != 8000 else 16000
            elif isinstance(old, int) and field == "magnification":
                value = 2 if old != 2 else 4
            elif isinstance(old, int) and field == "dma_buf_len":
                value = 64 if old != 64 else 128
            api = "M5." + name + ".config." + field
            try:
                setattr(candidate, field, value)
                owner.config(candidate)
                actual = owner.config(field)
                _hardware_emit(api, "API_ASSERTION_PASS" if actual == value else "FAIL", {"before": old, "trial": value, "actual": actual}, "configuration binding roundtrip while stopped; not a hardware data-plane claim")
                owner.config(**{field: old})
                _hardware_emit("M5." + name + ".config.keyword." + field, "API_ASSERTION_PASS" if owner.config(field) == old else "FAIL")
            except Exception as error:
                _hardware_emit(api, "ERROR", detail=repr(error))
            finally:
                owner.config(original)


def run_hardware(stage="read-only", expected=None, milliseconds=1000, pin_number=None):
    """Execute one isolated stage. Host supplies only physical/QOM expectations."""
    if expected is None:
        expected = {}
    print("HARDWARE_STAGE_START " + stage)
    if stage == "read-only":
        _hardware_read_only()
    elif stage == "sensors":
        _hardware_sensors(expected)
    elif stage == "audio":
        _hardware_audio(milliseconds)
    elif stage == "mic":
        _hardware_mic(expected)
    elif stage == "input":
        _hardware_inputs(milliseconds)
    elif stage == "keyboard":
        _hardware_keyboard(milliseconds)
    elif stage == "power":
        _hardware_power()
    elif stage == "rtc":
        _hardware_rtc()
    elif stage == "camera":
        _hardware_camera()
    elif stage == "ir-rgb":
        _hardware_ir_rgb(milliseconds)
    elif stage == "i2c":
        _hardware_i2c(expected)
    elif stage == "spi":
        _hardware_spi(expected)
    elif stage == "config":
        _hardware_config()
    elif stage == "adc":
        if pin_number is None:
            raise ValueError("adc stage requires an explicitly free pin_number")
        _hardware_adc(pin_number, expected)
    elif stage == "gpio":
        if pin_number is None:
            raise ValueError("gpio stage requires an explicitly free pin_number")
        _hardware_gpio(milliseconds, pin_number)
    else:
        raise ValueError("unknown hardware stage: " + stage)
    print("HARDWARE_STAGE_END " + stage)
