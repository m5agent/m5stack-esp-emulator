import M5
import sys
import time

try:
    print("CORE2_STARTUP:display:BEGIN")
    M5.begin()
    print("CORE2_STARTUP:display:M5_READY")
    M5.Lcd.fillScreen(0x101418)
    M5.Lcd.setTextColor(0xFFFFFF, 0x101418)
    M5.Lcd.drawString("Core2 first frame", 12, 20)
    print("CORE2_STARTUP:display:READY")
    for step in range(100):
        M5.update()
        time.sleep_ms(20)
    print("CORE2_STARTUP:display:DONE")
except Exception as error:
    print("CORE2_STARTUP:display:ERROR")
    sys.print_exception(error)
    raise
