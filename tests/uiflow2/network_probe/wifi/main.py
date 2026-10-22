import network
import time


print("UIFLOW_WIFI_START")
station = network.WLAN(network.STA_IF)
print("UIFLOW_WIFI_OBJECT_READY")
station.active(True)
print("UIFLOW_WIFI_ACTIVE", station.active())

try:
    scan = station.scan()
except Exception as error:
    print("UIFLOW_WIFI_SCAN_ERROR", repr(error))
    print("UIFLOW_WIFI_RESULT: FAILED")
else:
    print("UIFLOW_WIFI_SCAN", len(scan))
    if len(scan) < 1:
        print("UIFLOW_WIFI_RESULT: FAILED")
    else:
        print("UIFLOW_WIFI_CONNECT_BEGIN")
        error = station.connect("myssid", "mypassword")
        print("UIFLOW_WIFI_CONNECT_RETURNED", error)
        for attempt in range(80):
            status = station.status()
            connected = station.isconnected()
            address = station.ifconfig()[0]
            print("UIFLOW_WIFI_STATUS", attempt, status, connected, address)
            if connected and status == 1010 and address.startswith("192.168.4."):
                print("UIFLOW_WIFI_CONNECTED")
                print("UIFLOW_WIFI_DHCP", address)
                print("UIFLOW_WIFI_RESULT: PASSED")
                break
            time.sleep_ms(250)
        else:
            print("UIFLOW_WIFI_RESULT: FAILED")
