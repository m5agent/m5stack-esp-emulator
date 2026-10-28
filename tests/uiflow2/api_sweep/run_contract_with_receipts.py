#!/usr/bin/env python3
"""Run an existing live/network contract with artifact-bound lifecycle receipts."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import time
import zipfile

import run_live_contract
import run_network_contract
from run_device_api import Client, save
from run_guest import companion_cleanup, process_identity, runtime_executable


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def retained_serial_prefix(archived, history_text):
    """Keep CRLF unchanged when comparing archived bytes with API text."""
    return bool(archived) and history_text.startswith(archived.decode(errors="replace"))


class ReceiptClient(Client):
    """Observe only guests allocated by this invocation's production Client."""
    expected_runtime_sha256 = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owned = set()
        self.previews = {}
        self.receipts = {}
        self.receipt_errors = []

    def raw_call(self, method, path, **kwargs):
        record, body = super().call(method, path, **kwargs)
        require(record["status"] == 200, "receipt read failed: " + path)
        raw = (self.output / f"{self.index:04d}.response").read_bytes()
        return record, body, raw

    def observe(self, snapshot):
        sid = snapshot.get("session_id")
        if sid not in self.owned or snapshot.get("state") not in {"booting", "running"}:
            return
        pid = snapshot.get("pid")
        if type(pid) is not int or pid <= 0 or sid in self.receipts:
            return
        identity = process_identity(pid)
        executable = runtime_executable(pid)
        digest = sha(executable.read_bytes())
        require(identity["exists"] and digest == self.expected_runtime_sha256,
                "runtime identity/hash differs from the pinned contract lane")
        require(process_identity(pid) == identity, "runtime identity changed during initial hashing")
        self.receipts[sid] = {
            "session_id": sid, "device_id": snapshot["device_id"], "runtime": snapshot["runtime"],
            "profile": (snapshot.get("network") or {}).get("profile"),
            "firmware_sha256": snapshot["firmware_sha256"], "pid": pid,
            "process_identity": identity, "runtime_binary_sha256": digest,
            "runtime_executable_name": executable.name, "worker": snapshot.get("worker"),
            "evidence": [],
        }

    def verify_runtime(self, sid):
        row = self.receipts[sid]
        identity = process_identity(row["pid"])
        require(identity == row["process_identity"], "runtime PID/start identity changed")
        require(sha(runtime_executable(row["pid"]).read_bytes()) == row["runtime_binary_sha256"],
                "runtime executable changed during the contract")
        row["runtime_unchanged_before_stop"] = True

    def evidence(self, sid, raw, response_sha256):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(archive.testzip() is None, "receipt evidence ZIP is corrupt")
            manifest = json.loads(archive.read("manifest.json"))
            snapshot = manifest["session"]
            require(snapshot["session_id"] == sid and snapshot["state"] in {"running", "booting"},
                    "evidence is not from the owned active guest")
            self.observe(snapshot)
            row = self.receipts[sid]
            require(snapshot["firmware_sha256"] == row["firmware_sha256"] and snapshot["pid"] == row["pid"],
                    "ZIP changed the guest identity")
            self.verify_runtime(sid)
            sources = {name: sha(archive.read(name)) for name in archive.namelist()
                       if name.endswith(("source.json", "/files/main.py"))}
            serial = archive.read("serial.log")
            frame = archive.read("frames/current.png")
            require(frame.startswith(b"\x89PNG\r\n\x1a\n"), "ZIP frame is not PNG")
            row["evidence"].append({
                "sha256": sha(raw), "response_sha256": response_sha256, "before_stop": True,
                "session_state": snapshot["state"], "serial_sha256": sha(serial),
                "serial_bytes": len(serial), "frame_sha256": sha(frame), "sources_sha256": sources,
            })
            directory = self.output / "receipts" / sid
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "zip-serial.txt").write_text(serial.decode(errors="replace"))

    def prepare_stop(self, sid):
        _, before, _ = self.raw_call("GET", "/sessions/" + sid)
        self.observe(before)
        if before.get("state") in {"booting", "running"}:
            require(sid in self.receipts and self.receipts[sid]["evidence"],
                    "refusing receipt acceptance without pre-stop runtime/ZIP proof")
            self.verify_runtime(sid)
        _, worker, _ = self.raw_call("GET", "/worker")
        directory = self.output / "receipts" / sid
        directory.mkdir(parents=True, exist_ok=True)
        save(directory / "before-stop.json", before)
        save(directory / "worker-before-stop.json", worker)
        return before, worker

    def finish_stop(self, sid, before, worker_before):
        deadline = time.monotonic() + 20
        while True:
            _, stopped, _ = self.raw_call("GET", "/sessions/" + sid)
            if stopped["state"] in {"stopped", "failed"} or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        _, worker_after, _ = self.raw_call("GET", "/worker")
        same_worker = all(worker_before.get(key) == worker_after.get(key)
                          for key in ("worker_id", "instance_id", "generation", "pid"))
        row = self.receipts[sid]
        runtime_gone = not process_identity(row["pid"])["exists"]
        companions = companion_cleanup(before, stopped, runtime_pid_gone=runtime_gone,
                                       worker_identity=worker_after if same_worker else {})
        identity_fields = ("session_id", "device_id", "runtime", "firmware_id", "firmware_sha256")
        directory = self.output / "receipts" / sid
        save(directory / "stopped.json", stopped)
        save(directory / "worker-after-stop.json", worker_after)
        row["cleanup"] = {
            "terminal_state": stopped["state"], "runtime_pid_gone": runtime_gone,
            "history_preserved": all(before.get(key) == stopped.get(key) for key in identity_fields),
            "flash_retained_on_first_stop": stopped.get("flash_retained"), **companions,
        }

    def call(self, method, path, *args, **kwargs):
        stop_sid = None
        match = re.fullmatch(r"/sessions/([^/?]+)(?:\?.*)?", path)
        if method == "DELETE" and match and match[1] in self.owned:
            stop_sid = match[1]
        match = re.fullmatch(r"/previews/([^/]+)/close", path)
        if method == "POST" and match:
            stop_sid = self.previews.get(match[1])
        prepared = None
        if stop_sid:
            try:
                prepared = self.prepare_stop(stop_sid)
            except Exception as error:
                # A failed proof must fail acceptance, never prevent the
                # already-owned guest from receiving its stop/close request.
                self.receipt_errors.append(str(error))
        record, body = super().call(method, path, *args, **kwargs)
        if isinstance(body, dict):
            if method == "POST" and path == "/sessions" and record["status"] == 202:
                self.owned.add(body["session_id"])
            if path.startswith("/previews") and body.get("preview_id") and body.get("session_id"):
                self.previews[body["preview_id"]] = body["session_id"]
                self.owned.add(body["session_id"])
            try:
                self.observe(body)
            except Exception as error:
                self.receipt_errors.append(str(error))
        match = re.fullmatch(r"/sessions/([^/]+)/evidence", path)
        if method == "GET" and match and match[1] in self.owned and record["status"] == 200:
            raw = (self.output / f"{self.index:04d}.response").read_bytes()
            try:
                self.evidence(match[1], raw, record["response_sha256"])
            except Exception as error:
                self.receipt_errors.append(str(error))
        if prepared and record["status"] in {200, 202}:
            try:
                self.finish_stop(stop_sid, *prepared)
            except Exception as error:
                self.receipt_errors.append(str(error))
        return record, body

    def finalize_history(self):
        for sid in sorted(self.owned):
            require(sid in self.receipts and "cleanup" in self.receipts[sid], "owned session lacks stop receipt")
            row = self.receipts[sid]
            _, history, _ = self.raw_call("GET", "/sessions/" + sid)
            require(history["state"] == "stopped", "contract guest did not stop cleanly")
            if history.get("flash_retained"):
                record, history = super().call("DELETE", "/sessions/" + sid + "?purge=0&retain_flash=0")
                require(record["status"] == 200, "retained Flash release failed")
            _, history, _ = self.raw_call("GET", "/sessions/" + sid)
            _, _, frame = self.raw_call("GET", "/sessions/" + sid + "/frame.png")
            _, _, repeated = self.raw_call("GET", "/sessions/" + sid + "/frame.png")
            serial_text, offset = "", 0
            for _ in range(128):
                _, page, _ = self.raw_call("GET", f"/sessions/{sid}/serial?offset={offset}&limit=262144")
                serial_text += page["data"]
                require(page["next_offset"] >= offset, "history serial cursor moved backwards")
                if not page["bytes"]:
                    break
                require(page["next_offset"] > offset, "history serial cursor did not advance")
                offset = page["next_offset"]
            else:
                raise RuntimeError("history serial exceeds receipt bound")
            directory = self.output / "receipts" / sid
            save(directory / "history.json", history)
            (directory / "history-frame.png").write_bytes(frame)
            (directory / "history-serial.txt").write_text(serial_text)
            archived = (directory / "zip-serial.txt").read_bytes()
            row["cleanup"].update(
                flash_released=history.get("flash_retained") is False,
                history_frame_frozen=frame.startswith(b"\x89PNG\r\n\x1a\n") and frame == repeated,
                history_serial_retained=retained_serial_prefix(archived, serial_text),
                history_frame_sha256=sha(frame), history_serial_sha256=sha(serial_text.encode()),
            )
            cleanup = row["cleanup"]
            row["status"] = "PASS" if row["evidence"] and row.get("runtime_unchanged_before_stop") and all(
                cleanup.get(key) is True for key in ("runtime_pid_gone", "history_preserved", "flash_released",
                    "companions_cleanup_complete", "history_frame_frozen", "history_serial_retained")
            ) else "FAIL"


