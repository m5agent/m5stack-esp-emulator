#!/usr/bin/env python3
"""Validate the eight batch-7 Units with guest/Device Service evidence.

One QEMU build (canonical chain through 0145, 28 layers) covers the eight
contracts that were implemented in batch7a/0145: mini-tof-90, hbridge-v11,
cardkb-original, env-ii, hex, catm, catm-gnss and lorawan-cn470. `can` is
BLOCKED by the known CAN attachment gap and is recorded in the summary without
a session; mini-bps-v11/mini-pdm remain DEFERRED and are not probed.

Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 driver in one visible leased `/api/v1` session, provides
fixtures as session-initial Unit inputs (or unit-input where coordination is
needed), reads controller-backed state, captures serial/frame/evidence ZIP
before stopping with `purge=0`.
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

MARKER = "BATCH7_PROBE_READY"

QEMU_SOURCE_STATE = ("canonical 75f1d24 + canonical chain 28 layers "
                     "(0120-0145, incl. 0143 batch7 A and 0145 batch7 B)")

CASES = {
    "mini-tof-90": "cores3", "hbridge-v11": "cores3",
    "cardkb-original": "cores3", "env-ii": "cores3",
    "hex": "cores3", "catm": "cores3", "catm-gnss": "cores3",
    "lorawan-cn470": "cores3",
}
OFFICIAL_PORT = {
    "mini-tof-90": "PORT.A", "hbridge-v11": "PORT.A",
    "cardkb-original": "PORT.A", "env-ii": "PORT.A",
    "hex": "PORT.B", "catm": "PORT.C", "catm-gnss": "PORT.C",
    "lorawan-cn470": "PORT.C",
}
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "mini-tof-90": "ToFUnit (VL53L0X 0x29)",
    "hbridge-v11": "HbridgeUnit (STM32F030 0x20)",
    "cardkb-original": "CardKBUnit (0x5F)",
    "env-ii": "ENVUnit(ENV_II) SHT30 0x44 + BMP280 0x76",
    "hex": "RGBUnit/SK6812 37 LEDs (unit driver gap)",
    "catm": "CATMUnit (SIM7080G UART fixture)",
    "catm-gnss": "CATMGNSSUnit (SIM7080G GNSS UART fixture)",
    "lorawan-cn470": "LoRaWANUnit (ASR650x wrapper / STM32WLE5 product)",
}
OK = "4f4b0d0a"  # "OK\r\n"
INITIAL = {
    "mini-tof-90": {"distance-mm": 500},
    "hbridge-v11": {"adc-mv": 1650, "vin-current-a": 0.5},
    "cardkb-original": {},
    "env-ii": {"temperature-c": 31.5, "humidity-pct": 45.5, "pressure-pa": 100500},
    "hex": {},
    "catm": {"responses-hex": ";".join([
        OK, OK, "3132333435363738393031323334350d0a" + OK,
    ])},
    "catm-gnss": {"responses-hex": ";".join([
        OK, OK,
        "2b43474e535057523a20310d0a4f4b0d0a",
        OK,
        "2b43474e53494e463a20312c312c32303236313130333031303230332e3030302c33312e3530303030302c3132312e3530303030302c31302e302c302e302c302e302c302c302c302c302c302c302c302c300d0a4f4b0d0a",
    ])},
    "lorawan-cn470": {"responses-hex": ";".join([
        OK, OK, OK, OK,
        "4f4b2b53454e543a0d0a4f4b0d0a",  # OK+SENT:
OK

    ])},
}
CW_MODE2 = "41542b43574f524b4d4f44453d320d0a"
CW_MODE1 = "41542b43574f524b4d4f44453d310d0a"
AT = "41540d0a"
ATE0 = "415445300d0a"
CGNSPWR = "41542b43474e535057523d310d0a"


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


def run_case(client: Client, args, case: str) -> dict:
    device = CASES[case]
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device_row = next(row for row in matrix["devices"] if row["id"] == device)
    port = port_for(client, device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch7_probe", files, dirs_exist_ok=True)
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
        "device_id": device, "unit_id": case,
        "driver_class": CASE_DRIVERS[case],
        "driver_flavor": "reference-firmware-frozen-original-unit-driver",
        "runtime": "qemu", "status": "FAIL", "checks": {},
        "firmware_sha256": sha256(firmware_bytes),
        "base_firmware_sha256": sha256((ROOT / device_row["base"]).read_bytes()),
        "probe_sha256": {path.name: sha256(path.read_bytes()) for path in files.glob("*.py")},
        "runtime_binary_sha256": None,
        "fixture_source_baseline": QEMU_SOURCE_STATE,
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
            "X-Artifact-Name": f"{device}-batch7-{case}.bin",
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
            "ttl_seconds": 300, "ready_marker": MARKER, "ready_timeout_seconds": 120,
            "units": [unit_spec],
        })
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created on {device}/{port['id']}", flush=True)
        serial = wait_for(client, session_id, lambda text: MARKER in text, 150)
        result["checks"]["official_driver_ready"] = True
        result["serial_markers"]["ready"] = serial[serial.index(MARKER):serial.index(MARKER) + len(MARKER)]
        live = client.json(f"sessions/{session_id}/units")
        result["checks"]["live_controller_state"] = live.get("source") == "live" and bool(live.get("units"))
        attached = (live.get("units") or [{}])[0]
        result["attached_unit"] = {key: attached.get(key) for key in ("id", "unit_id", "available", "source")}

        if case == "mini-tof-90":
            serial = wait_for(client, session_id, lambda text: "I2C_TOF_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["mini-tof-90"] = serial[-700:]
            rng = last_match(r"I2C_TOF_RANGE (\d+)", serial)
            ready = last_match(r"I2C_TOF_DATA_READY (\d)", serial)
            final, samples = wait_properties(client, session_id,
                                             lambda p: int(p.get("transactions", 0)) > 0,
                                             label="tof qom")
            result["qom_samples"].extend(samples)
            result["observations"]["mini_tof_90"] = {
                "guest_range": rng, "guest_data_ready": ready,
                "qom": {k: final.get(k) for k in ("distance-mm", "transactions",
                                                  "read-bytes", "written-bytes")},
                "boundary": "90-degree laser mounting only; VL53L0X optics/940nm/range accuracy and "
                            "3-200cm physics are NOT RUN; 0x29 conflicts with tof/tof4m/color and the "
                            "official PORT.A connector is the only admitted port.",
            }
            result["checks"]["guest_range_fixture"] = rng == "500"
            result["checks"]["guest_data_ready_observed"] = ready in ("0", "1")
            result["checks"]["qom_distance_fixture"] = final.get("distance-mm") == 500
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "hbridge-v11":
            serial = wait_for(client, session_id, lambda text: "I2C_HBRIDGE_STATUS" in text, 90)
            serial = wait_for(client, session_id, lambda text: "I2C_HBRIDGE_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["hbridge-v11"] = serial[-800:]
            adc = last_match(r"I2C_HBRIDGE_ADC (\d+) (\d+)", serial)
            current = last_match(r"I2C_HBRIDGE_CURRENT (-?[\d.]+)", serial)
            status = last_match(r"I2C_HBRIDGE_STATUS (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("direction", 0)) == 1 and int(p.get("pwm-frequency-hz", 0)) == 1000,
                label="hbridge qom")
            result["qom_samples"].extend(samples)
            result["observations"]["hbridge_v11"] = {
                "guest_adc16_8": adc, "guest_vin_current": current, "guest_status": status,
                "qom": {k: final.get(k) for k in ("adc-mv", "vin-current-a", "direction",
                                                  "pwm-duty-pct", "pwm-frequency-hz",
                                                  "i2c-address", "transactions")},
                "boundary": "v1.1 reuses the 0x20 STM32F030 model; motor/RZ7899/INA199 electrical "
                            "behavior, real load current and protection are NOT RUN; 0x20 conflicts "
                            "with hbridge U160.",
            }
            result["checks"]["guest_adc_fixture"] = adc == ("2048", "128")
            result["checks"]["guest_vin_current"] = bool(current and abs(float(current) - 0.5) <= 0.01)
            result["checks"]["guest_identity"] = status == ("1", "32")
            result["checks"]["qom_direction_set"] = final.get("direction") == 1
            result["checks"]["qom_pwm_16bit"] = abs(float(final.get("pwm-duty-pct", 0)) - 50.0) <= 0.5
            result["checks"]["qom_pwm_frequency"] = final.get("pwm-frequency-hz") == 1000
            result["checks"]["qom_fixtures"] = (
                final.get("adc-mv") == 1650 and abs(float(final.get("vin-current-a", 0)) - 0.5) <= 0.01)
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "cardkb-original":
            inject(client, session_id, {"keycode": 0x71})
            serial = wait_for(client, session_id, lambda text: "I2C_CARDKB_KEY" in text, 90)
            serial = wait_for(client, session_id, lambda text: "I2C_CARDKB_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["cardkb-original"] = serial[-500:]
            key = last_match(r"I2C_CARDKB_KEY (\d+)", serial)
            final, samples = wait_properties(client, session_id,
                                             lambda p: int(p.get("input-events", 0)) >= 1,
                                             label="cardkb qom")
            result["qom_samples"].extend(samples)
            seen_keycode = any(s["properties"].get("keycode") == 113 for s in samples)
            result["observations"]["cardkb_original"] = {
                "guest_key": key, "qom": {k: final.get(k) for k in ("keycode", "queued-keys",
                                                                    "key-overflows", "modifier-mode",
                                                                    "i2c-address", "input-events")},
                "boundary": "U035 original vs U035-B MEGA8A/MEGA328P difference unresolved; keyboard "
                            "matrix/key travel/RGB LED are NOT RUN; 0x5F conflicts with cardkb.",
            }
            result["checks"]["guest_key_fixture"] = key == "113"
            result["checks"]["qom_key_event"] = int(final.get("input-events", 0)) >= 1
            result["checks"]["no_key_overflow"] = int(final.get("key-overflows", 0)) == 0

        elif case == "env-ii":
            serial = wait_for(client, session_id, lambda text: "I2C_ENV2_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["env-ii"] = serial[-600:]
            values = last_match(r"I2C_ENV2 (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("transactions", 0)) > 0,
                label="env-ii qom")
            result["qom_samples"].extend(samples)
            result["observations"]["env_ii"] = {
                "guest_temperature_humidity_pressure": values,
                "qom": {k: final.get(k) for k in ("temperature-c", "humidity-pct", "pressure-pa",
                                                  "transactions", "read-bytes", "written-bytes")},
                "boundary": "SHT30 0x44 + BMP280 0x76 dual-slave path; sensor accuracy/self-heating and "
                            "pressure physics are NOT RUN; 0x44 conflicts with env/env-iv and 0x76 with "
                            "bps/env/env-iv.",
            }
            result["checks"]["guest_temperature"] = bool(values and abs(float(values[0]) - 31.5) <= 0.01)
            result["checks"]["guest_humidity"] = bool(values and abs(float(values[1]) - 45.5) <= 0.01)
            result["checks"]["guest_pressure"] = bool(values and abs(float(values[2]) - 1005.0) <= 0.01)
            result["checks"]["qom_fixtures_exact"] = (
                abs(float(final.get("temperature-c", 0)) - 31.5) <= 0.01
                and abs(float(final.get("humidity-pct", 0)) - 45.5) <= 0.01
                and abs(float(final.get("pressure-pa", 0)) - 100500) <= 0.01)
            result["checks"]["i2c_transactions_observed"] = int(final.get("transactions", 0)) > 0

        elif case == "hex":
            serial = wait_for(client, session_id, lambda text: "GPIO_HEX_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["hex"] = serial[-500:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: len(p.get("led-rgb") or []) == 37 and (p.get("led-rgb") or [0])[0] == 0x112233,
                label="hex qom")
            result["qom_samples"].extend(samples)
            led = final.get("led-rgb") or []
            result["observations"]["hex"] = {
                "driver_gap": "public UIFlow2 has no unit/hex.py; probe uses the generic "
                              "RGBUnit/SK6812 37-LED path (explicit driver gap).",
                "qom": {k: final.get(k) for k in ("led-rgb", "led-frames", "incomplete-frames",
                                                  "output-transitions")},
                "boundary": "SK6812 vs WS2812C timing/order unresolved; LED optics/power/cascade are "
                            "NOT RUN; official PORT.B is substituted by cores3 PORT.A harness.",
            }
            result["checks"]["generic_sk6812_driver_used"] = "GPIO_HEX_DRIVER generic-SK6812-37" in serial
            result["checks"]["guest_frame_written"] = "GPIO_HEX_WRITTEN" in serial
            result["checks"]["qom_37_leds_match"] = led == [0x112233] * 37
            result["checks"]["qom_led_frames_observed"] = int(final.get("led-frames", 0)) >= 1
            result["checks"]["no_incomplete_frames"] = int(final.get("incomplete-frames", 0)) == 0

        elif case in ("catm", "catm-gnss", "lorawan-cn470"):
            end_marker = {"catm": "UART_CATM_END", "catm-gnss": "UART_CATMGNSS_END",
                          "lorawan-cn470": "UART_LORAWAN_END"}[case]
            serial = wait_for(client, session_id, lambda text: end_marker in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"][case] = serial[-1200:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("frames-sent", 0)) >= 2,
                label=f"{case} qom")
            result["qom_samples"].extend(samples)
            tx = final.get("tx-hex") or ""
            result["observations"][case] = {
                "guest_ready": end_marker.replace("_END", "_READY") in serial,
                "guest_lorawan_sent": "UART_LORAWAN_SENT" in serial,
                "tx_hex": tx,
                "qom": {k: final.get(k) for k in ("responses-hex", "tx-hex", "frames-sent",
                                                  "frames-injected", "transactions")},
                "boundary": ("UART fixture responder only; no AT/GNSS/LoRaWAN protocol decode, no "
                             "RF/cellular/SIM/network claim. Official PORT.C is substituted by cores3 "
                             "PORT.A harness."),
            }
            result["checks"]["guest_driver_ran"] = end_marker.replace("_END", "_READY") in serial
            result["checks"]["qom_tx_bytes"] = len(tx) > 0
            result["checks"]["frames_counted"] = (
                int(final.get("frames-sent", 0)) >= 2 and int(final.get("frames-injected", 0)) >= 1)
            if case == "catm":
                result["checks"]["qom_at_and_ate0"] = AT in tx and ATE0 in tx
                result["checks"]["no_rf_claim"] = True
            elif case == "catm-gnss":
                result["checks"]["qom_at_ate0_and_gnss"] = (
                    AT in tx and ATE0 in tx and CGNSPWR in tx)
                result["checks"]["gnss_parse_not_asserted"] = True
            else:
                result["checks"]["qom_workmode_bytes"] = CW_MODE2 in tx and CW_MODE1 in tx
                result["checks"]["guest_send_frame"] = "41542b445452583d" in tx
                result["checks"]["guest_lorawan_sent"] = "UART_LORAWAN_SENT" in serial
                result["checks"]["driver_product_mismatch_recorded"] = True

        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        screenshot = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(screenshot)
        result["frame"] = {"sha256": sha256(screenshot), "metrics": png_metrics(screenshot)}
        result["checks"]["nonempty_application_frame"] = result["frame"]["metrics"]["unique_colors"] > 1
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as error:  # noqa: BLE001 - failure preserved as evidence
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
        result["raw_evidence_note"] = (
            "Raw execution artifacts (evidence.zip, frame.png, serial.txt, probe files) stay in the local "
            "ignored .work directory; only concise reports, hashes and reproduction commands are committed.")
        client.finalize_result(result)
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
