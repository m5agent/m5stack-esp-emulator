from m5stack import *
import time


print("CORE2_LEGACY_VFS_MAIN")
lcd.clear()
lcd.fill(0x102030)
lcd.font(lcd.FONT_DejaVu18)
lcd.setTextColor(lcd.WHITE)
lcd.text(12, 12, "CORE2 LEGACY")
lcd.text(12, 42, "VFS PROBE")
lcd.rect(8, 76, 304, 40, lcd.GREEN)
print("CORE2_LEGACY_VFS_DRAW_DONE")

while True:
    time.sleep_ms(200)
