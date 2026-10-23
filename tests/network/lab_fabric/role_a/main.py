"""Guest A: connect over the isolated L2 fabric and call guest B."""

import network
import socket
import time


SSID = "myssid"
PEER = ("10.230.0.3", 19123)
HELLO = b"LAB_FABRIC_A_HELLO"
EXPECTED = b"LAB_FABRIC_B_ACK"


def emit(*parts):
    print("LAB_FABRIC_A", *parts)


station = network.WLAN(network.STA_IF)
station.active(True)
station.connect(SSID)
deadline = time.ticks_add(time.ticks_ms(), 30000)
while (
    not station.isconnected()
    and time.ticks_diff(deadline, time.ticks_ms()) > 0
):
    time.sleep_ms(100)
if not station.isconnected():
    raise RuntimeError("guest A WiFi association timed out")
emit("DHCP", station.ifconfig()[0])

deadline = time.ticks_add(time.ticks_ms(), 60000)
last_error = None
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    client = socket.socket()
    client.settimeout(3)
    try:
        client.connect(PEER)
        client.send(HELLO)
        response = client.recv(128)
        if not response.startswith(EXPECTED):
            raise RuntimeError("invalid guest B response: %r" % response)
        emit("RX", response)
        emit("PASS")
        break
    except Exception as error:
        last_error = error
        time.sleep_ms(500)
    finally:
        client.close()
else:
    raise RuntimeError("guest A could not reach guest B: %r" % last_error)

while True:
    time.sleep_ms(1000)
