"""One UIFlow2 guest exercising AtomS3R board, WiFi and BLE."""

import M5
import network
import socket
import time
from M5 import *
from machine import I2C, Pin


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18084
BLE_NAME = "M5-ATOMS3R-UNIFIED"
LP5562_ADDR = 0x30

state = {
    "ble": "init",
    "button": 0,
    "http": "not-run",
    "imu": (0.0, 0.0, 0.0),
    "gyro": (0.0, 0.0, 0.0),
    "lp5562": (0, 0, 0),
    "mag": (0.0, 0.0, 0.0),
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
    display.drawRect(3, 3, 121, 121, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.WHITE)
    display.setTextSize(1)
    display.setCursor(8, 10)
    display.print("AtomS3R unified")
    display.setCursor(8, 26)
    display.print("WiFi:%s BLE:%s" % (state["wifi"], state["ble"]))
    display.setCursor(8, 40)
    display.print("HTTP:%s" % state["http"])
    display.setCursor(8, 54)
    display.print("btn:%d" % state["button"])
    display.setCursor(8, 68)
    display.print("a %.1f %.1f %.1f" % state["imu"])
    display.setCursor(8, 82)
    display.print("m %.1f %.1f %.1f" % state["mag"])
    display.fillRect(8, 99, 111, 20, display.COLOR.BLUE)
    display.setTextColor(display.COLOR.GREEN)
    display.setTextSize(2)
    display.setCursor(27, 101)
    display.print("PRESS")


def probe_lp5562():
    i2c = I2C(1, scl=Pin(0), sda=Pin(45), freq=100000)
    i2c.writeto_mem(LP5562_ADDR, 0x00, b"\xC0")
    i2c.writeto_mem(LP5562_ADDR, 0x01, b"\x01")
    i2c.writeto_mem(LP5562_ADDR, 0x04, b"\x80")
    i2c.writeto_mem(LP5562_ADDR, 0x03, b"\x40")
    i2c.writeto_mem(LP5562_ADDR, 0x02, b"\x20")
    rgb = (
        i2c.readfrom_mem(LP5562_ADDR, 0x04, 1)[0],
        i2c.readfrom_mem(LP5562_ADDR, 0x03, 1)[0],
        i2c.readfrom_mem(LP5562_ADDR, 0x02, 1)[0],
    )
    if rgb != (0x80, 0x40, 0x20):
        raise RuntimeError("LP5562 PWM readback mismatch")
    return rgb


def probe_http():
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n")
        response = bytearray()
        while b"UNIFIED_ATOMS3R_OK" not in response and len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        emit("UNIFIED_ATOMS3R_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_ATOMS3R_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        return "pass"
    finally:
        sock.close()


def main():
    global log_uart

    from hardware import UART

    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    emit("UNIFIED_ATOMS3R_MAIN")
    M5.begin()
    M5.Display.setRotation(0)
    M5.Display.setBrightness(255)
    emit("UNIFIED_ATOMS3R_BOARD", M5.getBoard())
    emit(
        "UNIFIED_ATOMS3R_DISPLAY",
        M5.Display.width(),
        M5.Display.height(),
    )

    try:
        state["imu"] = Imu.getAccel()
        state["gyro"] = Imu.getGyro()
        state["mag"] = Imu.getMag()
        emit("UNIFIED_ATOMS3R_IMU", *state["imu"])
        emit("UNIFIED_ATOMS3R_GYRO", *state["gyro"])
        emit("UNIFIED_ATOMS3R_MAG", *state["mag"])
    except Exception as error:
        emit("UNIFIED_ATOMS3R_IMU_ERROR", repr(error))

    try:
        state["lp5562"] = probe_lp5562()
        emit("UNIFIED_ATOMS3R_LP5562", *state["lp5562"])
    except Exception as error:
        emit("UNIFIED_ATOMS3R_LP5562_ERROR", repr(error))

    draw()

    try:
        station = network.WLAN(network.STA_IF)
        station.active(True)
        networks = station.scan()
        emit("UNIFIED_ATOMS3R_WIFI_SCAN", len(networks))
        emit("UNIFIED_ATOMS3R_WIFI_SCAN_RESULTS", repr(networks))
        error = station.connect(SSID)
        emit("UNIFIED_ATOMS3R_WIFI_CONNECT_RETURNED", error)
        deadline = time.ticks_add(time.ticks_ms(), 20000)
        while (
            not station.isconnected()
            and time.ticks_diff(deadline, time.ticks_ms()) > 0
        ):
            time.sleep_ms(250)
        if not station.isconnected():
            raise RuntimeError("WiFi association timed out")
        address = station.ifconfig()[0]
        emit("UNIFIED_ATOMS3R_WIFI_CONNECTED", address)
        state["wifi"] = "pass"
    except Exception as error:
        state["wifi"] = "fail"
        emit("UNIFIED_ATOMS3R_WIFI_ERROR", repr(error))

    draw()
    if state["wifi"] == "pass":
        try:
            state["http"] = probe_http()
            emit("UNIFIED_ATOMS3R_HTTP_PASS")
        except Exception as error:
            state["http"] = "fail"
            emit("UNIFIED_ATOMS3R_HTTP_ERROR", repr(error))

    try:
        from bleuart import BLEUARTServer

        server = BLEUARTServer(name=BLE_NAME, verbose=True)

        def on_receive():
            payload = bytes(server.read())
            emit("UNIFIED_ATOMS3R_BLE_RX", payload)
            server.write(b"ACK:" + payload)
            emit("UNIFIED_ATOMS3R_BLE_ACK_SENT")

        server.irq(on_receive)
        state["ble"] = "pass"
        emit("UNIFIED_ATOMS3R_BLE_READY")
    except Exception as error:
        state["ble"] = "fail"
        emit("UNIFIED_ATOMS3R_BLE_ERROR", repr(error))

    draw()
    emit("UNIFIED_ATOMS3R_READY")
    was_pressed = False
    while True:
        M5.update()
        pressed = BtnA.isPressed()
        if pressed and not was_pressed:
            state["button"] += 1
            emit("UNIFIED_ATOMS3R_BUTTON", state["button"])
            draw()
        was_pressed = pressed
        time.sleep_ms(20)


main()
