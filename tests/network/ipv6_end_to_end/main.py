"""One UIFlow2 guest exercising IPv6 DNS, TCP and denied destinations."""

import M5
import network
import socket
import time
from M5 import *


SSID = "myssid"
HOST = "allowed.lab.test"
ALLOWED_IP = "fec0::2"
HTTP_PORT = __HTTP_PORT__
DENIED_PORT = __DENIED_PORT__
CHECK_DNS = __CHECK_DNS__
CHECK_DENIED = __CHECK_DENIED__
log_uart = None


def emit(*parts):
    line = " ".join(str(part) for part in parts)
    if log_uart:
        log_uart.write(line + "\n")
    else:
        print(line)


def ipv6_info(host, family):
    infos = socket.getaddrinfo(
        host,
        HTTP_PORT,
        family,
        socket.SOCK_STREAM,
    )
    for info in infos:
        if len(info) < 5 or not isinstance(info[-1], (tuple, list)):
            continue
        if not info[-1]:
            continue
        address = str(info[-1][0])
        if ":" in address and not address.lower().startswith("::ffff:"):
            return info
    raise RuntimeError("AAAA resolution returned no IPv6 address")


def request(info, path):
    client = socket.socket(info[0], info[1], info[2])
    client.settimeout(10)
    try:
        client.connect((info[-1][0], info[-1][1]))
        client.send(
            (
                "GET %s HTTP/1.0\r\n"
                "Host: %s\r\n"
                "Connection: close\r\n\r\n"
            )
            % (path, HOST)
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


def expect_blocked(info, label):
    client = socket.socket(info[0], info[1], info[2])
    client.settimeout(2)
    try:
        client.connect((info[-1][0], info[-1][1]))
    except OSError:
        emit(label, "BLOCKED")
        return
    else:
        raise RuntimeError("%s unexpectedly connected" % label)
    finally:
        client.close()


def main():
    global log_uart

    try:
        from hardware import UART

        log_uart = UART(0, baudrate=115200, tx=43, rx=44)
    except Exception:
        log_uart = None
    emit("IPV6_E2E_MAIN")
    M5.begin()

    station = network.WLAN(network.STA_IF)
    station.active(True)
    networks = station.scan()
    emit("IPV6_WIFI_SCAN", len(networks), repr(networks))
    error = station.connect(SSID)
    emit("IPV6_WIFI_CONNECT_RETURNED", repr(error))
    deadline = time.ticks_add(time.ticks_ms(), 20000)
    while (
        not station.isconnected()
        and time.ticks_diff(deadline, time.ticks_ms()) > 0
    ):
        time.sleep_ms(250)
    if not station.isconnected():
        raise RuntimeError("WiFi association timed out")
    emit("IPV6_WIFI_READY", station.ifconfig())

    family = getattr(socket, "AF_INET6", None)
    if family is None:
        raise RuntimeError("MicroPython socket lacks AF_INET6")
    emit("IPV6_SOCKET_FAMILY PASS")
    time.sleep(4)

    if CHECK_DNS:
        info = ipv6_info(HOST, family)
        if str(info[-1][0]).lower() != ALLOWED_IP.lower():
            raise RuntimeError("AAAA returned %s" % (info[-1][0],))
        emit("IPV6_DNS_AAAA PASS", info[-1][0])
    else:
        info = (
            family,
            socket.SOCK_STREAM,
            0,
            "",
            (ALLOWED_IP, HTTP_PORT, 0, 0),
        )

    response = request(info, "/ipv6")
    emit("IPV6_HTTP", repr(response[:128]))
    if (
        not response.startswith(b"HTTP/")
        or b"200 OK" not in response
        or b"IPV6_E2E_OK" not in response
    ):
        raise RuntimeError("IPv6 HTTP response is invalid")
    emit("IPV6_HTTP PASS")

    if CHECK_DENIED:
        expect_blocked(
            (
                family,
                socket.SOCK_STREAM,
                0,
                "",
                (ALLOWED_IP, DENIED_PORT, 0, 0),
            ),
            "IPV6_DENIED_PORT",
        )
    emit("IPV6_E2E_RESULT PASS")

    while True:
        time.sleep(1)


try:
    main()
except Exception as error:
    emit("IPV6_E2E_ERROR", repr(error))
    raise
