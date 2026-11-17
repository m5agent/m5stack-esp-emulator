"""Guest probe for replacing a microphone fixture during one Cardputer session."""

import binascii
import math
import struct
import time

import M5


M5.begin()


def wait_for_fixture(phase):
    print("AUDIO_API_WAIT", phase)
    time.sleep_ms(5000)
    print("AUDIO_API_RECORD_START", phase)


def record(phase):
    mic = M5.Mic
    assert mic.begin(), "microphone begin"
    frames = bytearray(6400)
    assert mic.record(frames, 16000, False), "microphone record"
    deadline = time.ticks_add(time.ticks_ms(), 5000)
    while mic.isRecording() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(10)
    assert not mic.isRecording(), "microphone recording completion"
    mic.end()
    for offset in range(0, len(frames), 400):
        print("AUDIO_API_MIC", phase, offset, binascii.hexlify(frames[offset:offset + 400]).decode())


M5.Speaker.end()
wait_for_fixture("tone")
record("tone")
wait_for_fixture("silence")
record("silence")

speaker = M5.Speaker
assert speaker.begin(), "speaker begin"
config = speaker.config()
print("AUDIO_API_SPEAKER_CONFIG", config.sample_rate, config.stereo, config.i2s_port)
speaker.setVolume(96)
signal = bytearray(12800)
for index in range(len(signal) // 2):
    sample = int(8000 * math.sin(2 * math.pi * 660 * index / 8000))
    struct.pack_into("<h", signal, index * 2, sample)
assert speaker.playRaw(signal, 8000, False, 1, 0, True), "speaker playRaw"
deadline = time.ticks_add(time.ticks_ms(), 14000)
while speaker.isPlaying() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
    time.sleep_ms(10)
assert not speaker.isPlaying(), "speaker completion"
time.sleep_ms(500)
speaker.stop()
speaker.end()
print("AUDIO_API_DONE")
