#!/usr/bin/env python3
"""Validate the second half of the sixth research batch (six Units).

One QEMU build (canonical chain through 0144 + the 0145 finger evidence fix)
covers unit-id, thermal2, qrcode, uwb, dmx and finger. Each case builds a merged
reference-firmware image that runs the firmware's frozen original UIFlow2 driver
in one visible leased /api/v1 session, provides fixtures as session-initial Unit
inputs, reads controller-backed state, captures serial markers, the frame and the
evidence ZIP before stopping with purge=0.

Expected BLOCKED cases are recorded honestly:
- unit-id: the ATECC driver wakes the chip by writing to I2C address 0x00, which
  a Unit slave bound to 0x35 cannot receive; the probe captures the exact error.
- dmx: the driver delegates to cdriver.esp_dmx; if that C module cannot be
  imported/executed in the reference firmware the probe records the failure.
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
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
from run_batch6_cases import (  # noqa: E402
    Client, utc_now, sha256, read_serial, properties, wait_properties,
    wait_for, last_match, inject,
)
from run_profile_ui_test import build_image  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402

START_MARKER = "BATCH6B_PROBE_START"
BINARY = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
QEMU_SOURCE_STATE = ("canonical 75f1d24 + canonical chain 24 layers through 0144 "
                     "(incl. 0142 batch6 B) + 0145-unit-batch6b-evidence-finger-fix")

CASES = {case: "cores3" for case in (
    "unit-id", "thermal2", "qrcode", "uwb", "dmx", "finger")}
OFFICIAL_PORT = {
    "unit-id": "PORT.A", "thermal2": "PORT.A", "qrcode": "PORT.A",
    "uwb": "PORT.C", "dmx": "PORT.C", "finger": "PORT.C",
}
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "unit-id": "IDUnit (ATECC608B, 0x35)",
    "thermal2": "Thermal2Unit (MLX90640/ESP32, 0x32)",
    "qrcode": "QRCodeUnit (I2C mode, 0x21)",
    "uwb": "UWBUnit (BU01 AT, UART)",
    "dmx": "DMX512Unit (cdriver.esp_dmx)",
    "finger": "FingerUnit (FPC1020A, UART)",
}
END_MARKER = {case: case.replace("-", "").upper()[:2] + "_END" for case in CASES}
END_MARKER.update({
    "unit-id": "ID_END", "thermal2": "T2_END", "qrcode": "QR_END",
    "uwb": "UWB_END", "dmx": "DMX_END", "finger": "FINGER_END",
})


def finger_fixture() -> str:
    """FPC1020A version-gate stream: two response frames per GET_VERSION command
    (control frame with data length, then the 8-byte version), repeated for the
    probe's own get_version plus two user-count control frames."""
    def frame(cmd: int, payload: bytes) -> str:
        checksum = cmd
        for byte in payload:
            checksum ^= byte
        return bytes([0xF5, cmd]) + payload + bytes([checksum, 0xF5])
    control = frame(0x26, bytes([0x00, 0x08, 0x00, 0x00])).hex()
    # The version payload is a raw data frame: its checksum covers the 8 data
    # bytes only (the control frame checksum covers cmd + payload).
    payload = b"B1.10.00"
    checksum = 0
    for byte in payload:
        checksum ^= byte
    version = (bytes([0xF5]) + payload + bytes([checksum, 0xF5])).hex()
    count = frame(0x09, bytes([0x00, 0x96, 0x00, 0x00])).hex()
    return ";".join([control, version, control, version, count, count])


UWB_FIXTURE = ";".join([
    "6465766963653a555742310d0a0d0a4f4b0d0a",  # device:UWB1 + OK (reset)
    "4f4b0d0a",                                  # OK (AT)
    "4f4b0d0a",                                  # OK (switchdis=0)
    "4f4b0d0a",                                  # OK (anchor_tag)
    "6465766963653a555742310d0a0d0a4f4b0d0a",  # device:UWB1 + OK (reset)
    "4f4b0d0a",                                  # OK (interval)
    "4f4b0d0a",                                  # OK (switchdis=1)
])

INITIAL = {
    "unit-id": {},
    "thermal2": {"median-c": 31.5, "average-c": 30.0, "differential-c": 1.5,
                 "button-pressed": False, "alarm-status": 0, "refresh-rate": 4},
    "qrcode": {"data-status": 1, "trigger-mode": 0},
    "uwb": {"responses-hex": UWB_FIXTURE},
    "dmx": {},
    "finger": {"responses-hex": finger_fixture()},
}
EXPECTED_BLOCKED = {"unit-id"}


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


