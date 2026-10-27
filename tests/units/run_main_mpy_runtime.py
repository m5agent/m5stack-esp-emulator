#!/usr/bin/env python3
"""Prepare offline, then explicitly verify untouched main.mpy through port 8787.

Ordinary stock and candidate sessions use only the public Device Service. An
optional third, managed Preview is handed to the Web observer without closing
it. No firmware upload, direct QEMU launch, binary rewriting or automatic retry
is performed. Results describe virtual devices; physical hardware is NOT RUN.
"""
from __future__ import annotations

import argparse
import ast
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid

import run_binary_checkpoint_admission as common

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SHA = "7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e"
BASE_SHA = "3cb901cbfebd616a96292f234fe88ad1b145c3bb019f256dcb57257d78f878d8"
COMPILER_SHA = "c8646ebb97047c1c56a9d164474729a1bf13508e49d4cd3b1e5c6f00c509911b"
COMPILER = ROOT / ".work/uiflow-package-live-20261026/mpy-cross-78ff170d/micropython/mpy-cross/build/mpy-cross"
PREFIX = "PUBLIC_MAIN_MPY "
STATE_KEY = "__m5_public_main_mpy_state__"
require, sha, save = common.require, common.sha, common.save


def source_program(nonce, recovery=False):
    """The VM owner is held in a private sys.modules value, never patched."""
    setup = (f"assert {STATE_KEY!r} not in sys.modules\n"
             f"sys.modules[{STATE_KEY!r}]={{'nonce':{nonce!r},'owner':__import__('__main__'),'count':0}}") if not recovery else ""
    kind = "source-recovery" if recovery else "source-seed"
    source = f'''import sys,json,time
import M5
from unit import PIRUnit
{setup}
_state=sys.modules[{STATE_KEY!r}]
assert _state['nonce']=={nonce!r}, 'VM nonce lost'
assert __import__('__main__') is _state['owner'], 'REPL owner not restored'
M5.begin()
_screen=M5.Display
_screen.setBrightness(255)
_screen.fillScreen(0)
_screen.fillRect(_screen.width()//2-4,_screen.height()//2-4,8,8,0x0000FF)
_pir=PIRUnit((1,2))
print({PREFIX!r}+json.dumps({{'kind':{kind!r},'nonce':_state['nonce'],'count':_state['count'],'owner_id':id(__import__('__main__')),'expected_owner_id':id(_state['owner']),'owner_restored':__import__('__main__') is _state['owner']}}))
_sequence=0
_previous=None
while True:
 M5.update()
 _motion=bool(_pir.get_status())
 if _motion != _previous:
  _screen.fillRect(_screen.width()//2-4,_screen.height()//2+16,8,8,0xFFFFFF if _motion else 0)
  _previous=_motion
 _sequence+=1
 print({PREFIX!r}+json.dumps({{'kind':'source-sample','nonce':_state['nonce'],'count':_state['count'],'sequence':_sequence,'motion':_motion}}))
 time.sleep_ms(200)
'''
    ast.parse(source)
    return source


def main_source(mode):
    require(mode in {"finite", "loop", "exception"}, "unknown binary probe")
    tail = "raise RuntimeError('PUBLIC_MAIN_MPY deliberate top-level exception')\n" if mode == "exception" else ""
    if mode == "loop":
        tail = f'''from unit import PIRUnit
_pir=PIRUnit((1,2))
_sequence=0
_previous=None
while True:
 M5.update()
 _motion=bool(_pir.get_status())
 if _motion != _previous:
  _screen.fillRect(_screen.width()//2-4,_screen.height()//2-4,8,8,0xFFFFFF if _motion else dep.COLOR)
  _screen.fillRect(_screen.width()//2-4,_screen.height()//2+16,8,8,0xFFFFFF if _motion else 0)
  _previous=_motion
 _sequence+=1
 _row=_identity.copy()
 _row.update(kind='mpy-sample',sequence=_sequence,motion=_motion)
 print({PREFIX!r}+json.dumps(_row))
 time.sleep_ms(200)
'''
    source = f'''import sys,json,time
import M5
import dep
_state=sys.modules[{STATE_KEY!r}]
_state['count']+=1
_main=sys.modules.get('main')
_identity={{'nonce':_state['nonce'],'count':_state['count'],'owner_id':id(_state['owner']),'name':__name__,'file':__file__,'main_id':id(_main),'sys_main_id':id(sys.modules.get('__main__')),'import_main_id':id(__import__('__main__')),'dep_value':dep.VALUE,'dep_file':dep.__file__}}
assert __name__=='__main__'
assert _main is sys.modules.get('__main__') and _main is __import__('__main__')
assert _main is not _state['owner']
_screen=M5.Display
_screen.fillRect(_screen.width()//2-4,_screen.height()//2-4,8,8,dep.COLOR)
if __name__=='__main__':
 _row=_identity.copy()
 _row.update(kind='mpy-entry',guard=True)
 print({PREFIX!r}+json.dumps(_row))
{tail}'''
    ast.parse(source)
    return source


