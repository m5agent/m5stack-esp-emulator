"""One UIFlow2 Core2 guest exercising board, WiFi and BLE."""

import M5
import network
import socket
import time
from M5 import *


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18089
BLE_NAME = "M5-CORE2-UNIFIED"

state = {
    "audio": "init",
    "ble": "init",
    "http": "not-run",
    "imu": "init",
    "ina": "init",
    "mic": "init",
    "power": (0, 0, 0),
    "rtc": "init",
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
    display.print("Core2 unified")
    display.setTextSize(1)
    lines = (
        "WiFi:%s BLE:%s" % (state["wifi"], state["ble"]),
        "HTTP:%s TOUCH:%s" % (state["http"], state["touch"]),
        "PMIC:%d BAT:%dmV" % state["power"],
        "IMU:%s RTC:%s" % (state["imu"], state["rtc"]),
        "INA:%s" % state["ina"],
        "SPK:%s MIC:%s" % (state["audio"], state["mic"]),
    )
    for index, line in enumerate(lines):
        display.setCursor(14, 48 + index * 24)
        display.print(line[:48])
    display.fillRect(160, 180, 140, 24, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLUE)
    display.setCursor(224, 186)
    display.print("TOUCH")


def probe_http():
    client = socket.socket()
    client.settimeout(10)
    try:
        client.connect((HTTP_HOST, HTTP_PORT))
        client.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_CORE2_OK" not in response and len(response) < 2048:
            chunk = client.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_CORE2_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_CORE2_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        client.close()


def main():
    global log_uart

    from machine import I2C, Pin
    from rtc_probe import check_pcf8563

    M5.begin()
    emit("UNIFIED_CORE2_MAIN")
    emit("UNIFIED_CORE2_BOARD", M5.getBoard())
    emit(
        "UNIFIED_CORE2_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )
    emit("UNIFIED_CORE2_IO_CONFIG_READY")
    time.sleep_ms(1500)

    try:
        state["power"] = (
            Power.getType(),
            Power.getBatteryVoltage(),
        )
        emit("UNIFIED_CORE2_POWER", *state["power"])
    except Exception as error:
        emit("UNIFIED_CORE2_POWER_ERROR", repr(error))

    try:
        imu_type = Imu.getType()
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        state["imu"] = "pass"
        emit("UNIFIED_CORE2_IMU", imu_type)
        emit("UNIFIED_CORE2_ACCEL", *accel)
        emit("UNIFIED_CORE2_GYRO", *gyro)
    except Exception as error:
        state["imu"] = "fail"
        emit("UNIFIED_CORE2_IMU_ERROR", repr(error))

    try:
        rtc = check_pcf8563(
            I2C(1, scl=Pin(22), sda=Pin(21), freq=100000)
        )
        state["rtc"] = "pass"
        emit("UNIFIED_CORE2_RTC", *rtc)
    except Exception as error:
        state["rtc"] = "fail"
        emit("UNIFIED_CORE2_RTC_ERROR", repr(error))

    try:
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
        chip_id = int.from_bytes(i2c.readfrom_mem(0x40, 0xFF, 2), "big")
        bus_raw = int.from_bytes(i2c.readfrom_mem(0x40, 0x02, 2), "big")
        shunt_raw = int.from_bytes(i2c.readfrom_mem(0x40, 0x01, 2), "big")
        emit("UNIFIED_CORE2_INA3221", hex(chip_id), bus_raw, shunt_raw)
        if chip_id != 0x3220 or bus_raw != 600 or shunt_raw != 60:
            raise RuntimeError("INA3221 register mismatch")
        state["ina"] = "pass"
    except Exception as error:
        state["ina"] = "fail"
        emit("UNIFIED_CORE2_INA3221_ERROR", repr(error))

    try:
        if not Mic.begin():
            raise RuntimeError("mic begin failed")
        samples = bytearray(6400)
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
        emit("UNIFIED_CORE2_MIC", nonzero, peak)
        if nonzero < 100 or peak < 10:
            raise RuntimeError("mic samples are silent")
        state["mic"] = "pass"
    except Exception as error:
        state["mic"] = "fail"
        emit("UNIFIED_CORE2_MIC_ERROR", repr(error))

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolumePercentage(0.6)
        Speaker.tone(440, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("speaker stopped unexpectedly")
        state["audio"] = "pass"
        emit("UNIFIED_CORE2_AUDIO_PASS")
    except Exception as error:
        state["audio"] = "fail"
        emit("UNIFIED_CORE2_AUDIO_ERROR", repr(error))

    draw()

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_CORE2_WIFI_SCAN", len(networks))
        emit("UNIFIED_CORE2_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_CORE2_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_CORE2_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_CORE2_WIFI_ERROR", repr(error))

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_CORE2_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_CORE2_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_CORE2_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_CORE2_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_CORE2_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_CORE2_BLE_ERROR", repr(error))

    if state["audio"] == "pass":
        try:
            Speaker.tone(440, 15000)
            time.sleep_ms(100)
            if not Speaker.isRunning():
                raise RuntimeError("speaker hold stopped unexpectedly")
            emit("UNIFIED_CORE2_AUDIO_HOLD")
        except Exception as error:
            state["audio"] = "fail"
            emit("UNIFIED_CORE2_AUDIO_HOLD_ERROR", repr(error))

    draw()
    emit("UNIFIED_CORE2_READY")
    touch_seen = False
    while True:
        M5.update()
        if M5.Touch.getCount() > 0 and not touch_seen:
            touch_seen = True
            state["touch"] = "pass"
            emit(
                "UNIFIED_CORE2_TOUCH",
                M5.Touch.getX(),
                M5.Touch.getY(),
            )
            display = M5.Display
            display.fillRect(6, 6, 308, 24, display.COLOR.GREEN)
            display.setTextColor(display.COLOR.BLACK, display.COLOR.GREEN)
            display.setTextSize(2)
            display.setCursor(90, 12)
            display.print("TOUCH PASS")
        time.sleep_ms(20)


main()
