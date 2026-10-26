"""Byte-exact host validators extracted from the frozen repository runner.
No guest source import, image builder or service API is loaded here.
"""
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path
from PIL import Image

THERMAL = Path(__file__).resolve().parent / 'fixtures'

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

