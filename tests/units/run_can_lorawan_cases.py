#!/usr/bin/env python3
"""Validate the CAN / LoRaWAN lane-unlock evidence Units (can, mini-can, lorawan-us915).

One QEMU build (canonical 35-layer chain through 0154) covers all three Units.
Each case builds a merged reference-firmware image that runs the firmware's
frozen original UIFlow2 driver in one visible leased `/api/v1` session, provides
fixtures as session-initial Unit inputs (UART responder) or through the Unit
QOM inject-hex input (CAN host frame), reads controller-backed QOM state,
captures the serial markers, the frame and the evidence ZIP, then stops with
purge=0.

The CAN cases use the real esp32s3 TWAI controller and the board m5-canbus
CanBusClient lane: the guest driver sends one standard frame that the Unit
client observes, and the runner injects one host fixture frame through the Unit
QOM inject-hex so the guest TWAI RX path is exercised. No CAN frame is faked by
the host.

The LoRaWAN case asserts only the UART byte layer: the frozen ASR650x wrapper
creates machine.UART(1, tx, rx) without a baud argument and only calls init()
afterwards, so the same documented guest-side UART bootstrap already used by
the batch-7 lorawan-cn470 evidence is applied (the official driver below writes
the AT bytes). The frozen unit/lorawan.py still inherits driver.asr650x while
the product is STM32WLE5/RAK3172, so join/OTAA/ABP/duty-cycle/FCC/RF are NOT RUN.
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
from run_batch6_cases import (  # noqa: E402
    Client, utc_now, sha256, read_serial, properties, wait_properties,
    wait_for, last_match, inject,
)
from run_profile_ui_test import build_image  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402

START_MARKER = "CANLORA_PROBE_START"
MARKER = "CANLORA_PROBE_READY"
BINARY = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
QEMU_SOURCE_STATE = "canonical 75f1d24 + canonical 35-layer chain through 0154"

CASES = {"can": "cores3", "mini-can": "cores3", "lorawan-us915": "cores3"}
OFFICIAL_PORT = {"can": "PORT.C", "mini-can": "PORT.C", "lorawan-us915": "PORT.C"}
PORT_IDS = {case: "port-a" for case in CASES}
CASE_DRIVERS = {
    "can": "official m5can C module on esp32s3 TWAI (CA-IS3050G isolated transceiver); frozen unit/can.py wrapper release incompatibility recorded",
    "mini-can": "official m5can C module on esp32s3 TWAI (TJA1051T/3 non-isolated transceiver); frozen unit/can.py wrapper release incompatibility recorded",
    "lorawan-us915": "LoRaWANUnit (ASR650x driver / STM32WLE5 product)",
}
END_MARKER = {"can": "CAN_END", "mini-can": "CAN_END", "lorawan-us915": "LW915_END"}
CAN_INJECT = "456#deadbeef"
INITIAL = {
    "can": {},
    "mini-can": {},
    "lorawan-us915": {
        "responses-hex": "4f4b0d0a;4f4b0d0a;4f4b0d0a;4f4b0d0a;4f4b2b53454e543a0d0a4f4b0d0a;4f4b0d0a"
    },
}
CAN_GUEST_TX_HEX = "123#0102030405060708"


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
    if case in ("can", "mini-can"):
        checks["official_driver_started"] = f"{MARKER} {case}" in serial
        checks["can_unit_ready"] = "CAN_READY" in serial
        checks["can_wrapper_caveat_recorded"] = (
            "CAN_WRAPPER_CAVEAT" in serial and "ESP_ERR_INVALID_ARG" in serial)
        checks["guest_sent_frame"] = "CAN_SENT" in serial
        observed = int(final.get("frames-observed", 0) or 0)
        injected = int(final.get("injected-frames", 0) or 0)
        last_hex = str(final.get("last-frame-hex", "") or "")
        checks["qom_frames_observed"] = observed >= 1
        checks["qom_injected_frames"] = injected >= 1
        checks["qom_last_frame_hex"] = last_hex.startswith(CAN_GUEST_TX_HEX)
        checks["guest_received_fixture_frame"] = bool(
            re.search(r"CAN_RECV\s+456#deadbeef", serial))
        checks["can_state_reported"] = bool(re.search(r"CAN_STATE_FINAL\s+\d+", serial))
        observations[case] = {
            "guest_ready": "CAN_READY" in serial,
            "guest_sent": "CAN_SENT" in serial,
            "frames_observed": observed,
            "injected_frames": injected,
            "last_frame_hex": last_hex,
            "guest_recv": last_match(r"CAN_RECV\s+(\S+)", serial),
            "can_state_final": last_match(r"CAN_STATE_FINAL\s+(\d+)", serial),
            "wrapper_caveat": "The frozen UIFlow2 release image's Python unit/can.py "
                        "wrapper is unusable on this firmware build (TypeError / "
                        "ESP_ERR_INVALID_ARG); the probe drives the same official m5can "
                        "C module (bus 0, default 125 kbit/s timing) the wrapper subclasses.",
            "boundary": "CAN frame lane only: electrical/transceiver/isolation/termination/"
                        "bit-timing/filtering/arbitration NOT modeled and NOT RUN; "
                        "PORT.C substituted by the cores3 PORT.A harness.",
        }
    else:  # lorawan-us915
        checks["official_driver_ready"] = "LW915_READY" in serial
        checks["no_init_error"] = "LW915_INIT_ERROR" not in serial
        tx_hex = str(final.get("tx-hex", "") or "")
        responses = str(final.get("responses-hex", "") or "")
        checks["qom_tx_bytes"] = bool(tx_hex)
        # "AT+CWORKMODE=" -> 41542b43574f524b4d4f44453d ; "AT+DTRX" -> 41542b44545258
        checks["qom_workmode_bytes"] = "41542b43574f524b4d4f44453d" in tx_hex
        checks["qom_dtrx_bytes"] = "41542b44545258" in tx_hex
        checks["frames_counted"] = (
            int(final.get("frames-sent", 0) or 0) >= 1
            and int(final.get("frames-injected", 0) or 0) >= 1)
        checks["responses_fixture_applied"] = bool(responses)
        checks["guest_workmode_sent"] = "LW915_WORKMODE_SENT" in serial
        checks["guest_send_frame"] = "LW915_SENT" in serial
        checks["driver_product_mismatch_recorded"] = True
        observations[case] = {
            "guest_ready": "LW915_READY" in serial,
            "tx_hex": tx_hex,
            "frames_sent": final.get("frames-sent"),
            "frames_injected": final.get("frames-injected"),
            "responses_hex": responses,
            "boundary": "UART byte layer only: the frozen unit/lorawan.py inherits driver.asr650x"
                        ".LoRaWAN_470 while the product is STM32WLE5/RAK3172; US915 join/OTAA/ABP/"
                        "duty-cycle/FCC/RF are NOT RUN. Official PORT.C is substituted by the "
                        "cores3 PORT.A harness.",
        }
    return checks, observations


def run_case(client: Client, args, case: str) -> dict:
    device = CASES[case]
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device_row = next(row for row in matrix["devices"] if row["id"] == device)
    port = port_for(client, device, case)

    files = args.out_dir / "files"
    shutil.copytree(Path(__file__).parent / "can_lorawan_probe", files, dirs_exist_ok=True)
    (files / "probe_config.py").write_text(
        f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n",
        encoding="utf-8",
    )
    image = build_image(SimpleNamespace(
        base=ROOT / device_row["base"], flash_size=int(device_row["flash_size"], 0),
        files_dir=files, mklittlefs=args.mklittlefs, preserve_vfs=False,
        vfs_offset=int(device_row["vfs_offset"], 0), vfs_size=int(device_row["vfs_size"], 0),
        prog_size=32, out_dir=args.out_dir,
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
            "PORT.C and is not the admitted runtime host port on cores3"),
        "port": {"id": port["id"], "pins": port["pins"]},
        "initial_inputs": INITIAL[case],
        "qom_samples": [], "serial_markers": {}, "observations": {},
    }
    if case in ("can", "mini-can"):
        result["can_fixture_frame"] = CAN_INJECT
    session_id = None
    try:
        artifact = client.json("artifacts", method="POST", body=firmware_bytes, headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": f"{device}-canlorawan-{case}.bin",
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
        if case in ("can", "mini-can"):
            wait_for(client, session_id, lambda text: "CAN_SENT" in text, 120)
            injected = inject(client, session_id, {"inject-hex": CAN_INJECT})
            result["injection"] = {"values": {"inject-hex": CAN_INJECT}, "properties": injected}
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
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        screenshot = client.raw(f"sessions/{session_id}/frame.png")
        (args.out_dir / f"frame-{case}.png").write_bytes(screenshot)
        result["frame"] = {"sha256": sha256(screenshot), "metrics": png_metrics(screenshot)}
        result["checks"]["nonempty_application_frame"] = result["frame"]["metrics"]["unique_colors"] > 1
        if result["status"] == "PASS" and not all(result["checks"].values()):
            result["status"] = "FAIL"
    except Exception as error:  # noqa: BLE001
        result["error"] = str(error)
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
                (args.out_dir / f"evidence-{case}.zip").write_bytes(bundle)
                result["evidence"] = {"sha256": sha256(bundle), "bytes": len(bundle)}
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    required = {"manifest.json", "serial.log", "units/runtime.json",
                                "units/state.json", "units/contract.json"}
                    result["checks"]["evidence_complete"] = required.issubset(archive.namelist())
                    (args.out_dir / f"serial-{case}.txt").write_bytes(archive.read("serial.log"))
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
            if result["status"] == "PASS" and not all(result["checks"].values()):
                result["status"] = "FAIL"
        result["raw_evidence_note"] = (
            "Raw execution artifacts (evidence ZIP, frame, serial log, probe files) stay in the local "
            "ignored .work directory; only concise reports, hashes and reproduction commands are committed.")
        (args.out_dir / f"result-{case}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{case}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8831")
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--mklittlefs", type=Path, default=None)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.api_url)
    result = run_case(client, args, args.case)
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
