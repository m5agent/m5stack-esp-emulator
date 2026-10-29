#!/usr/bin/env python3
"""Exercise the original UIFlow2 FlashLightUnit on admitted S3 QEMU hosts."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "platform/tools"))
from run_host_cases import runtime_provenance  # noqa: E402
from run_service_cases import Client  # noqa: E402

HOSTS = ("cores3", "atoms3r", "sticks3", "stopwatch")


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require(value, message):
    if not value:
        raise RuntimeError(message)


def poll(function, predicate, timeout=40):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = function()
        if predicate(latest):
            return latest
        time.sleep(0.1)
    raise RuntimeError(f"observation deadline exceeded: {latest}")


def source(phase, pins):
    action = {
        "construct": "",
        "flash": "flash.flash(FlashLightUnit.BRIGHTNESS_100, FlashLightUnit.TIME_220MS, False)\nprint('FLASHLIGHT_PULSED')",
        "off": "flash.flash(0, FlashLightUnit.TIME_220MS, True)\nprint('FLASHLIGHT_OFF')",
    }[phase]
    return f'''import time
import M5
M5.begin()
M5.Display.fillScreen(0)
from unit import FlashLightUnit
print("FLASHLIGHT_CONSTRUCTING")
flash = FlashLightUnit(({pins["white"]}, {pins["yellow"]}))
print("FLASHLIGHT_CONSTRUCTOR_LOW")
{action}
while True:
    M5.update()
    time.sleep_ms(50)
'''


def run_host(client, args, device):
    output = args.out_dir / device
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "validation": "virtual-device validation",
        "hardware": "NOT RUN",
        "device_id": device,
        "unit_id": "flashlight",
        "status": "FAIL",
        "checks": {},
    }
    session_id = None
    try:
        inventory = client.json(f"units?device_id={device}")
        host = next(row for row in inventory["hosts"] if row["device_id"] == device)
        port = next(
            row for row in host["ports"]
            if row.get("visual_port") == "grove" and row.get("wiring_status") == "confirmed"
        )
        created = client.json("sessions", "POST", {
            "device_id": device,
            "runtime": "qemu",
            "ttl_seconds": 600,
            "ready_timeout_seconds": 120,
            "program_mode": "uiflow-live",
            "units": [{
                "id": "flashlight",
                "unit_id": "flashlight",
                "port_id": port["id"],
                "initial": {"flash-mode": True},
            }],
        })
        session_id = report["session_id"] = created["session_id"]
        pins = next(row["pins"] for row in created["units"] if row["id"] == "flashlight")
        prefix = f"sessions/{session_id}"
        ready = poll(
            lambda: client.json(prefix),
            lambda row: row["state"] in {"running", "failed", "stopped"},
            120,
        )
        require(ready["state"] == "running", str(ready.get("error")))
        report.update(
            port_id=port["id"],
            pins=pins,
            firmware_sha256=ready["firmware_sha256"],
            pid=ready["pid"],
        )
        if args.expected_runtime_sha256:
            report["runtime_provenance"] = runtime_provenance(
                client, session_id, args.expected_runtime_sha256
            )
        serial_start = client.json(prefix + "/serial?limit=1048576")["data"]
        expected = None
        executions = []

        def submit(phase):
            nonlocal expected
            result = client.json(prefix + "/program", "POST", {
                "source": source(phase, pins),
                "expected_execution_id": expected,
                "timeout_seconds": 15,
            })
            execution = result["program"]
            expected = execution["execution_id"]
            executions.append(execution)
            save(output / f"program-{phase}.json", result)
            return execution

        def serial_marker(marker):
            def matches(row):
                text = row["data"]
                if f"__M5_EXEC_{expected}__:ERROR" in text:
                    raise RuntimeError(text[-1200:])
                return marker in text
            return poll(lambda: client.json(prefix + "/serial?limit=1048576"), matches)

        construct = submit("construct")
        serial_marker("FLASHLIGHT_CONSTRUCTOR_LOW")

        def initial_known():
            row = client.json(prefix + "/units")["units"][0]["properties"]
            return row if (
                row["en-level"] is False
                and row["gpio-route-supported"] is True
                and row["pad-synchronized"] is True
                and row["output-known"] is True
            ) else None

        initial = poll(initial_known, bool)
        report["initial"] = initial
        report["checks"]["cold_constructor_low_is_known"] = True

        flash = submit("flash")
        serial_marker("FLASHLIGHT_PULSED")

        def pulse_observed():
            row = client.json(prefix + "/units")["units"][0]["properties"]
            return row if (
                row["last-program-count"] == 1
                and row["decoded-programs"] >= 1
                and row["flash-level-pct"] == 100
                and row["timeout-ms"] == 220
                and row["output-known"] is True
            ) else None

        pulse = poll(pulse_observed, bool)
        report["after_flash"] = pulse
        report["checks"]["original_flash_api_decoded_100pct_220ms"] = True

        off = submit("off")
        serial_marker("FLASHLIGHT_OFF")

        def low_ready():
            row = client.json(prefix + "/units")["units"][0]["properties"]
            return row if (
                row["en-level"] is False
                and row["output-known"] is True
                and row["pad-synchronized"] is True
            ) else None

        after_off = poll(low_ready, bool)
        report["after_off"] = after_off
        report["checks"]["rerun_restores_long_low_baseline"] = True

        require(flash["pid"] == construct["pid"] == off["pid"] == ready["pid"], "guest process changed")
        serial = client.json(prefix + "/serial?limit=1048576")["data"]
        require(serial.count("ESP-ROM:") == serial_start.count("ESP-ROM:"), "guest reboot detected")
        report["checks"]["same_guest_replacement"] = True
        report["executions"] = executions

        bundle = client.raw(prefix + "/evidence")
        (output / "evidence.zip").write_bytes(bundle)
        report["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            require(archive.testzip() is None, "evidence ZIP is corrupt")
        report["checks"]["evidence_before_stop"] = True
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if session_id:
            try:
                serial = client.json(f"sessions/{session_id}/serial?limit=1048576")["data"]
                (output / "serial.txt").write_text(serial, encoding="utf-8")
            except Exception as error:
                report["serial_error"] = str(error)
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", "DELETE")
                report["stopped"] = stopped
            except Exception as error:
                report["stop_error"] = str(error)
        save(output / "result.json", report)
    print(json.dumps({
        "device": device,
        "status": report["status"],
        "error": report.get("error"),
        "result": str(output / "result.json"),
    }, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device", choices=(*HOSTS, "all"), default="all")
    parser.add_argument("--expected-runtime-sha256")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    client = Client(args.api)
    devices = HOSTS if args.device == "all" else (args.device,)
    results = [run_host(client, args, device) for device in devices]
    save(args.out_dir / "aggregate.json", {"results": results})
    return 0 if all(row["status"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
