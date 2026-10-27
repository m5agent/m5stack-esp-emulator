#!/usr/bin/env python3
"""Exercise real control Unit drivers through visible Device Service sessions.

--prepare-only composes images without launching a runtime or calling the API.
All execution uses /api/v1; evidence is requested before stop with purge=0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from run_service_cases import Client, wait_for, build_image  # noqa: E402

CASES = ("joystick-v11", "encoder", "8encoder", "cardkb", "rfid2")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def settled_frame(client, session_id):
    # Serial output precedes the probe's display redraw. Give the guest time to
    # finish, then require three identical native PNGs instead of archiving a
    # transient partially drawn tuple as the terminal screenshot.
    time.sleep(1)
    deadline = time.monotonic() + 10
    previous = None
    unchanged = 0
    while time.monotonic() < deadline:
        frame = client.raw(f"sessions/{session_id}/frame.png")
        if not frame.startswith(b"\x89PNG"):
            raise RuntimeError("runtime did not return a PNG framebuffer")
        unchanged = unchanged + 1 if frame == previous else 0
        if unchanged >= 2:
            return frame
        previous = frame
        time.sleep(0.3)
    raise RuntimeError("framebuffer did not settle before evidence capture")


def build_control_image(options):
    # Existing shared builder writes flat probe files. Add exact driver packages
    # through LittleFS itself, creating directories rather than flattening or
    # rewriting official relative imports.
    import littlefs
    files = options.files_dir
    entry = options.out_dir / "entry"
    entry.mkdir(exist_ok=True)
    for path in files.glob("*.py"):
        shutil.copyfile(path, entry / path.name)
    flat = SimpleNamespace(**vars(options))
    flat.files_dir = entry
    image = build_image(flat)
    data = bytearray(image.read_bytes())
    vfs = bytearray(data[options.vfs_offset:options.vfs_offset + options.vfs_size])
    fs = littlefs.LittleFS(
        context=littlefs.UserContext(buffer=vfs), block_size=4096,
        block_count=options.vfs_size // 4096, read_size=128, prog_size=options.prog_size,
        lookahead_size=128, block_cycles=100, mount=False,
    )
    fs.mount()
    for directory in sorted((path for path in files.rglob("*") if path.is_dir()), key=lambda path: len(path.parts)):
        fs.mkdir("/" + directory.relative_to(files).as_posix())
    for path in files.rglob("*.py"):
        if path.parent == files:
            continue
        with fs.open("/" + path.relative_to(files).as_posix(), "w") as stream:
            stream.write(path.read_text())
    fs.unmount()
    data[options.vfs_offset:options.vfs_offset + options.vfs_size] = vfs
    image.write_bytes(data)
    print(f"control image sha256: {hashlib.sha256(data).hexdigest()}")
    return image


def prepare(args, case):
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=True)
    matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
    device = next(row for row in matrix["devices"] if row["id"] == args.device)
    hosts = json.loads((ROOT / "platform/units/host-ports.json").read_text())["hosts"]
    host = next(row for row in hosts if row["device_id"] == args.device)
    port = next(row for row in host["ports"] if row.get("visual_port") == "grove" and row.get("wiring_status") == "confirmed")
    files = output / "files"
    shutil.copytree(Path(__file__).parent / "controls_probe", files, dirs_exist_ok=True)
    (files / "probe_config.py").write_text(
        f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\n", encoding="utf-8",
    )
    image = build_control_image(SimpleNamespace(
        base=ROOT / device["base"], flash_size=int(device["flash_size"], 0), files_dir=files,
        mklittlefs=None, preserve_vfs=False, vfs_offset=int(device["vfs_offset"], 0),
        vfs_size=int(device["vfs_size"], 0), prog_size=32, out_dir=output,
    ))
    result = {
        "schema_version": 1, "category": "virtual-device-validation", "status": "PREPARED",
        "device_id": args.device, "unit_id": case, "port_id": port["id"],
        "base_firmware_sha256": digest(ROOT / device["base"]), "firmware_sha256": digest(image),
        "probe_sha256": {str(path.relative_to(files)): digest(path) for path in sorted(files.rglob("*.py"))},
        "checks": {},
    }
    (output / "prepared.json").write_text(json.dumps(result, indent=2) + "\n")
    return output, image, port, result


def run_case(client, args, case):
    output, image, port, result = prepare(args, case)
    if args.prepare_only:
        print(f"{case}: PREPARED (no runtime started)", flush=True)
        return result
    session_id = None
    result["status"] = "FAIL"
    try:
        inventory = client.json(f"units?device_id={args.device}")
        descriptor = next(row for row in inventory["units"] if row["id"] == case)
        if descriptor["runtime"]["status"] not in {"implemented", "validated"}:
            raise RuntimeError(f"runtime_model_gap: {case} is not enabled")
        artifact = client.json("artifacts", method="POST", body=image.read_bytes(), headers={
            "Content-Type": "application/octet-stream", "X-Artifact-Name": f"{args.device}-{case}-control-probe.bin",
        })
        firmware = client.json("firmware", method="POST", payload={
            "device_id": args.device, "kind": "merged", "artifact_id": artifact["artifact_id"],
        })
        session = client.json("sessions", method="POST", payload={
            "device_id": args.device, "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 1200, "ready_marker": "CONTROL_PROBE_READY", "ready_timeout_seconds": 150,
            "units": [{"id": "external1", "unit_id": case, "port_id": port["id"]}],
        })
        session_id = session["session_id"]
        result["session_id"] = session_id
        print(f"{case}: visible session created", flush=True)
        serial = wait_for(client, session_id, lambda text: "CONTROL_PROBE_READY" in text, 180)
        result["checks"]["exact_official_driver_ready"] = True

        def send(values):
            return client.json(f"sessions/{session_id}/unit-input", method="POST", payload={"id": "external1", "values": values})

        def wait_marker(marker, offset=0):
            return wait_for(client, session_id, lambda text: marker in text[offset:], 40)

        if case == "joystick-v11":
            offset = len(serial)
            send({"x-raw": 31, "y-raw": 240, "button-raw": 1})
            serial = wait_marker("CONTROL_JOYSTICK 31 240 1", offset)
            offset = len(serial)
            send({"x-raw": 255, "y-raw": 0, "button-raw": 0})
            serial = wait_marker("CONTROL_JOYSTICK 255 0 0", offset)
            result["checks"]["three_raw_bytes_reach_guest"] = True
        elif case == "encoder":
            offset = len(serial)
            send({"counter": -12345, "pressed": True})
            serial = wait_marker("CONTROL_ENCODER -12345 1", offset)
            offset = len(serial)
            send({"counter": 32767, "pressed": False})
            serial = wait_marker("CONTROL_ENCODER 32767 0", offset)
            result["checks"]["signed_int16_and_active_low_driver"] = True
        elif case == "8encoder":
            assert "CONTROL_ENCODER8_REGISTER_WRITE -1234567 0" in serial
            assert "CONTROL_ENCODER8_ADDRESS 66" in serial
            counts = [1, -2, 123456, -123456, 2147483647, -2147483648, 7, 8]
            pressed = [True, False, True, False, False, True, False, True]
            offset = len(serial)
            send({"counters": counts, "pressed": pressed, "switch-on": True})
            expected = "CONTROL_ENCODER8 %s %s 1" % (counts, [int(value) for value in pressed])
            serial = wait_marker(expected, offset)
            result["checks"]["eight_signed_channels_buttons_and_switch"] = True
            result["checks"]["guest_counter_write_reset_and_address_change"] = True
        elif case == "cardkb":
            assert "CONTROL_CARDKB_LEGACY 1" in serial
            fixture = json.loads((ROOT / "platform/units/fixtures/cardkb-keymap.json").read_text())
            keys = [False] * 50
            by_id = {row["id"]: row for row in fixture["keys"]}
            expected_stream = []
            start_offset = len(serial)

            def tap(key, expected=None):
                nonlocal serial
                index = by_id[key]["index"]
                offset = len(serial)
                keys[index] = True
                send({"keys": keys.copy()})
                keys[index] = False
                send({"keys": keys.copy()})
                if expected is not None:
                    if expected:
                        expected_stream.append(expected)
                        serial = wait_for(client, session_id, lambda text: re.search(
                            rf"(?m)^CONTROL_CARDKB_KEY {expected}\r?$", text[offset:]), 40)

            for row in fixture["keys"]:
                if not row["modifier"]:
                    tap(row["id"], row["normal"])
            result["checks"]["all_47_nonmodifier_keys_via_i2c"] = True
            for modifier, field in (("key-shift", "shift"), ("key-sym", "sym"), ("key-fn", "fn")):
                tap(modifier)
                tap("key-q", by_id["key-q"][field])
                tap("key-q", by_id["key-q"]["normal"])
            result["checks"]["all_three_one_shot_modifiers"] = True
            for modifier, field, mode in (("key-shift", "shift", 2), ("key-sym", "sym", 4), ("key-fn", "fn", 6)):
                if client.web_ui:
                    # A single real browser gesture preserves the official
                    # 200 ms double-click interval; per-input evidence writes
                    # must not lengthen a timing-sensitive user gesture.
                    client.unit_double_tap(session_id, "external1", "keys", by_id[modifier]["index"])
                else:
                    tap(modifier)
                    tap(modifier)
                snapshot = client.json(f"sessions/{session_id}/units")
                assert snapshot["units"][0]["properties"]["modifier-mode"] == mode
                for row in fixture["keys"]:
                    if not row["modifier"]:
                        tap(row["id"], row[field])
                tap(modifier)  # Unlock returns normal.
                snapshot = client.json(f"sessions/{session_id}/units")
                assert snapshot["units"][0]["properties"]["modifier-mode"] == 0
            result["checks"]["all_four_official_key_tables_and_modifier_locks"] = True
            # Direct keycode is a byte fixture, separate from matrix evidence.
            offset = len(serial)
            send({"keycode": 0x41})
            serial = wait_for(client, session_id, lambda text: re.search(r"(?m)^CONTROL_CARDKB_KEY 65\r?$", text[offset:]), 40)
            expected_stream.append(65)
            observed = [int(value) for value in re.findall(r"(?m)^CONTROL_CARDKB_KEY (\d+)\r?$", serial[start_offset:])]
            assert observed == expected_stream, (observed, expected_stream)
            result["checks"]["legacy_byte_consumption"] = True
        else:
            assert "CONTROL_RFID_CRC_VECTOR 1 05bf" in serial
            offset = len(serial)
            send({"uid-hex": "04010203", "card-present": True})
            serial = wait_marker("CONTROL_RFID_UID 04010203", offset)
            serial = wait_marker("CONTROL_RFID_BLOCK 1 1 1 3132333435363738393a3b3c3d3e3f40")
            for marker in ("CONTROL_RFID_BAD_KEY 1", "CONTROL_RFID_BAD_CRC 1", "CONTROL_RFID_SECTOR_DENIED 1", "CONTROL_RFID_HALT_DENIED 1", "CONTROL_RFID_ANTENNA_OFF 1"):
                serial = wait_marker(marker)
            result["checks"]["request_anticollision_select_auth_block_write_read_halt"] = True
            result["checks"]["wrong_key_halt_and_antenna_negative_controls"] = True
            for uid in ("04010203040506", "04010203040506070809"):
                offset = len(serial)
                send({"uid-hex": uid, "card-present": True})
                serial = wait_marker("CONTROL_RFID_UID " + uid, offset)
                serial = wait_marker("CONTROL_RFID_ANTENNA_OFF 1", offset)
            result["checks"]["four_seven_ten_byte_uid_cascade_select"] = True
            offset = len(serial)
            send({"card-present": False})
            serial = wait_marker("CONTROL_RFID_NO_CARD", offset)
            result["checks"]["card_removal_reaches_guest"] = True

        snapshot = client.json(f"sessions/{session_id}/units")
        result["unit_state"] = snapshot
        state = snapshot["units"][0]
        properties = state["properties"]
        assert snapshot["source"] == "live" and state["source"] == "guest-qom" and state["available"]
        assert properties["transactions"] > 0 and properties["read-bytes"] > 0
        assert properties["written-bytes"] > 0 and properties["input-events"] > 0
        result["checks"]["same_guest_i2c_controller_counters"] = True
        if case == "encoder":
            assert properties["led-rgb"] == [0x112233, 0x445566]
            result["checks"]["guest_led_writes_read_back"] = True
        if case == "8encoder":
            assert properties["led-rgb"] == [i * 0x010203 for i in range(1, 9)] + [0x192939]
            assert properties["i2c-address"] == 0x42
            result["checks"]["all_nine_guest_rgb_register_triplets"] = True
        frame = settled_frame(client, session_id)
        (output / "frame.png").write_bytes(frame)
        result["frame_sha256"] = hashlib.sha256(frame).hexdigest()
        (output / "serial.txt").write_text(serial)
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
    finally:
        if session_id:
            try:
                bundle = client.raw(f"sessions/{session_id}/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
            except Exception as error:
                result["evidence_error"] = str(error)
                result["status"] = "FAIL"
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", method="DELETE")
                assert stopped["state"] in {"stopped", "failed"}
                result["checks"]["stopped_with_history"] = True
            except Exception as error:
                result["stop_error"] = str(error)
                result["status"] = "FAIL"
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"{case}: {result['status']} {result.get('error', '')}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8787")
    parser.add_argument("--device", default="cores3")
    parser.add_argument("--case", choices=(*CASES, "all"), default="all")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cases = CASES if args.case == "all" else (args.case,)
    results = [run_case(Client(args.api_url), args, case) for case in cases]
    return 0 if all(row["status"] in {"PASS", "PREPARED"} for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
