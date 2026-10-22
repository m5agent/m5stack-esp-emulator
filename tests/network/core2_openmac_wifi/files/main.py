import network
import socket
import time


HTTP_PORT = __HTTP_PORT__

print("CORE2_WIFI_MAIN_START")
station = network.WLAN(network.STA_IF)
print("CORE2_WIFI_OBJECT_READY")
station.active(True)
print("CORE2_WIFI_ACTIVE", station.active())

print("CORE2_WIFI_SCAN_BEGIN")
try:
    results = station.scan()
    print("CORE2_WIFI_SCAN_OK", len(results))
    print("CORE2_WIFI_SCAN_RESULTS", repr(results))
except Exception as error:
    print("CORE2_WIFI_SCAN_ERROR", repr(error))
    print("CORE2_WIFI_RESULT: FAILED")
else:
    print("CORE2_WIFI_CONNECT_BEGIN")
    try:
        errno = station.connect("myssid")
        print("CORE2_WIFI_CONNECT_RETURNED", errno)
    except Exception as error:
        print("CORE2_WIFI_CONNECT_ERROR", repr(error))
        print("CORE2_WIFI_RESULT: FAILED")
    else:
        for attempt in range(30):
            status = station.status()
            connected = station.isconnected()
            ifconfig = station.ifconfig()
            print(
                "CORE2_WIFI_STATUS",
                attempt,
                status,
                connected,
                ifconfig,
            )
            if connected and ifconfig[0] != "0.0.0.0":
                print("CORE2_WIFI_CONNECTED True")
                print("CORE2_WIFI_IP", ifconfig[0])
                try:
                    client = socket.socket()
                    client.settimeout(5)
                    client.connect(("10.0.2.2", HTTP_PORT))
                    client.send(
                        b"GET / HTTP/1.0\r\nHost: core2-test\r\n\r\n"
                    )
                    response = client.recv(128)
                    client.close()
                    print("CORE2_HTTP_RX", response[:32])
                    if b"200 OK" in response:
                        print("CORE2_HTTP_OK")
                        print("CORE2_WIFI_RESULT: PASSED")
                    else:
                        print("CORE2_WIFI_RESULT: FAILED")
                except Exception as error:
                    print("CORE2_HTTP_ERROR", repr(error))
                    print("CORE2_WIFI_RESULT: FAILED")
                break
            time.sleep_ms(500)
        else:
            print("CORE2_WIFI_RESULT: FAILED")