def case_checks(case, serial, final):
    checks, observations = {}, {}
    if case == "unit-id":
        errors = re.findall(r"ID_(?:REVISION|SERIAL|RANDOM)_ERROR", serial)
        observations["wake_errors"] = errors
        observations["blocker"] = (
            "ATECC608B wake writes to I2C address 0x00 before any command; a Unit "
            "slave model bound to 0x35 cannot receive that wake write, so "
            "revision/serial/random cannot be exercised in this harness. No "
            "revision/serial value is asserted or faked.")
        checks["guest_driver_registered"] = "ID_INIT_ERROR" not in serial
        checks["wake_failure_observed"] = bool(errors)
        return checks, observations
    if case == "thermal2":
        observations["guest_measure"] = last_match(r"T2_MEASURE (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)", serial)
        observations["guest_buffer"] = last_match(r"T2_BUFFER_LEN (\d+)", serial)
        observations["guest_buffer_head"] = last_match(
            r"T2_BUFFER_HEAD (\d+) (\d+) (\d+) (\d+)", serial)
        observations["guest_detail"] = last_match(r"T2_DETAIL (\d+) (\d+)", serial)
        observations["guest_alarm"] = last_match(r"T2_ALARM (\d+)", serial)
        checks["guest_driver_ready"] = "T2_ERROR" not in serial and "T2_END" in serial
        checks["guest_median_31_5"] = bool(
            observations["guest_measure"]
            and abs(float(observations["guest_measure"][0]) - 31.5) <= 0.01)
        checks["guest_buffer_384_u16"] = observations["guest_buffer"] == "384"
        checks["guest_buffer_head_matches_fixture"] = bool(
            observations["guest_buffer_head"]
            and int(observations["guest_buffer_head"][0]) == 12224
            and int(observations["guest_buffer_head"][1]) == 12256
            and int(observations["guest_buffer_head"][2]) == 12224
            and int(observations["guest_buffer_head"][3]) == 13216)
        checks["qom_fixtures_exact"] = (
            abs(float(final.get("median-c", 0)) - 31.5) <= 0.01
            and abs(float(final.get("average-c", 0)) - 30.0) <= 0.01
            and abs(float(final.get("differential-c", 0)) - 1.5) <= 0.01)
        checks["i2c_address_0x32"] = final.get("i2c-address") == 0x32
        return checks, observations
    if case == "qrcode":
        observations["guest_status"] = last_match(r"QR_STATUS (\d+)", serial)
        observations["guest_len"] = last_match(r"QR_LEN (\d+)", serial)
        observations["guest_data"] = last_match(r"QR_DATA (\S+)", serial)
        observations["guest_mode"] = last_match(r"QR_MODE (\d+)", serial)
        observations["guest_cleared"] = last_match(r"QR_CLEARED (\d+)", serial)
        checks["guest_driver_ready"] = "QR_ERROR" not in serial and "QR_END" in serial
        checks["guest_status_1"] = observations["guest_status"] == "1"
        checks["guest_len_15"] = observations["guest_len"] == "15"
        checks["guest_data_fixture"] = observations["guest_data"] == "M5STACK-TEST-QR"
        checks["guest_trigger_mode_0"] = observations["guest_mode"] == "0"
        checks["guest_status_cleared"] = observations["guest_cleared"] == "0"
        checks["qom_status_cleared"] = final.get("data-status") == 0
        checks["qom_trigger_mode"] = final.get("trigger-mode") == 0
        checks["i2c_address_0x21"] = final.get("i2c-address") == 0x21
        return checks, observations
    if case == "uwb":
        observations["guest_device"] = last_match(r"UWB_DEVICE (\S+)", serial)
        observations["guest_continuous"] = last_match(r"UWB_CONTINUOUS (\d+)", serial)
        tx = (final.get("tx-hex") or "").lower()
        observations["qom_tx_hex"] = tx
        checks["guest_driver_ready"] = (
            "UWB_INIT_ERROR" not in serial and "BATCH6B_PROBE_READY uwb" in serial
            and "UWB_END" in serial)
        checks["guest_continuous_on"] = observations["guest_continuous"] == "1"
        checks["qom_at_bytes"] = "41542b525354" in tx and "41542b616e63686f725f7461673d30" in tx
        checks["qom_frames"] = (
            int(final.get("frames-sent", 0)) >= 5
            and int(final.get("frames-injected", 0)) >= 5)
        return checks, observations
    if case == "dmx":
        errors = re.findall(r"DMX_(?:INIT|WRITE)_ERROR", serial)
        tx = (final.get("tx-hex") or "").lower()
        observations["module_errors"] = errors
        observations["qom_tx_hex"] = tx
        if errors:
            observations["blocker"] = (
                "DMX512Unit delegates to cdriver.esp_dmx; the probe records the "
                "guest-side import/init failure instead of faking DMX frames. No "
                "DMX512/RS485 electrical or 250kbps timing claim is made.")
            checks["module_failure_observed"] = True
            return checks, observations
        checks["guest_init_ok"] = "DMX_INIT_ERROR" not in serial
        checks["guest_write_marker"] = "DMX_WRITE 1 255" in serial
        checks["qom_uart_dmx_frame_observed"] = tx.startswith("00ff")
        observations["caveat"] = (
            "The frozen driver executes through cdriver.esp_dmx. Only guest "
            "write markers and any UART bytes exposed by the model are asserted; "
            "DMX512/RS485 electrical behavior and frame decoding are NOT RUN.")
        return checks, observations
    if case == "finger":
        observations["guest_version"] = last_match(r"FINGER_VERSION (\S+)", serial)
        observations["guest_count"] = last_match(r"FINGER_USER_COUNT (-?\d+)", serial)
        observations["guest_capacity"] = last_match(r"FINGER_USER_CAPACITY (-?\d+)", serial)
        tx = (final.get("tx-hex") or "").lower()
        checks["guest_driver_ready"] = "FINGER_INIT_ERROR" not in serial and "FINGER_END" in serial
        checks["guest_version_gate"] = observations["guest_version"] in ("B1.10.00", "B1.07.00")
        checks["qom_version_frames"] = tx.startswith("f526") and "b11000" not in tx
        checks["qom_frames"] = (
            int(final.get("frames-sent", 0)) >= 1
            and int(final.get("frames-injected", 0)) >= 1)
        return checks, observations
    raise ValueError(case)


