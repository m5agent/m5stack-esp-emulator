#!/usr/bin/env python3
"""Verify the unchanged AirMouseS3 release through a dedicated Device Service."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SOURCE_SHA = "bdb567de990ef5c2a0fd113c033b259acd17e49717c9fdb5e9cc9d3776b208d8"
FLASH_SHA = "08d4806570618bc41ab73a481d6a9d7f1e95833af735dc075344427950d8a03a"
VHCI_QOM = "/machine/peripheral/sticks3-vhci"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(args: argparse.Namespace) -> dict:
    image = args.firmware.read_bytes()
    if digest(image) != SOURCE_SHA:
        raise ValueError("firmware is not the original AirMouseS3 v1.0 release")
    base = args.base_url.rstrip("/")
    token = args.token_file.read_text().strip()

    def request(path, *, payload=None, binary=None, method=None, raw=False):
        headers = {"Authorization": f"Bearer {token}"}
        body = binary
        if binary is not None:
            headers["Content-Type"] = "application/octet-stream"
            headers["X-Artifact-Name"] = "AirMouseS3.bin"
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        req = urllib.request.Request(base + path, body, headers, method=method)
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read()
        return data if raw else json.loads(data)

    artifact = request("/artifacts", binary=image)
    if artifact["sha256"] != SOURCE_SHA:
        raise RuntimeError("uploaded bytes have a different SHA-256")
    firmware = request("/firmware", payload={
        "device_id": "sticks3", "kind": "merged", "artifact_id": artifact["artifact_id"],
    })
    if firmware["sha256"] != FLASH_SHA:
        raise RuntimeError("composed Flash has a different SHA-256")
    session = request("/sessions", payload={
        "device_id": "sticks3",
        "firmware_id": firmware["firmware_id"],
        "runtime": "qemu-ble",
        "network": {"profile": "sticks3-native-hid", "attempts": 1},
        "ready_timeout_seconds": args.ready_timeout,
        "ttl_seconds": args.ready_timeout + 90,
    })
    route = f"/sessions/{session['session_id']}"
    def counters():
        return {
            prop: request(route + "/qom?" + urllib.parse.urlencode({
                "path": VHCI_QOM, "property": prop,
            }))["value"]
            for prop in ("api-h2c-packets", "c2h-delivered", "c2h-errors", "rx-queue-depth")
        }

    evidence = None
    result = None
    try:
        deadline = time.monotonic() + args.ready_timeout + 8
        while time.monotonic() < deadline:
            state = request(route)
            if state["state"] == "running":
                break
            if state["state"] in {"failed", "exited", "stopped", "expired"}:
                raise RuntimeError(f"native HID session did not start: {state['state']} {state.get('error')}")
            time.sleep(0.2)
        else:
            raise TimeoutError("native HID peer did not subscribe")
        before = request(route + "/network")
        if before["status"] != "AWAITING_INPUT" or before["reports_observed"]:
            raise RuntimeError("HID reports arrived before BtnA input")
        before_controller = counters()
        if before_controller["api-h2c-packets"] <= 0 or before_controller["c2h-delivered"] <= 0:
            raise RuntimeError("native controller did not transfer HCI in both directions")
        frame = request(route + "/frame.png", raw=True)
        if not frame.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("connected guest frame was unavailable")

        for action in ("down", "up"):
            request(route + "/input", payload={
                "kind": "key", "key": "a", "action": action, "settle_seconds": 0.2,
            })
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            after = request(route + "/network")
            if after["status"] == "PASS":
                break
            if after["status"] == "FAIL":
                raise RuntimeError("HID peer reported a failure after BtnA input")
            time.sleep(0.2)
        else:
            raise TimeoutError("the peer did not receive two valid reports after BtnA input")

        after_controller = counters()
        if (after_controller["c2h-errors"] != 0
                or after_controller["api-h2c-packets"] < before_controller["api-h2c-packets"] + 2):
            raise RuntimeError("native controller did not carry both HID notifications")
        evidence = request(route + "/evidence?include=logs,serial,frames", raw=True)
        with zipfile.ZipFile(io.BytesIO(evidence)) as bundle:
            text = bundle.read("ble-probe.log").decode("utf-8")
        reports = re.findall(r"^BLE_HID_REPORT .* payload_hex=([0-9a-f]+)", text, re.MULTILINE)
        if reports != ["01000000", "00000000"]:
            raise RuntimeError(f"unexpected reports after BtnA down/up: {reports}")
        result = {
            "status": "PASS",
            "validation": "virtual-device",
            "source_sha256": SOURCE_SHA,
            "flash_sha256": FLASH_SHA,
            "frame_sha256": digest(frame),
            "evidence_sha256": digest(evidence),
            "negative_before_input": before["reports_observed"],
            "reports": reports,
            "controller_before_input": before_controller,
            "controller_after_input": after_controller,
            "checks": after["checks"],
        }
    finally:
        try:
            if evidence is None:
                evidence = request(route + "/evidence?include=logs,serial,frames", raw=True)
            args.evidence_out.write_bytes(evidence)
        finally:
            stopped = request(route + "?purge=0", method="DELETE")
            if result is not None:
                result["cleanup_state"] = stopped["state"]
    if result is None or result["cleanup_state"] != "stopped":
        raise RuntimeError("native HID session cleanup did not reach stopped")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="dedicated service URL ending in /api/v1")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--ready-timeout", type=int, default=60)
    args = parser.parse_args()
    port = urllib.parse.urlsplit(args.base_url).port
    if port is None or port in {8787, 8830}:
        parser.error("use a dedicated service port")
    if not 10 <= args.ready_timeout <= 120:
        parser.error("--ready-timeout must be between 10 and 120 seconds")
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
