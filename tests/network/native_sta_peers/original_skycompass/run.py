#!/usr/bin/env python3
"""Replay the immutable SkyCompass Satellite v3.6 provisioning UI and SNTP."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "platform/tools"))
from unix_sta_peer import NTP_SECONDS, UnixStaPeer

ORIGINAL_SHA256 = "7c8ddd56e87a3b3ef5a69721b0847eb8461cb1833eb68eade918290e21894bf3"
NORMALIZED_SHA256 = "bb779820e365a47f000416e0342ef922283d94014225813f5efd7d24533fd504"
UTC_SECONDS = NTP_SECONDS - 2208988800
PORTS_IN_USE = {8787, 8790, 8830, 18853}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def wait_for(read, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := read():
            return value
        time.sleep(.25)
    raise TimeoutError("expected guest observation did not arrive")


def run(args):
    original = args.original_bin.read_bytes()
    assert digest(original) == ORIGINAL_SHA256
    qemu = args.qemu.resolve()
    assert digest(qemu.read_bytes()) == args.qemu_sha256
    out = args.out_dir.resolve()
    out.mkdir(mode=0o700)
    token = secrets.token_hex(32)
    token_file = out / "control.token"
    with token_file.open("x") as secret:
        secret.write(token)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    assert port not in PORTS_IN_USE

    def api(path, value=None, *, method=None):
        headers = {"Authorization": "Bearer " + token}
        if isinstance(value, bytes):
            headers.update({"Content-Type": "application/octet-stream",
                            "X-Artifact-Name": "skycompass-v3.6.bin"})
        elif value is not None:
            headers["Content-Type"] = "application/json"
            value = json.dumps(value).encode()
        url = f"http://127.0.0.1:{port}/api/v1/{path}"
        with urlopen(Request(url, data=value, headers=headers, method=method), timeout=30) as reply:
            payload = reply.read()
            return json.loads(payload) if "json" in reply.headers.get("Content-Type", "") else payload

    def health():
        try:
            return api("health")["ok"]
        except URLError:
            return False

    def serial():
        return api(route + "/serial?limit=1048576")["data"]

    def capture(label):
        payload = api(route + "/frame.png")
        (out / f"{label}.png").write_bytes(payload)
        image = Image.open(io.BytesIO(payload)).convert("RGB")
        return {"sha256": digest(payload), "size": image.size,
                "nonblack_pixels": sum(pixel != (0, 0, 0) for pixel in image.getdata())}

    report = {
        "status": "FAIL", "scope": "same-session original Wi-Fi DHCP, DNS and SNTP",
        "validation": "virtual-device validation", "firmware_sha256": ORIGINAL_SHA256,
        "effective_firmware_sha256": NORMALIZED_SHA256, "runtime_sha256": args.qemu_sha256,
        "rom_sha256": digest((args.rom_dir / "esp32s3_rev0_rom.bin").read_bytes()),
        "scenario": "withheld-ntp" if args.withhold_ntp else "fixed-ntp",
        "device": "cardputer-adv", "http": "NOT RUN", "hardware": "NOT RUN",
    }
    route = None
    service = None
    peer = UnixStaPeer(out / "peer.json", ntp_reply=not args.withhold_ntp)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("M5_", "M5SW_"))}
    env.update(PYTHONDONTWRITEBYTECODE="1", M5_SERVICE_ESP_EMU=str(args.esp_emu.resolve()),
               M5_QEMU_XTENSA=str(Path(__file__).with_name("strict-qemu.py").resolve()),
               M5_QEMU_XTENSA_ROM_DIR=str(args.rom_dir.resolve()), ORIGINAL_STA_QEMU=str(qemu),
               ORIGINAL_STA_TOPOLOGY=str(out / "topology.json"), ORIGINAL_STA_UNIX=str(peer.path))
    try:
        with (out / "service.log").open("wb") as log:
            service = subprocess.Popen([
                sys.executable, str(ROOT / "platform/tools/serve.py"), str(port),
                "--bind", "127.0.0.1", "--state-dir", str(out / "state"),
                "--api-token-file", str(token_file), "--max-sessions", "1",
            ], env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        wait_for(health)
        artifact = api("artifacts", original)
        assert artifact["sha256"] == ORIGINAL_SHA256
        firmware = api("firmware", {"device_id": "cardputer-adv", "kind": "merged",
                                    "artifact_id": artifact["artifact_id"]})
        assert firmware["sha256"] == NORMALIZED_SHA256
        session = api("sessions", {
            "device_id": "cardputer-adv", "firmware_id": firmware["firmware_id"],
            "runtime": "qemu-wifi", "ttl_seconds": 240, "network": {
                "profile": "generic-observe", "wifi_ssid": "fixturetest", "wifi_auth": "open",
                "http_fixture": False, "capture_pcap": True,
            },
        })
        route = "sessions/" + session["session_id"]
        live = wait_for(lambda: value if (value := api(route))["state"] == "running" else None)
        assert live["firmware_sha256"] == NORMALIZED_SHA256 and live["runtime"] == "qemu-wifi"
        executable = subprocess.check_output(["ps", "-p", str(live["pid"]), "-o", "comm="], text=True)
        assert digest(Path(executable.strip()).read_bytes()) == args.qemu_sha256
        report["live_executable_verified"] = True

        def first_frame():
            frame = capture("boot")
            return frame if frame["nonblack_pixels"] > 16 else None

        report["boot_frame"] = wait_for(first_frame, 60)
        moves = (
            ("language", {"kind": "keyboard", "key": "w", "action": "hold", "seconds": 1.2}, 5),
            ("confirm_language", {"kind": "key", "key": "ret"}, 5),
            ("wifi_scan", {"kind": "key", "key": "ret"}, 14),
            ("select_ap", {"kind": "key", "key": "ret"}, 5),
            ("connect_ap", {"kind": "key", "key": "ret"}, 2),
        )
        report["input"] = []
        for name, payload, delay in moves:
            assert api(route + "/input", payload)["accepted"]
            time.sleep(delay)
            report["input"].append({"name": name, "request": payload, "frame": capture(name)})
            if name == "wifi_scan":
                assert not peer.events

        wait_for(lambda: "WiFi Connected!" in serial(), 35)
        if args.withhold_ntp:
            wait_for(lambda: any(item["message"] == "withheld" for item in peer.events), 20)
            time.sleep(50)
        else:
            wait_for(lambda: f"Time synced to UTC: {UTC_SECONDS}" in serial(), 30)
        text = serial()
        (out / "serial.log").write_text(text)
        report["serial_sha256"] = digest(text.encode())
        report["guest_utc"] = [int(value) for value in re.findall(r"Time synced to UTC: (\d+)", text)]
        report["guest_ntp_success"] = "Time synced successfully!" in text
        report["guest_wifi_connected"] = "WiFi Connected!" in text
        assert report["guest_ntp_success"] is not args.withhold_ntp
        if not args.withhold_ntp:
            assert UTC_SECONDS in report["guest_utc"]
        else:
            assert not report["guest_utc"]
        report["topology"] = json.loads((out / "topology.json").read_text())
        package = api(route + "/evidence")
        with ZipFile(io.BytesIO(package)) as archive:
            assert archive.testzip() is None and "network/capture.pcap" in archive.namelist()
        (out / "evidence.zip").write_bytes(package)
        report["evidence_zip_sha256"] = digest(package)
        assert digest(args.original_bin.read_bytes()) == ORIGINAL_SHA256
        report["status"] = "PASS"
    finally:
        try:
            if route:
                stopped = api(route + "?purge=0&retain_flash=0", method="DELETE")
                report["cleanup"] = {"state": stopped["state"], "flash_retained": stopped.get("flash_retained"),
                                     "active_leases": api("worker")["active_lease_count"]}
                assert report["cleanup"] == {"state": "stopped", "flash_retained": False, "active_leases": 0}
                network = api(route + "/network")
                report["native_data_plane"] = network["native_data_plane"]
                assert report["native_data_plane"]["dhcpv4"]["completed_dora_transactions"] == 1
        except Exception:
            report["status"] = "FAIL"
            raise
        finally:
            if service is not None:
                service.terminate()
                service.wait(timeout=12)
            token_file.unlink()
            peer.close()
            (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report["status"] == "PASS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-bin", required=True, type=Path)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--qemu-sha256", required=True)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--esp-emu", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--withhold-ntp", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("this replay uses the macOS process sandbox")
    os.umask(0o077)
    return 0 if run(args) else 1


if __name__ == "__main__":
    raise SystemExit(main())
