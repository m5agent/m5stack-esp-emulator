import time
import M5

M5.begin()
print("CORE2_BROWSER_MIC_READY")
while not M5.Touch.getCount():
    M5.update()
    time.sleep_ms(10)

microphone = M5.Mic
data = bytearray(3200)
if not microphone.begin() or not microphone.record(data, 16000, False):
    raise RuntimeError("Core2 microphone start failed")
while microphone.isRecording():
    time.sleep_ms(10)
microphone.end()
print("CORE2_BROWSER_MIC_SAMPLES", sum(value != 0 for value in data), max(data) - min(data))
