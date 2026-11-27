import time
import M5

M5.begin()
print("VOICES3R_BROWSER_MIC_READY")
while not M5.BtnA.isPressed():
    M5.update()
    time.sleep_ms(10)

microphone = M5.Mic
data = bytearray(3200)
if not microphone.begin() or not microphone.record(data, 16000, False):
    raise RuntimeError("VoiceS3R microphone start failed")
deadline = time.ticks_add(time.ticks_ms(), 2000)
while microphone.isRecording() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
    time.sleep_ms(10)
microphone.end()
print("VOICES3R_BROWSER_MIC_SAMPLES", sum(value != 0 for value in data), max(data) - min(data))
