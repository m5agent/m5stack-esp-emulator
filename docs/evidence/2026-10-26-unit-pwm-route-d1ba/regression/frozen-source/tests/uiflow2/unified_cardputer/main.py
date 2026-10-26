"""One UIFlow2 guest exercising Cardputer ADV board, WiFi and BLE."""

import M5
import machine
import network
import socket
import time
from M5 import *
from hardware import KeyboardI2C


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18082
BLE_NAME = "M5-CPTR-ADV-UNIFIED"

state = {
    "ble": "init",
    "http": "not-run",
    "imu": (0.0, 0.0, 0.0),
    "keys": 0,
    "speaker": "init",
    "wifi": "init",
}

i2c = machine.I2C(1, scl=machine.Pin(9), sda=machine.Pin(8), freq=400000)
intr = machine.Pin(11, mode=machine.Pin.IN, pull=None)
keyboard = KeyboardI2C(
    i2c,
    intr_pin=intr,
    mode=KeyboardI2C.ASCII_MODE,
)
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
    display.drawRect(3, 3, 233, 128, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(10, 10)
    display.print("Cardputer ADV")
    display.setTextSize(1)
    display.setCursor(10, 38)
    display.print("WiFi:%s BLE:%s" % (state["wifi"], state["ble"]))
    display.setCursor(10, 52)
    display.print("HTTP:%s SPK:%s" % (state["http"], state["speaker"]))
    display.setCursor(10, 66)
    display.print("IMU %.2f %.2f %.2f" % state["imu"])
    display.setCursor(10, 84)
    display.print("keys:%d" % state["keys"])
    display.fillRect(12, 103, 216, 22, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.GREEN)
    display.setTextSize(2)
    display.setCursor(77, 107)
    display.print("TYPE")


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_CARDPUTER_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_CARDPUTER_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_CARDPUTER_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    from hardware import UART

    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_CARDPUTER_MAIN")
    M5.begin()
    M5.Display.setBrightness(255)
    emit("UNIFIED_CARDPUTER_BOARD", M5.getBoard())
    emit(
        "UNIFIED_CARDPUTER_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    state["imu"] = Imu.getAccel()
    emit("UNIFIED_CARDPUTER_IMU", *state["imu"])
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
        emit("UNIFIED_CARDPUTER_AUDIO_PASS")
    except Exception as error:
        state["speaker"] = "fail"
        emit("UNIFIED_CARDPUTER_AUDIO_ERROR", repr(error))

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_CARDPUTER_WIFI_SCAN", len(networks))
        emit("UNIFIED_CARDPUTER_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_CARDPUTER_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_CARDPUTER_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_CARDPUTER_WIFI_ERROR", repr(error))

    draw()
    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_CARDPUTER_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_CARDPUTER_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)
        original_irq = server._irq

        def debug_irq(event, data):
            emit("UNIFIED_CARDPUTER_BLE_EVENT", event, repr(data))
            original_irq(event, data)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_CARDPUTER_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_CARDPUTER_BLE_ACK_SENT")

        server._ble.irq(debug_irq)
        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_CARDPUTER_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_CARDPUTER_BLE_ERROR", repr(error))

    draw()
    emit("UNIFIED_CARDPUTER_READY")
    while True:
        M5.update()
        keyboard._irq_handler(intr)
        while keyboard._keyevents:
            keyevent = keyboard._keyevents.pop(0)
            state["keys"] += 1
            emit(
                "UNIFIED_CARDPUTER_KEY",
                keyevent.keycode,
                state["keys"],
            )
            draw()
        time.sleep_ms(20)


main()
