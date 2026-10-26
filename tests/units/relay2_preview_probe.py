#!/usr/bin/env python3
"""Offline source, observation and evidence gates for the U131 Preview runner.

Default plan is pure: no network, guest, subprocess, or filesystem mutation.
The bundled original driver retains its MIT/SPDX notice and exact source bytes.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import sys
import zipfile

DEVICES = ("cores3", "atoms3r", "sticks3", "stopwatch")
PORTS = {"cores3": "port-a", "atoms3r": "custom", "sticks3": "custom", "stopwatch": "port-a"}
PINS = {"cores3": {"white": 1, "yellow": 2}, "atoms3r": {"white": 1, "yellow": 2},
        "sticks3": {"white": 10, "yellow": 9}, "stopwatch": {"white": 11, "yellow": 10}}
CONTROLS = {"cores3": "touch-halves", "stopwatch": "touch-halves", "sticks3": "buttons-ab", "atoms3r": "button-a-gray-cycle"}
PHASES = ("00", "10", "01", "11", "interactive")
PREFIX = "PREVIEW_RELAY2 "
DRIVER_SHA256 = "db05e974f2cd558c4fbaef85958b82730a9bcae1b21eb9646371bea7e6f273c5"
DRIVER_URL = "https://raw.githubusercontent.com/m5stack/uiflow-micropython/50e440780492aa847378c7d3477ab912f7063bac/m5stack/libs/unit/relay2.py"
DRIVER_SIZE = 1512
GUEST_BASE = "/flash/.m5-live-packages"
RESOURCE = bytes([0, 255, 1, 128, 13, 10, 77, 53])
FRAME_COLORS = (0x000000, 0x00FF00, 0xFF0000, 0x0000FF)
# Original upstream source; do not reformat, translate or silently fix its API.
OFFICIAL_DRIVER = b'''# SPDX-FileCopyrightText: 2024 M5Stack Technology CO LTD
#
# SPDX-License-Identifier: MIT
from machine import Pin


class Relay2Unit:
    """Create an Relay2Unit object.

    :param tuple port: The port of the relay.

    UiFlow2 Code Block:

        |init.png|

    MicroPython Code Block:

        .. code-block:: python

            from unit import Relay2Unit

            relay2_0 = Relay2Unit((32, 26))
    """

    def __init__(self, port: tuple) -> None:
        self._relay1 = Pin(port[0], Pin.OUT)
        self._relay2 = Pin(port[1], Pin.OUT)

    def set_relay_cntrl(self, num: int = 1, control: int = 0) -> None:
        """Set the on/off status of a relay

        :param int num: The relay number(the range is 1-2).
        :param int control: The control value(0: off, 1: on).

        UiFlow2 Code Block:

            |set_relay_cntrl.png|

        MicroPython Code Block:

            .. code-block:: python

                relay2_0.set_relay_cntrl(1, 1)
        """
        self._relay1(control) if num == 1 else self._relay2(control)

    def get_relay_status(self, num: int = 1) -> bool:
        """Getting the on/off status of a relay

        :param int num: The relay number.
        :returns: relay status.
        :rtype: bool

        UiFlow2 Code Block:

            |get_relay_status.png|

        MicroPython Code Block:

            .. code-block:: python

                relay2_0.get_relay_status()
        """
        return bool(self._relay1() if num == 1 else self._relay2())
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def attest_driver(value=OFFICIAL_DRIVER, declared_sha256=DRIVER_SHA256):
    require(type(value) is bytes and len(value) == DRIVER_SIZE and sha(value) == DRIVER_SHA256
            and declared_sha256 == DRIVER_SHA256, "official driver source bytes/hash mismatch")
    return {"size": len(value), "sha256": sha(value), "source": DRIVER_URL}


def frozen_pins(device, pins):
    require(device in DEVICES, "unadmitted host")
    require(type(pins) is dict and set(pins) == {"white", "yellow"}
            and all(type(v) is int for v in pins.values()) and pins == PINS[device], "host pin tuple mismatch")
    return pins


def nonce_path(nonce):
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce), "invalid nonce")
    return "/m5-preview-relay2-" + nonce


def plan(device):
    require(device in DEVICES, "unadmitted host")
    return {"category": "managed-preview-2relay-plan", "status": "NOT RUN", "device_id": device,
            "api_contacted": False, "guests_started": 0, "hardware": "NOT RUN",
            "attachments": [{"id": "relay2", "unit_id": "2relay", "port_id": PORTS[device]}],
            "pins": PINS[device], "driver_port_tuple": [PINS[device]["white"], PINS[device]["yellow"]],
            "official_driver": attest_driver(), "programs": ["builtin import compatibility and same-VM nonce", *PHASES, "interactive after confirmed cancel"],
            "host_control": CONTROLS[device], "reverse_unit_inputs": {},
            "observations": ["public complete checkpoint then same-VM Preview Run", "guest original source __file__/size/SHA256",
                             "independent machine.Pin pad reads, two raw QOM levels/counters", "mounted led-1/2 with physical channel binding",
                             "four 00/10/01/11 states, repeated writes without transitions, independent channel transitions",
                             "five frame headers and exact PNG SHA256", "cancel, new Run, nonce/PID/firmware preserved"],
            "cleanup": ["evidence ZIP before close", "retained stopped history and last frame", "Flash released", "PID gone", "session/worker leases zero"],
            "limits": ["virtual nominal powered GPIO indication only", "builtin frozen import is compatibility, not original-source attestation",
                       "no NO/NC/load/coil timing/electrical or physical-hardware claim", "interrupt-only; no arbitrary native/IRQ/thread cleanup guarantee"]}


def seed_package(nonce):
    source = "import sys,json\nfrom unit import Relay2Unit\nassert callable(Relay2Unit.set_relay_cntrl) and callable(Relay2Unit.get_relay_status)\nsys.path.append(%r)\nprint(%r+json.dumps({'kind':'seed','nonce':%r,'builtin_compatible':True,'builtin_source_attested':False}))\n" % (nonce_path(nonce), PREFIX, nonce)
    compile(source, "main.py", "exec")
    return {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {"main.py": {"encoding": "utf8", "data": source}}}


MAIN = r'''import os,sys,json,time,binascii,hashlib
import M5
from machine import Pin
import relay2_official
assert __NONCE_PATH__ in sys.path, 'MicroPython VM nonce lost'
with open('settings.json') as stream:
 config = json.load(stream)
with open('assets/state.bin','rb') as stream:
 resource = stream.read()
assert resource == __RESOURCE__, 'resource bytes changed'
cwd = os.getcwd()
assert relay2_official.__file__ == cwd + '/relay2_official.py', 'stale or frozen driver module'
with open(relay2_official.__file__,'rb') as stream:
 driver_bytes = stream.read()
driver_hash = binascii.hexlify(hashlib.sha256(driver_bytes).digest()).decode()
assert len(driver_bytes) == __DRIVER_SIZE__ and driver_hash == __DRIVER_SHA__, 'official source bytes changed'
phase = config['phase']
white,yellow = config['pins']['white'],config['pins']['yellow']
initial_pads = [int(Pin(white).value()),int(Pin(yellow).value())]
M5.begin()
screen = M5.Display
screen.setBrightness(255)
screen.fillScreen(0)
screen.setTextColor(0xFFFFFF,0)
screen.setTextSize(1)
relay = relay2_official.Relay2Unit((white,yellow))
levels = [0,0] if phase == 'interactive' else [int(c) for c in phase]
relay.set_relay_cntrl(1,levels[0])
relay.set_relay_cntrl(2,levels[1])
identity = {'nonce':config['nonce'],'phase':phase,'device':config['device'],'pins':[white,yellow],
 'cwd':cwd,'driver_file':relay2_official.__file__,'driver_sha256':driver_hash,'driver_size':len(driver_bytes),'resource_hex':binascii.hexlify(resource).decode()}
ready = dict(identity)
ready['kind'] = 'ready'
print('PREVIEW_RELAY2 '+json.dumps(ready))
sequence = 0
events = 0
last_touch = False
last_a = False
last_b = False
gray = 0
last_drawn = None
while True:
 M5.update()
 host_pressed = {'a':False,'b':False,'touch':False}
 if config['control'] == 'touch-halves':
  host_pressed['touch'] = bool(M5.Touch.getCount())
 else:
  host_pressed['a'] = bool(M5.BtnA.isPressed())
  if config['control'] == 'buttons-ab':
   host_pressed['b'] = bool(M5.BtnB.isPressed())
 if phase == 'interactive':
  if config['control'] == 'touch-halves':
   pressed = host_pressed['touch']
   if pressed and not last_touch:
    channel = 0 if M5.Touch.getX() < screen.width()//2 else 1
    levels[channel] = 1-levels[channel]
    events += 1
   last_touch = pressed
  else:
   a = host_pressed['a']
   if config['control'] == 'button-a-gray-cycle':
    if a and not last_a:
     gray = (gray+1)%4
     levels = [[0,0],[1,0],[1,1],[0,1]][gray]
     events += 1
   else:
    b = host_pressed['b']
    if a and not last_a:
     levels[0] = 1-levels[0]
     events += 1
    if b and not last_b:
     levels[1] = 1-levels[1]
     events += 1
    last_b = b
   last_a = a
 # Repeat both original-driver writes continuously. Unchanged pad levels must
 # not be counted as transitions or leak to the other independent channel.
 relay.set_relay_cntrl(1,levels[0])
 relay.set_relay_cntrl(2,levels[1])
 pads = [int(Pin(white).value()),int(Pin(yellow).value())]
 statuses = [relay.get_relay_status(1),relay.get_relay_status(2)]
 assert pads == levels and statuses == [bool(n) for n in levels], 'cross-channel pad mismatch'
 if levels != last_drawn:
  screen.fillRect(0,0,screen.width(),42,0)
  screen.setCursor(4,4)
  screen.print('RELAY1 %d RELAY2 %d' % (levels[0],levels[1]))
  screen.setCursor(4,20)
  screen.print('U131 '+phase)
  color = __FRAME_COLORS__[levels[0]*2+levels[1]]
  screen.fillRect(screen.width()//2-4,screen.height()//2-4,8,8,color)
  last_drawn = list(levels)
 sequence += 1
 sample = dict(identity)
 sample.update({'kind':'sample','sequence':sequence,'events':events,'levels':[bool(n) for n in levels],
  'pads':pads,'statuses':statuses,'initial_pads':initial_pads,'written':[int(n) for n in levels],'host_pressed':host_pressed})
 print('PREVIEW_RELAY2 '+json.dumps(sample))
 time.sleep_ms(200)
'''


def build_package(nonce, device, pins, phase, driver=OFFICIAL_DRIVER, driver_sha256=DRIVER_SHA256):
    nonce_path(nonce); frozen_pins(device, pins); attest_driver(driver, driver_sha256)
    require(phase in PHASES, "invalid relay phase")
    source = MAIN.replace("__NONCE_PATH__", repr(nonce_path(nonce))).replace("__RESOURCE__", repr(RESOURCE))
    source = source.replace("__DRIVER_SIZE__", str(DRIVER_SIZE)).replace("__DRIVER_SHA__", repr(DRIVER_SHA256))
    source = source.replace("__FRAME_COLORS__", repr(FRAME_COLORS))
    compile(source, "main.py", "exec")
    config = {"phase": phase, "nonce": nonce, "device": device, "pins": pins, "control": CONTROLS[device]}
    return {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {
        "main.py": {"encoding": "utf8", "data": source},
        "relay2_official.py": {"encoding": "base64", "data": base64.b64encode(driver).decode()},
        "settings.json": {"encoding": "utf8", "data": canonical(config).decode()},
        "assets/state.bin": {"encoding": "base64", "data": base64.b64encode(RESOURCE).decode()}}}


def decoded_files(payload):
    require(type(payload) is dict and payload.get("source_kind") == "uiflow2-package" and payload.get("entrypoint") == "main.py"
            and type(payload.get("files")) is dict, "package shape")
    result = {}
    for path, row in payload["files"].items():
        require(type(path) is str and not PurePosixPath(path).is_absolute() and ".." not in path.split("/") and "\\" not in path, "package path")
        require(type(row) is dict and set(row) == {"encoding", "data"} and type(row["data"]) is str, "file encoding shape")
        require(row["encoding"] in ("utf8", "base64"), "file encoding")
        result[path] = row["data"].encode() if row["encoding"] == "utf8" else base64.b64decode(row["data"], validate=True)
    return result


def revision_id(payload):
    files = decoded_files(payload)
    return sha(canonical({"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {p: sha(v) for p,v in sorted(files.items())}}))


def package_contract(payload, nonce, device, pins, phase):
    files = decoded_files(payload)
    require("relay2_official.py" in files, "original driver missing")
    attest_driver(files["relay2_official.py"])
    require(files == decoded_files(build_package(nonce, device, pins, phase)), "generated source/config/resource mismatch")
    return {"status": "PASS", "revision_id": revision_id(payload), "files": {p: {"size": len(v), "sha256": sha(v)} for p,v in sorted(files.items())}}


def identity(row, nonce, phase, device, revision):
    require(type(row) is dict and row.get("nonce") == nonce and row.get("phase") == phase and row.get("device") == device, "sample identity")
    require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{64}", revision), "revision identity")
    require(row.get("pins") == [PINS[device]["white"], PINS[device]["yellow"]]
            and all(type(n) is int for n in row["pins"]), "guest pin tuple")
    cwd = GUEST_BASE + "/" + revision
    require(row.get("cwd") == cwd and row.get("driver_file") == cwd + "/relay2_official.py"
            and row.get("driver_sha256") == DRIVER_SHA256 and type(row.get("driver_size")) is int
            and row["driver_size"] == DRIVER_SIZE and row.get("resource_hex") == RESOURCE.hex(), "guest source/resource attestation")


def typed_sample(row, nonce, phase, device, revision):
    identity(row, nonce, phase, device, revision)
    require(row.get("kind") == "sample" and type(row.get("sequence")) is int and row["sequence"] > 0
            and type(row.get("events")) is int and row["events"] >= 0, "sample sequence/event types")
    require(type(row.get("host_pressed")) is dict and set(row["host_pressed"]) == {"a", "b", "touch"}
            and all(type(v) is bool for v in row["host_pressed"].values()), "host pressed types")
    for field in ("levels", "statuses"):
        require(type(row.get(field)) is list and len(row[field]) == 2 and all(type(v) is bool for v in row[field]), "relay status types")
    for field in ("pads", "initial_pads", "written"):
        require(type(row.get(field)) is list and len(row[field]) == 2 and all(type(v) is int and v in (0,1) for v in row[field]), "relay pad/write types")
    require(row["levels"] == row["statuses"] == [bool(v) for v in row["pads"]] == [bool(v) for v in row["written"]], "independent relay readback")
    if phase != "interactive":
        require(row["written"] == [int(v) for v in phase] and row["events"] == 0, "fixed combination differs")
    return row


def parse_window(text, execution, nonce, phase, device, revision, *, require_ready=False, fresh_text=None):
    require(type(text) is str and isinstance(execution, str) and re.fullmatch(r"[0-9a-f]{32}", execution), "serial window identity")
    require(device in DEVICES and phase in PHASES, "serial host/phase")
    marker = "__M5_EXEC_" + execution + "__:START"
    position = text.find(marker)
    if position < 0:
        return None
    tail = text[position+len(marker):]
    require(not tail or tail.startswith(("\r\n", "\n")), "execution marker delimiter")
    # A later execution cannot donate observations to this execution.
    tail = tail.split("__M5_EXEC_", 1)[0]
    def rows(value):
        result = []
        for line in value.splitlines(keepends=True):
            if line.endswith("\n") and line.startswith(PREFIX):
                try: result.append(json.loads(line[len(PREFIX):]))
                except ValueError: pass
        return result
    complete = rows(tail)
    ready = False
    for row in complete:
        if type(row) is dict and row.get("kind") == "ready" and row.get("nonce") == nonce and row.get("phase") == phase:
            identity(row, nonce, phase, device, revision)
            ready = True
    if fresh_text is not None:
        require(type(fresh_text) is str and "__M5_EXEC_" not in fresh_text, "fresh input window crossed execution")
    candidates = complete if fresh_text is None else rows(fresh_text)
    for row in reversed(candidates):
        if type(row) is dict and row.get("kind") == "sample" and row.get("nonce") == nonce and row.get("phase") == phase:
            typed_sample(row, nonce, phase, device, revision)
            return None if require_ready and not ready else {"ready": ready, "sample": row}
    return None


def counter_contract(before, after, changed=None):
    fields = ["output-1-transitions", "output-2-transitions", "output-transitions"]
    for value in (before, after):
        require(type(value) is dict and all(type(value.get(k)) is int and value[k] >= 0 for k in fields), "counter evidence types")
        require(value[fields[2]] == value[fields[0]] + value[fields[1]], "counter sum")
    expected = [0,0] if changed is None else ([1,0] if changed == 1 else [0,1] if changed == 2 else None)
    require(expected is not None and [after[k]-before[k] for k in fields[:2]] == expected
            and after[fields[2]]-before[fields[2]] == sum(expected), "independent transition delta")
    return {"status": "PASS", "channel_delta": expected}


def frame_contract(raw, headers, expected):
    require(type(raw) is bytes and raw.startswith(b"\x89PNG\r\n\x1a\n"), "frame PNG bytes")
    headers = {k.lower(): v for k,v in headers.items()}
    values = {"x-preview-id": expected["preview_id"], "x-run-id": expected["run_id"],
              "x-frame-execution-id": expected["execution_id"], "x-frame-revision-id": expected["revision_id"], "x-frame-sha256": sha(raw)}
    require(all(headers.get(k) == v for k,v in values.items()), "five frame identities/hash")
    return {"status": "PASS", "sha256": sha(raw), "bytes": len(raw)}


def frame_color(levels):
    require(type(levels) is list and len(levels) == 2 and all(type(v) is bool for v in levels), "frame level types")
    color = FRAME_COLORS[int(levels[0])*2 + int(levels[1])]
    return {"color_rgb888": color, "rgb": [(color >> shift) & 255 for shift in (16, 8, 0)]}


def cleanup_contract(value):
    require(type(value) is dict, "cleanup record")
    closed, stopped, capacity = (value.get(k) for k in ("preview", "session", "capacity"))
    require(type(closed) is dict and closed.get("state") == "closed", "Preview not closed")
    require(type(stopped) is dict and stopped.get("state") == "stopped" and stopped.get("flash_retained") is False, "session/Flash cleanup")
    require(closed.get("session_id") == stopped.get("session_id") == value.get("session_id"), "cleanup identity")
    require(value.get("pid_gone") is True and value.get("zip_before_close") is True, "owned PID/evidence order")
    require(type(capacity) is dict and type(capacity.get("active_sessions")) is int and capacity["active_sessions"] == 0
            and type(capacity.get("worker", {}).get("active_lease_count")) is int and capacity["worker"]["active_lease_count"] == 0, "capacity/lease cleanup")
    require(value.get("history_frame_sha256") == value.get("last_frame_sha256") and isinstance(value.get("last_frame_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["last_frame_sha256"]), "history last frame evidence")
    return {"status": "PASS", "history_retained": True, "last_frame_retained": True, "flash_released": True, "owned_pid_gone": True}


def inspect_zip(raw, expected):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate ZIP members")
        for name in names:
            require(not PurePosixPath(name).is_absolute() and ".." not in name.split("/") and "\\" not in name
                    and (archive.getinfo(name).external_attr >> 16) & 0xf000 != 0xa000, "unsafe ZIP paths")
        require(archive.testzip() is None, "ZIP CRC")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(manifest["files"]) == set(names)-{"manifest.json"}, "ZIP manifest membership")
        for name,row in manifest["files"].items():
            value = archive.read(name)
            require(row == {"size": len(value), "sha256": sha(value)}, "ZIP member size/hash")
        require({"serial.log", "frames/current.png", "qom/snapshot.json", "units/contract.json", "units/state.json", "units/runtime.json"} <= set(names), "ZIP runtime evidence missing")
        for field in ("session_id", "device_id", "firmware_sha256", "pid"):
            require(manifest["session"].get(field) == expected[field], "ZIP session identity")
        for run in expected["runs"]:
            execution = json.loads(archive.read("programs/"+run["execution_id"]+".json"))
            require(all(execution.get(k) == run[k] for k in ("execution_id", "revision_id"))
                    and execution.get("pid") == expected["pid"] and execution.get("firmware_sha256") == expected["firmware_sha256"], "ZIP execution/VM identity")
            payload = expected["packages"][run["revision_id"]]
            files = decoded_files(payload)
            require(revision_id(payload) == run["revision_id"], "ZIP expected revision binding")
            prefix = "programs/"+run["revision_id"]+"/"
            source = json.loads(archive.read(prefix+"source.json"))
            require(source.get("entrypoint") == "main.py" and set(source["files"]) == set(files), "ZIP package source members")
            meta = json.loads(archive.read(prefix+"revision.json"))
            inventory = {p: {"size":len(v), "sha256":sha(v)} for p,v in files.items()}
            require(meta.get("revision_id") == run["revision_id"] and meta.get("source_kind") == "uiflow2-package"
                    and {r["path"]: {"size":r["size"],"sha256":r["sha256"]} for r in meta["files"]} == inventory, "ZIP package metadata")
            for path,value in files.items():
                row = source["files"][path]
                require(row.get("encoding") == "base64" and base64.b64decode(row["data"], validate=True) == value
                        and archive.read(prefix+"files/"+path) == value, "ZIP original file bytes")
        return {"status": "PASS", "members":len(names), "sha256":sha(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "seed", "package", "package-check", "revision", "parse", "counters", "frame", "frame-color", "cleanup", "zip"], nargs="?", default="plan")
    parser.add_argument("--device", choices=DEVICES, default="cores3")
    args = parser.parse_args()
    if args.action == "plan": result = plan(args.device)
    else:
        line = sys.stdin.readline()
        require(line.endswith("\n"), "one newline-terminated JSON input required")
        data = json.loads(line)
        if args.action == "seed": result = seed_package(data["nonce"])
        elif args.action == "package": result = build_package(data["nonce"], args.device, data["pins"], data["phase"])
        elif args.action == "package-check": result = package_contract(data["payload"], data["nonce"], args.device, data["pins"], data["phase"])
        elif args.action == "revision": result = {"revision_id": revision_id(data)}
        elif args.action == "parse": result = parse_window(device=args.device, **data)
        elif args.action == "counters": result = counter_contract(**data)
        elif args.action == "frame": result = frame_contract(base64.b64decode(data["bytes"], validate=True), data["headers"], data["expected"])
        elif args.action == "frame-color": result = frame_color(data["levels"])
        elif args.action == "cleanup": result = cleanup_contract(data)
        else: result = inspect_zip(base64.b64decode(data["bytes"], validate=True), data["expected"])
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
