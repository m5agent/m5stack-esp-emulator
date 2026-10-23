import M5
import binascii
import network
import socket
import ssl
import time


SSID = "myssid"
TLS_IP = "10.0.2.2"
TLS_PORT = __TLS_PORT__
SERVER_NAME = "allowed.lab.test"
CA_PEM_B64 = "__CA_PEM_B64__"
log_uart = None


def emit(*parts):
    line = " ".join(str(part) for part in parts)
    if log_uart:
        log_uart.write(line + "\n")
    else:
        print(line)


def tls_request(context, host, path):
    emit("TLS_CONNECT_BEGIN", host, TLS_IP, TLS_PORT)
    raw = socket.socket()
    raw.settimeout(15)
    sock = None
    try:
        raw.connect((TLS_IP, TLS_PORT))
        emit("TLS_TCP_CONNECTED", host)
        sock = context.wrap_socket(
            raw,
            server_hostname=SERVER_NAME,
        )
        emit("TLS_HANDSHAKE_DONE", host)
        sock.write(
            (
                "GET %s HTTP/1.0\r\n"
                "Host: %s\r\n"
                "Connection: close\r\n\r\n"
            )
            % (path, host)
        )
        response = b""
        while len(response) < 2048:
            chunk = sock.recv(512)
            if not chunk:
                break
            response += chunk
        first_line = response.split(b"\r\n", 1)[0]
        status = int(first_line.split(b" ")[1])
        emit("TLS_RESPONSE", host, path, status, repr(first_line))
        return status
    finally:
        if sock is not None:
            sock.close()
        else:
            raw.close()


try:
    from hardware import UART

    log_uart = UART(0, baudrate=115200, tx=43, rx=44)
except Exception:
    log_uart = None
emit("TLS_ALLOWLIST_MAIN")
M5.begin()

station = network.WLAN(network.STA_IF)
station.active(True)
networks = station.scan()
emit("TLS_WIFI_SCAN", len(networks))
station.connect(SSID)
deadline = time.ticks_add(time.ticks_ms(), 20000)
while (
    not station.isconnected()
    and time.ticks_diff(deadline, time.ticks_ms()) > 0
):
    time.sleep_ms(250)
if not station.isconnected():
    raise RuntimeError("TLS allowlist WiFi association timed out")
emit("TLS_WIFI_READY", station.ifconfig()[0])

try:
    emit("TLS_CA_PAYLOAD_DECODE_BEGIN")
    ca_pem = binascii.a2b_base64(CA_PEM_B64)
    emit("TLS_CA_PAYLOAD_DECODE_DONE", len(ca_pem))
    with open("/flash/ca.pem", "wb") as ca_file:
        ca_file.write(ca_pem)
    emit("TLS_CA_FILE_WRITTEN", len(ca_pem))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    emit("TLS_CONTEXT_READY")
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile="/flash/ca.pem")
    emit("TLS_CA_LOADED")

    allowed_status = tls_request(
        context,
        "allowed.lab.test",
        "/allowed",
    )
    if allowed_status != 200:
        raise RuntimeError("allowed host did not return 200")
    emit("TLS_ALLOWED PASS")

    denied_status = tls_request(
        context,
        "denied.lab.test",
        "/denied",
    )
    if denied_status != 403:
        raise RuntimeError("denied host did not return 403")
    emit("TLS_DENIED PASS")
    emit("TLS_ALLOWLIST_RESULT PASS")
except Exception as error:
    emit("TLS_ALLOWLIST_ERROR", repr(error))
    raise

while True:
    time.sleep(1)
