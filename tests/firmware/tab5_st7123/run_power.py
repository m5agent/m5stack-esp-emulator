#!/usr/bin/env python3
"""Check unchanged Arduventure power-off and restart through Device Service."""

import argparse
import io
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

from run_service import sha


ORIGINAL_SHA = "e2f228813b719b81c47a8deaa7576f1b83e61e950c6178c5cf570bfaca7b8616"
FLASH_SHA = "0922e46d70edc11d285fd3d4023a18f061d4d95fd8e7a1729e00702cc3dba063"
TITLE_SHA = "b132be51149e62583817538364084b4f31f31f16b54e9f8c89313dd861bc4348"
POWER_OFF_SHA = "84f04dbb5fa1edffcd6acd0977b33aab77d99b8d03bfc951c38d50217f4c0097"
ENABLED = {"latched": False, "chip_enabled": True, "latched_at_guest_ns": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="isolated local /api/v1 endpoint")
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.port in {8787, 8830}:
        parser.error("use a separate loopback Device Service worker")
    token = args.token_file.read_text().strip()
    firmware = args.firmware.read_bytes()
    if sha(firmware) != ORIGINAL_SHA:
        parser.error("the Arduventure 1.0.0 upload SHA-256 does not match")
    args.output.mkdir(mode=0o700)

    def api(path, method="GET", payload=None, *, raw=None):
        headers = {"Authorization": "Bearer " + token}
        if payload is not None:
            raw = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        elif raw is not None:
            headers.update({"Content-Type": "application/octet-stream", "X-Artifact-Name": args.firmware.name})
        request = Request(args.base_url.rstrip("/") + path, data=raw, headers=headers, method=method)
        with urlopen(request, timeout=60) as response:
            data = response.read()
            return json.loads(data) if response.headers.get_content_type() == "application/json" else data

    artifact = api("/artifacts", "POST", raw=firmware)
    assert artifact["sha256"] == ORIGINAL_SHA
    image = api("/firmware/import", "POST", {"device_id": "tab5", "artifact_id": ORIGINAL_SHA})
    assert image["sha256"] == FLASH_SHA
    baseline_leases = api("/worker")["active_lease_count"]
    opened = api("/sessions", "POST", {
        "device_id": "tab5", "firmware_id": image["firmware_id"], "ttl_seconds": 180,
    })
    session = "/sessions/" + opened["session_id"]
    summary = {"original_sha256": ORIGINAL_SHA, "execution_flash_sha256": FLASH_SHA, "status": "FAIL"}

    def frame(expected):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                png = api(session + "/frame.png?max_age_ms=0&orient=panel")
            except HTTPError as error:
                if error.code != 409:
                    raise
            else:
                if sha(png) == expected:
                    return png
            time.sleep(0.2)
        raise AssertionError("expected native Tab5 frame was not captured")

    def input_event(x, y, *, hold=False):
        payload = {"kind": "touch", "x": x, "y": y}
        if hold:
            payload.update(action="hold", seconds=3)
        return api(session + "/input", "POST", payload)

    def expect_powered_off(x, y, *, hold=False):
        try:
            input_event(x, y, hold=hold)
        except HTTPError as error:
            assert error.code == 409 and json.load(error)["error"]["code"] == "tab5_guest_powered_off"
        else:
            raise AssertionError("missing power-off input receipt")

    def power_state():
        return api(session + "/device-state")["components"]["power"]["properties"]

    def serial():
        return api(session + "/serial?limit=65536")["data"]

    try:
        frame(TITLE_SHA)
        snapshot = api(session)
        model = snapshot["flash"]["tab5"]
        assert snapshot["device_state_supported"]
        assert model["symbols_status"] == "unavailable" and model["power_model"] == "esp-emu-tab5-standby-latch"
        assert power_state() == ENABLED
        assert input_event(672, 53)["controller_reports"] == {"reports": 2, "acknowledged": 2}
        assert input_event(660, 1100, hold=True)["controller_reports"] == {"reports": 2, "acknowledged": 2}
        assert power_state() == ENABLED
        expect_powered_off(672, 53, hold=True)
        expect_powered_off(660, 1100)
        shutdown_frame = frame(POWER_OFF_SHA)
        power = power_state()
        assert power["latched"] is True and power["chip_enabled"] is False
        assert power["latched_at_guest_ns"] > 0
        console = serial()
        time.sleep(2.4)
        assert serial() == console and "HP_SYS_HP_WDT_RESET" not in console
        evidence = api(session + "/evidence?include=manifest,serial,frames,device-state")
        with ZipFile(io.BytesIO(evidence)) as bundle:
            assert bundle.testzip() is None
            state_bytes = bundle.read("device-state.json")
            assert json.loads(state_bytes)["components"]["power"]["properties"] == power
            assert json.loads(bundle.read("manifest.json"))["files"]["device-state.json"]["sha256"] == sha(state_bytes)
        assert api(session + "/reset", "POST")["reset"]
        frame(TITLE_SHA)
        assert power_state() == ENABLED and "M5Tab5 detected ST7123 display" in serial()
        (args.output / "power-off.png").write_bytes(shutdown_frame)
        (args.output / "evidence.zip").write_bytes(evidence)
        summary.update(status="PASS", power=power, power_off_frame_sha256=sha(shutdown_frame),
                       evidence_zip_sha256=sha(evidence), runtime_sha256=model["runtime_sha256"],
                       part_sha256=model["touch_part_sha256"], restart_frame_sha256=TITLE_SHA)
    finally:
        stopped = api(session + "?purge=0&retain_flash=0", "DELETE")
        assert stopped["state"] in {"stopped", "failed"} and not stopped["flash_retained"]
        assert api("/worker")["active_lease_count"] == baseline_leases
        summary["cleaned"] = True
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
