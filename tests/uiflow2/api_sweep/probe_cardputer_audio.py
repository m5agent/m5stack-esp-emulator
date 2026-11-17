import binascii
import math
import struct
import time
import M5


def settle(ms):
    deadline = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)


M5.begin()
with open('/flash/audio-test.mode') as test_mode:
    mode = test_mode.read().strip()
print('NATIVE_AUDIO_MODE', mode)
try:
    M5.Speaker.end()
    mic = M5.Mic
    assert mic.begin(), 'mic begin'
    data = bytearray(6400)
    assert mic.record(data, 16000, False), 'mic record'
    deadline = time.ticks_add(time.ticks_ms(), 4000)
    while mic.isRecording() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        settle(10)
    assert not mic.isRecording(), 'mic completion'
    mic.end()
    for i in range(0, len(data), 400):
        print('NATIVE_AUDIO_MIC', i, binascii.hexlify(data[i:i + 400]).decode())
except Exception as exc:
    M5.Mic.end()
    print('NATIVE_AUDIO_MIC_ERROR', repr(exc))

try:
    speaker = M5.Speaker
    assert speaker.begin(), 'speaker begin'
    try:
        config = speaker.config()
        print('NATIVE_AUDIO_SPEAKER_CONFIG', getattr(config, 'sample_rate', None),
              getattr(config, 'stereo', None), getattr(config, 'i2s_port', None))
    except Exception:
        pass
    speaker.setVolume(96)
    play = bytearray(12800)
    # The native capture starts at the first nonzero DMA frame. A short pilot
    # makes the following known-silent frames observable.
    active_samples = len(play) // 2 if mode == 'tone' else 800
    for i in range(active_samples):
        struct.pack_into('<h', play, i * 2, int(8000 * math.sin(2 * math.pi * 660 * i / 8000)))
    assert speaker.playRaw(play, 8000, False, 1, 0, True), 'speaker playRaw'
    print('NATIVE_AUDIO_SPEAKER_STARTED', len(play))
    deadline = time.ticks_add(time.ticks_ms(), 12000)
    while speaker.isPlaying() and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        settle(10)
    assert not speaker.isPlaying(), 'speaker queue completion'
    settle(500)
    speaker.stop()
    speaker.end()
    print('NATIVE_AUDIO_SPEAKER_FINISHED')
except Exception as exc:
    print('NATIVE_AUDIO_SPEAKER_ERROR', repr(exc))
print('NATIVE_AUDIO_FINISHED')
