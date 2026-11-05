#!/usr/bin/env python3
"""Validate the six Units of the sixth research batch (first half).

One QEMU build (canonical chain through 0141 + the 0144 evidence fix) covers
mini-scales, rgb-led-strip-50cm, op180, synth, mini-imu and env-pro. Each case
builds a merged reference-firmware image that runs the firmware's frozen
original UIFlow2 driver in one visible leased `/api/v1` session, provides
fixtures as session-initial Unit inputs (or unit-input where coordination is
needed), reads controller-backed state, captures serial markers, the frame and
the evidence ZIP before stopping with `purge=0`.

ENV-Pro note: the BME68x compensation inverse is not modeled, so only the
chip/variant identity and raw field bytes are asserted; guest-decoded
temperature/humidity/pressure are observation-only and are never a PASS check.
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

MARKER = "BATCH6_PROBE_READY"

QEMU_SOURCE_STATE = ("canonical 75f1d24 + canonical chain 22 layers "
                     "(0120-0141, incl. 0140 batch6 A) "
                     "+ 0144-unit-batch6-evidence-fixes")

CASES = {
    "mini-scales": "cores3", "rgb-led-strip-50cm": "cores3", "op180": "cores3",
    "synth": "cores3", "mini-imu": "cores3", "env-pro": "cores3",
}
OFFICIAL_PORT = {
    "mini-scales": "PORT.A", "mini-imu": "PORT.A", "env-pro": "PORT.A",
    "rgb-led-strip-50cm": "PORT.B", "op180": "PORT.B", "synth": "PORT.C",
}
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "mini-scales": "MiniScaleUnit (0x26)",
    "rgb-led-strip-50cm": "RGBUnit(SK6812, 30 LEDs)",
    "op180": "OPUnit(Button, active-low)",
    "synth": "SynthUnit (SAM2695 MIDI TX-only)",
    "mini-imu": "IMUUnit (MPU6886, 0x68)",
    "env-pro": "ENVPROUnit (BME688, 0x77; raw fields only)",
}
INITIAL = {
    "mini-scales": {"adc-raw": 123456, "weight-g": 123.5, "button-pressed": True},
    "rgb-led-strip-50cm": {},
    "op180": {"digital-level": True},
    "synth": {},
    "mini-imu": {"accel-x-g": 1.5, "accel-y-g": -0.5, "accel-z-g": 1.0,
                 "gyro-x-dps": 12.5, "gyro-y-dps": -25.0, "gyro-z-dps": 50.0,
                 "temperature-c": 31.25, "accel-range": 2, "gyro-range": 250},
    "env-pro": {"temperature-c": 31.5, "humidity-pct": 45.5,
                "pressure-pa": 100500, "gas-resistance-ohm": 500000,
                "data-ready": True},
}
# 0140 BME68X synthetic field encoding (see m5_unit_i2c_sensors.c bme68x_refresh):
# 0x1D ready, 0x1E page, 0x1F..0x21 pressure*16 BE24, 0x22..0x24 (temp+40)*16 BE24,
# 0x25..0x26 humidity/100*65535 BE16.
ENVPRO_EXPECTED_RAW = "8001188940000478747a"
SYNTH_EXPECTED_TX = "903c64803c00b00000c028f07f7f0401007ff7"


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
    shutil.copytree(Path(__file__).parent / "batch6_probe", files, dirs_exist_ok=True)
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
            "X-Artifact-Name": f"{device}-batch6-{case}.bin",
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

        if case == "mini-scales":
            wait_for(client, session_id, lambda text: "I2C_MINISCALE_FILTERS" in text, 90)
            serial = wait_for(client, session_id, lambda text: "I2C_MINISCALE_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["mini-scales"] = serial[-900:]
            values = last_match(r"I2C_MINISCALE ([\d.]+) ([\d.]+) (\d)", serial)
            tare = last_match(r"I2C_MINISCALE_TARE ([\d.]+)", serial)
            filters = last_match(r"I2C_MINISCALE_FILTERS (\d+) (-?\d+) (-?\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("calibration-writes", 0) >= 1 and p.get("lpf") == 1,
                label="mini-scales qom")
            result["qom_samples"].extend(samples)
            result["observations"]["mini_scales"] = {
                "guest_values": values, "guest_tare": tare, "guest_filters": filters,
                "qom": {k: final.get(k) for k in ("adc-raw", "weight-g", "button",
                                                  "calibration-gap", "reset-writes", "calibration-writes",
                                                  "lpf", "avg-level", "ema-alpha", "i2c-address")},
                "boundary": "HX711/5kg load-cell mechanics, tare drift, linearity, temperature drift and "
                            "firmware v3/v4 differences are NOT RUN; page FAQ says I2C OR UART but the frozen "
                            "driver is I2C-only, and 0x26 is a four-way product conflict. The 0140 model has "
                            "no QOM led-rgb output, so the guest set_led write is exercised but not asserted.",
            }
            result["checks"]["guest_adc_value"] = bool(values and values[0] == "123456")
            result["checks"]["guest_weight_value"] = bool(values and abs(float(values[1]) - 123.5) <= 0.01)
            result["checks"]["guest_button_pressed"] = bool(values and values[2] == "1")
            result["checks"]["guest_tare_zero"] = bool(tare and abs(float(tare)) <= 0.01)
            result["checks"]["guest_filter_readback"] = filters == ("1", "7", "42")
            result["checks"]["guest_led_write_executed"] = "I2C_MINISCALE_LED_WRITTEN" in serial
            result["checks"]["qom_fixtures_exact"] = (
                final.get("adc-raw") == 123456 and abs(float(final.get("weight-g", 0)) - 123.5) <= 0.01
                and final.get("button") == 0)
            result["checks"]["qom_calibration_gap"] = abs(float(final.get("calibration-gap", 0)) - 10.0) <= 0.001
            result["checks"]["qom_write_counters"] = (
                int(final.get("calibration-writes", 0)) >= 1 and int(final.get("reset-writes", 0)) >= 1)
            result["checks"]["qom_filters"] = (
                final.get("lpf") == 1 and final.get("avg-level") == 7 and final.get("ema-alpha") == 42)
            result["checks"]["qom_identity"] = final.get("i2c-address") == 0x26

        elif case == "rgb-led-strip-50cm":
            wait_for(client, session_id, lambda text: "GPIO_RGB30_INDEX" in text, 60)
            serial = wait_for(client, session_id, lambda text: "GPIO_RGB30_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["rgb-led-strip-50cm"] = serial[-500:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: len(p.get("led-rgb") or []) == 30 and int(p.get("led-frames", 0)) >= 2,
                label="rgb-strip qom")
            result["qom_samples"].extend(samples)
            led = final.get("led-rgb") or []
            expected = [0x112233] * 30
            expected[5] = 0x445566
            result["observations"]["rgb_led_strip_50cm"] = {
                "qom": {k: final.get(k) for k in ("led-rgb", "led-frames", "incomplete-frames",
                                                  "output-transitions")},
                "expected_led_rgb": expected,
                "boundary": "SK6812 LED optics/color/power/IP65 and 800kHz timing tolerance are NOT RUN; "
                            "the page gives strip-side VCC/GND/DATA line colors while the Grove adapter "
                            "mapping is unresolved. A093 30-LED results do not transfer to A093-B/C/D variants "
                            "or to A035/A045-B.",
            }
            result["checks"]["guest_fill_frame_written"] = "GPIO_RGB30_FILL" in serial
            result["checks"]["guest_indexed_frame_written"] = "GPIO_RGB30_INDEX" in serial
            result["checks"]["qom_30_leds_match"] = led == expected
            result["checks"]["qom_frames_counted"] = int(final.get("led-frames", 0)) >= 2
            result["checks"]["no_incomplete_frames"] = int(final.get("incomplete-frames", 0)) == 0

        elif case == "op180":
            wait_for(client, session_id, lambda text: "GPIO_OP180 1" in text, 60)
            inject(client, session_id, {"digital-level": False})
            wait_for(client, session_id, lambda text: "GPIO_OP180 0" in text, 60)
            inject(client, session_id, {"digital-level": True})
            serial = wait_for(client, session_id, lambda text: "GPIO_OP180_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["op180"] = serial[-700:]
            levels = [int(v) for v in re.findall(r"GPIO_OP180 (\d)", serial)]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("digital-level") is True and int(p.get("input-events", 0)) >= 2,
                label="op180 qom")
            result["qom_samples"].extend(samples)
            result["observations"]["op180"] = {
                "guest_levels": levels,
                "qom": {k: final.get(k) for k in ("digital-level", "blocked", "input-events",
                                                  "transactions")},
                "boundary": "180-degree IR through-beam optics, occlusion geometry, response speed and "
                            "mechanical mounting are NOT RUN; active-low polarity comes from the frozen "
                            "OPUnit default. OP90 batch5 results are NOT transferred to OP180 even though "
                            "both share unit/op.py. Official PORT.B is substituted by cores3 PORT.A harness.",
            }
            result["checks"]["guest_level_changes"] = 1 in levels and 0 in levels and levels[-1] == 1
            result["checks"]["qom_level_and_blocked"] = (
                final.get("digital-level") is True and final.get("blocked") is False)
            result["checks"]["input_events_counted"] = int(final.get("input-events", 0)) >= 2
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "synth":
            wait_for(client, session_id, lambda text: "UART_SYNTH_SENT" in text, 90)
            serial = wait_for(client, session_id, lambda text: "UART_SYNTH_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["synth"] = serial[-600:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: (p.get("tx-hex") or "").startswith("903c64"),
                label="synth qom")
            result["qom_samples"].extend(samples)
            tx = final.get("tx-hex") or ""
            result["observations"]["synth"] = {
                "expected_tx_hex": SYNTH_EXPECTED_TX,
                "qom": {k: final.get(k) for k in ("tx-hex", "written-bytes", "transactions")},
                "boundary": "SAM2695 synthesis/audio, GM instruments, NS4150B amplifier and speaker are "
                            "NOT RUN; the Unit is TX-only (white=NC) so no RX injection exists and none is "
                            "claimed. 31250 baud comes from the driver, not the product page. Official PORT.C "
                            "is substituted by cores3 PORT.A harness.",
            }
            result["checks"]["guest_midi_sent"] = "UART_SYNTH_SENT" in serial
            result["checks"]["qom_tx_hex_exact"] = tx == SYNTH_EXPECTED_TX
            result["checks"]["written_bytes_match"] = int(final.get("written-bytes", 0)) == len(SYNTH_EXPECTED_TX) // 2
            result["checks"]["no_rx_injection_modeled"] = "frames-injected" not in final
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "mini-imu":
            wait_for(client, session_id, lambda text: "I2C_IMU_RANGE1" in text, 90)
            serial = wait_for(client, session_id, lambda text: "I2C_IMU_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["mini-imu"] = serial[-1000:]
            whoami = last_match(r"I2C_IMU_WHOAMI (\d+)", serial)
            acc = last_match(r"I2C_IMU_ACC (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            gyro = last_match(r"I2C_IMU_GYRO (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            temp = last_match(r"I2C_IMU_TEMP (-?[\d.]+)", serial)
            range0 = last_match(r"I2C_IMU_RANGE0 ([\d.]+) ([\d.]+)", serial)
            range1 = last_match(r"I2C_IMU_RANGE1 ([\d.]+) ([\d.]+)", serial)
            acc2 = last_match(r"I2C_IMU_ACC2 (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("accel-range") == 8 and p.get("gyro-range") == 1000,
                label="mini-imu qom")
            result["qom_samples"].extend(samples)
            result["observations"]["mini_imu"] = {
                "guest_whoami": whoami, "guest_accel_g": acc, "guest_gyro_dps": gyro,
                "guest_temperature_c": temp, "guest_range0": range0, "guest_range1": range1,
                "guest_accel_after_range": acc2,
                "qom": {k: final.get(k) for k in ("accel-x-g", "accel-y-g", "accel-z-g",
                                                  "gyro-x-dps", "gyro-y-dps", "gyro-z-dps",
                                                  "temperature-c", "accel-range", "gyro-range",
                                                  "whoami", "i2c-address")},
                "boundary": "Real motion/vibration/temperature and MPU6886 DMP/FIFO calibration are NOT RUN. "
                            "The 0144 fix keeps the QOM accel-range/gyro-range view in sync with guest "
                            "ACCEL_CONFIG/GYRO_CONFIG writes; guest init selects 2g/250dps and the probe then "
                            "switches to 8g/1000dps. 0x68 is shared with Mini IMU-Pro (U171).",
            }
            result["checks"]["guest_whoami"] = whoami == "25"
            result["checks"]["guest_accel_g"] = bool(acc and abs(float(acc[0]) - 1.5) <= 0.02
                                                    and abs(float(acc[1]) + 0.5) <= 0.02
                                                    and abs(float(acc[2]) - 1.0) <= 0.02)
            result["checks"]["guest_gyro_dps"] = bool(gyro and abs(float(gyro[0]) - 12.5) <= 0.5
                                                     and abs(float(gyro[1]) + 25.0) <= 0.5
                                                     and abs(float(gyro[2]) - 50.0) <= 0.5)
            result["checks"]["guest_temperature"] = bool(temp and abs(float(temp) - 31.25) <= 0.1)
            result["checks"]["guest_default_range"] = range0 == ("16384", "131")
            result["checks"]["guest_range_switch"] = range1 == ("4096", "32.8")
            result["checks"]["guest_accel_after_range"] = bool(acc2 and abs(float(acc2[0]) - 1.5) <= 0.02)
            result["checks"]["qom_range_fixtures"] = final.get("accel-range") == 8 and final.get("gyro-range") == 1000
            result["checks"]["qom_identity"] = final.get("whoami") == 25 and final.get("i2c-address") == 0x68
            result["checks"]["qom_sensor_fixtures"] = (
                abs(float(final.get("accel-x-g", 0)) - 1.5) <= 0.01
                and abs(float(final.get("temperature-c", 0)) - 31.25) <= 0.01)

        elif case == "env-pro":
            wait_for(client, session_id, lambda text: "I2C_BME_RAW" in text, 90)
            serial = wait_for(client, session_id, lambda text: "I2C_BME_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["env-pro"] = serial[-900:]
            guest_id = last_match(r"I2C_BME_ID (\d+) (\d+)", serial)
            raw = last_match(r"I2C_BME_RAW ([0-9a-f]+)", serial)
            status = last_match(r"I2C_BME_STATUS (\d+)", serial)
            decoded = last_match(r"I2C_BME_DECODED_OBSERVATION ([^\n]*)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("chip-id") == 0x61 and p.get("variant") == 1,
                label="env-pro qom")
            result["qom_samples"].extend(samples)
            result["observations"]["env_pro"] = {
                "guest_id": guest_id, "guest_raw_field_hex": raw, "guest_status": status,
                "guest_decoded_observation": decoded,
                "expected_raw_field_hex": ENVPRO_EXPECTED_RAW,
                "qom": {k: final.get(k) for k in ("temperature-c", "humidity-pct", "pressure-pa",
                                                  "gas-resistance-ohm", "data-ready", "chip-id",
                                                  "variant", "i2c-address")},
                "decoded_assertion": "NOT ASSERTED: the 0140 model does not implement the BME68x "
                                     "compensation inverse, so guest T/RH/P are observation-only. Raw field "
                                     "bytes are the assertable data plane.",
                "boundary": "BME688 gas/IAQ/heater profile/10.8s scan, real T/RH/P physics and calibration "
                            "coefficients are NOT RUN; 0x77 is free but the 0x76 alternate conflicts with "
                            "env/bps/env-ii/env-iv.",
            }
            result["checks"]["guest_chip_variant"] = guest_id == ("97", "1")
            result["checks"]["guest_raw_field_bytes_exact"] = raw == ENVPRO_EXPECTED_RAW
            result["checks"]["guest_status_ready"] = status == "128"
            result["checks"]["qom_fixtures_exact"] = (
                abs(float(final.get("temperature-c", 0)) - 31.5) <= 0.01
                and abs(float(final.get("humidity-pct", 0)) - 45.5) <= 0.01
                and abs(float(final.get("pressure-pa", 0)) - 100500) <= 0.01
                and abs(float(final.get("gas-resistance-ohm", 0)) - 500000) <= 0.01
                and final.get("data-ready") is True)
            result["checks"]["qom_identity"] = final.get("chip-id") == 0x61 and final.get("variant") == 1
            result["checks"]["i2c_address_0x77"] = final.get("i2c-address") == 0x77
            result["checks"]["guest_decoded_not_asserted"] = True

        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        screenshot = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(screenshot)
        result["frame"] = {"sha256": sha256(screenshot), "metrics": png_metrics(screenshot)}
        result["checks"]["nonempty_application_frame"] = result["frame"]["metrics"]["unique_colors"] > 1
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as error:  # noqa: BLE001 - the failure is preserved as evidence
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
