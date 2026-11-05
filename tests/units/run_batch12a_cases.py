#!/usr/bin/env python3
"""Raw-I2C guest evidence for the seven driver-gap batch-12a Units.

Each case builds a merged reference-firmware image that runs a raw machine.I2C
probe (no official Unit driver exists) in one visible leased /api/v1 session,
reads controller-backed QOM state, captures serial markers, the frame and the
evidence ZIP, then stops with purge=0. Only byte/register-level virtual data
plane evidence is claimed; mechanical/electrical/optical/physics are NOT RUN.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
from run_batch6_cases import (  # noqa: E402
    Client, utc_now, sha256, read_serial, properties, wait_for, last_match,
)
from run_profile_ui_test import build_image  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402

START_MARKER = "BATCH12A_PROBE_START"

QEMU_SOURCE_STATE = "canonical 75f1d24 + canonical chain 39 layers through 0159"

CASES = {"byteswitch": "cores3", "bytebutton": "cores3", "step16": "cores3",
         "timerpwr": "cores3", "mq": "cores3", "8servos2-i2c": "cores3",
         "cardkb2": "cores3"}
DRIVERS = {
    "byteswitch": "raw machine.I2C register probe (driver-gap: no official Unit driver)",
    "bytebutton": "raw machine.I2C register probe (driver-gap: no official Unit driver)",
    "step16": "raw machine.I2C register probe (driver-gap: no official Unit driver)",
    "timerpwr": "raw machine.I2C register probe (driver-gap: no official Unit driver)",
    "mq": "raw machine.I2C register probe (driver-gap: no official Unit driver)",
    "8servos2-i2c": "raw machine.I2C register probe (driver-gap: no official Unit driver)",
    "cardkb2": "raw machine.I2C legacy-subset probe (driver-gap: no official Unit driver)",
}
END_MARKER = {"byteswitch": "BU_END", "bytebutton": "BU_END", "step16": "ST_END",
              "timerpwr": "TP_END", "mq": "MQ_END", "8servos2-i2c": "SV_END",
              "cardkb2": "CK_END"}
INITIAL = {
    "byteswitch": {"state-bitmap": 0xA5},
    "bytebutton": {"state-bitmap": 0x5A},
    "step16": {"position": 7},
    "timerpwr": {"battery-mv": 3700.0, "usb-v": 5.0, "charging": True},
    "mq": {"sensor-mv": 600.0, "ref-mv": 1100.0, "ntc-ohm": 10000.0},
    "8servos2-i2c": {"rotary": 3},
    "cardkb2": {"key-code": 113},
}


def port_for(client: Client, device_id: str, unit_id: str) -> dict:
    registry = client.json(f"units?device_id={device_id}")
    host = registry["hosts"][0]
    unit_rows = {row["id"]: row for row in registry["units"]}
    admission = unit_rows[unit_id]["host_admission"]
    if not admission["admitted"]:
        raise RuntimeError(f"{unit_id} is not admitted on {device_id}: {admission}")
    port_id = "port-a"
    port = next(p for p in host["ports"] if p["id"] == port_id)
    if port_id not in admission["port_ids"]:
        raise RuntimeError(f"{unit_id} admission does not include {port_id}: {admission}")
    return port


def case_checks(case, serial, final):
    checks, obs = {}, {}
    if case in ("byteswitch", "bytebutton"):
        bitmap = 0xA5 if case == "byteswitch" else 0x5A
        obs["bitmap"] = last_match(r"BU_BITMAP (\d+)", serial)
        obs["ch0"] = last_match(r"BU_CH0 (\d+)", serial)
        obs["ch7"] = last_match(r"BU_CH7 (\d+)", serial)
        obs["brightness"] = last_match(r"BU_BRIGHTNESS_READBACK (\d+)", serial)
        obs["mode"] = last_match(r"BU_MODE_READBACK (\d+)", serial)
        obs["rgb"] = last_match(r"BU_RGB_READBACK ([0-9a-f]+)", serial)
        obs["irq"] = last_match(r"BU_IRQ_READBACK (\d+)", serial)
        checks["guest_bitmap_fixture"] = obs["bitmap"] == str(bitmap)
        checks["guest_channel_bits"] = obs["ch0"] == str(bitmap & 1) and obs["ch7"] == str((bitmap >> 7) & 1)
        checks["guest_brightness_readback"] = obs["brightness"] == "66"
        checks["guest_mode_readback"] = obs["mode"] == "1"
        checks["guest_rgb_roundtrip"] = obs["rgb"] == "112233"
        checks["guest_irq_enable_readback"] = obs["irq"] == "1"
        checks["qom_bitmap"] = final.get("state-bitmap") == bitmap
        checks["qom_rgb_hex"] = (final.get("rgb-hex") or "").startswith("332211")
        checks["qom_save_count"] = int(final.get("save-count", 0)) >= 1
        checks["qom_irq_count"] = int(final.get("irq-count", 0)) >= 1
        checks["qom_fw"] = final.get("firmware-version") == 1
    elif case == "step16":
        obs["position"] = last_match(r"ST_POSITION (\d+)", serial)
        obs["direction"] = last_match(r"ST_DIRECTION_READBACK (\d+)", serial)
        obs["brightness"] = last_match(r"ST_BRIGHTNESS_READBACK (\d+)", serial)
        obs["rgb"] = last_match(r"ST_RGB_READBACK ([0-9a-f]+)", serial)
        checks["guest_position_fixture"] = obs["position"] == "7"
        checks["guest_direction_readback"] = obs["direction"] == "0"
        checks["guest_brightness_readback"] = obs["brightness"] == "42"
        checks["guest_rgb_roundtrip"] = obs["rgb"] == "123456"
        checks["qom_position"] = final.get("position") == 7
        checks["qom_direction"] = final.get("direction") == 0
        checks["qom_rgb"] = final.get("rgb") == 0x123456
        checks["qom_save_count"] = int(final.get("save-count", 0)) >= 1
    elif case == "timerpwr":
        obs["buttons"] = last_match(r"TP_BUTTONS ([0-9a-f]+)", serial)
        obs["battery"] = last_match(r"TP_BATTERY_RAW ([0-9a-f]+)", serial)
        obs["charging"] = last_match(r"TP_CHARGING (\d+)", serial)
        obs["grove"] = last_match(r"TP_GROVE_OUT_READBACK (\d+)", serial)
        obs["backlight"] = last_match(r"TP_BACKLIGHT_READBACK (\d+)", serial)
        obs["schedule"] = last_match(r"TP_SCHEDULE_READBACK ([0-9a-f]+)", serial)
        checks["guest_buttons_idle"] = obs["buttons"] == "0000"
        checks["guest_battery_le32"] = obs["battery"] == "72010000"
        checks["guest_charging_fixture"] = obs["charging"] == "1"
        checks["guest_grove_output_readback"] = obs["grove"] == "1"
        checks["guest_backlight_readback"] = obs["backlight"] == "0"
        checks["guest_schedule_readback"] = obs["schedule"] == "0c2200"
        checks["qom_grove_output"] = final.get("grove-output") is True
        checks["qom_backlight"] = final.get("backlight") == 0
        checks["qom_schedule_on"] = final.get("schedule-on") == "12:34"
        checks["qom_charging"] = final.get("charging") is True
    elif case == "mq":
        obs["valid"] = last_match(r"MQ_VALID (\d+)", serial)
        obs["adc8"] = last_match(r"MQ_ADC8 (\d+)", serial)
        obs["adc12"] = last_match(r"MQ_ADC12_RAW ([0-9a-f]+)", serial)
        obs["ntc"] = last_match(r"MQ_NTC_OHM_RAW ([0-9a-f]+)", serial)
        obs["ref"] = last_match(r"MQ_REF_RAW ([0-9a-f]+)", serial)
        obs["mode"] = last_match(r"MQ_MODE_READBACK (\d+)", serial)
        obs["led"] = last_match(r"MQ_LED_READBACK (\d+)", serial)
        obs["heat"] = last_match(r"MQ_HEAT_READBACK (\d+)", serial)
        checks["guest_valid_driver_polarity"] = obs["valid"] == "1"
        checks["guest_adc8_derived"] = obs["adc8"] == "139"
        checks["guest_adc12_le"] = obs["adc12"] == "ba08"
        checks["guest_ntc_ohm_le"] = obs["ntc"] == "1027"
        checks["guest_ref_mv_le"] = obs["ref"] == "4c04"
        checks["guest_mode_led_heat_readback"] = (obs["mode"], obs["led"], obs["heat"]) == ("1", "1", "60")
        checks["qom_adc12"] = final.get("adc12") == 2234
        checks["qom_valid_raw_driver_semantics"] = final.get("valid-raw") == 1
        checks["qom_mode_led_heat"] = (final.get("mq-mode"), final.get("led"), final.get("heat-high")) == (1, 1, 60)
        obs["valid_caveat"] = ("Driver unit/mq.py get_valid_tags() treats 1 as valid while "
                               "the protocol PDF says 0 = valid; the model implements the driver "
                               "semantics and this conflict remains UNRESOLVED.")
    elif case == "8servos2-i2c":
        obs["scan"] = last_match(r"SV_SCAN \[([^\]]*)\]", serial)
        obs["uid"] = last_match(r"SV_UID ([0-9a-f]+)", serial)
        obs["mode"] = last_match(r"SV_MODE_READBACK (\d+)", serial)
        obs["servo"] = last_match(r"SV_SERVO_READBACK ([0-9a-f]+)", serial)
        obs["pwm"] = last_match(r"SV_PWM_READBACK ([0-9a-f]+)", serial)
        obs["rgb"] = last_match(r"SV_RGB_READBACK ([0-9a-f]+)", serial)
        checks["guest_rotary_address_visible"] = obs["scan"] is not None and "40" in obs["scan"]
        checks["guest_uid_fixture"] = obs["uid"] == "101112131415161718191a1b"
        checks["guest_mode_readback"] = obs["mode"] == "2"
        checks["guest_servo_roundtrip"] = obs["servo"] == "0a0b0c0d0e0f1011"
        checks["guest_pwm_roundtrip"] = obs["pwm"] == "3233343536373839"
        checks["guest_rgb_roundtrip"] = obs["rgb"] == "01020304"
        checks["qom_rotary_address"] = (final.get("rotary"), final.get("i2c-address")) == (3, 0x28)
        checks["qom_servo_hex"] = (final.get("servo-angles-hex") or "").startswith("0a0b0c0d")
        checks["qom_pwm_hex"] = (final.get("pwm-hex") or "").startswith("32333435")
    elif case == "cardkb2":
        obs["key"] = last_match(r"CK_KEY (0x[0-9a-f]+)", serial)
        obs["fw"] = last_match(r"CK_FW (\d+)", serial)
        checks["guest_key_code_fixture"] = obs["key"] == "0x71"
        checks["guest_firmware_version"] = obs["fw"] == "1"
        checks["qom_key_code"] = final.get("key-code") == 113
        checks["qom_firmware_version"] = final.get("firmware-version") == 1
        obs["caveat"] = ("CardKB2 UART AA03 frame mode, v2 report, BLE HID and ESP-NOW "
                         "are separate attachment kinds and are NOT RUN on this I2C model.")
    else:
        raise ValueError(case)
    return checks, obs


def run_case(client: Client, args, case: str) -> dict:
    device = CASES[case]
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    row = next(r for r in matrix["devices"] if r["id"] == device)
    port = port_for(client, device, case)
    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch12a_probe", files, dirs_exist_ok=True)
    (files / "probe_config.py").write_text(
        f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n",
        encoding="utf-8")
    image = build_image(SimpleNamespace(
        base=ROOT / row["base"], flash_size=int(row["flash_size"], 0), files_dir=files,
        mklittlefs=None, preserve_vfs=False, vfs_offset=int(row["vfs_offset"], 0),
        vfs_size=int(row["vfs_size"], 0), prog_size=32, out_dir=output))
    firmware = image.read_bytes()
    result = {"schema_version": 1, "date": utc_now(), "validation": "virtual-device validation",
              "scope": "Unit raw-I2C register data plane through a visible Device Service session; not hardware",
              "device_id": device, "unit_id": case, "driver_class": DRIVERS[case],
              "driver_flavor": "guest raw machine.I2C probe (driver-gap; no official Unit driver)",
              "runtime": "qemu", "status": "FAIL", "checks": {},
              "firmware_sha256": sha256(firmware),
              "base_firmware_sha256": sha256((ROOT / row["base"]).read_bytes()),
              "probe_sha256": {p.name: sha256(p.read_bytes()) for p in files.glob("*.py")},
              "runtime_binary_sha256": None,
              "fixture_source_baseline": QEMU_SOURCE_STATE,
              "official_port": "PORT.A",
              "port": {"id": port["id"], "pins": port["pins"]},
              "initial_inputs": INITIAL[case],
              "qom_samples": [], "serial_markers": {}, "observations": {},
              "driver_gap": "no official Unit driver exists for this product; the guest probe uses machine.I2C directly"}
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{device}-batch12a-{case}.bin"})
        fw = client.json("firmware", method="POST", payload={
            "device_id": device, "kind": "merged", "artifact_id": artifact["artifact_id"]})
        result["firmware_id"] = fw["firmware_id"]
        spec = {"id": "external1", "unit_id": case, "port_id": port["id"]}
        if INITIAL[case]:
            spec["initial"] = INITIAL[case]
        session = client.json("sessions", method="POST", payload={
            "device_id": device, "firmware_id": fw["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 420, "ready_marker": START_MARKER, "ready_timeout_seconds": 150,
            "units": [spec]})
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created on {device}/{port['id']}", flush=True)
        wait_for(client, session_id, lambda t: f"{START_MARKER} {case}" in t, 150)
        wait_for(client, session_id, lambda t: END_MARKER[case] in t, 180)
        serial = read_serial(client, session_id)
        result["serial_markers"][case] = serial[-1600:]
        result["checks"]["guest_probe_started"] = f"{START_MARKER} {case}" in serial
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        final = properties(client, session_id)
        result["qom_samples"].append({"at": utc_now(), "properties": final})
        checks, obs = case_checks(case, serial, final)
        result["checks"].update(checks)
        result["observations"].update(obs)
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        shot = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(shot)
        result["frame"] = {"sha256": sha256(shot), "metrics": png_metrics(shot)}
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
                result["stop"] = {"stop_state": stopped.get("state"),
                                  "history_state": history.get("state"),
                                  "history_retained": history.get("session_id") == session_id}
                result["checks"]["stopped_with_history"] = (
                    stopped.get("state") in {"stopped", "failed"}
                    and history.get("state") in {"stopped", "failed"})
            except Exception as error:  # noqa: BLE001
                result["stop_error"] = str(error)
                result["checks"]["stopped_with_history"] = False
            if result["status"] == "PASS" and not all(result["checks"].values()):
                result["status"] = "FAIL"
        result["raw_evidence_note"] = (
            "Raw execution artifacts stay in local ignored .work; only concise reports, hashes "
            "and reproduction commands are committed.")
        client.finalize_result(result)
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"{case}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8804")
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.api_url)
    result = run_case(client, args, args.case)
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
