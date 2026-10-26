#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Derived arithmetic: Copyright 2019-2023 Espressif Systems (Shanghai) CO LTD.
"""Synthetic ESP32-S3 Unit ADC calibration; never writes hardware or files.

Field decoding and curve-reference arithmetic follow the Apache-2.0 Espressif
sources pinned in the fixture. Guest ADC APIs and QEMU SAR reads are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "platform/units/fixtures/esp32s3-adc-calibration.json"
BLOCK_OFFSETS = {0: 0, 1: 24, 2: 48}
FIELD_LAYOUT = {
    "BLK_VERSION_MAJOR": (2, 128, 2),
    **{f"ADC1_INIT_CODE_ATTEN{i}": (2, bit, width) for i, (bit, width) in enumerate(((149, 8), (157, 6), (163, 6), (169, 6)))},
    **{f"ADC2_INIT_CODE_ATTEN{i}": (2, bit, width) for i, (bit, width) in enumerate(((175, 8), (183, 6), (189, 6), (195, 6)))},
    **{f"ADC1_CAL_VOL_ATTEN{i}": (2, 201 + i * 8, 8) for i in range(4)},
    "ADC2_CAL_VOL_ATTEN0": (2, 233, 8),
    "ADC2_CAL_VOL_ATTEN1": (2, 241, 7),
    "ADC2_CAL_VOL_ATTEN2": (2, 248, 7),
    "ADC2_CAL_VOL_ATTEN3": (1, 186, 6),
}


def load_fixture(path: Path = FIXTURE, *, raw: bytes | None = None) -> dict:
    data = raw if raw is not None else path.read_bytes()
    if not isinstance(data, bytes):
        raise ValueError("frozen ADC fixture must be exact UTF-8 bytes")
    fixture = json.loads(data.decode("utf-8"))
    if not isinstance(fixture, dict) or type(fixture.get("schema_version")) is not int or fixture["schema_version"] != 1 or fixture.get("kind") != "synthetic-virtual-device-calibration":
        raise ValueError("unsupported synthetic ADC fixture")
    fields = fixture.get("fields", [])
    if not isinstance(fields, list) or any(
        not isinstance(field, dict)
        or set(field) != {"name", "block", "bit_start", "bit_count", "value"}
        or not isinstance(field["name"], str)
        or any(type(field[key]) is not int for key in ("block", "bit_start", "bit_count", "value"))
        for field in fields
    ):
        raise ValueError("invalid ADC field layout")
    locations = {field["name"]: (field["block"], field["bit_start"], field["bit_count"]) for field in fields}
    if locations != FIELD_LAYOUT or len(fields) != len(FIELD_LAYOUT):
        raise ValueError("fixture may write only the exact S3 ADC calibration fields")
    profile = fixture.get("sar_profile", {})
    if not isinstance(profile, dict) or fixture.get("backend") != "qemu-esp32s3" or profile.get("full_scale_mv") != [950, 1250, 1750, 3100] or any(
        type(profile.get(key)) is not int or profile[key] != value
        for key, value in (("bit_width", 12), ("maximum_raw", 4095), ("reference_voltage_mv", 850))
    ) or profile.get("id") != "s3-unit-ideal-12bit-v1":
        raise ValueError("fixture does not describe the supported ideal S3 SAR profile")
    if fixture.get("hardware_validation") is not False or fixture.get("efuse_layout") != {
        "kind": "qemu-esp-efuse-compact-blocks-le", "image_bytes": 4096,
        "block_byte_offsets": {"0": 0, "1": 24, "2": 48},
    }:
        raise ValueError("fixture must describe synthetic compact virtual eFuse only")
    if not isinstance(fixture.get("id"), str) or not fixture["id"]:
        raise ValueError("fixture requires an identifier")
    _firmware_binding(fixture)
    for field in fields:
        if type(field["value"]) is not int or not 0 <= field["value"] < 1 << field["bit_count"]:
            raise ValueError("invalid ADC field value")
    return fixture


def _firmware_binding(fixture: dict) -> tuple[int, int, str]:
    binding = fixture.get("firmware_binding")
    if not isinstance(binding, dict):
        raise ValueError("fixture requires an application-byte binding")
    start, length = binding.get("application_offset"), binding.get("application_segment_bytes")
    digest = binding.get("application_segment_sha256")
    if type(start) is not int or start < 0 or type(length) is not int or length <= 0 or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid application-byte binding")
    return start, length, digest


def field_value(image: bytes | bytearray, field: dict) -> int:
    start = BLOCK_OFFSETS[field["block"]] * 8 + field["bit_start"]
    return sum(((image[(start + bit) // 8] >> ((start + bit) % 8)) & 1) << bit for bit in range(field["bit_count"]))


def decoded_reference_digital(fixture: dict) -> dict[str, list[int]]:
    """S3 esp_efuse_rtc_calib_get_cal_voltage V1 unsigned deltas."""
    values = {field["name"]: field["value"] for field in fixture["fields"]}
    adc1 = [0] * 4
    adc1[3] = values["ADC1_CAL_VOL_ATTEN3"] + 900
    adc1[2] = values["ADC1_CAL_VOL_ATTEN2"] + adc1[3] + 800
    adc1[1] = values["ADC1_CAL_VOL_ATTEN1"] + adc1[2] + 700
    adc1[0] = values["ADC1_CAL_VOL_ATTEN0"] + adc1[1] + 800
    adc2 = [adc1[i] - values[f"ADC2_CAL_VOL_ATTEN{i}"] + (40, 10, 20, 15)[i] for i in range(4)]
    return {"adc1": adc1, "adc2": adc2}


def verify_firmware(firmware: bytes, fixture: dict) -> None:
    """Bind actual application bytes while allowing session VFS/NVS overlays."""
    start, length, digest = _firmware_binding(fixture)
    end = start + length
    if not isinstance(firmware, bytes) or len(firmware) < end or hashlib.sha256(firmware[start:end]).hexdigest() != digest:
        raise ValueError("synthetic ADC calibration is not validated for these firmware application bytes")


def apply_s3_adc_calibration(
    image: bytearray, *, backend: str, firmware: bytes, fixture_path: Path = FIXTURE,
    fixture_raw: bytes | None = None,
) -> dict:
    """Patch a fresh session's virtual eFuse in memory, preserving other bits.

    Call only for an explicit Angle/Light Unit execution. A nonzero conflicting
    calibration field fails before any mutation; real/unknown firmware fails
    admission. This function never flashes, erases or accesses a physical chip.
    """
    fixture_bytes = fixture_raw if fixture_raw is not None else fixture_path.read_bytes()
    if not isinstance(fixture_bytes, bytes):
        raise ValueError("frozen ADC fixture must be exact UTF-8 bytes")
    fixture = load_fixture(fixture_path, raw=fixture_bytes)
    if backend != "qemu-esp32s3" or not isinstance(image, bytearray) or len(image) != 4096:
        raise ValueError("requires a 4096-byte QEMU ESP32-S3 virtual eFuse buffer")
    verify_firmware(firmware, fixture)
    references = decoded_reference_digital(fixture)
    expected = [math.floor(850 * 4095 / scale + 0.5) for scale in fixture["sar_profile"]["full_scale_mv"]]
    if references != {"adc1": expected, "adc2": expected}:
        raise ValueError("synthetic eFuse references do not match the admitted SAR transfer")
    values = {field["name"]: field["value"] for field in fixture["fields"]}
    if values["BLK_VERSION_MAJOR"] != 1 or any(value != 0 for name, value in values.items() if "INIT_CODE" in name):
        raise ValueError("unsupported calibration version or offset fixture")
    candidate = bytearray(image)
    for field in fixture["fields"]:
        old = field_value(image, field)
        if old not in {0, field["value"]}:
            raise ValueError("existing virtual calibration conflicts with the synthetic fixture")
        start = BLOCK_OFFSETS[field["block"]] * 8 + field["bit_start"]
        for bit in range(field["bit_count"]):
            if field["value"] & (1 << bit):
                candidate[(start + bit) // 8] |= 1 << ((start + bit) % 8)
    image[:] = candidate
    return {
        "schema_version": 1, "status": "applied", "kind": fixture["kind"], "fixture_id": fixture["id"],
        "source": "session-frozen-fixture" if fixture_raw is not None else "explicit-fixture-file",
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "sar_profile": fixture["sar_profile"]["id"],
        "application_segment_sha256": fixture["firmware_binding"]["application_segment_sha256"],
        "reference_voltage_mv": 850, "reference_digital": references,
        "fields": values, "hardware_validation": False,
        "identity_or_security_fields_changed": False,
    }


def expected_read_uv(raw: int, *, attenuation: int = 3, adc_unit: int = 1, fixture: dict | None = None) -> int:
    """Host numeric oracle only; never a guest API or runtime return source."""
    fixture = fixture or load_fixture()
    if type(raw) is not int or not 0 <= raw <= 4095 or type(attenuation) is not int or attenuation not in range(4) or type(adc_unit) is not int or adc_unit not in (1, 2):
        raise ValueError("invalid S3 ADC reference input")
    reference = decoded_reference_digital(fixture)[f"adc{adc_unit}"][attenuation]
    coefficient = 65536 * 850 // reference
    voltage = raw * coefficient // 65536
    error = 0
    if voltage:
        variable = 1
        for numerator, denominator, sign in fixture["idf_second_stage_coefficients"][f"adc{adc_unit}"][attenuation]:
            # Match the official uint64_t integer products and per-term floors.
            error += ((variable * numerator) & ((1 << 64) - 1)) // denominator * sign
            variable = (variable * voltage) & ((1 << 64) - 1)
    return (voltage - error) * 1000


def expected_ideal_input(voltage_mv: float, *, attenuation: int = 3, adc_unit: int = 1) -> dict:
    fixture = load_fixture()
    try:
        finite = math.isfinite(voltage_mv)
    except (OverflowError, TypeError):
        finite = False
    if isinstance(voltage_mv, bool) or not isinstance(voltage_mv, (int, float)) or not finite or voltage_mv < 0 or type(attenuation) is not int or attenuation not in range(4):
        raise ValueError("invalid physical ADC test input")
    scale = fixture["sar_profile"]["full_scale_mv"][attenuation]
    raw = 4095 if voltage_mv >= scale else math.floor(voltage_mv * 4095 / scale + 0.5)
    return {
        "input_mv": voltage_mv, "raw_12bit": raw, "read_u16": (raw << 4) | (raw >> 8),
        "read_uv": expected_read_uv(raw, attenuation=attenuation, adc_unit=adc_unit, fixture=fixture),
        "scope": "synthetic QEMU SAR plus unchanged IDF curve-fitting reference, not hardware accuracy",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify public fixture layout and derived reference points")
    parser.add_argument("--input-mv", type=float, help="Print the host-only expected raw/u16/uv for a synthetic input")
    args = parser.parse_args()
    fixture = load_fixture()
    if args.input_mv is not None:
        print(json.dumps(expected_ideal_input(args.input_mv), indent=2))
    elif args.check:
        expected = [math.floor(850 * 4095 / scale + 0.5) for scale in (950, 1250, 1750, 3100)]
        if decoded_reference_digital(fixture) != {"adc1": expected, "adc2": expected}:
            raise SystemExit("UNIT_ADC_FIXTURE_INVALID")
        print("UNIT_ADC_FIXTURE_OK")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
