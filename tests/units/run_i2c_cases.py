#!/usr/bin/env python3
"""Validate the first B-class Unit batch through visible Device Service sessions.

Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 I2C Unit driver (dlight/accel/4relay/weight-i2c),
creates one visible leased `/api/v1` session with exactly one attached Unit,
drives external fixture values through `unit-input`, reads controller-backed
QOM state, captures serial markers, the frame and the evidence ZIP before
stopping with `purge=0`. Virtual-device results are never hardware results.
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

CASES = ("dlight", "accel", "4relay", "weight-i2c")
MARKER = "I2C_PROBE_READY"
CASE_DRIVERS = {
    "dlight": "DLightUnit",
    "accel": "AccelUnit",
    "4relay": "Relay4Unit",
    "weight-i2c": "WeightI2CUnit",
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
    samples = []
    last = None
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


def latest_lux(serial: str) -> float | None:
    rows = re.findall(r"I2C_DLIGHT_LUX (-?[\d.]+)", serial)
    return float(rows[-1]) if rows else None


def latest_accel(serial: str) -> list[float] | None:
    rows = re.findall(r"I2C_ACCEL (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
    return [float(value) for value in rows[-1]] if rows else None


def latest_weight(serial: str) -> dict | None:
    rows = re.findall(r"I2C_WEIGHT (\d+) (-?[\d.]+) (-?\d+) (.+)", serial)
    if not rows:
        return None
    adc, weight, weight_int, text = rows[-1]
    return {"adc": int(adc), "weight": float(weight), "int": int(weight_int), "text": text.strip()}


def parse_all_bits(state: int, serial: str) -> dict | None:
    match = re.search(rf"I2C_RELAY_ALL {state} ([01]{{4}}) ([01]{{4}})", serial)
    if not match:
        return None
    return {
        "relays": [bool(int(bit)) for bit in match.group(1)],
        "leds": [bool(int(bit)) for bit in match.group(2)],
    }


def parse_final_bits(serial: str) -> dict | None:
    match = re.search(r"I2C_RELAY_FINAL ([01]{4}) ([01]{4})", serial)
    if not match:
        return None
    return {
        "relays": [bool(int(bit)) for bit in match.group(1)],
        "leds": [bool(int(bit)) for bit in match.group(2)],
    }


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
    shutil.copytree(Path(__file__).parent / "i2c_probe", files, dirs_exist_ok=True)
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
            "X-Artifact-Name": f"{args.device}-i2c-{case}.bin",
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

        if case == "4relay":
            stages = [
                ("mode1", "I2C_RELAY_MODE1", lambda p: p.get("mode") == 1),
                ("relay1_on", "I2C_RELAY_STATE 1 1", lambda p: p.get("relay-1-level") is True),
                ("led1_on", "I2C_LED_STATE 1 1", lambda p: p.get("led-1-level") is True),
                ("relay1_off", "I2C_RELAY_STATE 1 0", lambda p: p.get("relay-1-level") is False),
                ("led1_off", "I2C_LED_STATE 1 0", lambda p: p.get("led-1-level") is False),
                ("relay_all_on", "I2C_RELAY_ALL 1",
                 lambda p: all(p.get(f"relay-{i}-level") is True for i in range(1, 5))
                 and all(p.get(f"led-{i}-level") is True for i in range(1, 5))),
                ("relay_all_off", "I2C_RELAY_ALL 0",
                 lambda p: all(p.get(f"relay-{i}-level") is False for i in range(1, 5))
                 and all(p.get(f"led-{i}-level") is False for i in range(1, 5))),
                ("relay2_on", "I2C_RELAY_STATE 2 1", lambda p: p.get("relay-2-level") is True),
            ]
            observed = {}
            for label, marker, predicate in stages:
                props, samples = wait_properties(client, session_id, predicate, timeout=10.0, label=f"4relay {label}")
                result["qom_samples"].extend(samples)
                observed[label] = {key: props.get(key) for key in ("mode", "relay-1-level", "relay-2-level",
                                                                  "relay-3-level", "relay-4-level",
                                                                  "led-1-level", "led-2-level", "led-3-level", "led-4-level")}
                serial = wait_for(client, session_id, lambda text, m=marker: m in text, 30)
                result["serial_markers"][label] = serial[-260:]
                time.sleep(0.2)
            final, samples = wait_properties(
                client, session_id,
                lambda p: (p.get("relay-2-level") is True
                           and all(p.get(f"relay-{i}-level") is False for i in (1, 3, 4))
                           and all(p.get(f"led-{i}-level") is False for i in range(1, 5))),
                label="4relay final",
            )
            result["qom_samples"].extend(samples)
            serial = read_serial(client, session_id)
            guest = {
                "mode0": re.findall(r"I2C_RELAY_MODE0 (\d+)", serial),
                "mode1": re.findall(r"I2C_RELAY_MODE1 (\d+)", serial),
                "all_on": parse_all_bits(1, serial),
                "all_off": parse_all_bits(0, serial),
                "final": parse_final_bits(serial),
            }
            qom_final = {
                "relays": [final.get(f"relay-{i}-level") for i in range(1, 5)],
                "leds": [final.get(f"led-{i}-level") for i in range(1, 5)],
            }
            result["4relay"] = {"stages": observed, "guest": guest, "qom_final": qom_final}
            result["checks"]["stage_qom_follows_guest_writes"] = all(
                observed[label] for label, _, _ in stages
            )
            result["checks"]["mode_register_roundtrip"] = guest["mode0"] == ["0"] and guest["mode1"] == ["1"]
            result["checks"]["relay_all_also_lights_leds"] = bool(
                guest["all_on"] and guest["all_on"]["relays"] == [True] * 4 and guest["all_on"]["leds"] == [True] * 4
            )
            result["checks"]["guest_readback_matches_qom"] = bool(
                guest["final"] and guest["final"]["relays"] == qom_final["relays"]
                and guest["final"]["leds"] == qom_final["leds"]
            )
            result["checks"]["output_transitions_observed"] = int(final.get("output-transitions", 0)) > 0
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "dlight":
            fixtures = [400.0, 1000.0]
            samples = []
            for fixture in fixtures:
                props = inject(client, session_id, {"illuminance-lx": fixture})
                result["qom_samples"].append({"at": utc_now(), "properties": props})
                serial = wait_for(
                    client, session_id,
                    lambda text, f=fixture: (
                        latest_lux(text) is not None and abs(latest_lux(text) - f) <= 1.0
                    ),
                    40,
                )
                serial = read_serial(client, session_id)
                samples.append({"fixture": fixture, "guest_lux": latest_lux(serial), "serial_tail": serial[-220:]})
            props = properties(client, session_id)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            result["dlight"] = {"samples": samples, "qom": props}
            result["checks"]["guest_lux_tracks_fixture"] = all(
                row["guest_lux"] is not None and abs(row["guest_lux"] - row["fixture"]) <= 1.0
                for row in samples
            )
            result["checks"]["qom_fixture_exact"] = props.get("illuminance-lx") == fixtures[-1]
            result["checks"]["i2c_transactions_observed"] = all(
                int(props.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "accel":
            fixtures = {"accel-x-g": 1.0, "accel-y-g": -0.5, "accel-z-g": 2.0}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            expected = [round(fixtures[key] * 250) * 0.004 * 9.80665
                        for key in ("accel-x-g", "accel-y-g", "accel-z-g")]
            serial = wait_for(
                client, session_id,
                lambda text: (latest_accel(text) is not None
                              and all(abs(a - b) <= 0.05 for a, b in zip(latest_accel(text), expected))),
                40,
            )
            serial = read_serial(client, session_id)
            observed = latest_accel(serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: all(p.get(name) == value for name, value in fixtures.items()),
                label="accel fixture qom",
            )
            result["qom_samples"].extend(samples)
            result["accel"] = {"fixtures": fixtures, "expected_m_s2": expected,
                               "observed_m_s2": observed, "qom": final}
            result["checks"]["guest_accel_matches_raw_conversion"] = bool(
                observed and all(abs(a - b) <= 0.05 for a, b in zip(observed, expected))
            )
            result["checks"]["qom_fixture_exact"] = all(final.get(name) == value for name, value in fixtures.items())
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "weight-i2c":
            fixtures = {"weight-g": 12.34, "adc-raw": 1234567}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            serial = wait_for(
                client, session_id,
                lambda text: (
                    (row := latest_weight(text)) is not None
                    and row["adc"] == 1234567
                    and abs(row["weight"] - 12.34) <= 1e-3
                ),
                40,
            )
            serial = read_serial(client, session_id)
            observed = latest_weight(serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("weight-g") == 12.34 and p.get("adc-raw") == 1234567,
                label="weight fixture qom",
            )
            result["qom_samples"].extend(samples)
            written_before = int(final.get("written-bytes", 0))
            serial = wait_for(client, session_id, lambda text: "I2C_WEIGHT_CAL" in text, 40)
            result["serial_markers"]["calibration"] = serial[-320:]
            after_cal, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("written-bytes", 0)) > written_before,
                timeout=10.0, label="weight calibration writes",
            )
            result["qom_samples"].extend(samples)
            final_serial = read_serial(client, session_id)
            calibration = re.findall(r"I2C_WEIGHT_CAL (\d+) (\d+) (\d+)", final_serial)
            spec = re.findall(r"I2C_WEIGHT_SPEC (.+)", final_serial)
            weight_text = observed["text"].strip("'\"") if observed else ""
            try:
                parsed_text = float(weight_text)
            except ValueError:
                parsed_text = None
            int_semantics = None
            if observed:
                if observed["int"] == 1234:
                    int_semantics = "x100-raw"
                elif observed["int"] == 12:
                    int_semantics = "divided-int"
            result["weight_i2c"] = {
                "fixtures": fixtures, "observed": observed,
                "qom_after_calibration": {"written-bytes": after_cal.get("written-bytes"),
                                          "read-bytes": after_cal.get("read-bytes")},
                "calibration_readback": calibration[-1] if calibration else None,
                "device_spec": spec[-1] if spec else None,
                "int_semantics": int_semantics,
                "string_parsed": parsed_text,
            }
            result["checks"]["qom_fixture_exact"] = (
                final.get("weight-g") == 12.34 and final.get("adc-raw") == 1234567
            )
            result["checks"]["guest_adc_exact"] = bool(observed and observed["adc"] == 1234567)
            result["checks"]["guest_float_tracks_weight"] = bool(
                observed and abs(observed["weight"] - 12.34) <= 1e-3
            )
            result["checks"]["guest_int_consistent_with_x100"] = int_semantics is not None
            result["checks"]["guest_string_consistent"] = bool(
                parsed_text is not None and abs(parsed_text - 12.34) <= 1e-2
            )
            result["checks"]["calibration_command_writes_observed"] = bool(
                calibration and calibration[-1] == ("1", "10", "20")
                and int(after_cal.get("written-bytes", 0)) > written_before
            )
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
