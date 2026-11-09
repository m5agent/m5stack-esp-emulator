#!/usr/bin/env python3
"""Exercise the ET047TC1 and primary inputs through an isolated Device Service."""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

from PIL import Image, ImageChops


PANEL = "/machine/et047tc1"
SIZE = (540, 960)
MARKERS = {
    "papers3": ("board_M5PaperS3",),
    "paperdiy": ("PaperDIY: Firmware version: V1.0", "board_M5PaperDIY", "Display ready: 540x960"),
}
BUTTONS = {"a": (9, 620, 119, 686), "b": (9, 731, 119, 797)}
BUZZER_ICON = (78, 296, 155, 385)
# The factory screens first flash black. The stable menu has these known
# black pixel counts in the input regions for the pinned firmware images.
BASELINE = {
    "papers3": {BUZZER_ICON: 1910},
    "paperdiy": {BUTTONS["a"]: 978, BUTTONS["b"]: 1099},
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Service:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.token = token

    def request(self, route, *, method=None, payload=None, binary=False, name=None):
        headers = {"Authorization": f"Bearer {self.token}"}
        if name is not None:
            headers.update({"Content-Type": "application/octet-stream", "X-Artifact-Name": name})
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(payload).encode()
        request = urllib.request.Request(self.url + route, payload, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{route}: HTTP {error.code} {error.read().decode(errors='replace')[:400]}") from error
        return raw if binary else json.loads(raw)

    def upload(self, path):
        data = path.read_bytes()
        result = self.request("/artifacts", payload=data, name=path.name)
        require(result["sha256"] == sha256(data), f"upload hash mismatch for {path.name}")
        return result


def changed_pixels(before, after, region):
    return sum(ImageChops.difference(before.crop(region), after.crop(region)).histogram()[1:])


def exercise(args, service, session, result):
    def capture(name=None):
        data = service.request(session + "/frame.png", binary=True)
        with Image.open(BytesIO(data)) as source:
            image = source.convert("L")
        require(image.size == SIZE, f"unexpected frame geometry {image.size}")
        if name is not None:
            (args.output_dir / f"{name}.png").write_bytes(data)
            result["frames"][name] = {"sha256": sha256(data), "size": list(image.size)}
        return image

    def wait_region(name, region, black_pixels):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if capture().crop(region).histogram()[0] == black_pixels:
                return capture(name)
            time.sleep(0.25)
        raise RuntimeError(f"{name} region did not reach {black_pixels} black pixels")

    def property_value(name):
        return service.request(f"{session}/qom?path={PANEL}&property={name}")["value"]

    def send_input(**payload):
        result["inputs"].append(service.request(session + "/input", payload=payload))
        require(result["inputs"][-1]["accepted"], "Device Service rejected input")

    markers = MARKERS[args.device]
    baseline = BASELINE[args.device]
    deadline = time.monotonic() + args.boot_timeout
    while time.monotonic() < deadline:
        state = service.request(session)["state"]
        require(state not in {"failed", "stopped"}, f"guest entered {state} before the factory UI")
        if state == "running":
            logs = service.request(session + "/logs")["data"]
            if all(marker in logs for marker in markers) and property_value("scan-frames") > 0:
                frame = capture()
                if all(frame.crop(region).histogram()[0] == count for region, count in baseline.items()):
                    break
        time.sleep(1)
    else:
        raise RuntimeError(f"timed out waiting for factory display and serial markers {markers}")
    result["serial_markers"] = list(markers)
    result["scan_frames_before"] = property_value("scan-frames")
    require(result["scan_frames_before"] > 0, "no firmware scanout")
    before = capture("before")
    require(before.getextrema() == (0, 255), "expected both black and white in factory UI")

    if args.device == "papers3":
        send_input(kind="longpress", x=113, y=347, hold_seconds=0.5, settle_seconds=0.3)
        after = wait_region("after", BUZZER_ICON, 1755)
        changed = changed_pixels(before, after, BUZZER_ICON)
        result["pixel_oracle"] = {"region": list(BUZZER_ICON), "changed": changed}
        require(changed == 607, f"expected 607 changed pixels in the buzzer icon, got {changed}")
    else:
        result["pixel_oracle"] = {}
        for key, region in BUTTONS.items():
            other_region = BUTTONS["b" if key == "a" else "a"]
            send_input(kind="key", key=key, action="down", settle_seconds=0.4)
            try:
                held = wait_region(f"{key}-held", region, baseline[region] + 533)
            finally:
                send_input(kind="key", key=key, action="up", settle_seconds=0.4)
            released = wait_region(f"{key}-released", region, baseline[region])
            counts = {
                "pressed": changed_pixels(before, held, region),
                "released": changed_pixels(held, released, region),
                "returned_to_baseline": changed_pixels(before, released, region) == 0,
                "other_button_changed": changed_pixels(before, held, other_region),
            }
            result["pixel_oracle"][key] = {"region": list(region), **counts}
            require(counts["pressed"] == 533 and counts["released"] == 533
                    and counts["returned_to_baseline"] and counts["other_button_changed"] == 0,
                    f"{key.upper()} press/release did not isolate its frame region: {counts}")
            before = released

    result["scan_frames_after"] = property_value("scan-frames")
    result["latched_lines"] = property_value("latched-lines")
    require(result["scan_frames_after"] > result["scan_frames_before"], "input produced no new scanout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="Isolated Device Service URL ending in /api/v1")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--device", choices=MARKERS, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--nvs-image", type=Path, help="Provisioned PaperDIY factory_done NVS image")
    parser.add_argument("--boot-timeout", type=float, default=120)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if (args.device == "paperdiy") != (args.nvs_image is not None):
        parser.error("--nvs-image is required for PaperDIY and applies only to PaperDIY")
    args.output_dir.mkdir(parents=True, exist_ok=False)

    service = Service(args.api, args.token_file.read_text(encoding="utf-8").strip())
    artifact = service.upload(args.firmware)
    imported = service.request("/firmware/import", payload={
        "device_id": args.device, "artifact_id": artifact["artifact_id"],
    })
    request = {
        "device_id": args.device, "firmware_id": imported["firmware_id"], "runtime": "qemu",
        "owner": "paper-et047tc1-regression", "ttl_seconds": 300,
    }
    result = {
        "device": args.device, "validation": "virtual-device validation",
        "source_sha256": artifact["sha256"], "frames": {}, "inputs": [],
    }
    if args.nvs_image:
        nvs = service.upload(args.nvs_image)
        request["nvs"] = {"partition_label": "nvs", "image_artifact_id": nvs["artifact_id"]}
        result["nvs_sha256"] = nvs["sha256"]
    started = service.request("/sessions", payload=request)
    session_id = started["session_id"]
    session = f"/sessions/{session_id}"
    result["session_id"] = session_id
    result["firmware_sha256"] = imported["firmware_id"]
    result["runtime"] = started["runtime"]
    result["runtime_memory"] = started["runtime_memory"]

    try:
        exercise(args, service, session, result)
        result["result"] = "PASS"
    except Exception as error:
        result["result"] = "FAIL"
        result["error"] = str(error)
        raise
    finally:
        try:
            evidence = service.request(session + "/evidence", binary=True)
            (args.output_dir / "evidence.zip").write_bytes(evidence)
            result["evidence_zip_sha256"] = sha256(evidence)
        finally:
            stopped = service.request(session + "?purge=0", method="DELETE")
            result["stopped_state"] = stopped["state"]
            result["flash_retained"] = stopped.get("flash_retained")
            save(args.output_dir / "summary.json", result)


if __name__ == "__main__":
    main()