def run_case(client: Client, args, case: str) -> dict:
    device = CASES[case]
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device_row = next(row for row in matrix["devices"] if row["id"] == device)
    port = port_for(client, device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch6b_probe", files, dirs_exist_ok=True)
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
        "device_id": device, "unit_id": case, "driver_class": CASE_DRIVERS[case],
        "driver_flavor": "reference-firmware-frozen-original-unit-driver",
        "runtime": "qemu", "status": "FAIL", "checks": {},
        "firmware_sha256": sha256(firmware_bytes),
        "base_firmware_sha256": sha256((ROOT / device_row["base"]).read_bytes()),
        "probe_sha256": {path.name: sha256(path.read_bytes()) for path in files.glob("*.py")},
        "runtime_binary_sha256": sha256(BINARY.read_bytes()) if BINARY.is_file() else None,
        "qemu_source_state": QEMU_SOURCE_STATE,
        "official_port": OFFICIAL_PORT[case],
        "runtime_port_substitution": (
            "cores3 PORT.A harness wiring; the official product PinMap connector is "
            + OFFICIAL_PORT[case] + " and is not the admitted runtime host port on cores3")
        if OFFICIAL_PORT[case] != "PORT.A" else None,
        "port": {"id": port["id"], "pins": port["pins"]},
        "initial_inputs": INITIAL[case],
        "qom_samples": [], "serial_markers": {}, "observations": {},
    }
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{device}-batch6b-{case}.bin",
        })
        firmware = client.json("firmware", method="POST", payload={
            "device_id": device, "kind": "merged", "artifact_id": artifact["artifact_id"],
        })
        result["firmware_id"] = firmware["firmware_id"]
        unit_spec = {"id": "external1", "unit_id": case, "port_id": port["id"]}
        if INITIAL[case]:
            unit_spec["initial"] = INITIAL[case]
        session = client.json("sessions", method="POST", payload={
            "device_id": device, "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 420, "ready_marker": START_MARKER, "ready_timeout_seconds": 150,
            "units": [unit_spec],
        })
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created on {device}/{port['id']}", flush=True)
        wait_for(client, session_id, lambda text: START_MARKER in text, 150)
        serial = wait_for(client, session_id, lambda text: END_MARKER[case] in text, 180)
        serial = read_serial(client, session_id)
        result["serial_markers"][case] = serial[-1600:]
        result["checks"]["official_driver_started"] = f"{START_MARKER} {case}" in serial
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        attached = (live.get("units") or [{}])[0]
        result["attached_unit"] = {key: attached.get(key) for key in ("id", "unit_id", "available", "source")}
        final = properties(client, session_id)
        result["qom_samples"].append({"at": utc_now(), "properties": final})
        checks, observations = case_checks(case, serial, final)
        result["checks"].update(checks)
        result["observations"].update(observations)
        if case in EXPECTED_BLOCKED:
            result["expected_blocked"] = True
            result["status"] = "BLOCKED" if all(checks.values()) else "FAIL"
        else:
            result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        screenshot = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(screenshot)
        result["frame"] = {"sha256": sha256(screenshot), "metrics": png_metrics(screenshot)}
        result["checks"]["nonempty_application_frame"] = result["frame"]["metrics"]["unique_colors"] > 1
        if result["status"] == "PASS" and not all(result["checks"].values()):
            result["status"] = "FAIL"
    except Exception as error:  # noqa: BLE001
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
            if result["status"] in {"PASS", "BLOCKED"} and not all(result["checks"].values()):
                result["status"] = "FAIL"
        result["raw_evidence_note"] = (
            "Raw execution artifacts (evidence.zip, frame.png, serial.txt, probe files) stay in the local "
            "ignored .work directory; only concise reports, hashes and reproduction commands are committed.")
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
    raise SystemExit(0 if result["status"] in {"PASS", "BLOCKED"} else 1)


if __name__ == "__main__":
    main()
