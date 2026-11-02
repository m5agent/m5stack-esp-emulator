#!/usr/bin/env python3
"""Validate all twelve Units of the eighth research batch (virtual devices).

One QEMU build (canonical 32-layer chain through 0151) covers the batch-8 A and
B Units. Each case builds a merged reference-firmware image that runs the
firmware's frozen original UIFlow2 driver (or machine.ADC/Pin for the MIC
driver gap) in one visible leased /api/v1 session, provides fixtures as
session-initial Unit inputs, reads controller-backed QOM state, captures the
serial markers, the frame and the evidence ZIP, then stops with purge=0.

Expected BLOCKED cases are recorded honestly: mini-can needs the m5can/TWAI
attachment lane the Unit runtime does not provide, and MIC has no public Unit
driver (the probe uses machine.ADC/Pin and the report keeps the driver-gap
caveat).
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

START_MARKER = "BATCH8_PROBE_START"
BINARY = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
QEMU_SOURCE_STATE = "canonical 75f1d24 + canonical chain 32 layers through 0151"

CASES = {case: "cores3" for case in (
    "pahub-v21", "gps-v11", "gps-sma", "lcd", "mini-can",
    "oled", "mini-oled", "glass2", "nbiot-cn", "lora-e220-920",
    "lorawan-us915", "mic")}
OFFICIAL_PORT = {
    "pahub-v21": "PORT.A", "gps-v11": "PORT.C", "gps-sma": "PORT.C",
    "lcd": "PORT.A", "mini-can": "PORT.C",
    "oled": "PORT.A", "mini-oled": "PORT.A", "glass2": "PORT.A",
    "nbiot-cn": "PORT.C", "lora-e220-920": "PORT.C", "lorawan-us915": "PORT.C",
    "mic": "PORT.B",
}
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "pahub-v21": "PAHUBUnit (PCA9548A mask, 0x70)",
    "gps-v11": "GPSUnit (AT6668 NMEA, 9600 driver)",
    "gps-sma": "GPSUnit (AT6668 NMEA, 9600 driver, SMA antenna)",
    "lcd": "LCDUnit (ST7789V2 I2C command table)",
    "mini-can": "CANUnit (m5can/TWAI)",
    "oled": "OLEDUnit (SH1107, M5.addDisplay)",
    "mini-oled": "MiniOLEDUnit (SSD1315, M5.addDisplay)",
    "glass2": "Glass2Unit (SSD1309, M5.addDisplay)",
    "nbiot-cn": "NBIOTUnit (SIM7020C AT)",
    "lora-e220-920": "LoRaE220JPUnit (E220-900T22S JP)",
    "lorawan-us915": "LoRaWANUnit (ASR650x driver / STM32WLE5 product)",
    "mic": "machine.ADC + machine.Pin (no official Unit driver)",
}
END_MARKER = {
    "pahub-v21": "PAHUB_END", "gps-v11": "GPS_END", "gps-sma": "GPS_END",
    "lcd": "LCD_END", "mini-can": "CAN_END",
    "oled": "DISP_END", "mini-oled": "DISP_END", "glass2": "DISP_END",
    "nbiot-cn": "NBIOT_END", "lora-e220-920": "LR920_END",
    "lorawan-us915": "LW915_END", "mic": "MIC_END",
}
EXPECTED_BLOCKED = {"mini-can", "lorawan-us915"}

GGA = "$GNGGA,024423.000,2242.10772,N,11348.64472,E,1,14,1.2,52.1,M,0.0,M,,*48"
RMC = "$GNRMC,024423.000,A,2242.10772,N,11348.64472,E,0.0,0.0,011122,,,A*XX"
VTG = "$GNVTG,90.5,T,,M,10.0,N,18.52,K,A*XX"
NMEA = "\r\n".join([GGA, RMC, VTG]) + "\r\n"

INITIAL = {
    "pahub-v21": {},
    "gps-v11": {"nmea-lines": NMEA, "baud": 9600},
    "gps-sma": {"nmea-lines": NMEA, "baud": 9600},
    "lcd": {},
    "mini-can": {},
    "oled": {},
    "mini-oled": {},
    "glass2": {},
    "nbiot-cn": {"responses-hex": "4f4b0d0a;4f4b0d0a;4f4b0d0a;4f4b0d0a"},
    "lora-e220-920": {},
    "lorawan-us915": {"responses-hex": "4f4b0d0a"},
    "mic": {"analog-mv": 1600.0, "comparator-level": True},
}


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


def case_checks(case: str, serial: str, final: dict):
    checks, observations = {}, {}
    if case == "pahub-v21":
        observations["read0"] = last_match(r"PAHUB_READ0 (\d+)", serial)
        observations["sel3"] = last_match(r"PAHUB_SEL3 (\d+)", serial)
        observations["sel5"] = last_match(r"PAHUB_SEL5 (\d+)", serial)
        observations["rel3"] = last_match(r"PAHUB_REL3 (\d+)", serial)
        checks["guest_driver_ready"] = "PAHUB_INIT_ERROR" not in serial and "PAHUB_END" in serial
        checks["guest_masks"] = (observations["read0"], observations["sel3"],
                                 observations["sel5"], observations["rel3"]) == ("0", "8", "40", "32")
        checks["qom_channel_mask_0x20"] = final.get("channel-mask") == 0x20
        checks["qom_channel_writes"] = int(final.get("channel-writes", 0)) >= 3
        checks["qom_dip_0x70"] = final.get("dip-address") == 0x70
        return checks, observations
    if case in ("gps-v11", "gps-sma"):
        observations["time"] = last_match(r"GPS_TIME (\S+)", serial)
        observations["date"] = last_match(r"GPS_DATE (\S+)", serial)
        observations["lat"] = last_match(r"GPS_LAT (\S+) ([-\d.]+)", serial)
        observations["lon"] = last_match(r"GPS_LON (\S+) ([-\d.]+)", serial)
        observations["sat"] = last_match(r"GPS_SAT (\d+)", serial)
        observations["alt"] = last_match(r"GPS_ALT (\S+)", serial)
        observations["speed"] = last_match(r"GPS_SPEED (\S+) (\S+)", serial)
        checks["guest_driver_ready"] = "GPS_INIT_ERROR" not in serial and "GPS_END" in serial
        checks["guest_lat"] = bool(observations["lat"] and observations["lat"][0] == "2242.10772N")
        checks["guest_lon"] = bool(observations["lon"] and observations["lon"][0] == "11348.64472E")
        checks["guest_time_utc_plus_8"] = observations["time"] == "10:44:23"
        checks["guest_date"] = observations["date"] == "01/11/22"
        checks["guest_satellites_14"] = observations["sat"] == "14"
        checks["guest_altitude"] = observations["alt"] == "52.1"
        checks["guest_course_speed"] = bool(observations["speed"] and observations["speed"][0] == "18.52"
                                            and observations["speed"][1] == "90.5")
        checks["qom_nmea_fixture"] = (final.get("nmea-lines") or "").startswith("$GNGGA")
        checks["qom_baud_fixture"] = final.get("baud") == 9600
        checks["qom_injected"] = int(final.get("injected-lines", 0)) >= 1
        observations["baud_caveat"] = (
            "Frozen unit/gps.py hard-codes 9600; the product page says 115200. "
            "The guest cannot expose the configured baud, so the 9600 host fixture "
            "is recorded and the page value stays UNRESOLVED/NOT validated.")
        return checks, observations
    if case == "lcd":
        observations["last_cmd"] = final.get("last-command-hex")
        checks["guest_driver_ready"] = "LCD_INIT_ERROR" not in serial and "LCD_END" in serial
        checks["guest_draw_calls"] = "LCD_FILL_SCREEN" in serial and "LCD_FILL_RECT" in serial
        checks["qom_commands"] = int(final.get("commands", 0)) > 0
        checks["qom_pixels"] = int(final.get("pixels-written", 0)) > 0
        checks["qom_framebuffer_crc"] = isinstance(final.get("framebuffer-crc"), int)
        return checks, observations
    if case in ("oled", "mini-oled", "glass2"):
        expected = {"oled": "sh1107", "mini-oled": "ssd1315", "glass2": "ssd1309"}[case]
        observations["controller"] = final.get("display-controller")
        observations["commands"] = final.get("commands")
        observations["data_bytes"] = final.get("data-bytes")
        observations["pixels"] = final.get("pixels-written")
        observations["fb_crc"] = final.get("framebuffer-crc")
        observations["last_cmd"] = final.get("last-command-hex")
        checks["guest_driver_ready"] = "DISP_INIT_ERROR" not in serial and "DISP_END" in serial
        checks["guest_draw_calls"] = "DISP_CLEAR" in serial and "DISP_RECT" in serial
        checks["qom_controller"] = final.get("display-controller") == expected
        checks["qom_commands"] = int(final.get("commands", 0)) > 0
        checks["qom_data_bytes"] = int(final.get("data-bytes", 0)) > 0
        checks["qom_pixels"] = int(final.get("pixels-written", 0)) > 0
        return checks, observations
    if case == "nbiot-cn":
        tx = (final.get("tx-hex") or "").lower()
        observations["tx_hex"] = tx
        checks["guest_driver_ready"] = "NBIOT_INIT_ERROR" not in serial and "NBIOT_READY" in serial
        checks["qom_at_probe"] = "4154" in tx
        checks["qom_reset_or_cfun"] = ("41542b435245534554" in tx or "41542b4346554e3d31" in tx)
        checks["qom_cgsn"] = "41542b4347534e" in tx
        checks["qom_frames"] = int(final.get("frames-sent", 0)) >= 1
        return checks, observations
    if case == "lora-e220-920":
        tx = (final.get("tx-hex") or "").lower()
        observations["tx_hex"] = tx
        observations["config_hex"] = final.get("config-hex")
        checks["guest_driver_ready"] = "LR920_INIT_ERROR" not in serial and "LR920_END" in serial
        checks["guest_setup_ok"] = last_match(r"LR920_SETUP (\d)", serial) == "1"
        checks["guest_sent"] = "LR920_SENT" in serial
        checks["qom_config_frame"] = tx.startswith("c0")
        checks["qom_config_mirror"] = (final.get("config-hex") or "").strip("0") != ""
        checks["qom_send_frame"] = "432107" in tx
        return checks, observations
    if case == "lorawan-us915":
        tx = (final.get("tx-hex") or "").lower()
        observations["tx_hex"] = tx
        observations["blocker"] = (
            "The frozen unit/lorawan.py inherits driver.asr650x.LoRaWAN_470 while "
            "the product is STM32WLE5/RAK3172 (driver/product mismatch). The guest "
            "constructor and get_DevAddr/get_DevEui/get_AppEui calls complete, but "
            "no AT bytes reach the attached Unit UART lane (tx-hex stays empty), so "
            "the byte layer cannot be asserted and no PASS is claimed. US915 "
            "join/OTAA/ABP/duty-cycle/FCC/RF are NOT RUN.")
        checks["guest_driver_constructed"] = "LW915_INIT_ERROR" not in serial and "LW915_READY" in serial
        checks["byte_layer_not_observed"] = not tx
        return checks, observations
    if case == "mini-can":
        errors = re.findall(r"CAN_(?:INIT|SEND)_ERROR", serial)
        observations["module_errors"] = errors
        observations["blocker"] = (
            "CANUnit needs the m5can/TWAI attachment lane; the Unit runtime does "
            "not provide CAN frame attachment, so the probe records the guest-side "
            "failure instead of fabricating frames. CAN electrical/arbitration are NOT RUN.")
        checks["module_failure_observed"] = bool(errors)
        return checks, observations
    if case == "mic":
        observations["guest_raw"] = last_match(r"MIC_ADC_RAW (\d+)", serial)
        observations["guest_uv"] = last_match(r"MIC_ADC_UV (-?\d+)", serial)
        observations["guest_level"] = last_match(r"MIC_LEVEL (\d+)", serial)
        checks["guest_adc_path"] = observations["guest_raw"] is not None
        checks["guest_comparator"] = observations["guest_level"] == "1"
        checks["guest_read_uv_boundary"] = ("MIC_ADC_UV_ERROR" in serial) or observations["guest_uv"] is not None
        checks["qom_analog_mv"] = abs(float(final.get("analog-mv", 0)) - 1600.0) <= 0.01
        checks["qom_digital_level"] = final.get("digital-level") is True
        checks["qom_adc_samples"] = int(final.get("adc-samples", 0)) >= 1
        observations["driver_gap_caveat"] = (
            "U096 has no public Unit MIC driver: the guest path is machine.ADC on "
            "the white analog output plus machine.Pin on the yellow comparator. "
            "Acoustic response/threshold/SNR are NOT RUN and are not claimed.")
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
    shutil.copytree(Path(__file__).parent / "batch8_probe", files, dirs_exist_ok=True)
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
        "schema_version": 1, "date": utc_now(), "validation": "virtual-device validation",
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
            "X-Artifact-Name": f"{device}-batch8-{case}.bin",
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
        wait_for(client, session_id, lambda text: f"{START_MARKER} {case}" in text, 150)
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
        if result["status"] in ("PASS", "BLOCKED") and not all(result["checks"].values()):
            result["status"] = "FAIL"
    except Exception as error:  # noqa: BLE001
        result["error"] = str(error)
        if case in EXPECTED_BLOCKED and "contract is incomplete" in str(error):
            result["expected_blocked"] = True
            result["blocker"] = (
                "The mini-can Unit model/state contract is incomplete in the Unit "
                "runtime (CAN attachment/frame lane gap); the session was refused "
                "before guest execution, so no frame is fabricated or asserted.")
            result["status"] = "BLOCKED"
        else:
            result["status"] = "FAIL"
        if session_id:
            try:
                result["serial_markers"][case] = read_serial(client, session_id)[-1600:]
                result["qom_samples"].append({"at": utc_now(), "properties": properties(client, session_id)})
            except Exception as capture_error:  # noqa: BLE001
                result["capture_error"] = str(capture_error)
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
            if result["status"] in ("PASS", "BLOCKED") and not all(result["checks"].values()):
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
    parser.add_argument("--api-url", default="http://127.0.0.1:8801")
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.api_url)
    result = run_case(client, args, args.case)
    raise SystemExit(0 if result["status"] in {"PASS", "BLOCKED"} else 1)


if __name__ == "__main__":
    main()
