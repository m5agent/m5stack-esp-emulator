"""Strict reconciliation for the explicit control/Web host evidence contract.

This validates immutable execution artifacts. It does not create a second live
PID observation, modify raw reports, or equate a functional PASS with readable
native-display or physical-device validation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

CONTROL_WEB_CONTRACT = "device-service-control-web-v1"
COMMON_CONTROL_CHECKS = {
    "exact_official_driver_ready", "same_guest_i2c_controller_counters", "stopped_with_history",
}
CONTROL_CHECKS = {
    "joystick-v11": {"three_raw_bytes_reach_guest"},
    "encoder": {"signed_int16_and_active_low_driver", "guest_led_writes_read_back"},
    "8encoder": {"eight_signed_channels_buttons_and_switch", "guest_counter_write_reset_and_address_change",
                 "all_nine_guest_rgb_register_triplets"},
    "cardkb": {"all_47_nonmodifier_keys_via_i2c", "all_three_one_shot_modifiers",
               "all_four_official_key_tables_and_modifier_locks", "legacy_byte_consumption"},
    "rfid2": {"request_anticollision_select_auth_block_write_read_halt",
              "wrong_key_halt_and_antenna_negative_controls", "four_seven_ten_byte_uid_cascade_select",
              "card_removal_reaches_guest"},
}
OUTER_CHECKS = {
    "original_control_assertions", "host_observations", "actual_web", "same_host_session_firmware",
    "positive_inputs_used_product_posts", "no_emergency_cleanup_needed", "retained_stopped_history",
    "flash_released_by_default", "zip_requested_before_stop", "retained_history_and_native_frame",
    "active_zero_after_case", "strict_zip_host_pid_worker_browser_binding",
    "frozen_execution_sources_unchanged", "execution_toolchain_unchanged",
}


def require(value, message):
    if not value:
        raise AssertionError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_control_web_evidence(root, report_path, report, validation):
    """Validate the explicit contract; legacy dual-observer validation is separate.

    normalization_receipt binds the archive locations for an unchanged raw
    report, the original source freeze/preparation snapshot and a post-run
    read-only history response. Its preparation_only_fields explicitly label
    historical NOT RUN/BLOCKED values carried by the shared packaging record.
    """
    root, report_path = Path(root).resolve(), Path(report_path).resolve()
    require(validation.get("evidence_contract") == CONTROL_WEB_CONTRACT, "unknown control evidence contract")
    require(report.get("category") == "virtual-device-browser-host-controls", "wrong control report category")
    require(report.get("firmware_flavor") == "reference-app-with-vendored-official-control-drivers-host-probe",
            "wrong control firmware flavor")
    unit, host = report["unit_id"], report["device_id"]
    require(unit in CONTROL_CHECKS and host in {"atoms3r", "sticks3", "stopwatch"}, "unreviewed host/control scope")
    require(OUTER_CHECKS <= set(report.get("checks", {})) and
            all(v is True for v in report["checks"].values()), "missing or failed execution assertion")
    require(report.get("status") == "PASS" and not report.get("cleanup_errors") and
            not report.get("host_errors"), "execution or cleanup failed")

    def path(name, base=root):
        require(isinstance(name, str) and name and not Path(name).is_absolute(), "nonrelative evidence path")
        result = (base / name).resolve()
        require(result.is_relative_to(root), "evidence path escapes root")
        return result

    def pinned(spec):
        require(isinstance(spec, dict), "missing pinned artifact reference")
        target = path(spec["path"])
        raw = target.read_bytes()
        require(digest(raw) == spec["sha256"], "pinned artifact hash differs: " + spec["path"])
        return json.loads(raw)

    receipt = pinned({"path": validation["normalization_receipt"],
                      "sha256": validation["normalization_receipt_sha256"]})
    require(receipt.get("schema_version") == 1 and receipt.get("evidence_contract") == CONTROL_WEB_CONTRACT,
            "normalization receipt has another contract")
    require(path(receipt["report"]) == report_path and
            receipt["report_sha256"] == digest(report_path.read_bytes()) == validation["report_sha256"],
            "normalization receipt refers to another raw report")
    require(receipt.get("scope") == "controller-and-browser-functionality", "functional scope must remain explicit")
    require(receipt.get("native_readability") in {"PASS", "PARTIAL", "NOT VERIFIED"}, "native readability absent")
    require(validation.get("native_readability") == receipt["native_readability"], "native readability scope differs")
    source_freeze = pinned(receipt["source_freeze"])
    require(source_freeze == report["source_sha256"], "execution/source freeze map differs")
    snapshot_root = path(receipt["source_snapshot_root"])

    def snapshot(source_name):
        target = path(source_name + ".txt", snapshot_root)
        raw = target.read_bytes()
        require(digest(raw) == source_freeze.get(source_name), "frozen source snapshot differs: " + source_name)
        return raw

    readiness = pinned(receipt["preparation_readiness"])
    prepared = [x for x in readiness["cases"] if x["unit_id"] == unit and x["device_id"] == host]
    require(len(prepared) == 1 and prepared[0]["firmware_sha256"] == report["firmware_sha256"],
            "preparation case/firmware differs")
    prepared = prepared[0]

    # Archived evidence is data. Load the reviewed checker from this checkout.
    spec = importlib.util.spec_from_file_location("unit_control_host_evidence_checker", Path(__file__).resolve().parents[2] / "tests/units/check_batch_evidence.py")
    checker_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker_module)
    checker = checker_module.Checker(root)
    manifest, _ = checker.zip_manifest(path(report["evidence"], report_path.parent), report, unit)
    artifacts = checker.artifacts(report, {}, report_path)
    checker.controller_detail(report, report_path, artifacts)
    checker.browser_detail(report, report_path, artifacts, manifest)
    proof, session = report["runtime_provenance"], manifest["session"]
    checker.direct_record(proof, session, unit, validation["runtime_binary_sha256"])
    require(proof.get("kind") == "direct-pid" and proof.get("status") == "VERIFIED", "direct runtime proof absent")
    worker = session.get("worker", {})
    require(worker.get("lease_active") is True and isinstance(worker.get("worker_id"), str) and worker["worker_id"] and
            type(worker.get("generation")) is int, "running lease identity missing")
    require(proof.get("worker_id") == worker["worker_id"] and proof.get("worker_generation") == worker["generation"] ==
            validation["worker_generation"], "worker generation differs")

    controller = json.loads(path(report["controller_result"], report_path.parent).read_bytes())
    browser = json.loads(path(report["browser_report"], report_path.parent).read_bytes())
    expected_checks = COMMON_CONTROL_CHECKS | CONTROL_CHECKS[unit]
    require(set(controller["checks"]) == expected_checks and all(v is True for v in controller["checks"].values()),
            "original unit-specific CONTROL assertions missing")
    preparation_fields = {key: prepared[key] for key in ("guest_execution", "web_execution", "admission")}
    require(receipt.get("preparation_only_fields") == preparation_fields and
            all(controller.get(key) == value for key, value in preparation_fields.items()),
            "historical preparation fields were reinterpreted or raw record changed")
    require(controller["host_profile"] == prepared["host_profile"], "prepared host geometry differs")
    with zipfile.ZipFile(path(report["evidence"], report_path.parent)) as archive:
        contract = json.loads(archive.read("units/contract.json"))
        runtime = json.loads(archive.read("units/runtime.json"))
        state = json.loads(archive.read("units/state.json"))
        serial = archive.read("serial.log").decode("utf-8")
        native_zip = archive.read("frames/current.png")
    normalized = session["units"]
    require(browser["attachments"] == runtime["attachments"] == normalized, "normalized attachment trees differ")
    def attachment_ids(rows):
        return [{k: x[k] for k in ("id", "unit_id", "port_id")} for x in rows]
    require(attachment_ids(normalized) == attachment_ids(controller["attachments"]) ==
            attachment_ids(prepared["attachments"]), "requested attachment projections differ")
    require(controller["attachments"] == prepared["attachments"], "prepared attachment request differs")
    require(len(normalized) == 1 and normalized[0]["unit_id"] == unit, "unexpected control attachment set")
    attachment = normalized[0]
    for key in ("initial", "parent_id"):
        if key in controller["attachments"][0]:
            require(controller["attachments"][0][key] == attachment.get(key), "optional attachment field differs")
    state_unit = [x for x in state["units"] if x["id"] == attachment["id"]]
    require(state.get("session_id") == session["session_id"] and state.get("source") == "live" and len(state_unit) == 1,
            "Unit state has another session or source")
    state_unit = state_unit[0]
    require(state_unit.get("source") == "guest-qom" and state_unit.get("available") is True and
            not state_unit.get("errors"), "Unit state unavailable")
    require(all(state_unit.get(k) == attachment.get(k) for k in attachment), "state attachment differs")
    require(all(type(state_unit["properties"].get(k)) is int and state_unit["properties"][k] > 0
                for k in ("transactions", "read-bytes", "written-bytes", "input-events")), "controller data plane absent")
    ports_raw = snapshot("platform/units/host-ports.json")
    require(digest(ports_raw) == contract["source_hashes"]["host-ports.json"], "ZIP host ports source binding differs")
    ports = json.loads(ports_raw)["hosts"]
    host_rows = [x for x in ports if x["device_id"] == host]
    require(len(host_rows) == 1, "host ports snapshot lacks device")
    port_rows = [x for x in host_rows[0]["ports"] if x["id"] == attachment["port_id"]]
    require(len(port_rows) == 1, "attachment port absent from frozen host map")
    port = port_rows[0]
    require(port.get("wiring_status") == "confirmed" and port.get("physical_presence") == "main-device" and
            port["pins"] == attachment["pins"] and port["visual_port"] == attachment["visual_port"],
            "normalized attachment pins differ from confirmed host map")
    profile = prepared["host_profile"]
    markers = ["HOST_CONTROL_GEOMETRY %d %d %d" % (*profile["canvas_size"], profile["rotation"]),
               "HOST_CONTROL_INTERNAL before 36 1", "HOST_CONTROL_INTERNAL after_init 36 2"]
    address = {"joystick-v11": 82, "encoder": 64, "8encoder": 65, "cardkb": 95, "rfid2": 40}[unit]
    markers.extend(["HOST_CONTROL_EXTERNAL_SCAN %d" % address,
                    "HOST_CONTROL_EXTERNAL_AFTER_INIT %d" % (66 if unit == "8encoder" else address)])
    require(all(re.search(r"(?m)^" + re.escape(text) + r"\r?$", serial) for text in markers), "host geometry/BMI/routing marker missing")
    offset = report["host_observations"].get("fresh_after_op_offset")
    require(type(offset) is int and 0 <= offset < len(serial) and re.search(
        r"(?m)^HOST_CONTROL_INTERNAL after_op 36 ([3-9]|[1-9][0-9]+)\r?$", serial[offset:]), "fresh post-control BMI marker absent")
    require(not any(x in serial for x in ("CONTROL_PROBE_ERROR", "HOST_CONTROL_FAIL", "Traceback (most recent call last)", "Guru Meditation")),
            "guest failure in evidence serial")
    native = path("frame.png", path(report["controller_result"], report_path.parent).parent).read_bytes()
    history_frame = path("history-frame.png", report_path.parent).read_bytes()
    require(native == native_zip == history_frame, "native/history/ZIP framebuffer differs")
    dimensions = checker.png(native, "native control frame")
    require([dimensions["width"], dimensions["height"]] == profile["size"], "native framebuffer host geometry differs")
    require(browser.get("posts") and all(x.get("status") == 200 and x.get("method") == "POST" and
            x.get("path") == f"/api/v1/sessions/{session['session_id']}/unit-input" and
            x.get("request", {}).get("id") == attachment["id"] for x in browser["posts"]), "real product input posts absent")
    history = pinned(receipt["history_snapshot"])
    require(all(history.get(k) == report[k] for k in ("session_id", "device_id", "runtime", "firmware_sha256")) and
            history.get("state") == "stopped" and history.get("flash_retained") is False, "clean stopped history/Flash release absent")
    return {"evidence_contract": CONTROL_WEB_CONTRACT, "scope": receipt["scope"],
            "native_readability": receipt["native_readability"], "original_control_assertions": len(expected_checks)}
