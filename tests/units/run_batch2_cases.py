#!/usr/bin/env python3
"""Validate the first six Units of the second research batch through Device Service.

Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 Unit driver, creates one visible leased `/api/v1`
session with exactly one attached Unit, drives external fixture values through
`unit-input`, reads controller-backed QOM state, captures serial markers, the
frame and the evidence ZIP before stopping with `purge=0`. Virtual-device
results are never hardware results.
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

CASES = ("joystick", "watering", "fader", "dac", "bps", "adc-v11")
MARKER = "BATCH2_PROBE_READY"
CASE_DRIVERS = {
    "joystick": "JoystickUnit",
    "watering": "WateringUnit",
    "fader": "FaderUnit",
    "dac": "DACUnit(MCP4725)",
    "bps": "BPSUnit",
    "adc-v11": "ADCV11Unit(ADS1110)",
}
RUNTIME_QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"


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


def wait_serial_match(client: Client, session_id: str, pattern: str, timeout: float = 60.0) -> str:
    return wait_for(client, session_id, lambda text: re.search(pattern, text) is not None, timeout)


def parse_int_list(marker: str, serial: str) -> list[int] | None:
    matches = re.findall(rf"{marker} (-?\d+(?: -?\d+)*)", serial)
    return [int(item) for item in matches[-1].split()] if matches else None


def expected_adc_raw(voltage_mv: float) -> int:
    """Reference-firmware ADC expansion: 12-bit model sample -> read_u16."""
    sample = round(voltage_mv * 4095.0 / 3100.0)
    sample = min(4095, sample)
    return round(sample * 65535.0 / 4095.0)


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


def run_case(client: Client, args, case: str) -> dict:
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device = next(row for row in matrix["devices"] if row["id"] == args.device)
    port = select_port(client, args.device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch2_probe", files, dirs_exist_ok=True)
    (files / "probe_config.py").write_text(
        f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {args.device!r}\n",
        encoding="utf-8",
    )
    image = build_image(SimpleNamespace(
        base=ROOT / device["base"], flash_size=int(device["flash_size"], 0),
        files_dir=files, mklittlefs=None, preserve_vfs=False,
        vfs_offset=int(device["vfs_offset"], 0), vfs_size=int(device["vfs_size"], 0),
        prog_size=32, out_dir=output,
    ))
    firmware_bytes = image.read_bytes()
    result = {
        "schema_version": 1, "date": utc_now(),
        "validation": "virtual-device validation",
        "scope": "device-local Unit data plane through a visible Device Service session; not hardware",
        "device_id": args.device, "unit_id": case,
        "driver_class": CASE_DRIVERS[case],
        "driver_flavor": "reference-firmware-frozen-original-unit-driver",
        "runtime": "qemu", "status": "FAIL", "checks": {},
        "firmware_sha256": sha256(firmware_bytes),
        "probe_sha256": {path.name: sha256(path.read_bytes()) for path in files.glob("*.py")},
        "runtime_binary_sha256": sha256(RUNTIME_QEMU.read_bytes()) if RUNTIME_QEMU.is_file() else None,
        "port": {"id": port["id"], "pins": port["pins"]},
        "qom_samples": [], "serial_markers": {},
    }
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{args.device}-batch2-{case}.bin",
        })
        firmware = client.json("firmware", method="POST", payload={
            "device_id": args.device, "kind": "merged", "artifact_id": artifact["artifact_id"],
        })
        result["firmware_id"] = firmware["firmware_id"]
        session = client.json("sessions", method="POST", payload={
            "device_id": args.device, "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 300, "ready_marker": MARKER, "ready_timeout_seconds": 120,
            "units": [{"id": "external1", "unit_id": case, "port_id": port["id"]}],
        })
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created on {args.device}/{port['id']}", flush=True)
        serial = wait_for(client, session_id, lambda text: MARKER in text, 150)
        result["checks"]["official_driver_ready"] = True
        result["serial_markers"]["ready"] = serial[serial.index(MARKER):serial.index(MARKER) + len(MARKER)]
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        attached = (live.get("units") or [{}])[0]
        result["attached_unit"] = {key: attached.get(key) for key in ("id", "unit_id", "available", "source")}

        if case == "joystick":
            fixtures = {"x-raw": 37, "y-raw": 201, "button-raw": 1}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            serial = wait_serial_match(client, session_id, r"I2C_JOYSTICK 37 201 1", 40)
            serial = read_serial(client, session_id)
            result["serial_markers"]["axis"] = serial[-400:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("x-raw") == 37 and p.get("y-raw") == 201 and p.get("button-raw") == 1,
                label="joystick fixture qom",
            )
            result["qom_samples"].extend(samples)
            sample = last_match(r"I2C_JOYSTICK (\d+) (\d+) (\d+)", serial)
            result["joystick"] = {"fixtures": fixtures, "guest": sample,
                                  "qom": {k: final.get(k) for k in ("x-raw", "y-raw", "button-raw",
                                                                   "transactions", "read-bytes", "written-bytes")}}
            result["checks"]["guest_axes_track_fixture"] = sample == ("37", "201", "1")
            result["checks"]["qom_fixture_exact"] = (
                final.get("x-raw") == 37 and final.get("y-raw") == 201 and final.get("button-raw") == 1
            )
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "watering":
            voltage_mv = 1600.0
            props = inject(client, session_id, {"analog-mv": voltage_mv})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            expected = expected_adc_raw(voltage_mv)
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_WATERING_RAW (\d+)", text)) is not None
                              and abs(int(row) - expected) <= max(64, expected // 50)),
                40,
            )
            serial = read_serial(client, session_id)
            raw_sample = last_match(r"I2C_WATERING_RAW (\d+)", serial)
            voltage_unsupported = "I2C_WATERING_VOLTAGE_UNSUPPORTED" in serial
            serial = wait_for(client, session_id, lambda text: "I2C_WATERING_PUMP 1" in text, 40)
            on_props, samples = wait_properties(
                client, session_id, lambda p: p.get("pump-level") is True, label="watering pump on")
            result["qom_samples"].extend(samples)
            after_on = int(on_props.get("pump-transitions", 0))
            serial = wait_for(client, session_id, lambda text: "I2C_WATERING_PUMP 0" in text, 40)
            off_props, samples = wait_properties(
                client, session_id, lambda p: p.get("pump-level") is False, label="watering pump off")
            result["qom_samples"].extend(samples)
            serial = wait_for(client, session_id, lambda text: "I2C_WATERING_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["pump"] = serial[-700:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("analog-mv") == voltage_mv and p.get("pump-level") is False
                and int(p.get("pump-transitions", 0)) >= after_on + 2,
                label="watering final qom",
            )
            result["qom_samples"].extend(samples)
            result["watering"] = {
                "voltage_mv": voltage_mv, "expected_read_u16": expected,
                "guest_raw": int(raw_sample) if raw_sample else None,
                "voltage_readback_unsupported": voltage_unsupported,
                "voltage_boundary": ("read_uv()/get_voltage() require the S3 ADC calibration fixture and are NOT RUN "
                                     "in this batch; read_u16() is the covered path.") if voltage_unsupported else None,
                "qom": {k: final.get(k) for k in ("analog-mv", "adc-samples", "pump-level",
                                                  "pump-transitions", "transactions", "written-bytes")},
            }
            result["checks"]["guest_raw_tracks_adc_fixture"] = bool(
                raw_sample and abs(int(raw_sample) - expected) <= max(64, expected // 50)
            )
            result["checks"]["qom_analog_fixture_exact"] = final.get("analog-mv") == voltage_mv
            result["checks"]["adc_samples_observed"] = int(final.get("adc-samples", 0)) > 0
            result["checks"]["pump_on_observed"] = bool(after_on >= 1)
            result["checks"]["pump_off_and_retrigger_observed"] = int(final.get("pump-transitions", 0)) >= after_on + 2
            result["checks"]["no_i2c_transactions_fabricated"] = all(
                int(final.get(key, 0)) == 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "fader":
            voltage_mv = 2500.0
            props = inject(client, session_id, {"analog-mv": voltage_mv})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            expected = expected_adc_raw(voltage_mv)
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_FADER_RAW (\d+)", text)) is not None
                              and abs(int(row) - expected) <= max(128, expected // 40)),
                40,
            )
            serial = wait_for(client, session_id, lambda text: "I2C_FADER_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["frames"] = serial[-1200:]
            raw_sample = last_match(r"I2C_FADER_RAW (\d+)", serial)
            voltage_unsupported = "I2C_FADER_VOLTAGE_UNSUPPORTED" in serial
            guest_frames = [line for line in re.findall(r"I2C_FADER_FRAME (-?\d+(?: -?\d+)*)", serial)]
            guest_frame = [int(value) for value in guest_frames[-1].split()] if guest_frames else None
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("analog-mv") == voltage_mv and len(p.get("led-rgb") or []) == 14
                and int(p.get("led-frames", 0)) > 0,
                label="fader final qom",
            )
            result["qom_samples"].extend(samples)
            result["fader"] = {
                "voltage_mv": voltage_mv, "expected_read_u16": expected,
                "guest_raw": int(raw_sample) if raw_sample else None,
                "voltage_readback_unsupported": voltage_unsupported,
                "voltage_boundary": ("read_uv()/get_voltage() require the S3 ADC calibration fixture and are NOT RUN "
                                     "in this batch; read_u16() is the covered path.") if voltage_unsupported else None,
                "guest_frame": guest_frame,
                "qom": {k: final.get(k) for k in ("analog-mv", "adc-samples", "led-rgb", "led-frames",
                                                  "incomplete-frames", "transactions", "written-bytes")},
            }
            result["checks"]["guest_raw_tracks_adc_fixture"] = bool(
                raw_sample and abs(int(raw_sample) - expected) <= max(128, expected // 40)
            )
            result["checks"]["qom_analog_fixture_exact"] = final.get("analog-mv") == voltage_mv
            result["checks"]["adc_samples_observed"] = int(final.get("adc-samples", 0)) > 0
            result["checks"]["led_frames_observed"] = int(final.get("led-frames", 0)) > 0
            result["checks"]["incomplete_frames_none"] = int(final.get("incomplete-frames", 0)) == 0
            result["checks"]["fourteen_led_strip"] = len(final.get("led-rgb") or []) == 14
            result["checks"]["guest_buffer_matches_qom_frame"] = bool(
                guest_frame and final.get("led-rgb") == guest_frame
            )
            result["checks"]["no_i2c_transactions_fabricated"] = all(
                int(final.get(key, 0)) == 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "dac":
            serial = wait_for(client, session_id, lambda text: "I2C_DAC_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["dac"] = serial[-600:]
            finals = {}
            for marker in ("RAW", "EEPROM"):
                values = re.findall(rf"I2C_DAC_{marker} (\d+)", serial)
                finals[marker] = [int(value) for value in values]
            voltage_line = last_match(r"I2C_DAC_VOLTAGE (-?[\d.]+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("dac-raw") == 1024 and p.get("eeprom-writes") == 1,
                label="dac final qom",
            )
            result["qom_samples"].extend(samples)
            result["dac"] = {"guest_raws": finals["RAW"], "guest_eeprom": finals["EEPROM"],
                             "guest_voltage": float(voltage_line) if voltage_line else None,
                             "qom": {k: final.get(k) for k in ("dac-raw", "dac-voltage-v",
                                                               "eeprom-value", "eeprom-writes")}}
            result["checks"]["guest_raw_roundtrip"] = finals["RAW"][:3] == [2048, 819, 1024]
            result["checks"]["guest_voltage_follows_driver_vdd"] = bool(
                voltage_line and abs(float(voltage_line) - 819 / 4095.0 * 5.0) <= 0.002
            )
            result["checks"]["guest_eeprom_write_observed"] = bool(finals["EEPROM"] and finals["EEPROM"][-1] == 819)
            result["checks"]["qom_raw_after_guest_write"] = final.get("dac-raw") == 1024
            result["checks"]["qom_eeprom_value"] = final.get("eeprom-value") == 819
            result["checks"]["qom_eeprom_writes"] = final.get("eeprom-writes") == 1
            result["checks"]["qom_voltage_matches_driver_default"] = bool(
                isinstance(final.get("dac-voltage-v"), (int, float))
                and abs(final["dac-voltage-v"] - 1024 / 4095.0 * 5.0) <= 0.002
            )

        elif case == "bps":
            fixtures = {"temperature-c": 25.0, "pressure-pa": 101325.0}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_BPS (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", text)) is not None
                              and abs(float(row[0]) - 25.0) <= 0.02
                              and abs(float(row[1]) - 1013.25) <= 0.05),
                40,
            )
            serial = read_serial(client, session_id)
            first = last_match(r"I2C_BPS (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            second_fixtures = {"temperature-c": 10.5, "pressure-pa": 95000.0}
            inject(client, session_id, second_fixtures)
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_BPS (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", text)) is not None
                              and abs(float(row[0]) - 10.5) <= 0.02
                              and abs(float(row[1]) - 950.0) <= 0.05),
                40,
            )
            serial = read_serial(client, session_id)
            result["serial_markers"]["bps"] = serial[-500:]
            second = last_match(r"I2C_BPS (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("temperature-c") == 10.5 and p.get("pressure-pa") == 95000.0,
                label="bps fixture qom",
            )
            result["qom_samples"].extend(samples)
            expected_altitude = round(44330.0 * (1.0 - (95000.0 / 101325.0) ** (1 / 5.255)), 2)
            result["bps"] = {"low_fixture": first, "high_fixture": second,
                             "expected_altitude": expected_altitude,
                             "qom": {k: final.get(k) for k in ("temperature-c", "pressure-pa",
                                                               "transactions", "read-bytes", "written-bytes")}}
            result["checks"]["guest_temperature_tracks_fixture"] = bool(
                first and second and abs(float(second[0]) - 10.5) <= 0.02
            )
            result["checks"]["guest_pressure_tracks_fixture"] = bool(
                first and second and abs(float(second[1]) - 950.0) <= 0.05
            )
            result["checks"]["guest_altitude_matches_driver_formula"] = bool(
                second and abs(float(second[2]) - expected_altitude) <= 0.5
            )
            result["checks"]["qom_fixture_exact"] = (
                final.get("temperature-c") == 10.5 and final.get("pressure-pa") == 95000.0
            )
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "adc-v11":
            voltage_mv = 1000.0
            props = inject(client, session_id, {"voltage-mv": voltage_mv})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_ADC11_VOLTAGE (-?[\d.]+)", text)) is not None
                              and abs(float(row) - 1.0) <= 0.02),
                40,
            )
            serial = read_serial(client, session_id)
            initial_voltage = last_match(r"I2C_ADC11_VOLTAGE (-?[\d.]+)", serial)
            initial_raw = last_match(r"I2C_ADC11_RAW (-?\d+)", serial)
            serial = wait_for(client, session_id, lambda text: "I2C_ADC11_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["adc"] = serial[-700:]
            gain_raw = last_match(r"I2C_ADC11_GAIN (-?\d+)", serial)
            rate_raw = last_match(r"I2C_ADC11_RATE (-?\d+)", serial)
            final_voltage = last_match(r"I2C_ADC11_FINAL_VOLTAGE (-?[\d.]+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("voltage-mv") == voltage_mv and p.get("config-word") == 0x95,
                label="adc-v11 final qom",
            )
            result["qom_samples"].extend(samples)
            expected_raw = round(1.0 * 2 ** 15 * 1 * (100 / 610) / 2.048)
            result["adc_v11"] = {"voltage_mv": voltage_mv, "initial_voltage": initial_voltage,
                                 "initial_raw": int(initial_raw) if initial_raw else None,
                                 "expected_raw_default": expected_raw,
                                 "gain_raw": gain_raw, "rate_raw": rate_raw,
                                 "final_voltage": final_voltage,
                                 "qom": {k: final.get(k) for k in ("voltage-mv", "adc-raw", "config-word",
                                                                   "transactions", "read-bytes")}}
            result["checks"]["guest_voltage_tracks_fixture"] = bool(
                initial_voltage and abs(float(initial_voltage) - 1.0) <= 0.02
            )
            result["checks"]["guest_raw_matches_default_config"] = bool(
                initial_raw and abs(int(initial_raw) - expected_raw) <= 2
            )
            result["checks"]["guest_config_writes_observed"] = bool(gain_raw and rate_raw)
            result["checks"]["guest_final_voltage_after_config"] = bool(
                final_voltage and abs(float(final_voltage) - 1.0) <= 0.03
            )
            result["checks"]["qom_fixture_exact"] = final.get("voltage-mv") == voltage_mv
            result["checks"]["qom_config_word_after_writes"] = final.get("config-word") == 0x95
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

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
                    and history.get("state") in {"stopped", "failed"}
                )
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
    parser.add_argument("--device", choices=("cores3", "atoms3r", "sticks3", "stopwatch"), required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.api_url)
    result = run_case(client, args, args.case)
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
