#!/usr/bin/env python3
"""Pure package/observation contracts for the managed Preview control cohort.

No network, guest, process creation, or files are mutated by this module.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEVICES = ("cores3", "atoms3r", "sticks3", "stopwatch")
PORTS = {"cores3": "port-a", "atoms3r": "custom", "sticks3": "custom", "stopwatch": "port-a"}
COLORS = {"A": 0xFF0000, "B": 0x00FF00, "C": 0x0000FF}
PREFIX = "PREVIEW_CONTROLS "
RESOURCE = bytes([0, 255, 1, 128, 13, 10, 77, 53])
OFFICIAL = {
    "encoder": "m5stack/libs/unit/encoder.py",
    "8encoder": "m5stack/libs/unit/encoder8.py",
    "joystick-v11": "m5stack/libs/unit/joystick.py",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def attachments(device):
    require(device in DEVICES, "unadmitted host")
    return [{"id": "hub1", "unit_id": "hub", "port_id": PORTS[device]},
            {"id": "encoder", "unit_id": "encoder", "parent_id": "hub1", "port_id": "grove-1"},
            {"id": "eight", "unit_id": "8encoder", "parent_id": "hub1", "port_id": "grove-2"},
            {"id": "joystick", "unit_id": "joystick-v11", "parent_id": "hub1", "port_id": "grove-3"}]


def plan(device):
    return {"category": "managed-preview-controls-plan", "status": "NOT RUN", "device_id": device,
            "api_contacted": False, "guests_started": 0, "hardware": "NOT RUN", "attachments": attachments(device),
            "addresses": [0x40, 0x41, 0x52], "official_driver_paths": OFFICIAL,
            "programs": ["seed nonce", "A API complete checkpoint", "B Web main.py edit retaining dependencies", "C after confirmed cancel"],
            "positive_input": "trusted DOM pointer hold/release on Encoder and 8Encoder; Joystick raw form fill/Tab",
            "observations": ["current execution START then typed READY/SAMPLE", "fresh per-leaf raw QOM",
                             "five frame headers plus exact PNG SHA", "actual mounted 2+9 uniform LEDs/material/glow; joints stay still"],
            "cleanup": ["evidence ZIP before Preview close", "closed retained session", "Flash released", "owned PID gone", "session/lease zero"],
            "limits": ["no implicit inheritance across hosts", "no physical angle/tilt or asymmetric LED binding",
                       "main.py only; fresh globals and interrupt-only", "no native/IRQ/thread cleanup guarantee"]}


def nonce_path(nonce):
    require(isinstance(nonce, str) and re.fullmatch(r"[0-9a-f]{32}", nonce), "invalid nonce")
    return "/m5-preview-controls-" + nonce


def seed_package(nonce):
    source = "import sys,json\nsys.path.append(%r)\nprint(%r+json.dumps({'kind':'seed','nonce':%r}))\n" % (nonce_path(nonce), PREFIX, nonce)
    return {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {"main.py": {"encoding": "utf8", "data": source}}}


MAIN = '''import sys,json,time,binascii
import M5
from machine import I2C, Pin
from unit import EncoderUnit, Encoder8Unit, JoystickUnit
from logic import feedback
assert __NONCE_PATH__ in sys.path, 'MicroPython VM nonce lost'
with open('settings.json') as stream:
 config = json.load(stream)
with open('assets/state.bin', 'rb') as stream:
 resource = stream.read()
assert resource == __RESOURCE__, 'resource bytes changed'
resource_hex = binascii.hexlify(resource).decode()
phase = globals().get('_preview_phase', config['phase'])
M5.begin()
screen = M5.Display
screen.setBrightness(255)
screen.fillScreen(0)
screen.setTextSize(1)
screen.setTextColor(0xFFFFFF, 0)
bus = I2C(0, scl=Pin(__WHITE__), sda=Pin(__YELLOW__), freq=100000)
scan = sorted(bus.scan())
assert scan == [64,65,82], 'HUB bus leaked or wrong addresses'
encoder = EncoderUnit(bus, 0x40)
eight = Encoder8Unit(bus, 0x41)
joystick = JoystickUnit(bus, 0x52)
print('PREVIEW_CONTROLS '+json.dumps({'kind':'ready','nonce':config['nonce'],'phase':phase,'scan':scan,'resource_hex':resource_hex}))
sequence = 0
last_colors = None
while True:
 M5.update()
 e = {'counter':encoder.get_rotary_value(),'pressed':bool(encoder.get_button_status())}
 b = {'counters':[eight.get_counter_value(i) for i in range(1,9)],'pressed':[bool(eight.get_button_status(i)) for i in range(1,9)],'switch_on':bool(eight.get_switch_status())}
 j = {'x_raw':joystick.get_x_raw(),'y_raw':joystick.get_y_raw(),'button_raw':int(joystick.get_button_status())}
 colors = feedback(phase,e['pressed'],b['pressed'])
 if colors != last_colors:
  encoder.fill_color(colors[0])
  for channel in range(1,9):
   eight.set_led_rgb(channel,colors[1])
  # Original public register helper reaches the separate ninth LED triplet.
  eight.write_reg_data(0x88,list(colors[1].to_bytes(3,'big')))
  last_colors = colors
 sequence += 1
 screen.fillRect(0,0,screen.width(),48,0)
 screen.setCursor(4,4)
 screen.print('ENC %d %d' % (e['counter'],int(e['pressed'])))
 screen.setCursor(4,18)
 screen.print('8ENC %d %d' % (b['counters'][0],int(b['pressed'][0])))
 screen.setCursor(4,32)
 screen.print('JOY %d %d' % (j['x_raw'],j['y_raw']))
 screen.fillRect(screen.width()//2-4,screen.height()//2-4,8,8,{'A':0xFF0000,'B':0x00FF00,'C':0x0000FF}[phase])
 print('PREVIEW_CONTROLS '+json.dumps({'kind':'sample','nonce':config['nonce'],'phase':phase,'sequence':sequence,'resource_hex':resource_hex,'encoder':e,'eight':b,'joystick':j,'written':{'encoder':[colors[0]]*2,'eight':[colors[1]]*9}}))
 time.sleep_ms(200)
'''


def build_package(nonce, pins):
    nonce_path(nonce)
    require(isinstance(pins, dict) and set(pins) == {"white", "yellow"}
            and all(type(v) is int and 0 <= v <= 48 for v in pins.values()) and pins["white"] != pins["yellow"], "invalid frozen pins")
    source = MAIN.replace("__NONCE_PATH__", repr(nonce_path(nonce))).replace("__RESOURCE__", repr(RESOURCE))
    source = source.replace("__WHITE__", str(pins["white"])).replace("__YELLOW__", str(pins["yellow"]))
    compile(source, "main.py", "exec")
    logic = "def feedback(phase, encoder_pressed, buttons):\n color = {'A':0xFF0000,'B':0x00FF00,'C':0x0000FF}[phase]\n return (color if encoder_pressed else 0,color if any(buttons) else 0)\n"
    return {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {
        "main.py": {"encoding": "utf8", "data": source}, "logic.py": {"encoding": "utf8", "data": logic},
        "settings.json": {"encoding": "utf8", "data": json.dumps({"phase": "A", "nonce": nonce}, sort_keys=True)},
        "assets/state.bin": {"encoding": "base64", "data": base64.b64encode(RESOURCE).decode()}}}


def typed_sample(row, nonce, phase):
    require(type(phase) is str and phase in COLORS, "unknown sample phase")
    require(type(row) is dict and row.get("kind") == "sample" and row.get("nonce") == nonce and row.get("phase") == phase, "sample identity")
    require(type(row.get("sequence")) is int and row["sequence"] > 0 and row.get("resource_hex") == RESOURCE.hex(), "sample resource/sequence")
    e, b, j, written = (row.get(k) for k in ("encoder", "eight", "joystick", "written"))
    require(type(e) is dict and type(e.get("counter")) is int and type(e.get("pressed")) is bool, "encoder types")
    require(-65535 <= e["counter"] <= 65535, "encoder range")
    require(type(b) is dict and type(b.get("counters")) is list and len(b["counters"]) == 8
            and all(type(n) is int and -(2**31) <= n < 2**31 for n in b["counters"]), "eight counters")
    require(type(b.get("pressed")) is list and len(b["pressed"]) == 8 and all(type(v) is bool for v in b["pressed"])
            and type(b.get("switch_on")) is bool, "eight buttons")
    require(type(j) is dict and all(type(j.get(k)) is int and 0 <= j[k] <= (1 if k == "button_raw" else 255)
                                  for k in ("x_raw", "y_raw", "button_raw")), "joystick types/range")
    color = COLORS[phase]
    expected = {"encoder": [color if e["pressed"] else 0] * 2, "eight": [color if any(b["pressed"]) else 0] * 9}
    require(written == expected and all(type(c) is int for a in written.values() for c in a), "uniform written output")
    return row


def parse_window(text, execution, nonce, phase, *, require_ready=False, fresh_text=None):
    require(isinstance(text, str) and re.fullmatch(r"[0-9a-f]{32}", execution or ""), "invalid serial window")
    marker = "__M5_EXEC_" + execution + "__:START"
    # Raw-paste acknowledgement may precede the marker on its first line.
    match = re.search(re.escape(marker) + r"\r?\n", text)
    if match is None:
        return None
    tail = text[match.end():]
    rows = []
    for line in tail.splitlines(keepends=True):
        if not line.endswith("\n") or not line.startswith(PREFIX):
            continue
        try:
            rows.append(json.loads(line[len(PREFIX):]))
        except ValueError:
            continue
    ready = any(type(row) is dict and row.get("kind") == "ready" and row.get("nonce") == nonce
                and row.get("phase") == phase and row.get("scan") == [64, 65, 82]
                and row.get("resource_hex") == RESOURCE.hex() for row in rows)
    if fresh_text is not None:
        require(type(fresh_text) is str, "fresh serial bytes must decode to text")
        rows = []
        for line in fresh_text.splitlines(keepends=True):
            if line.endswith("\n") and line.startswith(PREFIX):
                try: rows.append(json.loads(line[len(PREFIX):]))
                except ValueError: pass
    for row in reversed(rows):
        if type(row) is not dict or row.get("kind") != "sample" or row.get("nonce") != nonce or row.get("phase") != phase:
            continue
        sample = typed_sample(row, nonce, phase)
        if require_ready and not ready:
            return None
        return {"ready": ready, "sample": sample}
    return None


def cleanup_contract(value):
    require(type(value) is dict, "cleanup record")
    closed, stopped, capacity = (value.get(k) for k in ("preview", "session", "capacity"))
    require(type(closed) is dict and closed.get("state") == "closed", "Preview not closed")
    require(type(stopped) is dict and stopped.get("state") == "stopped" and stopped.get("flash_retained") is False, "session/Flash cleanup")
    require(type(value.get("session_id")) is str and value["session_id"]
            and closed.get("session_id") == stopped.get("session_id") == value["session_id"], "cleanup identity")
    require(value.get("pid_gone") is True and value.get("zip_before_close") is True, "owned PID/evidence order")
    require(type(capacity) is dict and type(capacity.get("active_sessions")) is int and capacity["active_sessions"] == 0
            and type(capacity.get("worker")) is dict and type(capacity["worker"].get("active_lease_count")) is int
            and capacity["worker"]["active_lease_count"] == 0, "capacity/lease cleanup")
    return {"status": "PASS", "history_retained": True, "flash_released": True, "owned_pid_gone": True}


def inspect_zip(raw, expected):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and all(not n.startswith("/") and ".." not in n.split("/") for n in names), "ZIP paths")
        require(archive.testzip() is None, "ZIP CRC")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(manifest["files"]) == set(names) - {"manifest.json"}, "ZIP manifest membership")
        for name, row in manifest["files"].items():
            value = archive.read(name)
            require(row == {"size": len(value), "sha256": hashlib.sha256(value).hexdigest()}, "ZIP member bytes")
        for field in ("session_id", "device_id", "firmware_sha256", "pid"):
            require(manifest["session"].get(field) == expected[field], "ZIP session identity")
        for run in expected["runs"]:
            execution = json.loads(archive.read("programs/" + run["execution_id"] + ".json"))
            require(all(execution.get(k) == run[k] for k in ("execution_id", "revision_id")), "ZIP execution identity")
            require(execution.get("pid") == expected["pid"] and execution.get("firmware_sha256") == expected["firmware_sha256"], "ZIP VM identity")
        return {"status": "PASS", "members": len(names), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "seed", "package", "parse", "cleanup", "zip"])
    parser.add_argument("--device", choices=DEVICES, default="cores3")
    args = parser.parse_args()
    if args.action == "plan":
        result = plan(args.device)
    else:
        data = json.load(sys.stdin)
        if args.action == "seed": result = seed_package(data["nonce"])
        elif args.action == "package": result = build_package(data["nonce"], data["pins"])
        elif args.action == "parse": result = parse_window(**data)
        elif args.action == "cleanup": result = cleanup_contract(data)
        else: result = inspect_zip(base64.b64decode(data["bytes"]), data["expected"])
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
