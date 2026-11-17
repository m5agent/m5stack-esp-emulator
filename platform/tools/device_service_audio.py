"""Bounded WAV and raw I2S capture interpretation for the Device Service."""

from __future__ import annotations

from array import array
import cmath
import io
import math
import sys
import wave

from device_service_errors import ServiceError

CARDPUTER_AUDIO_DEVICES = frozenset({"cardputer", "cardputer-adv"})
MICROPHONE_RATE = 16_000
MICROPHONE_MAX_FRAMES = 10 * MICROPHONE_RATE
WAV_MAX_BYTES = MICROPHONE_MAX_FRAMES * 2 + 64 * 1024
PCM_MAX_READ_BYTES = 512 * 1024
SPECTRUM_MAX_FRAMES = 8192


def decode_cardputer_wave(source: bytes) -> bytes:
    """Extract an exact s16le mono microphone fixture without resampling."""
    if len(source) > WAV_MAX_BYTES:
        raise ServiceError("audio_fixture_too_large", "WAV fixture is too large", 413)
    try:
        with wave.open(io.BytesIO(source), "rb") as wav:
            frames = wav.getnframes()
            if (
                (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, MICROPHONE_RATE)
                or wav.getcomptype() != "NONE"
                or not 1 <= frames <= MICROPHONE_MAX_FRAMES
            ):
                raise wave.Error("unsupported microphone fixture format")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2 or wav.readframes(1):
                raise wave.Error("invalid PCM data size")
    except (wave.Error, EOFError) as error:
        raise ServiceError(
            "invalid_audio_fixture", "expected a complete 16 kHz mono signed 16-bit PCM WAV, up to 10 seconds", 400,
        ) from error
    if sys.byteorder != "little":
        samples = array("h", pcm)
        samples.byteswap()
        return samples.tobytes()
    return pcm


def pcm_metrics(data: bytes, sample_rate_hz: int) -> dict:
    """Interpret the caller-declared s16le mono window as digital samples."""
    samples = array("h", data)
    if sys.byteorder != "little":
        samples.byteswap()
    count = len(samples)
    rms = math.sqrt(sum(sample * sample for sample in samples) / count)
    # Prefer the largest power-of-two window bounded independently of the read.
    length = min(SPECTRUM_MAX_FRAMES, 1 << (count.bit_length() - 1))
    frequency = dominant_frequency(samples[:length], sample_rate_hz) if length >= 256 else None
    return {
        "sample_format": "s16le",
        "layout_source": "caller_declared_mono",
        "sample_rate_hz": sample_rate_hz,
        "frames": count,
        "rms": round(rms, 3),
        "peak": max(abs(sample) for sample in samples),
        "dominant_frequency_hz": frequency,
        "spectrum_frames": length if length >= 256 else 0,
    }


def dominant_frequency(samples: array, rate: int) -> float | None:
    """Find the strongest non-DC band of one Hann-windowed sample block."""
    size = len(samples)
    mean = sum(samples) / size
    if all(sample == samples[0] for sample in samples):
        return None
    spectrum = [
        (sample - mean) * (0.5 - 0.5 * math.cos(math.tau * index / (size - 1)))
        for index, sample in enumerate(samples)
    ]
    # In-place radix-2 FFT, first reordering the time samples by reversed bits.
    reverse = 0
    for index in range(1, size):
        bit = size >> 1
        while reverse & bit:
            reverse ^= bit
            bit >>= 1
        reverse ^= bit
        if reverse > index:
            spectrum[index], spectrum[reverse] = spectrum[reverse], spectrum[index]
    width = 2
    while width <= size:
        half = width // 2
        step = cmath.exp(-math.tau * 1j / width)
        for start in range(0, size, width):
            angle = 1
            for index in range(start, start + half):
                first = spectrum[index]
                second = angle * spectrum[index + half]
                spectrum[index] = first + second
                spectrum[index + half] = first - second
                angle *= step
        width *= 2
    powers = [abs(value) ** 2 for value in spectrum[:size // 2 + 1]]
    peak = max(range(1, len(powers)), key=powers.__getitem__)
    shift = 0.0
    if 1 < peak < len(powers) - 1:
        left, midpoint, right = powers[peak - 1:peak + 2]
        curvature = left - 2 * midpoint + right
        if curvature:
            shift = 0.5 * (left - right) / curvature
    return round((peak + shift) * rate / size, 3)
