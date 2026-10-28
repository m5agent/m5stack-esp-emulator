print("CORE2_LEGACY_ORIGINAL_BOOT_START")
from hardware import sdcard
try:
    sdcard.SDCard(20000000)
except:
    pass
print("CORE2_LEGACY_ORIGINAL_BOOT_DONE")

from m5stack import *
import time

lcd.clear()
lcd.fill(0x102030)
lcd.font(lcd.FONT_DejaVu18)
lcd.setTextColor(lcd.WHITE)
lcd.text(12, 12, "CORE2 LEGACY")
lcd.text(12, 42, "PANEL ROUTING")
lcd.rect(8, 76, 304, 40, lcd.GREEN)
time.sleep_ms(500)
print("CORE2_LEGACY_DISPLAY_PROBE_DONE")

while True:
    time.sleep_ms(200)
