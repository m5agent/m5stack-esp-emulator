"""Bounded WAV and native PCM capture interpretation for Device Service."""

from __future__ import annotations

from array import array
import cmath
from hashlib import sha256
import io
import math
import os
from pathlib import Path
import struct
import sys
import wave

from device_service_errors import ServiceError

CARDPUTER_AUDIO_DEVICES = frozenset({"cardputer", "cardputer-adv"})
MICROPHONE_RATE = 16_000
MICROPHONE_MAX_FRAMES = 10 * MICROPHONE_RATE
WAV_MAX_BYTES = MICROPHONE_MAX_FRAMES * 2 + 64 * 1024
UNIT_AUDIO_MAX_TRACKS = 16
UNIT_AUDIO_MAX_CAPTURE_BYTES = 16 * 1024 * 1024
UNIT_AUDIO_SOURCE = "native_n9301_unit"
TAB5_AUDIO_SOURCE = "esp_emu_i2s1_tx"
TAB5_ESP32SIM_AUDIO_SOURCE = "esp32sim_i2s1_tx"
TAB5_MICROPHONE_SOURCE = "esp_emu_i2s1_rx"
TAB5_MICROPHONE_RATE = 48_000
TAB5_MICROPHONE_CHANNELS = 4
TAB5_MICROPHONE_SECONDS = 10
TAB5_MICROPHONE_MAX_BYTES = TAB5_MICROPHONE_RATE * TAB5_MICROPHONE_CHANNELS * 2 * TAB5_MICROPHONE_SECONDS + 64 * 1024
TAB5_AUDIO_EVIDENCE_BYTES = 8 * 1024 * 1024
TAB5_AUDIO_MAX_LEASE_SECONDS = 180
TAB5_AUDIO_WINDOW_EVIDENCE_BYTES = 1024 * 1024
TAB5_WAV_HEADER_BYTES = 44
TAB5_WAV_PLACEHOLDER = bytes(TAB5_WAV_HEADER_BYTES)
TAB5_PCM_FRAME_BYTES = 4
PCM_MAX_READ_BYTES = 512 * 1024
SPECTRUM_MAX_FRAMES = 8192


def decode_cardputer_wave(source: bytes) -> bytes:
    """Extract an exact s16le mono WAV fixture without resampling."""
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
                raise wave.Error("unsupported PCM fixture format")
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


def read_wave_artifact(path: Path, artifact_id: str) -> bytes:
    try:
        with path.open("rb") as stream:
            source = stream.read(WAV_MAX_BYTES + 1)
    except OSError as error:
        raise ServiceError("audio_fixture_unavailable", "WAV artifact could not be read", 409) from error
    pcm = decode_cardputer_wave(source)
    if sha256(source).hexdigest() != artifact_id:
        raise ServiceError("audio_fixture_unavailable", "WAV artifact digest changed", 409)
    return pcm


