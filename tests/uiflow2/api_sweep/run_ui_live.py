#!/usr/bin/env python3
"""Execute UI recipes in one visible Device Service session with retained frames.

The caller owns admission/firmware composition. This runner takes a running
uart-repl session, checks its identity around each source Run, and stops it
with purge=0 after taking the evidence ZIP unless --keep-session is explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from check_ui_frame import check_frame
import probe_ui
from run_guest import Api, process_identity, runtime_executable, save, serial_pages


def source_for(args, method):
    if args.lane == "m5ui":
        return probe_ui.build_m5ui_program(args.target, [method] if method else [], args.target + "-" + str(method))
    if args.lane in ("display", "canvas"):
        width, height = (320, 240) if args.device == "cores3" else (240, 135)
        return probe_ui.build_display_program(method, args.lane + "-" + method, canvas=args.lane == "canvas", width=width, height=height)
    if args.lane == "widgets":
        width, height = (320, 240) if args.device == "cores3" else (240, 135)
        return probe_ui.build_widgets_program(args.target, method, args.target + "-" + str(method), width=width, height=height)
    if args.lane == "widgets-module":
        width, height = (320, 240) if args.device == "cores3" else (240, 135)
        return probe_ui.build_widgets_module_program(method, "widgets-module-" + method, width=width, height=height)
    if args.lane == "native-styles":
        if args.uiflow_root is None:
            raise ValueError("native-styles requires --uiflow-root for pinned header recipes")
        return probe_ui.build_native_style_program(args.uiflow_root)
    if args.lane == "lifecycle":
        return probe_ui.build_lifecycle_program()
    if args.lane == "corrections":
        source = Path(__file__).with_name("probe_m5ui_corrections.py").read_text(encoding="utf-8")
        return ("M5UI_CANDIDATE=True\n" if args.candidate_dir else "") + source
    if args.lane == "native-objects-more":
        return Path(__file__).with_name("probe_lvgl_obj_more.py").read_text(encoding="utf-8")
    if args.lane == "native-objects":
        return Path(__file__).with_name("probe_lvgl_objects.py").read_text(encoding="utf-8")
    if args.lane == "native-widgets-more":
        return (("NATIVE_WIDGET_GROUP=" + repr(args.target) + "\n") if args.target else "") + Path(__file__).with_name("probe_lvgl_widgets_more.py").read_text(encoding="utf-8")
    if args.lane == "native-widgets":
        return Path(__file__).with_name("probe_lvgl_widgets.py").read_text(encoding="utf-8")
    raise ValueError(args.lane)


def record_lines(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("M5EMU_UI_"):
            try:
                kind, payload = line.split(" ", 1)
                rows.append({"kind": kind.removeprefix("M5EMU_UI_"), "data": json.loads(payload)})
            except (ValueError, TypeError):
                continue
    return rows


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    api = Api(args.api, args.token_file)
    prefix = "sessions/" + args.session_id
    identity = api.json(prefix)
    if identity["state"] != "running" or identity.get("program_transport") != "uart-repl":
        raise ValueError("requires a running uart-repl Device Service session")
    if identity["device_id"] != args.device:
        raise ValueError("session device does not match --device")
    executable = runtime_executable(identity["pid"])
    report = {"schema_version": 1, "status": "EXECUTED", "validation": "virtual-device validation", "hardware_validation": "NOT RUN",
              "device_id": args.device, "session_id": args.session_id, "firmware_sha256": identity["firmware_sha256"],
              "runtime_binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(), "runtime": identity["runtime"],
              "pid": identity["pid"], "worker_generation": identity["worker"]["generation"], "lane": args.lane, "cases": []}
    report["implementation_lane"] = "candidate-source-override" if args.candidate_dir else "reference-frozen-implementation"
    save(args.out_dir / "identity.json", identity)
    if args.method:
        methods = args.method
    elif args.lane in ("display", "canvas"):
        methods = sorted(probe_ui.DISPLAY_RECIPES)
    elif args.lane == "widgets":
        methods = [None] + sorted(probe_ui.WIDGET_RECIPES[args.target])
    elif args.lane == "widgets-module":
        methods = ["setBrightness", "setRotation", "fillScreen"]
    else:
        methods = [None]
    try:
        for number, method in enumerate(methods):
            label = f"{number:03d}-" + (method or args.target or args.lane)
            out = args.out_dir / label
            out.mkdir()
            source = source_for(args, method)
            (out / "main.py").write_text(source, encoding="utf-8")
            previous = api.json(prefix + "/program").get("program") or {}
            files = probe_ui.fixture_files()
            if args.candidate_dir:
                provenance = json.loads((args.candidate_dir / "provenance.json").read_text(encoding="utf-8"))
                for entry in provenance["files"]:
                    raw = (args.candidate_dir / entry["candidate_module"]).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != entry["candidate_sha256"]:
                        raise ValueError("candidate module digest changed")
                    files[entry["candidate_module"]] = {"encoding": "utf8", "data": raw.decode("utf-8")}
                for entry in provenance.get("support_files", []):
                    raw = (args.candidate_dir / entry["path"]).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                        raise ValueError("candidate package support digest changed")
                    files[entry["path"]] = {"encoding": "utf8", "data": raw.decode("utf-8")}
                save(args.out_dir / "candidate-provenance.json", provenance)
            files["main.py"] = {"encoding": "utf8", "data": source}
            receipt = api.json(prefix + "/program", "POST", {"files": files, "source_kind": "uiflow2-package", "entrypoint": "main.py",
                "expected_execution_id": previous.get("execution_id"), "timeout_seconds": 120})
            save(out / "program.json", receipt)
            execution_id = receipt["program"]["execution_id"]
            offset = receipt["program"]["serial_offset"]
            transcript = ""
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                text, offset, _pages = serial_pages(api, args.session_id, offset)
                transcript += text
                records = record_lines(transcript)
                if any(row["kind"] == "READY" for row in records) or ":ERROR" in transcript:
                    break
                time.sleep(.1)
            (out / "serial.txt").write_text(transcript, encoding="utf-8")
            state = api.json(prefix)
            program = api.json(prefix + "/program")
            if state["pid"] != identity["pid"] or state["firmware_sha256"] != identity["firmware_sha256"]:
                raise RuntimeError("session process/firmware changed during the UI batch")
            if (program.get("program") or {}).get("execution_id") != execution_id:
                raise RuntimeError("another program replaced the active UI recipe")
            frame = api.raw(prefix + "/frame.png")
            (out / "frame.png").write_bytes(frame)
            save(out / "context.json", program)
            case = {"label": label, "method": method, "execution_id": execution_id,
                    "api_target": next((row["data"].get("api_target") for row in records if row["data"].get("api_target")), None),
                    "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "frame_sha256": hashlib.sha256(frame).hexdigest(),
                    "ready": any(row["kind"] == "READY" for row in records),
                    "results": [row["data"] for row in records if row["kind"] == "RESULT"], "frame_oracles": []}
            case["group_errors"] = [row["data"] for row in records if row["kind"] == "GROUP_ERROR"]
            for row in records:
                if row["kind"] == "FRAME_ORACLE":
                    case["frame_oracles"].append({"method": row["data"]["method"], "argument_domain": row["data"].get("argument_domain"), **check_frame(frame, row["data"]["oracle"], row["data"].get("tolerance", 8))})
            save(out / "result.json", case)
            report["cases"].append(case)
            save(args.out_dir / "report.json", report)
            print(json.dumps({"label": label, "ready": case["ready"], "state_results": len(case["results"]), "frame_results": [row["status"] for row in case["frame_oracles"]]}), flush=True)
            if not case["ready"]:
                raise RuntimeError("UI recipe did not reach READY: " + label)
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    finally:
        if not args.keep_session:
            try:
                bundle = api.raw(prefix + "/evidence")
                (args.out_dir / "evidence.zip").write_bytes(bundle)
                report["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
                stopped = api.json(prefix + "?purge=0", "DELETE")
                for _ in range(100):
                    stopped = api.json(prefix)
                    if stopped["state"] in ("stopped", "failed"):
                        break
                    time.sleep(.1)
                save(args.out_dir / "stopped.json", stopped)
                report["cleanup"] = {"terminal_state": stopped["state"], "pid_gone": not process_identity(identity["pid"])["exists"],
                    "flash_released": not stopped.get("flash_retained"), "history_preserved": stopped["firmware_sha256"] == identity["firmware_sha256"]}
                if stopped["state"] != "stopped" or not all(report["cleanup"][key] for key in ("pid_gone", "flash_released", "history_preserved")):
                    report["status"] = "FAIL"
            except Exception as error:
                report.update(status="FAIL", cleanup_error=str(error))
        save(args.out_dir / "report.json", report)
    return 0 if report["status"] == "EXECUTED" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--device", choices=("cores3", "cardputer-adv"), required=True)
    parser.add_argument("--lane", choices=("m5ui", "display", "canvas", "widgets", "widgets-module", "native-styles", "native-objects", "native-objects-more", "native-widgets", "native-widgets-more", "lifecycle", "corrections"), required=True)
    parser.add_argument("--target")
    parser.add_argument("--method", action="append")
    parser.add_argument("--uiflow-root", type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--keep-session", action="store_true")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
