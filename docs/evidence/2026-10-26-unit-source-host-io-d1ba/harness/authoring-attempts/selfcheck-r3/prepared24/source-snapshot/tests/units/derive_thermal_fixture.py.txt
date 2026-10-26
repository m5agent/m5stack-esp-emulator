#!/usr/bin/env python3
"""Derive a reproducible raw-IR perturbation and offline numeric reference.

This executes only the unchanged driver's calibration/math functions on the
host. It never starts a guest or supplies replacement guest I2C/API methods.
The generated values are expectations, not runtime or physical measurements.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "platform/units/fixtures/mlx90640-public-example"
DRIVER = Path(__file__).parent / "sensors_probe/sensor_drivers/mlx90640.py"


def words(encoded):
    return [int(encoded[index:index + 4], 16) for index in range(0, len(encoded), 4)]


def calculate(initial):
    spec = importlib.util.spec_from_file_location("official_mlx90640_reference", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.eeData[:] = words(initial["eeprom-hex"])
    sensor = module.MLX90640.__new__(module.MLX90640)
    sensor._extract_parameters()
    result = [0.0] * 768
    for page in (0, 1):
        frame = words(initial[f"frame{page}-hex"]) + [initial["control-word"], page]
        sensor._calculate_to(frame, 0.95, sensor._get_ta(frame) - 8, result)
    assert len(result) == 768 and all(math.isfinite(value) for value in result)
    return result


def main():
    source_file = FIXTURES / "fixture.json"
    source = json.loads(source_file.read_text())
    baseline = calculate(source["initial"])
    assert max(abs(a - b) for a, b in zip(baseline, source["expected"]["pixel_temperature_c"])) < 1e-8
    initial = dict(source["initial"])
    for page in (0, 1):
        raw = words(initial[f"frame{page}-hex"])
        raw[:768] = [(value + 16) & 65535 for value in raw[:768]]
        initial[f"frame{page}-hex"] = "".join(f"{value:04x}" for value in raw)
    temperatures = calculate(initial)
    artifact = {
        "schema_version": 1,
        "kind": "synthetic-raw-ir-perturbation-of-public-reference",
        "source_fixture_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
        "derivation": "Add 16 modulo 65536 to each of the first 768 raw words in both subpages; preserve EEPROM, auxiliary words and control register.",
        "initial": initial,
        "expected": {
            "pixel_count": 768, "min_c": min(temperatures), "max_c": max(temperatures),
            "mean_c": sum(temperatures) / 768,
            "samples_c": {index: temperatures[int(index)] for index in source["expected"]["samples_c"]},
        },
        "offline_validation": {
            "driver_sha256": hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
            "method": "Unchanged official driver EEPROM extraction and _get_ta/_calculate_to math; no mocked guest APIs or runtime execution.",
            "runtime_evidence": False,
        },
    }
    destination = FIXTURES / "synthetic-plus16.json"
    destination.write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps({"fixture": destination.name, "samples_c": artifact["expected"]["samples_c"]}))


if __name__ == "__main__":
    main()
