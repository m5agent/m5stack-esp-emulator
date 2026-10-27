"""Offline adversarial contract fixtures; no session or execution evidence is created."""
from __future__ import annotations

import ast
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

import _unit_host_sensor_evidence as evidence

ROOT = Path(__file__).resolve().parents[2]


def original_cases():
    tree = ast.parse((ROOT / "tests/units/run_sensor_cases.py").read_text())
    return ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign) and
        any(isinstance(name, ast.Name) and name.id == "CASES" for name in node.targets)))


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()


def sample_line(unit, values):
    # Independent formatting of the original driver's public units.
    if unit == "color":
        return "SENSOR_COLOR %d %d %d %d" % tuple(values[k] for k in ("red-raw", "green-raw", "blue-raw", "clear-raw"))
    if unit in {"tof", "ultrasonic-i2c"}:
        return ("SENSOR_TOF" if unit == "tof" else "SENSOR_ULTRASONIC") + " %.3f %.3f" % (values["distance-mm"], values["distance-mm"] / 10)
    if unit == "ncir":
        return "SENSOR_NCIR %.4f %.4f" % (values["ambient-c"], values["object-c"])
    if unit == "heart":
        return "SENSOR_HEART %d %d" % (values["ir-sample"], values["red-sample"])
    return "SENSOR_TVOC %d %d %d %d" % tuple(values[k] for k in ("eco2-ppm", "tvoc-ppb", "raw-h2", "raw-ethanol"))


def input_fixture(unit="color"):
    spec = original_cases()[unit]
    session = {"session_id": "offline-synthetic-session", "device_id": "atoms3r", "runtime": "qemu", "firmware_sha256": "a" * 64}
    attachment = {"id": "external1", "unit_id": unit}
    serial = "".join("SENSOR_CHECK " + name + " PASS\r\n" for name in spec["negative"])
    serial += "SENSOR_PROBE_READY " + unit + "\r\n" + sample_line(unit, spec["initial"]) + "\r\n"
    starts, fresh, vectors, posts = [], [], [], []
    for sequence, values in enumerate(spec["changes"], 1):
        starts.append(len(serial))
        begin, finish = f"2026-10-26T00:00:0{sequence * 2}Z", f"2026-10-26T00:00:0{sequence * 2 + 1}Z"
        requested = {"id": "external1", "values": copy.deepcopy(values)}
        raw = {"requested": requested, "serial_offset_before_ui": len(serial), "before_serial_sha256": evidence.digest(serial.encode()),
               "request_started_at": begin, "request_returned_at": finish}
        fresh.append(raw)
        post_start = len(posts)
        for key, value in values.items():
            posts.append({"method": "POST", "status": 200, "at": begin,
                "path": "/api/v1/sessions/offline-synthetic-session/unit-input", "request": {"id": "external1", "values": {key: value}},
                "response": {"session_id": session["session_id"], "state": "running", "source": "live", "units": [
                    {**attachment, "source": "guest-qom", "available": True, "errors": {}, "properties": {key: value}}]}})
        serial += sample_line(unit, values) + "\r\n"
        vectors.append({**copy.deepcopy(raw), "sequence": sequence, "guest_observed": True,
            "guest_marker_lines": [sample_line(unit, values)], "post_start_index": post_start, "post_end_index": len(posts)})
    for index, vector in enumerate(vectors):
        end = starts[index + 1] if index == 0 else len(serial)
        vector.update(serial_end_offset=end, full_serial_sha256=evidence.digest(serial.encode()),
                      fresh_serial_sha256=evidence.digest(serial[starts[index]:end].encode()))
    controller = {"injections": [{"sequence": n, "values": copy.deepcopy(values), "guest_observed": True}
        for n, values in enumerate(spec["changes"], 1)]}
    report = {**session, "unit_id": unit, "fresh_inputs": fresh,
        "positive_input_binding": {**session, "schema_version": 1, "status": "VERIFIED", "unit_id": unit,
            "full_serial_sha256": evidence.digest(serial.encode()), "post_count": len(posts), "vectors": vectors}}
    return unit, serial, controller, {"posts": posts}, report, session, attachment


