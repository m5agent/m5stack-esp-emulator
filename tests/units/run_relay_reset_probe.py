#!/usr/bin/env python3
"""Verify Relay and Relay2 output transitions across one QEMU hard reset.

Preparation is offline. ``--execute`` uses the visible Device Service on
127.0.0.1:8787, requests evidence before stopping with purge=0, and labels the
result as virtual-device validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from run_service_cases import Client, build_image  # noqa: E402

MARKER = "RELAY2_RESET "

BOOT = r'''_uiflow_run_main = True
import os
import time
from hardware import UART
from machine import Pin

_console = UART(0, baudrate=115200, tx=43, rx=44)


def emit(*parts):
    _console.write(" ".join(str(part) for part in parts) + "\n")


white = Pin(__WHITE__, Pin.OUT)
yellow = Pin(__YELLOW__, Pin.OUT)
seen = False
try:
    os.stat("relay2_reset_seen")
    seen = True
except OSError:
    pass

if not seen:
    white.value(1)
    yellow.value(1)
    with open("relay2_reset_seen", "w") as stream:
        stream.write("1")
        stream.flush()
    try:
        os.sync()
    except OSError:
        pass
    emit("RELAY2_RESET FIRST_BOTH_HIGH 1 1")
else:
    white.value(0)
    yellow.value(0)
    emit("RELAY2_RESET SECOND_READY 0 0")
    time.sleep_ms(10000)
    white.value(1)
    emit("RELAY2_RESET SECOND_WHITE_HIGH 1 0")
    time.sleep_ms(30000)
    yellow.value(1)
    emit("RELAY2_RESET SECOND_YELLOW_HIGH 1 1")

emit("RELAY2_RESET_READY")
'''

MAIN = r'''import M5
import time

M5.begin()
screen = M5.Display
screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0)
screen.setTextColor(0xFFFFFF, 0)
screen.setCursor(8, 8)
screen.print("Relay2 hard-reset boundary")
while True:
    M5.update()
    time.sleep_ms(200)
'''


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(args) -> tuple[Path, Path, dict, str]:
    output = args.out_dir.resolve()
    files = output / "files"
    files.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device = next(row for row in matrix["devices"] if row["id"] == args.device)
    hosts = json.loads((ROOT / "platform/units/host-ports.json").read_text())["hosts"]
    host = next(row for row in hosts if row["device_id"] == args.device)
    port = next(
        row for row in host["ports"]
        if row.get("visual_port") == "grove" and row.get("wiring_status") == "confirmed"
    )
    white = port["pins"]["white"]
    yellow = port["pins"]["yellow"]
    boot = BOOT.replace("__WHITE__", str(white)).replace("__YELLOW__", str(yellow))
    (files / "boot.py").write_text(boot, encoding="utf-8")
    (files / "main.py").write_text(MAIN, encoding="utf-8")
    base = args.base.resolve() if args.base else ROOT / device["base"]
    image = build_image(SimpleNamespace(
        base=base,
        flash_size=int(device["flash_size"], 0),
        files_dir=files,
        mklittlefs=None,
        preserve_vfs=False,
        vfs_offset=int(device["vfs_offset"], 0),
        vfs_size=int(device["vfs_size"], 0),
        prog_size=32,
        out_dir=output,
    ))
    result = {
        "schema_version": 1,
        "date": datetime.now(timezone.utc).astimezone().isoformat(),
        "validation": "virtual-device validation",
        "category": "unit-hard-reset-output-boundary",
        "device_id": args.device,
        "unit_id": args.unit,
        "port_id": port["id"],
        "pins": {"white": white, "yellow": yellow},
        "base_firmware_sha256": digest(base.read_bytes()),
        "firmware_sha256": digest(image.read_bytes()),
        "files_sha256": {
            path.name: digest(path.read_bytes()) for path in sorted(files.glob("*.py"))
        },
        **({"qemu_sha256": digest(Path(args.qemu).read_bytes())} if args.qemu else {}),
        "checks": {},
        "markers": [],
    }
    (output / "prepared.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output, image, result, port["id"]


def serial(client: Client, session_id: str) -> str:
    return client.json(f"sessions/{session_id}/serial?limit=262144").get("data", "")


def wait_marker(client: Client, session_id: str, marker: str, *,
                offset: int = 0, timeout: float = 60) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = client.json(f"sessions/{session_id}")
        if session["state"] in {"failed", "stopped"}:
            raise RuntimeError(session.get("error") or "guest ended")
        text = serial(client, session_id)
        if marker in text[offset:]:
            return text
        for failure in ("Traceback (most recent call last)", "Guru Meditation",
                        "A fatal error occurred", "Rebooting..."):
            if failure in text[offset:]:
                raise RuntimeError("guest failure while waiting for " + marker)
        time.sleep(0.2)
    raise RuntimeError("timed out waiting for guest marker: " + marker)


def relay_state(client: Client, session_id: str, unit_id: str) -> tuple[dict, dict]:
    snapshot = client.json(f"sessions/{session_id}/units")
    relay = next(unit for unit in snapshot["units"] if unit["id"] == "relay2")
    if not relay.get("available") or relay.get("source") != "guest-qom":
        raise RuntimeError(f"{unit_id} QOM state is unavailable")
    return relay, snapshot


def wait_state(client: Client, session_id: str, unit_id: str,
               expected_levels: tuple[bool, bool],
               expected_counts: tuple[int, int], timeout: float = 15,
               minimum_counts: bool = False) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        relay, _ = relay_state(client, session_id, unit_id)
        latest = relay["properties"]
        if unit_id == "relay":
            count_matches = (
                latest["output-transitions"] >= expected_counts[1]
                if minimum_counts
                else latest["output-transitions"] == expected_counts[1]
            )
            matches = (
                latest["output-level"] == expected_levels[1]
                and count_matches
            )
        else:
            actual_counts = (
                latest["output-1-transitions"],
                latest["output-2-transitions"],
            )
            matches = (
                (latest["output-1-level"], latest["output-2-level"])
                == expected_levels
                and (
                    all(a >= b for a, b in zip(actual_counts, expected_counts))
                    if minimum_counts
                    else actual_counts == expected_counts
                )
            )
        if matches:
            return latest
        time.sleep(0.2)
    raise RuntimeError(f"{unit_id} state mismatch: {latest}")


def wait_level(client: Client, session_id: str, unit_id: str,
               expected_levels: tuple[bool, bool], timeout: float = 15) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        relay, _ = relay_state(client, session_id, unit_id)
        latest = relay["properties"]
        matches = (
            latest["output-level"] == expected_levels[1]
            if unit_id == "relay"
            else (
                latest["output-1-level"], latest["output-2-level"]
            ) == expected_levels
        )
        if matches:
            return latest
        time.sleep(0.2)
    raise RuntimeError(f"{unit_id} level mismatch: {latest}")


def execute(args) -> int:
    output, image, result, port_id = prepare(args)
    if not args.execute:
        print(json.dumps({"status": "PREPARED", "result": str(output / "prepared.json")}))
        return 0
    client = Client(args.api_url)
    session_id = None
    result["status"] = "FAIL"
    try:
        artifact = client.json(
            "artifacts",
            method="POST",
            body=image.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": "cores3-relay2-hard-reset.bin",
            },
        )
        firmware = client.json("firmware", method="POST", payload={
            "device_id": args.device,
            "kind": "merged",
            "artifact_id": artifact["artifact_id"],
        })
        session = client.json("sessions", method="POST", payload={
            "device_id": args.device,
            "firmware_id": firmware["firmware_id"],
            "runtime": "qemu",
            "ttl_seconds": 600,
            "ready_marker": "RELAY2_RESET_READY",
            "ready_timeout_seconds": 180,
            "units": [{"id": "relay2", "unit_id": args.unit, "port_id": port_id}],
        })
        session_id = result["session_id"] = session["session_id"]
        text = wait_marker(
            client, session_id, "RELAY2_RESET FIRST_BOTH_HIGH", timeout=180
        )
        result["markers"].append("FIRST_BOTH_HIGH")
        first = wait_state(
            client, session_id, args.unit, (True, True), (1, 1),
            minimum_counts=True,
        )
        result["first_boot"] = first
        result["checks"]["guest_transitions_reach_both_qom_channels"] = True

        offset = len(text)
        reset = client.json(f"sessions/{session_id}/reset", method="POST", payload={})
        result["reset_response"] = reset
        immediate, _ = relay_state(client, session_id, args.unit)
        result["immediately_after_reset"] = immediate["properties"]
        text = wait_marker(
            client, session_id, "RELAY2_RESET SECOND_READY", offset=offset, timeout=180
        )
        result["markers"].append("SECOND_READY")
        if args.unit == "relay":
            after_reset = wait_level(
                client, session_id, args.unit, (False, False), timeout=5
            )
            baseline = after_reset["output-transitions"]
            result["post_reset_transition_baseline"] = baseline
            reset_clean = result["immediately_after_reset"]["output-transitions"] == 0
        else:
            after_reset = wait_state(
                client, session_id, args.unit, (False, False), (0, 0), timeout=5
            )
            baseline = 0
            reset_clean = (
                result["immediately_after_reset"]["output-transitions"] == 0
                and after_reset["output-transitions"] == 0
            )
        result["after_reset"] = after_reset
        if not reset_clean:
            raise RuntimeError("hard reset did not clear the Unit transition state")
        result["checks"]["hard_reset_rebases_outputs_without_counting_edge"] = True

        offset = len(text)
        text = wait_marker(
            client, session_id, "RELAY2_RESET SECOND_WHITE_HIGH",
            offset=offset, timeout=60,
        )
        result["markers"].append("SECOND_WHITE_HIGH")
        if args.unit == "relay":
            white = wait_level(client, session_id, args.unit, (True, False))
            if white["output-transitions"] != baseline:
                raise RuntimeError("white Rail made a transition on single Relay yellow input")
        else:
            white = wait_state(client, session_id, args.unit, (True, False), (1, 0))
        result["second_white"] = white
        result["checks"]["independent_white_transition_after_reset"] = True

        offset = len(text)
        wait_marker(
            client, session_id, "RELAY2_RESET SECOND_YELLOW_HIGH",
            offset=offset, timeout=60,
        )
        result["markers"].append("SECOND_YELLOW_HIGH")
        if args.unit == "relay":
            yellow = wait_state(
                client, session_id, args.unit, (True, True),
                (baseline + 1, baseline + 1),
            )
        else:
            yellow = wait_state(client, session_id, args.unit, (True, True), (1, 1))
        result["second_yellow"] = yellow
        result["checks"]["independent_yellow_transition_after_reset"] = True

        bundle = client.raw(f"sessions/{session_id}/evidence")
        (output / "evidence.zip").write_bytes(bundle)
        result["evidence_sha256"] = digest(bundle)
        result["checks"]["evidence_captured_before_stop"] = True
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if session_id:
            try:
                (output / "serial.txt").write_text(
                    serial(client, session_id), encoding="utf-8"
                )
            except Exception as error:
                result["serial_error"] = str(error)
            if not (output / "evidence.zip").exists():
                try:
                    bundle = client.raw(f"sessions/{session_id}/evidence")
                    (output / "evidence.zip").write_bytes(bundle)
                    result["evidence_sha256"] = digest(bundle)
                    result["evidence_requested_before_stop"] = True
                except Exception as error:
                    result["evidence_error"] = str(error)
            try:
                stopped = client.json(
                    f"sessions/{session_id}?purge=0", method="DELETE"
                )
                result["stopped"] = stopped
            except Exception as error:
                result["stop_error"] = str(error)
        (output / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "status": result["status"],
        "result": str(output / "result.json"),
        "error": result.get("error"),
    }, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8787")
    parser.add_argument(
        "--device", choices=("cores3", "atoms3r", "sticks3", "stopwatch"),
        default="cores3",
    )
    parser.add_argument("--unit", choices=("relay", "2relay"), default="2relay")
    parser.add_argument("--qemu", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--execute", action="store_true")
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
