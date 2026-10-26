#!/usr/bin/env python3
"""Validate seven external I2C sensors through visible Device Service sessions."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import shutil
import sys
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from run_service_cases import Client  # noqa: E402
from run_control_cases import build_control_image, settled_frame  # noqa: E402

PROBE = Path(__file__).parent / "sensors_probe"
THERMAL = ROOT / "platform/units/fixtures/mlx90640-public-example"
TOOL_SOURCES = {filename: (ROOT / filename).read_bytes() for filename in (
    "tests/units/run_sensor_cases.py", "tests/units/run_control_cases.py",
    "tests/units/run_service_cases.py", "tests/uiflow2/run_profile_ui_test.py",
)}
CASES = {
    "color": {
        "initial": {"clear-raw": 55000, "red-raw": 12000, "green-raw": 8000, "blue-raw": 4000},
        "changes": [
            {"clear-raw": 42000, "red-raw": 9000, "green-raw": 6000, "blue-raw": 3000},
            {"clear-raw": 53000, "red-raw": 21000, "green-raw": 12000, "blue-raw": 6000},
        ],
        "negative": ["color_command_bit_required", "color_identity_read_only", "color_integration_not_ready", "color_adc_saturation"],
        "marker": "SENSOR_COLOR", "fields": ["red-raw", "green-raw", "blue-raw", "clear-raw"],
        "tolerances": [0, 0, 0, 0],
    },
    "tof": {
        "initial": {"distance-mm": 1000}, "changes": [{"distance-mm": 321}, {"distance-mm": 1456}],
        "negative": ["tof_reset_identity_absent", "tof_reset_identity_restored", "tof_conversion_not_ready", "tof_conversion_ready", "tof_interrupt_clear", "tof_old_address_nack", "tof_new_address_identity"],
        "marker": "SENSOR_TOF", "tolerances": [0, 0.001],
    },
    "ncir": {
        "initial": {"ambient-c": 25, "object-c": 32},
        "changes": [{"ambient-c": 17.3, "object-c": 37.1}, {"ambient-c": 31.5, "object-c": 53.2}],
        "negative": ["ncir_eeprom_write_nack", "ncir_pec_6", "ncir_pec_7"],
        "marker": "SENSOR_NCIR", "fields": ["ambient-c", "object-c"], "tolerances": [0.021, 0.021],
    },
    "heart": {
        "initial": {"ir-sample": 40000, "red-sample": 35000},
        "changes": [{"ir-sample": 41000, "red-sample": 36000}, {"ir-sample": 12000, "red-sample": 9000}],
        "negative": ["heart_reset_self_clear", "heart_fifo_initially_empty", "heart_fifo_overflow", "heart_fifo_four_byte_advance", "heart_fifo_sample_order", "heart_reset_clears_fifo", "heart_shutdown_stops_sampling"],
        "marker": "SENSOR_HEART", "fields": ["ir-sample", "red-sample"], "tolerances": [0, 0],
    },
    "tvoc": {
        "initial": {"eco2-ppm": 800, "tvoc-ppb": 40, "raw-h2": 21000, "raw-ethanol": 22000},
        "changes": [
            {"eco2-ppm": 1250, "tvoc-ppb": 230, "raw-h2": 26000, "raw-ethanol": 31000},
            {"eco2-ppm": 675, "tvoc-ppb": 18, "raw-h2": 18300, "raw-ethanol": 24500},
        ],
        "negative": ["tvoc_iaq_before_init_nack", "tvoc_initialization_fixed_output", "tvoc_busy_read_nack", "tvoc_response_crc", "tvoc_response_consumed", "tvoc_bad_argument_crc_nack", "tvoc_unknown_command_nack"],
        "marker": "SENSOR_TVOC", "fields": ["eco2-ppm", "tvoc-ppb", "raw-h2", "raw-ethanol"],
        "tolerances": [0, 0, 0, 0],
    },
    "ultrasonic-i2c": {
        "initial": {"distance-mm": 1000}, "changes": [{"distance-mm": 1234.5}, {"distance-mm": 876.2}],
        "negative": ["ultrasonic_unknown_command_nack", "ultrasonic_conversion_not_ready", "ultrasonic_uint24_units"],
        "marker": "SENSOR_ULTRASONIC", "tolerances": [0.011, 0.011],
    },
    "thermal": {
        "negative": ["thermal_eeprom_write_nack", "thermal_control_readback", "thermal_conversion_not_ready", "thermal_subpage_progression", "thermal_fixture_control_restored", "thermal_768_finite"],
    },
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_for(client, session_id, predicate, *, timeout=60, offset=0):
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        session = client.json(f"sessions/{session_id}")
        latest = client.json(f"sessions/{session_id}/serial?limit=262144").get("data", "")
        if session["state"] in {"failed", "stopped"}:
            raise RuntimeError(session.get("error") or "session ended before observation")
        if "Traceback (most recent call last)" in latest or "SENSOR_PROBE_FAIL" in latest:
            raise RuntimeError("guest probe raised an exception; see serial.txt")
        if session["state"] == "running" and predicate(latest[offset:]):
            return latest
        time.sleep(0.3)
    raise RuntimeError("expected guest observation did not arrive before timeout; see serial.txt")


def reading_matches(case, values, serial):
    spec = CASES[case]
    if case in {"tof", "ultrasonic-i2c"}:
        distance = values["distance-mm"]
        expected = [distance, distance / 10]
    else:
        expected = [values[field] for field in spec["fields"]]
    pattern = re.compile(r"^" + spec["marker"] + r"\s+([^\r\n]+)", re.MULTILINE)
    for match in pattern.finditer(serial):
        try:
            observed = [float(value) for value in match.group(1).split()]
        except ValueError:
            continue
        if len(observed) == len(expected) and all(
            math.isfinite(actual) and abs(actual - target) <= tolerance
            for actual, target, tolerance in zip(observed, expected, spec["tolerances"])
        ):
            return True
    return False


def thermal_reading(serial, expected):
    current = None
    for line in serial.splitlines():
        if line.startswith("SENSOR_THERMAL "):
            parts = line.split()
            if len(parts) != 6:
                current = None
                continue
            try:
                current = {"count": int(parts[1]), "finite": int(parts[2]), "stats": [float(value) for value in parts[3:]], "samples": {}}
            except ValueError:
                current = None
        elif current is not None and line.startswith("SENSOR_THERMAL_PIXEL "):
            try:
                _, index, temperature = line.split()
                current["samples"][index] = float(temperature)
            except ValueError:
                continue
            if set(current["samples"]) != set(expected["samples_c"]):
                continue
            actual = current["stats"] + list(current["samples"].values())
            if not all(math.isfinite(value) for value in actual):
                continue
            if current["count"] != 768 or current["finite"] != 768:
                continue
            if any(abs(actual - expected[key]) > 0.05 for actual, key in zip(current["stats"], ("min_c", "max_c", "mean_c"))):
                continue
            if all(abs(current["samples"][index] - value) <= 0.05 for index, value in expected["samples_c"].items()):
                return current
    return None


def validate_evidence(bundle, result, negative_control=False):
    """Reject unrelated, incomplete or internally inconsistent evidence ZIPs."""
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("evidence ZIP contains a corrupt member")
        required = {"manifest.json", "serial.log", "frames/current.png", "qom/snapshot.json", "units/contract.json", "units/runtime.json", "units/state.json"}
        if not required <= set(archive.namelist()):
            raise RuntimeError("evidence ZIP lacks required serial/frame/QOM/Unit contracts")
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise RuntimeError("evidence ZIP has duplicate members")
        manifest = json.loads(archive.read("manifest.json"))
        if set(manifest["files"]) != set(archive.namelist()) - {"manifest.json"}:
            raise RuntimeError("evidence ZIP and manifest file index differ")
        session = manifest["session"]
        for key in ("session_id", "device_id", "firmware_sha256", "runtime"):
            if session.get(key) != result[key]:
                raise RuntimeError(f"evidence belongs to another {key}")
        if session["state"] != "running":
            raise RuntimeError("evidence was not captured from the active guest")
        serial = archive.read("serial.log").decode("utf-8", errors="replace")
        if f"SENSOR_PROBE_READY {result['unit_id']}" not in serial:
            raise RuntimeError("evidence serial lacks the matching guest readiness marker")
        if "SENSOR_PROBE_FAIL" in serial or "Traceback (most recent call last)" in serial:
            raise RuntimeError("evidence includes a guest probe failure")
        checks = ["thermal_missing_fixture_nack"] if negative_control else CASES[result["unit_id"]]["negative"]
        if any(f"SENSOR_CHECK {name} PASS" not in serial for name in checks):
            raise RuntimeError("evidence lacks required guest negative assertions")
        if not negative_control:
            if result["unit_id"] == "thermal":
                expected = json.loads((THERMAL / "synthetic-plus16.json").read_text())["expected"]
                if thermal_reading(serial, expected) is None:
                    raise RuntimeError("evidence lacks the raw-input-dependent guest thermal result")
            elif not result["injections"] or any(not reading_matches(result["unit_id"], injection["values"], serial) for injection in result["injections"]):
                raise RuntimeError("evidence lacks the same-guest input observations")
        for name, record in manifest["files"].items():
            content = archive.read(name)
            if len(content) != record["size"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise RuntimeError(f"evidence manifest hash/size mismatch: {name}")
        frame = archive.read("frames/current.png")
        if not frame.startswith(b"\x89PNG\r\n\x1a\n") or manifest.get("frame", {}).get("unique_colors", 0) <= 1:
            raise RuntimeError("evidence lacks a nonblank guest application frame")
        with Image.open(io.BytesIO(frame)) as image:
            image.load()
            if image.format != "PNG" or len(set(image.convert("RGB").getdata())) <= 1:
                raise RuntimeError("evidence application frame is invalid or blank")
            if result.get("expected_size") and list(image.size) != result["expected_size"]:
                raise RuntimeError("evidence application frame has the wrong resolution")
        units = manifest.get("units", {}).get("units", [])
        if len(units) != 1 or units[0].get("unit_id") != result["unit_id"] or not units[0].get("available"):
            raise RuntimeError("evidence lacks the matching live Unit state")
        return {"files": sorted(archive.namelist()), "frame": manifest["frame"], "session_id": session["session_id"]}


def qom_value(client, session_id, prop):
    query = urllib.parse.urlencode({"path": "/machine/units/external1/chip", "property": prop})
    return client.json(f"sessions/{session_id}/qom?{query}")["value"]


def verify_drivers():
    manifest = json.loads((PROBE / "sensor_drivers/source-manifest.json").read_text())
    for filename, record in manifest.items():
        if sha256(PROBE / "sensor_drivers" / filename) != record["sha256"]:
            raise RuntimeError(f"vendored official driver hash differs: {filename}")
    return manifest


def verify_image_files(image, files, device):
    """Mount the generated VFS and compare the exact packaged Python bytes."""
    import littlefs
    offset, size = int(device["vfs_offset"], 0), int(device["vfs_size"], 0)
    raw = image.read_bytes()[offset:offset + size]
    filesystem = littlefs.LittleFS(
        context=littlefs.UserContext(buffer=bytearray(raw)), block_size=4096,
        block_count=size // 4096, read_size=128, prog_size=32,
        lookahead_size=128, block_cycles=100, mount=False,
    )
    filesystem.mount()
    hashes = {}
    try:
        for path in sorted(files.rglob("*.py")):
            relative = path.relative_to(files).as_posix()
            with filesystem.open("/" + relative, "rb") as stream:
                content = stream.read()
            if content != path.read_bytes():
                raise RuntimeError(f"packaged guest file differs: {relative}")
            hashes[relative] = hashlib.sha256(content).hexdigest()
    finally:
        filesystem.unmount()
    return hashes


def run_case(client, args, case):
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    spec = CASES[case]
    result = {
        "schema_version": 1, "date": datetime.now(timezone.utc).isoformat(),
        "validation": "negative-runtime-control" if args.thermal_no_fixture else "virtual-device validation",
        "device_id": args.device, "unit_id": case, "runtime": "qemu",
        "status": "FAIL", "checks": {}, "injections": [],
    }
    session_id = None
    try:
        result["official_drivers"] = verify_drivers()
        result["runner_sha256"] = {filename: hashlib.sha256(content).hexdigest() for filename, content in TOOL_SOURCES.items()}
        for filename, content in TOOL_SOURCES.items():
            provenance = output / "tool-sources" / filename
            provenance.parent.mkdir(parents=True, exist_ok=True)
            provenance.write_bytes(content)
        matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
        device = next(row for row in matrix["devices"] if row["id"] == args.device)
        if args.build_only:
            hosts = json.loads((ROOT / "platform/units/host-ports.json").read_text())["hosts"]
            inventory = {"hosts": [next(row for row in hosts if row["device_id"] == args.device)]}
        else:
            inventory = client.json(f"units?device_id={args.device}")
        port = next(row for row in inventory["hosts"][0]["ports"] if row.get("visual_port") == "grove")
        files = output / "files"
        shutil.copytree(PROBE, files, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (files / "probe_config.py").write_text(
            f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\n"
            f"DEVICE_ID = {args.device!r}\nNO_FIXTURE = {args.thermal_no_fixture!r}\n", encoding="utf-8",
        )
        result["probe_sha256"] = {str(path.relative_to(files)): sha256(path) for path in sorted(files.rglob("*.py"))}
        result["port_id"] = port["id"]
        result["expected_size"] = [int(value) for value in device["expected_size"].split("x")]
        image = build_control_image(SimpleNamespace(
            base=args.base or ROOT / device["base"], flash_size=int(device["flash_size"], 0),
            files_dir=files, mklittlefs=None, preserve_vfs=False,
            vfs_offset=int(device["vfs_offset"], 0), vfs_size=int(device["vfs_size"], 0),
            prog_size=32, out_dir=output,
        ))
        result["packaged_python_sha256"] = verify_image_files(image, files, device)
        result["base_firmware_sha256"] = sha256(args.base or ROOT / device["base"])
        result["vfs_prog_size"] = 32
        result["firmware_sha256"] = sha256(image)
        if args.build_only:
            result["status"] = "BUILT"
            return result
        artifact = client.json("artifacts", method="POST", body=image.read_bytes(), headers={
            "Content-Type": "application/octet-stream", "X-Artifact-Name": f"{args.device}-sensor-{case}.bin",
        })
        firmware = client.json("firmware", method="POST", payload={
            "device_id": args.device, "kind": "merged", "artifact_id": artifact["artifact_id"],
        })
        fixture = json.loads((THERMAL / "fixture.json").read_text()) if case == "thermal" else None
        initial = ({} if args.thermal_no_fixture else fixture["initial"]) if fixture else spec["initial"]
        if fixture:
            result["reference_fixture_sha256"] = sha256(THERMAL / "fixture.json")
        session = client.json("sessions", method="POST", payload={
            "device_id": args.device, "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 300, "ready_marker": "SENSOR_PROBE_READY", "ready_timeout_seconds": 180,
            "units": [{"id": "external1", "unit_id": case, "port_id": port["id"], "initial": initial}],
        })
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created", flush=True)
        serial = wait_for(client, session_id, lambda text: f"SENSOR_PROBE_READY {case}" in text, timeout=180)
        result["checks"]["official_driver_ready"] = not args.thermal_no_fixture
        if args.thermal_no_fixture:
            result["checks"] = {"thermal_missing_fixture_nack": "SENSOR_CHECK thermal_missing_fixture_nack PASS" in serial}
        else:
            for name in spec["negative"]:
                result["checks"][name] = f"SENSOR_CHECK {name} PASS" in serial or name == "thermal_768_finite"
            if fixture:
                serial = wait_for(client, session_id, lambda text: thermal_reading(text, fixture["expected"]) is not None)
                result["thermal_reference"] = thermal_reading(serial, fixture["expected"])
                result["checks"]["thermal_768_finite"] = "SENSOR_CHECK thermal_768_finite PASS" in serial
                result["checks"]["thermal_9_reference_samples_within_0_05_c"] = result["thermal_reference"] is not None
                variant_file = THERMAL / "synthetic-plus16.json"
                variant = json.loads(variant_file.read_text())
                values = {key: variant["initial"][key] for key in ("frame0-hex", "frame1-hex")}
                offset = len(serial)
                response = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={"id": "external1", "values": values})
                serial = wait_for(client, session_id, lambda text: thermal_reading(text, variant["expected"]) is not None, offset=offset)
                result["thermal_changed_input"] = thermal_reading(serial[offset:], variant["expected"])
                result["injections"].append({"fixture_sha256": sha256(variant_file), "qom_response_source": response.get("source")})
                result["checks"]["thermal_raw_input_reaches_guest_calculation"] = result["thermal_changed_input"] is not None
            else:
                serial = wait_for(client, session_id, lambda text: reading_matches(case, initial, text))
                result["checks"]["official_driver_initial_fixture"] = True
                for sequence, values in enumerate(spec["changes"], 1):
                    offset = len(serial)
                    response = client.json(f"sessions/{session_id}/unit-input", method="POST", payload={"id": "external1", "values": values})
                    properties = response["units"][0]["properties"]
                    if any(properties.get(key) != value for key, value in values.items()):
                        raise AssertionError("live QOM input differs from requested value")
                    serial = wait_for(client, session_id, lambda text: reading_matches(case, values, text), offset=offset)
                    result["injections"].append({"sequence": sequence, "values": values, "guest_observed": True})
                    result["checks"][f"same_guest_input_{sequence}"] = True
        state = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = state
        result["checks"]["live_controller_state"] = state.get("source") == "live" and state["units"][0]["available"]
        counters = {prop: qom_value(client, session_id, prop) for prop in ("transactions", "read-bytes", "written-bytes", "samples-generated", "crc-errors")}
        result["controller_counters"] = counters
        if not args.thermal_no_fixture:
            result["checks"]["real_i2c_data_plane"] = all(counters[key] > 0 for key in ("transactions", "read-bytes", "written-bytes", "samples-generated"))
            if case == "tvoc":
                result["checks"]["bad_crc_counted_by_chip"] = counters["crc-errors"] >= 1
        screenshot = settled_frame(client, session_id)
        (output / "frame.png").write_bytes(screenshot)
        result["frame_sha256"] = hashlib.sha256(screenshot).hexdigest()
        result["checks"]["frame_available"] = screenshot.startswith(b"\x89PNG")
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if session_id:
            try:
                serial = client.json(f"sessions/{session_id}/serial?limit=262144").get("data", "")
                (output / "serial.txt").write_text(serial, encoding="utf-8")
                result["serial_sha256"] = sha256(output / "serial.txt")
            except Exception as error:
                result["serial_error"] = str(error)
            try:
                bundle = client.raw(f"sessions/{session_id}/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
                result["evidence_summary"] = validate_evidence(bundle, result, args.thermal_no_fixture)
                result["checks"]["evidence_before_stop"] = True
            except Exception as error:
                result["evidence_error"] = str(error)
                result["checks"]["evidence_before_stop"] = False
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", method="DELETE")
                result["checks"]["stopped_with_history"] = stopped["state"] in {"stopped", "failed"}
                retained = client.json(f"sessions/{session_id}")
                result["checks"]["history_metadata_retained"] = retained["state"] in {"stopped", "failed"} and retained["firmware_sha256"] == result["firmware_sha256"]
                result["checks"]["history_last_frame_retained"] = retained.get("last_frame_available") is True
            except Exception as error:
                result["stop_error"] = str(error)
                result["checks"]["stopped_with_history"] = False
        if result["status"] != "BUILT":
            result["status"] = "PASS" if session_id and not result.get("error") and not result.get("serial_error") and all(result["checks"].values()) else "FAIL"
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{case}: {result['status']}" + (f" ({result['error']})" if result.get("error") else ""), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8787")
    parser.add_argument("--device", default="cores3")
    parser.add_argument("--case", choices=[*CASES, "all"], action="append")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path, help="Override the matrix's base UIFlow2 image")
    parser.add_argument("--build-only", "--prepare-only", dest="build_only", action="store_true", help="Build probes offline, without any Device Service API request")
    parser.add_argument("--thermal-no-fixture", action="store_true", help="Only the thermal fail-closed negative control; no sensor PASS claim")
    args = parser.parse_args()
    if args.thermal_no_fixture and args.case != ["thermal"]:
        parser.error("--thermal-no-fixture requires --case thermal")
    cases = list(CASES) if not args.case or "all" in args.case else list(dict.fromkeys(args.case))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    client = Client(args.api_url)
    results = [run_case(client, args, case) for case in cases]
    (args.out_dir / "aggregate.json").write_text(json.dumps({"schema_version": 1, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if all(result["status"] in {"PASS", "BUILT"} for result in results) else 1)


if __name__ == "__main__":
    main()
