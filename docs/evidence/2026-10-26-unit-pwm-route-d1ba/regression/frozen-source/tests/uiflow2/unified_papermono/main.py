"""One UIFlow2 guest exercising PaperMono board, WiFi and BLE."""

import M5
import network
import socket
import time
from M5 import *


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18086
BLE_NAME = "M5-PAPERMONO-UNIFIED"

state = {
    "ble": "init",
    "http": "not-run",
    "imu": "init",
    "key": 0,
    "mic": "not-run",
    "power": (0, 0, 0),
    "rgb": "init",
    "rtc": "init",
    "speaker": "init",
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
    display.fillScreen(display.COLOR.WHITE)
    display.drawRect(6, 6, 467, 787, display.COLOR.BLACK)
    display.setTextColor(display.COLOR.BLACK, display.COLOR.WHITE)
    display.setTextSize(3)
    display.setCursor(24, 36)
    display.print("PaperMono unified")
    draw_progress()
    display.fillRect(70, 660, 340, 76, display.COLOR.BLACK)
    display.setTextColor(display.COLOR.WHITE, display.COLOR.BLACK)
    display.setTextSize(3)
    display.setCursor(150, 684)
    display.print("TOUCH / KEY")


def draw_progress():
    display = M5.Display
    display.fillRect(24, 100, 432, 390, display.COLOR.WHITE)
    display.setTextColor(display.COLOR.BLACK, display.COLOR.WHITE)
    display.setTextSize(2)
    display.setCursor(24, 110)
    display.print("WiFi:%s BLE:%s" % (state["wifi"], state["ble"]))
    display.setCursor(24, 150)
    display.print("HTTP:%s" % state["http"])
    display.setCursor(24, 190)
    display.print("BAT %d%% %dmV C:%d" % state["power"])
    display.setCursor(24, 230)
    display.print("IMU:%s RGB:%s" % (state["imu"], state["rgb"]))
    display.setCursor(24, 270)
    display.print("RTC:%s" % state["rtc"])
    display.setCursor(24, 310)
    display.print("SPK:%s MIC:%s" % (state["speaker"], state["mic"]))
    display.setCursor(24, 350)
    display.print("TOUCH:%s KEY:%d" % (state["touch"], state["key"]))


def draw_input_state():
    draw_progress()


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_PAPERMONO_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_PAPERMONO_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_PAPERMONO_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    M5.begin()
    from hardware import UART

    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_PAPERMONO_MAIN")
    M5.Display.setRotation(0)
    emit("UNIFIED_PAPERMONO_BOARD", M5.getBoard())
    emit(
        "UNIFIED_PAPERMONO_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    state["power"] = (
        Power.getBatteryLevel(),
        Power.getBatteryVoltage(),
        1 if Power.isCharging() else 0,
    )
    emit("UNIFIED_PAPERMONO_POWER", *state["power"])

    try:
        imu_type = Imu.getType()
        accel = Imu.getAccel()
        gyro = Imu.getGyro()
        state["imu"] = "pass"
        emit("UNIFIED_PAPERMONO_IMU", imu_type)
        emit("UNIFIED_PAPERMONO_ACCEL", *accel)
        emit("UNIFIED_PAPERMONO_GYRO", *gyro)
    except Exception as error:
        state["imu"] = "fail"
        emit("UNIFIED_PAPERMONO_IMU_ERROR", repr(error))

    try:
        from machine import I2C, Pin
        from rtc_probe import check_rx8130

        rtc = check_rx8130(
            I2C(1, scl=Pin(48), sda=Pin(47), freq=100000)
        )
        state["rtc"] = "pass"
        emit("UNIFIED_PAPERMONO_RTC", *rtc)
    except Exception as error:
        state["rtc"] = "fail"
        emit("UNIFIED_PAPERMONO_RTC_ERROR", repr(error))

    try:
        M5.Led.setAllColor(0x00FF00)
        M5.Led.display()
        state["rgb"] = "pass"
        emit("UNIFIED_PAPERMONO_RGB")
    except Exception as error:
        state["rgb"] = "fail"
        emit("UNIFIED_PAPERMONO_RGB_ERROR", repr(error))

    try:
        if not Speaker.begin():
            raise RuntimeError("speaker begin failed")
        Speaker.setVolume(255)
        Speaker.tone(3500, 1000)
        time.sleep_ms(500)
        if not Speaker.isRunning():
            raise RuntimeError("speaker stopped unexpectedly")
        state["speaker"] = "pass"
        emit("UNIFIED_PAPERMONO_AUDIO_PASS")
    except Exception as error:
        state["speaker"] = "fail"
        emit("UNIFIED_PAPERMONO_AUDIO_ERROR", repr(error))

    draw()

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_PAPERMONO_WIFI_SCAN", len(networks))
        emit("UNIFIED_PAPERMONO_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_PAPERMONO_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_PAPERMONO_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_PAPERMONO_WIFI_ERROR", repr(error))

    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_PAPERMONO_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_PAPERMONO_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_PAPERMONO_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_PAPERMONO_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_PAPERMONO_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_PAPERMONO_BLE_ERROR", repr(error))

    if state["speaker"] == "pass":
        try:
            Speaker.tone(3500, 15000)
            time.sleep_ms(100)
            if not Speaker.isRunning():
                raise RuntimeError("speaker hold stopped unexpectedly")
            emit("UNIFIED_PAPERMONO_AUDIO_HOLD")
        except Exception as error:
            state["speaker"] = "fail"
            emit("UNIFIED_PAPERMONO_AUDIO_HOLD_ERROR", repr(error))

    draw_progress()
    emit("UNIFIED_PAPERMONO_READY")
    touch_seen = False
    while True:
        M5.update()
        if M5.Touch.getCount() > 0 and not touch_seen:
            touch_seen = True
            state["touch"] = "pass"
            emit(
                "UNIFIED_PAPERMONO_TOUCH",
                M5.Touch.getX(),
                M5.Touch.getY(),
            )
            draw_input_state()
        if BtnA.wasPressed():
            state["key"] += 1
            emit("UNIFIED_PAPERMONO_KEY", state["key"])
            draw_input_state()
        time.sleep_ms(20)


main()
