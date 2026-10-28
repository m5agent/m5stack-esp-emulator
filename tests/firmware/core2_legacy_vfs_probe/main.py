print("CORE2_LEGACY_ORIGINAL_MAIN_START")
from m5stack import *
print("CORE2_LEGACY_ORIGINAL_MAIN_IMPORT_DONE")
import time

time.sleep(0.1)
lcd.clear()
lcd.fill(0xffffff)
lcd.font(lcd.FONT_DejaVu18)
lcd.setTextColor(lcd.GREEN)
lcd.text(0, 60, "This is the default program. For online programming on UIFlow, click the reset button and hold the middle button during startup until it enters the online programming mode.")
print("CORE2_LEGACY_ORIGINAL_MAIN_DRAW_DONE")
