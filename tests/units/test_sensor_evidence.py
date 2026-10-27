"""Host-only failure tests for sensor result/evidence gates; no guest runs."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

import run_sensor_cases as runner


def result():
    return {
        "session_id": "probe-session", "device_id": "cores3", "unit_id": "color",
        "firmware_sha256": "1" * 64, "runtime": "qemu", "expected_size": [2, 2],
        "injections": [{"values": values} for values in runner.CASES["color"]["changes"]],
    }


def archive(*, omit=None, bad_hash=False, wrong_firmware=False, changed_input=True, invalid_png=False):
    png = io.BytesIO()
    image = Image.new("RGB", (2, 2), "white")
    image.putpixel((0, 0), (0, 0, 255))
    image.save(png, format="PNG")
    serial = "SENSOR_PROBE_READY color\n" + "".join(
        f"SENSOR_CHECK {name} PASS\n" for name in runner.CASES["color"]["negative"]
    )
    if changed_input:
        for values in runner.CASES["color"]["changes"]:
            serial += "SENSOR_COLOR %d %d %d %d\n" % tuple(values[field] for field in runner.CASES["color"]["fields"])
    files = {
        "serial.log": serial.encode(), "frames/current.png": b"\x89PNG\r\n\x1a\ninvalid" if invalid_png else png.getvalue(),
        "qom/snapshot.json": b"{}", "units/contract.json": b"{}",
        "units/runtime.json": b"{}", "units/state.json": b"{}",
    }
    if omit:
        del files[omit]
    session = {key: result()[key] for key in ("session_id", "device_id", "firmware_sha256", "runtime")}
    session["state"] = "running"
    if wrong_firmware:
        session["firmware_sha256"] = "2" * 64
    manifest = {
        "session": session, "frame": {"unique_colors": 2},
        "units": {"units": [{"unit_id": "color", "available": True}]},
        "files": {name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()} for name, content in files.items()},
    }
    if bad_hash:
        manifest["files"]["serial.log"]["sha256"] = "0" * 64
    files["manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for name, content in files.items():
            zipped.writestr(name, content)
    return output.getvalue()


def thermal_serial(expected):
    lines = ["SENSOR_THERMAL 768 768 %s %s %s" % tuple(expected[key] for key in ("min_c", "max_c", "mean_c"))]
    lines.extend(f"SENSOR_THERMAL_PIXEL {index} {value}" for index, value in expected["samples_c"].items())
    return "\n".join(lines) + "\n"


class SensorEvidenceTests(unittest.TestCase):
    def test_guest_marker_during_booting_does_not_allow_input(self):
        class Client:
            polls = 0

            def json(self, path):
                if "/serial?" in path:
                    return {"data": "SENSOR_PROBE_READY color"}
                self.polls += 1
                return {"state": "booting" if self.polls == 1 else "running"}

        client = Client()
        with patch.object(runner.time, "sleep"):
            runner.wait_for(client, "probe-session", lambda text: "SENSOR_PROBE_READY" in text, timeout=1)
        self.assertEqual(client.polls, 2)

    def test_complete_archive_is_accepted(self):
        self.assertEqual(runner.validate_evidence(archive(), result())["session_id"], "probe-session")

    def test_missing_unit_contract_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "lacks required"):
            runner.validate_evidence(archive(omit="units/runtime.json"), result())

    def test_wrong_firmware_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "another firmware_sha256"):
            runner.validate_evidence(archive(wrong_firmware=True), result())

    def test_mismatching_member_hash_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "hash/size mismatch"):
            runner.validate_evidence(archive(bad_hash=True), result())

    def test_missing_changed_input_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "input observations"):
            runner.validate_evidence(archive(changed_input=False), result())

    def test_invalid_png_is_rejected_even_with_matching_hash(self):
        with self.assertRaises(OSError):
            runner.validate_evidence(archive(invalid_png=True), result())

    def test_partial_thermal_lines_do_not_raise_or_pass(self):
        expected = json.loads((runner.THERMAL / "fixture.json").read_text())["expected"]
        self.assertIsNone(runner.thermal_reading("SENSOR_THERMAL 768 768 27 35 1e-\n", expected))
        self.assertIsNone(runner.thermal_reading("SENSOR_THERMAL 768 768 27 35 29\nSENSOR_THERMAL_PIXEL 0 1e-", expected))

    def test_thermal_nonfinite_or_outside_tolerance_is_rejected(self):
        expected = json.loads((runner.THERMAL / "fixture.json").read_text())["expected"]
        self.assertIsNotNone(runner.thermal_reading(thermal_serial(expected), expected))
        changed = copy.deepcopy(expected)
        changed["samples_c"]["0"] += 0.06
        self.assertIsNone(runner.thermal_reading(thermal_serial(changed), expected))
        changed["samples_c"]["0"] = float("nan")
        self.assertIsNone(runner.thermal_reading(thermal_serial(changed), expected))

    def test_samples_from_different_thermal_frames_do_not_combine(self):
        expected = json.loads((runner.THERMAL / "fixture.json").read_text())["expected"]
        lines = thermal_serial(expected).splitlines()
        mixed = "\n".join(lines[:6] + [lines[0]] + lines[6:])
        self.assertIsNone(runner.thermal_reading(mixed, expected))


if __name__ == "__main__":
    unittest.main()
