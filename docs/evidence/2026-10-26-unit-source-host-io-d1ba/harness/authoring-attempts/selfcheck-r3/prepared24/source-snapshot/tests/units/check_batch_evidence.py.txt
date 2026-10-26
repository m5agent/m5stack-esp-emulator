#!/usr/bin/env python3
"""Read-only, explicit-selection Unit evidence reconciliation.

No API requests, firmware execution, implicit report discovery or attempt
selection. --write saves the same JSON summary printed on stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CHECKER_BYTES = Path(__file__).read_bytes()
GENERATOR = "unit-batch-evidence-checker"
LAYERS = ("guest_controller", "live_browser", "bridge_contract")
REQUIRED_ZIP = {
    "manifest.json", "serial.log", "frames/current.png", "qom/snapshot.json",
    "units/contract.json", "units/runtime.json", "units/state.json",
}


class EvidenceError(ValueError):
    pass


class MissingEvidence(EvidenceError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def sha256_value(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class Checker:
    def __init__(self, root=ROOT, *, strict_direct=False):
        self.root = Path(root).resolve()
        self.strict_direct = strict_direct
        self.read_cache = {}
        self.input_paths = set()

    def path(self, name, *, relative_to=None):
        require(isinstance(name, str) and bool(name), "evidence path must be a nonempty repository-relative string")
        path = ((relative_to or self.root) / name).resolve()
        self.input_paths.add(path)
        require(not Path(name).is_absolute(), "absolute evidence paths are not accepted")
        require(path.is_relative_to(self.root), "evidence path escapes the repository")
        return path

    def label(self, path):
        return path.relative_to(self.root).as_posix()

    def read(self, path):
        self.input_paths.add(path.resolve())
        if path in self.read_cache:
            return self.read_cache[path]
        if not path.is_file():
            raise MissingEvidence("missing evidence file: " + self.label(path))
        self.read_cache[path] = path.read_bytes()
        return self.read_cache[path]

    def register_selection_paths(self, selection):
        """Protect even missing inputs and proofs skipped after an earlier failure."""
        def remember(name, relative_to=None):
            try:
                return self.path(name, relative_to=relative_to)
            except (EvidenceError, OSError, TypeError, ValueError):
                return None
        if not isinstance(selection, dict) or not isinstance(selection.get("cases"), list):
            return
        for row in selection["cases"]:
            if not isinstance(row, dict):
                continue
            for layer in LAYERS:
                spec = row.get(layer)
                if not isinstance(spec, dict):
                    continue
                report = remember(spec.get("report"))
                if report:
                    self.input_paths.add(report.parent / "evidence.zip")
                for key in ("evidence", "context_report"):
                    if key in spec:
                        remember(spec[key])
                if isinstance(spec.get("artifacts"), dict):
                    for name in spec["artifacts"]:
                        remember(name)
                proof = spec.get("runtime_proof")
                if isinstance(proof, dict):
                    path = remember(proof.get("path"))
                    if path:
                        remember(proof.get("service_provenance", "service-provenance.json"), path.parent)
                        remember(proof.get("source_replay", "source-replay.json"), path.parent)
                        if isinstance(proof.get("anchors"), list):
                            for name in proof["anchors"]:
                                remember(name, path.parent)

    def json(self, path):
        try:
            value = json.loads(self.read(path).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise EvidenceError("invalid UTF-8 JSON: " + self.label(path)) from error
        require(isinstance(value, dict), "JSON evidence must be an object: " + self.label(path))
        return value

    def pointer(self, report, pointer):
        if pointer is None:
            return report
        require(isinstance(pointer, str) and pointer.startswith("/"), "report_pointer must be a JSON Pointer")
        try:
            for part in pointer[1:].split("/"):
                key = part.replace("~1", "/").replace("~0", "~")
                report = report[int(key)] if isinstance(report, list) else report[key]
        except (KeyError, IndexError, ValueError, TypeError) as error:
            raise EvidenceError("report_pointer does not select a report") from error
        require(isinstance(report, dict), "report_pointer must select an object")
        return report

    def assertions(self, report, *, bridge=False):
        require(report.get("status") == "PASS", "selected report is not PASS")
        checks = report.get("checks")
        if bridge and isinstance(checks, list):
            require(bool(checks) and all(isinstance(x, str) and x for x in checks), "bridge checks must be nonempty named assertions")
            require(len(checks) == len(set(checks)), "bridge assertions contain duplicate names")
            return checks
        require(isinstance(checks, dict) and bool(checks), "selected report has no assertion results")
        require(all(isinstance(k, str) and k and v is True for k, v in checks.items()), "selected report has a failed or non-boolean assertion")
        return list(checks)

    def artifacts(self, report, spec, report_path):
        verified = {}
        for mapping, relative_to in ((report.get("artifact_sha256", {}), report_path.parent), (spec.get("artifacts", {}), self.root)):
            require(isinstance(mapping, dict), "artifact_sha256/artifacts must be path-to-SHA256 mappings")
            for name, expected in mapping.items():
                require(sha256_value(expected), "invalid artifact SHA256")
                path = self.path(name, relative_to=relative_to)
                require(digest(self.read(path)) == expected, "associated artifact SHA256 differs: " + self.label(path))
                verified[self.label(path)] = expected
        return verified

    def png(self, raw, label):
        """Decode bounded pixels as well as checking PNG chunks and CRCs."""
        require(0 < len(raw) <= 32 << 20, "PNG evidence is empty or too large: " + label)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                require(image.format == "PNG", "evidence image is not a PNG: " + label)
                width, height = image.size
                require(width > 0 and height > 0 and width * height <= 16 << 20, "PNG evidence has unsupported dimensions: " + label)
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
            if isinstance(error, EvidenceError):
                raise
            raise EvidenceError("PNG evidence cannot be decoded: " + label) from error
        return {"width": width, "height": height}

    def zip_manifest(self, path, report, unit_id):
        raw = self.read(path)
        require(sha256_value(report.get("evidence_sha256")), "report lacks the evidence ZIP SHA256")
        require(digest(raw) == report["evidence_sha256"], "evidence ZIP SHA256 differs from the report")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                require(len(names) == len(set(names)), "evidence ZIP contains duplicate member names")
                require(len(names) <= 512 and sum(e.file_size for e in entries) <= 128 << 20, "evidence ZIP exceeds validation bounds")
                for entry in entries:
                    name = PurePosixPath(entry.filename)
                    require(not name.is_absolute() and ".." not in name.parts and "\\" not in entry.filename, "evidence ZIP contains an unsafe member name")
                    require(not entry.is_dir() and entry.file_size <= 32 << 20, "unsupported ZIP member or member size")
                    require((entry.external_attr >> 16) & 0o170000 != 0o120000, "evidence ZIP contains a symbolic link")
                require(REQUIRED_ZIP <= set(names), "evidence ZIP lacks serial/frame/QOM/Unit contracts")
                require(archive.testzip() is None, "evidence ZIP has a corrupt member")
                manifest = json.loads(archive.read("manifest.json"))
                require(isinstance(manifest, dict) and isinstance(manifest.get("files"), dict), "ZIP manifest has no file index")
                require(set(manifest["files"]) == set(names) - {"manifest.json"}, "ZIP manifest and member index differ")
                for name, record in manifest["files"].items():
                    require(isinstance(record, dict), "invalid ZIP member hash record")
                    content = archive.read(name)
                    require(type(record.get("size")) is int and len(content) == record["size"] and digest(content) == record.get("sha256"), "ZIP member hash/size differs: " + name)
                session = manifest.get("session")
                require(isinstance(session, dict) and session.get("state") == "running", "evidence was not captured from a running guest")
                for name in ("session_id", "device_id", "firmware_sha256", "runtime"):
                    require(isinstance(report.get(name), str) and bool(report[name]) and report[name] == session.get(name), "report and ZIP session differ: " + name)
                require(sha256_value(report["firmware_sha256"]), "invalid firmware SHA256")
                units = manifest.get("units", {}).get("units", [])
                require(isinstance(units, list) and any(u.get("unit_id") == unit_id and u.get("available") is True for u in units if isinstance(u, dict)), "ZIP lacks the selected available Unit")
                if isinstance(report.get("attachments"), list):
                    expected = {u["id"]: u["unit_id"] for u in report["attachments"]}
                    require({u.get("id"): u.get("unit_id") for u in units} == expected, "ZIP attachment tree differs from the report")
                self.png(archive.read("frames/current.png"), "ZIP frames/current.png")
                return manifest, len(names)
        except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError, OSError) as error:
            raise EvidenceError("invalid evidence ZIP structure") from error

    def direct_record(self, proof, session, unit_id, expected):
        candidates = proof.get("observations")
        if candidates is None and isinstance(proof.get("observed"), dict):
            candidates = list(proof["observed"].values())
        if candidates is None:
            candidates = [proof]
        require(isinstance(candidates, list), "runtime observations must be a list")
        for item in candidates:
            if not isinstance(item, dict) or item.get("session_id") != session["session_id"]:
                continue
            pid = item.get("pid", item.get("observed_pid"))
            require(type(pid) is int and pid > 0 and pid == session.get("pid"), "runtime proof PID differs from the running ZIP session")
            actual = item.get("observed_binary_sha256", item.get("actual_binary_sha256", item.get("runtime_binary_sha256")))
            require(sha256_value(actual) and actual == expected, "runtime proof has another or missing executable SHA256")
            require(item.get("status", "PASS") in {"PASS", "VERIFIED"} and item.get("matches_expected", True) is True and item.get("executable_matches_frozen_copy", True) is True, "runtime observation did not verify its executable")
            require(not item.get("unit_ids") or unit_id in item["unit_ids"], "runtime observation belongs to another Unit")
            require(not item.get("runtime") or item["runtime"] == session["runtime"], "runtime observation belongs to another runtime")
            worker = session.get("worker", {})
            if isinstance(item.get("worker"), dict):
                require(all(item["worker"].get(key) == worker.get(key) for key in ("worker_id", "generation")), "runtime observation has another worker generation")
            if item.get("worker_generation") is not None:
                require(type(item["worker_generation"]) is int and item["worker_generation"] == worker.get("generation"), "runtime observation has another worker generation")
            if item.get("worker_id") is not None:
                require(item["worker_id"] == worker.get("worker_id"), "runtime observation has another worker")
            if item.get("firmware_sha256") is not None:
                require(item["firmware_sha256"] == session["firmware_sha256"], "runtime observation has another firmware")
            observed_generation = item["worker"].get("generation") if isinstance(item.get("worker"), dict) else item.get("worker_generation")
            return {"proof_kind": "direct-pid", "binary_sha256": actual, "direct_pid_observed": True, "pid": pid, "worker_generation_observed": observed_generation}
        raise EvidenceError("runtime proof has no observation for this session")

    def browser_detail(self, report, report_path, verified_artifacts, manifest):
        if "browser_report" not in report:
            return {"status": "LEGACY INLINE", "scope": "Uses the selected legacy report's embedded browser assertions; no separate detailed snapshot artifact is declared."}
        path = self.path(report["browser_report"], relative_to=report_path.parent)
        require(self.label(path) in verified_artifacts, "detailed browser report is not committed by artifact_sha256")
        detail = self.json(path)
        require(all(detail.get(key) == report.get(key) for key in ("session_id", "device_id", "firmware_sha256", "runtime")), "detailed browser report has another session/device/firmware/runtime")
        require(detail.get("errors") == [], "detailed browser report contains errors or lacks an error result")
        attachments = detail.get("attachments")
        require(isinstance(attachments, list) and bool(attachments) and all(isinstance(unit, dict) for unit in attachments), "browser attachments are empty or invalid")
        expected = {unit.get("id"): unit.get("unit_id") for unit in attachments}
        require(len(expected) == len(attachments) and all(isinstance(key, str) and key for key in expected), "browser attachment IDs are empty or duplicated")
        require(expected == {unit.get("id"): unit.get("unit_id") for unit in manifest["units"]["units"]}, "browser attachments differ from the running ZIP session")
        snapshots = detail.get("snapshots")
        require(isinstance(snapshots, list) and bool(snapshots), "detailed browser report has no snapshots")
        require(isinstance(detail.get("readbacks"), list) and bool(detail["readbacks"]), "detailed browser report has no actual HTTP readbacks")
        screenshots = {}
        screenshot_dimensions = {}
        outer_artifacts = {
            self.label(self.path(name, relative_to=report_path.parent))
            for name in report.get("artifact_sha256", {})
        }
        for snapshot in snapshots:
            require(isinstance(snapshot, dict) and isinstance(snapshot.get("units"), list), "invalid browser snapshot")
            units = snapshot["units"]
            require(bool(units) and all(isinstance(unit, dict) for unit in units), "browser snapshot has an empty Unit set")
            ids = [unit.get("instance") for unit in units]
            require(len(ids) == len(set(ids)) and set(ids) == set(expected), "browser snapshot Unit IDs are missing or duplicated")
            for unit in units:
                readback = unit.get("readback", {})
                require(isinstance(readback, dict) and readback.get("id") == unit["instance"] and readback.get("unit_id") == expected[unit["instance"]], "browser snapshot has another Unit readback")
                require(readback.get("available") is True and readback.get("source") == "guest-qom", "browser snapshot is not backed by an available guest QOM Unit")
                require(unit.get("dom_matches_product_readback") is True and unit.get("readback_matches_real_http_response") is True, "browser snapshot DOM/HTTP comparison did not pass")
            if snapshot.get("phase") == "before-evidence":
                require(snapshot.get("session_state") == "running", "browser evidence screenshot was not taken from the running session")
                screenshot = self.path(snapshot.get("screenshot"), relative_to=path.parent)
                label = self.label(screenshot)
                require(label in outer_artifacts and label in verified_artifacts, "browser screenshot is not committed by the outer artifact_sha256")
                pixels = self.read(screenshot)
                screenshot_dimensions[label] = self.png(pixels, label)
                screenshots[label] = digest(pixels)
        require(bool(screenshots), "browser report has no screenshot before evidence capture")
        return {"status": "PASS", "report": self.label(path), "snapshots": len(snapshots), "instances": sorted(expected), "screenshot_sha256": screenshots, "screenshot_dimensions": screenshot_dimensions}

    def controller_detail(self, report, report_path, verified_artifacts):
        """A browser wrapper cannot replace its underlying guest assertions."""
        path = self.path(report["controller_result"], relative_to=report_path.parent)
        require(self.label(path) in verified_artifacts, "controller result is not committed by artifact_sha256")
        controller = self.json(path)
        checks = self.assertions(controller)
        for key in ("unit_id", "session_id", "firmware_sha256", "evidence_sha256"):
            require(controller.get(key) and controller[key] == report.get(key), "controller result and browser wrapper differ: " + key)
        for key in ("device_id", "runtime", "firmware_flavor"):
            if key in controller:
                require(controller[key] == report.get(key), "controller result and browser wrapper differ: " + key)
        return {"status": "PASS", "report": self.label(path), "report_sha256": digest(self.read(path)), "assertions": len(checks)}

    def cohort_identity(self, guest, browser, expected_binary):
        """Independent passing layers must identify the same executed guest."""
        if guest.get("functional_status") != "PASS" or browser.get("functional_status") != "PASS":
            return {"status": "NOT VERIFIED", "reason": "both guest and live-browser functional evidence are required"}
        fields = ("session_id", "device_id", "runtime", "firmware_sha256", "evidence_sha256")
        mismatches = [key for key in fields if not guest.get(key) or guest[key] != browser.get(key)]
        if mismatches:
            reason = "selected guest and live-browser reports have different same-session identity: " + ", ".join(mismatches)
            browser.update(status="FAIL", reason=reason)
            return {"status": "FAIL", "reason": reason, "mismatched_fields": mismatches}
        proofs = [layer.get("runtime_proof", {}) for layer in (guest, browser)]
        verified = all(proof.get("status") == "PASS" and proof.get("binary_sha256") == expected_binary for proof in proofs)
        return {"status": "PASS" if verified else "NOT VERIFIED", **{key: guest[key] for key in fields}, "runtime_binary_sha256": expected_binary, "direct_pid_observed": all(proof.get("direct_pid_observed") is True for proof in proofs)}

    def runtime_proof(self, spec, manifest, unit_id, expected):
        if spec is None:
            return {"status": "NOT VERIFIED", "proof_kind": None, "reason": "no runtime proof selected"}
        kind = spec.get("kind") if isinstance(spec, dict) else None
        path = None
        try:
            require(isinstance(spec, dict), "runtime_proof must be an object")
            path = self.path(spec.get("path"))
            proof = self.pointer(self.json(path), spec.get("report_pointer"))
            session = manifest["session"]
            if kind == "direct-pid":
                result = self.direct_record(proof, session, unit_id, expected)
            elif kind == "service-generation":
                require(proof.get("runtime_binary_sha256") == expected, "service-generation proof declares another binary")
                matches = [row for row in proof.get("sessions", []) if isinstance(row, dict) and row.get("session_id") == session["session_id"]]
                require(len(matches) == 1, "service-generation proof must bind exactly this session")
                row = matches[0]
                worker = session.get("worker", {})
                require(isinstance(worker, dict) and worker.get("lease_active") is True and isinstance(worker.get("worker_id"), str) and type(worker.get("generation")) is int, "ZIP lacks an active worker generation")
                require(row.get("worker_id") == worker["worker_id"] and row.get("generation") == worker["generation"], "runtime proof worker/generation differs from ZIP")
                require(type(row.get("generation")) is int, "runtime proof generation must be an integer")
                if "pid" in row:
                    require(type(row["pid"]) is int and row["pid"] == session.get("pid"), "service-generation proof records another PID")
                require(row.get("unit_id") in {unit_id, unit_id + "-browser"}, "service-generation proof belongs to another Unit")
                service = self.path(spec.get("service_provenance", "service-provenance.json"), relative_to=path.parent)
                service_bytes = self.read(service)
                require(digest(service_bytes) == proof.get("service_provenance_sha256"), "service provenance SHA256 differs")
                require(json.loads(service_bytes).get("qemu_sha256") == expected, "service provenance declares another runtime binary")
                if proof.get("source_replay_sha256"):
                    replay = self.path(spec.get("source_replay", "source-replay.json"), relative_to=path.parent)
                    require(digest(self.read(replay)) == proof["source_replay_sha256"], "source replay SHA256 differs")
                anchors = spec.get("anchors", proof.get("direct_executable_observations", []))
                require(isinstance(anchors, list) and bool(anchors), "indirect proof needs direct executable anchors")
                anchor_ids = []
                for name in anchors:
                    anchor = self.path(name, relative_to=path.parent)
                    anchor_proof = self.json(anchor)
                    report_path = anchor.parent / "report.json"
                    if not report_path.is_file():
                        report_path = anchor.parent / "result.json"
                    anchor_report = self.json(report_path)
                    self.assertions(anchor_report)
                    anchor_unit = anchor_report.get("unit_id")
                    anchor_manifest, _ = self.zip_manifest(anchor.parent / "evidence.zip", anchor_report, anchor_unit)
                    anchor_worker = anchor_manifest["session"].get("worker", {})
                    require(anchor_worker.get("worker_id") == worker["worker_id"] and anchor_worker.get("generation") == worker["generation"], "direct anchor has another service generation")
                    self.direct_record(anchor_proof, anchor_manifest["session"], anchor_unit, expected)
                    anchor_ids.append(anchor_report["session_id"])
                result = {"proof_kind": "service-generation", "binary_sha256": expected, "direct_pid_observed": False, "worker_generation": worker["generation"], "anchor_sessions": anchor_ids}
                if self.strict_direct:
                    return {**result, "status": "NOT VERIFIED", "reason": "strict-direct policy rejects indirect service-generation evidence"}
            else:
                raise EvidenceError("unsupported runtime proof kind")
            return {**result, "status": "PASS", "report": self.label(path)}
        except (EvidenceError, OSError, KeyError, TypeError, ValueError) as error:
            return {"status": "NOT VERIFIED", "proof_kind": kind, "report": self.label(path) if path else None, "reason": str(error) if isinstance(error, EvidenceError) else "invalid runtime proof structure"}

    def layer(self, unit_id, layer, spec, selection, catalog_path, catalog_ids):
        if spec is None:
            return {"status": "NOT RUN", "functional_status": "NOT RUN", "reason": "no report explicitly selected"}
        result = {"status": "FAIL", "functional_status": "FAIL"}
        try:
            require(isinstance(spec, dict), "layer selection must be an object or null")
            report_path = self.path(spec.get("report"))
            result["report"] = self.label(report_path)
            report = self.pointer(self.json(report_path), spec.get("report_pointer"))
            result["report_sha256"] = digest(self.read(report_path))
            if "report_sha256" in spec:
                require(spec["report_sha256"] == result["report_sha256"], "selected report SHA256 differs")
            result["artifact_sha256_verified"] = self.artifacts(report, spec, report_path)
            if "context_report" in spec:
                context_path = self.path(spec["context_report"])
                context = self.json(context_path)
                require(context.get("status") == "PASS" and isinstance(context.get("cases"), list), "selected context report is not a passing case summary")
                matching = [case for case in context["cases"] if isinstance(case, dict) and case.get("unit_id") == unit_id]
                require(len(matching) == 1 and matching[0].get("status") == "PASS", "selected context does not identify one passing Unit case")
                require(all(matching[0].get(key) == report.get(key) and report.get(key) for key in ("session_id", "firmware_sha256", "evidence_sha256")), "selected context has another session/firmware/evidence")
                report = dict(report)
                missing = [key for key in ("device_id", "runtime") if key not in report]
                for key in missing:
                    require(isinstance(context.get(key), str) and bool(context[key]), "selected context lacks runtime/device metadata")
                    report[key] = context[key]
                result.update(context_report=self.label(context_path), context_report_sha256=digest(self.read(context_path)), fields_from_selected_context=missing)
            checks = self.assertions(report, bridge=layer == "bridge_contract")
            result["assertions"] = len(checks)
            result["firmware_flavor"] = report.get("firmware_flavor", "not-recorded")
            for key in ("ir_callback_patch", "guest_modifications", "limitations", "visual_scope", "hardware_execution"):
                if key in report:
                    result[key] = report[key]
            if "expected_firmware_flavor" in spec:
                require(result["firmware_flavor"] == spec["expected_firmware_flavor"], "selected report has another firmware flavor")
            if layer == "bridge_contract":
                require(report.get("category") == "browser-bridge-contract", "selected bridge report has another validation category")
                require(report.get("firmware_execution") == "NOT RUN", "bridge contract must identify its non-runtime scope")
                ids = report.get("unit_ids")
                if ids is not None:
                    require(isinstance(ids, list) and unit_id in ids, "bridge report does not cover this Unit")
                else:
                    require("all-27-schema-forms" in checks and len(catalog_ids) == 27, "bridge report does not explicitly enumerate its Unit scope")
                    sources = report.get("source_sha256", {})
                    require(sources.get(self.label(catalog_path)) == digest(self.read(catalog_path)), "all-catalog bridge source SHA256 differs")
                result.update(status="PASS", functional_status="PASS", proof_kind="browser-contract-only", firmware_execution="NOT RUN")
                return result
            require(report.get("unit_id") == unit_id, "selected report belongs to another Unit")
            if layer == "live_browser":
                require(report.get("category", "").startswith("virtual-device-browser"), "selected live-browser report has another validation category")
            require(report.get("device_id") == selection["device_id"] and report.get("runtime") == selection["runtime"], "selected report has another device/runtime")
            zip_path = self.path(spec["evidence"]) if "evidence" in spec else report_path.parent / "evidence.zip"
            manifest, count = self.zip_manifest(zip_path, report, unit_id)
            if layer == "live_browser":
                result["browser_detail"] = self.browser_detail(report, report_path, result["artifact_sha256_verified"], manifest)
            elif layer == "guest_controller" and "controller_result" in report:
                detail = self.controller_detail(report, report_path, result["artifact_sha256_verified"])
                result.update(controller_detail=detail, wrapper_assertions=result["assertions"], assertions=detail["assertions"])
            result.update(functional_status="PASS", session_id=report["session_id"], device_id=report["device_id"], runtime=report["runtime"], firmware_sha256=report["firmware_sha256"], evidence=self.label(zip_path), evidence_sha256=report["evidence_sha256"], zip_members=count)
            runtime = self.runtime_proof(spec.get("runtime_proof"), manifest, unit_id, selection["expected_runtime_binary_sha256"])
            result.update(status=runtime["status"], runtime_proof=runtime)
            return result
        except MissingEvidence as error:
            result.update(status="NOT RUN", functional_status="NOT RUN", reason=str(error))
            return result
        except (EvidenceError, OSError, KeyError, TypeError, ValueError) as error:
            result["reason"] = str(error) if isinstance(error, EvidenceError) else "invalid selected evidence structure"
            return result

    def check(self, selection, *, catalog="platform/units/catalog.json"):
        summary = {"schema_version": 1, "generator": GENERATOR, "checker_sha256": digest(CHECKER_BYTES), "status": "FAIL", "strict_direct": self.strict_direct, "layers": {}, "cases": [], "errors": []}
        self.register_selection_paths(selection)
        try:
            require(isinstance(selection, dict) and type(selection.get("schema_version")) is int and selection["schema_version"] == 1, "unsupported selection schema")
            catalog_path = self.path(catalog)
            inventory = self.json(catalog_path).get("units")
            require(isinstance(inventory, list), "catalog has no Unit inventory")
            ids = [unit["id"] for unit in inventory]
            require(all(isinstance(x, str) for x in ids) and len(ids) == len(set(ids)), "catalog IDs are invalid or duplicated")
            rows = selection.get("cases")
            require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "selection cases must be a list")
            selected = [row.get("unit_id") for row in rows]
            require(all(isinstance(x, str) for x in selected) and len(selected) == len(set(selected)), "selection has invalid or duplicate Unit IDs")
            require(set(selected) == set(ids), "selection Unit IDs must exactly equal the catalog: missing=" + ",".join(sorted(set(ids) - set(selected))) + "; extra=" + ",".join(sorted(set(selected) - set(ids))))
            require(sha256_value(selection.get("expected_runtime_binary_sha256")), "selection requires an exact runtime binary SHA256")
            require(all(isinstance(selection.get(key), str) and bool(selection[key]) for key in ("device_id", "runtime")), "selection requires device_id and runtime")
            required = selection.get("required_layers", list(LAYERS))
            require(isinstance(required, list) and bool(required) and len(required) == len(set(required)) and set(required) <= set(LAYERS), "invalid required_layers")
            summary.update(catalog=self.label(catalog_path), catalog_sha256=digest(self.read(catalog_path)), expected_units=len(ids), expected_runtime_binary_sha256=selection["expected_runtime_binary_sha256"], required_layers=required)
            for row in rows:
                require(set(row) <= {"unit_id", "reason", *LAYERS}, "selection case has unsupported fields")
                require("reason" not in row or isinstance(row["reason"], str), "selection reason must be a string")
                case = {"unit_id": row["unit_id"], **{layer: self.layer(row["unit_id"], layer, row.get(layer), selection, catalog_path, ids) for layer in LAYERS}}
                case["same_session_cohort"] = self.cohort_identity(case["guest_controller"], case["live_browser"], selection["expected_runtime_binary_sha256"])
                if row.get("reason"):
                    case["selection_note"] = row["reason"]
                    for layer in LAYERS:
                        if case[layer]["status"] == "NOT RUN":
                            case[layer]["reason"] = row["reason"]
                summary["cases"].append(case)
            for layer in LAYERS:
                states = [row[layer]["status"] for row in summary["cases"]]
                summary["layers"][layer] = {"status": "FAIL" if "FAIL" in states else "PASS" if all(state == "PASS" for state in states) else "PARTIAL", "counts": {state: states.count(state) for state in ("PASS", "NOT RUN", "NOT VERIFIED", "FAIL")}, "functional_pass_units": sum(row[layer]["functional_status"] == "PASS" for row in summary["cases"]), "direct_pid_units": sum(row[layer].get("runtime_proof", {}).get("direct_pid_observed") is True for row in summary["cases"]), "indirect_service_generation_units": sum(row[layer].get("runtime_proof", {}).get("proof_kind") == "service-generation" and row[layer]["runtime_proof"].get("binary_sha256") == selection["expected_runtime_binary_sha256"] for row in summary["cases"])}
            states = [summary["layers"][layer]["status"] for layer in required]
            summary["status"] = "FAIL" if any(summary["layers"][layer]["status"] == "FAIL" for layer in LAYERS) else "PASS" if all(state == "PASS" for state in states) else "PARTIAL"
        except (EvidenceError, OSError, KeyError, TypeError, ValueError) as error:
            summary["errors"].append(str(error) if isinstance(error, EvidenceError) else "invalid selection or catalog structure")
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True, help="Explicit JSON selection containing every catalog Unit exactly once")
    parser.add_argument("--catalog", default="platform/units/catalog.json")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict-direct", action="store_true", help="Indirect runtime evidence becomes NOT VERIFIED, while retaining functional PASS")
    parser.add_argument("--write", type=Path, help="Write the same summary JSON to this file")
    args = parser.parse_args()
    checker = Checker(args.root, strict_direct=args.strict_direct)
    try:
        selection_raw = args.selection.read_bytes()
        selection = json.loads(selection_raw.decode("utf-8"))
        result = checker.check(selection, catalog=args.catalog)
        result["selection_sha256"] = digest(selection_raw)
    except (OSError, ValueError):
        result = {"schema_version": 1, "generator": GENERATOR, "status": "FAIL", "strict_direct": args.strict_direct, "cases": [], "layers": {}, "errors": ["selection file is missing or invalid JSON"]}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.write is not None:
        output = args.write.resolve()
        if output in {*checker.input_paths, args.selection.resolve(), Path(__file__).resolve()}:
            parser.error("--write must not overwrite selected evidence, its selection, or this checker")
        if output.exists():
            try:
                previous = json.loads(output.read_bytes())
                own_marker = isinstance(previous, dict) and (previous.get("generator") == GENERATOR or (sha256_value(previous.get("checker_sha256")) and type(previous.get("strict_direct")) is bool))
                own_summary = own_marker and isinstance(previous.get("cases"), list) and isinstance(previous.get("layers"), dict) and isinstance(previous.get("errors"), list)
            except (OSError, ValueError):
                own_summary = False
            if not own_summary:
                parser.error("--write may replace only an existing summary generated by this checker")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, prefix=".unit-batch-summary-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(rendered)
            os.replace(temporary, output)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    print(rendered, end="")
    return {"PASS": 0, "PARTIAL": 2}.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