def read_tab5_microphone_artifact(path: Path, artifact_id: str) -> tuple[bytes, dict]:
    """Validate bytes for the stock Tab5 codec's four-slot I2S1 receive stream."""
    try:
        with path.open("rb") as stream:
            source = stream.read(TAB5_MICROPHONE_MAX_BYTES + 1)
    except OSError as error:
        raise ServiceError("audio_fixture_unavailable", "Tab5 WAV artifact could not be read", 409) from error
    if len(source) > TAB5_MICROPHONE_MAX_BYTES:
        raise ServiceError("audio_fixture_too_large", "Tab5 WAV fixture is too large", 413)
    if sha256(source).hexdigest() != artifact_id:
        raise ServiceError("audio_fixture_unavailable", "Tab5 WAV artifact digest changed", 409)
    try:
        _require_tab5_pcm16_header(source)
        with wave.open(io.BytesIO(source), "rb") as wav:
            frames = wav.getnframes()
            if (
                (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
                != (TAB5_MICROPHONE_CHANNELS, 2, TAB5_MICROPHONE_RATE)
                or wav.getcomptype() != "NONE"
                or not 1 <= frames <= TAB5_MICROPHONE_RATE * TAB5_MICROPHONE_SECONDS
            ):
                raise wave.Error("unsupported Tab5 PCM fixture format")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * TAB5_MICROPHONE_CHANNELS * 2 or wav.readframes(1):
                raise wave.Error("incomplete Tab5 PCM data")
    except (wave.Error, EOFError, RuntimeError) as error:
        raise ServiceError(
            "invalid_audio_fixture", "expected a complete 48 kHz four-channel signed 16-bit PCM WAV, up to 10 seconds", 400,
        ) from error
    return source, {
        "source": TAB5_MICROPHONE_SOURCE, "artifact_id": artifact_id, "pcm_sha256": sha256(pcm).hexdigest(),
        "sample_format": "s16le", "sample_rate_hz": TAB5_MICROPHONE_RATE,
        "channels": TAB5_MICROPHONE_CHANNELS, "frames": frames,
    }


def _require_tab5_pcm16_header(source: bytes) -> None:
    """Check the actual packed PCM bit depth, which wave rounds to bytes."""
    if len(source) < TAB5_WAV_HEADER_BYTES or source[:4] != b"RIFF" or source[8:12] != b"WAVE":
        raise wave.Error("invalid RIFF/WAVE container")
    container_end = 8 + struct.unpack_from("<I", source, 4)[0]
    if container_end > len(source):
        raise wave.Error("truncated RIFF container")
    offset = 12
    format_seen = False
    while offset + 8 <= container_end:
        chunk, size = struct.unpack_from("<4sI", source, offset)
        data_start = offset + 8
        data_end = data_start + size
        if data_end > container_end:
            raise wave.Error("WAV chunk exceeds its container")
        if chunk == b"data" and format_seen:
            return
        if chunk == b"fmt ":
            if format_seen or size < 16:
                raise wave.Error("invalid PCM format chunk")
            codec, _, _, _, _, bits = struct.unpack_from("<HHIIHH", source, data_start)
            if bits != 16:
                raise wave.Error("Tab5 audio requires 16-bit PCM")
            if codec == 0xFFFE and (size < 40 or struct.unpack_from("<H", source, data_start + 18)[0] != 16):
                raise wave.Error("Tab5 PCM fixture must declare 16 valid bits")
            format_seen = True
        offset = data_end + (size & 1)
    raise wave.Error("missing data or format chunk")


def _tab5_recording_id(seed: str, info: os.stat_result) -> str:
    return sha256(f"{seed}:{info.st_dev}:{info.st_ino}".encode()).hexdigest()


def read_tab5_speaker_cursor(path: Path, recording_seed: str) -> dict:
    """Observe file growth without interpreting the live WAV as finalized PCM."""
    try:
        with path.open("rb") as stream:
            header = stream.read(TAB5_WAV_HEADER_BYTES)
            info = os.fstat(stream.fileno())
    except OSError as error:
        raise ServiceError("audio_capture_unavailable", "Tab5 I2S1 recording has not started", 409) from error
    # The admitted runtime reserves the header as zeros until finalization.
    native_header = header[:4] == b"RIFF" and header[8:16] == b"WAVEfmt " and header[36:40] == b"data"
    if (len(header) != TAB5_WAV_HEADER_BYTES or info.st_size < TAB5_WAV_HEADER_BYTES
            or (header != TAB5_WAV_PLACEHOLDER and not native_header)):
        raise ServiceError("audio_capture_unavailable", "Tab5 I2S1 recording has not started", 409)
    return {
        "recording_id": _tab5_recording_id(recording_seed, info),
        "available_bytes": (info.st_size - TAB5_WAV_HEADER_BYTES) & ~(TAB5_PCM_FRAME_BYTES - 1),
    }


def read_tab5_speaker_pcm(
    path: Path, offset: int, limit: int, *, recording_seed: str | None = None,
    expected_recording_id: str | None = None, source: str = TAB5_AUDIO_SOURCE,
) -> tuple[bytes, dict]:
    """Read interleaved frames from the finalized native esp-emu recording."""
    try:
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            recording_id = _tab5_recording_id(recording_seed, info) if recording_seed else None
            if expected_recording_id is not None and recording_id != expected_recording_id:
                raise ServiceError("audio_recording_changed", "Tab5 speaker recording identity changed", 409)
            with wave.open(stream, "rb") as wav:
                data, sample_rate, channels, observed = _read_tab5_wav_window(
                    wav, info.st_size, offset, limit, exact=expected_recording_id is not None,
                )
    except (OSError, wave.Error, EOFError) as error:
        raise ServiceError("audio_capture_unavailable", "no finalized Tab5 I2S1 recording", 409) from error
    if sys.byteorder != "little":
        samples = array("h", data)
        samples.byteswap()
        data = samples.tobytes()
    return data, {
        "source": source, "sample_format": "s16le",
        "sample_rate_hz": sample_rate, "channels": channels, "observed_bytes": observed,
        **({"recording_id": recording_id} if recording_id else {}),
    }


def finalize_tab5_stereo_wav(path: Path, sample_rate: int) -> None:
    with path.open("r+b") as stream:
        data_size = os.fstat(stream.fileno()).st_size - TAB5_WAV_HEADER_BYTES
        if data_size <= 0 or data_size % TAB5_PCM_FRAME_BYTES:
            raise ValueError("Incomplete Tab5 stereo PCM frames")
        stream.write(struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", data_size + 36, b"WAVE", b"fmt ", 16, 1, 2,
            sample_rate, sample_rate * TAB5_PCM_FRAME_BYTES, TAB5_PCM_FRAME_BYTES, 16,
            b"data", data_size,
        ))


