#!/usr/bin/env python3
"""Validate the twelve Units of the fourth research batch.

One QEMU build is enough because the merged 0134 (A+B) and 0136 (C) layers
are both applied to the same tree. Each case builds a merged reference-firmware
image that runs the firmware's frozen original UIFlow2 driver, creates one
visible leased `/api/v1` session, injects external fixtures through
`unit-input`/QOM, reads controller-backed state, captures serial markers, the
frame and the evidence ZIP before stopping with `purge=0`.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
from run_service_cases import Client, wait_for  # noqa: E402
from run_profile_ui_test import build_image  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402

MARKER = "BATCH4_PROBE_READY"

QEMU_SOURCE_STATE = "canonical 75f1d24 + 0120/0121/0122/0123 + 0125/0126/0127/0128/0129 + 0131 + 0134 + 0136"

CASES = {
    # A+B (0134)
    "rs485-iso": "cores3", "laser-tx": "cores3", "co2l": "cores3",
    "neco": "cores3", "midi": "cores3", "tof4m": "cores3",
    # C (0136)
    "weight": "cores3", "bldc-driver": "cores3", "ac-measure": "cores3",
    "dds": "cores3", "gps": "cores3", "uhf-rfid": "cores3",
}
AB_CASES = ("rs485-iso", "laser-tx", "co2l", "neco", "midi", "tof4m")
C_CASES = ("weight", "bldc-driver", "ac-measure", "dds", "gps", "uhf-rfid")
# The official PinMaps put GPIO/RMT units on PORT.B and UART units on PORT.C,
# but the current host-port registry only admits main-device ports, and on
# cores3 that is PORT.A. All sessions therefore use the cores3 PORT.A pins as
# the harness wiring; the guest driver still drives the real SoC GPIO/RMT/UART
# controller path on those pins, and reports record the substitution.
OFFICIAL_PORT = {
    "rs485-iso": "PORT.C", "midi": "PORT.C", "gps": "PORT.C", "uhf-rfid": "PORT.C",
    "laser-tx": "PORT.B", "neco": "PORT.B", "weight": "PORT.B",
    "co2l": "PORT.A", "tof4m": "PORT.A", "bldc-driver": "PORT.A",
    "ac-measure": "PORT.A", "dds": "PORT.A",
}
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "rs485-iso": "RS485Unit(uSerial/Modbus master)",
    "laser-tx": "LaserTXUnit (GPIO DIN)",
    "co2l": "CO2LUnit(CO2Unit/SCD41)",
    "neco": "NECOUnit(WS2812 + Button)",
    "midi": "MIDIUnit(SAM2695)",
    "tof4m": "TOF4MUnit(VL53L1X)",
    "weight": "WeightUnit(HX711 bit-pulse)",
    "bldc-driver": "BLDCDriverUnit",
    "ac-measure": "AC_MEASUREUnit",
    "dds": "DDSUnit(AD9833)",
    "gps": "GPSUnit(NMEA)",
    "uhf-rfid": "UHFRFIDUnit(JRD4035)",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_serial(client: Client, session_id: str) -> str:
    return client.json(f"sessions/{session_id}/serial?limit=262144").get("data", "")


def properties(client: Client, session_id: str) -> dict:
    state = client.json(f"sessions/{session_id}/units")
    units = state.get("units") or []
    if not units:
        raise RuntimeError("session has no Unit state")
    return units[0].get("properties") or {}


def wait_properties(client: Client, session_id: str, predicate, timeout: float = 8.0, label: str = "QOM"):
    deadline = time.monotonic() + timeout
    samples, last = [], None
    while time.monotonic() < deadline:
        last = properties(client, session_id)
        samples.append({"at": utc_now(), "properties": last})
        if predicate(last):
            return last, samples
        time.sleep(0.1)
    raise RuntimeError(f"{label} condition not observed; last={last}")


def inject(client: Client, session_id: str, values: dict) -> dict:
    state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
        "id": "external1", "values": values,
    })
    return state["units"][0]["properties"]


def last_match(pattern: str, serial: str):
    matches = re.findall(pattern, serial)
    return matches[-1] if matches else None


def port_for(client: Client, device_id: str, unit_id: str) -> dict:
    registry = client.json(f"units?device_id={device_id}")
    host = registry["hosts"][0]
    unit_rows = {row["id"]: row for row in registry["units"]}
    admission = unit_rows[unit_id]["host_admission"]
    if not admission["admitted"]:
        raise RuntimeError(f"{unit_id} is not admitted on {device_id}: {admission}")
    port_id = PORT_IDS[unit_id]
    port = next(port for port in host["ports"] if port["id"] == port_id)
    if port_id not in admission["port_ids"]:
        raise RuntimeError(f"{unit_id} admission does not include {port_id}: {admission}")
    return port


def u16(value: int) -> int:
    return int(value) & 0xFFFF


def run_case(client: Client, args, case: str) -> dict:
    device = CASES[case]
    batch = "A+B" if case in AB_CASES else "C"
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device_row = next(row for row in matrix["devices"] if row["id"] == device)
    port = port_for(client, device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch4_probe", files, dirs_exist_ok=True)
    (files / "probe_config.py").write_text(
        f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n",
        encoding="utf-8",
    )
    image = build_image(SimpleNamespace(
        base=ROOT / device_row["base"], flash_size=int(device_row["flash_size"], 0),
        files_dir=files, mklittlefs=None, preserve_vfs=False,
        vfs_offset=int(device_row["vfs_offset"], 0), vfs_size=int(device_row["vfs_size"], 0),
        prog_size=32, out_dir=output,
    ))
    firmware_bytes = image.read_bytes()
    result = {
        "schema_version": 1, "date": utc_now(),
        "validation": "virtual-device validation",
        "scope": "device-local Unit data plane through a visible Device Service session; not hardware",
        "device_id": device, "unit_id": case, "batch": batch,
        "driver_class": CASE_DRIVERS[case],
        "driver_flavor": "reference-firmware-frozen-original-unit-driver",
        "runtime": "qemu", "status": "FAIL", "checks": {},
        "firmware_sha256": sha256(firmware_bytes),
        "base_firmware_sha256": sha256((ROOT / device_row["base"]).read_bytes()),
        "probe_sha256": {path.name: sha256(path.read_bytes()) for path in files.glob("*.py")},
        "runtime_binary_sha256": None,
        "fixture_source_baseline": QEMU_SOURCE_STATE,
        "port": {"id": port["id"], "pins": port["pins"]},
        "qom_samples": [], "serial_markers": {}, "observations": {},
        "official_port": OFFICIAL_PORT[case],
        "runtime_port_substitution": (
            "cores3 PORT.A harness wiring; the official product PinMap connector is "
            + OFFICIAL_PORT[case] + " and is not the admitted runtime host port on cores3")
        if OFFICIAL_PORT[case] != "PORT.A" else None,
    }
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{device}-batch4-{case}.bin",
        })
        firmware = client.json("firmware", method="POST", payload={
            "device_id": device, "kind": "merged", "artifact_id": artifact["artifact_id"],
        })
        result["firmware_id"] = firmware["firmware_id"]
        session = client.json("sessions", method="POST", payload={
            "device_id": device, "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 300, "ready_marker": MARKER, "ready_timeout_seconds": 120,
            "units": [{"id": "external1", "unit_id": case, "port_id": port["id"]}],
        })
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created on {device}/{port['id']}", flush=True)
        serial = wait_for(client, session_id, lambda text: MARKER in text, 150)
        result["checks"]["official_driver_ready"] = True
        result["serial_markers"]["ready"] = serial[serial.index(MARKER):serial.index(MARKER) + len(MARKER)]
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        attached = (live.get("units") or [{}])[0]
        result["attached_unit"] = {key: attached.get(key) for key in ("id", "unit_id", "available", "source")}

        if case == "rs485-iso":
            serial = wait_for(client, session_id, lambda text: "UART_RS485_TX 48454c4c4f" in text, 60)
            result["qom_samples"].append({"at": utc_now(), "properties": properties(client, session_id)})
            injected = "4d4f44425553"  # "MODBUS"
            inject(client, session_id, {"rx-hex": injected})
            serial = wait_for(client, session_id, lambda text: "UART_RS485_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["rs485-iso"] = serial[-700:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("tx-hex") == "48454c4c4f" and int(p.get("written-bytes", 0)) >= 5,
                label="rs485-iso qom")
            result["qom_samples"].extend(samples)
            guest_rx = last_match(r"UART_RS485_RX_TOTAL ([0-9a-f]*)", serial)
            result["observations"]["rs485_iso"] = {
                "guest_rx_hex": guest_rx, "injected_rx_hex": injected,
                "qom": {k: final.get(k) for k in ("rx-hex", "tx-hex", "transactions",
                                                  "read-bytes", "written-bytes")},
                "boundary": "RS485 isolation/ESD/fail-safe/500Kbps/256-node and physical bus behavior NOT RUN; "
                            "the frozen uSerial driver owns Modbus framing.",
            }
            result["checks"]["guest_tx_captured"] = final.get("tx-hex") == "48454c4c4f"
            result["checks"]["guest_rx_matches_injected"] = guest_rx == injected
            result["checks"]["qom_rx_fixture_exact"] = final.get("rx-hex") == injected
            result["checks"]["uart_bytes_counted"] = (
                int(final.get("written-bytes", 0)) >= 5 and int(final.get("read-bytes", 0)) >= 6)
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "laser-tx":
            serial = wait_for(client, session_id, lambda text: "GPIO_LASER_TX_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["laser-tx"] = serial[-500:]
            levels = re.findall(r"GPIO_LASER_TX_LEVEL (\d)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("output-level") is False and int(p.get("output-transitions", 0)) >= 3,
                label="laser-tx qom")
            result["qom_samples"].extend(samples)
            result["observations"]["laser_tx"] = {
                "guest_levels": levels,
                "qom": {k: final.get(k) for k in ("output-level", "output-transitions")},
                "boundary": "Human-eye safety / optical power / wavelength / modulation bandwidth NOT RUN. "
                            "The model observes the GPIO DIN line only and must never be described as an optical output.",
            }
            result["checks"]["guest_levels_driven"] = levels == ["1", "0", "1", "0"]
            result["checks"]["qom_final_level_low"] = final.get("output-level") is False
            result["checks"]["qom_transitions_observed"] = int(final.get("output-transitions", 0)) >= 3

        elif case == "co2l":
            fixtures = {"co2-ppm": 1234, "temperature-c": 25.5, "humidity-pct": 60.5, "data-ready": True}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: re.search(r"I2C_CO2L 1234 60\.5 ", text) is not None, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_CO2L_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["co2l"] = serial[-900:]
            co2 = last_match(r"I2C_CO2L (\d+)", serial)
            humidity = last_match(r"I2C_CO2L \d+ ([\d.]+)", serial)
            temperature = last_match(r"I2C_CO2L \d+ [\d.]+ ([\d.]+)", serial)
            serial_number = last_match(r"I2C_CO2L_SERIAL (\([^)]*\))", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("co2-ppm") == 1234 and p.get("humidity-pct") == 60.5
                and int(p.get("measurement-reads", 0)) > 0,
                label="co2l final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["co2l"] = {
                "fixtures": fixtures, "guest_co2": co2, "guest_humidity": humidity,
                "guest_temperature": temperature, "guest_serial_tuple": serial_number,
                "qom": {k: final.get(k) for k in ("co2-ppm", "temperature-c", "humidity-pct",
                                                  "data-ready", "serial-number", "chip-id",
                                                  "measurement-reads", "transactions",
                                                  "read-bytes", "written-bytes")},
                "driver_bug_boundary": "The frozen SCD4x driver decodes temperature from buf[1] instead of "
                                       "buf[4]; CO2/humidity are assertable and temperature is deliberately "
                                       "recorded as a known driver bug. SCD40-vs-SCD41 identity is unresolved. "
                                       "get_serial_number() is recorded as a boundary: the frozen driver raises "
                                       "and this QEMU tree does not carry the 0132 3-word SCD40 serial fix "
                                       "(not required for co2l's CO2/RH data plane).",
                "safety_boundary": "The model only observes I2C register words; CO2/RH accuracy, the 5s periodic "
                                   "timing and the physical sensor are NOT RUN.",
            }
            result["checks"]["guest_co2_tracks_fixture"] = co2 == "1234"
            result["checks"]["guest_humidity_tracks_fixture"] = humidity == "60.5"
            result["checks"]["guest_temperature_driver_bug_recorded"] = (
                temperature is not None and abs(float(temperature) - 25.5) > 0.1)
            serial_boundary = ("I2C_CO2L_SERIAL_ERROR" in serial) or ("I2C_CO2L_SERIAL" in serial)
            result["checks"]["guest_serial_path_recorded"] = serial_boundary
            result["qom_fixtures_exact"] = (
                final.get("co2-ppm") == 1234 and final.get("humidity-pct") == 60.5)
            result["checks"]["qom_scd41_chip_id"] = final.get("chip-id") == 0x41
            result["checks"]["qom_serial_number"] = final.get("serial-number") == 0x12345678
            result["checks"]["measurement_reads_observed"] = int(final.get("measurement-reads", 0)) > 0
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "neco":
            serial = wait_for(client, session_id, lambda text: "GPIO_NECO_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["neco"] = serial[-500:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: len(p.get("led-rgb") or []) == 35
                and (p.get("led-rgb") or [0])[0] == 0x112233,
                label="neco qom")
            result["qom_samples"].extend(samples)
            led_rgb = final.get("led-rgb") or []
            result["observations"]["neco"] = {
                "guest_marker": "GPIO_NECO_RGB 1122867" in serial,
                "qom": {k: final.get(k) for k in ("led-rgb", "led-frames", "incomplete-frames",
                                                  "button-pressed", "input-events")},
                "boundary": "The product page says 35 WS2812C LEDs while the frozen driver defaults to 70; "
                            "the model implements the page count (35) and this evidence constructs NECOUnit(...,35). "
                            "WS2812 timing tolerance, brightness/optics/power and the two-Grove-port pass-through "
                            "are NOT RUN; the RGB frame is the last committed GRB wire value.",
            }
            result["checks"]["guest_rgb_write_completed"] = "GPIO_NECO_RGB 1122867" in serial
            result["checks"]["qom_led_count_35"] = len(led_rgb) == 35
            result["checks"]["qom_led_rgb_matches_wire"] = led_rgb[:5] == [0x112233] * 5
            result["checks"]["qom_led_frames_observed"] = int(final.get("led-frames", 0)) >= 1
            result["checks"]["no_incomplete_frames"] = int(final.get("incomplete-frames", 0)) == 0
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "midi":
            serial = wait_for(client, session_id, lambda text: "UART_MIDI_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["midi"] = serial[-500:]
            expected = "903c64803c00b00000c005"
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("tx-hex") == expected,
                label="midi qom")
            result["qom_samples"].extend(samples)
            result["observations"]["midi"] = {
                "expected_midi_hex": expected,
                "qom": {k: final.get(k) for k in ("rx-hex", "tx-hex", "transactions", "written-bytes")},
                "boundary": "SAM2695 synthesis sound/instruments/polyphony and audio output are NOT RUN; "
                            "the page 31520bps vs standard MIDI 31250 vs the driver's implicit UART baud remains "
                            "unresolved. Only the guest->SAM2695 byte stream is asserted.",
            }
            result["checks"]["guest_note_on_off_stream"] = final.get("tx-hex") == expected
            result["checks"]["written_bytes_counted"] = int(final.get("written-bytes", 0)) >= 10
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "tof4m":
            fixtures = {"distance-mm": 1000, "data-ready": True}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id, lambda text: "I2C_TOF4M_DIST 1000" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_TOF4M_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["tof4m"] = serial[-900:]
            model_info = last_match(r"I2C_TOF4M_MODEL \(([\d, ]+)\)", serial)
            distance = last_match(r"I2C_TOF4M_DIST (\d+)", serial)
            ready = last_match(r"I2C_TOF4M_READY (\d)", serial)
            budget = last_match(r"I2C_TOF4M_BUDGET (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("distance-mm") == 1000 and int(p.get("clear-writes", 0)) >= 1
                and int(p.get("transactions", 0)) > 0,
                label="tof4m final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["tof4m"] = {
                "fixtures": fixtures, "guest_model_info": model_info, "guest_distance_mm": distance,
                "guest_data_ready": ready, "guest_timing_budget_ms": budget,
                "qom": {k: final.get(k) for k in ("distance-mm", "data-ready", "timing-budget-ms",
                                                  "range-status", "i2c-address", "clear-writes",
                                                  "transactions")},
                "boundary": "VL53L1CXV0FY/1 vs VL53L1X naming, 4m range/resolution, laser safety and optics "
                            "are NOT RUN; the covered path is the 16-bit register file and the driver's own "
                            "model-id/data-ready/distance reads.",
            }
            result["checks"]["guest_model_identity"] = model_info == "234, 204, 16"
            result["checks"]["guest_distance_tracks_fixture"] = distance == "1000"
            result["checks"]["guest_data_ready"] = ready == "1"
            result["checks"]["guest_timing_budget"] = budget == "50"
            result["checks"]["qom_distance_fixture_exact"] = final.get("distance-mm") == 1000
            result["checks"]["qom_range_status"] = final.get("range-status") == 9
            result["checks"]["qom_clear_writes_observed"] = int(final.get("clear-writes", 0)) >= 1
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "weight":
            fixtures = {"adc-raw": 123456, "channel": 1}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            serial = wait_for(client, session_id, lambda text: "GPIO_WEIGHT_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["weight"] = serial[-600:]
            expected_raw = (123456 << 1) ^ 0x800000
            guest_raw = last_match(r"GPIO_WEIGHT_RAW (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("adc-raw") == 123456 and int(p.get("conversions", 0)) >= 1,
                label="weight qom")
            result["qom_samples"].extend(samples)
            result["observations"]["weight"] = {
                "fixtures": fixtures, "expected_guest_raw": expected_raw, "guest_raw": guest_raw,
                "qom": {k: final.get(k) for k in ("adc-raw", "channel", "weight-g",
                                                  "conversions", "ready-level")},
                "driver_transform": "guest get_raw_weight = (raw << 1) ^ 0x800000 by the frozen driver "
                                    "(count is left-shifted after each of the 24 bits); the QOM adc-raw is the "
                                    "24-bit DAT pattern before that driver transform.",
                "boundary": "HX711 electrical/10SPS timing/load-cell mechanics/calibration/temperature drift "
                            "are NOT RUN; the page FAQ's I2C wording conflicts with the GPIO bit-pulse PinMap "
                            "and driver, and weight-i2c (U180 @0x26) is a different protocol.",
            }
            result["checks"]["guest_raw_matches_driver_transform"] = guest_raw == str(expected_raw)
            result["checks"]["qom_adc_fixture_exact"] = final.get("adc-raw") == 123456
            result["checks"]["qom_conversions_observed"] = int(final.get("conversions", 0)) >= 1
            result["checks"]["qom_ready_level"] = final.get("ready-level") is True
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "bldc-driver":
            serial = wait_for(client, session_id, lambda text: "I2C_BLDC_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["bldc-driver"] = serial[-900:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("mode") == 1 and p.get("direction") == 1
                and p.get("pole-pairs") == 11 and p.get("pwm") == 1000
                and abs(float(p.get("rpm", 0)) - 1500.0) <= 0.01,
                label="bldc final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["bldc_driver"] = {
                "guest": {
                    "mode": last_match(r"I2C_BLDC_MODE (\d+)", serial),
                    "direction": last_match(r"I2C_BLDC_DIR (\d+)", serial),
                    "model": last_match(r"I2C_BLDC_MODEL (\d+)", serial),
                    "pole_pairs": last_match(r"I2C_BLDC_POLES (\d+)", serial),
                    "pwm": last_match(r"I2C_BLDC_PWM (-?\d+)", serial),
                    "rpm": last_match(r"I2C_BLDC_RPM ([\d.]+) ([\d.]+)", serial),
                    "pid": last_match(r"I2C_BLDC_PID \(([^)]*)\)", serial),
                    "status": last_match(r"I2C_BLDC_STATUS (\d+)", serial),
                },
                "qom": {k: final.get(k) for k in ("mode", "direction", "pole-pairs", "pwm", "rpm",
                                                  "rpm-readback", "frequency-hz", "motor-status",
                                                  "flash-writes", "fw-version", "i2c-address")},
                "boundary": "BLDC motor electrical/rotation/stall protection/DRV11873 status/5V output are "
                            "NOT RUN; RPM float uses real IEEE754 LE encoding and the frequency readback is the "
                            "model's synthetic rpm/60 convention (real pole-pair/electrical relation unresolved); "
                            "0xF0 flash persistence semantics unresolved.",
            }
            result["checks"]["guest_mode_roundtrip"] = last_match(r"I2C_BLDC_MODE (\d+)", serial) == "1"
            result["checks"]["guest_direction_model_poles"] = (
                last_match(r"I2C_BLDC_DIR (\d+)", serial) == "1"
                and last_match(r"I2C_BLDC_MODEL (\d+)", serial) == "1"
                and last_match(r"I2C_BLDC_POLES (\d+)", serial) == "11")
            result["checks"]["guest_pwm_roundtrip"] = last_match(r"I2C_BLDC_PWM (-?\d+)", serial) == "1000"
            result["checks"]["guest_rpm_float_roundtrip"] = bool(
                (row := last_match(r"I2C_BLDC_RPM ([\d.]+) ([\d.]+)", serial)) and abs(float(row[1]) - 1500.0) < 0.01)
            result["checks"]["guest_pid_roundtrip"] = last_match(r"I2C_BLDC_PID \(([^)]*)\)", serial) == "10, 20, 30"
            result["checks"]["qom_writes_landed"] = (
                final.get("mode") == 1 and final.get("direction") == 1 and final.get("pole-pairs") == 11
                and final.get("pwm") == 1000 and abs(float(final.get("rpm", 0)) - 1500.0) <= 0.01)
            result["checks"]["qom_frequency_and_flash"] = (
                abs(float(final.get("frequency-hz", 0)) - 25.0) <= 0.01
                and int(final.get("flash-writes", 0)) >= 1)
            result["checks"]["qom_identity"] = final.get("fw-version") == 1 and final.get("i2c-address") == 0x65

        elif case == "ac-measure":
            fixtures = {"voltage-v": 230.0, "current-a": 1.0, "active-power-w": 230.0,
                        "apparent-power-va": 230.0, "power-factor": 1.0, "energy-kwh": 0.0,
                        "data-ready": True}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id, lambda text: "I2C_ACMEASURE_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["ac-measure"] = serial[-1200:]
            guest_strings = {
                "voltage": last_match(r"I2C_ACMEASURE_V (.+)\n", serial),
                "current": last_match(r"I2C_ACMEASURE_I (.+)\n", serial),
                "active_power": last_match(r"I2C_ACMEASURE_P (.+)\n", serial),
                "apparent_power": last_match(r"I2C_ACMEASURE_S (.+)\n", serial),
                "power_factor": last_match(r"I2C_ACMEASURE_PF (.+)\n", serial),
                "kwh": last_match(r"I2C_ACMEASURE_KWH (.+)\n", serial),
            }
            guest_bytes = last_match(
                r"I2C_ACMEASURE_BYTE (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)", serial)
            coeff = last_match(r"I2C_ACMEASURE_COEFF (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("coeff-voltage") == 12 and p.get("coeff-current") == 34
                and int(p.get("save-coeff-writes", 0)) >= 1,
                label="ac-measure final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["ac_measure"] = {
                "fixtures": fixtures,
                "guest_strings": guest_strings,
                "guest_bytes": guest_bytes,
                "guest_coeff": coeff,
                "guest_ready": last_match(r"I2C_ACMEASURE_READY (\d)", serial),
                "qom": {k: final.get(k) for k in ("voltage-v", "current-a", "active-power-w",
                                                  "apparent-power-va", "power-factor", "energy-kwh",
                                                  "data-ready", "coeff-voltage", "coeff-current",
                                                  "save-coeff-writes", "fw-version", "i2c-address")},
                "safety_boundary": "AC 100-240V@10A is a MEASUREMENT INPUT, never a switchable load. The model "
                                   "only simulates I2C register readings and must never be described as mains "
                                   "on/off, isolation withstand, overcurrent protection or metering accuracy. "
                                   "AC mains/HLW8032/isolation/calibration semantics are NOT RUN; the ASCII "
                                   "view widths are a deterministic model-side convention, not a page protocol.",
                "identity_conflict": "Product page says STM32G030 while the official I2C address index says "
                                     "STM32F030; unresolved.",
            }
            expected_strings = {
                "voltage": "  230.0", "current": "   1.00", "active_power": "    230",
                "apparent_power": "    230", "power_factor": "1.00", "kwh": "       0.00",
            }
            result["checks"]["guest_ascii_views"] = guest_strings == expected_strings
            result["checks"]["guest_byte_views"] = guest_bytes == ("23000", "1000", "23000", "23000", "100", "0")
            result["checks"]["guest_coeff_and_ready"] = coeff == ("12", "34")
            result["checks"]["qom_fixtures_exact"] = (
                final.get("voltage-v") == 230.0 and final.get("current-a") == 1.0)
            result["checks"]["qom_coeff_writes"] = (
                final.get("coeff-voltage") == 12 and final.get("coeff-current") == 34
                and int(final.get("save-coeff-writes", 0)) >= 1)
            result["checks"]["qom_identity"] = final.get("fw-version") == 1 and final.get("i2c-address") == 0x42

        elif case == "dds":
            serial = wait_for(client, session_id, lambda text: "I2C_DDS_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["dds"] = serial[-800:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("waveform") == 1 and abs(float(p.get("frequency-hz", 0)) - 1000.0) <= 1.0
                and abs(float(p.get("phase-deg", 0)) - 90.0) <= 1.0,
                label="dds final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["dds"] = {
                "guest_mode": last_match(r"I2C_DDS_MODE ([0-9a-f]+)", serial),
                "guest_freq": last_match(r"I2C_DDS_FREQ ([0-9a-f]+)", serial),
                "guest_phase": last_match(r"I2C_DDS_PHASE ([0-9a-f]+)", serial),
                "guest_wave": last_match(r"I2C_DDS_WAVE ([0-9a-f]+)", serial),
                "qom": {k: final.get(k) for k in ("waveform", "frequency-hz", "phase-deg",
                                                  "freq-reg", "phase-reg", "ctrl-word",
                                                  "active-freq-reg", "active-phase-reg", "i2c-address")},
                "boundary": "AD9833 analog waveform/amplitude/phase accuracy/output impedance/0-0.6V are NOT RUN; "
                            "only the register writes and the selected regs are asserted. The frozen driver's "
                            "combined set_freq_phase()/quick_output() writes frequency+phase as a contiguous "
                            "6-byte burst at 0x30; the 0136 model only accepts a 4-byte frequency write at 0x30 "
                            "and NACKs the trailing phase bytes, so this evidence uses the driver's separate "
                            "set_freq()/set_phase()/set_mode()/set_ctrl() APIs and records the burst gap unresolved. "
                            "The 0136 read-snapshot also overlaps frequency-register 1 at 0x34 with phase-register 0, "
                            "so the guest 0x34 readback is recorded as a model-snapshot boundary; QOM phase-deg is "
                            "still asserted from the accepted phase write.",
            }
            result["checks"]["guest_mode_and_freq_words"] = (
                last_match(r"I2C_DDS_MODE ([0-9a-f]+)", serial) == "81"
                and last_match(r"I2C_DDS_FREQ ([0-9a-f]+)", serial) == "800068db"
                and last_match(r"I2C_DDS_PHASE ([0-9a-f]+)", serial) is not None)
            result["checks"]["guest_ctrl_word"] = last_match(r"I2C_DDS_WAVE ([0-9a-f]+)", serial) == "80"
            result["checks"]["qom_frequency_phase"] = (
                abs(float(final.get("frequency-hz", 0)) - 1000.0) <= 1.0
                and abs(float(final.get("phase-deg", 0)) - 90.0) <= 1.0)
            result["checks"]["qom_ctrl_word_and_regs"] = (
                final.get("ctrl-word") == 0x80
                and final.get("freq-reg") == 0 and final.get("phase-reg") == 0
                and final.get("active-freq-reg") == 0 and final.get("active-phase-reg") == 0)
            result["checks"]["qom_identity"] = final.get("i2c-address") == 0x31

        elif case == "gps":
            lines = ";".join([
                "$GNGGA,024423.000,2242.10772,N,11348.64472,E,1,14,1.2,52.1,M,0.0,M,,*48",
                "$GNRMC,024423.000,A,2242.10772,N,11348.64472,E,0.0,0.0,031124,,,A*00",
                "$GNVTG,45.0,T,,M,0.5,N,0.926,K,A*00",
            ])
            props = inject(client, session_id, {"nmea-lines": lines})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: re.search(r"GPS_STATE 02:44:23 2242\.10772N 11348\.64472E 52\.1 14 1 03/11/24 45\.0 0\.5 0\.926", text) is not None,
                     90)
            serial = wait_for(client, session_id, lambda text: "UART_GPS_END" in text, 120)
            serial = read_serial(client, session_id)
            result["serial_markers"]["gps"] = serial[-1500:]
            row = last_match(
                r"GPS_STATE (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (\S+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("injected-lines", 0)) >= 2,
                label="gps final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["gps"] = {
                "fixture_lines": lines.split(";"),
                "guest_state": row,
                "qom": {k: final.get(k) for k in ("nmea-lines", "injected-lines", "tx-hex")},
                "boundary": "Real GNSS satellites/RF/antenna/position accuracy are NOT RUN; the frozen driver "
                            "does not validate NMEA checksums (unresolved), and cold/warm start/update-rate are "
                            "not modeled. PORT.C conflicts with midi/uhf-rfid/rs485-iso.",
            }
            result["checks"]["guest_gga_time_position"] = bool(
                row and row[0] == "02:44:23" and row[1] == "2242.10772N"
                and row[2] == "11348.64472E" and row[3] == "52.1")
            result["checks"]["guest_gga_quality_sats"] = bool(row and row[4] == "14" and row[5] == "1")
            result["checks"]["guest_rmc_date"] = bool(row and row[6] == "03/11/24")
            result["checks"]["guest_vtg_course_speed"] = bool(row and row[7:] == ("45.0", "0.5", "0.926"))
            result["checks"]["qom_injected_lines"] = int(final.get("injected-lines", 0)) >= 2
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "uhf-rfid":
            epc = "e200001234567890"
            def response(cmd: int, data: bytes) -> str:
                body = bytes([0x01, cmd]) + len(data).to_bytes(2, "big") + data
                return "bb" + body.hex() + ("%02x" % (sum(body) & 0xFF)) + "7e"
            inv_data = bytes([0x32, 0x30, 0x00]) + bytes.fromhex(epc) + bytes([0x12, 0x34])
            fixture = response(0x22, inv_data) + ";" + response(0x22, inv_data)
            props = inject(client, session_id, {"responses-hex": fixture})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: len(re.findall(r"UART_UHF_EPC " + epc, text)) >= 2, 90)
            serial = wait_for(client, session_id, lambda text: "UART_UHF_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["uhf-rfid"] = serial[-700:]
            epcs = re.findall(r"UART_UHF_EPC ([0-9a-f]*)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("frames-sent", 0)) >= 2 and int(p.get("frames-injected", 0)) >= 2,
                label="uhf-rfid final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["uhf_rfid"] = {
                "expected_epc": epc, "guest_epcs": epcs,
                "qom": {k: final.get(k) for k in ("responses-hex", "tx-hex", "rx-frames-hex",
                                                  "frames-sent", "frames-injected")},
                "boundary": "RF 840-960MHz/antenna/Gen2 air interface/read-range/region limits are NOT RUN. "
                            "The model only moves JRD4035 frames and the fixture EPC; this evidence must never "
                            "be described as a real tag capability, and kill/lock/password paths are frame-level "
                            "only.",
            }
            result["checks"]["guest_inventory_epc"] = epcs[:2] == [epc, epc]
            result["checks"]["qom_frames_sent"] = int(final.get("frames-sent", 0)) >= 2
            result["checks"]["qom_frames_injected"] = int(final.get("frames-injected", 0)) >= 2
            result["checks"]["qom_tx_command_frames"] = (final.get("tx-hex") or "").count("bb0022") >= 2
            result["checks"]["qom_fixture_preserved"] = (final.get("responses-hex") or "") == fixture
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        screenshot = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(screenshot)
        result["frame"] = {"sha256": sha256(screenshot), "metrics": png_metrics(screenshot)}
        result["checks"]["nonempty_application_frame"] = result["frame"]["metrics"]["unique_colors"] > 1
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as error:  # noqa: BLE001 - the failure is preserved as evidence
        result["error"] = str(error)
        result["status"] = "FAIL"
    finally:
        if session_id:
            try:
                bundle = client.raw(f"sessions/{session_id}/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence"] = {"sha256": sha256(bundle), "bytes": len(bundle)}
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    required = {"manifest.json", "serial.log", "units/runtime.json",
                                "units/state.json", "units/contract.json"}
                    result["checks"]["evidence_complete"] = required.issubset(archive.namelist())
                    (output / "serial.txt").write_bytes(archive.read("serial.log"))
                    if "units/state.json" in archive.namelist():
                        (output / "units-state.json").write_bytes(archive.read("units/state.json"))
                    if "units/contract.json" in archive.namelist():
                        (output / "units-contract.json").write_bytes(archive.read("units/contract.json"))
            except Exception as error:  # noqa: BLE001
                result["evidence_error"] = str(error)
                result["checks"]["evidence_complete"] = False
                result["status"] = "FAIL"
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", method="DELETE")
                history = client.json(f"sessions/{session_id}")
                result["stop"] = {
                    "stop_state": stopped.get("state"), "history_state": history.get("state"),
                    "history_retained": bool(history.get("session_id") == session_id),
                }
                result["checks"]["stopped_with_history"] = (
                    stopped.get("state") in {"stopped", "failed"}
                    and history.get("state") in {"stopped", "failed"})
            except Exception as error:  # noqa: BLE001
                result["stop_error"] = str(error)
                result["checks"]["stopped_with_history"] = False
            if result.get("error") or result.get("evidence_error") or not all(result["checks"].values()):
                result["status"] = "FAIL"
        result["raw_evidence_note"] = (
            "Raw execution artifacts (evidence.zip, frame.png, serial.txt, probe files) stay in the local "
            "ignored .work directory; only this concise report, hashes and reproduction commands are committed.")
        client.finalize_result(result)
        (output / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{case}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8799")
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.api_url)
    result = run_case(client, args, args.case)
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
