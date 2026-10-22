import bluetooth
import time


print("CORE2_BLE_MAIN_START")
radio = bluetooth.BLE()
print("CORE2_BLE_OBJECT_READY")
radio.active(True)
print("CORE2_BLE_ACTIVE", radio.active())
radio.config(gap_name="M5-CORE2-PROBE")
print("CORE2_BLE_CONFIG")

print("CORE2_BLE_ADVERTISE_BEGIN")
try:
    radio.gap_advertise(100_000, adv_data=b"\x02\x01\x06")
    print("CORE2_BLE_ADVERTISE_OK")
    time.sleep_ms(1000)
    print("CORE2_BLE_RESULT: PASSED")
except Exception as error:
    print("CORE2_BLE_ADVERTISE_ERROR", repr(error))
    print("CORE2_BLE_RESULT: FAILED")
