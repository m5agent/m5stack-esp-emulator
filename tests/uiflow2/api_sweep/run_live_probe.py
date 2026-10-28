#!/usr/bin/env python3
"""Run one finite source probe through an existing UART-REPL session.

This is the non-UI counterpart to run_ui_live.py. It executes the probe in the
same visible guest, records the execution receipt and serial bytes, and either
keeps the session for a subsequent batch or requests the evidence ZIP before
stopping it with purge=0.
"""
from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path
import time
import zipfile

from run_guest import Api, DEVICE_CHOICES, process_identity, runtime_executable, save, serial_pages


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
    source = args.source.read_text(encoding="utf-8")
    for statement in args.append_code or []:
        source += "\n" + statement.rstrip() + "\n"
    compile(source, "<live-probe>", "exec")
    report = {
        "schema_version": 1,
        "status": "FAIL",
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "device_id": args.device,
        "session_id": args.session_id,
        "firmware_sha256": identity["firmware_sha256"],
        "runtime_binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "runtime": identity["runtime"],
        "pid": identity["pid"],
        "worker_generation": identity["worker"]["generation"],
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
    }
    save(args.out_dir / "identity.json", identity)
    try:
        previous = api.json(prefix + "/program").get("program") or {}
        direct = len(source.encode("utf-8")) <= 65536 and args.timeout <= 30
        request = {
            "expected_execution_id": previous.get("execution_id"),
            "timeout_seconds": args.timeout if not direct else min(args.timeout, 30),
        }
        if direct:
            request["source"] = source
        else:
            direct = False
            request.update(
                files={"main.py": {"encoding": "utf8", "data": source}},
                source_kind="uiflow2-package",
                entrypoint="main.py",
                timeout_seconds=min(args.timeout, 120),
            )
        receipt = api.json(prefix + "/program", "POST", request)
        save(args.out_dir / "program.json", receipt)
        execution_id = receipt["program"]["execution_id"]
        offset = receipt["program"]["serial_offset"]
        transcript = ""
        deadline = time.monotonic() + args.timeout + 15
        while time.monotonic() < deadline:
            text, offset, pages = serial_pages(api, args.session_id, offset)
            transcript += text
            save(args.out_dir / "serial-pages.json", pages)
            (args.out_dir / "serial.txt").write_text(transcript, encoding="utf-8")
            if args.done_marker in transcript:
                report["status"] = "EXECUTED"
                break
            if "Traceback (most recent call last)" in transcript:
                raise RuntimeError("guest probe raised an exception before its completion marker")
            current = api.json(prefix)
            if current["state"] != "running":
                raise RuntimeError("session ended before the completion marker: " + str(current.get("error")))
            time.sleep(.1)
        else:
            raise RuntimeError("guest probe did not reach its completion marker")
        program = api.json(prefix + "/program")
        if (program.get("program") or {}).get("execution_id") != execution_id:
            raise RuntimeError("another program replaced the active probe")
        frame = api.raw(prefix + "/frame.png")
        (args.out_dir / "frame.png").write_bytes(frame)
        report.update(
            execution_id=execution_id,
            frame_sha256=hashlib.sha256(frame).hexdigest(),
            program_state=(program.get("program") or {}).get("state"),
            program_transport="package" if not direct else "direct-source",
        )
        save(args.out_dir / "program-after.json", program)
    except Exception as error:
        report["error"] = str(error)
    finally:
        keep = bool(args.keep_session and (
            report["status"] == "EXECUTED" or args.keep_on_failure
        ))
        if keep:
            current = api.json(prefix)
            report["kept_running"] = current["state"] == "running"
            if not report["kept_running"]:
                report["status"] = "FAIL"
        else:
            try:
                bundle = api.raw(prefix + "/evidence")
                (args.out_dir / "evidence.zip").write_bytes(bundle)
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    if archive.testzip():
                        raise RuntimeError("evidence ZIP is corrupt")
                report["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
            except Exception as error:
                report["evidence_error"] = str(error)
                report["status"] = "FAIL"
            try:
                before = api.json(prefix)
                api.json(prefix + "?purge=0", "DELETE")
                deadline = time.monotonic() + 15
                while True:
                    after = api.json(prefix)
                    if after["state"] in {"stopped", "failed"} or time.monotonic() >= deadline:
                        break
                    time.sleep(.1)
                pid_gone = before.get("pid") is None or not process_identity(before["pid"])["exists"]
                history_preserved = after["firmware_sha256"] == identity["firmware_sha256"]
                report["cleanup"] = {
                    "terminal_state": after["state"],
                    "pid_gone": pid_gone,
                    "flash_released": not after.get("flash_retained"),
                    "history_preserved": history_preserved,
                }
                if after["state"] != "stopped" or not all(report["cleanup"].values()):
                    report["status"] = "FAIL"
            except Exception as error:
                report["cleanup_error"] = str(error)
                report["status"] = "FAIL"
        save(args.out_dir / "report.json", report)
    print(_json(report), flush=True)
    return 0 if report["status"] == "EXECUTED" else 1


def _json(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--device", choices=DEVICE_CHOICES, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--append-code", action="append")
    parser.add_argument("--done-marker", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--keep-session", action="store_true")
    parser.add_argument("--keep-on-failure", action="store_true")
    parser.add_argument("--out-dir", type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
