#!/usr/bin/env python3
"""Replace UIFlow source in one visible guest with three real I2C Units.

Default invocation prints an offline plan. --execute uses Device Service only;
it neither launches QEMU nor uploads a replacement driver or application image.
The service prepares its admitted reference UART-REPL bootstrap once.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/units"))
from run_host_cases import runtime_provenance
from run_live_program import ProbeClient, require, save

DEVICES = ("cores3", "atoms3r", "sticks3", "stopwatch")
GROUPS = {
    "sensors": {
        "leaves": (("env", "env-iii"), ("ncir", "ncir"), ("tvoc", "tvoc")),
        "scan": [0x44, 0x58, 0x5A, 0x70],
        "initial": {
            "env": {"temperature-c": 25, "humidity-pct": 50, "pressure-pa": 101325},
            "ncir": {"ambient-c": 25, "object-c": 32},
            "tvoc": {"eco2-ppm": 800, "tvoc-ppb": 40, "raw-h2": 21000, "raw-ethanol": 22000},
        },
        "fixtures": {
            "env": ({"temperature-c": 31.5, "humidity-pct": 67, "pressure-pa": 98765},
                    {"temperature-c": 18.2, "humidity-pct": 42, "pressure-pa": 102345}),
            "ncir": ({"ambient-c": 17.3, "object-c": 37.1},
                     {"ambient-c": 31.5, "object-c": 53.2}),
            "tvoc": ({"eco2-ppm": 1250, "tvoc-ppb": 230, "raw-h2": 26000, "raw-ethanol": 31000},
                     {"eco2-ppm": 675, "tvoc-ppb": 18, "raw-h2": 18300, "raw-ethanol": 24500}),
        },
        "tolerances": {"env": {"temperature-c": .2, "humidity-pct": .2, "pressure-pa": 1.5},
                       "ncir": {"ambient-c": .021, "object-c": .021}},
        "imports": "from unit import ENVUnit, NCIRUnit, TVOCUnit",
        "official_docs": ["https://docs.m5stack.com/en/unit/envIII", "https://docs.m5stack.com/en/unit/ncir",
                          "https://docs.m5stack.com/en/unit/tvoc", "https://docs.m5stack.com/en/unit/hub"],
        "source_references": ["tests/units/io_probe/io_program.py", "tests/units/run_io_cases.py",
                              "tests/units/host_probe/host_program.py", "docs/unit-research/official-protocols.md"],
    },
    "controls": {
        "leaves": (("encoder", "encoder"), ("eight", "8encoder"), ("joystick", "joystick-v11")),
        "scan": [0x40, 0x41, 0x52],
        "initial": {
            "encoder": {"counter": 0, "pressed": False},
            "eight": {"counters": [0] * 8, "pressed": [False] * 8, "switch-on": False},
            "joystick": {"x-raw": 128, "y-raw": 128, "button-raw": 0},
        },
        "fixtures": {
            "encoder": ({"counter": -12345, "pressed": True}, {"counter": 32767, "pressed": False}),
            "eight": ({"counters": [1, -2, 123456, -123456, 2147483647, -2147483648, 7, 8],
                       "pressed": [True, False, True, False, False, True, False, True], "switch-on": True},
                      {"counters": [-17, 42, -300, 400, -500, 600, -700, 800],
                       "pressed": [False, True, False, True, True, False, True, False], "switch-on": False}),
            "joystick": ({"x-raw": 31, "y-raw": 240, "button-raw": 1},
                         {"x-raw": 255, "y-raw": 0, "button-raw": 0}),
        },
        "tolerances": {},
        "imports": "from unit import EncoderUnit, Encoder8Unit, JoystickUnit",
        "official_docs": ["https://docs.m5stack.com/en/unit/encoder", "https://docs.m5stack.com/en/unit/Unit_8Encoder",
                          "https://docs.m5stack.com/en/unit/joystick", "https://docs.m5stack.com/en/unit/hub"],
        "source_references": ["tests/units/controls_probe/control_drivers/encoder.py",
                              "tests/units/controls_probe/control_drivers/encoder8.py",
                              "tests/units/controls_probe/control_drivers/joystick.py",
                              "tests/units/controls_probe/control_drivers/source-manifest.json",
                              "tests/units/run_control_cases.py", "docs/unit-research/official-protocols.md"],
    },
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def attachments(group, port_id):
    spec = GROUPS[group]
    return [{"id": "hub1", "unit_id": "hub", "port_id": port_id}, *[
        {"id": instance, "unit_id": unit, "parent_id": "hub1", "port_id": f"grove-{index}",
         "initial": deepcopy(spec["initial"][instance])}
        for index, (instance, unit) in enumerate(spec["leaves"], 1)
    ]]


def led_expectations(version):
    factor = 1 if version == "A" else 3
    return {"encoder": [0x112233 * factor, 0x223344 * factor],
            "eight": [i * 0x010203 * factor for i in range(1, 9)] + [0x192939 * factor]}


def program_source(group, version, nonce, pins):
    spec = GROUPS[group]
    color = 0xFFFFFF if version == "A" else 0x88FF88
    prefix = f"LIVE_BATCH_{version}_{group.upper()}"
    if group == "sensors":
        initialize = '''env = ENVUnit(i2c=bus, type=3)
ncir = NCIRUnit(bus)
tvoc = TVOCUnit(bus)
# SGP30 returns its fixed 400ppm/0ppb output during real IAQ initialization.
for _second in range(16):
 M5.update()
 print("LIVE_BATCH_WARMUP", _second)
 time.sleep_ms(1000)
'''
        sample = '''iaq = tvoc.measure_iaq()
 raw = tvoc.measure_raw()
 values = {
  "env": {"temperature-c": env.read_temperature(), "humidity-pct": env.read_humidity(), "pressure-pa": env.read_pressure() * 100},
  "ncir": {"ambient-c": ncir.get_ambient_temperature(), "object-c": ncir.get_object_temperature()},
  "tvoc": {"eco2-ppm": iaq[0], "tvoc-ppb": iaq[1], "raw-h2": raw[0], "raw-ethanol": raw[1]},
 }
 lines = ["ENV %.1fC %.0f%%" % (values["env"]["temperature-c"], values["env"]["humidity-pct"]),
          "NCIR %.1fC" % values["ncir"]["object-c"], "TVOC %d ppb" % iaq[1]]
'''
    else:
        leds = led_expectations(version)
        initialize = f'''encoder = EncoderUnit(bus)
eight = Encoder8Unit(bus)
joystick = JoystickUnit(bus, 0x52)
encoder.set_color(1, {leds['encoder'][0]})
encoder.set_color(2, {leds['encoder'][1]})
for _channel, _color in enumerate({leds['eight'][:8]!r}, 1):
 eight.set_led_rgb(_channel, _color)
# Official high-level set_led_rgb clamps to 1..8. Its original register helper
# writes the separate ninth/switch LED triplet without replacing the driver.
eight.write_reg_data(0x88, {list(leds['eight'][8].to_bytes(3, 'big'))!r})
'''
        sample = '''values = {
  "encoder": {"counter": encoder.get_rotary_value(), "pressed": bool(encoder.get_button_status())},
  "eight": {"counters": [eight.get_counter_value(i) for i in range(1, 9)],
            "pressed": [bool(eight.get_button_status(i)) for i in range(1, 9)], "switch-on": bool(eight.get_switch_status())},
  "joystick": {"x-raw": joystick.get_x_raw(), "y-raw": joystick.get_y_raw(), "button-raw": int(joystick.get_button_status())},
 }
 lines = ["ENC %d" % values["encoder"]["counter"], "8ENC %d %d" % tuple(values["eight"]["counters"][:2]),
          "JOY %d %d" % (values["joystick"]["x-raw"], values["joystick"]["y-raw"])]
'''
    return f'''import sys
import time
import json
import M5
from machine import I2C, Pin
{spec['imports']}
assert {'/m5-live-batch-' + nonce!r} in sys.path, "MicroPython VM was reset"
M5.begin()
screen = M5.Display
screen.setBrightness(255)
screen.fillScreen({color})
screen.setFont(screen.FONTS.Montserrat12)
screen.setTextSize(1)
screen.setTextColor(0, {color})
x, y = (96, 120) if screen.width() > 400 else (4, 4)
screen.setCursor(x, y)
screen.print({version + ' ' + group!r})
bus = I2C(0, scl=Pin({pins['white']}), sda=Pin({pins['yellow']}), freq=100000)
scan = sorted(bus.scan())
assert scan == {spec['scan']!r}, "HUB address set differs or onboard bus leaked"
{initialize}
print({prefix + '_READY'!r}, json.dumps(scan))
while True:
 M5.update()
 {sample.strip()}
 print({prefix + '_SAMPLE'!r}, json.dumps(values))
 screen.fillRect(x, y + 18, min(120, screen.width() - x), 54, {color})
 for row, text in enumerate(lines):
  screen.setCursor(x, y + 18 + row * 18)
  screen.print(text)
 time.sleep_ms({1000 if group == 'sensors' else 200})
'''


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def values_match(observed, expected, tolerances=None):
    """Compare guest values without accepting bool/int or non-finite aliases."""
    tolerances = tolerances or {}
    if type(expected) is dict:
        return type(observed) is dict and set(observed) == set(expected) and all(
            values_match(observed[key], value, tolerances.get(key, {})) for key, value in expected.items())
    if type(expected) is list:
        return type(observed) is list and len(observed) == len(expected) and all(
            values_match(actual, value) for actual, value in zip(observed, expected))
    if type(expected) is bool:
        return type(observed) is bool and observed is expected
    if finite_number(expected):
        tolerance = tolerances if type(tolerances) in (int, float) else 0
        return finite_number(observed) and abs(observed - expected) <= tolerance
    return type(observed) is type(expected) and observed == expected


def matching_sample(text, group, version, expected):
    prefix = f"LIVE_BATCH_{version}_{group.upper()}_SAMPLE "
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n") or not line.startswith(prefix):
            continue
        try:
            value = json.loads(line[len(prefix):])
        except (ValueError, TypeError):
            continue
        if values_match(value, expected, GROUPS[group]["tolerances"]):
            return value
    return None


def live_units(response, session_id, requested):
    require(response.get("session_id") == session_id and response.get("source") == "live", "Unit state is not from the selected live session")
    rows = response.get("units", [])
    expected = {row["id"]: row["unit_id"] for row in requested}
    require(len(rows) == len(expected) and {row.get("id"): row.get("unit_id") for row in rows} == expected,
            "Unit response attachment tree differs")
    require(all(row.get("available") is True and row.get("source") == "guest-qom" for row in rows), "Unit QOM state is unavailable")
    return {row["id"]: row["properties"] for row in rows}


def validate_bundle(data, report, sources):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(archive.testzip() is None and len(names) == len(set(names)), "corrupt or duplicate evidence ZIP member")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(manifest["files"]) == set(names) - {"manifest.json"}, "evidence file index differs")
        for name, record in manifest["files"].items():
            content = archive.read(name)
            require(record["size"] == len(content) and record["sha256"] == sha(content), "evidence member hash/size differs: " + name)
        require({"serial.log", "frames/current.png", "qom/snapshot.json", "units/contract.json", "units/state.json", "units/runtime.json"} <= set(names), "evidence data planes are missing")
        session = manifest["session"]
        require(session["state"] == "running" and all(session[key] == report[key] for key in ("session_id", "device_id", "runtime", "firmware_sha256", "pid")), "evidence guest identity differs")
        units = manifest["units"]["units"]
        require({r["id"]: r["unit_id"] for r in units} == {r["id"]: r["unit_id"] for r in report["attachments"]} and all(r.get("available") is True for r in units), "evidence Unit attachment tree differs")
        serial_raw = archive.read("serial.log")
        # UART raw-paste negotiation contains binary credit bytes. The serial
        # JSON API exposes UTF-8 with replacement, while offsets count raw bytes.
        serial = serial_raw.decode("utf-8", errors="replace")
        require(serial.count("M5EMU_UART_REPL_READY") == 1 and serial.count("ESP-ROM:") == report["initial_rom_banners"], "guest rebooted or bootstrap restarted")
        for phase in report["phases"]:
            for row in phase["inputs"]:
                offset = row["serial_offset_before"]
                window = row["serial_window"]
                end = window.get("next_offset")
                require(type(end) is int and type(offset) is int and 0 <= offset <= end <= len(serial_raw),
                        "fresh serial window has invalid raw byte offsets")
                require(type(offset) is int and 0 <= offset <= len(serial_raw)
                        and sha(serial_raw[:offset].decode("utf-8", errors="replace").encode()) == row["serial_prefix_sha256"]
                        and serial_raw[offset:end].decode("utf-8", errors="replace") == window["data"],
                        "fresh input window is not bound to its ZIP serial offset")
                observed = matching_sample(row["serial_window"]["data"], report["group"], phase["version"], row["expected_all_leaves"])
                require(observed is not None and observed == row["matched_sample"], "fresh input observation is absent from ZIP serial")
        for name, result in report["executions"].items():
            execution = result["program"]
            history = json.loads(archive.read(f"programs/{execution['execution_id']}.json"))
            require(all(history[key] == execution[key] for key in ("execution_id", "revision_id", "pid", "firmware_sha256")), "program evidence identity differs")
            source = json.loads(archive.read(f"programs/{execution['revision_id']}/source.json"))
            require(source == {"entrypoint": "main.py", "files": {"main.py": sources[name]}}, "evidence program source differs")
            if name in {"a", "b"}:
                require(history["state"] == "interrupted" and history.get("interruption_confirmed") is True, "previous loop interruption was not confirmed")
        with Image.open(io.BytesIO(archive.read("frames/current.png"))) as image:
            image.load()
            require(image.format == "PNG" and list(image.size) == report["expected_frame_size"], "evidence PNG geometry differs")
        return {"members": len(names), "sha256": sha(data), "member_index_verified": True}


def wait(client, prefix, predicate, *, timeout=60, serial_offset=None, execution_id=None):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        state = client.json(prefix)
        require(state["state"] not in {"failed", "stopped"}, "guest ended before observation: " + str(state.get("error")))
        if serial_offset is None:
            last = state
        else:
            last = client.json(prefix + f"/serial?offset={serial_offset}&limit=1048576")
            if execution_id:
                require(f"__M5_EXEC_{execution_id}__:ERROR" not in last["data"], "guest program failed: " + last["data"][-1600:])
        if state["state"] == "running" and predicate(last):
            return last
        time.sleep(.1)
    raise RuntimeError("observation deadline exceeded; last response: " + str(last)[-1600:])


def completed_execution(client, prefix, execution_id):
    # /sessions is a cached session representation. /program advances its
    # scanner over newly committed guest UART bytes, including finite DONE.
    program = client.json(prefix + "/program")["program"]
    require(program["execution_id"] == execution_id, "another program replaced the finite execution")
    require(program["state"] not in {"failed", "interrupted"}, "finite guest program failed or was replaced")
    return program["state"] == "completed"


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    spec = GROUPS[args.group]
    report = {"schema_version": 1, "status": "FAIL", "date": datetime.now(timezone.utc).isoformat(),
              "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "device_id": args.device,
              "group": args.group, "runtime": "qemu", "driver_mode": "unchanged reference-frozen unit modules",
              "official_docs": spec["official_docs"], "runner_sha256": sha(Path(__file__).read_bytes()),
              "reference_source_sha256": {name: sha((ROOT / name).read_bytes()) for name in spec["source_references"]},
              "executions": {}, "phases": []}
    client = ProbeClient(args.api, args.out_dir)
    session_id = None
    sources = {}
    try:
        inventory = client.json(f"units?device_id={args.device}")
        host = next(row for row in inventory["hosts"] if row["device_id"] == args.device)
        ports = [row for row in host["ports"] if row.get("visual_port") == "grove" and row.get("wiring_status") == "confirmed" and row.get("physical_presence") == "main-device"]
        require(len(ports) == 1, "expected exactly one confirmed main-device Grove port")
        requested = attachments(args.group, ports[0]["id"])
        report["attachments"] = requested
        created = client.json("sessions", "POST", {"device_id": args.device, "runtime": "qemu", "program_mode": "uiflow-live",
                              "ttl_seconds": 600, "ready_timeout_seconds": 40, "units": requested})
        session_id = created["session_id"]
        report["session_id"] = session_id
        save(args.out_dir / "created.json", created)
        prefix = "sessions/" + session_id
        ready = wait(client, prefix, lambda row: row["state"] == "running", timeout=100)
        report.update(firmware_sha256=ready["firmware_sha256"], pid=ready["pid"], worker=ready.get("worker"))
        save(args.out_dir / "firmware.json", client.json(f"firmware/{ready['firmware_id']}"))
        report["runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        frozen = {row["id"]: row for row in created["units"]}
        require(set(frozen) == {row["id"] for row in requested}, "created attachments differ")
        pins = frozen["hub1"]["pins"]
        require(all(row["pins"] == pins for row in frozen.values()), "HUB children do not share frozen host pins")
        report["frozen_attachments"] = created["units"]
        matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
        device = next(row for row in matrix["devices"] if row["id"] == args.device)
        report["expected_frame_size"] = [int(part) for part in device["expected_size"].split("x")]
        initial_serial = client.json(prefix + "/serial?limit=1048576")
        report["initial_rom_banners"] = initial_serial["data"].count("ESP-ROM:")
        require(initial_serial["data"].count("M5EMU_UART_REPL_READY") == 1, "live bootstrap readiness is missing")
        expected_execution = None
        nonce = uuid.uuid4().hex

        def submit(name, source):
            nonlocal expected_execution
            sources[name] = source
            (args.out_dir / f"source-{name}.py").write_text(source, encoding="utf-8")
            started = time.monotonic()
            result = client.json(prefix + "/program", "POST", {"source": source, "expected_execution_id": expected_execution, "timeout_seconds": 20})
            result["request_seconds"] = time.monotonic() - started
            program = result["program"]
            require(program["pid"] == ready["pid"] and program["firmware_sha256"] == ready["firmware_sha256"], "program replaced the guest process or firmware")
            expected_execution = program["execution_id"]
            report["executions"][name] = result
            save(args.out_dir / f"program-{name}.json", result)
            return program

        finite = submit("finite", f"import sys\nsys.path.append({'/m5-live-batch-' + nonce!r})\nprint('LIVE_BATCH_FINITE_DONE')\n")
        wait(client, prefix, lambda row: completed_execution(client, prefix, finite["execution_id"]))
        expected = deepcopy(spec["initial"])
        frame_hashes = []
        for version in ("A", "B"):
            offset = client.json(prefix + "/serial?limit=1048576")["next_offset"]
            program = submit(version.lower(), program_source(args.group, version, nonce, pins))
            marker = f"LIVE_BATCH_{version}_{args.group.upper()}_READY " + json.dumps(spec["scan"])
            wait(client, prefix, lambda row: marker in row["data"], timeout=100, serial_offset=offset, execution_id=program["execution_id"])
            phase = {"version": version, "execution_id": program["execution_id"], "inputs": []}
            report["phases"].append(phase)
            before_state = client.json(prefix + "/units")
            before_properties = live_units(before_state, session_id, requested)
            phase["initial_qom"] = before_state
            if args.group == "controls":
                for instance, colors in led_expectations(version).items():
                    require(values_match(before_properties[instance].get("led-rgb"), colors), "guest LED writes did not reach QOM: " + instance)
            for instance, _unit_id in spec["leaves"]:
                for index, values in enumerate(spec["fixtures"][instance], 1):
                    before_serial = client.json(prefix + "/serial?limit=1048576")
                    offset = before_serial["next_offset"]
                    response = client.json(prefix + "/unit-input", "POST", {"id": instance, "values": values})
                    properties = live_units(response, session_id, requested)
                    require(all(values_match(properties[instance].get(key), value) for key, value in values.items()), "input POST did not reach the selected QOM child")
                    expected[instance].update(deepcopy(values))
                    window = wait(client, prefix, lambda row: matching_sample(row["data"], args.group, version, expected) is not None,
                                  timeout=100, serial_offset=offset, execution_id=program["execution_id"])
                    qom = client.json(prefix + "/units")
                    current = live_units(qom, session_id, requested)
                    require(all(values_match(current[child].get(key), value) for child, vector in expected.items() for key, value in vector.items()), "independent QOM readback differs from expected input state")
                    phase["inputs"].append({"id": instance, "fixture": index, "values": deepcopy(values),
                        "expected_all_leaves": deepcopy(expected), "serial_offset_before": offset,
                        "serial_prefix_sha256": sha(before_serial["data"].encode()),
                        "serial_prefix_encoding": "API UTF-8 errors=replace; offsets count raw bytes", "serial_window": window,
                        "matched_sample": matching_sample(window["data"], args.group, version, expected),
                        "post_response": response, "qom_readback": qom})
            after_state = client.json(prefix + "/units")
            after_properties = live_units(after_state, session_id, requested)
            phase["final_qom"] = after_state
            for instance, _unit_id in spec["leaves"]:
                require(all(after_properties[instance][key] > before_properties[instance][key] for key in ("transactions", "read-bytes", "written-bytes", "input-events")), "child lacks fresh driver traffic/input events: " + instance)
            if args.group == "controls":
                for instance, colors in led_expectations(version).items():
                    require(values_match(after_properties[instance].get("led-rgb"), colors), "guest LEDs changed unexpectedly")
            frame = client.raw(prefix + "/frame.png")
            with Image.open(io.BytesIO(frame)) as image:
                image.load()
                require(list(image.size) == report["expected_frame_size"], "phase frame geometry differs")
            (args.out_dir / f"frame-{version.lower()}.png").write_bytes(frame)
            frame_hashes.append(sha(frame))
            save(args.out_dir / f"phase-{version.lower()}.json", phase)
        require(frame_hashes[0] != frame_hashes[1], "source replacement did not change guest frame")
        syntax = submit("syntax-error", "def broken(:\n")
        require(syntax["state"] == "failed", "syntax error did not fail")
        recovered = submit("recovery", f"import sys\nassert {'/m5-live-batch-' + nonce!r} in sys.path\nprint('LIVE_BATCH_RECOVERED')\n")
        window = wait(client, prefix, lambda row: "LIVE_BATCH_RECOVERED" in row["data"], serial_offset=recovered["serial_offset"], execution_id=recovered["execution_id"])
        report["recovery_serial"] = window
        report["final_runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        require(report["final_runtime_provenance"]["pid"] == ready["pid"], "guest process changed during replacement")
        bundle = client.raw(prefix + "/evidence")
        (args.out_dir / "evidence.zip").write_bytes(bundle)
        report["evidence"] = validate_bundle(bundle, report, sources)
        report.update(status="PASS", frame_sha256=frame_hashes, checks={"same_pid_firmware_and_vm": True,
            "two_program_versions": True, "each_leaf_two_fixtures_per_version": True, "fresh_serial_and_independent_qom": True,
            "each_child_fresh_i2c_traffic": True, "syntax_error_recovered": True, "revision_sources_in_evidence": True,
            })
        if args.group == "controls":
            report["checks"]["guest_led_output_readback"] = True
    except Exception as error:
        report["error"] = str(error)
    finally:
        if session_id:
            try:
                if not (args.out_dir / "evidence.zip").exists():
                    (args.out_dir / "failure-evidence.zip").write_bytes(client.raw(f"sessions/{session_id}/evidence"))
            except Exception as error:
                report.update(status="FAIL", evidence_error=str(error))
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", "DELETE")
                deadline = time.monotonic() + 45
                while stopped["state"] not in {"stopped", "failed"} and time.monotonic() < deadline:
                    time.sleep(.1)
                    stopped = client.json(f"sessions/{session_id}")
                save(args.out_dir / "stopped.json", stopped)
                require(stopped["state"] == "stopped" and stopped.get("flash_retained") is False, "session cleanup/Flash release was not confirmed")
                report["cleanup"] = {"state": stopped["state"], "flash_retained": stopped["flash_retained"], "history_retained": True}
            except Exception as error:
                report.update(status="FAIL", cleanup_error=str(error))
        save(args.out_dir / "report.json", report)
    require(report["status"] == "PASS", report.get("error") or report.get("cleanup_error") or "batch validation failed")
    print(json.dumps({"status": report["status"], "device_id": args.device, "group": args.group,
                      "session_id": session_id, "programs": len(report["executions"]), "input_vectors": sum(len(p["inputs"]) for p in report["phases"])}))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--device", choices=DEVICES, default="cores3")
    parser.add_argument("--group", choices=tuple(GROUPS), default="sensors")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--expected-runtime-sha256")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"status": "PLANNED_NOT_EXECUTED", "device_id": args.device, "group": args.group,
                          "leaves": GROUPS[args.group]["leaves"], "expected_i2c_scan": GROUPS[args.group]["scan"],
                          "program_mode": "uiflow-live", "versions": ["A", "B"], "input_vectors": 12}, indent=2))
        return
    if args.out_dir is None or not re.fullmatch(r"[0-9a-f]{64}", args.expected_runtime_sha256 or ""):
        parser.error("--execute requires a new --out-dir and exact --expected-runtime-sha256")
    run(args)


if __name__ == "__main__":
    main()
