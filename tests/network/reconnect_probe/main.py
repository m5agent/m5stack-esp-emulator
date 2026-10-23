import network
import socket
import time


SSID = "myssid"
HTTP_HOST = "10.0.2.2"
HTTP_PORT = 18080


def emit(*values):
    print("RECONNECT", *values)


def wait_for_dhcp(label):
    for attempt in range(120):
        status = station.status()
        connected = station.isconnected()
        address = station.ifconfig()[0]
        if attempt % 8 == 0:
            emit("WAIT", label, attempt, status, connected, address)
        if connected and status == 1010 and address.startswith("10.0.2."):
            emit("DHCP", label, address)
            return address
        time.sleep_ms(250)
    return ""


def controlled_http(path):
    sock = socket.socket()
    sock.settimeout(10)
    try:
        sock.connect((HTTP_HOST, HTTP_PORT))
        sock.send(
            (
                "GET %s HTTP/1.0\r\n"
                "Host: qemu.test\r\n"
                "\r\n"
            ) % path
        )
        response = sock.recv(512)
        if not response.startswith(b"HTTP/"):
            raise RuntimeError("invalid HTTP response")
        emit("HTTP", path, response.split(b"\r\n", 1)[0])
    finally:
        sock.close()


try:
    emit("MAIN_START")
    station = network.WLAN(network.STA_IF)
    station.active(True)
    emit("SCAN", len(station.scan()))
    emit("CONNECT_BEGIN", 1)
    station.connect(SSID)
    if not wait_for_dhcp(1):
        raise RuntimeError("first DHCP lease timed out")
    emit("CONNECTED", 1)
    controlled_http("/before")
    emit("BEFORE_HTTP_PASS")

    station.disconnect()
    emit("DISCONNECTED")
    time.sleep(1)
    emit("RADIO_DOWN_SCAN", len(station.scan()))
    time.sleep(5)
    emit("AIR_GAP_DONE")
    emit("RADIO_RESTORED_SCAN", len(station.scan()))

    emit("CONNECT_BEGIN", 2)
    station.connect(SSID)
    if not wait_for_dhcp(2):
        raise RuntimeError("reconnect DHCP lease timed out")
    emit("CONNECTED", 2)
    controlled_http("/after")
    emit("AFTER_HTTP_PASS")
    emit("RESULT: PASSED")
except Exception as error:
    emit("ERROR", repr(error))
    emit("RESULT: FAILED")

while True:
    time.sleep(1)
