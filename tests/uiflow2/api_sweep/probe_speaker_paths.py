"""Exercise one isolated M5.Speaker data path in a visible guest."""
import json
import math
import struct
import time

import M5


def emit(case, status, **values):
    item = {"case": case, "status": status}
    item.update(values)
    print("SPEAKER_PATH " + json.dumps(item))


def pcm_tone(frequency, sample_rate, seconds):
    data = bytearray()
    for index in range(sample_rate * seconds):
        value = int(8000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        data.extend(struct.pack("<h", value))
    return data


def wav_bytes(pcm, sample_rate):
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16, b"data", len(pcm),
    )
    return header + pcm


def run(case, seconds=1.0):
    M5.begin()
    M5.Mic.end()
    M5.Speaker.end()
    speaker = M5.Speaker
    if not speaker.begin():
        raise RuntimeError("speaker begin failed")
    speaker.setVolume(96)
    pcm = pcm_tone(660, 8000, seconds)
    wav = wav_bytes(pcm, 8000)
    path = "/flash/speaker-path.wav"
    with open(path, "wb") as handle:
        handle.write(wav)

    if case == "raw":
        result = speaker.playRaw(pcm, 8000, False, 1, 0, True)
        emit(case, "STARTED", result=bool(result), bytes=len(pcm),
             seconds=seconds)
    elif case == "wav":
        result = speaker.playWav(wav)
        emit(case, "STARTED", result=bool(result), bytes=len(wav),
             seconds=seconds)
    elif case == "file":
        result = speaker.playWavFile(path)
        emit(case, "STARTED", result=result, bytes=len(wav),
             seconds=seconds)
    elif case == "wav-file":
        result = speaker.playWav(wav)
        emit(case, "WAV_STARTED", result=bool(result), bytes=len(wav),
             seconds=seconds)
        settle(250)
        result = speaker.playWavFile(path)
        emit(case, "FILE_STARTED", result=result, bytes=len(wav),
             seconds=seconds)
    elif case in {"blocking-chunks", "paced-chunks"}:
        chunks = [
            pcm[offset:offset + 512]
            for offset in range(0, len(pcm), 512)
        ]
        for index, chunk in enumerate(chunks):
            emit(case, "CHUNK_START", index=index, bytes=len(chunk))
            result = speaker.playRaw(
                chunk, 8000, False, 1, 0, False
            )
            emit(case, "CHUNK_QUEUED", index=index, result=bool(result))
            if case == "paced-chunks":
                settle(40)
    else:
        raise ValueError("unknown speaker case: " + case)

    settle(1200)
    speaker.stop()
    speaker.end()
    emit(case, "DONE")
    print("SPEAKER_PATH_DONE " + case)


def settle(milliseconds):
    deadline = time.ticks_add(time.ticks_ms(), milliseconds)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        M5.update()
        time.sleep_ms(10)
