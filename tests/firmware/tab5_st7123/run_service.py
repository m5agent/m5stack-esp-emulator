#!/usr/bin/env python3
"""Exercise the Tab5 ST7123 controller fixture over isolated Device Service."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile


POINTS = [(0, 1279), (719, 0), (310, 608)]
GUEST_REPORT = re.compile(r"ST7123_PROBE_(?:POINT|RELEASE)[^\r\n]+")
GUEST_CONTACT = re.compile(r"ST7123_PROBE_CONTACT samples=(\d+) duration_us=(\d+)")
DRAG_POINTS = [(0, 1279), (143, 1023), (287, 767), (431, 511), (575, 255), (719, 0)]


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="private loopback API base ending in /api/v1")
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.port in {8787, 8830}:
        parser.error("use a separate loopback Device Service worker")
    token = args.token_file.read_text().strip()
    args.output.mkdir(mode=0o700)

    def api(path, method="GET", payload=None, *, raw=None):
        headers = {"Authorization": "Bearer " + token}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            raw = json.dumps(payload).encode()
        elif raw is not None:
            headers.update({"Content-Type": "application/octet-stream", "X-Artifact-Name": args.firmware.name})
        request = Request(args.base_url.rstrip("/") + path, data=raw, headers=headers, method=method)
        with urlopen(request, timeout=35) as response:
            data = response.read()
            return json.loads(data) if response.headers.get_content_type() == "application/json" else data

    firmware = args.firmware.read_bytes()
    artifact = api("/artifacts", "POST", raw=firmware)
    assert artifact["sha256"] == sha(firmware)
    image = api("/firmware/import", "POST", {"device_id": "tab5", "artifact_id": artifact["sha256"]})
    baseline_leases = api("/worker")["active_lease_count"]
    started = api("/sessions", "POST", {
        "device_id": "tab5", "firmware_id": image["firmware_id"], "ttl_seconds": 180,
    })
    session = "/sessions/" + started["session_id"]
    summary = {"firmware_sha256": sha(firmware), "execution_flash_sha256": image["sha256"]}

    def serial_until(predicate):
        for _ in range(100):
            text = api(session + "/serial?limit=65536")["data"]
            if predicate(text):
                return text
            time.sleep(0.15)
        raise AssertionError("expected controller probe serial markers were not observed")

    try:
        before = serial_until(lambda text: "ST7123_PROBE_NO_IRQ" in text)
        assert "ST7123_PROBE_ID version=3 xmax=719 ymax=1279 slots=1" in before
        assert "ST7123_PROBE_WAIT irq=23 level=1" in before and not GUEST_REPORT.search(before)
        tab5 = api(session)["flash"]["tab5"]
        assert tab5["symbols_status"] == "unavailable" and tab5["touch_model"] == "esp-emu-st7123"
        assert tab5["execution_firmware_sha256"] == image["sha256"]
        expected = []
        for x, y in POINTS:
            receipt = api(session + "/input", "POST", {"kind": "touch", "x": x, "y": y})
            assert receipt["accepted"] and receipt["controller"] == "st7123" and receipt["raw"] == [x, y]
            assert receipt["controller_reports"] == {"reports": 2, "acknowledged": 2}
            expected.extend([
                f"ST7123_PROBE_POINT x={x} y={y} area=20 irq_level=0",
                "ST7123_PROBE_RELEASE status=0x00 irq_level=0",
            ])
        serial = serial_until(lambda text: len(GUEST_REPORT.findall(text)) >= len(expected))
        reports = GUEST_REPORT.findall(serial)
        assert reports == expected, reports
        hold = None
        if tab5.get("touch_hold_supported"):
            x, y = 240, 780
            receipt = api(session + "/input", "POST", {
                "kind": "touch", "action": "hold", "x": x, "y": y, "seconds": 1.2,
            })
            assert receipt["accepted"] and receipt["action"] == "hold" and receipt["raw"] == [x, y]
            assert receipt["controller_reports"] == {"reports": 2, "acknowledged": 2}
            timing = receipt["timing"]
            assert timing["completion"] == "guest-observed" and timing["hold_seconds"] == 1.2
            assert 1200 <= timing["guest_hold_ms"] <= 1250
            assert timing["refresh_acknowledged"] >= 3
            contacts = GUEST_CONTACT.findall(serial)
            serial = serial_until(lambda text: len(GUEST_CONTACT.findall(text)) == len(contacts) + 1)
            samples, guest_duration = map(int, GUEST_CONTACT.findall(serial)[-1])
            expected_hold = [f"ST7123_PROBE_POINT x={x} y={y} area=20 irq_level=0"] * samples
            expected_hold.append("ST7123_PROBE_RELEASE status=0x00 irq_level=0")
            assert GUEST_REPORT.findall(serial)[len(reports):] == expected_hold
            assert samples == 1 + timing["refresh_acknowledged"]
            assert 1190000 <= guest_duration <= 1260000
            hold = {"x": x, "y": y, "guest_samples": samples, "guest_duration_us": guest_duration,
                    "controller_timing": timing, "release_observed": True}
        drags = []
        if tab5.get("touch_drag_supported"):
            for positions in (DRAG_POINTS, list(reversed(DRAG_POINTS))):
                x1, y1 = positions[0]
                x2, y2 = positions[-1]
                contact_count = len(GUEST_CONTACT.findall(serial))
                report_count = len(GUEST_REPORT.findall(serial))
                offset = len(serial)
                receipt = api(session + "/input", "POST", {
                    "kind": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                })
                assert receipt["accepted"] and receipt["controller"] == "st7123"
                assert receipt["raw"] == [x1, y1, x2, y2]
                assert receipt["controller_reports"] == {"reports": 7, "acknowledged": 7}
                timing = receipt["timing"]
                assert timing["completion"] == "guest-observed" and timing["moves_acknowledged"] == 5
                assert 360 <= timing["guest_drag_ms"] <= 420
                serial = serial_until(lambda text: len(GUEST_CONTACT.findall(text)) == contact_count + 1)
                contact = GUEST_CONTACT.findall(serial)[-1]
                samples, duration_us = map(int, contact)
                expected_drag = [
                    f"ST7123_PROBE_POINT x={x} y={y} area=20 irq_level=0" for x, y in positions
                ] + ["ST7123_PROBE_RELEASE status=0x00 irq_level=0"]
                assert GUEST_REPORT.findall(serial)[report_count:] == expected_drag
                observed_drag = f"ST7123_PROBE_DRAG x1={x1} y1={y1} x2={x2} y2={y2} moves=5"
                assert observed_drag in serial[offset:]
                assert samples == 6 and 350000 <= duration_us <= 430000
                drags.append({
                    "guest_positions": positions, "guest_duration_us": duration_us,
                    "guest_drag_marker": observed_drag, "controller_timing": timing,
                    "controller_reports": receipt["controller_reports"], "release_observed": True,
                })
        evidence = api(session + "/evidence?include=manifest,serial,logs")
        with ZipFile(io.BytesIO(evidence)) as bundle:
            assert bundle.testzip() is None
        (args.output / "serial.log").write_text(serial)
        (args.output / "evidence.zip").write_bytes(evidence)
        summary.update(no_input_no_irq=True, guest_reports=reports, evidence_zip_sha256=sha(evidence),
                       serial_sha256=sha(serial.encode()), status="PASS",
                       runtime_sha256=tab5["runtime_sha256"], part_sha256=tab5["touch_part_sha256"])
        if hold is not None:
            summary["hold"] = hold
        if drags:
            summary["drags"] = drags
    finally:
        stopped = api(session + "?purge=0&retain_flash=0", "DELETE")
        assert stopped["state"] == "stopped" and not stopped["flash_retained"]
        assert api("/worker")["active_lease_count"] == baseline_leases
        summary["cleanup"] = {"stopped": True, "flash_released": True, "lease_count_restored": True}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
