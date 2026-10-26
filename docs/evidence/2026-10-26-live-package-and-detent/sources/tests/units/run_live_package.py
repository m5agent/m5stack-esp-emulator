#!/usr/bin/env python3
"""Plan, or explicitly validate, complete same-guest UIFlow2 program packages.

Only --execute may create a visible Device Service lease. Dependencies are
compiled by an explicitly supplied mpy-cross; submitted code is never executed
by host Python. QEMU evidence is not a physical-device measurement.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import urllib.error
import uuid
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/units"))
from run_live_program import ProbeClient, poll, require, save
from run_host_cases import runtime_provenance

DEVICES = ("cores3", "atoms3r", "sticks3", "stopwatch")
GUEST_BASE = "/flash/.m5-live-packages"
NONCE_PREFIX = "/m5-live-package-"
IMAGE_SIZE = (24, 24)
VERSIONS = {
    "A": {"helper": 17, "init": 101, "logic": 3, "color": [255, 0, 0], "relay": False, "old_present": True},
    "B": {"helper": 29, "init": 202, "logic": 5, "color": [0, 255, 0], "relay": True, "old_present": False},
    "C": {"helper": 41, "init": 303, "logic": 7, "color": [0, 0, 255], "relay": False, "old_present": False},
}
OFFICIAL_DOCS = {
    "display": "https://uiflow-micropython.readthedocs.io/en/latest/hardware/display.html",
    "pir": "https://uiflow-micropython.readthedocs.io/en/latest/units/pir.html",
    "relay": "https://uiflow-micropython.readthedocs.io/en/latest/units/relay.html",
    "mpy": "https://github.com/micropython/micropython/blob/78ff170de9e32c79db6e64d3e33d2bd60002bdcd/docs/reference/mpyfiles.rst",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def file_inventory(files):
    return {path: {"size": len(data), "sha256": sha(data)} for path, data in sorted(files.items())}


def revision_id(files):
    return sha(canonical({"source_kind": "uiflow2-package", "entrypoint": "main.py",
                          "files": {path: sha(data) for path, data in sorted(files.items())}}))


def package_payload(files, expected):
    encoded = {}
    for path, data in sorted(files.items()):
        text = path.endswith((".py", ".json"))
        encoded[path] = {"encoding": "utf8" if text else "base64",
                         "data": data.decode("utf-8") if text else base64.b64encode(data).decode("ascii")}
    return {"files": encoded, "entrypoint": "main.py", "expected_execution_id": expected, "timeout_seconds": 120}


def main_source(nonce, pins, unit):
    """The exact same entrypoint consumes all A/B/C dependency/resource variants."""
    construct = (f"from unit import PIRUnit\nunit = PIRUnit(({pins['white']}, {pins['yellow']}))"
                 if unit == "pir" else
                 f"from unit import RelayUnit\nunit = RelayUnit(({pins['white']}, {pins['yellow']}))\nunit.set_status(config['relay'])")
    return f'''import os, sys, json, time
import M5
assert {NONCE_PREFIX + nonce!r} in sys.path, "MicroPython VM was reset"
with open('config.json') as stream:
 config = json.load(stream)
import helper
import lib
from lib import logic
import namespace_lib.state as namespace_state
assert helper.VALUE == config['helper']
assert lib.VALUE == config['init']
assert logic.VALUE == config['logic']
assert namespace_state.VALUE == config['init']
assert logic.calculate(5) == 10 + config['helper'] + config['logic']
cwd = os.getcwd()
managed_paths = [path for path in sys.path if isinstance(path, str) and path.startswith({GUEST_BASE + '/'!r})]
assert managed_paths == [cwd], 'stale managed import path'
for module in (helper, lib, logic, namespace_state):
 assert module.__file__.startswith(cwd + '/'), 'stale module cache'
if config['old_present']:
 import old_only
 assert old_only.VALUE == 'A-only'
 old_absent = False
else:
 assert 'old_only' not in sys.modules, 'removed module stayed cached'
 try:
  import old_only
 except ImportError:
  old_absent = True
 else:
  raise AssertionError('removed file is still importable')
M5.begin()
screen = M5.Display
screen.setBrightness(255)
screen.fillScreen(0)
with open('assets/pixel.png', 'rb') as stream:
 screen.drawImage(stream.read(), (screen.width() - 24) // 2, (screen.height() - 24) // 2 - 24)
screen.setTextSize(2)
screen.setTextColor(0xFFFFFF, 0)
screen.setCursor(screen.width() // 2 - 24, screen.height() // 2 + 4)
screen.print('PKG ' + config['version'])
{construct}
print('LIVE_PACKAGE_READY ' + json.dumps({{'version': config['version'], 'helper': helper.VALUE, 'init': lib.VALUE, 'logic': logic.VALUE, 'cwd': cwd, 'managed_paths': managed_paths, 'old_absent': old_absent, 'helper_file': helper.__file__, 'logic_file': logic.__file__}}))
previous = None
last_sample = time.ticks_ms()
while True:
 M5.update()
 value = int(unit.get_status())
 now = time.ticks_ms()
 if value != previous:
  screen.fillRect(0, screen.height() // 2 + 24, screen.width(), 28, 0)
  screen.setCursor(screen.width() // 2 - 36, screen.height() // 2 + 24)
  screen.print('{unit.upper()} ' + str(value))
 if value != previous or time.ticks_diff(now, last_sample) >= 250:
  print('LIVE_PACKAGE_SAMPLE ' + json.dumps({{'version': config['version'], 'unit': {unit!r}, 'value': value, 'helper': helper.VALUE, 'init': lib.VALUE, 'logic': logic.VALUE, 'computed': logic.calculate(value)}}))
  last_sample = now
 previous = value
 time.sleep_ms(25)
'''


def compile_helper(compiler, directory, version):
    directory.mkdir(parents=True, exist_ok=False)
    source = (f"VALUE = {VERSIONS[version]['helper']}\n"
              "def transform(value):\n return value * 2 + VALUE\n")
    source_path, binary_path = directory / "helper.py", directory / "helper.mpy"
    source_path.write_text(source, encoding="utf-8")
    command = [str(compiler), "-msmall-int-bits=31", "-s", "helper.py", "-o", str(binary_path), str(source_path)]
    completed = subprocess.run(command, check=True, capture_output=True, timeout=30)
    binary = binary_path.read_bytes()
    require(len(binary) >= 4 and binary[:4] == b"M\x06\x00\x1f", "compiler did not emit bytecode-only v6/31-bit .mpy")
    receipt = {"command": command, "source_sha256": sha(source.encode()), "source_bytes": len(source.encode()),
               "binary_sha256": sha(binary), "binary_bytes": len(binary), "header": list(binary[:4]),
               "stdout": completed.stdout.decode("utf-8", errors="replace"),
               "stderr": completed.stderr.decode("utf-8", errors="replace")}
    save(directory / "receipt.json", receipt)
    return binary, receipt


def build_packages(compiler, directory, nonce, pins, unit):
    compiler = compiler.resolve(strict=True)
    require(compiler.is_file() and os.access(compiler, os.X_OK), "--mpy-cross must name an executable file")
    version = subprocess.run([str(compiler), "--version"], check=True, capture_output=True, timeout=15)
    compiler_receipt = {"executable_sha256": sha(compiler.read_bytes()), "executable_bytes": compiler.stat().st_size,
                        "version": (version.stdout + version.stderr).decode("utf-8", errors="replace").strip(),
                        "executable_name": compiler.name, "helpers": {}}
    directory.mkdir(parents=True, exist_ok=False)
    source = main_source(nonce, pins, unit).encode()
    packages = {}
    for name, config in VERSIONS.items():
        binary, receipt = compile_helper(compiler, directory / name, name)
        compiler_receipt["helpers"][name] = receipt
        image = io.BytesIO()
        Image.new("RGB", IMAGE_SIZE, tuple(config["color"])).save(image, format="PNG")
        files = {
            "main.py": source,
            "config.json": canonical({"version": name, **config}) + b"\n",
            "helper.mpy": binary,
            "lib/__init__.py": f"VALUE = {config['init']}\n".encode(),
            "lib/logic.py": f"import helper\nVALUE = {config['logic']}\ndef calculate(value):\n return helper.transform(value) + VALUE\n".encode(),
            "namespace_lib/state.py": f"VALUE = {config['init']}\n".encode(),
            "assets/pixel.png": image.getvalue(),
        }
        if name == "A":
            files["old_only.py"] = b"VALUE = 'A-only'\n"
        packages[name] = files
        for path, data in files.items():
            target = directory / name / "package" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        save(directory / name / "inventory.json", file_inventory(files))
    require(len({sha(packages[name]["helper.mpy"]) for name in packages}) == 3, "compiled helper variants did not change")
    require(len({sha(files["main.py"]) for files in packages.values()}) == 1, "A/B/C entrypoint bytes differ")
    save(directory / "compiler.json", compiler_receipt)
    return packages, compiler_receipt


def expected_sample(version, unit, value):
    config = VERSIONS[version]
    return {"version": version, "unit": unit, "value": value, "helper": config["helper"], "init": config["init"],
            "logic": config["logic"], "computed": value * 2 + config["helper"] + config["logic"]}


def matching_json_line(text, prefix, expected):
    """Require complete UART lines and exact types, never bool/int aliases."""
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n") or not line.startswith(prefix):
            continue
        try:
            value = json.loads(line[len(prefix):])
        except (ValueError, TypeError):
            continue
        if type(value) is dict and all(key in value and type(value[key]) is type(item) and value[key] == item for key, item in expected.items()):
            return value
    return None


def frame_observation(data, expected_size, version):
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        require(image.format == "PNG" and list(image.size) == list(expected_size), "guest frame PNG geometry differs")
        color = VERSIONS[version]["color"]
        colored_pixels = sum(all(abs(actual - wanted) <= 8 for actual, wanted in zip(pixel, color))
                             for pixel in image.convert("RGB").getdata())
        require(colored_pixels >= IMAGE_SIZE[0] * IMAGE_SIZE[1] * .7, "drawImage asset color is absent from the guest framebuffer")
        return {"sha256": sha(data), "size": list(image.size), "asset_rgb": color, "asset_color_pixels": colored_pixels}


def live_unit(response, session_id, unit):
    require(response.get("session_id") == session_id and response.get("source") == "live", "Unit response is from another or nonlive session")
    rows = response.get("units", [])
    require(len(rows) == 1 and rows[0].get("id") == "external1" and rows[0].get("unit_id") == unit,
            "Unit response attachment differs")
    require(rows[0].get("available") is True and rows[0].get("source") == "guest-qom" and not rows[0].get("errors"), "Unit controller readback is unavailable")
    return rows[0]["properties"]


def decode_rejection(error):
    """The reused Client retains HTTPError as the cause and JSON in its message."""
    cause = error.__cause__
    if not isinstance(cause, urllib.error.HTTPError):
        raise error
    separator = f": HTTP {cause.code} "
    text = str(error)
    require(separator in text, "HTTP rejection body is unavailable")
    payload = json.loads(text.split(separator, 1)[1])
    require(type(payload.get("error")) is dict and isinstance(payload["error"].get("code"), str), "invalid HTTP rejection envelope")
    return {"status": cause.code, "response": payload}


def validate_bundle(data, report, submitted):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(archive.testzip() is None and len(names) == len(set(names)), "corrupt or duplicate ZIP members")
        for name in names:
            path = PurePosixPath(name)
            require(not path.is_absolute() and ".." not in path.parts and "\\" not in name, "unsafe ZIP member path")
            require((archive.getinfo(name).external_attr >> 16) & 0xf000 != 0xa000, "ZIP member is a symlink")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(manifest["files"]) == set(names) - {"manifest.json"}, "ZIP member index differs")
        for path, row in manifest["files"].items():
            content = archive.read(path)
            require(row["size"] == len(content) and row["sha256"] == sha(content), "ZIP member size/hash differs: " + path)
        session = manifest["session"]
        require(session["state"] == "running" and all(session.get(key) == report[key] for key in ("session_id", "device_id", "runtime", "pid", "firmware_sha256")), "ZIP guest identity differs")
        require({"serial.log", "frames/current.png", "qom/snapshot.json", "units/contract.json", "units/state.json", "units/runtime.json"} <= set(names), "ZIP data-plane evidence is missing")
        live_unit(manifest["units"], report["session_id"], report["unit_id"])
        raw = archive.read("serial.log")
        serial = raw.decode("utf-8", errors="replace")
        require(serial.count("ESP-ROM:") == report["initial_rom_banners"] and serial.count("M5EMU_UART_REPL_READY") == 1, "ZIP shows guest reboot/bootstrap repetition")
        for row in report["serial_observations"]:
            start, end = row["offset"], row["window"]["next_offset"]
            require(type(start) is int and type(end) is int and 0 <= start <= end <= len(raw), "ZIP serial offsets are invalid")
            require(sha(raw[:start].decode("utf-8", errors="replace").encode()) == row["prefix_sha256"]
                    and raw[start:end].decode("utf-8", errors="replace") == row["window"]["data"], "ZIP serial offset binding differs")
            if "expected" in row:
                require(matching_json_line(row["window"]["data"], row["line_prefix"], row["expected"]) is not None,
                        "fresh guest sample is missing from ZIP serial")
            if "marker" in row:
                require(row["marker"] in row["window"]["data"], "fresh guest marker is missing from ZIP serial")
            for forbidden in row.get("forbidden", []):
                require(forbidden not in row["window"]["data"], "rejected package executed its application")
        for name, result in report["executions"].items():
            program = result["program"]
            history = json.loads(archive.read(f"programs/{program['execution_id']}.json"))
            require(all(history[key] == program[key] for key in ("execution_id", "revision_id", "pid", "firmware_sha256")), "ZIP execution identity differs")
            require(history["state"] == result["expected_history_state"], "ZIP execution terminal/current state differs: " + name)
            if history["state"] == "interrupted":
                require(history.get("interruption_confirmed") is True, "ZIP interruption was not confirmed")
            source = json.loads(archive.read(f"programs/{program['revision_id']}/source.json"))
            if isinstance(submitted[name], str):
                require(source == {"entrypoint": "main.py", "files": {"main.py": submitted[name]}}, "ZIP legacy source differs")
                continue
            files = submitted[name]
            metadata = json.loads(archive.read(f"programs/{program['revision_id']}/revision.json"))
            require(metadata.get("source_kind") == history.get("source_kind") == "uiflow2-package"
                    and metadata.get("revision_id") == program["revision_id"]
                    and source.get("entrypoint") == "main.py" and set(source["files"]) == set(files), "ZIP package snapshot differs")
            require({row["path"]: {"size": row["size"], "sha256": row["sha256"]} for row in metadata["files"]} == file_inventory(files), "ZIP package metadata inventory differs")
            for path, expected in files.items():
                require(source["files"][path].get("encoding") == "base64"
                        and base64.b64decode(source["files"][path]["data"], validate=True) == expected
                        and archive.read(f"programs/{program['revision_id']}/files/{path}") == expected,
                        "ZIP package original file bytes differ: " + path)
            require(program["revision_id"] == revision_id(files), "ZIP package revision is not bound to all original files")
            if result.get("activated"):
                deployment = history["deployment"]
                require(deployment["phase"] == "activated" and deployment["inventory"] == file_inventory(files), "ZIP verified guest inventory differs")
                require(deployment["package_path"] == GUEST_BASE + "/" + program["revision_id"], "ZIP activated guest path differs")
                require(deployment.get("reused") is result["reused"], "ZIP package reuse claim differs")
            if result.get("error_code"):
                require(history.get("error", {}).get("code") == result["error_code"], "ZIP rejected execution error differs")
        frame_observation(archive.read("frames/current.png"), report["expected_frame_size"], "C")
        return {"members": len(names), "sha256": sha(data), "original_files_and_guest_inventory_verified": True,
                "serial_byte_offsets_verified": True}


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    client = ProbeClient(args.api, args.out_dir)
    report = {"schema_version": 1, "status": "FAIL", "captured_at": datetime.now(timezone.utc).isoformat(),
              "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "device_id": args.device,
              "unit_id": args.unit, "runtime": "qemu", "program_mode": "uiflow-live", "official_docs": OFFICIAL_DOCS,
              "runner_sha256": sha(Path(__file__).read_bytes()), "executions": {}, "serial_observations": [],
              "phases": [], "negative_controls": {}, "planned_unique_guest_directories": 4}
    session_id, expected = None, None
    submitted = {}
    try:
        inventory = client.json(f"units?device_id={args.device}")
        host = next(row for row in inventory["hosts"] if row["device_id"] == args.device)
        ports = [row for row in host["ports"] if row.get("visual_port") == "grove" and row.get("wiring_status") == "confirmed" and row.get("physical_presence") == "main-device"]
        require(len(ports) == 1, "expected exactly one confirmed main-device Grove port")
        pins = ports[0]["pins"]
        nonce = uuid.uuid4().hex
        packages, compiler_receipt = build_packages(args.mpy_cross, args.out_dir / "compiled", nonce, pins, args.unit)
        report["compiler"] = compiler_receipt
        report["package_inventory"] = {name: {"revision_id": revision_id(files), "files": file_inventory(files)} for name, files in packages.items()}
        created = client.json("sessions", "POST", {"device_id": args.device, "runtime": "qemu", "program_mode": "uiflow-live",
                              "ttl_seconds": 1200, "ready_timeout_seconds": 40,
                              "units": [{"id": "external1", "unit_id": args.unit, "port_id": ports[0]["id"]}]})
        session_id = created["session_id"]
        prefix = "sessions/" + session_id
        save(args.out_dir / "created.json", created)
        require(len(created["units"]) == 1 and created["units"][0]["pins"] == pins, "frozen Unit pins differ from the compilation plan")
        ready = poll(lambda: client.json(prefix), lambda row: row["state"] in {"running", "failed", "stopped"}, 100)
        require(ready["state"] == "running", "visible guest failed to start: " + str(ready.get("error")))
        report.update(session_id=session_id, pins=pins, pid=ready["pid"], firmware_sha256=ready["firmware_sha256"], worker=ready.get("worker"))
        save(args.out_dir / "firmware.json", client.json("firmware/" + ready["firmware_id"]))
        report["runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
        device = next(row for row in matrix["devices"] if row["id"] == args.device)
        report["expected_frame_size"] = [int(part) for part in device["expected_size"].split("x")]
        initial_serial = client.json(prefix + "/serial?offset=0&limit=1048576")
        require(initial_serial["data"].count("M5EMU_UART_REPL_READY") == 1, "live UART bootstrap marker differs")
        report["initial_rom_banners"] = initial_serial["data"].count("ESP-ROM:")
        if args.unit == "pir":
            client.json(prefix + "/unit-input", "POST", {"id": "external1", "values": {"motion": False}})

        def same_guest(program):
            require(program["pid"] == ready["pid"] and program["firmware_sha256"] == ready["firmware_sha256"], "program changed process or firmware")

        def submit(name, content, *, history_state, activated=False, reused=False):
            nonlocal expected
            payload = package_payload(content, expected) if isinstance(content, dict) else {"source": content, "expected_execution_id": expected, "timeout_seconds": 20}
            started = time.monotonic()
            result = client.json(prefix + "/program", "POST", payload)
            result["request_seconds"] = time.monotonic() - started
            program = result["program"]
            same_guest(program)
            expected = program["execution_id"]
            submitted[name] = content
            result.update(expected_history_state=history_state, activated=activated, reused=reused)
            report["executions"][name] = result
            if activated:
                require(program["revision_id"] == revision_id(content), "submitted package revision differs")
                require(program.get("deployment", {}).get("phase") == "activated"
                        and program["deployment"]["inventory"] == file_inventory(content)
                        and program["deployment"].get("reused") is reused, "guest deployment receipt differs")
            save(args.out_dir / f"program-{name}.json", result)
            return program

        def before_serial():
            return client.json(prefix + "/serial?offset=0&limit=1048576")

        def observe(before, *, version=None, value=None, marker=None, extra=None, allow_failed=False, forbidden=()):
            def sample():
                current = client.json(prefix)
                require(current["state"] == "running" and current["pid"] == ready["pid"], "guest stopped or changed during observation")
                program = client.json(prefix + "/program")["program"]
                require(program["execution_id"] == expected, "another client replaced the expected execution")
                if not allow_failed:
                    require(program["state"] not in {"failed", "unknown", "cancelled"}, "guest application failed: " + str(program))
                return client.json(prefix + f"/serial?offset={before['next_offset']}&limit=1048576")
            expected_fields = (expected_sample(version, args.unit, value) if value is not None else
                               {"version": version, "helper": VERSIONS[version]["helper"], "init": VERSIONS[version]["init"], "logic": VERSIONS[version]["logic"], "old_absent": version != "A"}) if version else None
            line_prefix = "LIVE_PACKAGE_SAMPLE " if value is not None else "LIVE_PACKAGE_READY "
            def matches(row):
                return ((marker is None or marker in row["data"])
                        and (expected_fields is None or matching_json_line(row["data"], line_prefix, expected_fields) is not None))
            window = poll(sample, matches, 60)
            require(all(item not in window["data"] for item in forbidden), "rejected package ran application code")
            row = {"execution_id": expected, "offset": before["next_offset"], "prefix_sha256": sha(before["data"].encode()),
                   "window": window, "offset_encoding": "raw UART bytes; JSON data UTF-8 errors=replace", **(extra or {})}
            if expected_fields is not None:
                row.update(line_prefix=line_prefix, expected=expected_fields)
            if marker is not None:
                row["marker"] = marker
            if forbidden:
                row["forbidden"] = list(forbidden)
            report["serial_observations"].append(row)
            return window

        def finite_done(program):
            def state():
                current = client.json(prefix + "/program")["program"]
                require(current["execution_id"] == program["execution_id"] and current["state"] not in {"failed", "unknown", "interrupted"}, "finite execution failed or changed")
                return current
            return poll(state, lambda row: row["state"] == "completed", 60)

        def reject(name, files, error_code, *, stale=False):
            nonlocal expected
            before = before_serial()
            previous_id = expected
            payload = package_payload(files, None if stale else expected)
            try:
                client.json(prefix + "/program", "POST", payload)
            except RuntimeError as error:
                rejected = decode_rejection(error)
            else:
                raise RuntimeError("negative package was accepted: " + name)
            require(rejected["status"] == 409 and rejected["response"]["error"]["code"] == error_code, "unexpected package rejection: " + str(rejected))
            current = client.json(prefix + "/program")
            program = current["program"]
            same_guest(program)
            if stale:
                require(program["execution_id"] == previous_id and program["state"] == "running", "stale request interrupted/replaced the active application")
            else:
                expected = program["execution_id"]
                require(expected != previous_id and rejected["response"]["error"].get("execution_id") == expected
                        and program["state"] == "failed" and program.get("error", {}).get("code") == error_code, "failed package execution identity/state differs")
                current.update(expected_history_state="failed", activated=False, error_code=error_code)
                report["executions"][name] = current
                submitted[name] = files
                save(args.out_dir / f"program-{name}.json", current)
                forbidden = [f"__M5_EXEC_{expected}__:START", "LIVE_PACKAGE_READY "]
                observe(before, allow_failed=True, forbidden=forbidden)
            report["negative_controls"][name] = rejected
            save(args.out_dir / f"rejected-{name}.json", rejected)
            return program

        before = before_serial()
        finite = submit("finite", f"import sys\nsys.path.append({NONCE_PREFIX + nonce!r})\nprint('LIVE_PACKAGE_FINITE_DONE')\n", history_state="completed")
        finite_done(finite)
        observe(before, marker="LIVE_PACKAGE_FINITE_DONE")

        for version in ("A", "B"):
            before = before_serial()
            program = submit(version.lower(), packages[version], history_state="interrupted", activated=True)
            window = observe(before, version=version)
            receipt = matching_json_line(window["data"], "LIVE_PACKAGE_READY ", {"version": version})
            require(receipt["cwd"] == GUEST_BASE + "/" + program["revision_id"] and receipt["managed_paths"] == [receipt["cwd"]], "guest import path did not switch to the complete package")
            if version == "B":
                require({"helper", "lib", "lib.logic", "namespace_lib", "namespace_lib.state", "old_only"} <= set(program["deployment"]["removed_modules"]), "A modules were not removed before B imports")
            phase = {"version": version, "execution_id": expected, "guest_ready": receipt, "inputs": []}
            report["phases"].append(phase)
            for value in ((0, 1, 0) if args.unit == "pir" else (int(VERSIONS[version]["relay"]),)):
                before = before_serial()
                if args.unit == "pir":
                    posted = client.json(prefix + "/unit-input", "POST", {"id": "external1", "values": {"motion": bool(value)}})
                    require(live_unit(posted, session_id, args.unit).get("motion") is bool(value), "PIR POST did not reach its QOM model")
                window = observe(before, version=version, value=value)
                qom = client.json(prefix + "/units")
                properties = live_unit(qom, session_id, args.unit)
                field = "motion" if args.unit == "pir" else "output-level"
                require(properties.get(field) is bool(value), "independent QOM readback differs from guest input/output")
                frame = client.raw(prefix + "/frame.png")
                metrics = frame_observation(frame, report["expected_frame_size"], version)
                frame_name = f"frame-{version.lower()}-{len(phase['inputs'])}.png"
                (args.out_dir / frame_name).write_bytes(frame)
                phase["inputs"].append({"value": value, "serial_window": window, "qom": qom, "frame": {"path": frame_name, **metrics}})
            save(args.out_dir / f"phase-{version.lower()}.json", phase)

        reject("stale", packages["B"], "program_generation_conflict", stale=True)
        syntax_files = {**packages["B"], "main.py": b"def broken(:\n"}
        before = before_serial()
        syntax = submit("syntax", syntax_files, history_state="failed", activated=True)
        poll(lambda: client.json(prefix + "/program"), lambda row: row["program"]["state"] == "failed", 60)
        observe(before, marker="SyntaxError", allow_failed=True,
                forbidden=(f"__M5_EXEC_{syntax['execution_id']}__:START", "LIVE_PACKAGE_READY "))
        before = before_serial()
        submit("b-recovery", packages["B"], history_state="interrupted", activated=True, reused=True)
        observe(before, version="B")

        for name, byte_index, value in (("mpy-major", 1, 7), ("mpy-smallint", 3, 32)):
            binary = bytearray(packages["B"]["helper.mpy"])
            binary[byte_index] = value
            reject(name, {**packages["B"], "helper.mpy": bytes(binary)}, "program_mpy_incompatible")

        before = before_serial()
        extra_directory = GUEST_BASE + "/" + revision_id(packages["B"]) + "/extra_empty_namespace"
        extra_source = f"import os\nos.mkdir({extra_directory!r})\nprint('LIVE_PACKAGE_EXTRA_DIRECTORY')\n"
        extra = submit("extra-directory", extra_source, history_state="completed")
        finite_done(extra)
        observe(before, marker="LIVE_PACKAGE_EXTRA_DIRECTORY")
        reject("extra-directory-integrity", packages["B"], "program_package_integrity")

        before = before_serial()
        target = GUEST_BASE + "/" + revision_id(packages["B"]) + "/config.json"
        tamper_source = f'''import os, sys, json, hashlib, binascii
assert {NONCE_PREFIX + nonce!r} in sys.path
os.rmdir({extra_directory!r})
with open({target!r}, 'ab') as stream:
 assert stream.write(b' ') == 1
with open({target!r}, 'rb') as stream:
 data = stream.read()
print('LIVE_PACKAGE_TAMPERED ' + json.dumps({{'sha256': binascii.hexlify(hashlib.sha256(data).digest()).decode(), 'size': len(data)}}))
'''
        tamper = submit("tamper", tamper_source, history_state="completed")
        finite_done(tamper)
        window = observe(before, marker="LIVE_PACKAGE_TAMPERED ")
        changed = packages["B"]["config.json"] + b" "
        require(matching_json_line(window["data"], "LIVE_PACKAGE_TAMPERED ", {"size": len(changed), "sha256": sha(changed)}) is not None,
                "legacy source did not confirm the exact guest mutation")
        rejected = reject("integrity", packages["B"], "program_package_integrity")
        require(rejected["deployment"]["phase"] == "capabilities"
                and rejected["deployment"]["capabilities"]["existing"] is True, "tampered cache was not rejected on a verified reuse attempt")

        before = before_serial()
        final = submit("c-recovery", packages["C"], history_state="running", activated=True)
        observe(before, version="C")
        value = 0
        if args.unit == "pir":
            client.json(prefix + "/unit-input", "POST", {"id": "external1", "values": {"motion": False}})
        before = before_serial()
        observe(before, version="C", value=value)
        final_qom = client.json(prefix + "/units")
        properties = live_unit(final_qom, session_id, args.unit)
        require(properties["motion" if args.unit == "pir" else "output-level"] is False, "recovered C Unit state differs")
        save(args.out_dir / "units-c.json", final_qom)
        frame = client.raw(prefix + "/frame.png")
        (args.out_dir / "frame-c.png").write_bytes(frame)
        report["final_frame"] = frame_observation(frame, report["expected_frame_size"], "C")
        require(final["deployment"]["capabilities"]["directory_count"] <= 3, "negative controls exhausted guest package directories")
        report["final_runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        current = client.json(prefix)
        require(current["state"] == "running" and current["pid"] == ready["pid"] and current["firmware_sha256"] == ready["firmware_sha256"]
                and current.get("worker") == ready.get("worker"), "guest process, firmware or worker changed")
        report["final_program"] = client.json(prefix + "/program")
        bundle = client.raw(prefix + "/evidence")
        (args.out_dir / "evidence.zip").write_bytes(bundle)
        report["evidence"] = validate_bundle(bundle, report, submitted)
        report.update(status="PASS", checks={"same_entrypoint_different_modules_config_assets": True,
            "compiled_mpy_imported_in_guest": True, "removed_module_and_old_import_paths_absent": True,
            "fresh_serial_independent_qom_and_png": True, "syntax_error_and_cached_b_recovery": True,
            "mpy_capability_and_stale_execution_rejected": True, "guest_mutation_rejected_before_app": True,
            "new_c_recovered": True, "same_process_firmware_vm_and_banner": True,
            "zip_original_bytes_guest_inventory_and_executions": True})
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
                if stopped["state"] not in {"stopped", "failed"}:
                    stopped = poll(lambda: client.json(f"sessions/{session_id}"), lambda row: row["state"] in {"stopped", "failed"}, 45)
                save(args.out_dir / "stopped.json", stopped)
                require(stopped["state"] == "stopped" and stopped.get("flash_retained") is False
                        and stopped.get("last_frame_available") is True, "session stop/history frame/Flash release was not confirmed")
                report["cleanup"] = {"state": "stopped", "flash_retained": False, "history_retained": True, "last_frame_available": True}
            except Exception as error:
                report.update(status="FAIL", cleanup_error=str(error))
        save(args.out_dir / "report.json", report)
    require(report["status"] == "PASS", report.get("error") or report.get("cleanup_error") or report.get("evidence_error") or "package validation failed")
    print(json.dumps({"status": "PASS", "device_id": args.device, "unit_id": args.unit, "session_id": session_id,
                      "executions": len(report["executions"]), "package_directories": 4}))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--device", choices=DEVICES, default="cores3")
    parser.add_argument("--unit", choices=("pir", "relay"), default="pir")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--expected-runtime-sha256")
    parser.add_argument("--mpy-cross", type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "PLANNED_NOT_EXECUTED", "device_id": args.device, "unit_id": args.unit,
            "program_mode": "uiflow-live", "api": args.api, "versions": ["A", "B", "C"],
            "same_main_py": True, "files": ["main.py", "config.json", "helper.mpy", "lib/__init__.py", "lib/logic.py", "namespace_lib/state.py", "assets/pixel.png", "old_only.py (A only)"],
            "package_directories": 4, "guest_directory_limit": 64,
            "negative_controls": ["stale execution", "SyntaxError", "incompatible mpy major/small-int", "extra empty namespace directory", "mutated existing guest file"],
            "guest_execution": "NOT RUN", "hardware_validation": "NOT RUN"}, indent=2))
        return
    if args.out_dir is None or args.mpy_cross is None or not re.fullmatch(r"[0-9a-f]{64}", args.expected_runtime_sha256 or ""):
        parser.error("--execute requires a new --out-dir, exact --expected-runtime-sha256 and explicit --mpy-cross")
    if args.out_dir.exists() or not args.mpy_cross.is_file() or not os.access(args.mpy_cross, os.X_OK):
        parser.error("--out-dir must not exist and --mpy-cross must be an existing executable file")
    run(args)


if __name__ == "__main__":
    main()
