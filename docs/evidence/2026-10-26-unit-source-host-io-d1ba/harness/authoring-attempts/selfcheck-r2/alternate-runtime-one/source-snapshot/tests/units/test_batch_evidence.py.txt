"""Fault controls for the read-only, explicitly selected Unit batch checker."""
from __future__ import annotations

import base64
import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

from check_batch_evidence import Checker, REQUIRED_ZIP, digest, main


BINARY = "a" * 64
FIRMWARE = "b" * 64
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg+M/wHwAEAQH/cetH5QAAAABJRU5ErkJggg==")


class BatchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m5-unit-batch-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("platform/units/catalog.json", {"units": [{"id": "alpha"}, {"id": "beta"}]})
        self.selection = {
            "schema_version": 1, "device_id": "cores3", "runtime": "qemu",
            "expected_runtime_binary_sha256": BINARY, "required_layers": ["guest_controller"],
            "cases": [self.make_case("alpha", 11), self.make_case("beta", 12)],
        }

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def read(self, name):
        return json.loads((self.root / name).read_bytes())

    def make_case(self, unit, pid):
        session = {"session_id": unit + "-session", "device_id": "cores3", "runtime": "qemu", "state": "running", "firmware_sha256": FIRMWARE, "pid": pid, "worker": {"worker_id": "worker", "generation": 5, "lease_active": True}}
        report = {"unit_id": unit, "device_id": "cores3", "runtime": "qemu", "session_id": session["session_id"], "firmware_sha256": FIRMWARE, "status": "PASS", "checks": {"guest": True, "data_plane": True}}
        contents = {name: b"{}" for name in REQUIRED_ZIP - {"manifest.json"}}
        contents["frames/current.png"] = PNG
        contents["serial.log"] = b"READY\n"
        manifest = {"session": session, "units": {"units": [{"id": "external1", "unit_id": unit, "available": True}]}}
        self.write_zip(unit, report, manifest, contents)
        self.write(unit + "/runtime.json", {"session_id": session["session_id"], "pid": pid, "observed_binary_sha256": BINARY, "status": "PASS"})
        return {"unit_id": unit, "guest_controller": {"report": unit + "/report.json", "runtime_proof": {"kind": "direct-pid", "path": unit + "/runtime.json"}}}

    def write_zip(self, unit, report, manifest, contents):
        manifest = copy.deepcopy(manifest)
        manifest["files"] = {name: {"size": len(content), "sha256": digest(content)} for name, content in contents.items()}
        path = self.root / unit / "evidence.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest))
        report["evidence_sha256"] = digest(path.read_bytes())
        self.write(unit + "/report.json", report)

    def zip_parts(self, unit):
        with zipfile.ZipFile(self.root / unit / "evidence.zip") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            contents = {name: archive.read(name) for name in archive.namelist() if name != "manifest.json"}
        return manifest, contents

    def check(self, selection=None, *, strict=False):
        return Checker(self.root, strict_direct=strict).check(self.selection if selection is None else selection)

    def alpha(self, summary, layer="guest_controller"):
        return summary["cases"][0][layer]

    def test_complete_selected_guest_batch_passes_with_exact_unique_counts(self):
        result = self.check()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["layers"]["guest_controller"]["counts"]["PASS"], 2)
        self.assertEqual(result["layers"]["guest_controller"]["direct_pid_units"], 2)
        self.assertEqual(result["layers"]["live_browser"]["counts"]["NOT RUN"], 2)

    def test_default_requires_all_three_layers_instead_of_inheriting_guest_pass(self):
        self.selection.pop("required_layers")
        result = self.check()
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["layers"]["guest_controller"]["status"], "PASS")
        self.assertEqual(result["layers"]["live_browser"]["status"], "PARTIAL")

    def test_unselected_successful_attempt_never_fills_a_missing_unit(self):
        self.selection["cases"][0]["guest_controller"] = None
        self.assertEqual(self.alpha(self.check())["status"], "NOT RUN")

    def test_missing_selected_report_or_zip_is_not_run(self):
        self.selection["cases"][0]["guest_controller"]["report"] = "not-yet-recorded/report.json"
        self.assertEqual(self.alpha(self.check())["status"], "NOT RUN")
        self.selection["cases"][0]["guest_controller"]["report"] = "alpha/report.json"
        self.selection["cases"][0]["guest_controller"]["evidence"] = "not-yet-recorded/evidence.zip"
        self.assertEqual(self.alpha(self.check())["status"], "NOT RUN")

    def test_catalog_requires_exact_unique_selection(self):
        for rows in (self.selection["cases"][:1], self.selection["cases"] * 2, [*self.selection["cases"], {"unit_id": "extra"}]):
            selection = copy.deepcopy(self.selection)
            selection["cases"] = rows
            result = self.check(selection)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(result["errors"])

    def test_report_false_integer_empty_or_failure_cannot_pass(self):
        original = self.read("alpha/report.json")
        for checks, status in (({"bad": False}, "PASS"), ({"integer": 1}, "PASS"), ({}, "PASS"), ({"good": True}, "FAIL")):
            report = copy.deepcopy(original)
            report.update(checks=checks, status=status)
            self.write("alpha/report.json", report)
            self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_zip_whole_hash_is_required_and_checked(self):
        report = self.read("alpha/report.json")
        for value in (None, "c" * 64):
            report["evidence_sha256"] = value
            self.write("alpha/report.json", report)
            self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_zip_member_hash_is_checked_even_after_whole_zip_sha_is_updated(self):
        path = self.root / "alpha/evidence.zip"
        manifest, contents = self.zip_parts("alpha")
        contents["serial.log"] = b"changed without manifest update"
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest))
        report = self.read("alpha/report.json")
        report["evidence_sha256"] = digest(path.read_bytes())
        self.write("alpha/report.json", report)
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_duplicate_members_are_rejected(self):
        path = self.root / "alpha/evidence.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("serial.log", b"duplicate")
        report = self.read("alpha/report.json")
        report["evidence_sha256"] = digest(path.read_bytes())
        self.write("alpha/report.json", report)
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_required_frame_and_unit_contract_members_are_checked(self):
        manifest, contents = self.zip_parts("alpha")
        del contents["units/contract.json"]
        self.write_zip("alpha", self.read("alpha/report.json"), manifest, contents)
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_zip_running_session_identity_and_selected_unit_are_checked(self):
        original, contents = self.zip_parts("alpha")
        report = self.read("alpha/report.json")
        for key, value in (("session_id", "another"), ("device_id", "core2"), ("runtime", "qemu-unified"), ("firmware_sha256", "d" * 64), ("state", "stopped")):
            manifest = copy.deepcopy(original)
            manifest["session"][key] = value
            self.write_zip("alpha", report, manifest, contents)
            self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_another_unit_report_does_not_cover_the_selected_id(self):
        self.selection["cases"][0]["guest_controller"]["report"] = "beta/report.json"
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_custom_guest_flavor_and_patch_scope_remain_visible(self):
        report = self.read("alpha/report.json")
        report.update(firmware_flavor="custom-guest-callback-root", ir_callback_patch={"original_sha256": "c" * 64, "patched_sha256": "d" * 64}, limitations=["Does not establish the original published driver path"])
        self.write("alpha/report.json", report)
        checked = self.alpha(self.check())
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual(checked["firmware_flavor"], report["firmware_flavor"])
        self.assertEqual(checked["ir_callback_patch"], report["ir_callback_patch"])
        self.selection["cases"][0]["guest_controller"]["expected_firmware_flavor"] = "official-unmodified"
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_missing_runtime_proof_preserves_functional_pass(self):
        self.selection["cases"][0]["guest_controller"].pop("runtime_proof")
        result = self.alpha(self.check())
        self.assertEqual((result["status"], result["functional_status"]), ("NOT VERIFIED", "PASS"))

    def test_missing_proof_file_is_not_a_controller_failure(self):
        self.selection["cases"][0]["guest_controller"]["runtime_proof"]["path"] = "absent.json"
        result = self.alpha(self.check())
        self.assertEqual((result["status"], result["functional_status"]), ("NOT VERIFIED", "PASS"))

    def test_different_binary_or_pid_is_never_merged_into_full_pass(self):
        for field, value in (("observed_binary_sha256", "c" * 64), ("pid", 777), ("session_id", "another")):
            proof = {"session_id": "alpha-session", "pid": 11, "observed_binary_sha256": BINARY, "status": "PASS"}
            proof[field] = value
            self.write("alpha/runtime.json", proof)
            summary = self.check()
            self.assertEqual(summary["status"], "PARTIAL")
            self.assertEqual(self.alpha(summary)["status"], "NOT VERIFIED")

    def indirect_beta(self):
        service = self.write("proof/service-provenance.json", {"qemu_sha256": BINARY})
        self.write("proof/runtime.json", {"runtime_binary_sha256": BINARY, "service_provenance_sha256": digest(service.read_bytes()), "sessions": [{"unit_id": "beta", "session_id": "beta-session", "worker_id": "worker", "generation": 5}], "direct_executable_observations": ["../alpha/runtime.json"]})
        self.selection["cases"][1]["guest_controller"]["runtime_proof"] = {"kind": "service-generation", "path": "proof/runtime.json"}

    def test_indirect_proof_is_explicit_and_strict_mode_is_partial(self):
        self.indirect_beta()
        normal = self.check()
        self.assertEqual(normal["status"], "PASS")
        self.assertEqual(normal["layers"]["guest_controller"]["direct_pid_units"], 1)
        self.assertEqual(normal["layers"]["guest_controller"]["indirect_service_generation_units"], 1)
        strict = self.check(strict=True)
        self.assertEqual(strict["status"], "PARTIAL")
        beta = strict["cases"][1]["guest_controller"]
        self.assertEqual((beta["status"], beta["functional_status"]), ("NOT VERIFIED", "PASS"))

    def test_indirect_proof_requires_exact_worker_generation_and_anchor(self):
        self.indirect_beta()
        proof = self.read("proof/runtime.json")
        for generation, anchors in ((6, ["../alpha/runtime.json"]), (5, [])):
            proof["sessions"][0]["generation"] = generation
            proof["direct_executable_observations"] = anchors
            self.write("proof/runtime.json", proof)
            self.assertEqual(self.check()["cases"][1]["guest_controller"]["status"], "NOT VERIFIED")

    def test_indirect_service_configuration_hash_must_match(self):
        self.indirect_beta()
        self.write("proof/service-provenance.json", {"qemu_sha256": "c" * 64})
        self.assertEqual(self.check()["cases"][1]["guest_controller"]["status"], "NOT VERIFIED")

    def test_optional_runtime_worker_and_indirect_pid_must_match(self):
        proof = self.read("alpha/runtime.json")
        proof["worker_generation"] = 6
        self.write("alpha/runtime.json", proof)
        self.assertEqual(self.alpha(self.check())["status"], "NOT VERIFIED")
        proof.pop("worker_generation")
        self.write("alpha/runtime.json", proof)
        self.indirect_beta()
        indirect = self.read("proof/runtime.json")
        indirect["sessions"][0]["pid"] = 777
        self.write("proof/runtime.json", indirect)
        self.assertEqual(self.check()["cases"][1]["guest_controller"]["status"], "NOT VERIFIED")

    def test_root_observation_array_and_browser_inline_proof_are_supported(self):
        self.write("alpha/runtime.json", {"observations": [{"session_id": "alpha-session", "pid": 11, "unit_ids": ["alpha"], "runtime": "qemu", "actual_binary_sha256": BINARY, "matches_expected": True}]})
        self.assertEqual(self.check()["status"], "PASS")
        proof = {"session_id": "alpha-session", "observed_pid": 11, "runtime_binary_sha256": BINARY}
        self.write("alpha/runtime.json", {"runtime_provenance": proof})
        self.selection["cases"][0]["guest_controller"]["runtime_proof"]["report_pointer"] = "/runtime_provenance"
        self.assertEqual(self.check()["status"], "PASS")

    def test_verified_browser_pid_does_not_invent_an_unknown_worker_generation(self):
        proof = {"session_id": "alpha-session", "observed_pid": 11, "runtime_binary_sha256": BINARY, "status": "VERIFIED", "worker_generation": None, "worker_id": None, "firmware_sha256": FIRMWARE}
        self.write("alpha/runtime.json", proof)
        checked = self.alpha(self.check())
        self.assertEqual(checked["status"], "PASS")
        self.assertIsNone(checked["runtime_proof"]["worker_generation_observed"])
        proof["firmware_sha256"] = "c" * 64
        self.write("alpha/runtime.json", proof)
        self.assertEqual(self.alpha(self.check())["status"], "NOT VERIFIED")

    def test_live_browser_is_a_separate_layer_with_same_zip_binding(self):
        report = self.read("alpha/report.json")
        report["category"] = "virtual-device-browser-integration"
        self.write("alpha/report.json", report)
        self.selection["cases"][0]["live_browser"] = copy.deepcopy(self.selection["cases"][0]["guest_controller"])
        self.assertEqual(self.alpha(self.check(), "live_browser")["status"], "PASS")
        self.assertEqual(self.check()["layers"]["live_browser"]["counts"]["PASS"], 1)

    def detailed_browser_alpha(self):
        report = self.read("alpha/report.json")
        report.update(category="virtual-device-browser-integration", browser_report="browser.json")
        unit = {"instance": "external1", "readback": {"id": "external1", "unit_id": "alpha", "available": True, "source": "guest-qom"}, "dom_matches_product_readback": True, "readback_matches_real_http_response": True}
        detail = {"session_id": "alpha-session", "device_id": "cores3", "firmware_sha256": FIRMWARE, "runtime": "qemu", "attachments": [{"id": "external1", "unit_id": "alpha"}], "errors": [], "readbacks": [{"real_http": True}], "snapshots": [{"phase": "before-evidence", "session_state": "running", "units": [unit], "screenshot": "before.png"}]}
        (self.root / "alpha/before.png").write_bytes(PNG)
        self.selection["cases"][0]["live_browser"] = copy.deepcopy(self.selection["cases"][0]["guest_controller"])
        self.save_browser_alpha(report, detail)
        return report, detail

    def save_browser_alpha(self, report, detail):
        path = self.write("alpha/browser.json", detail)
        report["artifact_sha256"] = {"browser.json": digest(path.read_bytes()), "before.png": digest((self.root / "alpha/before.png").read_bytes())}
        self.write("alpha/report.json", report)

    def test_browser_detail_binds_exact_instances_http_and_screenshot(self):
        self.detailed_browser_alpha()
        result = self.alpha(self.check(), "live_browser")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["browser_detail"]["instances"], ["external1"])
        self.assertEqual(result["browser_detail"]["snapshots"], 1)
        self.assertTrue(result["browser_detail"]["screenshot_sha256"])
        self.assertEqual(list(result["browser_detail"]["screenshot_dimensions"].values()), [{"width": 1, "height": 1}])
        self.assertEqual(self.check()["cases"][0]["same_session_cohort"]["status"], "PASS")

    def test_browser_screenshot_must_be_committed_by_outer_report(self):
        report, _ = self.detailed_browser_alpha()
        del report["artifact_sha256"]["before.png"]
        self.write("alpha/report.json", report)
        # A selection-side hash cannot substitute for the report's commitment.
        self.selection["cases"][0]["live_browser"]["artifacts"] = {"alpha/before.png": digest(PNG)}
        result = self.alpha(self.check(), "live_browser")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("outer artifact_sha256", result["reason"])

    def test_browser_screenshot_replacement_does_not_reuse_committed_hash(self):
        self.detailed_browser_alpha()
        (self.root / "alpha/before.png").write_bytes(PNG + b"replaced")
        result = self.alpha(self.check(), "live_browser")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("artifact SHA256 differs", result["reason"])

    def test_browser_header_truncation_and_invalid_crc_fail_even_with_updated_hash(self):
        report, detail = self.detailed_browser_alpha()
        corrupt_crc = bytearray(PNG)
        corrupt_crc[29] ^= 1
        for pixels in (b"", PNG[:8], PNG[:-16], bytes(corrupt_crc)):
            with self.subTest(bytes=len(pixels)):
                (self.root / "alpha/before.png").write_bytes(pixels)
                self.save_browser_alpha(report, detail)
                result = self.alpha(self.check(), "live_browser")
                self.assertEqual(result["status"], "FAIL")
                self.assertIn("PNG evidence", result["reason"])

    def test_zip_framebuffer_must_decode_after_all_hashes_are_refreshed(self):
        manifest, contents = self.zip_parts("alpha")
        contents["frames/current.png"] = PNG[:24]
        self.write_zip("alpha", self.read("alpha/report.json"), manifest, contents)
        result = self.alpha(self.check())
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("PNG evidence", result["reason"])

    def test_guest_and_detailed_browser_cannot_merge_different_sessions_firmware_or_zip(self):
        original_report, original_detail = self.detailed_browser_alpha()
        original_manifest, original_contents = self.zip_parts("alpha")
        for field in ("session_id", "firmware_sha256", "evidence_sha256"):
            with self.subTest(field=field):
                report, detail = copy.deepcopy(original_report), copy.deepcopy(original_detail)
                manifest, contents = copy.deepcopy(original_manifest), dict(original_contents)
                if field == "evidence_sha256":
                    contents["serial.log"] = b"ANOTHER VALID EXECUTION ARTIFACT\n"
                else:
                    value = "another-session" if field == "session_id" else "c" * 64
                    report[field] = detail[field] = manifest["session"][field] = value
                browser_path = self.write("other-browser/browser.json", detail)
                (browser_path.parent / "before.png").write_bytes(PNG)
                report["artifact_sha256"] = {"browser.json": digest(browser_path.read_bytes()), "before.png": digest(PNG)}
                self.write_zip("other-browser", report, manifest, contents)
                self.write("other-browser/runtime.json", {"session_id": report["session_id"], "pid": 11, "observed_binary_sha256": BINARY, "firmware_sha256": report["firmware_sha256"]})
                self.selection["cases"][0]["live_browser"] = {"report": "other-browser/report.json", "runtime_proof": {"kind": "direct-pid", "path": "other-browser/runtime.json"}}
                checked = self.check(strict=True)
                row = checked["cases"][0]
                self.assertEqual(row["guest_controller"]["status"], "PASS")
                self.assertEqual(row["live_browser"]["functional_status"], "PASS")
                self.assertEqual(row["live_browser"]["status"], "FAIL")
                self.assertEqual(row["live_browser"]["browser_detail"]["status"], "PASS")
                self.assertIn(field, row["same_session_cohort"]["mismatched_fields"])
                self.assertEqual(checked["status"], "FAIL")

    def test_same_session_cohort_requires_both_runtime_proofs_to_verify_expected_binary(self):
        self.detailed_browser_alpha()
        proof = self.write("alpha/other-runtime.json", {"session_id": "alpha-session", "pid": 11, "observed_binary_sha256": "c" * 64})
        self.selection["cases"][0]["live_browser"]["runtime_proof"]["path"] = str(proof.relative_to(self.root))
        checked = self.check(strict=True)["cases"][0]
        self.assertEqual(checked["guest_controller"]["status"], "PASS")
        self.assertEqual(checked["live_browser"]["status"], "NOT VERIFIED")
        self.assertEqual(checked["same_session_cohort"]["status"], "NOT VERIFIED")

    def test_browser_wrapper_guest_layer_uses_committed_controller_assertions(self):
        report = self.read("alpha/report.json")
        controller = copy.deepcopy(report)
        controller["checks"] = {"controller_one": True, "controller_two": True, "controller_three": True}
        path = self.write("alpha/controller.json", controller)
        report.update(category="virtual-device-browser-integration", controller_result="controller.json", artifact_sha256={"controller.json": digest(path.read_bytes())})
        self.write("alpha/report.json", report)
        checked = self.alpha(self.check())
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual(checked["assertions"], 3)
        self.assertEqual(checked["wrapper_assertions"], 2)
        for fault in ("uncommitted", "failed-assertion", "another-session"):
            with self.subTest(fault=fault):
                candidate = copy.deepcopy(controller)
                if fault == "failed-assertion": candidate["checks"]["controller_one"] = False
                elif fault == "another-session": candidate["session_id"] = "different"
                path = self.write("alpha/controller.json", candidate)
                report["artifact_sha256"] = {} if fault == "uncommitted" else {"controller.json": digest(path.read_bytes())}
                self.write("alpha/report.json", report)
                self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_browser_snapshot_empty_or_duplicate_sets_cannot_pass_vacuously(self):
        report, original = self.detailed_browser_alpha()
        for kind in ("empty-attachments", "empty-snapshots", "empty-units", "duplicate-units", "wrong-instance", "no-http", "failed-dom", "wrong-firmware"):
            detail = copy.deepcopy(original)
            if kind == "empty-attachments": detail["attachments"] = []
            elif kind == "empty-snapshots": detail["snapshots"] = []
            elif kind == "empty-units": detail["snapshots"][0]["units"] = []
            elif kind == "duplicate-units": detail["snapshots"][0]["units"] *= 2
            elif kind == "wrong-instance": detail["snapshots"][0]["units"][0]["instance"] = "other"
            elif kind == "no-http": detail["readbacks"] = []
            elif kind == "failed-dom": detail["snapshots"][0]["units"][0]["dom_matches_product_readback"] = False
            elif kind == "wrong-firmware": detail["firmware_sha256"] = "c" * 64
            self.save_browser_alpha(report, detail)
            with self.subTest(kind=kind):
                self.assertEqual(self.alpha(self.check(), "live_browser")["status"], "FAIL")

    def test_linked_browser_detail_must_have_a_committed_hash(self):
        report, _ = self.detailed_browser_alpha()
        report.pop("artifact_sha256")
        self.write("alpha/report.json", report)
        self.assertEqual(self.alpha(self.check(), "live_browser")["status"], "FAIL")

    def test_bridge_contract_does_not_create_a_guest_or_live_browser_pass(self):
        self.write("bridge.json", {"category": "browser-bridge-contract", "status": "PASS", "checks": ["all-form-fields"], "unit_ids": ["alpha", "beta"], "firmware_execution": "NOT RUN"})
        self.selection["cases"][0] = {"unit_id": "alpha", "bridge_contract": {"report": "bridge.json"}}
        result = self.check()
        self.assertEqual(self.alpha(result, "bridge_contract")["status"], "PASS")
        self.assertEqual(self.alpha(result)["status"], "NOT RUN")
        self.assertEqual(self.alpha(result, "live_browser")["status"], "NOT RUN")

    def test_associated_artifact_and_selected_report_hash_are_checked(self):
        artifact = self.write("alpha/extra.json", {"snapshot": True})
        report = self.read("alpha/report.json")
        report["artifact_sha256"] = {"extra.json": digest(artifact.read_bytes())}
        self.write("alpha/report.json", report)
        self.assertEqual(self.check()["status"], "PASS")
        self.write("alpha/extra.json", {"snapshot": False})
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_paths_cannot_escape_root_or_accept_local_absolute_names(self):
        for name in ("../outside.json", "/tmp/private.json"):
            self.selection["cases"][0]["guest_controller"]["report"] = name
            result = self.alpha(self.check())
            self.assertEqual(result["status"], "FAIL")
            self.assertNotIn(name, result["reason"])

    def test_legacy_runtime_requires_explicit_identity_bound_context(self):
        report = self.read("alpha/report.json")
        report.pop("runtime")
        self.write("alpha/report.json", report)
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")
        context = {"status": "PASS", "device_id": "cores3", "runtime": "qemu", "cases": [{"unit_id": "alpha", "status": "PASS", **{key: report[key] for key in ("session_id", "firmware_sha256", "evidence_sha256")}}]}
        self.write("context.json", context)
        self.selection["cases"][0]["guest_controller"]["context_report"] = "context.json"
        checked = self.alpha(self.check())
        self.assertEqual(checked["status"], "PASS")
        self.assertEqual(checked["fields_from_selected_context"], ["runtime"])
        context["cases"][0]["session_id"] = "another"
        self.write("context.json", context)
        self.assertEqual(self.alpha(self.check())["status"], "FAIL")

    def test_file_bytes_are_frozen_once_for_hash_and_parsing(self):
        checker = Checker(self.root)
        path = checker.path("alpha/report.json")
        original = checker.read(path)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("second file read")):
            self.assertEqual(checker.json(path), json.loads(original))

    def test_write_cannot_overwrite_selected_input_evidence(self):
        selection = self.write("selection.json", self.selection)
        report = self.root / "alpha/report.json"
        before = report.read_bytes()
        argv = ["checker", "--root", str(self.root), "--selection", str(selection), "--write", str(report)]
        with patch("sys.argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(report.read_bytes(), before)

    def test_write_protects_missing_proof_skipped_after_a_failed_report(self):
        report = self.read("alpha/report.json")
        report["status"] = "FAIL"
        self.write("alpha/report.json", report)
        pending = self.root / "pending/runtime.json"
        self.selection["cases"][0]["guest_controller"]["runtime_proof"]["path"] = "pending/runtime.json"
        selection = self.write("selection.json", self.selection)
        argv = ["checker", "--root", str(self.root), "--selection", str(selection), "--write", str(pending)]
        with patch("sys.argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main()
        self.assertFalse(pending.exists())

    def test_write_refuses_an_unrelated_existing_file(self):
        selection = self.write("selection.json", self.selection)
        unrelated = self.write("unrelated.json", {"keep": "unrelated user content"})
        before = unrelated.read_bytes()
        argv = ["checker", "--root", str(self.root), "--selection", str(selection), "--write", str(unrelated)]
        with patch("sys.argv", argv), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main()
        self.assertEqual(unrelated.read_bytes(), before)

    def test_write_can_atomically_refresh_its_own_summary(self):
        selection = self.write("selection.json", self.selection)
        output = self.write("summary.json", self.check())
        argv = ["checker", "--root", str(self.root), "--selection", str(selection), "--write", str(output)]
        with patch("sys.argv", argv), redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        self.assertEqual(self.read("summary.json")["status"], "PASS")
        self.assertEqual(list(self.root.glob(".unit-batch-summary-*")), [])

    def test_interrupted_atomic_write_keeps_the_previous_summary(self):
        selection = self.write("selection.json", self.selection)
        output = self.write("summary.json", self.check())
        before = output.read_bytes()
        argv = ["checker", "--root", str(self.root), "--selection", str(selection), "--write", str(output)]
        with patch("sys.argv", argv), patch("check_batch_evidence.os.replace", side_effect=OSError("interrupted write")), redirect_stdout(io.StringIO()), self.assertRaises(OSError):
            main()
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".unit-batch-summary-*")), [])


if __name__ == "__main__":
    unittest.main()
