"""One UIFlow2 guest exercising StackChan board, WiFi and BLE."""

import M5
import camera
import network
import socket
import time
from M5 import *


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18087
BLE_NAME = "M5-STACKCHAN-UNIFIED"

state = {
    "audio": "init",
    "ble": "init",
    "body_touch": "init",
    "camera": "init",
    "http": "not-run",
    "imu": "init",
    "ir": "init",
    "mag": "init",
    "mic": "init",
    "nfc": "init",
    "power": (0, 0, 0),
    "rgb": "init",
    "rtc": "init",
    "servo": "init",
    "touch": "init",
    "wifi": "init",
}
log_uart = None


def emit(*parts):
    line = " ".join(str(part) for part in parts)
    if log_uart:
        log_uart.write(line + "\n")
    else:
        print(line)


def draw():
    display = M5.Display
    display.fillScreen(display.COLOR.BLACK)
    display.drawRect(4, 4, 311, 231, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLACK)
    display.setTextSize(2)
    display.setCursor(14, 12)
    display.print("StackChan unified")
    draw_progress()
    display.fillRect(55, 176, 210, 44, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLUE)
    display.setTextSize(2)
    display.setCursor(125, 190)
    display.print("TOUCH")


def draw_progress():
    display = M5.Display
    display.fillRect(12, 42, 296, 126, display.COLOR.BLACK)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLACK)
    display.setTextSize(1)
    lines = (
        "WiFi:%s BLE:%s HTTP:%s" % (
            state["wifi"],
            state["ble"],
            state["http"],
        ),
        "BAT %d%% %dmV C:%d" % state["power"],
        "IMU:%s MAG:%s" % (state["imu"], state["mag"]),
        "RTC:%s SERVO:%s" % (state["rtc"], state["servo"]),
        "CAM:%s MIC:%s SPK:%s" % (
            state["camera"],
            state["mic"],
            state["audio"],
        ),
        "RGB:%s NFC:%s IR:%s" % (
            state["rgb"],
            state["nfc"],
            state["ir"],
        ),
        "TOUCH:%s BODY:%s" % (
            state["touch"],
            state["body_touch"],
        ),
    )
    for index, line in enumerate(lines):
        display.setCursor(16, 50 + index * 16)
        display.print(line[:39])


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_STACKCHAN_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_STACKCHAN_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_STACKCHAN_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    from machine import I2C, Pin, UART
    from driver.aw9523 import AW9523, Pin as ExpanderPin
    from driver.ina226 import INA226
    from driver.m5ioe1 import M5IOE1, RGB
    from driver.scs_servo import Scscl
    from driver.si12t import Si12T
    from hardware import IR, NFC, UART as HardwareUART
    from rtc_probe import check_pcf8563

    M5.begin()
    log_uart = HardwareUART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_STACKCHAN_MAIN")
    M5.Display.setRotation(1)
    M5.Display.setBrightness(255)
    emit("UNIFIED_STACKCHAN_BOARD", M5.getBoard())
    emit(
        "UNIFIED_STACKCHAN_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("UNIFIED_STACKCHAN_POWER", *state["power"])
    emit("UNIFIED_STACKCHAN_IMU_CONFIG_READY")
    time.sleep_ms(500)

    try:
        imu_type = Imu.getType()
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        state["imu"] = "pass"
        emit("UNIFIED_STACKCHAN_IMU", imu_type)
        emit("UNIFIED_STACKCHAN_ACCEL", *accel)
        emit("UNIFIED_STACKCHAN_GYRO", *gyro)
    except Exception as error:
        state["imu"] = "fail"
        emit("UNIFIED_STACKCHAN_IMU_ERROR", repr(error))

    try:
        state["mag"] = "pass"
        emit("UNIFIED_STACKCHAN_MAG", *Imu.getMag())
    except Exception as error:
        state["mag"] = "fail"
        emit("UNIFIED_STACKCHAN_MAG_ERROR", repr(error))

    i2c = I2C(1, scl=Pin(11), sda=Pin(12), freq=100000)

    try:
        rtc = check_pcf8563(i2c)
        state["rtc"] = "pass"
        emit("UNIFIED_STACKCHAN_RTC", *rtc)
    except Exception as error:
        state["rtc"] = "fail"
        emit("UNIFIED_STACKCHAN_RTC_ERROR", repr(error))

    try:
        expander = AW9523(i2c, 0x58)
        output = ExpanderPin(0, ExpanderPin.OUT, 1)
        input_pin = ExpanderPin(12, ExpanderPin.IN)
        emit("UNIFIED_STACKCHAN_AW9523", output.value(), input_pin.value())
        if output.value() != 1 or input_pin.value() != 0:
            raise RuntimeError("AW9523 state is invalid")
    except Exception as error:
        emit("UNIFIED_STACKCHAN_AW9523_ERROR", repr(error))

    try:
        monitor = INA226(i2c, 0x41, shunt_resistor=0.08)
        monitor.configure(
            avg=INA226.CFG_AVGMODE_16SAMPLES,
            vbus_conv_time=INA226.CFG_VBUSCT_8244us,
            vshunt_conv_time=INA226.CFG_VSHUNTCT_8244us,
            mode=INA226.CFG_MODE_SANDBVOLT_CONTINUOUS,
        )
        monitor.calibrate(cal_value=0x0800)
        emit(
            "UNIFIED_STACKCHAN_INA226",
            "%.2f" % monitor.read_bus_voltage(),
            "%.2f" % monitor.read_current(),
            "%.2f" % monitor.read_power(),
        )
    except Exception as error:
        emit("UNIFIED_STACKCHAN_INA226_ERROR", repr(error))

    try:
        emit(
            "UNIFIED_STACKCHAN_ALS",
            M5.Als.getLightSensorData(),
            M5.Als.getProximitySensorData(),
        )
    except Exception as error:
        emit("UNIFIED_STACKCHAN_ALS_ERROR", repr(error))

    try:
        ioe = M5IOE1(i2c, 0x6F)
        rgb = RGB(ioe, io=14, n=12)
        rgb.fill_color(0xFF0000)
        raw_first = ioe.read_reg16(0x30)
        raw_last = ioe.read_reg16(0x30 + 11 * 2)
        emit("UNIFIED_STACKCHAN_RGB", hex(raw_first), hex(raw_last))
        if raw_first != 0xF800 or raw_last != 0xF800:
            raise RuntimeError("M5IOE1 RGB RAM mismatch")
        state["rgb"] = "pass"
    except Exception as error:
        state["rgb"] = "fail"
        emit("UNIFIED_STACKCHAN_RGB_ERROR", repr(error))

    body_touch = None
    try:
        body_touch = Si12T(i2c)
        emit("UNIFIED_STACKCHAN_BODY_TOUCH_READY")
    except Exception as error:
        state["body_touch"] = "fail"
        emit("UNIFIED_STACKCHAN_BODY_TOUCH_ERROR", repr(error))

    try:
        servo_uart = UART(1, baudrate=1000000, tx=Pin(6), rx=Pin(7))
        servo = Scscl(servo_uart, end=1, level=1)
        if servo.ping(1) != 1 or servo.ping(2) != 2:
            raise RuntimeError("servo ping failed")
        if not servo.enable_torque(1, 1) or not servo.enable_torque(2, 1):
            raise RuntimeError("servo torque failed")
        if not servo.write_pos(1, 500, 100, 0):
            raise RuntimeError("servo X write failed")
        if not servo.write_pos(2, 300, 100, 0):
            raise RuntimeError("servo Y write failed")
        time.sleep_ms(50)
        x = servo.read_pos(1)
        y = servo.read_pos(2)
        emit("UNIFIED_STACKCHAN_SERVO", x, y)
        if x != 500 or y != 300:
            raise RuntimeError("servo readback mismatch")
        state["servo"] = "pass"
    except Exception as error:
        state["servo"] = "fail"
        emit("UNIFIED_STACKCHAN_SERVO_ERROR", repr(error))

    try:
        nfc = NFC()
        card = nfc.detect()
        if card is None:
            raise RuntimeError("NFC tag not detected")
        nfc.write(card, 12, b"CHAN")
        if nfc.read(card, 12) != b"CHAN":
            raise RuntimeError("NFC page readback mismatch")
        state["nfc"] = "pass"
        emit("UNIFIED_STACKCHAN_NFC", card.uid_str)
    except Exception as error:
        state["nfc"] = "fail"
        emit("UNIFIED_STACKCHAN_NFC_ERROR", repr(error))

    ir_result = {"count": 0, "address": -1, "command": -1}

    def ir_rx(data, address, control):
        ir_result["count"] += 1
        ir_result["address"] = address
        ir_result["command"] = data
        emit("UNIFIED_STACKCHAN_IR_RX", address, data, control)

    try:
        ir = IR()
        ir.rx_cb(ir_rx)
        ir.tx(0x56, 0xA3)
        deadline = time.ticks_add(time.ticks_ms(), 5000)
        while (
            not ir_result["count"]
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(20)
        if ir_result["count"] == 0:
            raise RuntimeError("IR loopback timed out")
        state["ir"] = "pass"
    except Exception as error:
        state["ir"] = "fail"
        emit("UNIFIED_STACKCHAN_IR_ERROR", repr(error))

    try:
        if not Mic.begin():
            raise RuntimeError("mic begin failed")
        samples = bytearray(12800)
        if not Mic.record(samples, 16000, False):
            raise RuntimeError("mic record failed")
        deadline = time.ticks_add(time.ticks_ms(), 2500)
        while (
            Mic.isRecording()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(20)
        Mic.end()
        nonzero = sum(1 for value in samples if value)
        peak = max(samples) - min(samples)
        emit("UNIFIED_STACKCHAN_MIC", nonzero, peak)
        if nonzero < 100 or peak < 10:
            raise RuntimeError("mic samples are silent")
        state["mic"] = "pass"
    except Exception as error:
        state["mic"] = "fail"
        emit("UNIFIED_STACKCHAN_MIC_ERROR", repr(error))

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolumePercentage(0.6)
        Speaker.tone(440, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("speaker stopped unexpectedly")
        state["audio"] = "pass"
        emit("UNIFIED_STACKCHAN_AUDIO_PASS")
    except Exception as error:
        state["audio"] = "fail"
        emit("UNIFIED_STACKCHAN_AUDIO_ERROR", repr(error))

    try:
        camera.init(pixformat=camera.RGB565, framesize=camera.QVGA)
        image = camera.snapshot()
        if image is None:
            raise RuntimeError("camera snapshot returned None")
        detail = "%dx%d %d bytes" % (
            image.width(),
            image.height(),
            image.size(),
        )
        image.draw_string(8, 8, "STACKCHAN", color=(0, 255, 0), scale=1)
        M5.Display.show(image, 0, 0)
        state["camera"] = "pass"
        emit("UNIFIED_STACKCHAN_CAMERA", detail)
    except Exception as error:
        state["camera"] = "fail"
        emit("UNIFIED_STACKCHAN_CAMERA_ERROR", repr(error))

    draw()

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_STACKCHAN_WIFI_SCAN", len(networks))
        emit("UNIFIED_STACKCHAN_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_STACKCHAN_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_STACKCHAN_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_STACKCHAN_WIFI_ERROR", repr(error))

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_STACKCHAN_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_STACKCHAN_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_STACKCHAN_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_STACKCHAN_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_STACKCHAN_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_STACKCHAN_BLE_ERROR", repr(error))

    if state["audio"] == "pass":
        try:
            Speaker.tone(440, 15000)
            time.sleep_ms(100)
            if not Speaker.isRunning():
                raise RuntimeError("speaker hold stopped unexpectedly")
            emit("UNIFIED_STACKCHAN_AUDIO_HOLD")
        except Exception as error:
            state["audio"] = "fail"
            emit("UNIFIED_STACKCHAN_AUDIO_HOLD_ERROR", repr(error))

    draw()
    emit("UNIFIED_STACKCHAN_READY")
    touch_seen = False
    body_seen = False
    while True:
        M5.update()
        if M5.Touch.getCount() > 0 and not touch_seen:
            touch_seen = True
            state["touch"] = "pass"
            emit(
                "UNIFIED_STACKCHAN_TOUCH",
                M5.Touch.getX(),
                M5.Touch.getY(),
            )
            draw()
        if body_touch is not None and not body_seen:
            value = body_touch.get_touch_status()
            if value is not None and any(value):
                body_seen = True
                state["body_touch"] = "pass"
                emit("UNIFIED_STACKCHAN_BODY_TOUCH", value)
                draw()
        time.sleep_ms(20)


main()
