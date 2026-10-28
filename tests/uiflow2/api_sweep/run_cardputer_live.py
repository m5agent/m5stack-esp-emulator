#!/usr/bin/env python3
"""Cardputer-ADV same-VM Preview source/input/cancel/recovery validation."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import uuid
import zipfile

from run_guest import Api, process_identity, save, serial_pages


def require(value, message):
    if not value:
        raise RuntimeError(message)


def poll(action, predicate, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = action()
        if predicate(value):
            return value
        time.sleep(.1)
    raise RuntimeError("bounded observation timed out")


def program(nonce, phase):
    lines = ["import M5,time,sys", "M5.begin()", "_key='m5emu-cardputer-live-state'", "_state=sys.modules.get(_key)"]
    if phase == "A":
        lines += ["assert _state is None,'fresh VM state already exists'", "_state={'nonce':" + repr(nonce) + ", 'count':0}", "sys.modules[_key]=_state"]
    else:
        lines += ["assert _state is not None and _state['nonce']==" + repr(nonce) + ",'VM nonce lost'"]
    lines += ["_state['count']+=1", "M5.Display.fillScreen(" + str({"A": 0x123456, "B": 0x44AA22, "C": 0x3333CC}[phase]) + ")", "M5.Display.setCursor(5,10)", "M5.Display.setTextColor(0xFFFFFF)", "M5.Display.print('LIVE " + phase + "')", "print('CARDPUTER_LIVE_" + phase + "_READY',_state['nonce'],_state['count'])"]
    if phase == "B":
        lines += ["from hardware import KeyboardI2C", "from machine import I2C,Pin", "_keyboard=KeyboardI2C(I2C(1,scl=Pin(9),sda=Pin(8),freq=400000),intr_pin=Pin(11,Pin.IN),mode=KeyboardI2C.ASCII_MODE)", "_keyboard.set_keyevent_callback(lambda keyboard:print('CARDPUTER_LIVE_KEY_CALLBACK',keyboard.is_key_pressed(97)))", "print('CARDPUTER_LIVE_KEYBOARD_READY')", "_last=None", "try:", " while True:", "  M5.update()", "  _pressed=_keyboard.is_key_pressed(97)", "  if _pressed!=_last:", "   print('CARDPUTER_LIVE_KEY_STATE',_pressed)", "   _last=_pressed", "  time.sleep_ms(10)", "finally:", " _keyboard.deinit()", " print('CARDPUTER_LIVE_KEYBOARD_DEINIT')"]
    elif phase == "A":
        lines += ["while True:", " M5.update()", " time.sleep_ms(20)"]
    return "\n".join(lines) + "\n"


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    api = Api(args.api, args.token_file)
    preview = session_id = None
    serial_text = ""
    offset = 0
    report = {"status": "FAIL", "device_id": "cardputer-adv", "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "checks": {}}
    nonce = uuid.uuid4().hex
    try:
        preview = api.json("previews", "POST", {"device_id": "cardputer-adv", "runtime": "qemu", "ttl_seconds": 300}, headers={"Idempotency-Key": "cardputer-live-" + nonce})
        preview_id = preview["preview_id"]
        preview_path = "previews/" + preview_id
        ready = poll(lambda: api.json(preview_path), lambda value: value["state"] in ("ready", "failed", "closed"), 90)
        require(ready["state"] == "ready", "Preview failed admission/readiness: " + str(ready.get("error")))
        session_id = ready["session_id"]
        session_path = "sessions/" + session_id
        identity = api.json(session_path)
        pid = identity["pid"]
        report.update(preview_id=preview_id, session_id=session_id, firmware_sha256=identity["firmware_sha256"], runtime_pid=pid)
        owner_epoch = ready["owner_epoch"]
        generation = ready["generation"]
        runs = []
        save(args.out_dir / "ready.json", ready)

        def serial(marker):
            nonlocal serial_text, offset
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                text, offset, _pages = serial_pages(api, session_id, offset)
                serial_text += text
                (args.out_dir / "serial.txt").write_text(serial_text)
                if marker in serial_text:
                    return serial_text
                time.sleep(.1)
            raise RuntimeError("guest marker missing: " + marker)

        def submit(source, label):
            nonlocal generation
            (args.out_dir / (label + ".py")).write_text(source)
            package = api.json("program-revisions", "POST", {"source_kind": "uiflow2-package", "entrypoint": "main.py", "files": {"main.py": {"encoding": "utf8", "data": source}}})
            revision = package["revision"]["revision_id"]
            result = api.json(preview_path + "/runs", "POST", {"revision_id": revision, "expected_owner_epoch": owner_epoch, "expected_generation": generation, "client_generation": label, "timeout_seconds": 40}, headers={"Idempotency-Key": nonce + "-" + label})
            generation = result["generation"]
            rid = result["run_id"]
            finished = poll(lambda: api.json(preview_path + "/runs/" + rid), lambda value: value["state"] in ("running", "completed", "failed", "cancelled"), 90)
            runs.append(finished)
            save(args.out_dir / (label + "-run.json"), finished)
            require(finished["state"] in ("running", "completed"), "Run failed: " + str(finished.get("error")))
            current = api.json(session_path)
            require(current["pid"] == pid and current["firmware_sha256"] == identity["firmware_sha256"], "Run replaced the guest process/firmware")
            return finished

        a = submit(program(nonce, "A"), "A")
        serial("CARDPUTER_LIVE_A_READY " + nonce + " 1")
        frame_a = api.raw(preview_path + "/runs/" + a["run_id"] + "/frame.png?max_age_ms=0")
        (args.out_dir / "frame-a.png").write_bytes(frame_a)
        b = submit(program(nonce, "B"), "B")
        serial("CARDPUTER_LIVE_B_READY " + nonce + " 2")
        serial("CARDPUTER_LIVE_KEYBOARD_READY")
        frame_b = api.raw(preview_path + "/runs/" + b["run_id"] + "/frame.png?max_age_ms=0")
        (args.out_dir / "frame-b.png").write_bytes(frame_b)
        require(frame_a != frame_b, "new Run failed to change the framebuffer")
        api.json(preview_path + "/input", "POST", {"expected_owner_epoch": owner_epoch, "expected_run_id": b["run_id"], "input": {"kind": "key", "key": "a", "action": "down", "settle_seconds": .1}})
        serial("CARDPUTER_LIVE_KEY_STATE True")
        serial("CARDPUTER_LIVE_KEY_CALLBACK True")
        api.json(preview_path + "/input", "POST", {"expected_owner_epoch": owner_epoch, "expected_run_id": b["run_id"], "input": {"kind": "key", "key": "a", "action": "up", "settle_seconds": .1}})
        before_cancel = api.json(preview_path + "/runs/" + b["run_id"])
        api.json(preview_path + "/runs/" + b["run_id"] + "/cancel", "POST", {"expected_owner_epoch": owner_epoch})
        cancelled = poll(lambda: api.json(preview_path + "/runs/" + b["run_id"]), lambda value: value["state"] in ("cancelled", "failed"), 60)
        save(args.out_dir / "cancelled.json", cancelled)
        require(cancelled["state"] == "cancelled" and cancelled.get("interrupt_ack") == "confirmed", "cancel did not confirm a new raw prompt")
        serial("CARDPUTER_LIVE_KEYBOARD_DEINIT")
        c = submit(program(nonce, "C"), "C")
        serial("CARDPUTER_LIVE_C_READY " + nonce + " 3")
        frame_c = api.raw(preview_path + "/runs/" + c["run_id"] + "/frame.png?max_age_ms=0")
        (args.out_dir / "frame-c.png").write_bytes(frame_c)
        require(frame_c != frame_b and frame_c != frame_a, "recovery frame did not change")
        require(serial_text.count("ESP-ROM:") == 1, "guest reboot banner count changed")
        snapshot = api.json(session_path + "/qom-snapshot", "POST", {"path": "/machine", "depth": 2, "max_nodes": 500})
        save(args.out_dir / "qom.json", snapshot)
        report["checks"] = {"same_pid": True, "same_firmware": True, "sys_modules_nonce": True, "runs_count_1_2_3": True, "no_reboot": True, "source_replacement": True, "distinct_frames": True, "keyboard_irq_callback": True, "keyboard_pressed_state": True, "cancel_prompt_confirmed": True, "keyboard_deinit_on_cancel": True, "recovery_after_cancel": True}
        report["runs"] = runs
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if session_id:
            try:
                serial_text, _offset, _pages = serial_pages(api, session_id)
                (args.out_dir / "serial.txt").write_text(serial_text)
                bundle = api.raw("sessions/" + session_id + "/evidence")
                (args.out_dir / "evidence.zip").write_bytes(bundle)
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    require(archive.testzip() is None, "evidence ZIP corruption")
                report["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
            except Exception as error:
                report.update(status="FAIL", evidence_error=str(error))
        if preview:
            try:
                control = api.json("previews/" + preview["preview_id"])
                api.json("previews/" + preview["preview_id"] + "/close", "POST", {"expected_owner_epoch": control["owner_epoch"]})
                closed = poll(lambda: api.json("previews/" + preview["preview_id"]), lambda value: value["state"] == "closed", 60)
                save(args.out_dir / "closed.json", closed)
            except Exception as error:
                report.update(status="FAIL", close_error=str(error))
        if session_id:
            stopped = api.json("sessions/" + session_id)
            save(args.out_dir / "stopped.json", stopped)
            report["cleanup"] = {"state": stopped["state"], "pid_gone": not process_identity(report["runtime_pid"])["exists"], "flash_released": not stopped["flash_retained"]}
            if stopped["state"] != "stopped" or not all((report["cleanup"]["pid_gone"], report["cleanup"]["flash_released"])):
                report["status"] = "FAIL"
        save(args.out_dir / "report.json", report)
    print(json.dumps({key: report.get(key) for key in ("status", "session_id", "preview_id", "error", "cleanup")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
