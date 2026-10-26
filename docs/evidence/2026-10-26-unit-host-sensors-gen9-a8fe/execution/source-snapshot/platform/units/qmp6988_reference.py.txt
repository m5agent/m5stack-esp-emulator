#!/usr/bin/env python3
"""Offline QMP6988 register-fixture reference; never a runtime adapter.

The calibration decoding and compensation equations follow the official
M5Stack UIFlow2 driver checked on 2026-10-26:
https://github.com/m5stack/uiflow-micropython/blob/master/m5stack/libs/driver/qmp6988.py

The selected OTP bytes are synthetic values within the encoded coefficient
domain. They are not factory calibration read from a physical sensor. This
utility encodes controller-visible registers for a deterministic test fixture;
it does not replace the guest's calibration/compensation or establish hardware
accuracy, electrical behavior, sensor timing, or runtime model coverage.
"""

from __future__ import annotations

import json
import struct


NAMES = ("b00", "bt1", "bt2", "bp1", "b11", "bp2", "b12", "b21", "bp3", "a0", "a1", "a2")
TRANSFORMS = {
    "a1": (-6.30e-3, 4.30e-4),
    "a2": (-1.90e-11, 1.20e-10),
    "bt1": (1.00e-1, 9.10e-2),
    "bt2": (1.20e-8, 1.20e-6),
    "bp1": (3.30e-2, 1.90e-2),
    "b11": (2.10e-7, 1.40e-7),
    "bp2": (-6.30e-10, 3.50e-10),
    "b12": (2.90e-13, 7.60e-13),
    "b21": (2.10e-15, 1.20e-14),
    "bp3": (1.30e-16, 7.90e-17),
}
RAW_MIN = -(1 << 23)
RAW_MAX = (1 << 23) - 1


def synthetic_calibration() -> bytes:
    """Choose deterministic OTP words; these have no physical provenance."""
    words = {name: 0 for name in NAMES}
    words.update(b00=20000, a0=640)
    return struct.pack(">12hB", *(words[name] for name in NAMES), 0)


def decode_calibration(data: bytes) -> dict[str, float]:
    if len(data) != 25:
        raise ValueError("QMP6988 calibration is 25 bytes")
    values = dict(zip(NAMES, struct.unpack(">12h", data[:24])))
    values["b00"] = ((values["b00"] << 4) | (data[24] >> 4)) / 16
    values["a0"] = ((values["a0"] << 4) | (data[24] & 15)) / 16
    for name, (center, span) in TRANSFORMS.items():
        values[name] = center + span * values[name] / 32767
    return values


def compensate(data: bytes, calibration: bytes) -> tuple[float, float]:
    if len(data) != 6:
        raise ValueError("QMP6988 sample is six bytes")
    c = decode_calibration(calibration)
    dp = int.from_bytes(data[:3], "big") - (1 << 23)
    dt = int.from_bytes(data[3:], "big") - (1 << 23)
    tr = c["a0"] + c["a1"] * dt + c["a2"] * dt**2
    pr = (
        c["b00"] + c["bt1"] * tr + c["bp1"] * dp
        + c["b11"] * tr * dp + c["bt2"] * tr**2
        + c["bp2"] * dp**2 + c["b12"] * dp * tr**2
        + c["b21"] * dp**2 * tr + c["bp3"] * dp**3
    )
    return tr / 256, pr


def _nearest_monotonic(target: float, evaluate, *, increasing: bool) -> int:
    lo, hi = RAW_MIN, RAW_MAX
    a, b = sorted((evaluate(lo), evaluate(hi)))
    if not a <= target <= b:
        raise ValueError("Requested fixture is outside this OTP/raw domain")
    while lo < hi:
        mid = (lo + hi) // 2
        if (evaluate(mid) < target) == increasing:
            lo = mid + 1
        else:
            hi = mid
    candidates = (max(RAW_MIN, lo - 1), lo)
    return min(candidates, key=lambda raw: abs(evaluate(raw) - target))


def encode(temperature_c: float, pressure_pa: float, calibration: bytes | None = None) -> bytes:
    """Invert the synthetic fixture's monotonic transfer into 24-bit samples."""
    calibration = calibration or synthetic_calibration()
    if calibration != synthetic_calibration():
        raise ValueError("Inverse is validated only for the selected synthetic OTP fixture")
    c = decode_calibration(calibration)
    dt = _nearest_monotonic(
        temperature_c * 256,
        lambda raw: c["a0"] + c["a1"] * raw + c["a2"] * raw**2,
        increasing=False,
    )
    tr = c["a0"] + c["a1"] * dt + c["a2"] * dt**2

    def pressure(raw: int) -> float:
        return (
            c["b00"] + c["bt1"] * tr + c["bp1"] * raw
            + c["b11"] * tr * raw + c["bt2"] * tr**2
            + c["bp2"] * raw**2 + c["b12"] * raw * tr**2
            + c["b21"] * raw**2 * tr + c["bp3"] * raw**3
        )

    dp = _nearest_monotonic(pressure_pa, pressure, increasing=True)
    return (dp + (1 << 23)).to_bytes(3, "big") + (dt + (1 << 23)).to_bytes(3, "big")


def fixture() -> dict:
    calibration = synthetic_calibration()
    cases = []
    for temperature_c, pressure_pa in ((25, 101325), (-40, 30000), (120, 110000), (0, 80000), (50, 95000)):
        raw = encode(temperature_c, pressure_pa, calibration)
        actual_t, actual_p = compensate(raw, calibration)
        cases.append({
            "requested": {"temperature_c": temperature_c, "pressure_pa": pressure_pa},
            "register_f7_hex": raw.hex(),
            "decoded": {"temperature_c": actual_t, "pressure_pa": actual_p},
            "quantization_error": {"temperature_c": actual_t - temperature_c, "pressure_pa": actual_p - pressure_pa},
        })
    return {
        "schema_version": 1,
        "checked_at": "2026-10-26",
        "kind": "offline-synthetic-register-fixture",
        "provenance": "Synthetic legal-domain OTP; no physical sensor calibration or runtime PASS is claimed.",
        "official_driver": "https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/qmp6988.py",
        "address_7bit": 0x70,
        "chip_id": {"register": "0xD1", "value": "0x5C"},
        "calibration": {"register": "0xA0", "length": 25, "hex": calibration.hex()},
        "reference_coefficients": decode_calibration(calibration),
        "cases": cases,
    }


if __name__ == "__main__":
    print(json.dumps(fixture(), ensure_ascii=False, indent=2))
