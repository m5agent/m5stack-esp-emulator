"""Probe stock UIFlow2 C6 WiFi initialization on the current QEMU machine."""

import M5
import network
import socket
import time


print("C6_QEMU_WIFI_MAIN")
M5.begin()
print("C6_QEMU_WIFI_BOARD", M5.getBoard())

sta = network.WLAN(network.STA_IF)
print("C6_QEMU_WIFI_OBJECT")
try:
    sta.active(True)
    print("C6_QEMU_WIFI_ACTIVE", int(sta.active()))
    time.sleep_ms(500)
except Exception as exc:
    print("C6_QEMU_WIFI_ACTIVE_ERROR", repr(exc))

try:
    result = sta.scan()
    print("C6_QEMU_WIFI_SCAN", repr(result))
except Exception as exc:
    print("C6_QEMU_WIFI_SCAN_ERROR", repr(exc))

time.sleep_ms(500)
try:
    print("C6_QEMU_WIFI_CONNECT_START")
    try:
        print("C6_QEMU_WIFI_STATUS_BEFORE", sta.status())
    except Exception as exc:
        print("C6_QEMU_WIFI_STATUS_BEFORE_ERROR", repr(exc))
    sta.connect("myssid", "", bssid=b"\x10\x01\x00\xc4\x0aP")
    deadline = time.ticks_add(time.ticks_ms(), 15000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        if sta.isconnected():
            break
        try:
            print("C6_QEMU_WIFI_STATUS", sta.status())
        except Exception:
            pass
        time.sleep_ms(100)
    print("C6_QEMU_WIFI_CONNECTED", int(sta.isconnected()))
    if sta.isconnected():
        print("C6_QEMU_WIFI_IFCONFIG", repr(sta.ifconfig()))
        try:
            addresses = socket.getaddrinfo("example.com", 80)
            print("C6_QEMU_WIFI_DNS", repr(addresses))
            address = next(
                info[-1] for info in addresses
                if len(info[-1][0].split(".")) == 4
            )
            print("C6_QEMU_WIFI_DNS_IPV4", repr(address))
        except Exception as exc:
            print("C6_QEMU_WIFI_DNS_ERROR", repr(exc))
        else:
            try:
                connection = socket.socket()
                connection.settimeout(5)
                connection.connect(address)
                connection.send(
                    b"GET / HTTP/1.0\r\n"
                    b"Host: example.com\r\n"
                    b"Connection: close\r\n\r\n"
                )
                response = connection.recv(256)
                connection.close()
                print("C6_QEMU_WIFI_HTTP", repr(response))
                print(
                    "C6_QEMU_WIFI_PUBLIC",
                    int(response.startswith(b"HTTP/")),
                )
            except Exception as exc:
                print("C6_QEMU_WIFI_HTTP_ERROR", repr(exc))
except Exception as exc:
    print("C6_QEMU_WIFI_CONNECT_ERROR", repr(exc))

print("C6_QEMU_WIFI_DONE")
while True:
    M5.update()
    time.sleep_ms(100)
