#!/usr/bin/env python3
"""Run the documented M5UI method matrix on one UIFlow2 board.

Each widget receives a fresh visible Device Service session. The caller supplies
an isolated service and token; fixtures and all observations remain in --out-dir.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tests/uiflow2/api_sweep"
sys.path.insert(0, str(TOOLS))

import probe_ui  # noqa: E402
from run_m5ui_documented import documented_targets, widget_source  # noqa: E402
from run_ui_live import api_dimensions, record_lines, ui_rotation  # noqa: E402


PYTHON = Path(sys.executable)
RUN_GUEST = TOOLS / "run_guest.py"


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fixture_dir(output: Path) -> Path:
    path = output / "m5ui-fixtures"
    path.mkdir(exist_ok=True)
    for name, row in probe_ui.fixture_files().items():
        (path / name).write_bytes(base64.b64decode(row["data"]))
    return path


def lifecycle_source(width: int, height: int, rotation: int) -> str:
    source = probe_ui.GUEST_COMMON % ("documented-lifecycle", "m5ui")
    source = source.replace(
        "    M5.Lcd.setRotation(0)\n",
        f"    M5.Lcd.setRotation({rotation})\n",
        1,
    )
    return source + f'''
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
ok=(lv.is_initialized() and loop is not None and loop._initialized
    and callbacks[0]>0
    and lv.display_get_default().get_horizontal_resolution()=={width})
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


def execute(command: list[str], timeout: int) -> dict:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return {
        "returncode": completed.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "output_tail": completed.stdout[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("stopwatch", "core2"), required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--target", action="append")
    args = parser.parse_args()
    output_root = args.out_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    lane = output_root / args.device
    inventory = json.loads((TOOLS / "inventory_ui.source.json").read_text())
    targets = documented_targets(inventory)
    requested = set(args.target or [])
    if requested:
        targets = {target: methods for target, methods in targets.items() if target in requested}
    width, height = api_dimensions(args.device)
    rotation = ui_rotation(args.device)
    fixtures = fixture_dir(output_root)
    sources = lane / "m5ui-sources"
    sources.mkdir(parents=True, exist_ok=True)
    cases = []
    batches = [
        (target, methods, widget_source(target, methods, width, height, rotation))
        for target, methods in targets.items()
    ]
    if not requested or "m5ui" in requested:
        batches.append(("m5ui", ["init", "deinit"], lifecycle_source(width, height, rotation)))
    for target, methods, source in batches:
        source_path = sources / (target + ".py")
        source_path.write_text(source, encoding="utf-8")
        output = lane / "m5ui" / target
        command = [
            str(PYTHON),
            str(RUN_GUEST),
            "--api",
            args.api,
            "--device",
            args.device,
            "--source",
            str(source_path),
            "--fixture-dir",
            str(fixtures),
            "--done-marker",
            "M5EMU_UI_READY",
            "--out-dir",
            str(output),
            "--timeout",
            str(args.timeout),
            "--prepare-timeout",
            "600",
            "--ready-timeout",
            "180",
            "--token-file",
            str(args.token_file.resolve()),
        ]
        print(json.dumps({"device": args.device, "target": target, "phase": "start"}), flush=True)
        result = execute(command, args.timeout + 700)
        serial = (output / "serial.txt").read_text(errors="replace") if (output / "serial.txt").is_file() else ""
        records = record_lines(serial)
        results = [row["data"] for row in records if row["kind"] == "RESULT"]
        case = {
            "target": target,
            "documented_methods": methods,
            "returncode": result["returncode"],
            "seconds": result["seconds"],
            "ready": any(row["kind"] == "READY" for row in records),
            "results": results,
            "unobserved_methods": sorted(set(methods) - {row.get("method") for row in results}),
            "status_counts": dict(Counter(row.get("status") for row in results)),
        }
        report_path = output / "report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            case["session"] = {
                key: report.get(key)
                for key in (
                    "status",
                    "session_id",
                    "firmware_sha256",
                    "runtime_binary_sha256",
                    "frame_sha256",
                    "evidence_sha256",
                    "cleanup",
                )
            }
        cases.append(case)
        save(output_root / (args.device + "-m5ui-run.json"), cases)
        print(
            json.dumps(
                {
                    "device": args.device,
                    "target": target,
                    "phase": "done",
                    "returncode": result["returncode"],
                    "ready": case["ready"],
                    "status_counts": case["status_counts"],
                }
            ),
            flush=True,
        )
    return 0 if all(row["returncode"] == 0 and row["ready"] for row in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
