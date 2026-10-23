"""Guest B: serve guest A over the isolated L2 fabric."""

import network
import socket
import time


SSID = "myssid"
PORT = 19123
EXPECTED = b"LAB_FABRIC_A_HELLO"
REPLY = b"LAB_FABRIC_B_ACK:"


def emit(*parts):
    print("LAB_FABRIC_B", *parts)


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
    raise RuntimeError("guest B WiFi association timed out")
emit("DHCP", station.ifconfig()[0])

server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("0.0.0.0", PORT))
server.listen(1)
emit("READY", PORT)

client, peer = server.accept()
try:
    client.settimeout(10)
    emit("ACCEPT", peer)
    payload = client.recv(128)
    emit("RX", payload)
    if payload != EXPECTED:
        raise RuntimeError("invalid guest A payload: %r" % payload)
    client.send(REPLY + payload)
    emit("PASS")
finally:
    client.close()
    server.close()

while True:
    time.sleep_ms(1000)
