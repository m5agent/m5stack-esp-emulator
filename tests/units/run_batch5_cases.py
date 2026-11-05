#!/usr/bin/env python3
"""Validate the twelve Units of the fifth research batch.

One QEMU build is enough: the merged 0137 (batch5 A) and 0139 (batch5 B)
layers both sit on the canonical chain. Each case builds a merged
reference-firmware image that runs the firmware's frozen original UIFlow2
driver, creates one visible leased `/api/v1` session, provides fixtures as
session-initial Unit inputs (or unit-input where coordination is needed),
reads controller-backed state, captures serial markers, the frame and the
evidence ZIP before stopping with `purge=0`.
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

MARKER = "BATCH5_PROBE_READY"

QEMU_SOURCE_STATE = ("canonical 75f1d24 + canonical chain 20 layers "
                     "(0120-0139, incl. 0137 batch5 A and 0139 batch5 B) "
                     "+ 0141-unit-batch5-evidence-fixes")

CASES = {
    "pbhub-v11": "cores3", "op90": "cores3", "rgb-led-10cm": "cores3",
    "8angle": "cores3", "kmeter-iso-v11": "cores3",
    "pahub-v20": "cores3", "rtc": "cores3", "tmos-pir": "cores3",
    "neohex": "cores3", "lora-e220-433": "cores3", "zigbee": "cores3",
    "nbiot2": "cores3",
}
A_CASES = ("pbhub-v11", "op90", "rgb-led-10cm", "8angle", "kmeter-iso-v11")
B_CASES = ("pahub-v20", "rtc", "tmos-pir", "neohex", "lora-e220-433", "zigbee", "nbiot2")
OFFICIAL_PORT = {
    "pbhub-v11": "PORT.A", "8angle": "PORT.A", "kmeter-iso-v11": "PORT.A",
    "pahub-v20": "PORT.A", "rtc": "PORT.A", "tmos-pir": "PORT.A",
    "op90": "PORT.B", "rgb-led-10cm": "PORT.B", "neohex": "PORT.B",
    "lora-e220-433": "PORT.C", "zigbee": "PORT.C", "nbiot2": "PORT.C",
}
# The current host-port registry only admits main-device ports and on cores3
# that is PORT.A, so all sessions use its GPIO 2/1 pins as harness wiring.
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "pbhub-v11": "PBHUBUnit v1.1 (0x61)",
    "op90": "OPUnit(Button)",
    "rgb-led-10cm": "RGBUnit(SK6812, 15 LEDs)",
    "8angle": "Angle8Unit",
    "kmeter-iso-v11": "KMeterISOUnit",
    "pahub-v20": "PAHUBUnit",
    "rtc": "RTC8563Unit",
    "tmos-pir": "TMOSUnit(STHS34PF80)",
    "neohex": "driver.neopixel.ws2812.WS2812 (unit driver gap)",
    "lora-e220-433": "LoRaE220433Unit",
    "zigbee": "ZigbeeUnit(DRF1609H)",
    "nbiot2": "NBIOT2Unit(SIM7028)",
}
INITIAL = {
    "pbhub-v11": {"digital-inputs": [True, False, True, False, True, False],
                  "analog-inputs": [512, 0, 1023, 0, 100, 0]},
    "op90": {"digital-level": True},
    "rgb-led-10cm": {},
    "8angle": {"adc12-raw": [100, 200, 300, 400, 500, 600, 700, 800],
               "adc8-raw": [10, 20, 30, 40, 50, 60, 70, 80],
               "switch-pressed": True},
    "kmeter-iso-v11": {"thermocouple-temperature-c": 123.45,
                       "internal-temperature-c": 26.5, "data-ready": True},
    "pahub-v20": {},
    "rtc": {"unix-time": 1767225600, "running": True},
    "tmos-pir": {"tobject-c": 31.5, "tambient-c": 22.25,
                 "presence": True, "motion": True, "shock": False,
                 "gain-mode": 1, "odr": 3},
    "neohex": {},
    "lora-e220-433": {"responses-hex": "48454c4c4f"},
    "zigbee": {"responses-hex": "fa060a0a44544b00483f;fa310a0a0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003f;fa010a0a0f;a1a2a3a4"},
    "nbiot2": {"responses-hex": "4f4b0d0a;4f4b0d0a;4f4b0d0a;4f4b0d0a"},
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
    batch = "A" if case in A_CASES else "B"
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device_row = next(row for row in matrix["devices"] if row["id"] == device)
    port = port_for(client, device, case)

    files = output / "files"
    shutil.copytree(Path(__file__).parent / "batch5_probe", files, dirs_exist_ok=True)
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
        "device_id": device, "unit_id": case, "batch": batch,
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
            "X-Artifact-Name": f"{device}-batch5-{case}.bin",
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

        if case == "pbhub-v11":
            wait_for(client, session_id, lambda text: "I2C_PBHUB_WRITTEN" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_PBHUB_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["pbhub-v11"] = serial[-700:]
            fw = last_match(r"I2C_PBHUB_FW (\d+)", serial)
            read = last_match(r"I2C_PBHUB_READ (\d+) (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("digital-inputs") == [True, False, True, False, True, False]
                and p.get("pwm-outputs", [0])[0] == 128
                and p.get("rgb-frames", [0])[0] == 0xFF0000,
                label="pbhub-v11 qom")
            result["qom_samples"].extend(samples)
            result["observations"]["pbhub_v11"] = {
                "guest_fw": fw, "guest_read": read,
                "qom": {k: final.get(k) for k in ("digital-inputs", "analog-inputs",
                                                  "digital-outputs", "pwm-outputs", "rgb-frames",
                                                  "rgb-mode", "fw-version", "i2c-address", "transactions")},
                "boundary": "0x61 conflicts with pbhub (one Unit per bus); PbHub v2 firmware adds SK6812/IAP "
                            "but the IAP path is not modeled; servo/pin electrical behavior is NOT RUN. The "
                            "0137 model collapses IO0/IO1 positions onto one digital fixture boolean, so the "
                            "second-position read equals the first and per-position semantics stay a limitation.",
            }
            result["checks"]["guest_fw_v2"] = fw == "2"
            # 0137 collapse: IO0/IO1 positions share one digital fixture boolean.
            result["checks"]["guest_channel_reads"] = read == ("1", "1", "512")
            result["checks"]["qom_inputs_exact"] = (
                final.get("digital-inputs") == [True, False, True, False, True, False]
                and final.get("analog-inputs") == [512, 0, 1023, 0, 100, 0])
            result["checks"]["qom_digital_write"] = final.get("digital-outputs", [False])[0] is True
            result["checks"]["qom_pwm_observed"] = final.get("pwm-outputs", [0])[0] == 128
            result["checks"]["qom_rgb_observed"] = final.get("rgb-frames", [0])[0] == 0xFF0000
            result["checks"]["qom_identity"] = final.get("fw-version") == 2 and final.get("i2c-address") == 0x61

        elif case == "op90":
            wait_for(client, session_id, lambda text: "GPIO_OP90 1" in text, 60)
            inject(client, session_id, {"digital-level": False})
            wait_for(client, session_id, lambda text: "GPIO_OP90 0" in text, 60)
            inject(client, session_id, {"digital-level": True})
            serial = wait_for(client, session_id, lambda text: "GPIO_OP90_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["op90"] = serial[-700:]
            levels = [int(v) for v in re.findall(r"GPIO_OP90 (\d)", serial)]
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("input-events", 0)) >= 2 and p.get("digital-level") is True,
                label="op90 qom")
            result["qom_samples"].extend(samples)
            result["observations"]["op90"] = {
                "guest_levels": levels,
                "qom": {k: final.get(k) for k in ("digital-level", "blocked", "input-events")},
                "boundary": "90-degree IR beam/optical alignment/response speed are NOT RUN; active-low "
                            "polarity comes from the frozen OPUnit default and the model's blocked view; "
                            "the official PORT.B connector is not runtime-admitted.",
            }
            result["checks"]["guest_level_changes"] = 0 in levels and 1 in levels
            result["checks"]["qom_level_and_blocked"] = (
                final.get("digital-level") is True and final.get("blocked") is False)
            result["checks"]["input_events_counted"] = int(final.get("input-events", 0)) >= 2
            result["checks"]["no_i2c_transactions_fabricated"] = int(final.get("transactions", 0)) == 0

        elif case == "rgb-led-10cm":
            serial = wait_for(client, session_id, lambda text: "GPIO_RGB15_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["rgb-led-10cm"] = serial[-400:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: len(p.get("led-rgb") or []) == 15 and (p.get("led-rgb") or [0])[0] == 0x112233,
                label="rgb-led-10cm qom")
            result["qom_samples"].extend(samples)
            led = final.get("led-rgb") or []
            result["observations"]["rgb_led_10cm"] = {
                "qom": {k: final.get(k) for k in ("led-rgb", "led-frames", "incomplete-frames",
                                                  "output-transitions")},
                "boundary": "LED optics/color/power and RMT timing tolerance are NOT RUN; PORT.B is not "
                            "runtime-admitted so cores3 PORT.A harness wiring is recorded in the report.",
            }
            result["checks"]["guest_frame_written"] = "GPIO_RGB15_WRITTEN" in serial
            result["checks"]["qom_15_leds_match"] = led == [0x112233] * 15
            result["checks"]["qom_led_frames_observed"] = int(final.get("led-frames", 0)) >= 1
            result["checks"]["no_incomplete_frames"] = int(final.get("incomplete-frames", 0)) == 0

        elif case == "neohex":
            serial = wait_for(client, session_id, lambda text: "GPIO_NEOHEX_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["neohex"] = serial[-500:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: len(p.get("led-rgb") or []) == 37 and (p.get("led-rgb") or [0])[0] == 0x445566,
                label="neohex qom")
            result["qom_samples"].extend(samples)
            led = final.get("led-rgb") or []
            result["observations"]["neohex"] = {
                "qom": {k: final.get(k) for k in ("led-rgb", "led-frames", "incomplete-frames",
                                                  "output-transitions")},
                "driver_gap": "public UIFlow2 has no unit/neohex.py; the probe uses the generic "
                              "driver.neopixel.ws2812.WS2812 path (pinned SHA) and records the gap.",
                "boundary": "WS2812 vs SK6812 byte order/timing, 37-LED optics/power and cascade limits "
                            "are NOT RUN; official PORT.B is substituted by cores3 PORT.A harness wiring.",
            }
            result["checks"]["generic_ws2812_driver_used"] = "GPIO_NEOHEX_DRIVER ws2812" in serial
            result["checks"]["guest_frame_written"] = "GPIO_NEOHEX_WRITTEN" in serial
            result["checks"]["qom_37_leds_match"] = led == [0x445566] * 37
            result["checks"]["qom_led_frames_observed"] = int(final.get("led-frames", 0)) >= 1

        elif case == "8angle":
            wait_for(client, session_id, lambda text: "I2C_ANGLE8_RGB" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_ANGLE8_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["8angle"] = serial[-800:]
            adc12 = last_match(r"I2C_ANGLE8_ADC12 (\d+) (\d+)", serial)
            adc8 = last_match(r"I2C_ANGLE8_ADC8 (\d+) (\d+)", serial)
            switch = last_match(r"I2C_ANGLE8_SWITCH (\d)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("adc12-raw") == [100, 200, 300, 400, 500, 600, 700, 800]
                and (p.get("led-rgb") or [0, 0])[:2] == [0x112233, 0x445566],
                label="8angle qom")
            result["qom_samples"].extend(samples)
            result["observations"]["8angle"] = {
                "guest_adc12": adc12, "guest_adc8": adc8, "guest_switch": switch,
                "qom": {k: final.get(k) for k in ("adc12-raw", "adc8-raw", "switch-pressed",
                                                  "led-rgb", "fw-version", "i2c-address", "transactions")},
                "boundary": "Potentiometer mechanics/linearity/zero, ADC reference/filtering and SK6812 "
                            "optics are NOT RUN; the model stores RGB without the 4th brightness byte.",
            }
            result["checks"]["guest_adc12_samples"] = adc12 == ("100", "800")
            result["checks"]["guest_adc8_samples"] = adc8 == ("10", "80")
            result["checks"]["guest_switch_pressed"] = switch == "1"
            result["checks"]["qom_adc_fixtures_exact"] = (
                final.get("adc12-raw") == [100, 200, 300, 400, 500, 600, 700, 800]
                and final.get("adc8-raw") == [10, 20, 30, 40, 50, 60, 70, 80]
                and final.get("switch-pressed") is True)
            result["checks"]["qom_led_rgb_written"] = (
                (final.get("led-rgb") or [0, 0])[:2] == [0x112233, 0x445566])
            result["checks"]["qom_identity"] = final.get("fw-version") == 1 and final.get("i2c-address") == 0x43

        elif case == "kmeter-iso-v11":
            wait_for(client, session_id, lambda text: "I2C_KMETER_READY" in text, 60)
            serial = wait_for(client, session_id, lambda text: "I2C_KMETER_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["kmeter-iso-v11"] = serial[-600:]
            temps = last_match(r"I2C_KMETER ([\d.]+) ([\d.]+)", serial)
            ready = last_match(r"I2C_KMETER_READY (\d)", serial)
            fw = last_match(r"I2C_KMETER_FW (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("thermocouple-temperature-c") == 123.45
                and p.get("internal-temperature-c") == 26.5,
                label="kmeter qom")
            result["qom_samples"].extend(samples)
            result["observations"]["kmeter_iso_v11"] = {
                "guest_temperatures": temps, "guest_ready": ready, "guest_fw": fw,
                "qom": {k: final.get(k) for k in ("thermocouple-temperature-c",
                                                  "internal-temperature-c", "data-ready",
                                                  "fw-version", "i2c-address", "transactions")},
                "boundary": "MAX31855 fault bits, thermocouple physics/cold-junction/isolation and 10Hz "
                            "sampling are NOT RUN; 0x66 has no registered conflict.",
            }
            result["checks"]["guest_thermocouple_temperature"] = bool(
                temps and abs(float(temps[0]) - 123.45) <= 0.01)
            result["checks"]["guest_internal_temperature"] = bool(
                temps and abs(float(temps[1]) - 26.5) <= 0.01)
            result["checks"]["guest_ready_and_fw"] = ready == "1" and fw == "1"
            result["checks"]["qom_fixtures_exact"] = (
                final.get("thermocouple-temperature-c") == 123.45
                and final.get("internal-temperature-c") == 26.5
                and final.get("data-ready") is True)

        elif case == "pahub-v20":
            wait_for(client, session_id, lambda text: "I2C_PAHUB_SELECT 0" in text, 60)
            mask1, s1 = wait_properties(client, session_id, lambda p: p.get("channel-mask") == 1, label="pahub mask1")
            result["qom_samples"].extend(s1)
            wait_for(client, session_id, lambda text: "I2C_PAHUB_SELECT 3" in text, 60)
            mask9, s2 = wait_properties(client, session_id, lambda p: p.get("channel-mask") == 9, label="pahub mask9")
            result["qom_samples"].extend(s2)
            wait_for(client, session_id, lambda text: "I2C_PAHUB_SELECT 5" in text, 60)
            mask41, s3 = wait_properties(client, session_id, lambda p: p.get("channel-mask") == 41, label="pahub mask41")
            result["qom_samples"].extend(s3)
            wait_for(client, session_id, lambda text: "I2C_PAHUB_RELEASE 3" in text, 60)
            mask33, s4 = wait_properties(client, session_id, lambda p: p.get("channel-mask") == 33, label="pahub mask33")
            result["qom_samples"].extend(s4)
            serial = wait_for(client, session_id, lambda text: "I2C_PAHUB_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["pahub-v20"] = serial[-600:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("channel-mask") == 0 and int(p.get("channel-writes", 0)) >= 5,
                label="pahub final qom")
            result["qom_samples"].extend(samples)
            result["observations"]["pahub_v20"] = {
                "masks": {"after_select0": 1, "after_select3": 9, "after_select5": 41,
                          "after_release3": 33, "final": 0},
                "qom": {k: final.get(k) for k in ("channel-mask", "channel-writes", "i2c-address")},
                "boundary": "Downstream bus forwarding/nested hubs are NOT modeled; only the 1-byte "
                            "select/release mask is asserted. A0-A2 address straps, PCA9548A 8-channel "
                            "vs 6-channel exposure and electrical behavior are NOT RUN; 0x70 conflicts "
                            "with env-iii (one Unit per bus).",
            }
            result["checks"]["mask_sequence"] = (
                mask1.get("channel-mask") == 1 and mask9.get("channel-mask") == 9
                and mask41.get("channel-mask") == 41 and mask33.get("channel-mask") == 33)
            result["checks"]["mask_final_zero"] = final.get("channel-mask") == 0
            result["checks"]["channel_writes_counted"] = int(final.get("channel-writes", 0)) >= 5
            result["checks"]["i2c_address_0x70"] = final.get("i2c-address") == 0x70
            result["checks"]["downstream_not_modeled"] = True

        elif case == "rtc":
            wait_for(client, session_id, lambda text: "RTC_T1" in text, 60)
            base_props, s1 = wait_properties(
                client, session_id, lambda p: p.get("unix-time", 0) >= 1767225600,
                label="rtc base")
            result["qom_samples"].extend(s1)
            wait_for(client, session_id, lambda text: "RTC_T2" in text, 60)
            advanced, s2 = wait_properties(
                client, session_id,
                lambda p: p.get("unix-time", 0) >= 1767225601, label="rtc advanced")
            result["qom_samples"].extend(s2)
            wait_for(client, session_id, lambda text: "RTC_PHASE1" in text, 60)
            inject(client, session_id, {"running": False})
            serial = wait_for(client, session_id, lambda text: "RTC_WRITTEN" in text, 120)
            serial = wait_for(client, session_id, lambda text: "I2C_RTC_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["rtc"] = serial[-900:]
            t1 = last_match(r"RTC_T1 (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)", serial)
            t2 = last_match(r"RTC_T2 (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)", serial)
            written = last_match(r"RTC_WRITTEN (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("unix-time") == 1772452800 and p.get("running") is False,
                label="rtc written qom")
            result["qom_samples"].extend(samples)
            result["observations"]["rtc"] = {
                "guest_t1": t1, "guest_t2": t2, "guest_written": written,
                "qom": {k: final.get(k) for k in ("unix-time", "running", "i2c-address")},
                "boundary": "Crystal accuracy/battery backup/power-loss retention, timezone/NTP, alarm "
                            "IRQ timing and century/leap-year are NOT RUN; the clock uses QEMU virtual time "
                            "while running and BCD registers while stopped. 0x51 conflicts with the ameter "
                            "calibration EEPROM (one Unit per bus).",
            }
            result["checks"]["guest_base_time"] = bool(
                t1 and t1[:5] == ("26", "1", "1", "0", "0") and 0 <= int(t1[5]) <= 59)
            result["checks"]["virtual_clock_advanced"] = (
                int(advanced.get("unix-time", 0)) >= int(base_props.get("unix-time", 0)) + 1)
            result["checks"]["guest_time_advanced"] = bool(t2 and t1 and t2[5] != t1[5] or (t2 and t1 and t2 != t1))
            result["checks"]["guest_write_fields"] = written == ("26", "3", "2", "12", "0", "0")
            result["checks"]["qom_unix_time_written"] = final.get("unix-time") == 1772452800
            result["checks"]["i2c_address_0x51"] = final.get("i2c-address") == 0x51

        elif case == "tmos-pir":
            wait_for(client, session_id, lambda text: "I2C_TMOS_END" in text, 60)
            serial = read_serial(client, session_id)
            result["serial_markers"]["tmos-pir"] = serial[-900:]
            state = last_match(r"I2C_TMOS_STATE (\d) (\d) (\d)", serial)
            raw = last_match(r"I2C_TMOS_RAW (\d+) (\d+) (\d+) (\d+)", serial)
            temp = last_match(r"I2C_TMOS_TEMP (-?[\d.]+)", serial)
            odr = last_match(r"I2C_TMOS_ODR (\d+) (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: p.get("presence") is True and p.get("motion") is True
                and p.get("tobject-c") == 31.5,
                label="tmos qom")
            result["qom_samples"].extend(samples)
            result["observations"]["tmos_pir"] = {
                "guest_state": state, "guest_raw": raw, "guest_temperature_data": temp,
                "guest_odr_gain": odr,
                "qom": {k: final.get(k) for k in ("tobject-c", "tambient-c", "presence", "motion",
                                                  "shock", "gain-mode", "odr", "i2c-address")},
                "boundary": "IR optics 5-20um/FOV/range/thermal model, gain saturation, embedded-function "
                            "thresholds/hysteresis/interrupt timing and power-down reset semantics are NOT RUN; "
                            "0x5A conflicts with ncir/ncir2 (one Unit per bus).",
            }
            result["checks"]["guest_presence_motion"] = state == ("1", "1", "0")
            result["checks"]["guest_raw_temperature"] = raw == ("3150", "2225", "1", "1")
            result["checks"]["guest_temperature_data"] = bool(
                temp and abs(float(temp) - 1.575) <= 0.01)
            result["checks"]["qom_fixtures_exact"] = (
                final.get("tobject-c") == 31.5 and final.get("tambient-c") == 22.25
                and final.get("presence") is True and final.get("motion") is True
                and final.get("shock") is False)
            result["checks"]["qom_gain_odr_fixture"] = (
                final.get("gain-mode") == 1 and final.get("odr") == 3)
            result["checks"]["i2c_address_0x5a"] = final.get("i2c-address") == 0x5A

        elif case == "lora-e220-433":
            wait_for(client, session_id, lambda text: "UART_LORA_SETUP" in text, 90)
            serial = wait_for(client, session_id, lambda text: "UART_LORA_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["lora-e220-433"] = serial[-1100:]
            setup = last_match(r"UART_LORA_SETUP (\d)", serial)
            config = last_match(r"UART_LORA_CONFIG \(([^)]*)\)", serial)
            available = last_match(r"UART_LORA_AVAILABLE (\d+)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("frames-sent", 0)) >= 2 and int(p.get("frames-injected", 0)) >= 1,
                label="lora-final qom")
            result["qom_samples"].extend(samples)
            tx = final.get("tx-hex") or ""
            result["observations"]["lora_e220_433"] = {
                "guest_setup": setup, "guest_config": config, "guest_available": available,
                "qom": {k: final.get(k) for k in ("responses-hex", "tx-hex", "config-hex",
                                                  "frames-sent", "frames-injected")},
                "boundary": "RF 433MHz/antenna/range/air-rate/power, DIP M0/M1 modes and LoRa physics are "
                            "NOT RUN; only UART configuration frames and the fixture response bytes are "
                            "asserted. Page 115200 vs driver 9600 baud stays unresolved. Official PORT.C is "
                            "substituted by cores3 PORT.A harness wiring.",
            }
            result["checks"]["guest_setup_ok"] = setup == "1"
            result["checks"]["guest_config_address_channel"] = bool(
                config and config.startswith("4660,") and ", 5," in config)
            result["checks"]["qom_config_write_frame"] = tx.startswith("c00008") and "1234" in tx
            result["checks"]["qom_send_frame"] = "43210748454c4c4f" in tx
            result["checks"]["qom_config_mirror"] = len(final.get("config-hex") or "") == 16
            result["checks"]["frames_counted"] = (
                int(final.get("frames-sent", 0)) >= 2 and int(final.get("frames-injected", 0)) >= 1)

        elif case == "zigbee":
            serial = wait_for(client, session_id, lambda text: "UART_ZIGBEE_END" in text, 90)
            serial = read_serial(client, session_id)
            result["serial_markers"]["zigbee"] = serial[-900:]
            rx_hex = last_match(r"UART_ZIGBEE_RX ([0-9a-f]*)", serial)
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("frames-sent", 0)) >= 1 and int(p.get("frames-injected", 0)) >= 1,
                label="zigbee final qom")
            result["qom_samples"].extend(samples)
            tx = final.get("tx-hex") or ""
            result["observations"]["zigbee"] = {
                "guest_rx_hex": rx_hex,
                "qom": {k: final.get(k) for k in ("responses-hex", "tx-hex",
                                                  "frames-sent", "frames-injected")},
                "boundary": "Zigbee mesh/routing/2.4GHz RF/encryption/antenna distance are NOT RUN; for a "
                            "byte-layer probe the model captures the 0xED P2P frame and injects the "
                            "';'-separated fixture response after the idle gap. DRF1609H firmware/parameter "
                            "frame parsing is minimal. Official PORT.C is substituted by cores3 PORT.A.",
            }
            result["checks"]["guest_p2p_frame_sent"] = "ed05123448454c4c4f" in tx
            result["checks"]["guest_rx_fixture"] = rx_hex == "a1a2a3a4"
            result["checks"]["frames_counted"] = (
                int(final.get("frames-sent", 0)) >= 1 and int(final.get("frames-injected", 0)) >= 1)

        elif case == "nbiot2":
            wait_for(client, session_id, lambda text: "UART_NBIOT_READY" in text, 120)
            serial = wait_for(client, session_id, lambda text: "UART_NBIOT_END" in text, 120)
            serial = read_serial(client, session_id)
            result["serial_markers"]["nbiot2"] = serial[-900:]
            final, samples = wait_properties(
                client, session_id,
                lambda p: int(p.get("frames-sent", 0)) >= 2 and int(p.get("frames-injected", 0)) >= 2,
                label="nbiot2 final qom")
            result["qom_samples"].extend(samples)
            tx = final.get("tx-hex") or ""
            result["observations"]["nbiot2"] = {
                "qom": {k: final.get(k) for k in ("responses-hex", "tx-hex",
                                                  "frames-sent", "frames-injected")},
                "boundary": "NB-IoT RF/network/SIM/operator certifications/TLS/DTLS/CoAP/SSL are NOT RUN; "
                            "only the AT byte/response-framing layer is asserted (the constructor's AT "
                            "readiness and ATE0 are answered by fixture chunks). SIM7028 AT firmware "
                            "version/URC timing remains unresolved. Official PORT.C is substituted by "
                            "cores3 PORT.A harness wiring.",
            }
            result["checks"]["guest_constructor_ready"] = "UART_NBIOT_READY" in serial
            # The frozen NBIOT2Unit sends AT then AT+CFUN=1 (not ATE0 as the
            # public-source Modem suggests); assert the observed byte stream.
            result["checks"]["qom_at_command_bytes"] = (
                "41540d0a" in tx and "41542b4346554e3d310d0a" in tx)
            result["checks"]["frames_counted"] = (
                int(final.get("frames-sent", 0)) >= 2 and int(final.get("frames-injected", 0)) >= 2)

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