def run(args):
    module = run_live_contract if args.contract == "live" else run_network_contract
    if not args.execute:
        return module.run(args)
    require(re.fullmatch(r"[0-9a-f]{64}", args.expected_runtime_sha256 or ""), "pin the exact runtime SHA256")
    clients = []

    class PinnedClient(ReceiptClient):
        expected_runtime_sha256 = args.expected_runtime_sha256

        def __init__(self, *values, **options):
            super().__init__(*values, **options)
            clients.append(self)

    original_client = module.Client
    module.Client = PinnedClient
    error = None
    try:
        module.run(args)
    except Exception as failure:
        error = str(failure)
    finally:
        module.Client = original_client
    report_path = args.out_dir / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {"status": "FAIL", "cases": []}
    try:
        for client in clients:
            client.finalize_history()
            if client.receipt_errors:
                error = error or "; ".join(client.receipt_errors)
    except Exception as failure:
        error = error or str(failure)
    combined = dict(report)
    combined.update(original_report_sha256=sha(report_path.read_bytes()) if report_path.exists() else None,
                    runner_sha256=sha(Path(module.__file__).read_bytes()),
                    receipt_runner_sha256=sha(Path(__file__).read_bytes()),
                    expected_runtime_sha256=args.expected_runtime_sha256,
                    session_receipts=[row for client in clients for row in client.receipts.values()])
    source = args.out_dir / "files/main.py"
    if source.exists():
        combined["effective_guest_source_sha256"] = sha(source.read_bytes())
    combined["status"] = "PASS" if report["status"] == "PASS" and not error and combined["session_receipts"] and all(
        row.get("status") == "PASS" for row in combined["session_receipts"]
    ) else "FAIL"
    if error:
        combined["receipt_error"] = error
    save(args.out_dir / "report-with-receipts.json", combined)
    print(json.dumps({"status": combined["status"], "contract": args.contract,
                      "sessions": len(combined["session_receipts"]), "error": error}), flush=True)
    return 0 if combined["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", choices=("live", "network"), required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--expected-runtime-sha256")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--execute", action="store_true")
    raise SystemExit(run(parser.parse_args()))
