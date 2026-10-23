"""One UIFlow2 guest exercising StickS3 board, WiFi and BLE data planes."""

import M5
import network
import socket
import time
from M5 import *


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18080
BLE_NAME = "M5-STICKS3-UNIFIED"

state = {
    "a": 0,
    "ble": "init",
    "http": "not-run",
    "imu": (0.0, 0.0, 0.0),
    "power": (0, 0, 0),
    "speaker": "init",
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
    display.setTextColor(display.COLOR.WHITE)
    display.setTextSize(1)
    display.setCursor(5, 5)
    display.print("StickS3 unified")
    display.setCursor(5, 22)
    display.print("A:%d" % state["a"])
    display.setCursor(5, 36)
    display.print("WiFi:%s" % state["wifi"])
    display.setCursor(5, 50)
    display.print("BLE:%s" % state["ble"])
    display.setCursor(5, 64)
    display.print("HTTP:%s" % state["http"])
    display.setCursor(5, 78)
    display.print("SPK:%s" % state["speaker"])
    display.setCursor(5, 92)
    display.print(
        "IMU %.2f %.2f %.2f" % state["imu"]
    )
    display.setCursor(5, 106)
    display.print(
        "BAT %d%% %dmV C:%d" % state["power"]
    )
    display.drawRect(2, 2, 131, 236, display.COLOR.BLUE)
    display.fillRect(4, 128, 127, 48, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.GREEN)
    display.setTextSize(2)
    display.setCursor(20, 140)
    display.print("BTN A")


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(
            b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n"
        )
        response = bytearray()
        while b"UNIFIED_STICKS3_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_STICKS3_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_STICKS3_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    from hardware import UART

    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_STICKS3_MAIN")

    M5.begin()
    M5.Display.setRotation(0)
    M5.Display.setBrightness(255)
    emit("UNIFIED_STICKS3_BOARD", M5.getBoard())
    emit(
        "UNIFIED_STICKS3_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    state["imu"] = Imu.getAccel()
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("UNIFIED_STICKS3_IMU", *state["imu"])
    emit("UNIFIED_STICKS3_POWER", *state["power"])

    draw()

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolumePercentage(0.6)
        Speaker.tone(440, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("speaker stopped unexpectedly")
        state["speaker"] = "pass"
        emit("UNIFIED_STICKS3_AUDIO_PASS")
    except Exception as error:
        state["speaker"] = "fail"
        emit("UNIFIED_STICKS3_AUDIO_ERROR", repr(error))

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_STICKS3_WIFI_SCAN", len(networks))
        emit("UNIFIED_STICKS3_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_STICKS3_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_STICKS3_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_STICKS3_WIFI_ERROR", repr(error))

    draw()

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_STICKS3_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_STICKS3_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_STICKS3_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_STICKS3_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_STICKS3_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_STICKS3_BLE_ERROR", repr(error))

    draw()
    emit("UNIFIED_STICKS3_READY")

    while True:
        M5.update()
        if BtnA.wasPressed():
            state["a"] += 1
            emit("UNIFIED_STICKS3_BTN_A", state["a"])
            draw()
        time.sleep_ms(20)


main()
