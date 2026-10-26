import network
import time


print("CORE2_WIFI_MAIN_START")
station = network.WLAN(network.STA_IF)
print("CORE2_WIFI_OBJECT_READY")
station.active(True)
print("CORE2_WIFI_ACTIVE", station.active())

print("CORE2_WIFI_SCAN_BEGIN")
try:
    results = station.scan()
    print("CORE2_WIFI_SCAN_OK", len(results))
except Exception as error:
    print("CORE2_WIFI_SCAN_ERROR", repr(error))

print("CORE2_WIFI_CONNECT_BEGIN")
errno = station.connect("myssid", "mypassword")
print("CORE2_WIFI_CONNECT_RETURNED", errno)

for attempt in range(20):
    status = station.status()
    print(
        "CORE2_WIFI_STATUS",
        attempt,
        status,
        station.isconnected(),
        station.ifconfig(),
    )
    if station.isconnected():
        print("CORE2_WIFI_RESULT: PASSED")
        break
    time.sleep_ms(500)
else:
    print("CORE2_WIFI_RESULT: FAILED")
