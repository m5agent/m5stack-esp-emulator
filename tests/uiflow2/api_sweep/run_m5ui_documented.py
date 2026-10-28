#!/usr/bin/env python3
"""Observe each documented M5UI method in one owned visible CoreS3 session.

Every widget receives one program containing its exact documented method list.
probe_ui resets the constructor state before each call. State, frame/input
pending, unsupported and documentation mismatch observations remain distinct.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.parse

import probe_ui
from run_contract_with_receipts import ReceiptClient, require, sha
from run_device_api import save
from run_guest import Api
from run_ui_live import record_lines

HERE = Path(__file__).resolve().parent
COMMIT = "3a86d8f611b3639cca755a933e01a5a829771ef1"
CHILD_LABEL_METHODS = {"set_text", "set_long_mode", "set_shadow", "unset_shadow", "get_text"}


def documented_targets(inventory):
    return {row["api_path"].split(".")[-1]: [m["name"] for m in row["members"] if m["kind"] == "method"]
            for row in inventory["documented_surfaces"] if row["api_path"].startswith("m5ui.")}


def source_audit(root):
    require(subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == COMMIT,
            "M5UI source checkout must match the documented pinned commit")
    result = {}
    for module in ("msgbox", "win", "roller", "base", "label", "port", "__init__"):
        relative = "m5stack/libs/m5ui/" + module + ".py"
        path = root / relative
        raw = path.read_bytes()
        pinned = subprocess.check_output(["git", "-C", str(root), "show", COMMIT + ":" + relative])
        require(raw == pinned, "source audit refuses a dirty relevant M5UI module: " + relative)
        tree = ast.parse(raw)
        result[module] = {"path": relative, "sha256": sha(raw), "classes": {
            cls.name: [node.name for node in cls.body if isinstance(node, ast.FunctionDef)]
            for cls in tree.body if isinstance(cls, ast.ClassDef)}}
    return result


def widget_source(target, methods):
    source = probe_ui.build_m5ui_program(target, methods, "documented-" + target)
    mismatches = CHILD_LABEL_METHODS if target in {"M5Msgbox", "M5Win"} else ({"event"} if target == "M5Roller" else set())
    for method in mismatches.intersection(methods):
        old = "emit('RESULT',method=" + repr(method) + ",status='NOT_RUN',reason='No behavior-specific recipe yet')"
        reason = ("Documentation example operates on returned M5Label/M5Button, not the container"
                  if target != "M5Roller" else "Pinned M5Roller/M5Base has no event method; use add_event_cb")
        new = ("emit('RESULT',method=" + repr(method) + ",status='DOCUMENTATION_MISMATCH',reason=" + repr(reason)
               + ",runtime_has_member=hasattr(obj," + repr(method) + "),runtime_member_type=str(type(getattr(obj,"
               + repr(method) + ",None))))")
        require(old in source, "mismatch must replace exactly an unassigned documented slot")
        source = source.replace(old, new, 1)
    compile(source, "<m5ui>" , "exec")
    return source


def lifecycle_source():
    return probe_ui.GUEST_COMMON % ("documented-lifecycle", "m5ui") + '''
import m5ui
import m5ui.port as port
import lvgl as lv
callbacks=[0]
def observed_tick(timer):
    callbacks[0]+=1
m5ui.init()
timer=lv.timer_create(observed_tick,30,None)
settle()
loop=port.event_loop._instance
ok=lv.is_initialized() and loop is not None and loop._initialized and callbacks[0]>0 and lv.display_get_default().get_horizontal_resolution()==320
emit('RESULT',method='init',status='STATE_PASS' if ok else 'FAIL',oracle='native LVGL/display and actual timer delivery',callback_count=callbacks[0],native_initialized=lv.is_initialized(),instance_initialized=loop is not None and loop._initialized,class_helper_initialized=port.event_loop.is_initialized())
m5ui.deinit()
before=callbacks[0]
settle()
ok=not lv.is_initialized() and port.event_loop._instance is None and callbacks[0]==before
emit('RESULT',method='deinit',status='STATE_PASS' if ok else 'FAIL',oracle='native LVGL deinitialized and timer delivery stopped',native_initialized=lv.is_initialized(),instance_released=port.event_loop._instance is None,callback_count_at_return=before,callback_count_after_wait=callbacks[0])
m5ui.init()
try:
    page=m5ui.M5Page(bg_c=0x0B1014)
    label=m5ui.M5Label('M5UI lifecycle',x=30,y=80,parent=page)
    page.screen_load()
    settle()
    emit('READY',status='AWAITING_FRAME_AND_INPUT',method_count=2)
    while True:
        M5.update()
        time.sleep_ms(20)
finally:
    m5ui.deinit()
'''


def run(args):
    origin = urllib.parse.urlparse(args.api)
    require(origin.hostname in {"localhost", "127.0.0.1", "::1"} and origin.port != 8787
            and origin.path in {"", "/"}, "use a dedicated local service origin; port 8787 belongs to the user")
    require(re.fullmatch(r"[0-9a-f]{64}", args.expected_runtime_sha256), "pin the exact runtime SHA256")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    inventory_path = HERE / "inventory_ui.source.json"
    inventory = json.loads(inventory_path.read_text())
    targets = documented_targets(inventory)
    requested = set(getattr(args, "target", None) or [])
    require(requested.issubset(set(targets) | {"m5ui"}), "requested target must be a documented M5UI widget or m5ui lifecycle")
    if requested:
        targets = {target: methods for target, methods in targets.items() if target in requested}
    audit = source_audit(args.uiflow_root)
    for target, methods in targets.items():
        widget_source(target, methods)
    client = ReceiptClient(args.api.rstrip("/") + "/api/v1", args.token_file.read_text().strip(), args.out_dir)
    client.expected_runtime_sha256 = args.expected_runtime_sha256
    program_api = Api(args.api, args.token_file)
    report = {"schema_version": 1, "status": "FAIL", "validation": "selected virtual-device state observations",
              "hardware_validation": "NOT_RUN", "implementation_lane": "stock-frozen-M5UI",
              "inventory_sha256": sha(inventory_path.read_bytes()), "source_commit": COMMIT,
              "source_audit": audit, "runner_sha256": sha(Path(__file__).read_bytes()),
              "probe_source_sha256": sha(Path(probe_ui.__file__).read_bytes()), "cases": []}
    sid = None

    def call(method, path, payload=None, expected=200):
        record, data = client.call(method, path, payload)
        require(record["status"] == expected, f"{method} {path}: HTTP {record['status']}")
        return data

    try:
        firmware = call("GET", "/firmware/" + args.firmware_id)
        require(firmware["device_id"] == "cores3" and firmware["kind"] == "uiflow", "requires admitted CoreS3 UIFlow firmware")
        save(args.out_dir / "firmware.json", firmware)
        created = call("POST", "/sessions", {"device_id": "cores3", "firmware_id": args.firmware_id,
                       "uiflow_source_sha256": firmware["source"]["metadata"]["source_sha256"],
                       "program_transport": "uart-repl", "runtime": "qemu", "ttl_seconds": 1800,
                       "ready_marker": "M5EMU_UART_REPL_READY", "ready_timeout_seconds": 60}, expected=202)
        sid = created["session_id"]
        prefix = "/sessions/" + sid
        report["session_id"] = sid
        deadline = time.monotonic() + 180
        while True:
            identity = call("GET", prefix)
            if identity["state"] in {"running", "failed", "stopped"} or time.monotonic() > deadline:
                break
            time.sleep(.2)
        require(identity["state"] == "running" and identity["program_transport"] == "uart-repl", "guest not ready for actual warm Runs")
        save(args.out_dir / "identity.json", identity)
        batches = [(target, methods, widget_source(target, methods)) for target, methods in targets.items()]
        if not requested or "m5ui" in requested:
            batches.append(("m5ui", ["init", "deinit"], lifecycle_source()))
        for target, methods, source in batches:
            out = args.out_dir / target
            out.mkdir()
            (out / "main.py").write_text(source)
            previous = call("GET", prefix + "/program").get("program") or {}
            files = probe_ui.fixture_files()
            files["main.py"] = {"encoding": "utf8", "data": source}
            request = {"files": files, "entrypoint": "main.py", "source_kind": "uiflow2-package",
                       "expected_execution_id": previous.get("execution_id"), "timeout_seconds": 120}
            save(out / "program-request.json", request)
            # Large real UART transfers may exceed Client's 30-second read
            # limit. The established program client allows 180 seconds;
            # its saved response and the final ZIP bind the actual source.
            receipt = program_api.json(prefix.lstrip("/") + "/program", "POST", request)
            save(out / "program.json", receipt)
            execution = receipt["program"]["execution_id"]
            offset = receipt["program"]["serial_offset"]
            transcript = ""
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                page = call("GET", prefix + f"/serial?offset={offset}&limit=262144")
                transcript += page["data"]
                require(page["next_offset"] >= offset, "serial cursor moved backwards")
                offset = page["next_offset"]
                records = record_lines(transcript)
                if any(row["kind"] == "READY" for row in records) or "Traceback (most recent call last)" in transcript:
                    break
                time.sleep(.25)
            (out / "serial.txt").write_text(transcript)
            state = call("GET", prefix)
            program = call("GET", prefix + "/program")
            require(all(state[k] == identity[k] for k in ("pid", "firmware_sha256")), "guest identity changed")
            require(program["program"]["execution_id"] == execution, "program replaced concurrently")
            client.verify_runtime(sid)
            record, _ = client.call("GET", prefix + "/frame.png")
            require(record["status"] == 200, "frame missing")
            frame = (args.out_dir / f"{client.index:04d}.response").read_bytes()
            (out / "frame.png").write_bytes(frame)
            case = {"target": target, "documented_methods": methods, "execution_id": execution,
                    "source_sha256": sha(source.encode()), "frame_sha256": sha(frame),
                    "ready": any(row["kind"] == "READY" for row in records),
                    "results": [row["data"] for row in records if row["kind"] == "RESULT"],
                    "frame_behavior": "NOT_RUN", "injected_input_behavior": "NOT_RUN"}
            case["unobserved_methods"] = sorted(set(methods) - {row["method"] for row in case["results"]})
            save(out / "result.json", case)
            report["cases"].append(case)
            save(args.out_dir / "report.json", report)
            print(json.dumps({"target": target, "ready": case["ready"], "results": dict(Counter(row["status"] for row in case["results"]))}), flush=True)
            require(case["ready"], "batch did not reach READY: " + target)
        report["status"] = "EXECUTED_WITH_BOUNDARIES"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if sid:
            prefix = "/sessions/" + sid
            try:
                record, _ = client.call("GET", prefix + "/evidence")
                require(record["status"] == 200, "pre-stop ZIP request failed")
                (args.out_dir / "evidence.zip").write_bytes((args.out_dir / f"{client.index:04d}.response").read_bytes())
            except Exception as error:
                report["evidence_error"] = str(error)
            try:
                call("DELETE", prefix + "?purge=0")
                client.finalize_history()
            except Exception as error:
                report["cleanup_error"] = str(error)
        report["session_receipts"] = list(client.receipts.values())
        report["receipt_errors"] = client.receipt_errors
        report["result_counts"] = dict(Counter(row["status"] for case in report["cases"] for row in case["results"]))
        if client.receipt_errors or not report["session_receipts"] or any(row.get("status") != "PASS" for row in report["session_receipts"]):
            report["status"] = "FAIL"
        save(args.out_dir / "report.json", report)
    return 0 if report["status"] == "EXECUTED_WITH_BOUNDARIES" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="Dedicated local Device Service origin, without /api/v1")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--firmware-id", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--uiflow-root", type=Path, required=True)
    parser.add_argument("--target", action="append", help="repeat to narrow targets; m5ui selects only init/deinit")
    parser.add_argument("--out-dir", type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