def _read_tab5_wav_window(
    wav: wave.Wave_read, size: int, offset: int, limit: int, *, exact: bool,
) -> tuple[bytes, int, int, int]:
    channels, width = wav.getnchannels(), wav.getsampwidth()
    sample_rate = wav.getframerate()
    if channels != 2 or width != 2 or not 8000 <= sample_rate <= 192000:
        raise wave.Error("unexpected native speaker layout")
    observed = wav.getnframes() * TAB5_PCM_FRAME_BYTES
    if observed == 0 or observed + TAB5_WAV_HEADER_BYTES != size:
        raise wave.Error("incomplete native speaker capture")
    if offset % TAB5_PCM_FRAME_BYTES or limit % TAB5_PCM_FRAME_BYTES:
        raise ServiceError("invalid_audio_layout", "Tab5 PCM byte ranges must align to stereo frames", 400)
    if offset > observed or (exact and offset + limit > observed):
        raise ServiceError("audio_range_unavailable", "requested range exceeds the observed capture length", 416)
    wav.setpos(offset // TAB5_PCM_FRAME_BYTES)
    count = min(limit, observed - offset)
    data = wav.readframes(count // TAB5_PCM_FRAME_BYTES)
    if len(data) != count:
        raise wave.Error("native speaker capture changed during read")
    return data, sample_rate, channels, observed


def tab5_stereo_pcm_metrics(data: bytes, sample_rate_hz: int) -> dict:
    samples = array("h", data)
    channels = [pcm_metrics(samples[channel::2].tobytes(), sample_rate_hz) for channel in range(2)]
    return {
        "layout_source": "esp_emu_wav",
        "frames": len(samples) // 2,
        "spectrum_frames": channels[0]["spectrum_frames"],
        "peak": max(channel["peak"] for channel in channels),
        "rms": round(math.hypot(*(channel["rms"] for channel in channels)) / math.sqrt(2), 3),
        "dominant_frequency_hz": None,
        "channel_metrics": [
            {key: channel[key] for key in ("rms", "peak", "dominant_frequency_hz")}
            for channel in channels
        ],
    }


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
