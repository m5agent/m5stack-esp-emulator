#!/usr/bin/env python3
"""Validate the twelve Units of the third research batch.

Two separate QEMU builds are required because the merged 0130 (A+B) and 0131
(C) patches are parallel layers: A+B sessions run on the 0130+0133 binary and
C sessions on the 0131+0132 binary. Each case builds a merged reference-firmware
image that runs the firmware's frozen original UIFlow2 driver, creates one
visible leased `/api/v1` session, injects external fixtures through
`unit-input`, reads controller-backed QOM state, captures serial markers, the
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

MARKER = "BATCH3_PROBE_READY"
CASES = {
    "rfid": "cores3", "tube-pressure": "atoms3r", "laser-rx": "atoms3r",
    "extio": "sticks3", "dac2": "cores3", "scales": "sticks3",
    "vmeter": "cores3", "adc": "stopwatch",
    "env-iv": "atoms3r", "co2": "sticks3", "pbhub": "cores3",
    "ultrasonic-io": "stopwatch",
}
AB_CASES = ("rfid", "tube-pressure", "laser-rx", "extio", "dac2", "scales", "vmeter", "adc")
C_CASES = ("env-iv", "co2", "pbhub", "ultrasonic-io")
CASE_DRIVERS = {
    "rfid": "RFIDUnit(MFRC522)", "tube-pressure": "TubePressureUnit",
    "laser-rx": "LaserRXUnit", "extio": "EXTIOUnit(PCA9554)",
    "dac2": "DAC2Unit(GP8413)", "scales": "ScalesUnit",
    "vmeter": "VoltmeterUnit(ADS1115)", "adc": "ADCUnit(ADS1100)",
    "env-iv": "ENVUnit(ENV_IV: SHT40+BMP280)", "co2": "CO2Unit(SCD40)",
    "pbhub": "PBHUBUnit", "ultrasonic-io": "ULTRASONIC_IOUnit",
}
BINARIES = {
    "ab": ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa",
    "c": ROOT / ".work/M5StopWatch-QEMU-c/build/qemu/build/qemu-system-xtensa",
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


def select_port(client: Client, device_id: str, unit_id: str) -> dict:
    registry = client.json(f"units?device_id={device_id}")
    host = registry["hosts"][0]
    unit_rows = {row["id"]: row for row in registry["units"]}
    admission = unit_rows[unit_id]["host_admission"]
    if not admission["admitted"]:
        raise RuntimeError(f"{unit_id} is not admitted on {device_id}: {admission}")
    port = next(port for port in host["ports"] if port.get("visual_port") == "grove")
    if port["id"] not in admission["port_ids"]:
        raise RuntimeError(f"{unit_id} admission does not include {port['id']}")
    return port


def expected_adc16(voltage_mv: float) -> int:
    sample = round(voltage_mv * 4095.0 / 3100.0)
    sample = min(4095, sample)
    return round(sample * 65535.0 / 4095.0)


def run_case(client: Client, args, case: str) -> dict:
    device = CASES[case]
    batch = "ab" if case in AB_CASES else "c"
    runtime_qemu = BINARIES[batch]
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device_row = next(row for row in matrix["devices"] if row["id"] == device)
    port = select_port(client, device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch3_probe", files, dirs_exist_ok=True)
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
        "device_id": device, "unit_id": case, "batch": "A+B" if batch == "ab" else "C",
        "driver_class": CASE_DRIVERS[case],
        "driver_flavor": "reference-firmware-frozen-original-unit-driver",
        "runtime": "qemu", "status": "FAIL", "checks": {},
        "firmware_sha256": sha256(firmware_bytes),
        "probe_sha256": {path.name: sha256(path.read_bytes()) for path in files.glob("*.py")},
        "runtime_binary_sha256": sha256(runtime_qemu.read_bytes()) if runtime_qemu.is_file() else None,
        "port": {"id": port["id"], "pins": port["pins"]},
        "qom_samples": [], "serial_markers": {},
    }
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{device}-batch3-{case}.bin",
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
        print(f"{case}: visible session created on {device}/{port['id']} ({batch} binary)", flush=True)
        serial = wait_for(client, session_id, lambda text: MARKER in text, 150)
        result["checks"]["official_driver_ready"] = True
        result["serial_markers"]["ready"] = serial[serial.index(MARKER):serial.index(MARKER) + len(MARKER)]
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        attached = (live.get("units") or [{}])[0]
        result["attached_unit"] = {key: attached.get(key) for key in ("id", "unit_id", "available", "source")}

        if case == "rfid":
            props = inject(client, session_id, {"card-present": True})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: re.search(r"I2C_RFID 1 [0-9a-f]{8}", text) is not None, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_RFID_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["rfid"] = serial[-500:]
            guest = last_match(r"I2C_RFID (\d) ([0-9a-f]*)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("card-present") is True and p.get("selected") is True,
                label="rfid qom")
            result["qom_samples"].extend(samples)
            result["rfid"] = {"guest": guest,
                              "qom": {k: final.get(k) for k in ("card-present", "uid-hex", "selected",
                                                                "card-reads", "card-writes", "transactions",
                                                                "read-bytes", "written-bytes",
                                                                "i2c-address")}}
            result["checks"]["guest_card_and_uid"] = bool(
                guest and guest[0] == "1" and guest[1].startswith("04010203"))
            result["checks"]["qom_card_present_and_selected"] = (
                final.get("card-present") is True and final.get("selected") is True)
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0
            result["checks"]["i2c_address_0x28"] = final.get("i2c-address") == 0x28

        elif case == "tube-pressure":
            voltage_mv = 1600.0
            props = inject(client, session_id, {"analog-mv": voltage_mv})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            expected16 = expected_adc16(voltage_mv)
            expected12 = min(4095, round(voltage_mv * 4095.0 / 3100.0))
            wait_for(client, session_id,
                     lambda text: ((row := last_match(r"ADC_TUBE_RAW (\d+) (\d+)", text)) is not None
                                   and abs(int(row[0]) - expected16) <= 2
                                   and int(row[1]) == expected12), 60)
            serial = wait_for(client, session_id, lambda text: "ADC_TUBE_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["tube"] = serial[-700:]
            guest = last_match(r"ADC_TUBE_RAW (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("analog-mv") == voltage_mv and int(p.get("adc-samples", 0)) > 0,
                label="tube qom")
            result["qom_samples"].extend(samples)
            result["tube_pressure"] = {
                "voltage_mv": voltage_mv, "expected_adc16": expected16, "expected_adc12": expected12,
                "guest_raw": guest,
                "pressure_voltage_unsupported": "ADC_TUBE_PRESSURE_UNSUPPORTED" in serial
                and "ADC_TUBE_VOLTAGE_UNSUPPORTED" in serial,
                "qom": {k: final.get(k) for k in ("analog-mv", "adc-samples", "pressure-kpa",
                                                  "transactions", "read-bytes", "written-bytes")},
                "boundary": "read_uv()/get_pressure()/get_voltage() need the S3 ADC calibration fixture and are "
                            "NOT RUN; the covered path is read_u16()/read()/get_analog_value().",
            }
            result["checks"]["guest_raw_tracks_adc_fixture"] = bool(
                guest and abs(int(guest[0]) - expected16) <= 2 and int(guest[1]) == expected12)
            result["checks"]["qom_analog_fixture_exact"] = final.get("analog-mv") == voltage_mv
            result["checks"]["adc_samples_observed"] = int(final.get("adc-samples", 0)) > 0
            result["checks"]["voltage_path_reported_unsupported"] = result["tube_pressure"]["pressure_voltage_unsupported"]
            result["checks"]["no_i2c_transactions_fabricated"] = all(
                int(final.get(key, 0)) == 0 for key in ("transactions", "read-bytes", "written-bytes"))

        elif case == "laser-rx":
            inject(client, session_id, {"digital-level": False})
            wait_for(client, session_id, lambda text: "GPIO_LASER 0" in text, 60)
            inject(client, session_id, {"digital-level": True})
            wait_for(client, session_id,
                     lambda text: text.find("GPIO_LASER 1", text.find("GPIO_LASER 0")) >= 0, 60)
            serial = wait_for(client, session_id, lambda text: "GPIO_LASER_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["laser"] = serial[-400:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("input-events", 0)) >= 2 and p.get("digital-level") is True,
                label="laser qom")
            result["qom_samples"].extend(samples)
            levels = re.findall(r"GPIO_LASER (\d)", serial)
            zero = levels.index("0") if "0" in levels else -1
            result["laser_rx"] = {"guest_levels": levels,
                                  "qom": {k: final.get(k) for k in ("digital-level",
                                                                    "input-events", "transactions")}}
            result["checks"]["guest_level_tracks_fixture"] = zero >= 0 and "1" in levels[zero + 1:]
            result["checks"]["input_events_counted"] = int(final.get("input-events", 0)) >= 2
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "extio":
            levels = [True, False, True, False, True, False, True, False]
            inject(client, session_id, {"input-levels": levels})
            wait_for(client, session_id, lambda text: "I2C_EXTIO_READ 85" in text, 40)
            serial = wait_for(client, session_id, lambda text: "I2C_EXTIO_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["extio"] = serial[-500:]
            reads = re.findall(r"I2C_EXTIO_READ (\d+)", serial)
            readback = last_match(r"I2C_EXTIO_READBACK (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("config") == 0xFF and p.get("polarity") == 0
                and int(p.get("transactions", 0)) > 0,
                label="extio final qom")
            result["qom_samples"].extend(samples)
            result["extio"] = {"guest_reads": reads, "guest_readback": readback,
                               "qom": {k: final.get(k) for k in ("input-levels", "output-levels",
                                                                 "polarity", "config", "i2c-address",
                                                                 "transactions")}}
            result["checks"]["input_fixture_read"] = reads[:1] == ["85"]
            result["checks"]["output_latch_roundtrip"] = readback == "165"
            result["checks"]["outputs_returned_to_zero"] = final.get("output-levels") == [False] * 8
            result["checks"]["config_and_polarity_observed"] = final.get("config") == 0xFF and final.get("polarity") == 0
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0
            result["checks"]["i2c_address_0x27"] = final.get("i2c-address") == 0x27

        elif case == "dac2":
            serial = wait_for(client, session_id, lambda text: "I2C_DAC2_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["dac2"] = serial[-500:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("range") == 1 and p.get("dac-0-raw") == 0xFFFF and p.get("dac-1-raw") == 0xFFFF,
                label="dac2 final qom")
            result["qom_samples"].extend(samples)
            result["dac2"] = {"guest_markers": {m: (m in serial) for m in (
                "I2C_DAC2_CH1", "I2C_DAC2_CH0", "I2C_DAC2_BOTH", "I2C_DAC2_RANGE1")},
                "qom": {k: final.get(k) for k in ("range", "dac-0-raw", "dac-1-raw",
                                                  "voltage-0-v", "voltage-1-v",
                                                  "i2c-address", "transactions")},
                "driver_note": "The frozen driver's channel constants are tuples while set_voltage() "
                               "compares with ==; callers must pass unit.CHANNEL_* (a plain 0/1/2 "
                               "silently does nothing). The evidence uses the driver's constants."}
            result["checks"]["guest_write_paths_completed"] = all(result["dac2"]["guest_markers"].values())
            result["checks"]["both_channels_16bit_full_scale"] = (
                final.get("dac-0-raw") == 0xFFFF and final.get("dac-1-raw") == 0xFFFF)
            result["checks"]["range_switched_to_10v"] = final.get("range") == 1
            result["checks"]["voltage_follows_range"] = (
                isinstance(final.get("voltage-0-v"), (int, float))
                and abs(final["voltage-0-v"] - 10.0) <= 0.01
                and abs(final["voltage-1-v"] - 10.0) <= 0.01)
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "scales":
            fixtures = {"weight-g": 543.21, "adc-raw": 123456, "button-status": 2}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id, lambda text: "I2C_SCALES 123456 543" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_SCALES_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["scales"] = serial[-700:]
            guest = last_match(r"I2C_SCALES (\d+) (\d+)", serial)
            rgb_guest = last_match(r"I2C_SCALES_RGB \[(\d+), (\d+), (\d+)\]", serial)
            sync = last_match(r"I2C_SCALES_SYNC (\d+)", serial)
            fw = last_match(r"I2C_SCALES_FW (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("led-rgb") == 0x112233 and int(p.get("calibration-writes", 0)) >= 2
                and p.get("fw-version") == 2,
                label="scales final qom")
            result["qom_samples"].extend(samples)
            result["scales"] = {"fixtures": fixtures, "guest": guest, "guest_rgb": rgb_guest,
                                "guest_sync": sync, "guest_fw": fw,
                                "qom": {k: final.get(k) for k in ("weight-g", "adc-raw", "button-status",
                                                                  "offset-adc", "led-rgb", "led-sync",
                                                                  "calibration-writes", "fw-version",
                                                                  "i2c-address", "transactions")}}
            result["checks"]["guest_raw_and_weight_registers"] = guest == ("123456", "543")
            result["checks"]["guest_rgb_roundtrip"] = rgb_guest == ("17", "34", "51")
            result["checks"]["guest_sync_and_fw"] = sync == "1" and fw == "2"
            result["checks"]["qom_fixtures_exact"] = (
                final.get("weight-g") == 543.21 and final.get("adc-raw") == 123456
                and final.get("button-status") == 2)
            result["checks"]["qom_led_and_calibration"] = (
                final.get("led-rgb") == 0x112233 and final.get("led-sync") == 1
                and int(final.get("calibration-writes", 0)) >= 2)
            result["checks"]["qom_offset_written"] = final.get("offset-adc") == 123
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "vmeter":
            fixtures = {"voltage-v": 12.0}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: ((row := last_match(r"I2C_VMETER (-?[\d.]+) (-?\d+) (\d+) (\d+)", text))
                                   is not None and abs(float(row[0]) - 11.78) <= 0.05
                                   and int(row[1]) == -3), 60)
            serial = wait_for(client, session_id, lambda text: "I2C_VMETER_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["vmeter"] = serial[-700:]
            guest = last_match(r"I2C_VMETER (-?[\d.]+) (-?\d+) (\d+) (\d+)", serial)
            config = last_match(r"I2C_VMETER_CONFIG (\d+) (\d+) (\d+)", serial)
            rejected = "I2C_VMETER_EEPROM_WRITE_REJECTED" in serial
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("eeprom-writes", 0)) >= 1 and p.get("config-word") == 0x8B80,
                label="vmeter final qom")
            result["qom_samples"].extend(samples)
            result["vmeter"] = {"fixtures": fixtures, "guest": guest, "guest_config": config,
                                "eeprom_write_rejected": rejected,
                                "qom": {k: final.get(k) for k in ("voltage-v", "adc-raw", "config-word",
                                                                  "eeprom-writes", "i2c-address",
                                                                  "transactions")}}
            result["checks"]["guest_voltage_follows_driver_quantization"] = bool(
                guest and abs(float(guest[0]) - 11.7786) <= 0.05)
            result["checks"]["guest_raw_matches_default_gain"] = bool(guest and int(guest[1]) == -3)
            result["checks"]["guest_gain_rate"] = guest is not None and guest[2:] == ("2", "4")
            result["checks"]["guest_config_path"] = config == ("5", "4", "1")
            result["checks"]["eeprom_write_rejected_and_counted"] = bool(
                rejected and int(final.get("eeprom-writes", 0)) >= 1)
            result["checks"]["qom_voltage_fixture_exact"] = final.get("voltage-v") == 12.0
            result["checks"]["qom_config_after_writes"] = final.get("config-word") == 0x8B80
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0
            result["vmeter"]["quantization_boundary"] = (
                "PGA_2048 resolution is 3.93 V/LSB by the driver's own table; the 12.0 V fixture "
                "quantizes to 11.78 V. This is driver quantization, not a measurement.")

        elif case == "adc":
            fixtures = {"voltage-v": 3.3}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: ((row := last_match(r"I2C_ADC (\d+) ([0-9a-f]*) ([\d.]+) (\d+) (\d+) (\d+)", text))
                                   is not None and int(row[0]) == 8192
                                   and abs(float(row[2]) - 3.3) <= 0.001), 60)
            serial = wait_for(client, session_id, lambda text: "I2C_ADC_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["adc"] = serial[-600:]
            guest = last_match(r"I2C_ADC (\d+) ([0-9a-f]*) ([\d.]+) (\d+) (\d+) (\d+)", serial)
            config = last_match(r"I2C_ADC_CONFIG (\d+) (\d+) (\d+) (.+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("config-word") == 0x99 and int(p.get("transactions", 0)) > 0,
                label="adc final qom")
            result["qom_samples"].extend(samples)
            expected_raw = round(3.3 / 13.2 * 32768.0)
            result["adc"] = {"fixtures": fixtures, "guest": guest, "guest_config": config,
                             "expected_raw_default": expected_raw,
                             "qom": {k: final.get(k) for k in ("voltage-v", "adc-raw", "config-word",
                                                               "i2c-address", "transactions")}}
            result["checks"]["guest_value_tracks_fixture"] = bool(guest and int(guest[0]) == expected_raw)
            result["checks"]["guest_raw_slice_is_two_bytes"] = bool(guest and len(guest[1]) == 4)
            result["checks"]["guest_voltage_matches_fixture"] = bool(
                guest and abs(float(guest[2]) - 3.3) <= 0.001)
            result["checks"]["guest_default_gain_rate"] = guest is not None and guest[3:] == ("1", "8", "0")
            result["checks"]["guest_config_sequence"] = bool(
                config and config[0:3] == ("2", "16", "1"))
            result["checks"]["qom_voltage_fixture_exact"] = final.get("voltage-v") == 3.3
            result["checks"]["qom_config_after_writes"] = final.get("config-word") == 0x99
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "env-iv":
            fixtures = {"temperature-c": 25.5, "humidity-pct": 60.5, "pressure-pa": 100000.0}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: re.search(r"I2C_ENV4 25\.5 60\.5 1000\.0", text) is not None, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_ENV4_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["env-iv"] = serial[-800:]
            guest = last_match(r"I2C_ENV4 ([\d.]+) ([\d.]+) ([\d.]+)", serial)
            sht = last_match(r"I2C_SHT4X_MEASURE \(([\d.]+), ([\d.]+)\)", serial)
            serial_number = last_match(r"I2C_SHT4X_ATTR serial_number (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("temperature-c") == 25.5 and p.get("humidity-pct") == 60.5
                and p.get("pressure-pa") == 100000.0,
                label="env-iv final qom")
            result["qom_samples"].extend(samples)
            result["env_iv"] = {"fixtures": fixtures, "guest": guest, "sht4x_measure": sht,
                                "serial_number_guest": serial_number,
                                "qom": {k: final.get(k) for k in ("temperature-c", "humidity-pct",
                                                                  "pressure-pa", "serial-number",
                                                                  "transactions", "read-bytes",
                                                                  "written-bytes")}}
            result["checks"]["guest_sht40_temperature_humidity"] = bool(
                guest and abs(float(guest[0]) - 25.5) <= 0.06 and abs(float(guest[1]) - 60.5) <= 0.06)
            result["checks"]["guest_bmp280_pressure"] = bool(guest and abs(float(guest[2]) - 1000.0) <= 0.2)
            result["checks"]["sht4x_crc_verified_by_driver"] = bool(
                sht and abs(float(sht[0]) - 25.5) <= 0.06 and abs(float(sht[1]) - 60.5) <= 0.06)
            result["checks"]["dual_slave_transactions"] = int(final.get("transactions", 0)) > 0
            result["checks"]["qom_fixtures_exact"] = (
                final.get("temperature-c") == 25.5 and final.get("humidity-pct") == 60.5
                and final.get("pressure-pa") == 100000.0)
            result["checks"]["qom_serial_number"] = final.get("serial-number") == 0x12345678

        elif case == "co2":
            fixtures = {"co2-ppm": 1234, "temperature-c": 25.5, "humidity-pct": 60.5, "data-ready": True}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: "I2C_CO2_ATTR co2 1234" in text and "I2C_CO2_ATTR humidity 60.5" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_CO2_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["co2"] = serial[-900:]
            co2 = last_match(r"I2C_CO2_ATTR co2 (\d+)", serial)
            humidity = last_match(r"I2C_CO2_ATTR humidity ([\d.]+)", serial)
            temperature = last_match(r"I2C_CO2_ATTR temperature ([\d.]+)", serial)
            serial_guest = last_match(r"I2C_CO2_CALL get_serial_number (\([^)]*\))", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("co2-ppm") == 1234 and p.get("humidity-pct") == 60.5
                and int(p.get("measurement-reads", 0)) > 0,
                label="co2 final qom")
            result["qom_samples"].extend(samples)
            result["co2"] = {"fixtures": fixtures, "guest_co2": co2, "guest_humidity": humidity,
                             "guest_temperature": temperature, "guest_serial_tuple": serial_guest,
                             "qom": {k: final.get(k) for k in ("co2-ppm", "temperature-c", "humidity-pct",
                                                               "data-ready", "serial-number",
                                                               "measurement-reads", "transactions")},
                             "driver_bug_boundary": "The frozen SCD40 driver decodes temperature from "
                                                    "buf[1] instead of buf[4] (self.temperature is wrong); CO2 "
                                                    "and humidity are assertable. SCD40-vs-SCD41 identity is unresolved."}
            result["checks"]["guest_co2_tracks_fixture"] = co2 == "1234"
            result["checks"]["guest_humidity_tracks_fixture"] = humidity == "60.5"
            result["checks"]["guest_serial_number_readable"] = serial_guest is not None
            result["checks"]["temperature_decode_driver_bug_recorded"] = (
                temperature is not None and abs(float(temperature) - 25.5) > 0.1)
            result["checks"]["qom_fixtures_exact"] = (
                final.get("co2-ppm") == 1234 and final.get("humidity-pct") == 60.5)
            result["checks"]["measurement_reads_observed"] = int(final.get("measurement-reads", 0)) > 0
            result["checks"]["qom_serial_number"] = final.get("serial-number") == 0x12345678

        elif case == "pbhub":
            fixtures = {"digital-inputs": [True, False, True, False, True, False],
                        "analog-inputs": [512, 0, 1023, 0, 100, 0]}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id, lambda text: "I2C_PBHUB 1 1 512" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_PBHUB_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["pbhub"] = serial[-800:]
            guest = last_match(r"I2C_PBHUB (\d) (\d) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("digital-inputs") == [True, False, True, False, True, False]
                and p.get("analog-inputs") == [512, 0, 1023, 0, 100, 0]
                and p.get("rgb-frames", [None])[0] == 0xFF0000,
                label="pbhub final qom")
            result["qom_samples"].extend(samples)
            result["pbhub"] = {"fixtures": fixtures, "guest": guest,
                               "guest_pwm_marker": "I2C_PBHUB_PWM 50" in serial,
                               "guest_rgb_marker": "I2C_PBHUB_RGB 1 16711680 128" in serial,
                               "guest_status": last_match(r"I2C_PBHUB_CALL read_status \(254,\) (\d+)", serial),
                               "qom": {k: final.get(k) for k in ("digital-inputs", "analog-inputs",
                                                                 "digital-outputs", "pwm-outputs",
                                                                 "rgb-frames", "rgb-mode",
                                                                 "fw-version", "i2c-address",
                                                                 "transactions")},
                               "boundary": "The 0131 model exposes one digital boolean per channel for both "
                                           "input and output (IO0/IO1 positions are collapsed: reads return the "
                                           "same fixture bit and writes use one latch). Per-position IO0/IO1 "
                                           "semantics are NOT modeled and remain a catalog limitation. RGB "
                                           "frame is the last committed GRB wire value; frozen tag driver "
                                           "sends GRB."}
            result["checks"]["guest_digital_and_analog_reads"] = guest == ("1", "1", "512")
            result["checks"]["guest_write_markers"] = (
                result["pbhub"]["guest_pwm_marker"] and result["pbhub"]["guest_rgb_marker"])
            result["checks"]["guest_status_registers"] = result["pbhub"]["guest_status"] == "1"
            result["checks"]["qom_inputs_exact"] = (
                final.get("digital-inputs") == [True, False, True, False, True, False]
                and final.get("analog-inputs") == [512, 0, 1023, 0, 100, 0])
            result["checks"]["qom_pwm_observed"] = final.get("pwm-outputs", [0] * 6)[0] == 128
            result["checks"]["qom_rgb_observed"] = final.get("rgb-frames", [0] * 6)[0] == 0xFF0000
            result["checks"]["qom_rgb_mode_observed"] = final.get("rgb-mode") == 1
            result["checks"]["qom_fw_and_address"] = final.get("fw-version") == 1 and final.get("i2c-address") == 0x61
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "ultrasonic-io":
            props = inject(client, session_id, {"distance-mm": 1000})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: len(re.findall(r"GPIO_ULTRA \d+ [\d.]+", text)) >= 2
                     and "GPIO_ULTRA_END" in text, 120)
            serial = read_serial(client, session_id)
            distances = [int(value) for value in re.findall(r"GPIO_ULTRA (\d+) ", serial)]
            fast = last_match(r"GPIO_ULTRA_FAST_TIMEOUT (-?\d+)", serial)
            fast_error = last_match(r"GPIO_ULTRA_FAST_ERROR (.+)", serial)
            result["serial_markers"]["ultrasonic"] = serial[-900:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("trigger-count", 0)) >= 8,
                label="ultrasonic final qom")
            result["qom_samples"].extend(samples)
            expected_pulse = 1000 * 582 // 100
            result["ultrasonic_io"] = {"guest_distances_mm": distances,
                                       "fast_timeout_value": fast,
                                       "fast_timeout_error": fast_error,
                                       "expected_echo_pulse_us": expected_pulse,
                                       "qom": {k: final.get(k) for k in ("distance-mm", "echo-pulse-us",
                                                                         "trigger-count", "timeouts",
                                                                         "echo-level", "input-events")},
                                       "boundary": "Echo width is distance-mm*582/100 us; acoustic physics, "
                                                   "40kHz response and the documented PORT.A SDA/SCL label "
                                                   "conflict are NOT RUN. The timeout path uses a second unit "
                                                   "instance with echo_timeout_us=1000 (< the 5820us echo), so "
                                                   "machine.time_pulse_us reports the guest-side timeout; the "
                                                   "catalog input range (20..4500) cannot express an invalid "
                                                   "distance, so the model's timeouts counter stays 0."}
            result["checks"]["guest_distance_tracks_fixture"] = bool(
                distances and all(abs(d - 1000) <= 150 for d in distances[:2]))
            result["checks"]["timeout_path_exercised"] = bool(
                (fast is not None and int(fast) < 0) or fast_error is not None)
            result["checks"]["qom_echo_pulse_matches_formula"] = final.get("echo-pulse-us") == expected_pulse
            result["checks"]["qom_trigger_count"] = int(final.get("trigger-count", 0)) >= 8
            result["checks"]["model_timeouts_zero_for_valid_fixture"] = int(final.get("timeouts", 0)) == 0
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        screenshot = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(screenshot)
        result["frame_sha256"] = sha256(screenshot)
        result["frame_metrics"] = png_metrics(screenshot)
        result["checks"]["nonempty_application_frame"] = result["frame_metrics"]["unique_colors"] > 1
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as error:  # noqa: BLE001 - the failure is preserved as evidence
        result["error"] = str(error)
        result["status"] = "FAIL"
    finally:
        if session_id:
            try:
                bundle = client.raw(f"sessions/{session_id}/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence_sha256"] = sha256(bundle)
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
