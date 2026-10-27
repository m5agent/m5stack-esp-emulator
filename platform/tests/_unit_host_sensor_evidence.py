"""Read-only reconciliation of the explicit sensor/Web host evidence contract.

This checks retained artifacts, including fresh guest samples after product
inputs. It neither executes firmware nor promotes offline preparation to PASS.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

from _unit_host_control_evidence import digest, require

SENSOR_WEB_CONTRACT = "device-service-sensor-web-v1"
BASELINE_COMMIT = "eff1561e9f0da700c843ed14d9019c81f1e27e55"
FIRMWARE_FLAVOR = "reference-app-with-vendored-official-sensor-drivers-host-probe"
SENSOR_CASES = {
    "color": {"address": 41, "marker": "SENSOR_COLOR", "fields": ("red-raw", "green-raw", "blue-raw", "clear-raw"),
        "tolerance": (0, 0, 0, 0), "initial": {"clear-raw": 55000, "red-raw": 12000, "green-raw": 8000, "blue-raw": 4000},
        "changes": ({"clear-raw": 42000, "red-raw": 9000, "green-raw": 6000, "blue-raw": 3000},
                    {"clear-raw": 53000, "red-raw": 21000, "green-raw": 12000, "blue-raw": 6000}),
        "negative": ("color_command_bit_required", "color_identity_read_only", "color_integration_not_ready", "color_adc_saturation")},
    "tof": {"address": 41, "marker": "SENSOR_TOF", "tolerance": (0, .001), "initial": {"distance-mm": 1000},
        "changes": ({"distance-mm": 321}, {"distance-mm": 1456}),
        "negative": ("tof_reset_identity_absent", "tof_reset_identity_restored", "tof_conversion_not_ready", "tof_conversion_ready",
                     "tof_interrupt_clear", "tof_old_address_nack", "tof_new_address_identity")},
    "ncir": {"address": 90, "marker": "SENSOR_NCIR", "fields": ("ambient-c", "object-c"), "tolerance": (.021, .021),
        "initial": {"ambient-c": 25, "object-c": 32},
        "changes": ({"ambient-c": 17.3, "object-c": 37.1}, {"ambient-c": 31.5, "object-c": 53.2}),
        "negative": ("ncir_eeprom_write_nack", "ncir_pec_6", "ncir_pec_7")},
    "heart": {"address": 87, "marker": "SENSOR_HEART", "fields": ("ir-sample", "red-sample"), "tolerance": (0, 0),
        "initial": {"ir-sample": 40000, "red-sample": 35000},
        "changes": ({"ir-sample": 41000, "red-sample": 36000}, {"ir-sample": 12000, "red-sample": 9000}),
        "negative": ("heart_reset_self_clear", "heart_fifo_initially_empty", "heart_fifo_overflow", "heart_fifo_four_byte_advance",
                     "heart_fifo_sample_order", "heart_reset_clears_fifo", "heart_shutdown_stops_sampling")},
    "tvoc": {"address": 88, "marker": "SENSOR_TVOC", "fields": ("eco2-ppm", "tvoc-ppb", "raw-h2", "raw-ethanol"),
        "tolerance": (0, 0, 0, 0), "initial": {"eco2-ppm": 800, "tvoc-ppb": 40, "raw-h2": 21000, "raw-ethanol": 22000},
        "changes": ({"eco2-ppm": 1250, "tvoc-ppb": 230, "raw-h2": 26000, "raw-ethanol": 31000},
                    {"eco2-ppm": 675, "tvoc-ppb": 18, "raw-h2": 18300, "raw-ethanol": 24500}),
        "negative": ("tvoc_iaq_before_init_nack", "tvoc_initialization_fixed_output", "tvoc_busy_read_nack", "tvoc_response_crc",
                     "tvoc_response_consumed", "tvoc_bad_argument_crc_nack", "tvoc_unknown_command_nack")},
    "ultrasonic-i2c": {"address": 87, "marker": "SENSOR_ULTRASONIC", "tolerance": (.011, .011),
        "initial": {"distance-mm": 1000}, "changes": ({"distance-mm": 1234.5}, {"distance-mm": 876.2}),
        "negative": ("ultrasonic_unknown_command_nack", "ultrasonic_conversion_not_ready", "ultrasonic_uint24_units")},
}
COMMON_SENSOR_CHECKS = {"official_driver_ready", "official_driver_initial_fixture", "same_guest_input_1", "same_guest_input_2",
    "live_controller_state", "real_i2c_data_plane", "frame_available", "evidence_before_stop", "stopped_with_history",
    "history_metadata_retained", "history_last_frame_retained"}
OUTER_CHECKS = {"original_sensor_assertions", "prepared_image_and_config_binding", "host_observations", "actual_web",
    "same_host_session_firmware", "positive_inputs_used_product_posts", "no_emergency_cleanup_needed", "retained_stopped_history",
    "flash_released_by_default", "zip_requested_before_stop", "retained_history_and_native_frame", "active_zero_after_case",
    "strict_zip_host_pid_worker_browser_binding", "frozen_execution_sources_unchanged", "execution_toolchain_unchanged",
    "preparation_sources_still_exact"}
GUEST_FAILURES = ("SENSOR_PROBE_FAIL", "HOST_SENSOR_FAIL", "Traceback (most recent call last)", "Guru Meditation", "Rebooting...")


def baseline_source(root, name, entry, expected):
    """Read only an exact regular Git blob from the fixed repository baseline."""
    require(isinstance(name, str) and name and not PurePosixPath(name).is_absolute() and
        PurePosixPath(name).as_posix() == name and ".." not in PurePosixPath(name).parts and
        not any(ord(char) < 32 or char in "\\:" for char in name), "unsafe baseline source path")
    require(entry.get("storage") == "baseline-git-reference" and entry.get("commit") == BASELINE_COMMIT and
        entry.get("repository_path") == name and entry.get("sha256") == expected and
        isinstance(expected, str) and re.fullmatch("[a-f0-9]{64}", expected) and
        isinstance(entry.get("git_blob"), str) and re.fullmatch("[a-f0-9]{40}", entry["git_blob"]),
        "baseline source commit/path/blob/hash differs")
    command = ["git", "--no-replace-objects", "-C", str(Path(root).resolve())]
    tree = subprocess.run([*command, "ls-tree", "--full-tree", "-z", BASELINE_COMMIT, "--", name],
        capture_output=True, timeout=10, check=False)
    require(tree.returncode == 0, "fixed baseline Git tree unavailable")
    rows = [row for row in tree.stdout.split(b"\0") if row]
    require(len(rows) == 1 and b"\t" in rows[0], "baseline source missing or ambiguous")
    header, filename = rows[0].split(b"\t", 1)
    fields = header.split(b" ")
    require(len(fields) == 3 and fields[0] in {b"100644", b"100755"} and fields[1] == b"blob" and
        fields[2].decode("ascii") == entry["git_blob"] and filename == name.encode("utf-8"), "baseline Git blob identity differs")
    blob = subprocess.run([*command, "cat-file", "blob", entry["git_blob"]], capture_output=True, timeout=10, check=False)
    require(blob.returncode == 0 and digest(blob.stdout) == expected and
        hashlib.sha1(b"blob " + str(len(blob.stdout)).encode() + b"\0" + blob.stdout).hexdigest() == entry["git_blob"],
        "baseline Git blob bytes differ")
    return blob.stdout


def source_snapshot(root, name, expected, snapshot_root, entry=None, reconstruction_root=None):
    """Never redirect a missing snapshot to an arbitrary proof-supplied path."""
    require(isinstance(name, str) and name and not Path(name).is_absolute() and ".." not in Path(name).parts and
        "\\" not in name and not any(ord(char) < 32 for char in name), "unsafe frozen source name")
    target = (Path(snapshot_root) / (name + ".txt")).resolve()
    require(target.is_relative_to(Path(root).resolve()), "source snapshot escapes root")
    if entry is not None:
        require(isinstance(entry, dict) and entry.get("sha256") == expected, "source reconstruction hash differs")
        if entry.get("storage") == "baseline-git-reference":
            raw = baseline_source(root, name, entry, expected)
            if target.exists():
                require(digest(target.read_bytes()) == expected, "retained baseline snapshot bytes differ")
            return raw
        require(entry.get("storage") == "verbatim-text-snapshot" and isinstance(entry.get("path"), str) and
            not Path(entry["path"]).is_absolute() and ".." not in Path(entry["path"]).parts and "\\" not in entry["path"],
            "invalid verbatim source reconstruction path/storage")
        require((Path(reconstruction_root) / entry["path"]).resolve() == target, "verbatim reconstruction points to another snapshot")
    require(target.is_file(), "frozen source snapshot missing without exact baseline proof: " + name)
    raw = target.read_bytes()
    require(digest(raw) == expected, "sensor frozen source snapshot differs: " + name)
    return raw


def numeric(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def same_values(actual, expected):
    return isinstance(actual, dict) and set(actual) == set(expected) and all(
        numeric(actual[key]) and actual[key] == value for key, value in expected.items())


def timestamp(value):
    require(isinstance(value, str), "missing input timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "input timestamp lacks timezone")
    return result


def reading_lines(unit, values, serial, start=0, end=None):
    spec = SENSOR_CASES[unit]
    expected = ([values["distance-mm"], values["distance-mm"] / 10]
                if unit in {"tof", "ultrasonic-i2c"} else [values[k] for k in spec["fields"]])
    end = len(serial) if end is None else end
    lines = []
    for match in re.finditer(r"(?m)^" + spec["marker"] + r" ([^\r\n]+)\r?$", serial):
        if not (start <= match.start() and match.end() <= end):
            continue
        try:
            actual = [float(x) for x in match.group(1).split()]
        except ValueError:
            continue
        if len(actual) == len(expected) and all(math.isfinite(x) and abs(x-y) <= tolerance
                for x, y, tolerance in zip(actual, expected, spec["tolerance"])):
            lines.append(match.group(0).rstrip("\r"))
    return lines


def verify_sensor_inputs(unit, serial, controller, browser, report, session, attachment):
    """Independent fixed-vector/negative/POST/fresh-serial oracle for six sensors."""
    spec = SENSOR_CASES[unit]
    ready = list(re.finditer(r"(?m)^SENSOR_PROBE_READY " + re.escape(unit) + r"\r?$", serial))
    require(len(ready) == 1, "sensor readiness marker missing or duplicated")
    for name in spec["negative"]:
        matches = list(re.finditer(r"(?m)^SENSOR_CHECK " + name + r" PASS\r?$", serial))
        require(len(matches) == 1 and matches[0].end() < ready[0].start(), "original sensor negative marker missing or misplaced: " + name)
    require(not any(x in serial for x in GUEST_FAILURES), "guest exception in sensor serial")
    injections = controller.get("injections")
    require(isinstance(injections, list) and len(injections) == 2, "original sensor must retain exactly two injections")
    binding, fresh, posts = report.get("positive_input_binding", {}), report.get("fresh_inputs"), browser.get("posts")
    require(binding.get("schema_version") == 1 and binding.get("status") == "VERIFIED", "positive input binding missing")
    require(all(binding.get(k) == report.get(k) == session.get(k) for k in
        ("session_id", "device_id", "runtime", "firmware_sha256")) and binding.get("unit_id") == unit, "positive input identity differs")
    full_sha = digest(serial.encode("utf-8"))
    require(binding.get("full_serial_sha256") == full_sha, "positive input full serial hash differs")
    vectors = binding.get("vectors")
    require(isinstance(vectors, list) and len(vectors) == 2 and isinstance(fresh, list) and len(fresh) == 2,
            "positive input vector count differs")
    require(isinstance(posts, list) and binding.get("post_count") == len(posts) == sum(len(v) for v in spec["changes"]),
            "actual product POST count differs")
    post_index, previous_end, previous_time = 0, 0, None
    for sequence, (values, vector, raw, injection) in enumerate(zip(spec["changes"], vectors, fresh, injections), 1):
        requested = {"id": attachment["id"], "values": values}
        require(type(injection.get("sequence")) is int and injection["sequence"] == sequence and injection.get("guest_observed") is True and
            same_values(injection.get("values"), values), "original sensor injection metadata differs")
        for item in (vector, raw):
            require(item.get("requested", {}).get("id") == attachment["id"] and
                same_values(item.get("requested", {}).get("values"), values), "fresh input requested vector differs")
        require(type(vector.get("sequence")) is int and vector["sequence"] == sequence and vector.get("guest_observed") is True, "fresh vector observation absent")
        start, end = vector.get("serial_offset_before_ui"), vector.get("serial_end_offset")
        require(type(start) is int and type(end) is int and previous_end <= start < end <= len(serial), "fresh serial windows overlap or are invalid")
        require(type(raw.get("serial_offset_before_ui")) is int and raw["serial_offset_before_ui"] == start, "raw input serial offset differs")
        prefix_sha, window_sha = digest(serial[:start].encode()), digest(serial[start:end].encode())
        require(vector.get("before_serial_sha256") == raw.get("before_serial_sha256") == prefix_sha and
            vector.get("full_serial_sha256") == full_sha and vector.get("fresh_serial_sha256") == window_sha,
            "fresh serial prefix/window hash differs")
        if sequence == 1:
            require(reading_lines(unit, spec["initial"], serial, ready[0].end(), start), "initial driver reading absent before first input")
        observed = reading_lines(unit, values, serial, start, end)
        claimed = vector.get("guest_marker_lines")
        require(observed and isinstance(claimed, list) and claimed and all(line in observed for line in claimed),
                "fresh guest sensor reading absent in this vector window")
        begin, finish = timestamp(vector.get("request_started_at")), timestamp(vector.get("request_returned_at"))
        require(begin <= finish and (previous_time is None or previous_time <= begin), "input request times are unordered")
        require(all(raw.get(k) == vector.get(k) for k in ("request_started_at", "request_returned_at")), "raw input request times differ")
        require(type(vector.get("post_start_index")) is int and type(vector.get("post_end_index")) is int and
            vector["post_start_index"] == post_index and vector["post_end_index"] == post_index + len(values), "POST vector index bounds differ")
        for key, value in values.items():
            post = posts[post_index]
            require(post.get("method") == "POST" and type(post.get("status")) is int and post["status"] == 200 and
                post.get("path") == f"/api/v1/sessions/{session['session_id']}/unit-input", "actual product POST identity/status differs")
            request, response = post.get("request", {}), post.get("response", {})
            require(request.get("id") == attachment["id"] and same_values(request.get("values"), {key: value}), "product POST vector/order differs")
            require(begin <= timestamp(post.get("at")) <= finish, "product POST lies outside its request interval")
            require(response.get("session_id") == session["session_id"] and response.get("state") == "running" and
                response.get("source") == "live", "product POST response has another session/source")
            units = response.get("units", [])
            require(len(units) == 1 and units[0].get("id") == attachment["id"] and units[0].get("unit_id") == unit and
                units[0].get("source") == "guest-qom" and units[0].get("available") is True and not units[0].get("errors"),
                "product POST response is not the selected live guest Unit")
            actual = units[0].get("properties", {}).get(key)
            require(numeric(actual) and actual == value, "product POST response differs from requested physical value")
            post_index += 1
        previous_end, previous_time = end, finish
    require(previous_end == len(serial) and post_index == len(posts), "input binding leaves unaccounted serial or POSTs")
    return {"vectors": 2, "posts": post_index, "serial_sha256": full_sha, "negative_markers": len(spec["negative"])}


def verify_host_display(serial, prepared):
    host, unit = prepared["device_id"], prepared["unit_id"]
    native, canvas, rectangle, scale, height = {
        "atoms3r": ([128, 128], [128, 128], (4, 4, 120), .7, 10),
        "sticks3": ([135, 240], [135, 240], (4, 4, 127), 1.0, 15),
        "stopwatch": ([466, 466], [468, 468], (110, 45, 246), 2.0, 30),
    }[host]
    profile, font = prepared["host_profile"], prepared["display_font"]
    require(profile["size"] == native and profile["canvas_size"] == canvas and profile["rotation"] == 0 and
        font == {"name": "Montserrat12", "scale": scale, "height": height}, "prepared sensor display/font differs")
    x, y, width = rectangle
    rows = 4 if unit in {"color", "tvoc"} else 2
    line_height, body_y = height + 1, y + 2 * (height + 1) + 2
    values = (x, y, width, body_y, line_height, rows, body_y + rows * line_height, 2)
    marker = "HOST_SENSOR_LAYOUT " + " ".join(map(str, values))
    require(re.search(r"(?m)^" + re.escape(marker) + r"\r?$", serial), "actual sensor layout marker differs")
    font_rows = re.findall(r"(?m)^HOST_SENSOR_FONT (\S+) (\S+) ([0-9]+)\r?$", serial)
    require(len(font_rows) == 1 and font_rows[0][0] == "Montserrat12" and
        float(font_rows[0][1]) == scale and int(font_rows[0][2]) == height, "actual sensor font differs")
    defaults = re.findall(r"(?m)^HOST_SENSOR_DEFAULT_FONT_HEIGHT ([1-9][0-9]*)\r?$", serial)
    require(len(defaults) == 1, "sensor default font observation missing or duplicated")


def verify_native_review(review, receipt, validation, report, frames, size):
    """Bind a retained human review without dereferencing its original .work paths."""
    host, unit = report["device_id"], report["unit_id"]
    scope = "captured-final-native-frames-only"
    require(review.get("schema_version") == 1 and review.get("category") == "root-native-frame-review" and
        review.get("status") == "PASS" and review.get("scope") == scope and
        receipt.get("native_readability_scope") == validation.get("native_readability_scope") == scope,
        "native review schema/status/captured-only scope differs")
    rows = review.get("cases")
    expected = {h + "/" + u for h in ("atoms3r", "sticks3", "stopwatch") for u in SENSOR_CASES}
    require(isinstance(rows, dict) and set(rows) == expected, "native review must identify exactly eighteen host/sensor cases")
    row = rows[host + "/" + unit]
    require(isinstance(row, dict) and row.get("native_readability") == receipt["native_readability"], "native review selected case/readability differs")
    def origin(name, suffix):
        require(isinstance(name, str) and name and not PurePosixPath(name).is_absolute() and
            PurePosixPath(name).as_posix() == name and ".." not in PurePosixPath(name).parts and
            not any(ord(char) < 32 or char in "\\:" for char in name) and name.endswith("/" + host + "/" + unit + "/" + suffix),
            "native review source path is unsafe or belongs to another host/sensor")
    selected_report = row.get("report", {})
    origin(selected_report.get("path"), "report.json")
    require(selected_report.get("sha256") == validation["report_sha256"], "native review refers to another raw report hash")
    lines, notes = row.get("observed_lines"), row.get("notes")
    require(isinstance(lines, list) and lines and all(isinstance(x, str) and x for x in lines) and
        isinstance(notes, list) and all(isinstance(x, str) for x in notes), "native review has no observed lines or valid notes")
    additional = row.get("additional_frames", [])
    require(isinstance(additional, list) and receipt.get("observed_lines") == lines and
        receipt.get("additional_frames") == additional and receipt.get("root_review_notes") == notes,
        "normalized native observations differ from the pinned root review")
    seen, hashes = set(), set()
    for index, selected in enumerate([row.get("frame", {}), *additional]):
        require(isinstance(selected, dict), "native reviewed frame is invalid")
        name = selected.get("path")
        suffix = "controller/" + unit + "/frame.png" if isinstance(name, str) and name.endswith("/controller/" + unit + "/frame.png") else "history-frame.png"
        origin(name, suffix)
        require(name not in seen, "duplicate native reviewed frame path")
        seen.add(name)
        channel = "controller" if suffix.startswith("controller/") else "history"
        require(selected.get("sha256") == frames[channel]["sha256"] and
            all(type(selected.get(k)) is int and selected[k] == value for k, value in zip(("width", "height"), size)),
            "native reviewed frame hash/dimensions differ from actual capture")
        observed = lines if index == 0 else selected.get("observed_lines")
        require(isinstance(observed, list) and observed and all(isinstance(x, str) and x for x in observed), "additional native frame has no observed lines")
        hashes.add(selected["sha256"])
    require({frames[k]["sha256"] for k in ("controller", "evidence", "history")} <= hashes,
            "native review omits a distinct actual captured frame")


def verify_sensor_web_evidence(root, report_path, report, validation):
    """Verify immutable sensor evidence; an archive receipt cannot create PASS."""
    root, report_path = Path(root).resolve(), Path(report_path).resolve()
    require(validation.get("evidence_contract") == SENSOR_WEB_CONTRACT, "unknown sensor evidence contract")
    require(report.get("category") == "virtual-device-browser-host-sensors" and report.get("firmware_flavor") == FIRMWARE_FLAVOR,
            "wrong sensor report category or firmware flavor")
    unit, host = report["unit_id"], report["device_id"]
    require(unit in SENSOR_CASES and host in {"atoms3r", "sticks3", "stopwatch"}, "unreviewed host/sensor scope")
    require(OUTER_CHECKS <= set(report.get("checks", {})) and all(v is True for v in report["checks"].values()), "missing or failed sensor execution assertion")
    require(report.get("status") == "PASS" and not report.get("cleanup_errors") and not report.get("host_errors") and
        not report.get("controller_error"), "sensor execution or cleanup failed")
    for key in ("device_id", "unit_id", "runtime", "session_id", "firmware_sha256", "firmware_flavor", "evidence_sha256"):
        require(validation.get(key) == report.get(key), "validation and sensor report differ: " + key)
    require(report.get("runtime") == "qemu", "sensor host runtime differs")
    def path(name, base=root):
        require(isinstance(name, str) and name and not Path(name).is_absolute(), "nonrelative evidence path")
        result = (base / name).resolve()
        require(result.is_relative_to(root), "evidence path escapes root")
        return result
    require(report_path.is_relative_to(root) and json.loads(report_path.read_bytes()) == report, "selected raw sensor report differs")
    def pinned(spec):
        require(isinstance(spec, dict), "missing pinned artifact reference")
        raw = path(spec["path"]).read_bytes()
        require(digest(raw) == spec["sha256"], "pinned artifact hash differs: " + spec["path"])
        return json.loads(raw)
    receipt = pinned({"path": validation["normalization_receipt"], "sha256": validation["normalization_receipt_sha256"]})
    require(receipt.get("schema_version") == 1 and receipt.get("evidence_contract") == SENSOR_WEB_CONTRACT,
            "normalization receipt has another sensor contract")
    require(path(receipt["report"]) == report_path and receipt["report_sha256"] == digest(report_path.read_bytes()) == validation["report_sha256"],
            "normalization receipt refers to another raw sensor report")
    require(receipt.get("scope") == "controller-and-browser-functionality" and receipt.get("native_readability") in {"PASS", "PARTIAL", "NOT VERIFIED"}
        and validation.get("native_readability") == receipt["native_readability"], "sensor functional/native readability scope differs")
    freeze = pinned(receipt["source_freeze"])
    require(isinstance(freeze, dict) and freeze == report.get("source_sha256"), "sensor execution/source freeze differs")
    snapshots = path(receipt["source_snapshot_root"])
    reconstruction = pinned(receipt["source_reconstruction"]) if "source_reconstruction" in receipt else None
    reconstruction_root, execution_entries = None, {}
    if reconstruction is not None:
        reconstruction_root = path(receipt["source_reconstruction"]["path"]).parent
        execution_entries = reconstruction.get("entries", {}).get("execution")
        require(reconstruction.get("schema_version") == 1 and reconstruction.get("baseline_commit") == BASELINE_COMMIT and
            type(reconstruction.get("execution_source_count")) is int and reconstruction["execution_source_count"] == len(freeze) and
            isinstance(execution_entries, dict) and set(execution_entries) == set(freeze), "source reconstruction execution inventory/baseline differs")
    def snapshot(name):
        return source_snapshot(root, name, freeze.get(name), snapshots, execution_entries.get(name), reconstruction_root)
    required_sources = {"platform/units/host-ports.json", "tests/units/run_sensor_cases.py", "tests/units/run_host_sensor_cases.py",
        "tests/units/prepare_host_sensors.py", "tests/units/host_sensors_probe/sensor_probe.py",
        "tests/units/host_sensors_probe/host_sensor_layout.py", "tests/units/sensors_probe/sensor_drivers/source-manifest.json",
        "tests/units/check_batch_evidence.py", "tests/units/web_ui_bridge.py", "platform/tests/unit_web_bridge.mjs",
        "platform/tools/unit_runtime.py", "platform/tools/device_service.py", "platform/tools/serve.py",
        "platform/web/sessions.js", "platform/web/unit-panel.js"}
    require(required_sources <= set(freeze), "sensor source freeze omits direct source or official driver manifest")
    for name in freeze:
        if reconstruction is not None or Path(name).suffix.lower() in {".py", ".js", ".mjs", ".css", ".html", ".json", ".md", ".yaml", ".txt"}:
            snapshot(name)
    readiness = pinned(receipt["preparation_readiness"])
    if reconstruction is not None:
        preparation_freeze = readiness.get("source_sha256")
        entries = reconstruction.get("entries", {}).get("preparation")
        require(isinstance(preparation_freeze, dict) and isinstance(entries, dict) and set(entries) == set(preparation_freeze) and
            type(reconstruction.get("preparation_source_count")) is int and reconstruction["preparation_source_count"] == len(preparation_freeze),
            "source reconstruction preparation inventory differs")
        for name, expected in preparation_freeze.items():
            require(freeze.get(name) == expected, "preparation source is absent from execution freeze")
            source_snapshot(root, name, expected, reconstruction_root / "preparation/source-snapshot", entries[name], reconstruction_root)
    rows = [x for x in readiness["cases"] if x["unit_id"] == unit and x["device_id"] == host]
    require(len(rows) == 1, "sensor preparation has missing or duplicate host case")
    prepared = rows[0]
    require(prepared.get("firmware_sha256") == report["firmware_sha256"] and prepared.get("status") == "PREPARED_NOT_EXECUTED",
            "prepared sensor image hash/status differs")
    fields = {key: prepared[key] for key in ("guest_execution", "web_execution", "admission")}
    require(receipt.get("preparation_only_fields") == fields, "sensor historical preparation scope differs")
    # Archived evidence is data. Load the reviewed checker from this checkout.
    spec = importlib.util.spec_from_file_location("unit_sensor_host_evidence_checker", Path(__file__).resolve().parents[2] / "tests/units/check_batch_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checker = module.Checker(root)
    evidence_path = path(report["evidence"], report_path.parent)
    manifest, _ = checker.zip_manifest(evidence_path, report, unit)
    artifacts = checker.artifacts(report, {}, report_path)
    checker.controller_detail(report, report_path, artifacts)
    checker.browser_detail(report, report_path, artifacts, manifest)
    proof, session = report["runtime_provenance"], manifest["session"]
    checker.direct_record(proof, session, unit, validation["runtime_binary_sha256"])
    require(proof.get("kind") == "direct-pid" and proof.get("status") == "VERIFIED", "sensor direct runtime proof absent")
    worker = session.get("worker", {})
    require(worker.get("lease_active") is True and isinstance(worker.get("worker_id"), str) and worker["worker_id"] and
        type(worker.get("generation")) is int and type(validation.get("worker_generation")) is int and
        proof.get("worker_id") == worker["worker_id"] and proof.get("worker_generation") == worker["generation"] == validation["worker_generation"],
        "sensor running worker identity/generation differs")
    controller = json.loads(path(report["controller_result"], report_path.parent).read_bytes())
    browser = json.loads(path(report["browser_report"], report_path.parent).read_bytes())
    expected_checks = COMMON_SENSOR_CHECKS | set(SENSOR_CASES[unit]["negative"]) | ({"bad_crc_counted_by_chip"} if unit == "tvoc" else set())
    require(set(controller.get("checks", {})) == expected_checks and all(v is True for v in controller["checks"].values()),
            "original unit-specific SENSOR assertions missing")
    adapter = report.get("preparation_adapter", {})
    require(adapter == controller.get("preparation_adapter") and adapter.get("status") == "VERIFIED", "sensor preparation adapter absent or differs")
    require(adapter.get("firmware_sha256") == controller.get("firmware_sha256") == prepared["firmware_sha256"] and
        controller.get("base_firmware_sha256") == prepared["base_firmware_sha256"], "sensor final/base image hash differs")
    packaged = prepared["probe_sha256"]
    require(adapter.get("restored_probe_sha256") == adapter.get("actual_packaged_probe_sha256") == controller.get("packaged_python_sha256") == packaged,
            "sensor actual/restored packaged Python metadata differs")
    before = adapter.get("original_runner_prebuild_probe_sha256", {})
    require(controller.get("probe_sha256") == before and set(before) == set(packaged) and
        all(before[name] == value for name, value in packaged.items() if name != "probe_config.py") and
        before.get("probe_config.py") == adapter.get("original_runner_config_sha256") and
        packaged.get("probe_config.py") == adapter.get("restored_config_sha256"), "sensor original prebuild metadata was replaced")
    require(adapter.get("complete_vfs_sha256") == prepared["packaged_full_py_sha256"] and
        all(prepared["packaged_full_py_sha256"].get(k) == v for k, v in packaged.items()) and
        "rtc_probe.py" in prepared["packaged_full_py_sha256"], "sensor complete VFS metadata differs")
    require({k: v for k, v in prepared["prepared_file_sha256"].items() if k.endswith(".py")} == packaged,
            "sensor prepared file/Python membership differs")
    for name, record in json.loads(snapshot("tests/units/sensors_probe/sensor_drivers/source-manifest.json")).items():
        require(controller.get("official_drivers", {}).get(name) == record and packaged.get("sensor_drivers/" + name) == record["sha256"],
                "sensor official driver bytes/metadata differ")
    with zipfile.ZipFile(evidence_path) as archive:
        contract, runtime, state = [json.loads(archive.read("units/" + name + ".json")) for name in ("contract", "runtime", "state")]
        zip_serial = archive.read("serial.log").decode("utf-8")
        native_zip = archive.read("frames/current.png")
    require(not any(x in zip_serial for x in GUEST_FAILURES), "guest exception in sensor ZIP serial")
    normalized = session["units"]
    require(browser.get("attachments") == runtime.get("attachments") == normalized and len(normalized) == 1 and normalized[0]["unit_id"] == unit,
            "sensor normalized attachment trees differ")
    attachment = normalized[0]
    require(prepared.get("attachments") == [{key: attachment[key] for key in ("id", "unit_id", "port_id", "initial")}] and
        same_values(attachment.get("initial"), SENSOR_CASES[unit]["initial"]), "prepared sensor attachment/initial differs")
    units = state.get("units", [])
    require(state.get("session_id") == session["session_id"] and state.get("source") == "live" and len(units) == 1 and
        all(units[0].get(k) == v for k, v in attachment.items()) and units[0].get("source") == "guest-qom" and
        units[0].get("available") is True and not units[0].get("errors"), "sensor Unit state has another source/session/attachment")
    for key in ("transactions", "read-bytes", "written-bytes", "samples-generated"):
        require(type(controller.get("controller_counters", {}).get(key)) is int and controller["controller_counters"][key] > 0,
                "sensor controller data-plane counter absent: " + key)
    for key in ("transactions", "read-bytes", "written-bytes", "input-events"):
        require(type(units[0].get("properties", {}).get(key)) is int and units[0]["properties"][key] > 0, "sensor live data plane absent: " + key)
    require(type(controller["controller_counters"].get("crc-errors")) is int and controller["controller_counters"]["crc-errors"] >= (1 if unit == "tvoc" else 0),
            "sensor CRC negative counter absent")
    ports_raw = snapshot("platform/units/host-ports.json")
    require(digest(ports_raw) == contract["source_hashes"]["host-ports.json"], "sensor ZIP/frozen host map differs")
    hosts = [x for x in json.loads(ports_raw)["hosts"] if x["device_id"] == host]
    ports = [x for x in hosts[0]["ports"] if x["id"] == attachment["port_id"]] if len(hosts) == 1 else []
    require(len(ports) == 1 and ports[0].get("wiring_status") == "confirmed" and ports[0].get("physical_presence") == "main-device" and
        ports[0]["pins"] == attachment["pins"] and ports[0]["visual_port"] == attachment["visual_port"], "sensor attachment pins differ from confirmed host map")
    profile = prepared["host_profile"]
    verify_host_display(zip_serial, prepared)
    markers = ["HOST_SENSOR_GEOMETRY %d %d %d" % (*profile["canvas_size"], profile["rotation"]),
        "HOST_SENSOR_INTERNAL before 36 1", "HOST_SENSOR_INTERNAL after_init 36 2",
        "HOST_SENSOR_EXTERNAL_SCAN %d" % SENSOR_CASES[unit]["address"], "HOST_SENSOR_EXTERNAL_AFTER_INIT %d" % SENSOR_CASES[unit]["address"]]
    require(all(re.search(r"(?m)^" + re.escape(line) + r"\r?$", zip_serial) for line in markers), "sensor host geometry/BMI/routing marker absent")
    offset = report.get("host_observations", {}).get("fresh_after_op_offset")
    require(type(offset) is int and 0 <= offset < len(zip_serial) and re.search(r"(?m)^HOST_SENSOR_INTERNAL after_op 36 ([3-9]|[1-9][0-9]+)\r?$", zip_serial[offset:]),
            "fresh post-sensor internal BMI marker absent")
    serial_path = path(report["positive_input_binding"]["serial_artifact"], report_path.parent)
    require(serial_path == path("serial.txt", path(report["controller_result"], report_path.parent).parent) and
        checker.label(serial_path) in artifacts, "sensor serial artifact is not the pinned controller serial")
    serial_raw = serial_path.read_bytes()
    require(digest(serial_raw) == controller.get("serial_sha256") and zip_serial.startswith(serial_raw.decode("utf-8")), "sensor controller/ZIP serial differs")
    inputs = verify_sensor_inputs(unit, serial_raw.decode("utf-8"), controller, browser, report, session, attachment)
    frame_observations = receipt.get("frame_observations", {})
    require(frame_observations.get("scope") == "separate-captures-no-atomic-frame-claim", "separate frame capture scope absent")
    frame_paths = {"controller": path("frame.png", path(report["controller_result"], report_path.parent).parent),
                   "history": path("history-frame.png", report_path.parent)}
    captured_frames = {"evidence": native_zip}
    for channel, frame_path in frame_paths.items():
        observation = frame_observations.get(channel, {})
        require(path(observation.get("path")) == frame_path and checker.label(frame_path) in artifacts,
                "sensor frame has another path or is not artifact-pinned: " + channel)
        captured_frames[channel] = frame_path.read_bytes()
    observation = frame_observations.get("evidence", {})
    require(path(observation.get("archive_path")) == evidence_path and observation.get("archive_sha256") == report["evidence_sha256"] and
            observation.get("member") == "frames/current.png", "sensor evidence frame has another ZIP/member")
    for channel, raw in captured_frames.items():
        observation = frame_observations[channel]
        require(observation.get("sha256") == digest(raw), "sensor frame observation hash differs: " + channel)
        dimensions = checker.png(raw, "native sensor " + channel + " frame")
        require([dimensions["width"], dimensions["height"]] == profile["size"] and
            all(type(observation.get(key)) is int and observation[key] == value for key, value in dimensions.items()),
            "sensor native framebuffer dimensions differ: " + channel)
        with module.Image.open(io.BytesIO(raw)) as image:
            require(any(low != high for low, high in image.convert("RGB").getextrema()), "sensor native framebuffer is blank: " + channel)
    require(digest(captured_frames["controller"]) == controller.get("frame_sha256"), "sensor controller frame hash differs")
    if receipt["native_readability"] != "NOT VERIFIED":
        reference = receipt.get("native_review")
        require(isinstance(reference, dict) and validation.get("native_review") == reference.get("path") and
            validation.get("native_review_sha256") == reference.get("sha256"), "native readability has no matching pinned root review")
        verify_native_review(pinned(reference), receipt, validation, report, frame_observations, profile["size"])
    history = pinned(receipt["history_snapshot"])
    require(all(history.get(k) == report[k] for k in ("session_id", "device_id", "runtime", "firmware_sha256")) and
        history.get("state") == "stopped" and history.get("flash_retained") is False, "clean sensor history/Flash release absent")
    return {"evidence_contract": SENSOR_WEB_CONTRACT, "scope": receipt["scope"], "native_readability": receipt["native_readability"],
            "original_sensor_assertions": len(expected_checks), "positive_inputs": inputs}
