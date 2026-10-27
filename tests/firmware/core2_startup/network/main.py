import M5
import network
import socket
import sys
import time

try:
    print("CORE2_STARTUP:network:BEGIN")
    M5.begin()
    M5.Lcd.fillScreen(0x0E1114)
    print("CORE2_STARTUP:network:BACKGROUND_READY")
    started = time.ticks_ms()
    wlan = network.WLAN(network.STA_IF)
    print("CORE2_STARTUP:network:OBJECT_READY")
    wlan.active(True)
    print("CORE2_STARTUP:network:ACTIVE", wlan.active(),
          "elapsed_ms", time.ticks_diff(time.ticks_ms(), started))
    print("CORE2_STARTUP:network:CONNECTED", wlan.isconnected())
    # TEST-NET-1 is an intentionally unavailable NTP destination. Use an
    # explicit IP and socket deadline so DNS or an external service is not
    # needed to verify the offline/error path.
    request = bytearray(48)
    request[0] = 0x1B
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(1)
    started = time.ticks_ms()
    try:
        client.sendto(request, ("192.0.2.1", 123))
        client.recvfrom(48)
        raise RuntimeError("unexpected TEST-NET NTP response")
    except OSError as error:
        print("CORE2_STARTUP:network:NTP_ERROR", repr(error),
              "elapsed_ms", time.ticks_diff(time.ticks_ms(), started))
    finally:
        client.close()
    M5.Lcd.setTextColor(0xFFFFFF, 0x0E1114)
    M5.Lcd.drawString("loading...", 12, 20)
    print("CORE2_STARTUP:network:READY")
    for step in range(100):
        M5.update()
        time.sleep_ms(20)
    print("CORE2_STARTUP:network:DONE")
except Exception as error:
    print("CORE2_STARTUP:network:ERROR")
    sys.print_exception(error)
    raise
