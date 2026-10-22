import network


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
    if results:
        print("CORE2_WIFI_RESULT: PASSED")
    else:
        print("CORE2_WIFI_RESULT: FAILED")
except Exception as error:
    print("CORE2_WIFI_SCAN_ERROR", repr(error))
    print("CORE2_WIFI_RESULT: FAILED")
