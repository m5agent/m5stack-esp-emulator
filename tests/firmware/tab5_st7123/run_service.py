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
        evidence = api(session + "/evidence?include=manifest,serial,logs")
        with ZipFile(io.BytesIO(evidence)) as bundle:
            assert bundle.testzip() is None
        (args.output / "serial.log").write_text(serial)
        (args.output / "evidence.zip").write_bytes(evidence)
        summary.update(no_input_no_irq=True, guest_reports=reports, evidence_zip_sha256=sha(evidence),
                       serial_sha256=sha(serial.encode()), status="PASS",
                       runtime_sha256=tab5["runtime_sha256"], part_sha256=tab5["touch_part_sha256"])
    finally:
        stopped = api(session + "?purge=0&retain_flash=0", "DELETE")
        assert stopped["state"] == "stopped" and not stopped["flash_retained"]
        assert api("/worker")["active_lease_count"] == baseline_leases
        summary["cleanup"] = {"stopped": True, "flash_released": True, "lease_count_restored": True}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
