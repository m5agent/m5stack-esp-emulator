"""One UIFlow2 guest exercising CoreS3 board, WiFi and BLE data planes."""

import M5
import network
import socket
import time
from M5 import *


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18081
BLE_NAME = "M5-CORES3-UNIFIED"

state = {
    "ble": "init",
    "http": "not-run",
    "imu": (0.0, 0.0, 0.0),
    "power": (0, 0, 0),
    "speaker": "init",
    "touch": 0,
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
    display.drawRect(3, 3, 313, 233, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(12, 12)
    display.print("CoreS3 unified")
    display.setTextSize(1)
    display.setCursor(12, 42)
    display.print("WiFi:%s  BLE:%s" % (state["wifi"], state["ble"]))
    display.setCursor(12, 58)
    display.print("HTTP:%s  SPK:%s" % (state["http"], state["speaker"]))
    display.setCursor(12, 74)
    display.print("touch:%d" % state["touch"])
    display.setCursor(12, 90)
    display.print("IMU %.2f %.2f %.2f" % state["imu"])
    display.setCursor(12, 106)
    display.print("BAT %d%% %dmV C:%d" % state["power"])
    display.fillRect(55, 153, 210, 60, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.GREEN)
    display.setTextSize(2)
    display.setCursor(111, 171)
    display.print("TAP")


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_CORES3_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_CORES3_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_CORES3_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    from hardware import UART

    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_CORES3_MAIN")
    M5.begin()
    M5.Display.setRotation(1)
    M5.Display.setBrightness(255)
    emit("UNIFIED_CORES3_BOARD", M5.getBoard())
    emit(
        "UNIFIED_CORES3_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    state["imu"] = Imu.getAccel()
    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("UNIFIED_CORES3_IMU", *state["imu"])
    emit("UNIFIED_CORES3_POWER", *state["power"])
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
        emit("UNIFIED_CORES3_AUDIO_PASS")
    except Exception as error:
        state["speaker"] = "fail"
        emit("UNIFIED_CORES3_AUDIO_ERROR", repr(error))

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_CORES3_WIFI_SCAN", len(networks))
        emit("UNIFIED_CORES3_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_CORES3_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_CORES3_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_CORES3_WIFI_ERROR", repr(error))

    draw()
    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_CORES3_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_CORES3_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_CORES3_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_CORES3_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_CORES3_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_CORES3_BLE_ERROR", repr(error))

    draw()
    emit("UNIFIED_CORES3_READY")
    while True:
        M5.update()
        if M5.Touch.getCount() > 0:
            x = M5.Touch.getX()
            y = M5.Touch.getY()
            if 55 <= x <= 265 and 153 <= y <= 213:
                state["touch"] += 1
                emit("UNIFIED_CORES3_TOUCH", x, y, state["touch"])
                draw()
        time.sleep_ms(20)


main()
