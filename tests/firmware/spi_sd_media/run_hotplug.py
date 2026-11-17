#!/usr/bin/env python3
"""Verify GPIO48 interrupts and FAT32 state during PaperDIY SD hot-plug."""

import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

SWITCH = "/machine/et047tc1"
PROPERTY = "sd-card-present"
EXPECTED_PROOF = b"M5EMU_PAPERDIY_HOTPLUG_PERSISTED"
COMMANDS = ("0", "17", "18", "24", "25")


def digest(data):
    return sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="isolated local /api/v1 endpoint")
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--media", required=True, type=Path, help="seeded FAT32+MBR fixture")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check-write-stamp", action="store_true")
    args = parser.parse_args()
    base = urlsplit(args.base_url)
    if base.scheme != "http" or base.hostname != "127.0.0.1" or not base.port or base.port in {8787, 8830}:
        parser.error("use a separate loopback Device Service worker")
    token = args.token_file.read_text().strip()
    args.output.mkdir(mode=0o700)

    def api(path, method="GET", payload=None, file=None):
        headers = {"Authorization": "Bearer " + token}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        elif file is not None:
            headers.update({"Content-Type": "application/octet-stream", "X-Artifact-Name": file.name})
            body = file.read_bytes()
        request = Request(args.base_url.rstrip("/") + path, data=body, headers=headers, method=method)
        with urlopen(request, timeout=75) as response:
            data = response.read()
            return json.loads(data) if response.headers.get_content_type() == "application/json" else data

    capability = api("/devices/paperdiy/capabilities")["fixtures"]["sd"]
    assert capability["hotplug"]
    if args.check_write_stamp:
        assert capability.get("write_stamp") is True
    original_sd = args.media.read_bytes()
    sd = api("/artifacts", "POST", file=args.media)["artifact_id"]
    firmware = api("/artifacts", "POST", file=args.firmware)["artifact_id"]
    assert sd == digest(original_sd) and firmware == digest(args.firmware.read_bytes())
    image = api("/firmware", "POST", {"device_id": "paperdiy", "artifact_id": firmware, "kind": "merged"})
    leases_before = api("/worker")["active_lease_count"]
    opened = api("/sessions", "POST", {
        "device_id": "paperdiy", "firmware_id": image["firmware_id"], "ttl_seconds": 180,
        "storage": {"sd_image_artifact_id": sd, "sd_initially_ejected": True},
    })
    session = "/sessions/" + opened["session_id"]
    summary = {"status": "FAIL", "firmware_sha256": firmware, "source_sd_sha256": sd}
    if args.check_write_stamp:
        summary["composed_flash_sha256"] = image["sha256"]
        summary["sd_capability"] = capability

    def wait_for(marker):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            serial = api(session + "/serial?limit=65536")["data"]
            if marker in serial:
                return serial
            if "HOTPLUG_ERROR" in serial or api(session)["state"] == "failed":
                break
            time.sleep(0.15)
        raise AssertionError(f"guest missed {marker}")

    def stamp(present):
        try:
            receipt = api(session + "/storage/sd/write-stamp")
        except HTTPError as error:
            detail = json.loads(error.read())
            assert not present and error.code == 409 and detail["error"]["code"] == "sd_media_ejected", detail
            return None
        assert present and receipt["session_id"] == opened["session_id"]
        assert receipt["firmware_sha256"] == image["sha256"] and receipt["source_artifact_id"] == sd
        return receipt

    def evidence():
        package = api(session + "/evidence?include=manifest,serial,logs")
        with ZipFile(BytesIO(package)) as archive:
            assert archive.testzip() is None
            trace = archive.read("qemu.stderr").decode()
        return package, Counter(re.findall(r"^\[sd-spi\] cmd=(\d+)", trace, re.M))

    try:
        wait_for("HOTPLUG_INITIAL level=1 mount=ESP_ERR_TIMEOUT")
        if args.check_write_stamp:
            assert stamp(False) is None
        before = api(session)
        _, previous = evidence()
        assert not any(previous[command] for command in COMMANDS)
        summary["cmd_delta"] = []
        states = (
            (True, "HOTPLUG_FIRST seed=1 write=1 unmounted=1"),
            (False, "HOTPLUG_EJECTED mount=ESP_ERR_TIMEOUT"),
            (True, "HOTPLUG_REINSERT persisted=1 unmounted=1"),
            (False, "HOTPLUG_DONE"),
        )
        stamps = []
        for present, marker in states:
            api(session + "/qom", "POST", {"path": SWITCH, "property": PROPERTY, "value": present})
            pre = stamp(present) if args.check_write_stamp else None
            assert api(session + "/qom?" + urlencode({"path": SWITCH, "property": PROPERTY}))["value"] is present
            serial = wait_for(marker)
            if args.check_write_stamp:
                post = stamp(present)
                if present:
                    assert post["media_id"] == pre["media_id"]
                    stamps.append((pre, post))
            package, now = evidence()
            summary["cmd_delta"].append({command: now[command] - previous[command] for command in COMMANDS})
            previous = now
            assert api(session)["pid"] == before["pid"]
        assert re.findall(r"^HOTPLUG_IRQ generation=(\d) level=(\d)\r?$", serial, re.M) == [
            ("1", "0"), ("2", "1"), ("3", "0"), ("4", "1"),
        ]
        if args.check_write_stamp:
            (before_write, after_write), (before_read, after_read) = stamps
            summary["stamps"] = {
                "write_advanced": int(after_write["modified_ns"]) > int(before_write["modified_ns"]),
                "read_quiet": after_read["modified_ns"] == before_read["modified_ns"],
                "reinsertion_changed_identity": before_write["media_id"] != before_read["media_id"],
                "ejected_requests_rejected": True,
            }
            assert all(summary["stamps"].values()), summary["stamps"]
        first, ejected, reinserted, final = summary["cmd_delta"]
        assert first["0"] and first["17"] and first["24"]
        assert reinserted["0"] and reinserted["17"] and not reinserted["24"]
        assert not any(ejected.values()) and not any(final.values())
        with ZipFile(BytesIO(package)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            storage = json.loads(archive.read("storage/summary.json"))
        assert storage["initially_ejected"] and storage["artifact_id"] == sd
        observed = [event["value"] for event in manifest["timeline"]
                    if event.get("event") == "qom_set" and event.get("property") == PROPERTY]
        assert observed == [present for present, _ in states]
        summary.update(guest_markers=[line for line in serial.splitlines() if line.startswith("HOTPLUG_")],
                       bundle_sha256=digest(package), same_process=True)
        (args.output / "evidence.zip").write_bytes(package)
    finally:
        stopped = api(session + "?purge=0&retain_flash=0", "DELETE")
        assert stopped["state"] in {"stopped", "failed"} and not stopped["flash_retained"]
        assert api("/worker")["active_lease_count"] == leases_before
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    inventory = api(session + "/storage/sd")
    exported = api(session + "/storage/sd/export", "POST")
    assert inventory["source_artifact_id"] == sd and inventory["sha256"] == exported["artifact_id"] != sd
    assert inventory["layout"] == "mbr" and not inventory["errors"]
    files = {entry["path"]: entry["sha256"] for volume in inventory["filesystems"]
             for entry in volume["files"]}
    assert files["/FIXTURE/ROM.BIN"] == digest(b"M5EMU_SEEDED_FAT32_PAYLOAD")
    assert files["/PROOF.BIN"] == digest(EXPECTED_PROOF)
    assert digest(args.media.read_bytes()) == sd
    summary.update(status="PASS", stopped_sd_sha256=exported["artifact_id"],
                   retained_proof_sha256=digest(EXPECTED_PROOF), cleaned=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
