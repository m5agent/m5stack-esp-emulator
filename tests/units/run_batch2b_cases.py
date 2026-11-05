#!/usr/bin/env python3
"""Validate the remaining six Units of the second research batch.

Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 driver, creates one visible leased `/api/v1` session
with exactly one attached Unit, drives external fixture values through
`unit-input`, reads controller-backed QOM state, captures serial markers, the
frame and the evidence ZIP before stopping with `purge=0`. Virtual-device
results are never hardware results; the ACSSR case exercises I2C transactions
only and is explicitly NOT an AC mains switching model.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
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

CASES = ("env", "ameter", "extencoder", "ain4-20ma", "acssr", "gesture")
MARKER = "BATCH2B_PROBE_READY"
CASE_DRIVERS = {
    "env": "ENVUnit(ENV_I)",
    "ameter": "AMeterUnit",
    "extencoder": "ExtEncoderUnit",
    "ain4-20ma": "AIN4_20MAUnit",
    "acssr": "ACSSRUnit",
    "gesture": "GestureUnit",
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


def run_case(client: Client, args, case: str) -> dict:
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device = next(row for row in matrix["devices"] if row["id"] == args.device)
    port = select_port(client, args.device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch2b_probe", files, dirs_exist_ok=True)
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
        "runtime_binary_sha256": None,
        "port": {"id": port["id"], "pins": port["pins"]},
        "qom_samples": [], "serial_markers": {},
    }
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{args.device}-batch2b-{case}.bin",
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

        if case == "env":
            fixtures = {"temperature-c": 25.5, "humidity-pct": 60.5, "pressure-pa": 100000.0}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_ENV (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", text)) is not None
                              and abs(float(row[0]) - 25.5) <= 0.06
                              and abs(float(row[1]) - 60.5) <= 0.06
                              and abs(float(row[2]) - 1000.0) <= 0.1),
                40,
            )
            serial = wait_for(client, session_id, lambda text: "I2C_ENV_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["env"] = serial[-500:]
            guest = last_match(r"I2C_ENV (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("temperature-c") == 25.5 and p.get("humidity-pct") == 60.5
                and p.get("pressure-pa") == 100000.0,
                label="env fixture qom",
            )
            result["qom_samples"].extend(samples)
            result["env"] = {"fixtures": fixtures, "guest": guest,
                             "qom": {k: final.get(k) for k in ("temperature-c", "humidity-pct",
                                                               "pressure-pa", "transactions",
                                                               "read-bytes", "written-bytes")}}
            result["checks"]["guest_temperature_humidity_tracks_fixture"] = bool(
                guest and abs(float(guest[0]) - 25.5) <= 0.06 and abs(float(guest[1]) - 60.5) <= 0.06
            )
            result["checks"]["guest_pressure_tracks_fixture"] = bool(
                guest and abs(float(guest[2]) - 1000.0) <= 0.1
            )
            result["checks"]["dual_slave_addresses_served"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "ameter":
            fixtures = {"current-a": 1.0}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_AMETER (-?[\d.]+) (-?\d+)", text)) is not None
                              and abs(float(row[0]) - 1.0) <= 0.1),
                40,
            )
            serial = wait_for(client, session_id, lambda text: "I2C_AMETER_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["ameter"] = serial[-600:]
            guest = last_match(r"I2C_AMETER (-?[\d.]+) (-?\d+)", serial)
            gain_line = last_match(r"I2C_AMETER_GAIN (\d+) (\d+) (\d+)", serial)
            eeprom_rejected = "I2C_AMETER_EEPROM_WRITE_REJECTED" in serial
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("current-a") == 1.0 and int(p.get("eeprom-writes", 0)) == 1,
                label="ameter final qom",
            )
            result["qom_samples"].extend(samples)
            config = int(final.get("config-word", 0))
            gain = (config >> 9) & 0x7
            mv_lsb = [0.1875, 0.125, 0.0625, 0.03125, 0.015625, 0.007813][gain] if gain < 6 else 0.007813
            resolution = mv_lsb / 0.05
            expected_raw = round(-1.0 / resolution)
            result["ameter"] = {"fixtures": fixtures, "guest": guest, "guest_gain": gain_line,
                                "expected_raw": expected_raw,
                                "eeprom_write_rejected": eeprom_rejected,
                                "qom": {k: final.get(k) for k in ("current-a", "adc-raw", "config-word",
                                                                  "eeprom-writes", "i2c-address",
                                                                  "transactions")}}
            result["checks"]["guest_current_tracks_fixture"] = bool(
                guest and abs(float(guest[0]) - 1.0) <= 0.1
            )
            result["checks"]["guest_adc_raw_matches_driver_resolution"] = bool(
                guest and abs(int(guest[1]) - expected_raw) <= 1
            )
            result["checks"]["config_word_observed"] = config != 0 and bool(gain_line)
            result["checks"]["eeprom_write_rejected_and_counted"] = bool(
                eeprom_rejected and int(final.get("eeprom-writes", 0)) == 1
            )
            result["checks"]["qom_current_fixture_exact"] = final.get("current-a") == 1.0
            result["checks"]["i2c_address_0x48"] = final.get("i2c-address") == 0x48
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "extencoder":
            fixtures = {"counter": 1234}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: ((row := last_match(r"I2C_EXTENC (-?\d+) (\d+)", text)) is not None
                                   and int(row[0]) == 1234), 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["extencoder"] = serial[-800:]
            serial = wait_for(client, session_id, lambda text: "I2C_EXTENC_END" in text, 60)
            serial = read_serial(client, session_id)
            guest_value = last_match(r"I2C_EXTENC (-?\d+) (\d+)", serial)
            config = last_match(r"I2C_EXTENC_CONFIG (\d+) (\d+) (\d+) (\d+)", serial)
            reset_value = last_match(r"I2C_EXTENC_RESET (-?\d+)", serial)
            increments = last_match(r"I2C_EXTENC_INCREMENTS (-?\d+)", serial)
            fw = last_match(r"I2C_EXTENC_FW (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("reset-writes", 0)) == 1 and int(p.get("counter", -1)) == 0,
                label="extencoder final qom",
            )
            result["qom_samples"].extend(samples)
            result["extencoder"] = {"fixtures": fixtures, "guest_value": guest_value,
                                    "guest_config": config, "guest_reset": reset_value,
                                    "guest_increments": increments, "guest_fw": fw,
                                    "qom": {k: final.get(k) for k in ("counter", "increments", "perimeter",
                                                                      "pulse", "zero-pulse", "zero-mode",
                                                                      "fw-version", "reset-writes",
                                                                      "i2c-address", "transactions")}}
            result["checks"]["guest_counter_tracks_fixture"] = bool(guest_value and int(guest_value[0]) == 1234)
            result["checks"]["config_registers_roundtrip"] = config == ("500", "20", "1", "10")
            result["checks"]["reset_clears_counter"] = bool(reset_value and int(reset_value) == 0)
            result["checks"]["reset_write_counted"] = int(final.get("reset-writes", 0)) == 1
            result["checks"]["guest_increments_track_fixture"] = bool(increments and int(increments) == 1234)
            result["checks"]["fw_fixture_and_address"] = bool(fw and int(fw) == 2) and final.get("i2c-address") == 0x59
            result["checks"]["qom_config_matches_guest"] = (
                final.get("perimeter") == 500 and final.get("pulse") == 20
                and final.get("zero-mode") == 1 and final.get("zero-pulse") == 10
            )
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "ain4-20ma":
            fixtures = {"current-ma": 12.5, "adc-raw": 2500}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(
                client, session_id,
                lambda text: ((row := last_match(r"I2C_AIN4 (\d+) (-?[\d.]+) (\d+) (0x[0-9a-f]+)", text)) is not None
                              and int(row[0]) == 2500 and abs(float(row[1]) - 12.5) <= 0.01),
                40,
            )
            serial = wait_for(client, session_id, lambda text: "I2C_AIN4_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["ain4"] = serial[-600:]
            guest = last_match(r"I2C_AIN4 (\d+) (-?[\d.]+) (\d+) (0x[0-9a-f]+)", serial)
            cal_done = "I2C_AIN4_CAL_DONE 15" in serial
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("current-ma") == 12.5 and p.get("adc-raw") == 2500,
                label="ain4 fixture qom",
            )
            result["qom_samples"].extend(samples)
            result["ain4_20ma"] = {"fixtures": fixtures, "guest": guest, "calibration_written": cal_done,
                                   "qom": {k: final.get(k) for k in ("current-ma", "adc-raw", "fw-version",
                                                                     "i2c-address", "transactions")}}
            result["checks"]["guest_adc_raw_tracks_fixture"] = bool(guest and int(guest[0]) == 2500)
            result["checks"]["guest_current_tracks_fixture"] = bool(
                guest and abs(float(guest[1]) - 12.5) <= 0.01
            )
            result["checks"]["guest_fw_and_address"] = bool(
                guest and int(guest[2]) == 1 and guest[3].lower() == "0x55"
            )
            result["checks"]["calibration_write_accepted"] = cal_done
            result["checks"]["qom_fixture_exact"] = (
                final.get("current-ma") == 12.5 and final.get("adc-raw") == 2500
            )
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "acssr":
            serial = wait_for(client, session_id, lambda text: "I2C_ACSSR_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["acssr"] = serial[-700:]
            relay_true, samples = wait_properties(
                client, session_id, lambda p: p.get("relay-level") is False,
                label="acssr final relay state")
            result["qom_samples"].extend(samples)
            relay_marks = re.findall(r"I2C_ACSSR_RELAY (\d+)", serial)
            rgb_mark = "I2C_ACSSR_RGB 1122867" in serial
            fw = last_match(r"I2C_ACSSR_FW (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("led-rgb") == 0x112233 and int(p.get("relay-transitions", 0)) >= 2,
                label="acssr rgb/transitions qom")
            result["qom_samples"].extend(samples)
            result["acssr"] = {"guest_relay_marks": relay_marks, "guest_rgb_marker": rgb_mark,
                               "guest_fw": fw,
                               "qom": {k: final.get(k) for k in ("relay-level", "relay-transitions",
                                                                 "led-rgb", "fw-version",
                                                                 "i2c-address", "transactions")},
                               "safety_boundary": "I2C transaction model only: NOT an AC mains switch model; "
                                                  "24-480V/10A, zero-cross, leakage, isolation, lifetime and any "
                                                  "mains-switching claim are NOT RUN and must not be inferred."}
            result["checks"]["guest_relay_register_roundtrip"] = relay_marks == ["1", "0"]
            result["checks"]["guest_rgb_marker"] = rgb_mark
            result["checks"]["qom_relay_state_final_off"] = final.get("relay-level") is False
            result["checks"]["qom_relay_transitions"] = int(final.get("relay-transitions", 0)) >= 2
            result["checks"]["qom_led_rgb"] = final.get("led-rgb") == 0x112233
            result["checks"]["fw_and_address"] = bool(fw and int(fw) == 1) and final.get("i2c-address") == 0x50
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "gesture":
            props = inject(client, session_id, {"gesture": 64})
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            wait_for(client, session_id,
                     lambda text: ((row := last_match(r"I2C_GESTURE (\d+)", text)) is not None
                                   and int(row) == 64), 60)
            inject(client, session_id, {"gesture": 256})
            wait_for(client, session_id,
                     lambda text: ((row := last_match(r"I2C_GESTURE (\d+)", text)) is not None
                                   and int(row) == 256), 60)
            serial = wait_for(client, session_id, lambda text: "I2C_GESTURE_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["gesture"] = serial[-800:]
            guest_values = [int(value) for value in re.findall(r"I2C_GESTURE (\d+)", serial)]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("gesture") == 256 and int(p.get("init-writes", 0)) >= 219,
                label="gesture final qom",
            )
            result["qom_samples"].extend(samples)
            result["gesture"] = {"guest_values": guest_values,
                                 "qom": {k: final.get(k) for k in ("gesture", "gesture-flags",
                                                                   "init-writes", "i2c-address",
                                                                   "transactions")}}
            result["checks"]["official_init_sequence_observed"] = int(final.get("init-writes", 0)) >= 219
            result["checks"]["guest_gesture_flags_track_fixture"] = 64 in guest_values and 256 in guest_values
            result["checks"]["qom_gesture_fixture_exact"] = final.get("gesture") == 256
            result["checks"]["i2c_address_0x73"] = final.get("i2c-address") == 0x73
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

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
        client.finalize_result(result)
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