class SensorInputContractTests(unittest.TestCase):
    def test_all_six_original_cases_have_independent_negative_and_two_vector_oracles(self):
        for unit, fixed in evidence.SENSOR_CASES.items():
            with self.subTest(unit=unit):
                original = original_cases()[unit]
                self.assertEqual(tuple(original["negative"]), fixed["negative"])
                self.assertEqual(tuple(original["changes"]), fixed["changes"])
                self.assertEqual(original["initial"], fixed["initial"])
                result = evidence.verify_sensor_inputs(*input_fixture(unit))
                self.assertEqual(result["vectors"], 2)

    def test_old_or_missing_second_reading_does_not_satisfy_fresh_window(self):
        for unit in evidence.SENSOR_CASES:
            fixture = list(input_fixture(unit))
            values = original_cases()[unit]["changes"][1]
            stale = sample_line(unit, values)
            serial = fixture[1]
            fixture[1] = serial.replace(stale, "STALE" + " " * (len(stale) - 5))
            self.rehash(fixture)
            with self.subTest(unit=unit), self.assertRaisesRegex(AssertionError, "fresh guest"):
                evidence.verify_sensor_inputs(*fixture)

    @staticmethod
    def rehash(fixture):
        serial, report = fixture[1], fixture[4]
        binding = report["positive_input_binding"]
        binding["full_serial_sha256"] = evidence.digest(serial.encode())
        for raw, vector in zip(report["fresh_inputs"], binding["vectors"]):
            start, end = vector["serial_offset_before_ui"], vector["serial_end_offset"]
            raw["before_serial_sha256"] = vector["before_serial_sha256"] = evidence.digest(serial[:start].encode())
            vector["full_serial_sha256"] = evidence.digest(serial.encode())
            vector["fresh_serial_sha256"] = evidence.digest(serial[start:end].encode())

    def test_mutated_asserted_pass_is_rejected_by_actual_input_oracle(self):
        faults = {
            "missing-negative": lambda f: f.__setitem__(1, f[1].replace("SENSOR_CHECK color_adc_saturation PASS", "SENSOR_CHECK color_adc_saturation FAIL")),
            "bool-value": lambda f: f[3]["posts"][0]["request"]["values"].update({"clear-raw": True}),
            "nan-response": lambda f: f[3]["posts"][0]["response"]["units"][0]["properties"].update({"clear-raw": float("nan")}),
            "wrong-instance": lambda f: f[3]["posts"][0]["request"].update(id="external2"),
            "wrong-session": lambda f: f[3]["posts"][0].update(path="/api/v1/sessions/another/unit-input"),
            "post-404": lambda f: f[3]["posts"][0].update(status=404),
            "cached-response": lambda f: f[3]["posts"][0]["response"].update(source="cached"),
            "host-fake": lambda f: f[3]["posts"][0]["response"]["units"][0].update(source="host-cache"),
            "wrong-response-value": lambda f: f[3]["posts"][0]["response"]["units"][0]["properties"].update({"clear-raw": 1}),
            "missing-post": lambda f: f[3]["posts"].pop(),
            "extra-post": lambda f: f[3]["posts"].append(copy.deepcopy(f[3]["posts"][0])),
            "post-order": lambda f: f[3]["posts"].reverse(),
            "post-outside-time": lambda f: f[3]["posts"][0].update(at="2026-10-25T00:00:00Z"),
            "raw-time-differs": lambda f: f[4]["fresh_inputs"][0].update(request_returned_at="2026-10-26T00:00:08Z"),
            "fake-prefix": lambda f: f[4]["positive_input_binding"]["vectors"][0].update(before_serial_sha256="0" * 64),
            "fake-slice": lambda f: f[4]["positive_input_binding"]["vectors"][0].update(fresh_serial_sha256="0" * 64),
            "wrong-full-hash": lambda f: f[4]["positive_input_binding"].update(full_serial_sha256="0" * 64),
            "overlap": lambda f: f[4]["positive_input_binding"]["vectors"][1].update(serial_offset_before_ui=0),
            "bool-sequence": lambda f: f[4]["positive_input_binding"]["vectors"][0].update(sequence=True),
            "fake-marker-claim": lambda f: f[4]["positive_input_binding"]["vectors"][0].update(guest_marker_lines=["SENSOR_COLOR 1 2 3 4"]),
            "third-injection": lambda f: f[2]["injections"].append(copy.deepcopy(f[2]["injections"][0])),
            "wrong-original-vector": lambda f: f[2]["injections"][0]["values"].update({"clear-raw": 1}),
        }
        for name, mutate in faults.items():
            fixture = list(input_fixture())
            mutate(fixture)
            with self.subTest(fault=name), self.assertRaises((AssertionError, ValueError)):
                evidence.verify_sensor_inputs(*fixture)

    def test_distance_units_and_nonfinite_samples_cannot_be_relabelled_as_pass(self):
        for unit in ("tof", "ultrasonic-i2c"):
            fixture = list(input_fixture(unit))
            old = sample_line(unit, original_cases()[unit]["changes"][0])
            fixture[1] = fixture[1].replace(old, old.rsplit(" ", 1)[0] + " nan")
            self.rehash(fixture)
            with self.subTest(unit=unit), self.assertRaisesRegex(AssertionError, "fresh guest"):
                evidence.verify_sensor_inputs(*fixture)


