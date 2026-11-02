import M5
import time
from M5 import *

print("VOICES3R_MAIN_START")
M5.begin()
print("VOICES3R_M5_BEGIN_OK")
print("VOICES3R_BOARD", M5.getBoard())
display = M5.Display
if display is not None:
    display.fillScreen(0x000000)
    display.setTextColor(0xFFFFFF, 0x000000)
    display.setCursor(4, 8)
    display.print("VoiceS3R audio probe")
status = "init"
try:
    if not Speaker.begin():
        raise RuntimeError("speaker begin failed")
    Speaker.setVolumePercentage(0.8)
    Speaker.tone(440, 900)
    time.sleep_ms(1200)
    running = bool(Speaker.isRunning())
    print("VOICES3R_SPEAKER_RUNNING", int(running))
    status = "ok" if running else "stopped"
except Exception as exc:
    print("VOICES3R_SPEAKER_ERROR", repr(exc))
    status = "error"
print("VOICES3R_STATUS", status)
if display is not None:
    display.setCursor(4, 28)
    display.print("status=%s" % status)
# Keep the guest alive long enough for the I2S DMA window to be observable.
time.sleep_ms(1500)
print("VOICES3R_AUDIO_WINDOW_DONE")
while True:
    M5.update()
    time.sleep_ms(100)
