#!/usr/bin/env python3
"""Validate the first C-class Unit batch through visible Device Service sessions.

Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 I2C Unit driver (ncir2/extio2/hbridge), creates one
visible leased `/api/v1` session with exactly one attached Unit, drives external
fixture values through `unit-input`, reads controller-backed QOM state, captures
serial markers, the frame and the evidence ZIP before stopping with `purge=0`.
Virtual-device results are never hardware results.
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

CASES = ("ncir2", "extio2", "hbridge")
MARKER = "CCLASS_PROBE_READY"
CASE_DRIVERS = {
    "ncir2": "NCIR2Unit",
    "extio2": "EXTIO2Unit",
    "hbridge": "HbridgeUnit",
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


def latest_ncir2(serial: str) -> dict | None:
    rows = re.findall(r"I2C_NCIR2 (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (\d)", serial)
    if not rows:
        return None
    temperature, chip, emissivity, pressed = rows[-1]
    return {"temperature": float(temperature), "chip": float(chip),
            "emissivity": float(emissivity), "pressed": int(pressed)}


def parse_int_list(marker: str, serial: str) -> list[int] | None:
    matches = re.findall(rf"{marker} \[([0-9, ]*)\]", serial)
    return [int(item) for item in matches[-1].replace(" ", "").split(",")] if matches else None


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
    shutil.copytree(Path(__file__).parent / "cclass_probe", files, dirs_exist_ok=True)
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
            "X-Artifact-Name": f"{args.device}-cclass-{case}.bin",
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

        if case == "ncir2":
            fixtures = {"object-c": 25.5, "chip-c": 30.25, "button-pressed": True}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            serial = wait_for(
                client, session_id,
                lambda text: (
                    (row := latest_ncir2(text)) is not None
                    and abs(row["temperature"] - 25.5) <= 0.01
                    and abs(row["chip"] - 30.25) <= 0.01
                    and row["pressed"] == 1
                ),
                40,
            )
            normal = latest_ncir2(read_serial(client, session_id))
            # Signed int16 x0.01 cannot encode 380C; the model saturates at
            # +327.67C and this boundary must stay explicit, not a hardware claim.
            inject(client, session_id, {"object-c": 380.0})
            wait_for(
                client, session_id,
                lambda text: ((row := latest_ncir2(text)) is not None
                              and abs(row["temperature"] - 327.67) <= 0.02),
                40,
            )
            saturated = latest_ncir2(read_serial(client, session_id))
            inject(client, session_id, {"object-c": -20.5})
            wait_for(
                client, session_id,
                lambda text: ((row := latest_ncir2(text)) is not None
                              and abs(row["temperature"] + 20.5) <= 0.01),
                40,
            )
            negative = latest_ncir2(read_serial(client, session_id))
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("object-c") == -20.5 and p.get("chip-c") == 30.25
                and p.get("button-pressed") is True,
                label="ncir2 fixture qom",
            )
            result["qom_samples"].extend(samples)
            serial = wait_for(client, session_id, lambda text: "I2C_NCIR2_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["config"] = serial[-900:]
            final, after = wait_properties(
                client, session_id,
                lambda p: p.get("rgb-led") == 0x0A0B0C and p.get("buzzer-on") is True,
                label="ncir2 config qom",
            )
            result["qom_samples"].extend(after)
            emiss = last_match(r"I2C_NCIR2_EMISS (-?[\d.]+)", serial)
            thresholds = last_match(r"I2C_NCIR2_THRESH (-?[\d.]+) (-?[\d.]+)", serial)
            alarm_rgb = parse_int_list("I2C_NCIR2_ALARM_RGB", serial)
            buzzer = last_match(r"I2C_NCIR2_BUZZER (\d+) (\d+) (\d+)", serial)
            rgb = parse_int_list("I2C_NCIR2_RGB", serial)
            spec = last_match(r"I2C_NCIR2_SPEC (\d+) (\d+)", serial)
            result["ncir2"] = {
                "normal": normal, "saturated": saturated, "negative": negative,
                "emissivity": emiss, "thresholds": thresholds, "alarm_rgb": alarm_rgb,
                "buzzer": buzzer, "rgb": rgb, "spec": spec,
                "saturation_boundary": "signed int16 x0.01 encode limit is +327.67C; "
                                       "the product-page 380C range is unresolved and NOT claimed",
                "qom": {key: final.get(key) for key in ("object-c", "chip-c", "button-pressed",
                                                        "rgb-led", "buzzer-on",
                                                        "transactions", "written-bytes")},
            }
            result["checks"]["guest_temperature_tracks_fixture"] = bool(
                normal and abs(normal["temperature"] - 25.5) <= 0.01
                and abs(normal["chip"] - 30.25) <= 0.01
            )
            result["checks"]["negative_temperature_encoded"] = bool(
                negative and abs(negative["temperature"] + 20.5) <= 0.01
            )
            result["checks"]["int16_encode_limit_saturates"] = bool(
                saturated and abs(saturated["temperature"] - 327.67) <= 0.02
            )
            result["checks"]["qom_fixture_exact"] = (
                final.get("object-c") == -20.5 and final.get("chip-c") == 30.25
                and final.get("button-pressed") is True
            )
            result["checks"]["emissivity_roundtrip"] = bool(emiss and abs(float(emiss) - 0.5) <= 0.001)
            result["checks"]["thresholds_roundtrip"] = bool(
                thresholds and abs(float(thresholds[0]) - 5.0) <= 0.01
                and abs(float(thresholds[1]) - 40.0) <= 0.01
            )
            result["checks"]["alarm_led_roundtrip"] = alarm_rgb == [0x11, 0x22, 0x33]
            result["checks"]["buzzer_roundtrip"] = buzzer == ("2000", "50", "1")
            result["checks"]["rgb_led_roundtrip"] = rgb == [0x0A, 0x0B, 0x0C]
            result["checks"]["rgb_led_qom_observed"] = final.get("rgb-led") == 0x0A0B0C
            result["checks"]["buzzer_on_qom_observed"] = final.get("buzzer-on") is True
            result["checks"]["spec_identity"] = spec == ("1", "90")
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "extio2":
            fixtures = {
                "input-levels": [True, False, True, False, True, False, True, False],
                "adc-mv": [100.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3300.0],
                "fw-version": 7,
            }
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            serial = wait_for(client, session_id, lambda text: "I2C_EXTIO2_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["config"] = serial[-1500:]
            modes = parse_int_list("I2C_EXTIO2_MODES", serial)
            inputs = parse_int_list("I2C_EXTIO2_INPUTS", serial)
            adc8 = parse_int_list("I2C_EXTIO2_ADC8", serial)
            adc12 = parse_int_list("I2C_EXTIO2_ADC12", serial)
            servo = last_match(r"I2C_EXTIO2_SERVO (\d+) (\d+)", serial)
            rgb = last_match(r"I2C_EXTIO2_RGB (\d+) (\d+)", serial)
            fw = last_match(r"I2C_EXTIO2_FW (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("modes") == [0, 1, 2, 3, 4, 0, 1, 2]
                and p.get("fw-version") == 7,
                label="extio2 qom",
            )
            result["qom_samples"].extend(samples)
            expected_adc8 = [round(mv * 255.0 / 3300.0) for mv in fixtures["adc-mv"]]
            expected_adc12 = [round(mv * 4095.0 / 3300.0) for mv in fixtures["adc-mv"]]
            expected_inputs = [int(value) for value in fixtures["input-levels"]]
            result["extio2"] = {
                "modes": modes, "inputs": inputs, "adc8": adc8, "adc12": adc12,
                "servo": servo, "rgb": rgb, "fw": fw,
                "expected_adc8": expected_adc8, "expected_adc12": expected_adc12,
                "qom": {key: final.get(key) for key in ("modes", "output-levels", "servo-angles",
                                                        "servo-pulses", "rgb-leds", "fw-version",
                                                        "transactions", "written-bytes")},
            }
            result["checks"]["guest_modes_roundtrip"] = modes == [0, 1, 2, 3, 4, 0, 1, 2]
            result["checks"]["guest_inputs_track_fixture"] = inputs == expected_inputs
            result["checks"]["guest_adc8_tracks_fixture"] = bool(
                adc8 and all(abs(a - b) <= 1 for a, b in zip(adc8, expected_adc8))
            )
            result["checks"]["guest_adc12_tracks_fixture"] = bool(
                adc12 and all(abs(a - b) <= 2 for a, b in zip(adc12, expected_adc12))
            )
            result["checks"]["servo_roundtrip"] = servo == ("90", "1500")
            result["checks"]["rgb_roundtrip"] = rgb == (str(0x112233), str(0x445566))
            result["checks"]["fw_and_address"] = fw == ("7", "69")
            result["checks"]["qom_output_registers"] = (
                final.get("modes") == [0, 1, 2, 3, 4, 0, 1, 2]
                and final.get("output-levels") == [True, True, False, False, False, True, True, False]
                and final.get("servo-angles", [None] * 8)[3] == 90
                and final.get("servo-pulses", [None] * 8)[4] == 1500
                and final.get("rgb-leds", [None] * 8)[2] == 0x112233
                and final.get("rgb-leds", [None] * 8)[7] == 0x445566
            )
            result["checks"]["qom_fixtures_exact"] = (
                final.get("input-levels") == fixtures["input-levels"]
                and all(abs(a - b) < 1e-9 for a, b in zip(final.get("adc-mv", []), fixtures["adc-mv"]))
                and final.get("fw-version") == 7
            )
            result["checks"]["i2c_transactions_observed"] = all(
                int(final.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
            )

        elif case == "hbridge":
            fixtures = {"adc-mv": 1650.0, "vin-current-a": 1.5}
            props = inject(client, session_id, fixtures)
            result["qom_samples"].append({"at": utc_now(), "properties": props})
            serial = wait_for(
                client, session_id,
                lambda text: ((values := last_match(
                    r"I2C_HBRIDGE (\d+) (\d+) (\d+) (\d+) (\d+) (-?[\d.]+)", text)) is not None
                    and values[0] == "1" and values[1] == "32767" and values[2] == "500"
                    and abs(float(values[5]) - 1.5) <= 1e-3),
                60,
            )
            serial = read_serial(client, session_id)
            sample = last_match(r"I2C_HBRIDGE (\d+) (\d+) (\d+) (\d+) (\d+) (-?[\d.]+)", serial)
            serial = wait_for(client, session_id, lambda text: "I2C_HBRIDGE_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["config"] = serial[-900:]
            final = last_match(r"I2C_HBRIDGE_FINAL (\d+) (\d+)", serial)
            spec = last_match(r"I2C_HBRIDGE_SPEC (\d+) (\d+)", serial)
            qom, samples = wait_properties(
                client, session_id,
                lambda p: p.get("direction") == 2 and p.get("pwm-frequency-hz") == 500
                and abs(p.get("pwm-duty-pct", 0) - 128.0 * 100.0 / 255.0) <= 0.1,
                label="hbridge qom",
            )
            result["qom_samples"].extend(samples)
            result["hbridge"] = {
                "sample": sample, "final": final, "spec": spec,
                "expected_adc8": round(1650.0 * 255.0 / 3300.0),
                "expected_adc16": round(1650.0 * 4095.0 / 3300.0),
                "qom": {key: qom.get(key) for key in ("adc-mv", "vin-current-a", "direction",
                                                      "pwm-duty-pct", "pwm-frequency-hz",
                                                      "transactions", "output-transitions")},
            }
            result["checks"]["guest_register_roundtrip"] = bool(
                sample and sample[0] == "1" and sample[1] == "32767" and sample[2] == "500"
            )
            result["checks"]["guest_adc8_tracks_fixture"] = bool(
                sample and abs(int(sample[3]) - round(1650.0 * 255.0 / 3300.0)) <= 1
            )
            result["checks"]["guest_adc16_tracks_fixture"] = bool(
                sample and abs(int(sample[4]) - round(1650.0 * 4095.0 / 3300.0)) <= 1
            )
            result["checks"]["guest_vin_current_tracks_fixture"] = bool(
                sample and abs(float(sample[5]) - 1.5) <= 1e-3
            )
            result["checks"]["final_direction_and_pwm"] = final == ("2", "128")
            result["checks"]["spec_identity"] = spec == ("1", "32")
            result["checks"]["qom_fixtures_exact"] = (
                qom.get("adc-mv") == 1650.0 and qom.get("vin-current-a") == 1.5
            )
            result["checks"]["qom_motor_state"] = (
                qom.get("direction") == 2 and qom.get("pwm-frequency-hz") == 500
                and abs(qom.get("pwm-duty-pct") - 128.0 * 100.0 / 255.0) <= 0.1
            )
            result["checks"]["i2c_transactions_observed"] = all(
                int(qom.get(key, 0)) > 0 for key in ("transactions", "read-bytes", "written-bytes")
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