def payload(files, entrypoint="main.mpy"):
    return {"source_kind": "uiflow2-package", "entrypoint": entrypoint,
            "files": {name: {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")}
                      for name, data in files.items()}}


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    require(sha(COMPILER.read_bytes()) == COMPILER_SHA, "official compiler SHA differs")
    sys.path.insert(0, str(ROOT / "platform/tools"))
    from mpy_bytecode import validate_bytecode
    recipes, compiled = {}, {}
    sources = {"finite": main_source("finite"), "loop": main_source("loop"),
               "exception": main_source("exception"),
               "dep-v1": "VALUE=17\nCOLOR=0xFF0000\n", "dep-v2": "VALUE=29\nCOLOR=0x00FF00\n"}
    for name, source in sources.items():
        src, dst = folder / (name + ".py"), folder / (name + ".mpy")
        src.write_text(source, encoding="utf-8")
        argv = [str(COMPILER), "-s", "dep.py" if name.startswith("dep-") else "main.py", "-o", str(dst), str(src)]
        subprocess.run(argv, check=True, capture_output=True, timeout=15)
        data = dst.read_bytes()
        validate_bytecode(data)
        compiled[name] = data
        recipes[name] = {"argv": argv, "source_sha256": sha(src.read_bytes()), "bytecode_sha256": sha(data), "bytes": len(data)}
    packages = {"v1": payload({"main.mpy": compiled["finite"], "dep.mpy": compiled["dep-v1"]}),
                "v2": payload({"main.mpy": compiled["finite"], "dep.mpy": compiled["dep-v2"]}),
                "exception": payload({"main.mpy": compiled["exception"], "dep.mpy": compiled["dep-v2"]}),
                "loop": payload({"main.mpy": compiled["loop"], "dep.mpy": compiled["dep-v2"]})}
    for name, value in packages.items():
        save(folder / (name + ".package.json"), value)
    nonces = {name: uuid.uuid4().hex for name in ("stock", "candidate", "preview")}
    for name, nonce in nonces.items():
        (folder / (name + "-seed.py")).write_text(source_program(nonce), encoding="utf-8")
        (folder / (name + "-restore.py")).write_text(source_program(nonce, True), encoding="utf-8")
    report = {"schema_version": 1, "status": "PREPARED", "api_contacted": False, "guests_started": 0,
              "hardware": "NOT RUN", "compiler_sha256": COMPILER_SHA,
              "compiler_commit": "78ff170de9e32c79db6e64d3e33d2bd60002bdcd", "emitter": "official default pure bytecode",
              "recipes": recipes, "nonces": nonces,
              "packages": {name: {"revision_id": common.package_identity(value),
                                  "files": {path: sha(data) for path, data in common.decoded_files(value).items()}}
                           for name, value in packages.items()}}
    require(report["packages"]["v1"]["files"]["main.mpy"] == report["packages"]["v2"]["files"]["main.mpy"], "dependency-only update changed entrypoint")
    report["file_sha256"] = {path.name: sha(path.read_bytes()) for path in sorted(folder.iterdir()) if path.is_file()}
    save(folder / "prepared.json", report)
    return report


def load_prepared(folder):
    record = json.loads((folder / "prepared.json").read_text())
    require(record["api_contacted"] is False and record["compiler_sha256"] == COMPILER_SHA, "prepared provenance differs")
    for name, digest in record["file_sha256"].items():
        require(Path(name).name == name and sha((folder / name).read_bytes()) == digest, "prepared file changed")
    return record


def records(text):
    result = []
    for line in text.splitlines(keepends=True):
        if line.endswith("\n") and line.startswith(PREFIX):
            try:
                value = json.loads(line[len(PREFIX):])
            except ValueError:
                continue
            if isinstance(value, dict):
                result.append(value)
    return result


class MainLane(common.Lane):
    def __init__(self, client, args, mode, output, prepared):
        super().__init__(client, args, "cores3", "preview" if mode == "preview" else "session", output)
        self.mode, self.prepared = mode, prepared
        self.nonce = prepared["nonces"][mode]
        self.report.update(mode=mode, nonce=self.nonce)
        self.count, self.owner_id = 0, None

    def checkpoint(self, name):
        value = json.loads((self.args.prepared_dir / (name + ".package.json")).read_text())
        saved = self.client.json("program-revisions", "POST", value)
        revision = common.verify_checkpoint(saved, value)
        downloaded = self.client.json("program-revisions/" + revision["revision_id"] + "/files")
        common.verify_checkpoint(downloaded, value)
        require(saved["revision"] == downloaded["revision"], "immutable metadata changed")
        self.report.setdefault("checkpoints", {})[name] = {"revision": revision, "original_bytes_verified": True}
        return revision["revision_id"]

    def create(self):
        body = {"device_id": "cores3", "runtime": "qemu", "ttl_seconds": 3600 if self.kind == "preview" else 900,
                "units": [{"id": "pir", "unit_id": "pir", "port_id": "port-a"}]}
        if self.mode != "stock":
            body.update(base_firmware_id=BASE_SHA, expected_base_sha256=BASE_SHA)
        self.owned.update(create_body=body, creation_outcome="unknown")
        if self.kind == "preview":
            self.owned["create_key"] = uuid.uuid4().hex
            save(self.output / "create-intent.json", {"body": body, "key": self.owned["create_key"]})
            receipt = self.client.json("previews", "POST", body, self.owned["create_key"])
            common.remember_preview(self.owned, receipt)
            self.owned["creation_outcome"] = "confirmed"
            ready = common.poll(lambda: self.client.json("previews/" + self.owned["preview_id"]), lambda row: row["state"] in {"ready", "failed"}, 120)
            common.remember_preview(self.owned, ready)
            require(ready["state"] == "ready" and ready["capabilities"]["main_mpy"] is True, "managed candidate loader not verified")
            self.report["preview"] = ready
        else:
            body.update(program_mode="uiflow-live", ready_timeout_seconds=40)
            save(self.output / "create-intent.json", body)
            try:
                created = self.client.json("sessions", "POST", body, timeout=120)
                require(re.fullmatch(r"[0-9a-f]{32}", created.get("session_id", "")), "ordinary creation receipt identity missing")
                self.owned["session_id"] = created["session_id"]
            except common.HTTPFailure as error:
                if error.complete and 400 <= error.status < 500 and error.status != 408:
                    self.owned["creation_outcome"] = "rejected"
                raise
            self.owned["creation_outcome"] = "confirmed"
        self.session = common.poll(lambda: self.client.json("sessions/" + self.sid), lambda row: row["state"] in {"running", "failed", "stopped"}, 120)
        require(self.session["state"] == "running", "owned guest did not run")
        self.owned["pid"] = self.session["pid"]
        runtime = common.runtime_identity(self.session["pid"])
        require(runtime["sha256"] == RUNTIME_SHA, "frozen runtime SHA differs")
        require(self.session["worker"]["generation"] == self.args.expected_generation, "worker generation differs")
        require(self.session["units"][0]["pins"] == {"white": 1, "yellow": 2}, "CoreS3 PIR frozen pin mapping differs")
        capability = self.session["program_capabilities"]
        require(capability["mpy_entrypoint"] is (self.mode != "stock"), "observed main loader differs")
        require(capability["status"] == ("unsupported" if self.mode == "stock" else "verified"), "canary status differs")
        self.report.update(session_id=self.sid, pid=self.session["pid"], firmware_sha256=self.session["firmware_sha256"],
                           worker=self.session["worker"], runtime=runtime, program_capabilities=capability)

    def start(self, rid, label, *, expected="running"):
        if self.kind == "preview":
            preview = self.client.json("previews/" + self.owned["preview_id"])
            receipt = self.client.json(f"previews/{self.owned['preview_id']}/runs", "POST", {
                "revision_id": rid, "expected_owner_epoch": self.owned["owner_epoch"],
                "expected_generation": preview["generation"], "timeout_seconds": 120}, uuid.uuid4().hex)
            run = common.poll(lambda: self.client.json(f"previews/{self.owned['preview_id']}/runs/{receipt['run_id']}"),
                              lambda row: row["state"] in {"running", "completed", "failed", "unknown"}, 130)
            program = self.client.json(f"sessions/{self.sid}/program")["program"]
            require(program["execution_id"] == run["execution_id"], "managed execution differs")
            run = {**program, "run_id": run["run_id"]}
        else:
            old = self.client.json(f"sessions/{self.sid}/program")["program"]
            run = self.client.json(f"sessions/{self.sid}/program", "POST", {
                "revision_id": rid, "expected_execution_id": (old or {}).get("execution_id"),
                "timeout_seconds": 120}, timeout=130)["program"]
        run["probe_label"] = label
        self.report["runs"].append(run)
        if expected != "running":
            run = common.poll(lambda: self.client.json(f"sessions/{self.sid}/program")["program"], lambda row: row["state"] != "running", 30)
            run["probe_label"] = label
            self.report["runs"][-1] = run
        require(run["state"] == expected, f"{label} execution expected {expected}, got {run['state']}")
        require(run["revision_id"] == rid, "execution checkpoint differs")
        self.same_vm()
        return run

    def source(self, recovery=False):
        previous = self.client.json(f"sessions/{self.sid}/program")["program"] if recovery else None
        name = self.mode + ("-restore.py" if recovery else "-seed.py")
        source = (self.args.prepared_dir / name).read_bytes()
        package = payload({"main.py": source}, "main.py")
        rid = self.client.json("program-revisions", "POST", package)["revision"]["revision_id"]
        run = self.start(rid, "restore" if recovery else "seed")
        kind = "source-recovery" if recovery else "source-seed"
        found = self.wait_record(run, kind)
        require(found["nonce"] == self.nonce and found["count"] == self.count and found["owner_restored"] is True,
                "source VM nonce/count/owner differs")
        if self.owner_id is None:
            self.owner_id = found["owner_id"]
        require(found["owner_id"] == found["expected_owner_id"] == self.owner_id, "source REPL owner differs")
        self.report.setdefault("source_identity", []).append(found)
        if previous and previous.get("entrypoint") == "main.mpy" and previous["state"] == "running":
            history = json.loads((self.args.state_dir / "sessions" / self.sid / "programs" / (previous["execution_id"] + ".json")).read_text())
            terminal = self.serial(previous["serial_offset"])["data"]
            require(history["state"] == "interrupted" and history["interruption_confirmed"] is True
                    and f"__M5_EXEC_{previous['execution_id']}__:ERROR" in terminal
                    and f"__M5_EXEC_{previous['execution_id']}__:RESTORE_ERROR" not in terminal,
                    "binary Ctrl-C/owner restoration evidence unconfirmed")
            self.report["binary_loop_interruption"] = {"history": history, "restored_wrapper_error_marker": True,
                                                         "same_owner_recovery_source": found}
        return run

    def wait_record(self, run, kind, *, fresh=None, minimum=0, motion=None):
        marker = f"__M5_EXEC_{run['execution_id']}__:{'LOAD' if run['entrypoint'] == 'main.mpy' else 'START'}"
        def read():
            full = self.serial(run["serial_offset"])
            position = full["data"].find(marker)
            if position < 0:
                return None
            rows = records(full["data"][position + len(marker):])
            if fresh is not None:
                rows = records(self.serial(fresh)["data"])
            for row in reversed(rows):
                if row.get("kind") != kind or row.get("nonce") != self.nonce:
                    continue
                if "sample" in kind and not (type(row.get("sequence")) is int and row["sequence"] > minimum
                                               and type(row.get("motion")) is bool and (motion is None or row["motion"] is motion)):
                    continue
                return row
            return None
        return common.poll(read, lambda row: row is not None, 40)

    def binary_identity(self, run, row, dep_value):
        package_path = run["deployment"]["package_path"]
        require(row["nonce"] == self.nonce and row["count"] == self.count and row["owner_id"] == self.owner_id, "binary VM state differs")
        require(row["name"] == "__main__" and row["file"] == package_path + "/main.mpy", "actual main identity differs")
        require(row["dep_value"] == dep_value and row["dep_file"] == package_path + "/dep.mpy", "dependency was not refreshed")
        require(type(row["main_id"]) is int and row["main_id"] > 0 and row["main_id"] != self.owner_id
                and row["main_id"] == row["sys_main_id"] == row["import_main_id"], "real import owner identity differs")

    def binary(self, name, rid, *, terminal="completed", dep_value=29):
        run = self.start(rid, name, expected=terminal)
        self.count += 1
        entry = self.wait_record(run, "mpy-entry")
        self.binary_identity(run, entry, dep_value)
        require(entry["guard"] is True, "if-main guard did not execute")
        require(run["application_started"] is None and run["application_ready"] is None
                and run["start_semantics"] == "import-request-only", "dispatch misreported application readiness")
        if terminal in {"completed", "failed"}:
            require(run["owner_restored"] is True, "binary terminal owner restoration unconfirmed")
            expected_marker = "DONE" if terminal == "completed" else "ERROR"
            text = self.serial(run["serial_offset"])["data"]
            require(f"__M5_EXEC_{run['execution_id']}__:{expected_marker}" in text, "terminal import marker missing")
            if terminal == "failed":
                require("PUBLIC_MAIN_MPY deliberate top-level exception" in text and run["execution_phase"] == "load-or-execute-failed", "top-level exception not recorded truthfully")
        self.report["binary_executed"] = True
        self.report.setdefault("binary_identity", []).append({"label": name, "execution_id": run["execution_id"], "entry": entry})
        return run

    def input(self, run, motion):
        binary = run["entrypoint"] == "main.mpy"
        kind = "mpy-sample" if binary else "source-sample"
        previous = self.wait_record(run, kind)
        offset = self.serial()["next_offset"]
        body = {"id": "pir", "values": {"motion": motion}}
        if self.kind == "preview":
            response = self.client.json(f"previews/{self.owned['preview_id']}/input", "POST", {
                "expected_owner_epoch": self.owned["owner_epoch"], "expected_run_id": run["run_id"], "unit_input": body})
            require(all(response[key] == run[key] for key in ("run_id", "execution_id", "revision_id")), "managed input targeted different Run")
        else:
            self.client.json(f"sessions/{self.sid}/unit-input", "POST", body)
        sample = self.wait_record(run, kind, fresh=offset, minimum=previous["sequence"], motion=motion)
        require(sample["count"] == self.count, "fresh sample reused prior application state")
        if binary:
            self.binary_identity(run, sample, 29)
        qom = self.client.json(f"sessions/{self.sid}/qom?path=%2Fmachine%2Funits%2Fpir&property=input-level")
        require(qom["session_id"] == self.sid and qom["path"] == "/machine/units/pir" and qom["value"] is motion, "PIR QOM differs")
        frame = self.frame(run, sample, f"{run['probe_label']}-{int(motion)}")
        self.report["observations"].append({"label": run["probe_label"], "fresh_serial_offset": offset, "sample": sample, "qom": qom, "frame": frame})
        self.same_vm()
        return sample

    def frame(self, run, sample, label):
        from PIL import Image
        route = f"previews/{self.owned['preview_id']}/runs/{run['run_id']}/frame.png" if self.kind == "preview" else f"sessions/{self.sid}/frame.png?max_age_ms=1"
        raw, headers = self.client.request(route, binary=True)
        require(headers.get("x-frame-sha256") == sha(raw) and headers.get("x-frame-execution-id") == run["execution_id"]
                and headers.get("x-frame-revision-id") == run["revision_id"], "frame attribution differs")
        with Image.open(io.BytesIO(raw)) as image:
            rgb = image.convert("RGB")
            positions = common.marker_positions(image.width, image.height)
            center = list(rgb.getpixel(positions["phase"]))
            motion = list(rgb.getpixel(positions["motion"]))
            expected_center = ([255, 255, 255] if sample["motion"] else [0, 255, 0]) if run["entrypoint"] == "main.mpy" else [0, 0, 255]
            require(center == expected_center and motion == ([255, 255, 255] if sample["motion"] else [0, 0, 0]), "fresh GPIO framebuffer pixels differ")
            require(headers.get("x-frame-width") == str(image.width) and headers.get("x-frame-height") == str(image.height), "frame dimension differs")
            size = list(image.size)
        (self.output / (label + ".png")).write_bytes(raw)
        self.report["last_frame_sha256"] = sha(raw)
        return {"sha256": sha(raw), "size": size, "positions": positions, "center": center, "motion": motion, "headers": headers}

    def reject(self, run, body, expected_status, code, label):
        before = self.client.json(f"sessions/{self.sid}/program")
        disk = common.disk_programs(self.args.state_dir, self.sid)
        packages = common.store_snapshot(self.args.state_dir)
        body = {**body, "expected_execution_id": run["execution_id"]}
        response = self.client.json(f"sessions/{self.sid}/program", "POST", body, expected=expected_status)
        require(response.get("error", {}).get("code") == code, "rejection classification differs")
        common.no_execution_changed(before, self.client.json(f"sessions/{self.sid}/program"), disk, common.disk_programs(self.args.state_dir, self.sid))
        require(packages == common.store_snapshot(self.args.state_dir), "rejection changed package store")
        self.report["rejections"].append({"label": label, "status": expected_status, "code": code,
                                           "execution_allocation": False, "old_program_and_history_unchanged": True,
                                           "package_store_unchanged": True, "durable_programs": disk, "package_store_count": len(packages)})

    def execute(self):
        handed_off = False
        try:
            self.create()
            seed = self.source()
            self.input(seed, False)
            v1 = self.checkpoint("v1")
            if self.mode == "stock":
                self.reject(seed, {"revision_id": v1}, 409, "program_mpy_entrypoint_unsupported", "stock-reference")
                self.input(seed, True)
                value = json.loads((self.args.prepared_dir / "v1.package.json").read_text())
                self.reject(seed, value, 409, "program_mpy_entrypoint_unsupported", "stock-inline")
                self.input(seed, False)
            elif self.mode == "candidate":
                self.binary("v1-first", v1, dep_value=17)
                self.binary("v1-repeat", v1, dep_value=17)
                v2 = self.checkpoint("v2")
                self.binary("dependency-only", v2)
                exception = self.checkpoint("exception")
                self.binary("top-level-exception", exception, terminal="failed")
                restore = self.source(True)
                self.input(restore, True)
                bad = payload({"main.mpy": b"!\x06\x00\x1f"})
                self.reject(restore, bad, 400, "invalid_program_package_mpy", "bad-magic-inline")
                truncated = payload({"main.mpy": b"M\x06\x00\x1f"})
                self.reject(restore, truncated, 409, "program_mpy_invalid", "truncated-container-inline")
                self.input(restore, False)
                loop = self.binary("loop", self.checkpoint("loop"), terminal="running")
                self.input(loop, True)
                self.input(loop, False)
                restore = self.source(True)
                self.input(restore, True)
                self.input(restore, False)
            else:
                loop_rid = self.checkpoint("loop")
                loop = self.binary("handoff-loop", loop_rid, terminal="running")
                self.input(loop, True)
                self.input(loop, False)
                self.capture_zip()
                restore = (self.args.prepared_dir / "preview-restore.py").resolve()
                hold = {"session_id": self.sid, "preview_id": self.owned["preview_id"], "owner_epoch": self.owned["owner_epoch"],
                        "pid": self.session["pid"], "firmware_sha256": self.session["firmware_sha256"],
                        "worker_generation": self.session["worker"]["generation"], "service_pid": self.args.expected_service_pid,
                        "runtime_sha256": RUNTIME_SHA, "nonce": self.nonce, "owner_id": self.owner_id, "count": self.count,
                        "binary_revision_id": loop_rid, "binary_file_sha256": self.prepared["packages"]["loop"]["files"],
                        "pir_id": "pir", "source_restore_file": str(restore), "source_restore_sha256": sha(restore.read_bytes()),
                        "frame_center_by_motion": {"true": [255, 255, 255], "false": [0, 255, 0]}, "source_restore_center": [0, 0, 255],
                        "token_file": str(self.args.token_file.resolve()), "execution_id": loop["execution_id"], "run_id": loop["run_id"]}
                save(self.output / "handoff.json", hold)
                self.report["handoff"] = hold
                handed_off = True
            self.report["status"] = "HANDOFF READY" if handed_off else "PASS"
        except BaseException as error:
            self.report["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            if not handed_off:
                self.report["cleanup"] = self.cleanup()
                if self.report["cleanup"]["status"] != "PASS":
                    self.report["status"] = "FAIL"
            save(self.output / "owned.json", self.owned)
            save(self.output / "report.json", self.report)
        return self.report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--token-file", type=Path, default=ROOT / ".work/preview-control-token")
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".work/unit-device-service")
    parser.add_argument("--start-receipt", type=Path, default=ROOT / ".work/public-main-mpy-owned-start-gen45-20261027/start.json")
    parser.add_argument("--expected-generation", type=int, default=45)
    parser.add_argument("--expected-service-pid", type=int, default=95400)
    parser.add_argument("--handoff-preview", action="store_true")
    args = parser.parse_args(argv)
    args.expected_runtime_sha256 = RUNTIME_SHA
    if args.prepare_only:
        result = prepare(args.prepared_dir)
        print(json.dumps({"status": result["status"], "api_contacted": False, "guests_started": 0,
                          "packages": result["packages"], "nonces": result["nonces"]}, indent=2))
        return 0
    require(args.out_dir is not None, "--out-dir required")
    prepared = load_prepared(args.prepared_dir)
    receipt = json.loads(args.start_receipt.read_text())
    frozen = receipt["source_sha256"]
    require(all(sha((ROOT / path).read_bytes()) == digest for path, digest in frozen.items()), "product source changed since owned service start")
    require(receipt["pid"] == args.expected_service_pid and receipt["runtime_sha256"] == RUNTIME_SHA
            and receipt["health"]["capacity"]["worker"]["generation"] == args.expected_generation, "owned start receipt differs")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    output = args.out_dir.resolve()
    report = {"schema_version": 1, "category": "public-main-mpy-runtime", "status": "FAIL", "hardware": "NOT RUN",
              "started_at": datetime.now(timezone.utc).isoformat(), "lanes": [], "product_source_sha256": frozen,
              "runner_sha256": sha(Path(__file__).read_bytes()), "prepared_record_sha256": sha((args.prepared_dir / "prepared.json").read_bytes())}
    token = common.read_token(args.token_file)
    client = common.Client(args.base_url, token, output)
    try:
        health = client.json("health")
        common.validate_local_state(args, health)
        worker = health["capacity"]["worker"]
        require(worker["generation"] == args.expected_generation and worker["pid"] == args.expected_service_pid
                and worker["state"] == "ready" and health["capacity"]["active_sessions"] == 0, "service generation/readiness or active scope differs")
        report["service_worker"] = worker
        base = client.json("firmware/" + BASE_SHA)
        require(base["firmware_id"] == base["sha256"] == BASE_SHA and base["kind"] == "manifest"
                and base["device_id"] == "cores3" and isinstance(base.get("manifest"), dict), "public candidate manifest base differs")
        require(sha((args.state_dir / "firmware" / (BASE_SHA + ".bin")).read_bytes()) == BASE_SHA,
                "existing candidate base bytes differ; never replace or upload them")
        save(output / "candidate-base-metadata.json", base)
        for lane_mode in ("stock", "candidate", *(("preview",) if args.handoff_preview else ())):
            folder = output / lane_mode
            folder.mkdir()
            lane = MainLane(common.Client(args.base_url, token, folder), args, lane_mode, folder, prepared)
            result = lane.execute()
            report["lanes"].append({"mode": lane_mode, "status": result["status"], "report": str(folder / "report.json")})
            save(output / "report.json", report)
            require(result["status"] in {"PASS", "HANDOFF READY"}, f"{lane_mode} failed; retained original evidence; no automatic retry")
            print("PUBLIC_MAIN_MPY_" + lane_mode.upper() + "_" + result["status"], flush=True)
        require(all(sha((ROOT / path).read_bytes()) == digest for path, digest in frozen.items()), "frozen product changed during acceptance")
        require(report["runner_sha256"] == sha(Path(__file__).read_bytes()), "runner changed during acceptance")
        report["final_capacity"] = client.json("capacity")
        report["status"] = "HANDOFF READY" if args.handoff_preview else "PASS"
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        save(output / "report.json", report)
    print("PUBLIC_MAIN_MPY_" + report["status"], flush=True)
    return 0 if report["status"] in {"PASS", "HANDOFF READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