class SensorArchiveFixture:
    """Synthetic offline contract material; never represents a firmware run."""
    def __init__(self, root):
        self.root = root
        self.case = root / "archive/color"
        self.controller_dir = self.case / "controller/color"
        self.browser_dir = self.case / "browser/session"
        self.controller_dir.mkdir(parents=True)
        self.browser_dir.mkdir(parents=True)
        checker = root / "tests/units/check_batch_evidence.py"
        checker.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "tests/units/check_batch_evidence.py", checker)
        unit, serial, controller, browser, report, session, _ = input_fixture()
        self.session = {**session, "state": "running", "pid": 12, "worker": {"worker_id": "synthetic-worker", "generation": 9, "lease_active": True}}
        self.attachment = {"id": "external1", "unit_id": unit, "port_id": "custom", "pins": {"yellow": 2, "white": 1},
            "visual_port": "grove", "initial": copy.deepcopy(original_cases()[unit]["initial"])}
        self.session["units"] = [self.attachment]
        self.serial = serial
        self.zip_serial = ("HOST_SENSOR_GEOMETRY 128 128 0\r\nHOST_SENSOR_INTERNAL before 36 1\r\n"
            "HOST_SENSOR_EXTERNAL_SCAN 41\r\nHOST_SENSOR_INTERNAL after_init 36 2\r\nHOST_SENSOR_EXTERNAL_AFTER_INIT 41\r\n"
            "HOST_SENSOR_DEFAULT_FONT_HEIGHT 15\r\nHOST_SENSOR_FONT Montserrat12 0.7 10\r\nHOST_SENSOR_LAYOUT 4 4 120 28 11 4 72 2\r\n")
        # Host observations are appended to the controller serial, exactly as
        # this offline fixture's declared retained artifacts record them.
        self.zip_serial = serial + self.zip_serial
        fresh_after = len(self.zip_serial)
        self.zip_serial += "HOST_SENSOR_INTERNAL after_op 36 3\r\n"
        self.frame = self.png()
        self.controller = {**session, **controller, "unit_id": unit, "status": "PASS", "firmware_flavor": evidence.FIRMWARE_FLAVOR,
            "checks": {k: True for k in evidence.COMMON_SENSOR_CHECKS | set(original_cases()[unit]["negative"])},
            "base_firmware_sha256": "c" * 64, "serial_sha256": evidence.digest(serial.encode()), "frame_sha256": evidence.digest(self.frame),
            "controller_counters": {"transactions": 10, "read-bytes": 10, "written-bytes": 10, "samples-generated": 10, "crc-errors": 0}}
        source_names = ["platform/units/host-ports.json", "tests/units/run_sensor_cases.py", "tests/units/run_host_sensor_cases.py",
            "tests/units/prepare_host_sensors.py", "tests/units/host_sensors_probe/sensor_probe.py",
            "tests/units/host_sensors_probe/host_sensor_layout.py", "tests/units/sensors_probe/sensor_drivers/source-manifest.json",
            "tests/units/check_batch_evidence.py", "tests/units/web_ui_bridge.py", "platform/tests/unit_web_bridge.mjs",
            "platform/tools/unit_runtime.py", "platform/tools/device_service.py", "platform/tools/serve.py",
            "platform/web/sessions.js", "platform/web/unit-panel.js"]
        self.sources = {name: (ROOT / name).read_bytes() for name in source_names}
        drivers = json.loads(self.sources["tests/units/sensors_probe/sensor_drivers/source-manifest.json"])
        probe = {"main.py": evidence.digest(b"# offline synthetic guest\n"), "probe_config.py": evidence.digest(b"# prepared config\n"),
            **{"sensor_drivers/" + name: record["sha256"] for name, record in drivers.items()}}
        old = {**probe, "probe_config.py": evidence.digest(b"# original prebuild config\n")}
        complete = {**probe, "rtc_probe.py": evidence.digest(b"# explicit shared builder member\n")}
        adapter = {"schema_version": 1, "status": "VERIFIED", "firmware_sha256": session["firmware_sha256"],
            "original_runner_prebuild_probe_sha256": old, "restored_probe_sha256": probe, "actual_packaged_probe_sha256": probe,
            "original_runner_config_sha256": old["probe_config.py"], "restored_config_sha256": probe["probe_config.py"], "complete_vfs_sha256": complete}
        self.prepared = {"device_id": "atoms3r", "unit_id": unit, "status": "PREPARED_NOT_EXECUTED", "firmware_sha256": session["firmware_sha256"],
            "base_firmware_sha256": "c" * 64, "attachments": [{key: self.attachment[key] for key in ("id", "unit_id", "port_id", "initial")}],
            "guest_execution": "NOT RUN", "web_execution": "NOT RUN", "admission": {"status": "BLOCKED"},
            "probe_sha256": probe, "packaged_full_py_sha256": complete, "prepared_file_sha256": probe,
            "display_font": {"name": "Montserrat12", "scale": .7, "height": 10},
            "host_profile": {"size": [128, 128], "canvas_size": [128, 128], "rotation": 0}}
        self.controller.update(preparation_adapter=adapter, probe_sha256=old, packaged_python_sha256=probe, official_drivers=drivers)
        self.browser = {**session, **browser, "errors": [], "attachments": [self.attachment], "readbacks": [{"offline_fixture": True}],
            "snapshots": [{"phase": "before-evidence", "session_state": "running", "screenshot": "before.png", "units": [{
                "instance": "external1", "readback": {"id": "external1", "unit_id": unit, "source": "guest-qom", "available": True},
                "dom_matches_product_readback": True, "readback_matches_real_http_response": True}]}]}
        self.report = {**report, "category": "virtual-device-browser-host-sensors", "status": "PASS", "firmware_flavor": evidence.FIRMWARE_FLAVOR,
            "checks": {key: True for key in evidence.OUTER_CHECKS}, "host_errors": [], "cleanup_errors": [], "controller_error": None,
            "host_observations": {"fresh_after_op_offset": fresh_after}, "controller_result": "controller/color/result.json",
            "browser_report": "browser/session/web-report.json", "evidence": "controller/color/evidence.zip", "preparation_adapter": adapter,
            "runtime_provenance": {**session, "kind": "direct-pid", "status": "VERIFIED", "observed_pid": 12,
                "runtime_binary_sha256": "b" * 64, "worker_id": "synthetic-worker", "worker_generation": 9}}
        self.report["positive_input_binding"]["serial_artifact"] = "controller/color/serial.txt"
        self.history = {**session, "state": "stopped", "flash_retained": False}
        self.extra_zip = {}
        self.save()

    @staticmethod
    def png(blank=False, size=(128, 128), pixel=(1, 2, 3)):
        image = Image.new("RGB", size, "white")
        if not blank:
            image.putpixel((0, 0), pixel)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else json_bytes(value))
        return {"path": path.relative_to(self.root).as_posix(), "sha256": evidence.digest(path.read_bytes())}

    def save(self):
        self.controller["frame_sha256"] = evidence.digest(self.frame)
        self.report["source_sha256"] = {name: evidence.digest(raw) for name, raw in self.sources.items()}
        for name, raw in self.sources.items():
            self.write(self.root / "archive/source-snapshot" / (name + ".txt"), raw)
        state_unit = {**self.attachment, "source": "guest-qom", "available": True, "errors": {},
            "properties": {key: 5 for key in ("transactions", "read-bytes", "written-bytes", "input-events")}}
        evidence_frame, history_frame = getattr(self, "evidence_frame", self.frame), getattr(self, "history_frame", self.frame)
        members = {"serial.log": self.zip_serial.encode(), "frames/current.png": evidence_frame, "qom/snapshot.json": b"{}",
            "units/contract.json": json_bytes({"source_hashes": {"host-ports.json": evidence.digest(self.sources["platform/units/host-ports.json"])}}),
            "units/runtime.json": json_bytes({"attachments": [self.attachment]}),
            "units/state.json": json_bytes({"session_id": self.session["session_id"], "source": "live", "units": [state_unit]}), **self.extra_zip}
        manifest = {"session": self.session, "units": {"units": [state_unit]}, "files": {name: {"size": len(raw), "sha256": evidence.digest(raw)} for name, raw in members.items()}}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, raw in members.items():
                archive.writestr(name, raw)
            archive.writestr("manifest.json", json_bytes(manifest))
        self.report["evidence_sha256"] = self.controller["evidence_sha256"] = evidence.digest(buffer.getvalue())
        self.write(self.controller_dir / "evidence.zip", buffer.getvalue())
        self.write(self.controller_dir / "result.json", self.controller)
        self.write(self.controller_dir / "serial.txt", self.serial.encode())
        self.write(self.controller_dir / "frame.png", self.frame)
        self.write(self.case / "history-frame.png", history_frame)
        self.write(self.browser_dir / "before.png", self.png())
        self.write(self.browser_dir / "web-report.json", self.browser)
        self.report["artifact_sha256"] = {p.relative_to(self.case).as_posix(): evidence.digest(p.read_bytes())
            for p in self.case.rglob("*") if p.is_file() and p.name not in {"report.json", "normalization-receipt.json"}}
        self.report_path = self.case / "report.json"
        report_pin = self.write(self.report_path, self.report)
        receipt = {"schema_version": 1, "evidence_contract": evidence.SENSOR_WEB_CONTRACT, "report": report_pin["path"],
            "report_sha256": report_pin["sha256"], "scope": "controller-and-browser-functionality", "native_readability": "NOT VERIFIED",
            "source_freeze": self.write(self.root / "archive/source-before.json", self.report["source_sha256"]),
            "source_snapshot_root": "archive/source-snapshot", "preparation_readiness": self.write(self.root / "archive/readiness.json", {
                "cases": [self.prepared], "source_sha256": self.report["source_sha256"]}),
            "preparation_only_fields": {key: self.prepared[key] for key in ("guest_execution", "web_execution", "admission")},
            "history_snapshot": self.write(self.case / "history.json", self.history)}
        receipt["frame_observations"] = {"scope": "separate-captures-no-atomic-frame-claim"}
        for channel, frame in (("controller", self.frame), ("evidence", evidence_frame), ("history", history_frame)):
            with Image.open(io.BytesIO(frame)) as image:
                width, height = image.size
            entry = {"sha256": evidence.digest(frame), "width": width, "height": height}
            if channel == "evidence":
                entry.update(archive_path=(self.controller_dir / "evidence.zip").relative_to(self.root).as_posix(),
                    archive_sha256=self.report["evidence_sha256"], member="frames/current.png")
            else:
                entry["path"] = (self.controller_dir / "frame.png" if channel == "controller" else self.case / "history-frame.png").relative_to(self.root).as_posix()
            receipt["frame_observations"][channel] = entry
        if hasattr(self, "frame_observation_mutation"):
            self.frame_observation_mutation(receipt["frame_observations"])
        native_pin = None
        if hasattr(self, "native_review"):
            native_pin = self.write(self.root / "archive/native-review.json", self.native_review)
            native_row = self.native_review.get("cases", {}).get("atoms3r/color", {})
            receipt.update(native_readability="PASS", native_review=native_pin,
                native_readability_scope="captured-final-native-frames-only", observed_lines=native_row.get("observed_lines"),
                additional_frames=native_row.get("additional_frames", []), root_review_notes=native_row.get("notes"))
        if hasattr(self, "reconstruction"):
            receipt["source_reconstruction"] = self.write(self.root / "archive/source-reconstruction.json", self.reconstruction)
        pin = self.write(self.case / "normalization-receipt.json", receipt)
        self.validation = {key: self.report[key] for key in ("device_id", "unit_id", "runtime", "session_id", "firmware_sha256", "firmware_flavor", "evidence_sha256")}
        self.validation.update(evidence_contract=evidence.SENSOR_WEB_CONTRACT, report_sha256=report_pin["sha256"], normalization_receipt=pin["path"],
            normalization_receipt_sha256=pin["sha256"], native_readability="NOT VERIFIED", worker_generation=9, runtime_binary_sha256="b" * 64)
        if native_pin is not None:
            self.validation.update(native_readability="PASS", native_review=native_pin["path"], native_review_sha256=native_pin["sha256"],
                native_readability_scope="captured-final-native-frames-only")

    def verify(self):
        return evidence.verify_sensor_web_evidence(self.root, self.report_path, self.report, self.validation)

    def reconstruct_sources(self):
        for name, raw in self.sources.items():
            self.write(self.root / "archive/preparation/source-snapshot" / (name + ".txt"), raw)
        self.reconstruction = {"schema_version": 1, "baseline_commit": evidence.BASELINE_COMMIT,
            "execution_source_count": len(self.sources), "preparation_source_count": len(self.sources), "entries": {
                lane: {name: {"storage": "verbatim-text-snapshot", "path": prefix + name + ".txt", "sha256": evidence.digest(raw)}
                    for name, raw in self.sources.items()}
                for lane, prefix in (("execution", "source-snapshot/"), ("preparation", "preparation/source-snapshot/"))}}
        self.save()

    def reviewed_native(self):
        def frame(path, raw):
            return {"path": ".work/offline-review/atoms3r/color/" + path, "sha256": evidence.digest(raw), "width": 128, "height": 128}
        row = {"report": {"path": ".work/offline-review/atoms3r/color/report.json", "sha256": evidence.digest(self.report_path.read_bytes())},
            "native_readability": "PASS", "frame": frame("history-frame.png", getattr(self, "history_frame", self.frame)),
            "observed_lines": ["atoms3r", "color", "R 21000"], "notes": ["Synthetic offline review record; no human or firmware execution claim."],
            "additional_frames": []}
        if getattr(self, "history_frame", self.frame) != self.frame:
            row["additional_frames"].append({**frame("controller/color/frame.png", self.frame), "observed_lines": ["color", "R 0"]})
        self.native_review = {"schema_version": 1, "category": "root-native-frame-review", "status": "PASS", "scope": "captured-final-native-frames-only",
            "cases": {host + "/" + unit: (row if host == "atoms3r" and unit == "color" else {})
                for host in ("atoms3r", "sticks3", "stopwatch") for unit in original_cases() if unit != "thermal"}}
        self.save()


class SensorArchiveContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="m5-sensor-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture = SensorArchiveFixture(Path(self.temporary.name))

    def test_synthetic_fixture_only_exercises_read_only_contract(self):
        result = self.fixture.verify()
        self.assertEqual(result["evidence_contract"], evidence.SENSOR_WEB_CONTRACT)
        self.assertEqual(result["native_readability"], "NOT VERIFIED")
        self.assertEqual(result["positive_inputs"]["vectors"], 2)

    def test_separate_live_captures_may_have_distinct_pixels(self):
        f = self.fixture
        f.evidence_frame = f.png(pixel=(4, 5, 6))
        f.history_frame = f.png(pixel=(7, 8, 9))
        f.save()
        self.assertEqual(f.verify()["evidence_contract"], evidence.SENSOR_WEB_CONTRACT)
        faults = {
            "frame-hash": lambda o: o["controller"].update(sha256="0" * 64),
            "other-case-frame": lambda o: o["controller"].update(path="archive/color/history-frame.png"),
            "wrong-zip": lambda o: o["evidence"].update(archive_sha256="0" * 64),
            "wrong-member": lambda o: o["evidence"].update(member="frames/another.png"),
            "wrong-frame-dims": lambda o: o["history"].update(width=129),
        }
        for name, mutate in faults.items():
            f.frame_observation_mutation = mutate
            f.save()
            with self.subTest(fault=name), self.assertRaises(AssertionError):
                f.verify()

    def test_rehashed_metadata_cannot_mask_artifact_identity_or_controller_gaps(self):
        faults = {
            "control-contract": lambda f: f.validation.update(evidence_contract="device-service-control-web-v1"),
            "wrong-host": lambda f: f.session.update(device_id="sticks3"),
            "wrong-pid": lambda f: f.session.update(pid=13),
            "worker-reuse": lambda f: f.session["worker"].update(generation=10),
            "missing-negative": lambda f: f.controller["checks"].pop("color_adc_saturation"),
            "original-probe-overwritten": lambda f: f.controller.update(probe_sha256=f.prepared["probe_sha256"]),
            "wrong-image-hash": lambda f: f.report["preparation_adapter"].update(firmware_sha256="d" * 64),
            "missing-vfs-member": lambda f: f.prepared["packaged_full_py_sha256"].pop("rtc_probe.py"),
            "tampered-packaged-driver": lambda f: f.prepared["probe_sha256"].update({"sensor_drivers/tcs3472.py": "d" * 64}),
            "zero-controller-counter": lambda f: f.controller["controller_counters"].update({"samples-generated": 0}),
            "history-kept-flash": lambda f: f.history.update(flash_retained=True),
            "zip-late-exception": lambda f: setattr(f, "zip_serial", f.zip_serial + "Traceback (most recent call last)\r\n"),
            "actual-font": lambda f: setattr(f, "zip_serial", f.zip_serial.replace("Montserrat12 0.7", "Montserrat12 0.8")),
            "actual-layout": lambda f: setattr(f, "zip_serial", f.zip_serial.replace("4 4 120 28 11 4 72 2", "4 4 120 28 11 4 73 2")),
            "blank-native": lambda f: setattr(f, "frame", f.png(blank=True)),
            "bad-native-size": lambda f: setattr(f, "frame", f.png(size=(129, 128))),
            "zip-unsafe-member": lambda f: f.extra_zip.update({"../unsafe": b"x"}),
        }
        for name, mutate in faults.items():
            with self.subTest(fault=name), tempfile.TemporaryDirectory(prefix="m5-sensor-fault-") as temporary:
                f = SensorArchiveFixture(Path(temporary))
                mutate(f)
                if name != "control-contract":
                    f.save()
                with self.assertRaises((AssertionError, ValueError)):
                    f.verify()

    def test_snapshot_bytes_or_pinned_receipt_cannot_change_after_hashing(self):
        f = self.fixture
        snapshot = f.root / "archive/source-snapshot/tests/units/run_sensor_cases.py.txt"
        snapshot.write_bytes(snapshot.read_bytes() + b"# changed\n")
        with self.assertRaisesRegex(AssertionError, "snapshot differs"):
            f.verify()
        f.save()
        receipt = f.case / "normalization-receipt.json"
        receipt.write_bytes(receipt.read_bytes() + b" ")
        with self.assertRaisesRegex(AssertionError, "pinned artifact hash"):
            f.verify()

    def test_complete_reconstruction_inventory_and_verbatim_paths_are_pinned(self):
        f = self.fixture
        f.reconstruct_sources()
        self.assertEqual(f.verify()["evidence_contract"], evidence.SENSOR_WEB_CONTRACT)
        original = copy.deepcopy(f.reconstruction)
        faults = {
            "unknown-baseline": lambda r: r.update(baseline_commit="0" * 40),
            "count": lambda r: r.update(execution_source_count=1),
            "missing-execution-source": lambda r: r["entries"]["execution"].pop("tests/units/run_sensor_cases.py"),
            "missing-preparation-source": lambda r: r["entries"]["preparation"].pop("tests/units/run_sensor_cases.py"),
            "other-snapshot": lambda r: r["entries"]["execution"]["tests/units/run_sensor_cases.py"].update(path="preparation/source-snapshot/tests/units/run_sensor_cases.py.txt"),
            "outside": lambda r: r["entries"]["execution"]["tests/units/run_sensor_cases.py"].update(path="../../outside.txt"),
            "unknown-storage": lambda r: r["entries"]["execution"]["tests/units/run_sensor_cases.py"].update(storage="url"),
            "rehash": lambda r: r["entries"]["execution"]["tests/units/run_sensor_cases.py"].update(sha256="0" * 64),
        }
        for name, mutate in faults.items():
            f.reconstruction = copy.deepcopy(original)
            mutate(f.reconstruction)
            f.save()
            with self.subTest(fault=name), self.assertRaises(AssertionError):
                f.verify()
        f.reconstruction = original
        f.save()
        target = f.root / "archive/source-snapshot/tests/units/run_sensor_cases.py.txt"
        target.unlink()
        with self.assertRaisesRegex(AssertionError, "snapshot missing"):
            f.verify()

    def test_native_pass_requires_the_actual_pinned_review_and_all_distinct_frames(self):
        f = self.fixture
        f.evidence_frame = f.history_frame = f.png(pixel=(4, 5, 6))
        f.save()
        f.reviewed_native()
        # Original .work paths intentionally do not exist in this fixture.
        self.assertEqual(f.verify()["native_readability"], "PASS")
        original = copy.deepcopy(f.native_review)
        faults = {
            "wrong-schema": lambda r: r.update(category="untrusted-description"),
            "wrong-scope": lambda r: r.update(scope="all-runtime-values"),
            "wrong-case": lambda r: r["cases"].pop("atoms3r/color"),
            "wrong-report-hash": lambda r: r["cases"]["atoms3r/color"]["report"].update(sha256="0" * 64),
            "missing-distinct-frame": lambda r: r["cases"]["atoms3r/color"].update(additional_frames=[]),
            "bad-original-path": lambda r: r["cases"]["atoms3r/color"]["frame"].update(path="../../outside.png"),
            "another-host-path": lambda r: r["cases"]["atoms3r/color"]["frame"].update(path=".work/offline-review/sticks3/color/history-frame.png"),
            "wrong-frame-hash": lambda r: r["cases"]["atoms3r/color"]["frame"].update(sha256="0" * 64),
            "wrong-frame-size": lambda r: r["cases"]["atoms3r/color"]["frame"].update(width=129),
            "missing-lines": lambda r: r["cases"]["atoms3r/color"].update(observed_lines=[]),
        }
        for name, mutate in faults.items():
            f.native_review = copy.deepcopy(original)
            mutate(f.native_review)
            f.save()
            with self.subTest(fault=name), self.assertRaises(AssertionError):
                f.verify()
        f.native_review = original
        f.save()
        f.validation["native_review_sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "matching pinned root review"):
            f.verify()

    def test_rehashed_native_pass_label_without_a_review_is_rejected(self):
        f = self.fixture
        receipt_path = f.case / "normalization-receipt.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["native_readability"] = "PASS"
        f.write(receipt_path, receipt)
        f.validation.update(native_readability="PASS", normalization_receipt_sha256=evidence.digest(receipt_path.read_bytes()))
        with self.assertRaisesRegex(AssertionError, "matching pinned root review"):
            f.verify()


class FixedBaselineSourceTests(unittest.TestCase):
    """Exercise Git blob identity with a tiny, isolated synthetic repository.

    Testing the reconstruction contract must not require a developer's .work
    directory or an unrelated historical commit to exist in a clean clone.
    The explicit historical archive verifier still pins the real baseline.
    """
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="m5-source-reference-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.name = "platform/tools/ble_probe.py"
        cls.raw = b"# Synthetic Git reconstruction contract fixture; no execution evidence.\n"
        source = cls.root / cls.name
        source.parent.mkdir(parents=True)
        source.write_bytes(cls.raw)
        command = ["git", "--no-replace-objects", "-C", str(cls.root)]
        subprocess.run([*command, "init", "--quiet", "--object-format=sha1"], check=True, capture_output=True, timeout=10)
        subprocess.run([*command, "add", "--", cls.name], check=True, capture_output=True, timeout=10)
        subprocess.run([*command, "-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgSign=false", "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "synthetic source fixture"],
                       check=True, capture_output=True, timeout=10)
        cls.commit = subprocess.run([*command, "rev-parse", "HEAD"], capture_output=True, check=True, timeout=10).stdout.decode().strip()
        import hashlib
        cls.entry = {"storage": "baseline-git-reference", "commit": cls.commit, "repository_path": cls.name,
            "git_blob": hashlib.sha1(b"blob " + str(len(cls.raw)).encode() + b"\0" + cls.raw).hexdigest(), "sha256": evidence.digest(cls.raw)}

    def setUp(self):
        baseline = patch.object(evidence, "BASELINE_COMMIT", self.commit)
        baseline.start()
        self.addCleanup(baseline.stop)

    def test_exact_regular_baseline_blob_reconstructs_absent_text_without_api(self):
        snapshot = self.root / "absent-source-snapshot"
        self.assertEqual(evidence.source_snapshot(self.root, self.name, self.entry["sha256"], snapshot, self.entry, self.root), self.raw)
        self.assertFalse(snapshot.exists())

    def test_unknown_commit_path_blob_hash_and_missing_source_fail_closed(self):
        for fault in ("commit", "repository_path", "git_blob", "sha256"):
            entry = dict(self.entry)
            entry[fault] = "0" * (40 if fault in {"commit", "git_blob"} else 64) if fault != "repository_path" else "platform/tools/serve.py"
            with self.subTest(fault=fault), self.assertRaises(AssertionError):
                evidence.baseline_source(self.root, self.name, entry, self.entry["sha256"])
        absent = "platform/tools/not-an-existing-baseline-source.py"
        entry = {**self.entry, "repository_path": absent}
        with self.assertRaisesRegex(AssertionError, "missing"):
            evidence.baseline_source(self.root, absent, entry, self.entry["sha256"])

    def test_missing_baseline_git_tree_fails_closed(self):
        absent_commit = "0" * 40
        with patch.object(evidence, "BASELINE_COMMIT", absent_commit), self.assertRaisesRegex(AssertionError, "unavailable"):
            evidence.baseline_source(self.root, self.name, {**self.entry, "commit": absent_commit}, self.entry["sha256"])

    def test_unsafe_names_or_arbitrary_proof_paths_never_reach_git(self):
        for name in ("../outside.py", "/tmp/outside.py", "platform/../outside.py", "platform\\outside.py", "HEAD:path", "platform/./tools/x.py", "platform/tools/x\n.py"):
            with self.subTest(name=name), patch.object(evidence.subprocess, "run") as git, self.assertRaises(AssertionError):
                evidence.baseline_source(self.root, name, {**self.entry, "repository_path": name}, self.entry["sha256"])
            git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
