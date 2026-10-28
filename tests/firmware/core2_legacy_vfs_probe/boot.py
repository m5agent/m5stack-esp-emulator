print("CORE2_LEGACY_ORIGINAL_BOOT_START")
from hardware import sdcard
try:
    sdcard.SDCard(20000000)
except:
    pass
print("CORE2_LEGACY_ORIGINAL_BOOT_DONE")
