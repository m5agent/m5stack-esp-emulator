#!/usr/bin/env python3
"""Same-guest UIFlow2 source replacement through visible Device Service APIs.

Admitted S3 hosts: initialize UART routing once, then run and replace main.py in
RAM. No direct QEMU launch, host execution of submitted code or physical I/O.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/units"))
from run_host_cases import runtime_provenance
from run_service_cases import Client

BOOT = '''from machine import UART
import os
_repl_uart = UART(0, baudrate=115200, timeout=0, timeout_char=0)
os.dupterm(_repl_uart, 0)
_repl_uart.irq(handler=os.dupterm_notify, trigger=UART.IRQ_RX)
_uiflow_run_main = False
print("M5EMU_UART_REPL_READY")
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class ProbeClient(Client):
    def __init__(self, url, output):
        super().__init__(url)
        self.output = output
        self.requests = []

    def raw(self, path, method="GET", payload=None, **kwargs):
        index = len(self.requests)
        started = time.monotonic()
        row = {"path": path, "method": method}
        self.requests.append(row)
        if payload is not None:
            save(self.output / f"{index:04d}.request.json", payload)
        try:
            data = super().raw(path, method, payload, **kwargs)
            (self.output / f"{index:04d}.response").write_bytes(data)
            return data
        finally:
            row["elapsed_seconds"] = time.monotonic() - started
            save(self.output / "http.json", self.requests)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def poll(function, predicate, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = function()
        if predicate(result):
            return result
        time.sleep(.05)
    raise RuntimeError("observation deadline exceeded")


def program_source(nonce, version, color, pins, unit="pir"):
    if unit == "relay":
        initialize = f"from unit import RelayUnit\nunit = RelayUnit(({pins['white']}, {pins['yellow']}))\nunit.set_status({version == 'B'})"
        sample = "int(unit.get_status())"
    else:
        initialize = f"from unit import PIRUnit\nunit = PIRUnit(({pins['white']}, {pins['yellow']}))"
        sample = "int(unit.get_status())"
    return f'''import sys
import time
import M5
assert {'/m5-live-' + nonce!r} in sys.path, "MicroPython VM was reset"
M5.begin()
screen = M5.Display
screen.setBrightness(255)
screen.fillScreen({color})
screen.setTextSize(2)
screen.setTextColor(0, {color})
{initialize}
print("LIVE_{version}_READY")
previous = None
while True:
 M5.update()
 value = {sample}
 if value != previous:
  print("LIVE_{version}_{unit.upper()}", value)
  screen.fillRect(0, 0, 128, 80, {color})
  screen.setCursor(4, 4)
  screen.print("RUN {version}")
  screen.setCursor(4, 32)
  screen.print("{unit.upper()} " + str(value))
  previous = value
 time.sleep_ms(25)
'''


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    client = ProbeClient(args.api, args.out_dir)
    session_id = None
    report = {"validation": "virtual-device validation", "hardware_validation": "NOT RUN", "status": "FAIL"}
    try:
        inventory = client.json(f"units?device_id={args.device}")
        host = next(row for row in inventory["hosts"] if row["device_id"] == args.device)
        port = next(row for row in host["ports"] if row.get("visual_port") == "grove")
        payload = {"device_id": args.device, "runtime": "qemu", "ttl_seconds": 300,
                   "ready_timeout_seconds": 30,
                   "units": [{"id": "external1", "unit_id": args.unit, "port_id": port["id"]}]}
        if args.manual_bootstrap:
            firmware = client.json("firmware/uiflow", "POST", {
                "device_id": args.device, "files": {"boot.py": BOOT, "main.py": "pass\n"},
            })
            payload.update(firmware_id=firmware["firmware_id"],
                           uiflow_source_sha256=firmware["source"]["metadata"]["source_sha256"],
                           program_transport="uart-repl", ready_marker="M5EMU_UART_REPL_READY")
        else:
            payload["program_mode"] = "uiflow-live"
        created = client.json("sessions", "POST", payload)
        session_id = created["session_id"]
        pins = next(row["pins"] for row in created["units"] if row["id"] == "external1")
        firmware = client.json(f"firmware/{created['firmware_id']}")
        save(args.out_dir / "firmware.json", firmware)
        prefix = f"sessions/{session_id}"
        ready = poll(lambda: client.json(prefix), lambda r: r["state"] in {"running", "failed", "stopped"}, 90)
        require(ready["state"] == "running", str(ready.get("error")))
        report.update(session_id=session_id, device_id=args.device, unit_id=args.unit, pins=pins,
                      bootstrap="manual" if args.manual_bootstrap else "program_mode=uiflow-live",
                      runtime="qemu", firmware_sha256=ready["firmware_sha256"], pid=ready["pid"])
        report["runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        if args.unit == "pir":
            client.json(prefix + "/unit-input", "POST", {"id": "external1", "values": {"motion": False}})
        expected = None
        nonce = uuid.uuid4().hex
        serial_start = client.json(prefix + "/serial?limit=1048576")["data"]
        executions = []

        def submit(source, name):
            nonlocal expected
            start = time.monotonic()
            result = client.json(prefix + "/program", "POST", {
                "source": source, "expected_execution_id": expected, "timeout_seconds": 15,
            })
            expected = result["program"]["execution_id"]
            result["request_seconds"] = time.monotonic() - start
            save(args.out_dir / f"program-{name}.json", result)
            executions.append(result)
            require(result["program"]["pid"] == ready["pid"], "guest process changed")
            require(result["program"]["firmware_sha256"] == ready["firmware_sha256"], "firmware changed")
            return result["program"]

        def serial_marker(marker):
            def observed(row):
                if f"__M5_EXEC_{expected}__:ERROR" in row["data"]:
                    raise RuntimeError("guest execution failed: " + row["data"][-1200:])
                return marker in row["data"]
            return poll(lambda: client.json(prefix + "/serial?limit=1048576"), observed)

        finite = submit(f"import sys\nsys.path.append({'/m5-live-' + nonce!r})\nprint('LIVE_FINITE_DONE')\n", "finite")
        require(poll(lambda: client.json(prefix + "/program"), lambda r: r["program"]["state"] == "completed")["program"]["execution_id"] == finite["execution_id"], "finite execution identity differs")
        a = submit(program_source(nonce, "A", 0xFFFFFF, pins, args.unit), "a")
        serial_marker("LIVE_A_READY")
        frame_hashes = []
        serial_marker(f"LIVE_A_{args.unit.upper()} 0")
        if args.unit == "pir":
            for index, value in enumerate((True, False, True)):
                before = client.json(prefix + "/serial?limit=1048576")["next_offset"]
                client.json(prefix + "/unit-input", "POST", {"id": "external1", "values": {"motion": value}})
                poll(lambda: client.json(prefix + f"/serial?offset={before}"), lambda r: f"LIVE_A_PIR {int(value)}" in r["data"])
                save(args.out_dir / f"units-a-{index}.json", client.json(prefix + "/units"))
        else:
            state_a = client.json(prefix + "/units")
            require(state_a["units"][0]["properties"]["output-level"] is False, "relay guest OFF did not reach controller")
            save(args.out_dir / "units-a.json", state_a)
        frame_a = client.raw(prefix + "/frame.png")
        (args.out_dir / "frame-a.png").write_bytes(frame_a)
        frame_hashes.append(hashlib.sha256(frame_a).hexdigest())
        b = submit(program_source(nonce, "B", 0x88FF88, pins, args.unit), "b")
        serial_marker("LIVE_B_READY")
        if args.unit == "relay":
            serial_marker("LIVE_B_RELAY 1")
            state_b = client.json(prefix + "/units")
            require(state_b["units"][0]["properties"]["output-level"] is True, "relay guest ON did not reach controller")
            save(args.out_dir / "units-b.json", state_b)
        frame_b = client.raw(prefix + "/frame.png")
        (args.out_dir / "frame-b.png").write_bytes(frame_b)
        frame_hashes.append(hashlib.sha256(frame_b).hexdigest())
        require(frame_hashes[0] != frame_hashes[1], "new source did not change the guest frame")
        syntax = submit("def broken(:\n", "syntax-error")
        require(syntax["state"] == "failed", "syntax error was not reported as failed")
        recovery = submit(f"import sys\nassert {'/m5-live-' + nonce!r} in sys.path\nprint('LIVE_RECOVERED')\n", "recovery")
        serial = serial_marker("LIVE_RECOVERED")["data"]
        require(serial.count("ESP-ROM:") == serial_start.count("ESP-ROM:"), "guest reboot detected")
        require(serial.count("M5EMU_UART_REPL_READY") == 1, "bootstrap restarted")
        current = client.json(prefix)
        require(current["pid"] == ready["pid"] and current["state"] == "running", "same guest no longer running")
        bundle = client.raw(prefix + "/evidence")
        (args.out_dir / "evidence.zip").write_bytes(bundle)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            require(archive.testzip() is None, "evidence ZIP is corrupt")
            for execution in executions:
                p = execution["program"]
                history = json.loads(archive.read(f"programs/{p['execution_id']}.json"))
                require(history["revision_id"] == p["revision_id"], "execution/revision mismatch")
                require(f"programs/{p['revision_id']}/source.json" in archive.namelist(), "revision source is missing")
                if p["execution_id"] in {a["execution_id"], b["execution_id"]}:
                    require(history["state"] == "interrupted" and history["interruption_confirmed"], "previous loop interruption unconfirmed")
        report.update(status="PASS", executions=executions, frame_sha256=frame_hashes,
                      checks={"same_process": True, "same_firmware": True, "vm_nonce_preserved": True,
                              "no_reboot_banner": True, f"{args.unit}_guest_readback": True, "different_guest_frames": True,
                              "infinite_loop_replaced": True, "syntax_error_recovered": True,
                              "revision_sources_in_evidence": True})
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if session_id:
            try:
                if not (args.out_dir / "evidence.zip").exists():
                    (args.out_dir / "failure-evidence.zip").write_bytes(client.raw(f"sessions/{session_id}/evidence"))
            except Exception as error:
                report.update(status="FAIL", evidence_error=str(error))
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", "DELETE")
                if stopped["state"] not in {"stopped", "failed"}:
                    stopped = poll(lambda: client.json(f"sessions/{session_id}"),
                                   lambda row: row["state"] in {"stopped", "failed"}, 40)
                save(args.out_dir / "stopped.json", stopped)
                require(stopped["state"] == "stopped" and not stopped["flash_retained"], "session cleanup was not confirmed")
            except Exception as error:
                report.update(status="FAIL", cleanup_error=str(error))
        save(args.out_dir / "report.json", report)
    require(report["status"] == "PASS", report.get("cleanup_error") or report.get("evidence_error") or "validation failed")
    print(json.dumps({"status": report["status"], "session_id": session_id, "runs": len(report["executions"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--device", choices=("cores3", "atoms3r", "sticks3", "stopwatch"), default="atoms3r")
    parser.add_argument("--unit", choices=("pir", "relay"), default="pir")
    parser.add_argument("--manual-bootstrap", action="store_true")
    run(parser.parse_args())
