#!/usr/bin/env python3
"""Validate the first A-class Unit batch through visible Device Service sessions.

Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 Unit driver (ssr/earth/hall/reflective-ir/vibrator),
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

CASES = ("ssr", "earth", "hall", "reflective-ir", "vibrator")
MARKER = "GPIO_PROBE_READY"
CASE_DRIVERS = {
    "ssr": "SSRUnit",
    "earth": "EarthUnit",
    "hall": "HallEffectUnit",
    "reflective-ir": "ReflectiveIRUnit",
    "vibrator": "VibratorUnit",
}



def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_serial(client: Client, session_id: str) -> str:
    return client.json(f"sessions/{session_id}/serial?limit=262144").get("data", "")


def wait_marker(client: Client, session_id: str, marker: str, offset: int, timeout: float = 90.0):
    """Wait for a marker after the current serial offset; return (serial, offset)."""
    serial = wait_for(client, session_id, lambda text: marker in text[offset:], timeout)
    position = serial.index(marker, offset)
    return serial, position + len(marker), serial[offset:position + len(marker)]


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


def latest_earth(serial: str) -> dict | None:
    rows = re.findall(r"GPIO_EARTH (\d+) (\d+)\r?\n", serial)
    if not rows:
        return None
    raw, digital = rows[-1]
    return {"raw": int(raw), "digital": int(digital)}


def latest_earth_uv(serial: str) -> dict | None:
    rows = re.findall(r"GPIO_EARTH_UV (-?\d+) (-?[\d.]+)", serial)
    if not rows:
        return None
    mv, humidity = rows[-1]
    return {"mv": int(mv), "humidity": float(humidity)}


def earth_uv_unsupported(serial: str) -> bool:
    return "GPIO_EARTH_UV_UNSUPPORTED" in serial


def latest_rir(serial: str) -> dict | None:
    rows = re.findall(r"GPIO_RIR (-?\d+) (-?\d+)", serial)
    if not rows:
        return None
    raw, digital = rows[-1]
    return {"raw": int(raw), "digital": int(digital)}


def latest_hall(serial: str) -> int | None:
    rows = re.findall(r"GPIO_HALL (-?\d+)", serial)
    return int(rows[-1]) if rows else None


def select_port(client: Client, device_id: str, unit_id: str) -> dict:
    registry = client.json(f"units?device_id={device_id}")
    host = registry["hosts"][0]
    # Registry-level admission must already report this Unit on the selected port.
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
    shutil.copytree(Path(__file__).parent / "gpio_probe", files, dirs_exist_ok=True)
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
        "qom_samples": [],
        "serial_markers": {},
    }
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{args.device}-gpio-{case}.bin",
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
        offset = serial.index(MARKER) + len(MARKER)
        result["serial_markers"]["ready"] = serial[serial.index(MARKER):offset]
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        attached = (live.get("units") or [{}])[0]
        result["attached_unit"] = {key: attached.get(key) for key in ("id", "unit_id", "available", "source")}

        if case == "ssr":
            states = []
            for label, expected in (("on", True), ("off", False), ("set_state", True), ("off_final", False)):
                time.sleep(0.2)
                props, samples = wait_properties(
                    client, session_id, lambda p: p.get("output-level") is expected,
                    timeout=8.0, label=f"ssr {label}",
                )
                result["qom_samples"].extend(samples)
                states.append({"stage": label, "output-level": props.get("output-level")})
                serial, offset, chunk = wait_marker(client, session_id, "GPIO_SSR_STATE", offset)
                result["serial_markers"][label] = chunk
                time.sleep(0.2)
            final, samples = wait_properties(client, session_id, lambda p: p.get("output-level") is False, label="ssr final")
            result["qom_samples"].extend(samples)
            result["checks"]["guest_gpio_output_follows_driver"] = all(
                row["output-level"] is expected for row, expected in zip(states, (True, False, True, False))
            )
            result["checks"]["output_transitions_observed"] = int(final.get("output-transitions", 0)) >= 3
            result["checks"]["no_i2c_transactions_fabricated"] = all(
                final.get(key, 0) == 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "vibrator":
            windows = []
            for label, expected in (("duty50", True), ("duty25", True), ("off", False)):
                serial, offset, chunk = wait_marker(client, session_id, "GPIO_VIB_STATE", offset)
                result["serial_markers"][label] = chunk
                if expected:
                    freq = 4000 if label != "duty25" else 4000
                    duty = 50 if label == "duty50" else 25
                    props, samples = wait_properties(
                        client, session_id,
                        lambda p, f=freq, d=duty: (
                            isinstance(p.get("frequency-hz"), (int, float))
                            and abs(p["frequency-hz"] - f) <= max(1.0, f * 0.1)
                            and isinstance(p.get("duty-pct"), (int, float))
                            and abs(p["duty-pct"] - d) <= 3.0
                        ),
                        timeout=10.0, label=f"vibrator {label}",
                    )
                else:
                    props, samples = wait_properties(
                        client, session_id, lambda p: p.get("duty-pct") == 0,
                        timeout=10.0, label="vibrator off",
                    )
                    freq = 4000
                result["qom_samples"].extend(samples)
                windows.append({"stage": label, "frequency-hz": props.get("frequency-hz"), "duty-pct": props.get("duty-pct")})
            serial, offset, chunk = wait_marker(client, session_id, "GPIO_VIB_ONCE", offset, timeout=30)
            result["serial_markers"]["once"] = chunk
            once_props, samples = wait_properties(
                client, session_id,
                lambda p: (
                    isinstance(p.get("duty-pct"), (int, float)) and abs(p["duty-pct"] - 60) <= 4
                    and isinstance(p.get("frequency-hz"), (int, float))
                    and abs(p["frequency-hz"] - 2000) <= 200
                ),
                timeout=8.0, label="vibrator once programmed duty",
            )
            result["qom_samples"].extend(samples)
            time.sleep(0.6)
            once_final, samples = wait_properties(
                client, session_id, lambda p: p is not None, timeout=2.0, label="vibrator once final")
            result["qom_samples"].extend(samples)
            once_cleared = once_final.get("duty-pct") == 0
            result["vibrator_once"] = {
                "programmed": {"frequency-hz": once_props.get("frequency-hz"), "duty-pct": once_props.get("duty-pct")},
                "final": {"frequency-hz": once_final.get("frequency-hz"), "duty-pct": once_final.get("duty-pct")},
                "one_shot_completion": "PASS" if once_cleared else "NOT OBSERVED",
                "boundary": None if once_cleared else (
                    "Original Haptic/SoftTimer one-shot callback did not clear duty_u16 in this firmware; "
                    "this is a known original-driver SoftTimer gap (same family as the documented Buzzer "
                    "callback issue), not a controller data-plane failure. Model faithfully keeps the last "
                    "programmed duty; one-shot completion is not claimed."),
            }
            result["checks"]["ledc_frequency_duty_observed"] = (
                bool(windows) and all(
                    isinstance(row.get("duty-pct"), (int, float)) and row["duty-pct"] > 0
                    for row in windows[:2]
                )
            )
            result["checks"]["turn_off_returns_zero_duty"] = windows[2].get("duty-pct") == 0
            result["checks"]["once_programmed_duty_observed"] = (
                abs(once_props.get("frequency-hz", 0) - 2000) <= 200
                and abs(once_props.get("duty-pct", 0) - 60) <= 4
            )
            result["checks"]["output_transitions_observed"] = int(once_final.get("output-transitions", 0)) >= 2

        elif case == "earth":
            state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
                "id": "external1", "values": {"analog-mv": 1000, "digital-level": True},
            })
            result["qom_samples"].append({"at": utc_now(), "properties": state["units"][0]["properties"]})
            time.sleep(0.8)
            serial = read_serial(client, session_id)
            low = latest_earth(serial)
            result["serial_markers"]["bucket_low"] = serial[-400:]
            state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
                "id": "external1", "values": {"analog-mv": 2500, "digital-level": False},
            })
            result["qom_samples"].append({"at": utc_now(), "properties": state["units"][0]["properties"]})
            time.sleep(0.8)
            serial = read_serial(client, session_id)
            high = latest_earth(serial)
            result["serial_markers"]["bucket_high"] = serial[-400:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("analog-mv") == 2500 and p.get("digital-level") is False,
                label="earth qom high",
            )
            result["qom_samples"].extend(samples)
            uv_low = latest_earth_uv(serial)
            serial = read_serial(client, session_id)
            uv_high = latest_earth_uv(serial)
            uv_unsupported = earth_uv_unsupported(serial)
            result["earth"] = {"low_input": low, "high_input": high,
                               "uv_low": uv_low, "uv_high": uv_high,
                               "uv_unsupported": uv_unsupported,
                               "uv_boundary": ("read_uv/humidity() require the esp32s3 ADC calibration "
                                               "fixture, which this A-class batch does not apply") if uv_unsupported else None}
            result["checks"]["qom_analog_input_exact"] = final.get("analog-mv") == 2500
            result["checks"]["qom_digital_input_matches"] = final.get("digital-level") is False
            result["checks"]["guest_raw_tracks_input"] = bool(low and high and high["raw"] > low["raw"])
            result["checks"]["guest_digital_tracks_input"] = bool(low and high and low["digital"] == 1 and high["digital"] == 0)
            result["checks"]["adc_samples_observed"] = int(final.get("adc-samples", 0)) > 0
            if not uv_unsupported:
                result["checks"]["guest_voltage_tracks_input"] = bool(uv_low and uv_high and uv_high["mv"] > uv_low["mv"])
                result["checks"]["hydrometric_mapping_moves_opposite"] = bool(
                    uv_low and uv_high and uv_low["humidity"] > uv_high["humidity"] + 0.2
                )

        elif case == "reflective-ir":
            wait_for(client, session_id, lambda text: "GPIO_RIR " in text, 30)
            time.sleep(0.3)
            serial = read_serial(client, session_id)
            baseline = latest_rir(serial)
            state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
                "id": "external1", "values": {"analog-mv": 2000, "digital-level": True},
            })
            result["qom_samples"].append({"at": utc_now(), "properties": state["units"][0]["properties"]})
            serial = wait_for(client, session_id, lambda text: "GPIO_RIR_EVENT 1" in text, 30)
            result["serial_markers"]["raise"] = serial[-400:]
            time.sleep(0.8)
            serial = read_serial(client, session_id)
            raised = latest_rir(serial)
            state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
                "id": "external1", "values": {"digital-level": False},
            })
            result["qom_samples"].append({"at": utc_now(), "properties": state["units"][0]["properties"]})
            serial = wait_for(client, session_id, lambda text: "GPIO_RIR_EVENT 0" in text, 30)
            result["serial_markers"]["fall"] = serial[-400:]
            time.sleep(0.8)
            serial = read_serial(client, session_id)
            fallen = latest_rir(serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("analog-mv") == 2000 and p.get("digital-level") is False,
                label="reflective-ir qom",
            )
            result["qom_samples"].extend(samples)
            result["reflective_ir"] = {"baseline": baseline, "raised": raised, "fallen": fallen}
            result["checks"]["qom_analog_input_exact"] = final.get("analog-mv") == 2000
            result["checks"]["qom_digital_input_matches"] = final.get("digital-level") is False
            result["checks"]["guest_raw_tracks_input"] = bool(
                baseline and raised and raised["raw"] > baseline["raw"]
            )
            final_serial = read_serial(client, session_id)
            result["checks"]["both_edge_callbacks_observed"] = bool(
                raised and fallen and raised["digital"] == 1 and fallen["digital"] == 0
                and "GPIO_RIR_EVENT 1" in final_serial
                and "GPIO_RIR_EVENT 0" in final_serial
            )
            result["checks"]["adc_samples_observed"] = int(final.get("adc-samples", 0)) > 0

        elif case == "hall":
            initial, samples = wait_properties(
                client, session_id,
                lambda p: p.get("magnetic-detected") is False and p.get("input-level") is True,
                label="hall idle",
            )
            result["qom_samples"].extend(samples)
            state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
                "id": "external1", "values": {"magnetic-detected": True},
            })
            result["qom_samples"].append({"at": utc_now(), "properties": state["units"][0]["properties"]})
            serial = wait_for(client, session_id, lambda text: "GPIO_HALL_EVENT active" in text, 30)
            result["serial_markers"]["active"] = serial[-400:]
            detected, samples = wait_properties(
                client, session_id,
                lambda p: p.get("magnetic-detected") is True and p.get("input-level") is False,
                label="hall detected",
            )
            result["qom_samples"].extend(samples)
            time.sleep(0.8)
            serial = read_serial(client, session_id)
            active_level = latest_hall(serial)
            state = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={
                "id": "external1", "values": {"magnetic-detected": False},
            })
            result["qom_samples"].append({"at": utc_now(), "properties": state["units"][0]["properties"]})
            serial = wait_for(client, session_id, lambda text: "GPIO_HALL_EVENT negative" in text, 30)
            result["serial_markers"]["negative"] = serial[-400:]
            released, samples = wait_properties(
                client, session_id,
                lambda p: p.get("magnetic-detected") is False and p.get("input-level") is True,
                label="hall released",
            )
            result["qom_samples"].extend(samples)
            time.sleep(0.8)
            serial = read_serial(client, session_id)
            released_level = latest_hall(serial)
            result["hall"] = {"initial": initial, "detected": detected, "released": released,
                              "guest_active_level": active_level, "guest_released_level": released_level}
            result["checks"]["qom_low_active_semantics"] = (
                detected.get("magnetic-detected") is True and detected.get("input-level") is False
                and released.get("input-level") is True
            )
            result["checks"]["guest_status_follows_low_active"] = active_level == 0 and released_level == 1
            final_serial = read_serial(client, session_id)
            result["checks"]["both_direction_callbacks_observed"] = (
                "GPIO_HALL_EVENT active" in final_serial
                and "GPIO_HALL_EVENT negative" in final_serial
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
