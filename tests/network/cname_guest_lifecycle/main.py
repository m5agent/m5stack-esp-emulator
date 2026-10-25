"""Resolve a controlled DNS CNAME chain and use its terminal address."""

import M5
import network
import socket
import time
from M5 import *


SSID = "myssid"
CNAME_HOST = "alias.cname.test"
DENIED_HOST = "denied.cname.test"
EXPECTED_IP = "10.0.2.2"
HTTP_PORT = 18080
DENIED_PORT = 18081
log_uart = None


def emit(*parts):
    line = " ".join(str(part) for part in parts)
    if log_uart:
        log_uart.write(line + "\n")
    else:
        print(line)


def resolve_ipv4(host):
    infos = socket.getaddrinfo(
        host,
        HTTP_PORT,
        socket.AF_INET,
        socket.SOCK_STREAM,
    )
    for info in infos:
        if len(info) < 5 or not isinstance(info[-1], (tuple, list)):
            continue
        if not info[-1]:
            continue
        address = str(info[-1][0])
        if "." in address:
            return info
    raise RuntimeError("CNAME resolution returned no IPv4 address")


def request(info):
    client = socket.socket(info[0], info[1], info[2])
    client.settimeout(10)
    try:
        client.connect((info[-1][0], info[-1][1]))
        client.send(
            (
                "GET /cname HTTP/1.0\r\n"
                "Host: %s\r\n"
                "Connection: close\r\n\r\n"
            )
            % CNAME_HOST
        )
        response = bytearray()
        while len(response) < 2048:
            chunk = client.recv(512)
            if not chunk:
                break
            response.extend(chunk)
        return bytes(response)
    finally:
        client.close()


def main():
    global log_uart

    try:
        from hardware import UART

        log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    except Exception:
        log_uart = None
    emit("CNAME_GUEST_MAIN")
    M5.begin()

    station = network.WLAN(network.STA_IF)
    station.active(True)
    time.sleep(1)
    error = station.connect(SSID)
    emit("CNAME_GUEST_CONNECT_RETURNED", repr(error))
    deadline = time.ticks_add(time.ticks_ms(), 20000)
    while (
        not station.isconnected()
        and time.ticks_diff(deadline, time.ticks_ms()) > 0
    ):
        time.sleep_ms(250)
    if not station.isconnected():
        raise RuntimeError("WiFi association timed out")
    emit("CNAME_GUEST_WIFI_READY", station.ifconfig())

    info = resolve_ipv4(CNAME_HOST)
    if str(info[-1][0]) != EXPECTED_IP:
        raise RuntimeError("CNAME terminal returned %s" % (info[-1][0],))
    emit("CNAME_GUEST_RESOLVED", info[-1][0])

    response = request(info)
    emit("CNAME_GUEST_HTTP_RESPONSE", repr(response[:128]))
    if (
        not response.startswith(b"HTTP/")
        or b"200 OK" not in response
        or b"STICKS3_WIFI_OK" not in response
    ):
        raise RuntimeError("CNAME HTTP response is invalid")
    emit("CNAME_GUEST_HTTP PASS")

    try:
        resolve_ipv4(DENIED_HOST)
    except OSError:
        emit("CNAME_GUEST_DENIED_NAME PASS")
    else:
        raise RuntimeError("denied CNAME host unexpectedly resolved")

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(3)
    try:
        client.connect((EXPECTED_IP, DENIED_PORT))
    except OSError:
        emit("CNAME_GUEST_DENIED_PORT BLOCKED")
    else:
        raise RuntimeError("denied endpoint port unexpectedly connected")
    finally:
        client.close()

    emit("CNAME_GUEST_RESULT PASS")
    while True:
        time.sleep(1)


try:
    main()
except Exception as error:
    emit("CNAME_GUEST_ERROR", repr(error))
    raise
