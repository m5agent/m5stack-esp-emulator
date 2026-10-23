"""One UIFlow2 guest exercising PaperColor board, WiFi and BLE."""

import M5
import network
import socket
import time
from M5 import *
from hardware import SHT4X


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18085
BLE_NAME = "M5-PAPERCOLOR-UNIFIED"

state = {
    "ble": "init",
    "http": "not-run",
    "key": 0,
    "power": (0, 0, 0),
    "sht40": (0.0, 0.0),
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
    display.fillScreen(display.COLOR.WHITE)
    display.drawRect(6, 6, 387, 587, display.COLOR.BLACK)
    display.setTextColor(display.COLOR.BLACK)
    display.setTextSize(3)
    display.setCursor(24, 36)
    display.print("PaperColor unified")
    draw_progress()
    display.fillRect(24, 520, 352, 44, display.COLOR.BLACK)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLACK)
    display.setCursor(160, 532)
    display.print("PRESS A")


def draw_progress():
    display = M5.Display
    display.fillRect(24, 100, 352, 240, display.COLOR.WHITE)
    display.setTextColor(display.COLOR.BLACK, display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(24, 110)
    display.print("WiFi:%s BLE:%s" % (state["wifi"], state["ble"]))
    display.setCursor(24, 150)
    display.print("HTTP:%s" % state["http"])
    display.setCursor(24, 190)
    display.print("SPK:%s key:%d" % (state["speaker"], state["key"]))
    display.setCursor(24, 230)
    display.print("BAT %d%% %dmV C:%d" % state["power"])
    display.setCursor(24, 270)
    display.print("SHT %.2fC %.2f%%" % state["sht40"])


def draw_key_state():
    display = M5.Display
    display.fillRect(24, 190, 352, 38, display.COLOR.WHITE)
    display.setTextColor(display.COLOR.BLACK, display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(24, 190)
    display.print("SPK:%s key:%d" % (state["speaker"], state["key"]))


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_PAPERCOLOR_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_PAPERCOLOR_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_PAPERCOLOR_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    from hardware import UART

    # GPIO43 is the e-paper DC pin on PaperColor.
    log_uart = UART(0, baudrate=115200, tx=44, rx=45)
    emit("UNIFIED_PAPERCOLOR_MAIN")
    M5.begin()
    M5.Display.setRotation(0)
    emit("UNIFIED_PAPERCOLOR_BOARD", M5.getBoard())
    emit(
        "UNIFIED_PAPERCOLOR_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("UNIFIED_PAPERCOLOR_POWER", *state["power"])

    try:
        state["sht40"] = SHT4X().measure()
        emit("UNIFIED_PAPERCOLOR_SHT40", *state["sht40"])
    except Exception as error:
        emit("UNIFIED_PAPERCOLOR_SHT40_ERROR", repr(error))

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolumePercentage(0.6)
        Speaker.tone(440, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("speaker stopped unexpectedly")
        state["speaker"] = "pass"
        emit("UNIFIED_PAPERCOLOR_AUDIO_PASS")
    except Exception as error:
        state["speaker"] = "fail"
        emit("UNIFIED_PAPERCOLOR_AUDIO_ERROR", repr(error))

    draw()

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_PAPERCOLOR_WIFI_SCAN", len(networks))
        emit("UNIFIED_PAPERCOLOR_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_PAPERCOLOR_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_PAPERCOLOR_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_PAPERCOLOR_WIFI_ERROR", repr(error))

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_PAPERCOLOR_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_PAPERCOLOR_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_PAPERCOLOR_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_PAPERCOLOR_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_PAPERCOLOR_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_PAPERCOLOR_BLE_ERROR", repr(error))

    if state["speaker"] == "pass":
        try:
            Speaker.tone(440, 15000)
            time.sleep_ms(100)
            if not Speaker.isRunning():
                raise RuntimeError("speaker hold stopped unexpectedly")
            emit("UNIFIED_PAPERCOLOR_AUDIO_HOLD")
        except Exception as error:
            state["speaker"] = "fail"
            emit("UNIFIED_PAPERCOLOR_AUDIO_HOLD_ERROR", repr(error))

    draw_progress()
    emit("UNIFIED_PAPERCOLOR_READY")
    while True:
        M5.update()
        if BtnA.wasPressed():
            state["key"] += 1
            emit("UNIFIED_PAPERCOLOR_KEY", state["key"])
            draw_key_state()
        time.sleep_ms(20)


main()
