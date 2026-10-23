"""NanoC6 board peripherals and UART1 HCI BLE in one C6 guest."""

import M5
import machine
import network
import socket
import time
from hardware import IR, RGB


WIFI_SSID = "myssid"
WIFI_BSSID = b"\x10\x01\x00\xc4\x0a\x50"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18090


def connect_wifi():
    station = network.WLAN(network.STA_IF)
    station.active(True)
    time.sleep_ms(500)
    access_points = station.scan()
    print("NANOC6_HCI_WIFI_SCAN", repr(access_points))
    station.connect(WIFI_SSID, "", bssid=WIFI_BSSID)
    deadline = time.ticks_add(time.ticks_ms(), 20000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        if station.isconnected():
            address = station.ifconfig()[0]
            print("NANOC6_HCI_WIFI_CONNECTED", address)
            return station
        time.sleep_ms(100)
    raise RuntimeError("WiFi connection timed out")


def probe_http():
    connection = socket.socket()
    connection.settimeout(10)
    try:
        connection.connect((HTTP_HOST, HTTP_PORT))
        connection.send(
            b"GET /unified HTTP/1.0\r\nHost: qemu.test\r\n\r\n"
        )
        response = bytearray()
        while b"UNIFIED_NANOC6_OK" not in response and len(response) < 2048:
            chunk = connection.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        response = bytes(response)
        print("NANOC6_HCI_HTTP", repr(response))
        if (
            not response.startswith(b"HTTP/")
            or b"200 OK" not in response
            or b"UNIFIED_NANOC6_OK" not in response
        ):
            raise RuntimeError("controlled HTTP response is invalid")
        print("NANOC6_HCI_HTTP_PASS")
    finally:
        connection.close()


print("NANOC6_HCI_MAIN")
M5.begin()
print("NANOC6_HCI_BOARD", M5.getBoard())

rgb_power = machine.Pin(19, machine.Pin.OUT)
rgb_power.value(1)
rgb = RGB()
rgb.set_brightness(100)
rgb.set_color(0, 0x00FF00)
print("NANOC6_HCI_RGB 1 00FF00")

blue = machine.Pin(7, machine.Pin.OUT)
blue.value(1)
print("NANOC6_HCI_BLUE 1")

ir = IR()
ir.tx(0x56, 0xA3)
print("NANOC6_HCI_IR 0x56 0xA3")

button = machine.Pin(9, machine.Pin.IN, machine.Pin.PULL_UP)
print("NANOC6_HCI_BUTTON_READY")

connect_wifi()
probe_http()

from bleuart import BLEUARTServer

server = BLEUARTServer(name="M5-NANOC6-HCI", verbose=True)


def on_receive():
    payload = bytes(server.read())
    print("NANOC6_HCI_BLE_RX", payload)
    server.write(b"ACK:" + payload)
    print("NANOC6_HCI_BLE_ACK_SENT")


server.irq(on_receive)
print("NANOC6_HCI_BLE_READY")
print("NANOC6_HCI_READY")

button_seen = False
while True:
    M5.update()
    value = button.value()
    if not button_seen and value == 0:
        button_seen = True
        print("NANOC6_HCI_BUTTON_PRESS")
    elif button_seen and value == 1:
        button_seen = False
        blue.value(0)
        print("NANOC6_HCI_BUTTON_RELEASE")
        print("NANOC6_HCI_BLUE 0")
    time.sleep_ms(20)
