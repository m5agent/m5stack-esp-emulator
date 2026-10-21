#!/usr/bin/env python3
"""Run deterministic Tab5 peripheral state scenarios through esp-emu P4."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_tab5_ui_test.py"
SCENARIOS = ROOT / "tests/uiflow2/tab5_peripherals/scenarios.json"
VENV_PYTHON = ROOT / ".work/tab5-venv/bin/python"


def main() -> None:
    if (
        VENV_PYTHON.is_file()
        and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
    ):
        os.execv(
            str(VENV_PYTHON),
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-tab5-peripheral-scenarios"),
    )
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--scenario", action="append", default=[])
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(SCENARIOS.read_text())
    results = {}
    for scenario in manifest["scenarios"]:
        if args.scenario and scenario["id"] not in args.scenario:
            continue
        case_dir = args.out_dir / scenario["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(RUNNER),
            "--base", str(ROOT / manifest["base"]),
            "--elf", str(ROOT / manifest["elf"]),
            "--files-dir", str(ROOT / manifest["files_dir"]),
            "--out-dir", str(case_dir),
            "--timeout", str(args.timeout),
            "--ready-marker", manifest["ready_marker"],
            "--probe-only",
        ]
        for device in manifest["common_i2c"] + scenario["i2c"]:
            command.extend(["--i2c-dev", device])
        process = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        result_path = case_dir / "result.json"
        serial = ""
        if result_path.is_file():
            serial = json.loads(result_path.read_text()).get("serial", "")
        missing = [
            marker for marker in scenario["serial_expect"]
            if marker not in serial
        ]
        status = (
            "PASS"
            if process.returncode == 0 and not missing
            else "FAIL"
        )
        results[scenario["id"]] = {
            "status": status,
            "description": scenario["description"],
            "exit_code": process.returncode,
            "command": command,
            "serial_expect": scenario["serial_expect"],
            "missing_markers": missing,
            "serial_log": str(case_dir / "p4.log"),
            "result": str(result_path),
            "output": process.stdout,
        }
        print(
            f"{status} tab5/{scenario['id']} "
            f"missing={','.join(missing) or 'none'}"
        )

    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "device": manifest["device"],
        "scenario_manifest": str(SCENARIOS.relative_to(ROOT)),
        "scenario_manifest_sha256": hashlib.sha256(
            SCENARIOS.read_bytes()
        ).hexdigest(),
        "results": results,
    }
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    if any(result["status"] != "PASS" for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
