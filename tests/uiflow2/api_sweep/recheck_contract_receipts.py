#!/usr/bin/env python3
"""Recheck retained contract bytes after the CRLF receipt-comparison correction."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import zipfile

from run_contract_with_receipts import require, retained_serial_prefix, sha
from run_guest import companion_cleanup, process_identity


def recheck(path):
    root = path.parent
    original_bytes = path.read_bytes()
    original = json.loads(original_bytes)
    functional_report = json.loads((root / "report.json").read_text())
    require(sha((root / "report.json").read_bytes()) == original["original_report_sha256"],
            "functional report bytes changed")
    require(functional_report["status"] == "PASS" and not original.get("receipt_error"),
            "recheck cannot replace an original functional/provenance failure")
    report = copy.deepcopy(original)
    archives = {sha(p.read_bytes()): p for p in root.glob("*.zip")}
    for row in report["session_receipts"]:
        require(all(row["cleanup"].get(key) is True for key in (
            "runtime_pid_gone", "history_preserved", "flash_released",
            "companions_cleanup_complete", "history_frame_frozen")),
            "CRLF recheck cannot replace another original lifecycle failure")
        sid = row["session_id"]
        directory = root / "receipts" / sid
        read = lambda name: json.loads((directory / name).read_text())
        before, stopped, history = (read(name) for name in ("before-stop.json", "stopped.json", "history.json"))
        worker_before, worker_after = (read(name) for name in ("worker-before-stop.json", "worker-after-stop.json"))
        require(all(worker_before.get(k) == worker_after.get(k)
                    for k in ("worker_id", "instance_id", "generation", "pid")), "worker identity changed")
        require(row["runtime_binary_sha256"] == report["expected_runtime_sha256"]
                and row.get("runtime_unchanged_before_stop") is True, "runtime hash/drift gate failed")
        history_serial = (directory / "history-serial.txt").read_bytes()
        require(sha(history_serial) == row["cleanup"]["history_serial_sha256"], "history serial bytes changed")
        for evidence in row["evidence"]:
            require(evidence["sha256"] in archives and evidence["before_stop"], "pre-stop ZIP missing")
            with zipfile.ZipFile(archives[evidence["sha256"]]) as archive:
                require(archive.testzip() is None, "corrupt ZIP")
                snapshot = json.loads(archive.read("manifest.json"))["session"]
                require(snapshot["session_id"] == sid and snapshot["pid"] == row["pid"]
                        and snapshot["firmware_sha256"] == row["firmware_sha256"], "ZIP identity mismatch")
                serial = archive.read("serial.log")
                require(sha(serial) == evidence["serial_sha256"], "archived serial changed")
                require(retained_serial_prefix(serial, history_serial.decode(errors="replace")),
                        "history does not retain exact ZIP serial prefix")
                require(sha(archive.read("frames/current.png")) == evidence["frame_sha256"], "ZIP frame changed")
                require(all(sha(archive.read(name)) == digest for name, digest in evidence["sources_sha256"].items()),
                        "archived program source changed")
        frame = (directory / "history-frame.png").read_bytes()
        require(sha(frame) == row["cleanup"]["history_frame_sha256"], "history frame changed")
        frame_responses = []
        for request in sorted(root.glob("*.request.json")):
            request_row = json.loads(request.read_text())
            if request_row["method"] == "GET" and request_row["path"] == f"/sessions/{sid}/frame.png":
                response = request.with_name(request.name.replace(".request.json", ".response"))
                require(sha(response.read_bytes()) == request_row["response_sha256"], "frame response changed")
                frame_responses.append(response.read_bytes())
        require(len(frame_responses) >= 2 and frame_responses[-1] == frame_responses[-2] == frame,
                "two exact stopped-history frame responses missing")
        runtime_gone = not process_identity(row["pid"])["exists"]
        companions = companion_cleanup(before, stopped, runtime_pid_gone=runtime_gone, worker_identity=worker_after)
        row["cleanup"].update(companions, runtime_pid_gone=runtime_gone, history_serial_retained=True)
        require(history["state"] == "stopped" and history.get("flash_retained") is False, "Flash/history gate failed")
        require(all(row["cleanup"].get(key) is True for key in (
            "runtime_pid_gone", "history_preserved", "flash_released", "companions_cleanup_complete",
            "history_frame_frozen", "history_serial_retained")), "lifecycle gate failed")
        row["status"] = "PASS"
    report.update(status="PASS", original_receipt_status=original["status"],
                  original_receipt_report_sha256=sha(original_bytes),
                  receipt_recheck_source_sha256=sha(Path(__file__).read_bytes()),
                  receipt_recheck_reason="Only serial-prefix comparison changed: preserve CRLF from original ZIP/history bytes.")
    require(path.read_bytes() == original_bytes, "original receipt report changed during recheck")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(args.report.resolve() != args.out.resolve() and not args.out.exists(), "use a fresh independent output")
    result = recheck(args.report)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "sessions": len(result["session_receipts"]),
                      "original_receipt_status": result["original_receipt_status"]}))
