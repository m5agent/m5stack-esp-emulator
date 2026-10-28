#!/usr/bin/env python3
"""Reconcile declared/observed UI APIs with actual per-device recipe outcomes.

The detailed output belongs in ignored raw storage. A short summary may be
published; it must retain STATE_PASS/pending/blocker distinctions. Shared C
implementation owners never grant unexecuted aliases or inherited classes PASS.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

DEVICES = ("cores3", "cardputer-adv")
SDK_PREIMAGES = {
    "cores3": "7ce5ca0744a27508913c4dd69dd06f30454fb27c54a920faf486d3350cf2267b",
    "cardputer-adv": "ce48e92a4658059fbd370b5045f51b604974795cea45635ed87a6d293fb01777",
}


def implementation_lane(report):
    lane = report.get("implementation_lane", "reference-frozen-implementation")
    if report.get("base_sha256") == SDK_PREIMAGES.get(report.get("device_id")):
        return "matching-sdk-preimage"
    if report.get("firmware_lane") not in (None, "stock-frozen") or report.get("base_lane") == "caller-pinned-candidate":
        return "candidate-firmware"
    return lane


def expand_members(sets, key, active=None):
    active = set() if active is None else active
    if key in active:
        raise ValueError("runtime member-set cycle")
    active.add(key)
    spec = sets[key]
    result = expand_members(sets, spec["base"], active) if spec.get("base") else {}
    for name in spec.get("removed", []):
        result.pop(name, None)
    for row in spec.get("members", []):
        result[row[0]] = row
    active.remove(key)
    return result


def inventory_rows(inventory):
    rows = {}
    def ensure(surface, name, kind, source):
        key = surface + "." + name
        if key not in rows:
            rows[key] = {"surface": surface, "member": name, "kind": kind, "sources": [],
                "devices": {device: {"status": "NOT_RUN", "blocker": "No device-specific behavioral observation selected"} for device in DEVICES}}
        if source not in rows[key]["sources"]:
            rows[key]["sources"].append(source)
        return rows[key]
    for surface in inventory["documented_surfaces"]:
        for member in surface["members"]:
            ensure(surface["api_path"], member["name"], member["kind"], "official-documentation")
    runtime = inventory["runtime"]
    for surface in runtime["surfaces"]:
        path = surface["api_path"]
        if not (path.startswith(("m5ui", "lvgl", "M5.Widgets", "M5.Display", "label_plus", "image_plus")) or path == "M5.Lcd"):
            continue
        for name, member in expand_members(runtime["member_sets"], surface["member_set"]).items():
            kind = "read_error" if member[1] == "read_error" else "constant_or_enum_type" if name.isupper() else "callable" if member[2] is True else "data"
            row = ensure(path, name, kind, "firmware-runtime-export")
            if kind in ("constant_or_enum_type", "data"):
                for device in DEVICES:
                    row["devices"][device] = {"status": "INVENTORY_ONLY", "blocker": "Data/enum reflection is outside functional-callable PASS"}
    return rows


def scan_run(root):
    observations = []
    for summary in root.rglob("summary.json"):
        data = json.loads(summary.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "results" not in data:
            continue
        receipt = summary.with_name("program.json")
        submitted = ""
        if receipt.exists():
            program = json.loads(receipt.read_text(encoding="utf-8")).get("program") or {}
            submitted = program.get("submitted_at", "")
        for result in data["results"]:
            if "data" in result and "kind" in result:
                result = result["data"]
            if "method" not in result:
                continue
            target = result.get("api_target") or ("m5ui." + data["target"] if str(data.get("target", "")).startswith("M5") else data.get("target"))
            if not target:
                continue
            observations.append((submitted, target, result, {"device_id": "cores3", "evidence": str(summary), "execution_id": data.get("execution_id"), "implementation_lane": "reference-frozen-implementation"}))
    for report_file in root.rglob("report.json"):
        report = json.loads(report_file.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or "device_id" not in report:
            continue
        if "cases" not in report:
            serial = report_file.with_name("serial.txt")
            frame_path = report_file.with_name("frame.png")
            if not serial.exists():
                continue
            lane = implementation_lane(report)
            context = {key: report.get(key) for key in ("device_id", "session_id", "base_sha256", "source_sha256", "firmware_sha256", "runtime_binary_sha256", "runtime", "frame_sha256", "evidence_sha256")}
            context.update(evidence=str(report_file), implementation_lane=lane, execution_id=report.get("session_id"))
            submitted = ""
            created = report_file.with_name("created.json")
            if created.exists():
                submitted = json.loads(created.read_text()).get("created_at", "")
            for line in serial.read_text(encoding="utf-8").splitlines():
                if not line.startswith(("M5EMU_UI_RESULT ", "M5EMU_UI_FRAME_ORACLE ")):
                    continue
                kind, payload = line.split(" ", 1)
                result = json.loads(payload)
                target = result.get("api_target")
                if not target or "method" not in result:
                    continue
                if kind == "M5EMU_UI_FRAME_ORACLE" and frame_path.exists():
                    from check_ui_frame import check_frame
                    result.update(check_frame(frame_path.read_bytes(), result["oracle"], result.get("tolerance", 8)))
                    observations.append((submitted, target, result, {**context, "observation_kind": "frame"}))
                elif kind == "M5EMU_UI_RESULT":
                    observations.append((submitted, target.removesuffix(".style"), result, context))
            continue
        for case in report["cases"]:
            if not isinstance(case, dict) or "label" not in case:
                continue
            receipt = report_file.parent / case["label"] / "program.json"
            submitted = ""
            if receipt.exists():
                program = json.loads(receipt.read_text(encoding="utf-8")).get("program") or {}
                submitted = program.get("submitted_at", "")
            context = {key: report.get(key) for key in ("device_id", "session_id", "firmware_sha256", "runtime_binary_sha256", "runtime", "worker_generation", "implementation_lane")}
            context.update(evidence=str(report_file), execution_id=case.get("execution_id"), frame_sha256=case.get("frame_sha256"))
            for result in case["results"]:
                target = result.get("api_target")
                if target:
                    observations.append((submitted, target.removesuffix(".style"), result, context))
            for frame in case["frame_oracles"]:
                # The renderer oracle is kept separately from the native state
                # result so missing glyph/alignment checks cannot disappear.
                target = next((row.get("api_target") for row in case["results"] if row.get("method") == frame["method"]), case.get("api_target"))
                if target:
                    observations.append((submitted, target, {"method": frame["method"], "status": frame["status"], "frame_oracle": frame}, {**context, "observation_kind": "frame"}))
    return observations


def apply_runtime(rows, device, transcript):
    from generate_ui_inventory import runtime_inventory
    runtime = runtime_inventory([transcript])
    origin = {"transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest()}
    identity_path = transcript.with_name("report.json")
    if identity_path.exists():
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        origin.update({key: identity.get(key) for key in ("session_id", "firmware_sha256", "runtime_binary_sha256")})
    for surface in runtime["surfaces"]:
        path = surface["api_path"]
        if not path.startswith(("m5ui", "lvgl", "M5.Widgets", "M5.Display", "M5.Lcd", "label_plus", "image_plus")):
            continue
        for name, member in expand_members(runtime["member_sets"], surface["member_set"]).items():
            key = path + "." + name
            if key not in rows:
                kind = "constant_or_enum_type" if name.isupper() else "callable" if member[2] is True else "data"
                rows[key] = {"surface": path, "member": name, "kind": kind, "sources": ["device-runtime-export"],
                    "devices": {item: {"status": "NOT_RUN", "blocker": "No device-specific behavioral observation selected"} for item in DEVICES}}
            rows[key]["devices"][device]["runtime_presence"] = {"status": "PRESENT", **origin}
    for record in runtime["records"]:
        if record.get("kind") != "import_error" or "ImportError" not in record.get("error", ""):
            continue
        prefix = record["path"]
        for row in rows.values():
            if row["surface"] == prefix or row["surface"].startswith(prefix + "."):
                entry = row["devices"][device]
                if entry["status"] in ("NOT_RUN", "INVENTORY_ONLY"):
                    entry.update(status="UNAVAILABLE_ON_DEVICE", blocker=record["error"], runtime_presence={"status": "IMPORT_ERROR", **origin})
    return {"device_id": device, "surfaces": len(runtime["surfaces"]), **origin}


def summarize(inventory, roots, device_logs=None):
    rows = inventory_rows(inventory)
    runtime_checks = [apply_runtime(rows, device, transcript) for device, transcript in (device_logs or [])]
    observations = sorted((observation for root in roots for observation in scan_run(root)), key=lambda row: row[0])
    candidates = []
    for submitted, target, result, context in observations:
        key = target + "." + result["method"]
        if context.get("implementation_lane") not in (None, "reference-frozen-implementation"):
            candidates.append({"api": key, "submitted_at": submitted, "result": result, **context})
            continue
        if key not in rows:
            rows[key] = {"surface": target, "member": result["method"], "kind": "executed_callable", "sources": ["actual-behavioral-probe"],
                         "devices": {device: {"status": "NOT_RUN", "blocker": "No device-specific behavioral observation selected"} for device in DEVICES}}
        device = context["device_id"]
        entry = rows[key]["devices"][device]
        if context.get("observation_kind") == "frame":
            if entry.get("execution_id") not in (None, context.get("execution_id")):
                entry = {"status": "NOT_RUN"}
                rows[key]["devices"][device] = entry
            entry["frame_result"] = result
            frames = entry.setdefault("frame_results", [])
            frames.append(result)
            if entry["status"] == "NOT_RUN":
                entry.update(status=result["status"], **context)
            if any(frame["status"] == "FAIL" for frame in frames):
                entry["status"] = "FAIL"
        else:
            if entry.get("execution_id") and entry.get("execution_id") == context.get("execution_id"):
                domains = entry.setdefault("argument_results", [{key: entry[key] for key in ("status", "argument_domain") if key in entry}])
                domains.append(result)
                if result["status"] == "FAIL" or any(row["status"] == "FAIL" for row in domains):
                    entry["status"] = "FAIL"
            else:
                rows[key]["devices"][device] = {**result, **context, "submitted_at": submitted}
            getter = result.get("paired_getter")
            if getter and result["status"] == "STATE_PASS":
                getter_key = target + "." + getter
                if getter_key in rows:
                    rows[getter_key]["devices"][device] = {"status": "STATE_PASS", "oracle": result.get("oracle"), "directly_called_by_set_get_recipe": key, **context}
    counts = {device: dict(Counter(row["devices"][device]["status"] for row in rows.values())) for device in DEVICES}
    return {"schema_version": 1, "status": "PARTIAL" if any(any(state["status"] in ("NOT_RUN", "FAIL", "PENDING_FRAME_OR_INPUT", "PENDING_FRAME_OBJECT_REMOVAL") for state in row["devices"].values()) for row in rows.values()) else "REQUIRES_REVIEW",
            "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "api_rows": len(rows), "counts": counts,
            "coverage_rule": "STATE_PASS is a specific native/state oracle. It does not imply pixels/events, an untested alias, inherited class, resource shape or another device. Candidate corrections never overwrite reference-firmware outcomes.",
            "results": rows, "candidate_observations": candidates, "runtime_checks": runtime_checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path(__file__).with_name("inventory_ui.source.json"))
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-log", action="append", default=[], help="DEVICE=complete UI reflection transcript")
    args = parser.parse_args()
    device_logs = []
    for value in args.runtime_log:
        device, path = value.split("=", 1)
        if device not in DEVICES:
            raise ValueError("unknown runtime device: " + device)
        device_logs.append((device, Path(path)))
    result = summarize(json.loads(args.inventory.read_text(encoding="utf-8")), args.run_dir, device_logs)
    result["inventory_sha256"] = hashlib.sha256(args.inventory.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "api_rows", "counts")}))


if __name__ == "__main__":
    main()
