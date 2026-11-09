#!/usr/bin/env python3
"""Run one pinned K132 stock image through an isolated Device Service."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
from user_firmware_matrix import request_bytes, request_json

CASES = {
    "factory-v09": (
        "5a80d85877ca82feb888d404fd0a22659f1f5049bbf6db7615bf9c5b722923cb",
        "a",
        "installed apps num: 9",
    ),
    "factory-v08": (
        "76cfa4cb8b6ba639e35b8de2489c75c5a6d677fe22982cb926aaf6dbf651992e",
        "q",
        "installed apps num: 8",
    ),
    "uiflow2-v254": (
        "d9e1287eccb641863e7b1cc7cf057733592403d65aeec2d4b1fa4cb3e8b1b309",
        "f12",
        None,
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(args: argparse.Namespace) -> dict:
    prefix = f"{args.service.rstrip('/')}/api/v1"
    auth = {"Authorization": f"Bearer {args.token_file.read_text().strip()}"}
    expected, key, marker = CASES[args.case]
    binary = args.firmware.read_bytes()
    if digest(binary) != expected:
        raise RuntimeError(f"{args.case} firmware SHA-256 mismatch")
    args.out_dir.mkdir(parents=True, exist_ok=False)

    def call(path: str, **kwargs):
        return request_json(prefix + path, headers=auth, **kwargs)

    def post(path: str, payload: dict):
        return call(path, method="POST", payload=payload)

    device = call("/devices/cardputer")
    if not device["creatable"] or device["sku"] != "K132" or device["machine"] != "m5cardputer":
        raise RuntimeError("Exact K132 runtime is not available")
    artifact = request_json(
        prefix + "/artifacts", method="POST", body=binary, headers={
            **auth, "Content-Type": "application/octet-stream",
            "X-Artifact-Name": args.firmware.name,
        },
    )
    firmware = post("/firmware", {
        "device_id": "cardputer", "kind": "merged", "artifact_id": artifact["artifact_id"],
    })
    session = post("/sessions", {
        "device_id": "cardputer", "runtime": "qemu", "firmware_id": firmware["firmware_id"],
        "ttl_seconds": 180,
    })
    sid = session["session_id"]
    path = f"/sessions/{sid}"
    result = {
        "case": args.case, "session_id": sid, "firmware_sha256": expected,
        "firmware_id": firmware["firmware_id"], "machine": device["machine"],
        "runtime": "qemu", "input_qcode": key, "status": "FAIL",
    }

    def read_frame() -> tuple[bytes, Image.Image]:
        png, _ = request_bytes(prefix + path + "/frame.png", headers=auth)
        with Image.open(io.BytesIO(png)) as frame:
            if frame.size != (240, 135):
                raise RuntimeError("Unexpected framebuffer dimensions")
            return png, frame.convert("RGB")

    def capture(label: str, oracle=None) -> tuple[str, Image.Image]:
        deadline = time.monotonic() + 20
        while True:
            png, frame = read_frame()
            if oracle is None or oracle(frame):
                (args.out_dir / f"{label}.png").write_bytes(png)
                return digest(png), frame
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{label}: expected guest display was not observed")
            time.sleep(0.25)

    def offline(frame: Image.Image) -> bool:
        r, g, b = frame.getpixel((16, 26))
        # The offline page has an orange status banner below the title.
        return r > 220 and 100 < g < 195 and b < 85

    def app_menu(frame: Image.Image) -> bool:
        r, g, b = frame.getpixel((95, 51))
        # The left edge of the centered DEVELOP tile is bright blue.
        return r < 70 and 85 < g < 200 and b > 150

    def fn_indicator(frame: Image.Image) -> bytes:
        return frame.crop((4, 38, 32, 58)).tobytes()

    try:
        post(path + "/wait", {
            "timeout_seconds": 75,
            "ready": {"frame_nonblank": True, "frame_min_nonblack_pixels": 32},
        })
        before_sha, _ = capture("before", offline if not marker else None)
        result["before_frame_sha256"] = before_sha
        serial = call(path + "/serial?offset=0&limit=65536")["data"]
        if marker and (marker in serial or "Launcher onCreate" not in serial):
            raise RuntimeError("Factory guest did not start at its pre-input launcher")
        post(path + "/input", {"kind": "key", "key": key, "settle_seconds": 0.5})
        if marker:
            post(path + "/wait", {
                "timeout_seconds": 12, "ready": {"serial_markers": [marker]},
            })
        after_sha, after = capture("after", app_menu if not marker else None)
        result["after_frame_sha256"] = after_sha
        if result["after_frame_sha256"] == result["before_frame_sha256"]:
            raise RuntimeError("Expected guest framebuffer change after input")
        serial = call(path + "/serial?offset=0&limit=65536")["data"]
        (args.out_dir / "serial.log").write_text(serial)
        if marker and marker not in serial:
            raise RuntimeError("Missing factory launcher marker after input")
        if args.case == "factory-v09":
            post(path + "/input", {"kind": "key", "key": "menu", "action": "down"})
            time.sleep(0.4)
            try:
                held_sha, held = capture("fn-held")
                result["fn_held_sha256"] = held_sha
            finally:
                post(path + "/input", {"kind": "key", "key": "menu", "action": "up"})
            time.sleep(0.4)
            released_sha, released = capture("fn-released")
            result["fn_released_sha256"] = released_sha
            if not (fn_indicator(held) != fn_indicator(after) == fn_indicator(released)):
                raise RuntimeError("Factory Fn indicator did not change and restore")
        result["serial_marker"] = marker
        result["status"] = "PASS"
    finally:
        try:
            zip_data, _ = request_bytes(
                prefix + path + "/evidence?include=manifest,serial,frames,logs,qom",
                headers=auth,
            )
            (args.out_dir / "evidence.zip").write_bytes(zip_data)
            result["evidence_sha256"] = digest(zip_data)
        finally:
            final = call(path + "?purge=0&retain_flash=0", method="DELETE")
            result["final_state"] = final["state"]
            (args.out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["final_state"] != "stopped":
        raise RuntimeError("Device Service did not stop the owned guest")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    print(json.dumps(run(parser.parse_args()), indent=2))


if __name__ == "__main__":
    main()
