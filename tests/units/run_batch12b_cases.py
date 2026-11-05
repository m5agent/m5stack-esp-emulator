#!/usr/bin/env python3
"""Guest/Device Service evidence for the batch-12b seven I2C Units.

No official Unit driver exists for these products (driver-gap), so each case
runs a raw machine.I2C register probe on a visible Device Service session.
Sessions are one-per-unit because 0x41 (INA226 pair) and 0x64 (Roller family)
addresses are mutually exclusive on one bus.
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

MARKER = "BATCH12B_PROBE_READY"

QEMU_STATE = ("canonical 75f1d24 native layers + canonical 39-layer Unit chain "
              "(0120-0159; reconciled 0157/0158/0159); no batch12b evidence fix expected")
CASES = ("bmm350", "ina226-10a", "ina226-1a", "roller485", "roller485-lite",
         "rollercan", "rollercan-lite")
DRIVERS = {case: "machine.I2C raw register probe (driver-gap; no official Unit driver)"
           for case in CASES}
ADDRESS = {"bmm350": 0x14, "ina226-10a": 0x41, "ina226-1a": 0x41,
           "roller485": 0x64, "roller485-lite": 0x64,
           "rollercan": 0x64, "rollercan-lite": 0x64}
END = {case: f"{'BMM350' if case == 'bmm350' else 'INA226' if case.startswith('ina226') else 'ROLLER'}_END"
       for case in CASES}
INITIAL = {
    "bmm350": {"magnetic-x": 100.0, "magnetic-y": -50.0, "magnetic-z": 25.0},
    "ina226-10a": {"bus-voltage-v": 12.0, "current-a": 2.0},
    "ina226-1a": {"bus-voltage-v": 5.0, "current-a": 0.5},
    "roller485": {},
    "roller485-lite": {},
    "rollercan": {},
    "rollercan-lite": {},
}
SHUNT = {"ina226-10a": 0.005, "ina226-1a": 0.08}
CAL = {"ina226-10a": 0x0C80, "ina226-1a": 0x0800}
PRODUCT = {"roller485": 0x01, "roller485-lite": 0x01, "rollercan": 0x02, "rollercan-lite": 0x02}
BMM_X_SCALE, BMM_Z_SCALE, BMM_TEMP_SCALE, BMM_TEMP_OFFSET = 0.007069979, 0.007174964, 0.000981282, 25.49


def now():
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def serial(client, sid):
    return client.json(f"sessions/{sid}/serial?limit=262144").get("data", "")


def props(client, sid):
    units = client.json(f"sessions/{sid}/units").get("units") or []
    if not units:
        raise RuntimeError("no unit state")
    row = units[0]
    return row, row.get("properties") or {}


def wait_props(client, sid, predicate, timeout=15, label="QOM"):
    end_time = time.monotonic() + timeout
    samples = []
    last = {}
    while time.monotonic() < end_time:
        row, p = props(client, sid)
        last = p
        samples.append({"at": now(), "properties": p})
        if predicate(p):
            return row, p, samples
        time.sleep(0.1)
    raise RuntimeError(f"{label} condition not observed; last={last}")


def int_line(text, name):
    match = re.findall(rf"^{re.escape(name)} (-?\d+)$", text, re.M)
    return int(match[-1]) if match else None


def build_probe_image(device, port, case, out):
    files = out / "files"
    shutil.copytree(Path(__file__).parent / "batch12b_probe", files, dirs_exist_ok=True)
    (files / "probe_config.py").write_text(
        f"CASE = {case!r}\nWHITE = {port['pins']['white']}\n"
        f"YELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n")
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    row = next(r for r in matrix["devices"] if r["id"] == device)
    image = build_image(SimpleNamespace(
        base=ROOT / row["base"], flash_size=int(row["flash_size"], 0),
        files_dir=files, mklittlefs=None, preserve_vfs=False,
        vfs_offset=int(row["vfs_offset"], 0), vfs_size=int(row["vfs_size"], 0),
        prog_size=32, out_dir=out))
    return image.read_bytes(), files


def expected_bmm(qom):
    return {
        "chip": 0x33,
        "x": int(round(float(qom["magnetic-x"]) / BMM_X_SCALE)),
        "y": int(round(float(qom["magnetic-y"]) / BMM_X_SCALE)),
        "z": int(round(float(qom["magnetic-z"]) / BMM_Z_SCALE)),
        "temp": int(round((float(qom["temperature-c"]) + BMM_TEMP_OFFSET) / BMM_TEMP_SCALE)),
    }


def expected_ina(case, qom):
    shunt = SHUNT[case]
    cal = int(qom.get("calibration", CAL[case]))
    lsb = 0.00512 / (cal * shunt) if cal else 0.0
    plsb = 25.0 * lsb
    bus = float(qom["bus-voltage-v"])
    current = float(qom["current-a"])
    return {
        "manufacturer": 0x5449, "die": 0x2260, "config": 0x4127, "cal": cal,
        "shunt": int(round(current * shunt / 2.5e-6)),
        "bus": int(round(bus / 1.25e-3)),
        "current": int(round(current / lsb)) if lsb else 0,
        "power": int(round(bus * current / plsb)) if plsb else 0,
    }


def expected_roller(case, qom):
    return {
        "product": PRODUCT[case], "fw": 3, "address": 0x64,
        "mode_initial": int(qom.get("mode", 1)),
        "encoder": int(qom.get("encoder-pos", 0)),
        "vin": int(round(float(qom.get("vin-v", 12.0)) * 100)),
        "temperature": int(round(float(qom.get("mcu-temp-c", 30.0)))),
        "actual_speed": int(round(float(qom.get("actual-speed-rpm", 0.0)) * 100)),
        "actual_position": int(round(float(qom.get("actual-position-deg", 0.0)) * 100)),
        "current": int(round(float(qom.get("current-ma", 0.0)) * 100)),
        "target_speed": int(round(float(qom.get("target-speed-rpm", 0.0)) * 100)),
    }


def run_case(client, args, case):
    device = "cores3"
    out = args.out_dir / case
    out.mkdir(parents=True, exist_ok=True)
    registry = client.json(f"units?device_id={device}")
    host = registry["hosts"][0]
    unit_row = {row["id"]: row for row in registry["units"]}[case]
    admission = unit_row["host_admission"]
    if not admission["admitted"] or "port-a" not in admission["port_ids"]:
        raise RuntimeError(f"{case} is not admitted on {device}: {admission}")
    port = next(p for p in host["ports"] if p["id"] == "port-a")

    firmware, files = build_probe_image(device, port, case, out)
    result = {
        "schema_version": 1, "date": now(), "validation": "virtual-device validation",
        "scope": "device-local Unit data plane through a visible Device Service session; not hardware",
        "device_id": device, "unit_id": case, "driver_class": DRIVERS[case],
        "driver_flavor": "reference-firmware-raw-machine-I2C-driver-gap",
        "runtime": "qemu", "status": "FAIL", "checks": {},
        "firmware_sha256": sha(firmware),
        "base_firmware_sha256": sha((ROOT / next(r for r in json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())["devices"] if r["id"] == device)["base"]).read_bytes()),
        "probe_sha256": {p.name: sha(p.read_bytes()) for p in files.glob("*.py")},
        "runtime_binary_sha256": None, "fixture_source_baseline": QEMU_STATE,
        "official_port": "PORT.A", "runtime_port_substitution": None,
        "port": {"id": port["id"], "pins": port["pins"]},
        "initial_inputs": INITIAL[case], "qom_samples": [], "serial_markers": {},
        "observations": {},
    }
    sid = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware,
                               headers={"Content-Type": "application/octet-stream",
                                        "X-Artifact-Name": f"{device}-batch12b-{case}.bin"})
        fw = client.json("firmware", method="POST",
                         payload={"device_id": device, "kind": "merged",
                                  "artifact_id": artifact["artifact_id"]})
        session = client.json("sessions", method="POST", payload={
            "device_id": device, "firmware_id": fw["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 300, "ready_marker": MARKER, "ready_timeout_seconds": 120,
            "units": [{"id": "external1", "unit_id": case, "port_id": port["id"],
                       "initial": INITIAL[case]}]})
        sid = session["session_id"]
        result["session_id_sha256"] = sha(sid.encode())
        result["firmware_id_sha256"] = sha(str(fw["firmware_id"]).encode())
        print(f"{case}: visible session created on {device}/{port['id']}", flush=True)
        wait_for(client, sid, lambda text: MARKER in text, 150)
        result["checks"]["driver_ready"] = True
        live = client.json(f"sessions/{sid}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        result["attached_unit"] = {
            key: (live.get("units") or [{}])[0].get(key)
            for key in ("id", "unit_id", "available", "source")
        }
        wait_for(client, sid, lambda text: END[case] in text, 120)
        text = serial(client, sid)
        result["serial_markers"][case] = text[-2000:]
        row, qom, samples = wait_props(client, sid, lambda p: True)
        result["qom_samples"].extend(samples)
        result["unit_state_source"] = live.get("source")
        scan = re.findall(r"BATCH12B_SCAN \[(.*?)\]", text)
        result["checks"]["guest_scan"] = bool(scan) and (
            str(ADDRESS[case]) in scan[-1].replace(" ", ""))

        if case == "bmm350":
            exp = expected_bmm(qom)
            obs = {
                "guest": {name: int_line(text, f"BMM350_{name.upper()}_RAW") for name in ("x", "y", "z", "temp")},
                "expected_from_qom": exp,
                "qom_fixture": {k: qom.get(k) for k in ("magnetic-x", "magnetic-y", "magnetic-z", "temperature-c")},
                "boundary": "Bosch BMM350 datasheet Table 8 / section 9.2.3 two dummy bytes; raw machine.I2C only (no official Unit driver). Magnetometer/heading/OTP calibration physics NOT RUN.",
            }
            obs["guest"]["chip"] = int_line(text, "BMM350_CHIP_ID")
            obs["guest"]["otp_status"] = int_line(text, "BMM350_OTP_STATUS")
            result["observations"][case] = obs
            result["checks"]["driver_gap_recorded"] = "machine.I2C raw driver-gap" in text
            result["checks"]["guest_chip_id"] = obs["guest"]["chip"] == exp["chip"]
            for axis in ("x", "y", "z"):
                result["checks"][f"guest_mag_{axis}_raw"] = obs["guest"][axis] == exp[axis]
            result["checks"]["guest_temp_raw"] = obs["guest"]["temp"] == exp["temp"]
            result["checks"]["dummy_two_bytes_consistent"] = all(
                obs["guest"][axis] == exp[axis] for axis in ("x", "y", "z"))
            result["checks"]["qom_fixture_matches_initial"] = (
                abs(float(qom.get("magnetic-x", 0)) - 100.0) < 1e-6 and
                abs(float(qom.get("magnetic-y", 0)) - -50.0) < 1e-6 and
                abs(float(qom.get("magnetic-z", 0)) - 25.0) < 1e-6)
            result["checks"]["qom_otp_status"] = obs["guest"]["otp_status"] == 1

        elif case.startswith("ina226"):
            exp = expected_ina(case, qom)
            guest = {name: int_line(text, f"INA226_{name.upper()}") for name in
                     ("manufacturer", "die", "config", "cal", "shunt_raw", "bus_raw",
                      "current_raw", "power_raw", "cal_rb")}
            guest["shunt"] = guest.pop("shunt_raw")
            guest["bus"] = guest.pop("bus_raw")
            guest["current"] = guest.pop("current_raw")
            guest["power"] = guest.pop("power_raw")
            result["observations"][case] = {
                "guest": guest, "expected_from_qom": exp,
                "qom_fixture": {k: qom.get(k) for k in
                                ("bus-voltage-v", "current-a", "power-w",
                                 "manufacturer-id", "die-id", "i2c-address")},
                "boundary": ("TI INA226 SBOS547C Table 7-1 raw register probe only "
                             "(no official Unit driver); isolation/accuracy/fuse/thermal "
                             "NOT RUN; 0x41 is shared with the other INA226 variant so "
                             "each case uses an independent session."),
            }
            result["checks"]["driver_gap_recorded"] = "machine.I2C raw driver-gap" in text
            for name in ("manufacturer", "die", "config", "cal", "shunt", "bus",
                         "current", "power"):
                result["checks"][f"guest_{name}"] = guest[name] == exp[name]
            result["checks"]["guest_cal_readback"] = guest["cal_rb"] == exp["cal"]
            result["checks"]["qom_fixture_matches_initial"] = (
                abs(float(qom.get("bus-voltage-v", -1)) - INITIAL[case]["bus-voltage-v"]) < 1e-6 and
                abs(float(qom.get("current-a", -99)) - INITIAL[case]["current-a"]) < 1e-6)
            result["checks"]["qom_power_derived"] = abs(
                float(qom.get("power-w", -1)) -
                INITIAL[case]["bus-voltage-v"] * INITIAL[case]["current-a"]) < 1e-6
            result["checks"]["qom_address"] = int(qom.get("i2c-address", 0)) == 0x41

        else:
            exp = expected_roller(case, qom)
            guest = {
                "product": int_line(text, "ROLLER_PRODUCT_ID"),
                "fw": int_line(text, "ROLLER_FW"),
                "address": int_line(text, "ROLLER_I2C_ADDR"),
                "state": int_line(text, "ROLLER_STATE"),
                "error": int_line(text, "ROLLER_ERROR"),
                "encoder": int_line(text, "ROLLER_ENCODER"),
                "vin": int_line(text, "ROLLER_VIN_RAW"),
                "temperature": int_line(text, "ROLLER_TEMP_RAW"),
                "actual_speed": int_line(text, "ROLLER_ACTUAL_SPEED_RAW"),
                "actual_position": int_line(text, "ROLLER_ACTUAL_POS_RAW"),
                "current": int_line(text, "ROLLER_CURRENT_RAW"),
                "target_speed": int_line(text, "ROLLER_TARGET_SPEED_RAW"),
                "mode_rb": int_line(text, "ROLLER_MODE_RB"),
                "target_speed_rb": int_line(text, "ROLLER_TARGET_SPEED_RB"),
                "target_pos_rb": int_line(text, "ROLLER_TARGET_POS_RB"),
            }
            try:
                row2, qom2, more = wait_props(
                    client, sid,
                    lambda p: int(p.get("mode", -1)) == 2 and
                    abs(float(p.get("target-speed-rpm", -1)) - 1500.0) < 1e-6 and
                    abs(float(p.get("target-position-deg", -1)) - 90.0) < 1e-6,
                    label=case)
                result["qom_samples"].extend(more)
                qom = qom2
            except Exception:
                pass
            result["observations"][case] = {
                "guest": guest, "expected_from_qom": exp,
                "qom_fixture": {k: qom.get(k) for k in
                                ("mode", "target-speed-rpm", "target-position-deg",
                                 "actual-speed-rpm", "actual-position-deg",
                                 "encoder-pos", "current-ma", "vin-v", "mcu-temp-c",
                                 "fault", "i2c-address", "save-count")},
                "boundary": ("Roller family I2C 0x64 register subset from the Internal-FW "
                             "V2.2/V3.1 protocols; RS485/CAN frame layers and FOC "
                             "motor/encoder physics NOT RUN; 0x64 is shared by four "
                             "products so each case uses an independent session."),
            }
            result["checks"]["driver_gap_recorded"] = "machine.I2C raw driver-gap" in text
            result["checks"]["guest_product_id"] = guest["product"] == exp["product"]
            result["checks"]["guest_firmware"] = guest["fw"] == exp["fw"]
            result["checks"]["guest_address"] = guest["address"] == exp["address"]
            for name in ("encoder", "vin", "temperature", "actual_speed",
                         "actual_position", "current"):
                result["checks"][f"guest_{name}"] = guest[name] == exp[name]
            # Pre-write target speed is the model default 0.0 (mode/target
            # fixtures are not seeded because catalog "mode" is a string enum
            # while the QOM property is the numeric register).
            result["checks"]["guest_target_speed"] = guest["target_speed"] == 0
            result["checks"]["guest_status_clean"] = guest["state"] == 0 and guest["error"] == 0
            result["checks"]["guest_mode_readback"] = guest["mode_rb"] == 2
            result["checks"]["guest_target_speed_readback"] = guest["target_speed_rb"] == 150000
            result["checks"]["guest_target_pos_readback"] = guest["target_pos_rb"] == 9000
            result["checks"]["qom_mode_write"] = int(qom.get("mode", -1)) == 2
            result["checks"]["qom_target_speed_write"] = abs(float(qom.get("target-speed-rpm", -1)) - 1500.0) < 1e-6
            result["checks"]["qom_target_position_write"] = abs(float(qom.get("target-position-deg", -1)) - 90.0) < 1e-6
            result["checks"]["qom_save_count"] = int(qom.get("save-count", 0)) >= 1
            result["checks"]["qom_address"] = int(qom.get("i2c-address", 0)) == 0x64

        state = client.json(f"sessions/{sid}/units")
        result["unit_state"] = state
        frame = client.raw(f"sessions/{sid}/frame.png")
        (out / "frame.png").write_bytes(frame)
        result["frame"] = {"sha256": sha(frame), "metrics": png_metrics(frame)}
        result["checks"]["nonempty_application_frame"] = result["frame"]["metrics"]["unique_colors"] > 1
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as error:  # noqa: BLE001 - evidence runner records failures
        result["error"] = repr(error)
        result["status"] = "FAIL"
    finally:
        if sid:
            try:
                bundle = client.raw(f"sessions/{sid}/evidence")
                (out / "evidence.zip").write_bytes(bundle)
                result["evidence"] = {"sha256": sha(bundle), "bytes": len(bundle)}
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    required = {"manifest.json", "serial.log", "units/runtime.json",
                                "units/state.json", "units/contract.json"}
                    result["checks"]["evidence_complete"] = required.issubset(archive.namelist())
                    (out / "serial.txt").write_bytes(archive.read("serial.log"))
                    if "units/state.json" in archive.namelist():
                        (out / "units-state.json").write_bytes(archive.read("units/state.json"))
                    if "units/contract.json" in archive.namelist():
                        (out / "units-contract.json").write_bytes(
                            archive.read("units/contract.json"))
            except Exception as error:  # noqa: BLE001
                result["evidence_error"] = repr(error)
                result["checks"]["evidence_complete"] = False
                result["status"] = "FAIL"
            try:
                stopped = client.json(f"sessions/{sid}?purge=0", method="DELETE")
                history = client.json(f"sessions/{sid}")
                result["stop"] = {
                    "stop_state": stopped.get("state"), "history_state": history.get("state"),
                    "history_retained": bool(history.get("session_id") == sid),
                }
                result["checks"]["stopped_with_history"] = (
                    stopped.get("state") in {"stopped", "failed"} and
                    history.get("state") in {"stopped", "failed"})
            except Exception as error:  # noqa: BLE001
                result["stop_error"] = repr(error)
                result["checks"]["stopped_with_history"] = False
            if result.get("error") or result.get("evidence_error") or not all(result["checks"].values()):
                result["status"] = "FAIL"
        result["raw_evidence_note"] = ("Raw execution artifacts stay in local ignored .work; "
                                       "only concise reports, hashes and reproduction commands "
                                       "are committed.")
        client.finalize_result(result)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"{case}: {result['status']}" + (f" ({result.get('error')})" if result.get("error") else ""), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8805")
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    result = run_case(Client(args.api_url), args, args.case)
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
